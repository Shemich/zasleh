"""Lossless reader / writer for Arma (Real Virtuality) editable models: MLOD .p3d"""

from __future__ import annotations

import re
import struct
import sys
from typing import Callable, List, Optional, Sequence, Tuple

__all__ = [
    "DEFAULT_ENCODING", "MLOD_VERSION", "LOD_VERSION", "WEIGHT_OF_BYTE",
    "P3DError", "P3D", "LOD", "Face",
    "Tagg", "Selection", "SharpEdges", "Property", "Mass", "UVSet", "Animation",
    "weight_to_byte", "read", "loads", "write", "dumps",
]

MLOD_MAGIC = b"MLOD"
MLOD_VERSION = 0x101
LOD_MAGIC = b"P3DM"
LOD_VERSION = 0x100
LOD_HEAD_SIZE = 28
TAGG_MAGIC = b"TAGG"
EOF_NAME = "#EndOfFile#"

_LOD_HEAD = struct.Struct("<4s6i")      # magic, headSize
_POINT = struct.Struct("<3fI")
_NORMAL = struct.Struct("<3f")
_FACE = struct.Struct("<i" + "2i2f" * 4 + "I")
_FACE_SIZE = _FACE.size                 # 72
_I32 = struct.Struct("<i")
_F32 = struct.Struct("<f")

Vec3 = Tuple[float, float, float]
UV = Tuple[float, float]


class P3DError(ValueError):
    """The data isn't a readable MLOD p3d, or the model can't be written"""


def _ansi_codepage() -> str:
    # Object Builder is an ANSI application: names are in the system code page.
    if sys.platform == "win32":
        try:
            import codecs
            import ctypes
            name = "cp%d" % ctypes.windll.kernel32.GetACP()
            codecs.lookup(name)
            return name
        except Exception:
            pass
    return "cp1252"


# code page of the names when the caller gives none
DEFAULT_ENCODING = _ansi_codepage()

# weight of a selection byte, see weight_to_byte
WEIGHT_OF_BYTE = tuple(((-b) & 0xFF) / 255.0 for b in range(256))


def weight_to_byte(weight: float) -> int:
    """Selection byte for a weight"""
    w = int(round(weight * 255.0))
    w = 0 if w < 0 else 255 if w > 255 else w
    return (-w) & 0xFF


# Faces

class Face:
    """One poly (3 or 4 corners)"""

    __slots__ = ("n", "v", "flags", "texture", "material")

    def __init__(self, n: int, v: tuple, flags: int = 0, texture: str = "", material: str = ""):
        self.n = n
        self.v = v
        self.flags = flags
        self.texture = texture
        self.material = material

    @classmethod
    def new(cls, points: Sequence[int], normals: Sequence[int], uvs: Sequence[UV] = (),
            flags: int = 0, texture: str = "", material: str = "") -> "Face":
        n = len(points)
        if n not in (3, 4) or len(normals) != n or (uvs and len(uvs) != n):
            raise P3DError("a face needs 3 or 4 corners, with one normal (and one uv) per corner")
        v: list = []
        for i in range(4):
            if i < n:
                u, w = uvs[i] if uvs else (0.0, 0.0)
                v += (points[i], normals[i], u, w)
            else:
                v += (0, 0, 0.0, 0.0)
        return cls(n, tuple(v), flags, texture, material)

    @property
    def points(self) -> tuple:
        return self.v[0:4 * self.n:4]

    @property
    def normals(self) -> tuple:
        return self.v[1:4 * self.n:4]

    @property
    def uvs(self) -> tuple:
        v = self.v
        return tuple(zip(v[2:4 * self.n:4], v[3:4 * self.n:4]))

    def __repr__(self) -> str:
        return "Face(%r, texture=%r, material=%r)" % (self.points, self.texture, self.material)


# TAGGs

class _TaggBase:
    __slots__ = ("name", "_fixed_name")

    def __init__(self, name: str):
        self.name = name
        self._fixed_name: Optional[bytes] = None    # raw 64-byte name of an old style tag header

    def _payload(self, lod: "LOD", enc: Callable[[str], bytes]) -> bytes:
        raise NotImplementedError

    def __repr__(self) -> str:
        return "%s(%r)" % (type(self).__name__, self.name)


