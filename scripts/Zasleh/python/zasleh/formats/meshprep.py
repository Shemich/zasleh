"""Turn one LOD into the flat arrays a 3D package builds a mesh from"""

from __future__ import annotations

from math import sqrt
from typing import Dict, List, Optional, Sequence, Tuple

from . import normals as normals_module
from .mlod import LOD, SharpEdges
from .smoothing import sharp_edges_from_normals, to_smoothing_groups

__all__ = ["MeshData", "Channel", "SparseChannel", "Slot", "prepare", "to_scene", "from_scene",
           "flag_code", "flag_from_code"]

Vec3 = Tuple[float, float, float]


def to_scene(point: Sequence[float]) -> Vec3:
    return (point[0], point[2], point[1])


def from_scene(point: Sequence[float]) -> Vec3:
    return (point[0], point[2], point[1])


# Flag bytes travel as floats in map channels
_CODE_OF_BYTE = tuple(float(sum(3 ** bit for bit in range(8) if byte >> bit & 1)) for byte in range(256))
_BYTE_OF_CODE = {int(code): byte for byte, code in enumerate(_CODE_OF_BYTE)}


def flag_code(byte: int) -> float:
    """The float that stands for one byte of flags"""
    return _CODE_OF_BYTE[byte & 0xFF]


def flag_from_code(value: float) -> int:
    """The byte a float stands for"""
    nearest = int(round(value))
    if abs(value - nearest) > 1e-3:
        return 0
    return _BYTE_OF_CODE.get(nearest, 0)


class Channel:
    """A map channel: its own verts, and one tri of them per mesh tri"""

    __slots__ = ("verts", "tris")

    def __init__(self):
        self.verts: List[Vec3] = []
        self.tris: List[Tuple[int, int, int]] = []


class Slot:
    """One float per face corner: point_part[p3d point] + face_part[p3d face]"""

    __slots__ = ("point_part", "face_part", "points", "faces")

    def __init__(self, point_part: Optional[Sequence[float]] = None,
                 face_part: Optional[Sequence[float]] = None,
                 points: Optional[Sequence[int]] = None, faces: Optional[Sequence[int]] = None):
        self.point_part = point_part
        self.face_part = face_part
        self.points = points
        self.faces = faces

    def nonzero_points(self) -> Sequence[int]:
        if self.point_part is None:
            return ()
        if self.points is None:
            part = self.point_part
            self.points = [i for i in range(len(part)) if part[i]]
        return self.points

    def nonzero_faces(self) -> Sequence[int]:
        if self.face_part is None:
            return ()
        if self.faces is None:
            part = self.face_part
            self.faces = [i for i in range(len(part)) if part[i]]
        return self.faces


class SparseChannel:
    """A map channel described as changes to the plain one (a map vert per mesh vert, all zero"""

    __slots__ = ("base", "extra", "tris")

    def __init__(self):
        self.base: Dict[int, tuple] = {}            # mesh vert -> value, where it isn't zero
        self.extra: List[tuple] = []                # further map verts, numbered after the mesh's
        self.tris: Dict[int, tuple] = {}            # tri -> its map verts, where they differ