class Tagg(_TaggBase):
    """A tag whose payload isn't interpreted (unknown tag, or unexpected size)"""

    __slots__ = ("data",)

    def __init__(self, name: str, data: bytes = b""):
        super().__init__(name)
        self.data = bytes(data)

    def _payload(self, lod, enc) -> bytes:
        return self.data


# finding the members of a selection: a selection is mostly zeros
_NONZERO = re.compile(rb"[^\x00]")


class Selection(_TaggBase):
    """Named selection: one byte per point (see WEIGHT_OF_BYTE) and one per face"""

    __slots__ = ("weights", "faces")

    def __init__(self, name: str, weights: bytes = b"", faces: bytes = b""):
        super().__init__(name)
        self.weights = bytearray(weights)
        self.faces = bytearray(faces)

    @property
    def is_named(self) -> bool:
        return not self.name.startswith("#")

    @property
    def is_weighted(self) -> bool:
        """True if any point has a weight other than 0 or 1"""
        return bool(self.weights.translate(None, b"\x00\x01"))

    def point_indices(self) -> List[int]:
        return [match.start() for match in _NONZERO.finditer(self.weights)]

    def face_indices(self) -> List[int]:
        return [match.start() for match in _NONZERO.finditer(self.faces)]

    def point_weights(self) -> List[float]:
        table = WEIGHT_OF_BYTE
        return [table[b] for b in self.weights]

    def _payload(self, lod, enc) -> bytes:
        if len(self.weights) != len(lod.points) or len(self.faces) != len(lod.faces):
            raise P3DError("selection %r has %d point / %d face entries, the LOD has %d points / %d faces"
                           % (self.name, len(self.weights), len(self.faces), len(lod.points), len(lod.faces)))
        return bytes(self.weights) + bytes(self.faces)


class SharpEdges(_TaggBase):
    """Hard edges, as pairs of point indices"""

    __slots__ = ("edges",)
    NAME = "#SharpEdges#"

    def __init__(self, edges: Sequence[Tuple[int, int]] = (), name: str = NAME):
        super().__init__(name)
        self.edges = list(edges)

    def _payload(self, lod, enc) -> bytes:
        flat = [i for edge in self.edges for i in edge]
        return struct.pack("<%di" % len(flat), *flat)


class Property(_TaggBase):
    """LOD named property: two zero padded 64-byte fields"""

    __slots__ = ("key", "value", "_raw")
    NAME = "#Property#"
    FIELD = 64

    def __init__(self, key: str, value: str = "", name: str = NAME):
        super().__init__(name)
        self.key = key
        self.value = value
        self._raw: Optional[bytes] = None       # payload as read, reused while key/value are unchanged

    @staticmethod
    def _split(raw: bytes) -> Tuple[bytes, bytes]:
        field = Property.FIELD
        return raw[:field].split(b"\0", 1)[0], raw[field:].split(b"\0", 1)[0]

    @classmethod
    def _from_payload(cls, raw: bytes, dec: Callable[[bytes], str], name: str) -> "Property":
        key, value = cls._split(raw)
        prop = cls(dec(key), dec(value), name)
        prop._raw = raw
        return prop

    def _payload(self, lod, enc) -> bytes:
        key, value = enc(self.key), enc(self.value)
        if self._raw is not None and self._split(self._raw) == (key, value):
            return self._raw
        if len(key) >= self.FIELD or len(value) >= self.FIELD:
            raise P3DError("property %r = %r: name and value are limited to %d characters"
                           % (self.key, self.value, self.FIELD - 1))
        return key.ljust(self.FIELD, b"\0") + value.ljust(self.FIELD, b"\0")

    def __repr__(self) -> str:
        return "Property(%r, %r)" % (self.key, self.value)