class MeshData:
    def __init__(self):
        self.points: List[int] = []                 # p3d point index of every mesh vert (a point
        self.verts: List[Vec3] = []                 # scene positions
        self.faces: List[int] = []                  # p3d face index of every mesh poly
        self.tris: List[Tuple[int, int, int]] = []  # vert indices, 0-based
        self.tri_face: List[int] = []               # p3d face index of every tri
        self.tri_corners: List[Tuple[int, int, int]] = []   # which corners of that face
        self.quads: List[int] = []                  # tris k where k and k + 1 form a quad
        self.materials: List[Tuple[str, str]] = []  # (texture, rvmat), in order of first use
        self.mat_ids: List[int] = []                # per tri, 1-based
        self.groups: List[int] = []                 # smoothing groups per tri
        self.smoothing_wrong = 0                    # points the smoothing groups shade differently
        self.sharp_from_normals = False             # no #SharpEdges# tag: taken from normal indices
        self.loose: List[int] = []                  # p3d points used by no face
        self.carriers = 0                           # loose points carried by a zero-size tri each
        # (the last tris; their tri_face is -1)
        self.dropped = 0                            # faces skipped: not tri/quad, bad or repeated index
        self._verts_of_point: Optional[Dict[int, List[int]]] = None
        self._tris_of_face: Optional[Dict[int, List[int]]] = None
        self._corners_of_vertex: Optional[List[List[int]]] = None

    def verts_of_point(self) -> Dict[int, List[int]]:
        if self._verts_of_point is None:
            table: Dict[int, List[int]] = {}
            for vertex, point in enumerate(self.points):
                table.setdefault(point, []).append(vertex)
            self._verts_of_point = table
        return self._verts_of_point

    def tris_of_face(self) -> Dict[int, List[int]]:
        if self._tris_of_face is None:
            table: Dict[int, List[int]] = {}
            for tri, face in enumerate(self.tri_face):
                if face >= 0:
                    table.setdefault(face, []).append(tri)
            self._tris_of_face = table
        return self._tris_of_face

    def corners_of_vertex(self) -> List[List[int]]:
        """Per mesh vert, its tri corners as 3 * tri + corner"""
        if self._corners_of_vertex is None:
            table: List[List[int]] = [[] for _ in self.verts]
            for tri, (a, b, c) in enumerate(self.tris):
                table[a].append(3 * tri)
                table[b].append(3 * tri + 1)
                table[c].append(3 * tri + 2)
            self._corners_of_vertex = table
        return self._corners_of_vertex

    def sparse_channel(self, slots: Sequence[Optional[Slot]]) -> SparseChannel:
        """Map channel carrying up to three slots, as changes to the plain channel"""
        slots = (list(slots) + [None, None, None])[:3]
        channel = SparseChannel()
        base: Dict[int, List[float]] = {}
        verts_of_point = self.verts_of_point()
        for component, slot in enumerate(slots):
            if slot is None or slot.point_part is None:
                continue
            part = slot.point_part
            for point in slot.nonzero_points():
                value = part[point]
                for vertex in verts_of_point.get(point, ()):
                    found = base.get(vertex)
                    if found is None:
                        found = base[vertex] = [0.0, 0.0, 0.0]
                    found[component] = value

        face_values: Dict[int, List[float]] = {}
        for component, slot in enumerate(slots):
            if slot is None or slot.face_part is None:
                continue
            part = slot.face_part
            for face in slot.nonzero_faces():
                found = face_values.get(face)
                if found is None:
                    found = face_values[face] = [0.0, 0.0, 0.0]
                found[component] = part[face]
        if face_values:
            # a "code" is what a face adds to all its corners; most verts see one code only
            codes: List[tuple] = [(0.0, 0.0, 0.0)]
            code_index: Dict[tuple, int] = {codes[0]: 0}
            code_of_tri: Dict[int, int] = {}
            tris_of_face = self.tris_of_face()
            for face, triple in face_values.items():
                key = tuple(triple)
                code = code_index.get(key)
                if code is None:
                    code = code_index[key] = len(codes)
                    codes.append(key)
                for tri in tris_of_face.get(face, ()):
                    code_of_tri[tri] = code
            corners_of_vertex = self.corners_of_vertex()
            tris = self.tris
            vertex_count = len(self.verts)
            extra_index: Dict[Tuple[int, int], int] = {}
            get_code = code_of_tri.get
            for vertex in {v for tri in code_of_tri for v in tris[tri]}:
                corners = corners_of_vertex[vertex]
                seen: Dict[int, int] = {}
                for packed in corners:
                    code = get_code(packed // 3, 0)
                    seen[code] = seen.get(code, 0) + 1
                main = max(seen, key=seen.get) if len(seen) > 1 else next(iter(seen))
                weights = base.get(vertex) or (0.0, 0.0, 0.0)
                if len(seen) > 1:
                    for packed in corners:
                        tri, corner = divmod(packed, 3)
                        code = get_code(tri, 0)
                        if code != main:
                            key = (vertex, code)
                            index = extra_index.get(key)
                            if index is None:
                                index = extra_index[key] = vertex_count + len(channel.extra)
                                add = codes[code]
                                channel.extra.append((weights[0] + add[0], weights[1] + add[1], weights[2] + add[2]))
                            changed = channel.tris.get(tri)
                            if changed is None:
                                changed = channel.tris[tri] = list(tris[tri])
                            changed[corner] = index
                if main:
                    add = codes[main]
                    base[vertex] = [weights[0] + add[0], weights[1] + add[1], weights[2] + add[2]]
        channel.base = {vertex: tuple(value) for vertex, value in base.items() if value[0] or value[1] or value[2]}
        channel.tris = {tri: tuple(value) for tri, value in channel.tris.items()}
        return channel

    def uv_channel(self, uvs: Sequence[Sequence[Tuple[float, float]]]) -> Channel:
        """Map channel for one UV set"""
        channel = Channel()
        index: Dict[tuple, int] = {}
        verts = channel.verts
        nothing = ((0.0, 0.0),) * 4
        for tri, face, corners in zip(self.tris, self.tri_face, self.tri_corners):
            face_uvs = uvs[face] if face >= 0 else nothing
            out = []
            for vertex, corner in zip(tri, corners):
                u, v = face_uvs[corner]
                key = (vertex, u, v)
                found = index.get(key)
                if found is None:
                    found = index[key] = len(verts)
                    verts.append((u, 1.0 - v, 0.0))
                out.append(found)
            channel.tris.append((out[0], out[1], out[2]))
        return channel

    def data_channel(self, slots: Sequence[Optional[Slot]]) -> Channel:
        """Map channel carrying up to three slots in its x, y, z"""
        slots = (list(slots) + [None, None, None])[:3]
        point_parts = [s.point_part if s is not None else None for s in slots]
        face_parts = [s.face_part if s is not None else None for s in slots]
        channel = Channel()
        points = self.points

        def at_vertex(vertex: int) -> List[float]:
            point = points[vertex]
            return [part[point] if part is not None else 0.0 for part in point_parts]

        if not any(part is not None for part in face_parts):
            # nothing depends on the face: one map vert per mesh vert
            channel.verts = [tuple(at_vertex(vertex)) for vertex in range(len(points))]
            channel.tris = list(self.tris)
            return channel

        codes: Dict[tuple, int] = {}
        triples: List[tuple] = []
        index: Dict[Tuple[int, int], int] = {}
        verts = channel.verts
        previous_face = -1
        code = 0
        for tri, face in zip(self.tris, self.tri_face):
            if face != previous_face:
                previous_face = face
                triple = tuple(part[face] if part is not None and face >= 0 else 0.0 for part in face_parts)
                code = codes.get(triple, -1)
                if code < 0:
                    code = codes[triple] = len(triples)
                    triples.append(triple)
            out = []
            for vertex in tri:
                key = (vertex, code)
                found = index.get(key)
                if found is None:
                    found = index[key] = len(verts)
                    base = at_vertex(vertex)
                    extra = triples[code]
                    verts.append((base[0] + extra[0], base[1] + extra[1], base[2] + extra[2]))
                out.append(found)
            channel.tris.append((out[0], out[1], out[2]))
        return channel


def face_uvs(lod: LOD) -> Dict[int, List[tuple]]:
    """UV sets as {set index: per p3d face tuple of (u, v)}"""
    sets = lod.uvsets
    if not sets:
        return {0: [face.uvs for face in lod.faces]}
    out: Dict[int, List[tuple]] = {}
    for uvset in sets:
        per_face = []
        at = 0
        flat = uvset.uvs
        for face in lod.faces:
            n = face.n
            per_face.append(tuple(flat[at:at + n]))
            at += n
        out[uvset.index] = per_face
    return out


def split_into_sheets(kept: List[Tuple[int, tuple]], positions: Sequence[Vec3],
                       points_out: List[int]) -> List[List[int]]:
    """Give every face corner a mesh vert"""
    offsets = []
    total = 0
    for _index, points in kept:
        offsets.append(total)
        total += len(points)
    parent = list(range(total))

    def find(corner: int) -> int:
        root = corner
        while parent[root] != root:
            root = parent[root]
        while parent[corner] != root:
            parent[corner], corner = root, parent[corner]
        return root

    def join(first: Tuple[int, int], second: Tuple[int, int]) -> None:
        # first runs low -> high starting at its corner i1, second runs high -> low from i2
        (k1, i1), (k2, i2) = first, second
        n1, n2 = len(kept[k1][1]), len(kept[k2][1])
        for one, other in ((offsets[k1] + i1, offsets[k2] + (i2 + 1) % n2),          # both at `low`
                           (offsets[k1] + (i1 + 1) % n1, offsets[k2] + i2)):         # both at `high`
            a, b = find(one), find(other)
            if a != b:
                parent[b] = a

    normals: Dict[int, Vec3] = {}

    def normal(k: int) -> Vec3:
        found = normals.get(k)
        if found is None:
            corners = [positions[point] for point in kept[k][1]]
            x = y = z = 0.0
            for i, (ax, ay, az) in enumerate(corners):                               # Newell's method
                bx, by, bz = corners[(i + 1) % len(corners)]
                x += (ay - by) * (az + bz)
                y += (az - bz) * (ax + bx)
                z += (ax - bx) * (ay + by)
            length = sqrt(x * x + y * y + z * z) or 1.0
            found = normals[k] = (x / length, y / length, z / length)
        return found

    directed: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for k, (_index, points) in enumerate(kept):
        count = len(points)
        for i in range(count):
            directed.setdefault((points[i], points[(i + 1) % count]), []).append((k, i))
    point_sets: Dict[int, frozenset] = {}

    def same_polygon(k1: int, k2: int) -> bool:
        # the back side of a face (or most of it): never one surface with its front
        a = point_sets.get(k1) or point_sets.setdefault(k1, frozenset(kept[k1][1]))
        b = point_sets.get(k2) or point_sets.setdefault(k2, frozenset(kept[k2][1]))
        return len(a & b) >= 3

    for (low, high), forward in directed.items():
        if low > high:
            continue
        backward = directed.get((high, low))
        if backward is None:
            continue
        if len(forward) == 1 and len(backward) == 1:
            if not same_polygon(forward[0][0], backward[0][0]):
                join(forward[0], backward[0])
            continue
        pairs = []
        for f in forward:
            nf = normal(f[0])
            for b in backward:
                if not same_polygon(f[0], b[0]):
                    nb = normal(b[0])
                    pairs.append((nf[0] * nb[0] + nf[1] * nb[1] + nf[2] * nb[2], f, b))
        pairs.sort(key=lambda pair: -pair[0])
        taken = set()
        for _alike, f, b in pairs:
            if f not in taken and b not in taken:
                taken.add(f)
                taken.add(b)
                join(f, b)

    fans_of_point: Dict[int, List[int]] = {}
    seen = set()
    for k, (_index, points) in enumerate(kept):
        for i, point in enumerate(points):
            root = find(offsets[k] + i)
            if root not in seen:
                seen.add(root)
                fans_of_point.setdefault(point, []).append(root)
    vertex_of_root: Dict[int, int] = {}
    for point in sorted(fans_of_point):
        for root in fans_of_point[point]:
            vertex_of_root[root] = len(points_out)
            points_out.append(point)
    return [[vertex_of_root[find(offsets[k] + i)] for i in range(len(points))]
            for k, (_index, points) in enumerate(kept)]


def _sharp_without_tag(lod: LOD, kept: List[Tuple[int, tuple]]) -> list:
    """Sharp edges of a LOD that has no #SharpEdges# tag"""
    faces = [points for _index, points in kept]
    file_normals = [lod.faces[index].normals for index, _points in kept]
    flags = [lod.faces[index].flags for index, _points in kept]
    _vectors, computed = normals_module.compute(lod.points, lod.point_flags, faces, flags, [], {})
    forward: Dict[int, int] = {}
    backward: Dict[int, int] = {}
    for ours, theirs in zip(computed, file_normals):
        for a, b in zip(ours, theirs):
            if forward.setdefault(a, b) != b or backward.setdefault(b, a) != a:
                return list(sharp_edges_from_normals(faces, file_normals))
    return []


def prepare(lod: LOD, cloud_from: Optional[int] = None, accel=None) -> MeshData:
    """Arrays for one LOD"""
    split = accel.split_into_sheets if accel is not None else split_into_sheets
    smooth = accel.to_smoothing_groups if accel is not None else to_smoothing_groups
    mesh = MeshData()
    point_count = len(lod.points)
    used = bytearray(point_count)
    kept: List[Tuple[int, tuple]] = []
    for index, face in enumerate(lod.faces):
        n = face.n
        if n != 3 and n != 4:
            mesh.dropped += 1
            continue
        points = face.points
        if min(points) < 0 or max(points) >= point_count or len(set(points)) != n:
            mesh.dropped += 1
            continue
        kept.append((index, points))
        for point in points:
            used[point] = 1

    mesh.loose = [point for point in range(point_count) if not used[point]]
    source = lod.points
    corner_vertex = split(kept, source, mesh.points)
    mesh.verts = [to_scene(source[point]) for point in mesh.points]

    material_ids: Dict[Tuple[str, str], int] = {}
    face_points = [points for _index, points in kept]
    tagg = lod.find(SharpEdges)
    if tagg is not None:
        sharp = tagg.edges
    else:
        sharp = _sharp_without_tag(lod, kept)
        mesh.sharp_from_normals = bool(sharp)
    groups, mesh.smoothing_wrong = smooth(face_points, sharp)

    for (index, points), group, vertices in zip(kept, groups, corner_vertex):
        face = lod.faces[index]
        key = (face.texture, face.material)
        material = material_ids.get(key)
        if material is None:
            material = material_ids[key] = len(mesh.materials) + 1
            mesh.materials.append(key)
        a, b, c = vertices[0], vertices[1], vertices[2]
        mesh.faces.append(index)
        if len(points) == 4:
            mesh.quads.append(len(mesh.tris))
            mesh.tris.append((a, b, c))
            mesh.tris.append((a, c, vertices[3]))
            mesh.tri_face += (index, index)
            mesh.tri_corners += ((0, 1, 2), (0, 2, 3))
            mesh.mat_ids += (material, material)
            mesh.groups += (group, group)
        else:
            mesh.tris.append((a, b, c))
            mesh.tri_face.append(index)
            mesh.tri_corners.append((0, 1, 2))
            mesh.mat_ids.append(material)
            mesh.groups.append(group)
    if cloud_from is not None and len(mesh.loose) >= cloud_from:
        key = ("", "")
        material = material_ids.get(key)
        if material is None:
            material = material_ids[key] = len(mesh.materials) + 1
            mesh.materials.append(key)
        for point in mesh.loose:
            first = len(mesh.points)
            mesh.points += (point, point, point)
            mesh.verts += (to_scene(source[point]),) * 3
            mesh.tris.append((first, first + 1, first + 2))
            mesh.tri_face.append(-1)
            mesh.tri_corners.append((0, 1, 2))
            mesh.mat_ids.append(material)
            mesh.groups.append(0)
        mesh.carriers = len(mesh.loose)
        mesh.loose = []
    return mesh