class Mass(_TaggBase):
    """Mass of every point (Geometry LODs)"""

    __slots__ = ("masses",)
    NAME = "#Mass#"

    def __init__(self, masses: Sequence[float] = (), name: str = NAME):
        super().__init__(name)
        self.masses = list(masses)

    def _payload(self, lod, enc) -> bytes:
        if len(self.masses) != len(lod.points):
            raise P3DError("#Mass# has %d values, the LOD has %d points" % (len(self.masses), len(lod.points)))
        return struct.pack("<%df" % len(self.masses), *self.masses)


class UVSet(_TaggBase):
    """UV set ``index``"""

    __slots__ = ("index", "uvs")
    NAME = "#UVSet#"

    def __init__(self, index: int = 0, uvs: Sequence[UV] = (), name: str = NAME):
        super().__init__(name)
        self.index = index
        self.uvs = list(uvs)

    def _payload(self, lod, enc) -> bytes:
        if len(self.uvs) != lod.corner_count():
            raise P3DError("#UVSet# %d has %d uvs, the LOD has %d face corners"
                           % (self.index, len(self.uvs), lod.corner_count()))
        flat = [c for uv in self.uvs for c in uv]
        return _I32.pack(self.index) + struct.pack("<%df" % len(flat), *flat)


class Animation(_TaggBase):
    """Vert animation key frame (OFP era): a time and a position per point"""

    __slots__ = ("time", "points")
    NAME = "#Animation#"

    def __init__(self, time: float = 0.0, points: Sequence[Vec3] = (), name: str = NAME):
        super().__init__(name)
        self.time = time
        self.points = list(points)

    def _payload(self, lod, enc) -> bytes:
        if len(self.points) != len(lod.points):
            raise P3DError("#Animation# has %d positions, the LOD has %d points"
                           % (len(self.points), len(lod.points)))
        flat = [c for p in self.points for c in p]
        return _F32.pack(self.time) + struct.pack("<%df" % len(flat), *flat)


_STATE_TAGS = ("#selected#", "#lock#", "#hide#")


# LOD / file

class LOD:
    """One level of detail: points, normals, faces and an ordered list of tags"""

    def __init__(self, resolution: float = 0.0):
        self.resolution = resolution
        self.points: List[Vec3] = []
        self.point_flags: List[int] = []        # parallel to points
        self.normals: List[Vec3] = []
        self.faces: List[Face] = []
        self.taggs: List[_TaggBase] = []        # in file order, w/o #EndOfFile#
        self.version = LOD_VERSION
        self.flags = 0
        self.head_extra = b""                   # header bytes beyond the 28 known ones
        self._eof = Tagg(EOF_NAME)

    # views over the tag list

    def find(self, cls: type) -> Optional[_TaggBase]:
        """First tag of the given class, or None"""
        for tagg in self.taggs:
            if type(tagg) is cls:
                return tagg
        return None

    @property
    def selections(self) -> List[Selection]:
        return [t for t in self.taggs if type(t) is Selection and t.is_named]

    def selection(self, name: str) -> Optional[Selection]:
        """Named selection by name (case-insensitive, like the engine)"""
        key = name.lower()
        for tagg in self.taggs:
            if type(tagg) is Selection and tagg.name.lower() == key:
                return tagg
        return None

    @property
    def properties(self) -> List[Property]:
        return [t for t in self.taggs if type(t) is Property]

    def get_property(self, key: str, default: Optional[str] = None) -> Optional[str]:
        key = key.lower()
        for tagg in self.taggs:
            if type(tagg) is Property and tagg.key.lower() == key:
                return tagg.value
        return default

    @property
    def sharp_edges(self) -> List[Tuple[int, int]]:
        tagg = self.find(SharpEdges)
        return tagg.edges if tagg is not None else []

    @property
    def mass(self) -> Optional[List[float]]:
        tagg = self.find(Mass)
        return tagg.masses if tagg is not None else None

    @property
    def uvsets(self) -> List[UVSet]:
        return [t for t in self.taggs if type(t) is UVSet]

    def corner_count(self) -> int:
        """Total nr of face corners, or -1 if a face isn't a tri / quad"""
        total = 0
        for face in self.faces:
            n = face.n
            if n < 0 or n > 4:
                return -1
            total += n
        return total

    def problems(self) -> List[str]:
        """Index problems a consumer has to guard against (empty list = clean)"""
        out = []
        npoints, nnormals = len(self.points), len(self.normals)
        bad_n = bad_point = bad_normal = 0
        for face in self.faces:
            n = face.n
            if n != 3 and n != 4:
                bad_n += 1
                continue
            v = face.v
            for i in range(n):
                if not 0 <= v[4 * i] < npoints:
                    bad_point += 1
                if not 0 <= v[4 * i + 1] < nnormals:
                    bad_normal += 1
        if bad_n:
            out.append("%d face(s) that are not triangles or quads" % bad_n)
        if bad_point:
            out.append("%d face corner(s) with a point index out of range" % bad_point)
        if bad_normal:
            out.append("%d face corner(s) with a normal index out of range" % bad_normal)
        bad_edge = sum(1 for a, b in self.sharp_edges if not (0 <= a < npoints and 0 <= b < npoints))
        if bad_edge:
            out.append("%d sharp edge(s) with a point index out of range" % bad_edge)
        return out

    def __repr__(self) -> str:
        return "LOD(resolution=%r, %d points, %d faces, %d taggs)" % (
            self.resolution, len(self.points), len(self.faces), len(self.taggs))


class P3D:
    """An MLOD file: a list of LODs"""

    def __init__(self):
        self.version = MLOD_VERSION
        self.lods: List[LOD] = []
        self.trailer = b""                      # bytes after the last LOD (O2 editor config)
        self.encoding = DEFAULT_ENCODING
        self.warnings: List[str] = []           # non fatal oddities found while reading

    def __repr__(self) -> str:
        return "P3D(%d LODs)" % len(self.lods)


# Reading

def _decoder(encoding: str) -> Callable[[bytes], str]:
    cache: dict = {}

    def dec(raw: bytes) -> str:
        text = cache.get(raw)
        if text is None:
            text = cache[raw] = raw.decode(encoding, "surrogateescape")
        return text

    return dec


def _decode_tagg(lod: LOD, name: str, payload: bytes, corners: int,
                 dec: Callable[[bytes], str]) -> Tuple[_TaggBase, bool]:
    """Typed tag for a payload"""
    key = name.lower()
    size = len(payload)
    npoints, nfaces = len(lod.points), len(lod.faces)

    if key in _STATE_TAGS or not key.startswith("#"):
        if size == npoints + nfaces:
            return Selection(name, payload[:npoints], payload[npoints:]), True
    elif key == "#sharpedges#":
        if size % 8 == 0:
            return SharpEdges(list(struct.iter_unpack("<2i", payload)), name), True
    elif key == "#property#":
        if size == 2 * Property.FIELD:
            return Property._from_payload(payload, dec, name), True
    elif key == "#mass#":
        if size == 4 * npoints:
            return Mass(struct.unpack("<%df" % npoints, payload), name), True
    elif key == "#uvset#":
        if corners >= 0 and size == 4 + 8 * corners:
            (index,) = _I32.unpack_from(payload, 0)
            return UVSet(index, list(struct.iter_unpack("<2f", payload[4:])), name), True
    elif key == "#animation#":
        if size == 4 + 12 * npoints:
            (time,) = _F32.unpack_from(payload, 0)
            return Animation(time, list(struct.iter_unpack("<3f", payload[4:])), name), True
    else:
        return Tagg(name, payload), True        # a tag we don't know: kept raw
    return Tagg(name, payload), False


def _read_lod(data: bytes, view: memoryview, pos: int, index: int,
              dec: Callable[[bytes], str], warnings: List[str]) -> Tuple[LOD, int]:
    size = len(data)
    magic, head_size, version, npoints, nnormals, nfaces, flags = _LOD_HEAD.unpack_from(data, pos)
    if magic != LOD_MAGIC:
        if magic in (b"SP3X", b"SP3D"):
            raise P3DError("LOD %d is in the old OFP format (%s), which is not supported"
                           % (index, magic.decode("ascii")))
        raise P3DError("LOD %d: expected P3DM at offset %d, found %r" % (index, pos, magic))
    if head_size < LOD_HEAD_SIZE or npoints < 0 or nnormals < 0 or nfaces < 0:
        raise P3DError("LOD %d has a corrupt header" % index)

    lod = LOD()
    lod.version = version
    lod.flags = flags
    lod.head_extra = data[pos + LOD_HEAD_SIZE:pos + head_size]
    pos += head_size

    end = pos + 16 * npoints
    normals_end = end + 12 * nnormals
    if normals_end + nfaces * (_FACE_SIZE + 2) > size:
        raise P3DError("LOD %d is truncated" % index)
    block = view[pos:end]
    lod.points = list(struct.iter_unpack("<3f4x", block))
    lod.point_flags = [t[0] for t in struct.iter_unpack("<12xI", block)]
    lod.normals = list(_NORMAL.iter_unpack(view[end:normals_end]))
    pos = normals_end

    faces = lod.faces
    append = faces.append
    unpack = _FACE.unpack_from
    find = data.find
    corners = 0
    for _ in range(nfaces):
        vals = unpack(data, pos)
        tex_at = pos + _FACE_SIZE
        tex_end = find(b"\0", tex_at)
        mat_end = find(b"\0", tex_end + 1)
        if tex_end < 0 or mat_end < 0:
            raise P3DError("LOD %d is truncated inside its faces" % index)
        n = vals[0]
        if corners >= 0:
            corners = corners + n if 0 <= n <= 4 else -1
        append(Face(n, vals[1:17], vals[17], dec(data[tex_at:tex_end]), dec(data[tex_end + 1:mat_end])))
        pos = mat_end + 1

    if data[pos:pos + 4] != TAGG_MAGIC:
        raise P3DError("LOD %d: expected TAGG at offset %d, found %r" % (index, pos, data[pos:pos + 4]))
    pos += 4
    while True:
        if pos >= size:
            raise P3DError("LOD %d: the tag list is not closed by %s" % (index, EOF_NAME))
        if data[pos] == 1:
            name_end = find(b"\0", pos + 1)
            if name_end < 0:
                raise P3DError("LOD %d is truncated inside a tag name" % index)
            raw_name = data[pos + 1:name_end]
            fixed = None
            pos = name_end + 1
        else:
            # old style header: the name sits in a fixed 64-byte field
            fixed = data[pos:pos + 64]
            raw_name = fixed.split(b"\0", 1)[0]
            pos += 64
        (tagg_size,) = _I32.unpack_from(data, pos)
        pos += 4
        if tagg_size < 0 or pos + tagg_size > size:
            raise P3DError("LOD %d: tag %r has an impossible size (%d)" % (index, raw_name, tagg_size))
        payload = data[pos:pos + tagg_size]
        pos += tagg_size
        name = dec(raw_name)
        if name.lower() == "#endoffile#":
            lod._eof = Tagg(name, payload)
            lod._eof._fixed_name = fixed
            break
        tagg, understood = _decode_tagg(lod, name, payload, corners, dec)
        if not understood:
            warnings.append("LOD %d: tag %r has an unexpected size (%d bytes), kept as raw data"
                            % (index, name, tagg_size))
        tagg._fixed_name = fixed
        lod.taggs.append(tagg)

    (lod.resolution,) = _F32.unpack_from(data, pos)
    return lod, pos + 4


def loads(data: bytes, encoding: Optional[str] = None) -> P3D:
    """Parse the contents of an MLOD p3d file"""
    data = bytes(data)
    if len(data) < 12:
        raise P3DError("too short to be a p3d file")
    magic = data[:4]
    if magic == b"ODOL":
        raise P3DError("this is a binarized (ODOL) model; only editable MLOD p3d files can be read")
    if magic != MLOD_MAGIC:
        raise P3DError("not an MLOD p3d file (starts with %r)" % magic)

    p3d = P3D()
    p3d.encoding = encoding or DEFAULT_ENCODING
    dec = _decoder(p3d.encoding)
    p3d.version, nlods = struct.unpack_from("<2i", data, 4)
    view = memoryview(data)
    pos = 12
    for index in range(nlods):
        try:
            lod, pos = _read_lod(data, view, pos, index, dec, p3d.warnings)
        except (P3DError, struct.error, IndexError) as error:
            # O2 keeps the LODs it managed to load, and so do we - except for the first one
            if index == 0:
                if isinstance(error, P3DError):
                    raise
                raise P3DError("LOD 0 is truncated") from error
            p3d.warnings.append("the file declares %d LODs but only %d are readable (%s)"
                                % (nlods, index, error))
            break
        p3d.lods.append(lod)
    p3d.trailer = data[pos:]
    return p3d


def read(path: str, encoding: Optional[str] = None) -> P3D:
    """Read an MLOD p3d file"""
    with open(path, "rb") as stream:
        return loads(stream.read(), encoding)


# Writing

def _encoder(encoding: str) -> Callable[[str], bytes]:
    cache: dict = {}

    def enc(text: str) -> bytes:
        raw = cache.get(text)
        if raw is None:
            try:
                raw = text.encode(encoding, "surrogateescape")
            except UnicodeEncodeError as error:
                raise P3DError("the name %r cannot be stored in code page %s" % (text, encoding)) from error
            if b"\0" in raw:
                raise P3DError("the name %r contains a NUL character" % text)
            cache[text] = raw
        return raw

    return enc


def _tagg_header(tagg: _TaggBase, size: int, enc: Callable[[str], bytes]) -> bytes:
    name = enc(tagg.name)
    fixed = tagg._fixed_name
    if fixed is not None and fixed.split(b"\0", 1)[0] == name:
        return fixed + _I32.pack(size)
    return b"\x01" + name + b"\0" + _I32.pack(size)


def _write_lod(out: List[bytes], lod: LOD, index: int, enc: Callable[[str], bytes]) -> None:
    npoints = len(lod.points)
    if len(lod.point_flags) != npoints:
        raise P3DError("LOD %d has %d points but %d point flags" % (index, npoints, len(lod.point_flags)))

    out.append(_LOD_HEAD.pack(LOD_MAGIC, LOD_HEAD_SIZE + len(lod.head_extra), lod.version,
                              npoints, len(lod.normals), len(lod.faces), lod.flags))
    out.append(lod.head_extra)
    try:
        pack = _POINT.pack
        out.append(b"".join([pack(p[0], p[1], p[2], f) for p, f in zip(lod.points, lod.point_flags)]))
        pack = _NORMAL.pack
        out.append(b"".join([pack(*n) for n in lod.normals]))
        pack = _FACE.pack
        out.append(b"".join([pack(f.n, *f.v, f.flags) + enc(f.texture) + b"\0" + enc(f.material) + b"\0"
                             for f in lod.faces]))

        out.append(TAGG_MAGIC)
        for tagg in lod.taggs:
            payload = tagg._payload(lod, enc)
            out.append(_tagg_header(tagg, len(payload), enc))
            out.append(payload)
        payload = lod._eof._payload(lod, enc)
        out.append(_tagg_header(lod._eof, len(payload), enc))
        out.append(payload)
        out.append(_F32.pack(lod.resolution))
    except (struct.error, OverflowError, TypeError) as error:
        raise P3DError("LOD %d holds a value that does not fit the file format: %s" % (index, error)) from error


def dumps(p3d: P3D, encoding: Optional[str] = None) -> bytes:
    """Serialize a model to the contents of an MLOD p3d file"""
    enc = _encoder(encoding or p3d.encoding)
    out: List[bytes] = [MLOD_MAGIC, struct.pack("<2i", p3d.version, len(p3d.lods))]
    for index, lod in enumerate(p3d.lods):
        _write_lod(out, lod, index, enc)
    out.append(p3d.trailer)
    return b"".join(out)


def write(p3d: P3D, path: str, encoding: Optional[str] = None) -> None:
    """Write a model as an MLOD p3d file"""
    data = dumps(p3d, encoding)
    with open(path, "wb") as stream:
        stream.write(data)
