"""Import an editable (MLOD) p3d into the scene"""

from __future__ import annotations

import json
import os
import re
import time
from array import array
from itertools import accumulate, chain
from typing import Dict, List, Optional, Tuple

import pymxs

from zasleh import formats
from zasleh.formats import WEIGHT_OF_BYTE, paa
from zasleh.formats.flags import POINT_SPECIAL_LOCKNORMAL
from zasleh.formats.meshprep import MeshData, Slot, face_uvs, flag_code, prepare, to_scene

from . import bulk, scene, settings
from . import registry as reg
from .scene import PREVIEW_EXTENSIONS, UNNAMED_POINT, set_layer_info
from .settings import default_texture_root, scratch_folder

rt = pymxs.runtime

TO_BOOL = bytes([0] + [1] * 255)
# a LOD with this many loose points gets them as one mesh, not as helpers
CLOUD_FROM = int(os.environ.get("ZASLEH_CLOUD_FROM", "1000"))

timing: Dict[str, float] = {}       # seconds per stage of the last import, for the report


class _Timed:
    def __init__(self, stage: str):
        self.stage = stage

    def __enter__(self):
        self.started = time.perf_counter()

    def __exit__(self, *_error):
        timing[self.stage] = timing.get(self.stage, 0.0) + time.perf_counter() - self.started

_MAXSCRIPT = r'''
fn zaslehBuildMesh verts tris quads matIds groups objName =
(
    local m = mesh vertices:verts faces:tris name:objName
    for q in quads do
    (
        setEdgeVis m q 3 false
        setEdgeVis m (q + 1) 1 false
    )
    for f = 1 to tris.count do
    (
        setFaceMatID m f matIds[f]
        setFaceSmoothGroup m f groups[f]
    )
    m
)
fn zaslehSetChannel m ch mverts mtris =
(
    if (meshop.getNumMaps m) <= ch do meshop.setNumMaps m (ch + 1) keep:true
    meshop.setMapSupport m ch true
    meshop.setNumMapVerts m ch mverts.count
    for i = 1 to mverts.count do meshop.setMapVert m ch i mverts[i]
    for f = 1 to mtris.count do meshop.setMapFace m ch f mtris[f]
)
-- A data channel given as changes to the plain one: a map vert per mesh vert, all zero
fn zaslehSetSparseChannel m ch baseIdx baseVals extraVals triIdx triVals =
(
    if (meshop.getNumMaps m) <= ch do meshop.setNumMaps m (ch + 1) keep:true
    meshop.setMapSupport m ch true
    meshop.defaultMapFaces m ch
    local nv = m.numverts
    -- shrinking and growing the vert list again leaves it zeroed
    meshop.setNumMapVerts m ch 1 keep:false
    meshop.setNumMapVerts m ch nv keep:false
    local clean = true
    for i in #(1, nv / 2 + 1, nv) while clean do
        if (length (meshop.getMapVert m ch i)) != 0 do clean = false
    if not clean do for i = 1 to nv do meshop.setMapVert m ch i [0, 0, 0]
    for k = 1 to baseIdx.count do meshop.setMapVert m ch baseIdx[k] baseVals[k]
    if extraVals.count > 0 do
    (
        meshop.setNumMapVerts m ch (nv + extraVals.count) keep:true
        for k = 1 to extraVals.count do meshop.setMapVert m ch (nv + k) extraVals[k]
    )
    for k = 1 to triIdx.count do meshop.setMapFace m ch triIdx[k] triVals[k]
)
'''
_defined = False


def define_maxscript() -> None:
    global _defined
    scene.define_maxscript()
    if not _defined:
        rt.execute(_MAXSCRIPT)
        _defined = True


class _Weights:
    """Selection bytes seen as weights, w/o building a list per selection"""

    __slots__ = ("data",)

    def __init__(self, data):
        self.data = data

    def __getitem__(self, index: int) -> float:
        return WEIGHT_OF_BYTE[self.data[index]]


class _FaceFlags:
    __slots__ = ("data",)

    def __init__(self, data):
        self.data = data

    def __getitem__(self, index: int) -> float:
        return reg.FACE_FLAG if self.data[index] else 0.0


class _Ordinals:
    """1 + index: the place of a point or a face in the file"""

    def __getitem__(self, index: int) -> float:
        return float(index + 1)


PREVIEW_SIZE = 1024         # longer side of a .paa preview, in pixels


def preview_settings(tex_root: str) -> Tuple[bool, str, int]:
    """(make previews of .paa textures?, the folder they are kept in, their size)"""
    enabled = settings.get("paaPreview") != "0"
    folder = settings.get("previewDir") or scratch_folder("preview", tex_root)
    try:
        size = max(16, int(settings.get("previewSize") or PREVIEW_SIZE))
    except ValueError:
        size = PREVIEW_SIZE
    return enabled, folder, size


_PROCEDURAL_COLOUR = re.compile(r"^#\(\s*a?rgb[^)]*\)\s*color\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", re.I)


class _Materials:
    """One Multi/Sub-Object material for the whole model"""

    def __init__(self, model: str, tex_root: str, preview: Tuple[bool, str, int], warnings: List[str]):
        self.model = model
        self.tex_root = tex_root
        self.roots = [tex_root] + [r for r in settings.get("gameRoot").split(";") if r.strip()]
        self.preview_on, self.preview_dir, self.preview_size = preview
        self.previews = 0                    # previews written by this import
        self.warnings = warnings
        self.ids: Dict[Tuple[str, str], int] = {}
        self.pairs: List[Tuple[str, str]] = []
        self.nodes: list = []

    def id(self, texture: str, rvmat: str) -> int:
        key = (texture, rvmat)
        found = self.ids.get(key)
        if found is None:
            self.pairs.append(key)
            found = self.ids[key] = len(self.pairs)
        return found

    def _file(self, texture: str) -> Optional[str]:
        """An image 3ds Max can show for this texture: a source file lying next to the .paa"""
        if not texture or texture.startswith("#"):
            return None                              # none, or a procedural texture
        relative = texture.lstrip("\\/")
        full = extension = ""
        for folder in self.roots:               # the project first, then the game data
            full = os.path.join(folder.strip(), relative) if folder else relative
            base, extension = os.path.splitext(full)
            for candidate in PREVIEW_EXTENSIONS:
                if os.path.isfile(base + candidate):
                    return base + candidate
            if os.path.isfile(full):
                break
        if self.preview_on and extension.lower() in (".paa", ".pac") and os.path.isfile(full):
            name = "%s.%d.png" % (os.path.splitext(relative)[0].replace(":", ""), self.preview_size)
            target = os.path.join(self.preview_dir, name)
            try:
                if not (os.path.isfile(target) and os.path.getmtime(target) >= os.path.getmtime(full)):
                    paa.to_png(full, target, self.preview_size)
                    self.previews += 1
                return target
            except (paa.PaaError, OSError) as error:
                self.warnings.append("no preview of %s: %s" % (texture, error))
        return None

    def _make(self, texture: str, rvmat: str):
        name = os.path.splitext(os.path.basename(texture or rvmat))[0] or "no_texture"
        material = rt.PhysicalMaterial(name=name)
        path = self._file(texture)
        if path:
            try:
                material.base_color_map = rt.Bitmaptexture(filename=path, name=name)
                material.showInViewport = True
            except Exception:  # noqa: BLE001 - a texture Max cannot open must not stop the import
                pass
        colour = _PROCEDURAL_COLOUR.match(texture or "")
        if colour:                                   # "#(argb,8,8,3)color(r,g,b,a,co)": a plain colour
            red, green, blue = (min(1.0, float(value)) * 255.0 for value in colour.groups())
            material.base_color = rt.Color(red, green, blue)
        rt.custAttributes.add(material, rt.zaslehArmaMaterialCA)
        attributes = rt.custAttributes.get(material, rt.zaslehArmaMaterialCA)
        attributes.texture = texture
        attributes.rvmat = rvmat
        return material, name

    def assign(self) -> None:
        if not self.nodes or not self.pairs:
            return
        multi = rt.Multimaterial(numsubs=len(self.pairs), name=self.model)
        for index, (texture, rvmat) in enumerate(self.pairs):
            material, name = self._make(texture, rvmat)
            multi.materialList[index] = material
            multi.names[index] = name
        for node in self.nodes:
            node.material = multi


def arma_material(texture: str, rvmat: str, tex_root: Optional[str] = None):
    """A material that stands for a texture and an .rvmat of the game, with a picture for the viewport if one is found"""
    define_maxscript()
    tex_root = default_texture_root() if tex_root is None else tex_root
    material, _name = _Materials("", tex_root, preview_settings(tex_root), [])._make(texture, rvmat)
    return material


def _layer_for(name: str, model: str):
    manager = rt.LayerManager
    candidate = name
    counter = 1
    while True:
        layer = manager.getLayerFromName(candidate)
        if layer is None:
            return manager.newLayerFromName(candidate)
        if int(rt.zaslehLayerNodes(layer).count) == 0:
            return layer
        candidate = "%s [%s]" % (name, model) if counter == 1 else "%s [%s %d]" % (name, model, counter)
        counter += 1


def _points3(values) -> list:
    point3 = rt.Point3
    return [point3(a, b, c) for a, b, c in values]


def _triangles(tris) -> list:
    point3 = rt.Point3
    return [point3(a + 1, b + 1, c + 1) for a, b, c in tris]


class _Checks:
    """The check value of each point's group number (see registry.check_value)"""

    __slots__ = ("numbers", "cache")

    def __init__(self, numbers):
        self.numbers = numbers
        self.cache: Dict[float, float] = {0.0: 0.0}

    def __getitem__(self, index: int) -> float:
        number = self.numbers[index]
        found = self.cache.get(number)
        if found is None:
            found = self.cache[number] = reg.check_value(int(number))
        return found


def _data_slots(lod, mesh: MeshData, registry: reg.Registry, info: dict, warnings: List[str],
                face_ids: bool = True) -> Dict[int, list]:
    """{channel: [Slot or None] * 3} for everything of this LOD that lives in map channels"""
    point_count = len(lod.points)
    in_mesh = bytearray(point_count)
    for point in mesh.points:
        in_mesh[point] = 1
    # one byte per point, packed into a big integer
    mesh_bits = int.from_bytes(bytes(in_mesh), "little")
    kept_faces = bytearray(len(lod.faces))
    for face in mesh.faces:
        kept_faces[face] = 1

    channels: Dict[int, list] = {}

    def put(entry: dict, slot: Slot) -> None:
        channel, component = reg.Registry.place(entry["slot"])
        channels.setdefault(channel, [None, None, None])[component] = slot

    # plain groups go into layers: groups that share no point of the mesh share a layer
    layer_taken: List[int] = []
    layer_numbers: List[List[float]] = []
    layer_flags: List[bytearray] = []
    layer_points: List[List[int]] = []
    layer_faces: List[List[int]] = []
    group_names: List[str] = []
    plain = weighted = skipped = 0
    candidates = []
    for selection in lod.selections:
        bits = int.from_bytes(bytes(selection.weights).translate(TO_BOOL), "little") & mesh_bits
        faces = [f for f in selection.face_indices() if kept_faces[f]]
        if bits or faces:                               # else: only loose points (helpers), or empty
            candidates.append((bin(bits).count("1"), selection, bits, faces))
    candidates.sort(key=lambda item: -item[0])          # big ones first: fewer layers
    for _size, selection, bits, faces in candidates:
        weights = selection.weights
        fits_a_layer = not selection.is_weighted
        if fits_a_layer:
            for face in faces:                          # a face of the group must have all its points in it
                for point in lod.faces[face].points:
                    if not weights[point]:
                        fits_a_layer = False
                        break
                if not fits_a_layer:
                    break
        try:
            if not fits_a_layer:
                entry = registry.allocate(selection.name, reg.WEIGHTED)
                put(entry, Slot(_Weights(weights), _FaceFlags(selection.faces) if faces else None,
                                selection.point_indices(), faces if faces else None))
                weighted += 1
            else:
                number = float(registry.number(selection.name))
                for index, taken in enumerate(layer_taken):
                    if not taken & bits:
                        break
                else:
                    index = len(layer_taken)
                    registry.layer(index)               # may be one channel too many
                    layer_taken.append(0)
                    layer_numbers.append([0.0] * point_count)
                    layer_flags.append(bytearray(len(lod.faces)))
                    layer_points.append([])
                    layer_faces.append([])
                layer_taken[index] |= bits
                numbers, flags = layer_numbers[index], layer_flags[index]
                members = selection.point_indices()
                for point in members:
                    numbers[point] = number
                for face in faces:
                    flags[face] = 1
                layer_points[index] += members
                layer_faces[index] += faces
                plain += 1
            group_names.append(selection.name)
        except reg.RegistryFull:
            skipped += 1
    for index, numbers in enumerate(layer_numbers):
        channels[registry.layer(index)] = [
            Slot(numbers, None, layer_points[index]),
            Slot(_Checks(numbers), None, layer_points[index]),
            Slot(None, layer_flags[index], None, layer_faces[index]),
        ]

    try:
        put(registry.allocate(reg.POINT_ID, reg.NUMBER), Slot(_Ordinals(), None, range(point_count)))
        if face_ids:
            put(registry.allocate(reg.FACE_ID, reg.NUMBER), Slot(None, _Ordinals(), None, range(len(lod.faces))))
        masses = lod.mass
        if masses is not None and any(masses[point] for point in mesh.points):
            put(registry.allocate(reg.MASS, reg.NUMBER), Slot(masses))
        flags = lod.point_flags
        used_bits = 0
        for point in mesh.points:
            used_bits |= flags[point]
        for byte, key in enumerate(reg.POINT_FLAGS):
            if used_bits >> (8 * byte) & 0xFF:
                put(registry.allocate(key, reg.NUMBER), Slot([flag_code(f >> (8 * byte)) for f in flags]))
        if used_bits & POINT_SPECIAL_LOCKNORMAL:
            # the normal such a point keeps: the one its last face corner refers to (as O2 reads it)
            kept = [(0.0, 0.0, 0.0)] * point_count
            normal_count = len(lod.normals)
            for index in mesh.faces:
                face = lod.faces[index]
                for point, normal in zip(face.points, face.normals):
                    if flags[point] & POINT_SPECIAL_LOCKNORMAL and 0 <= normal < normal_count:
                        kept[point] = lod.normals[normal]
            for axis, key in enumerate(reg.LOCKED_NORMAL):
                put(registry.allocate(key, reg.NUMBER), Slot([vector[axis] for vector in kept]))
        used_bits = 0
        for index in mesh.faces:
            used_bits |= lod.faces[index].flags
        for byte, key in enumerate(reg.FACE_FLAGS):
            if used_bits >> (8 * byte) & 0xFF:
                put(registry.allocate(key, reg.NUMBER),
                    Slot(None, [flag_code(face.flags >> (8 * byte)) for face in lod.faces]))
    except reg.RegistryFull:
        skipped += 1

    if skipped:
        warnings.append("%s: %d selection(s) not imported - all map channels of the scene are in use"
                        % (info["lod"], skipped))
    info.update(selections=plain + weighted, weighted=weighted, layers=len(layer_numbers),
                data_channels=len(channels), selections_skipped=skipped, group_names=group_names)
    return channels


_FACE_FLAG_OF_BYTE = (0.0,) + (reg.FACE_FLAG,) * 255


def _dense(part, count: int) -> Optional[array]:
    """A slot's point or face part as one double per point / face"""
    if part is None:
        return None
    if isinstance(part, _Weights):
        return array("d", map(WEIGHT_OF_BYTE.__getitem__, part.data))
    if isinstance(part, _FaceFlags):
        return array("d", map(_FACE_FLAG_OF_BYTE.__getitem__, part.data))
    if isinstance(part, _Ordinals):
        return array("d", range(1, count + 1))
    if isinstance(part, _Checks):
        checks = {number: reg.check_value(int(number)) for number in set(part.numbers)}
        return array("d", map(checks.__getitem__, part.numbers))
    return array("d", list(part))


def _uv_arrays(lod) -> Tuple[Dict[int, array], array]:
    """({UV set: (u, v) per face corner of the file, flat}, the first corner of every face)"""
    faces = lod.faces
    offsets = array("i", accumulate(chain((0,), (face.n for face in faces))))
    corners = offsets[-1]
    sets = lod.uvsets
    if sets:                    # as Object Builder
        flat = {uvset.index: array("f", chain.from_iterable(uvset.uvs)) for uvset in sets}
    else:
        flat = {0: array("f", chain.from_iterable(chain.from_iterable(face.uvs for face in faces)))}
    for values in flat.values():
        if len(values) < 2 * corners:                   # a tag cut short: the rest is zero
            values.extend(bytes(4 * (2 * corners - len(values))))
    return flat, offsets


def _fill_fast(node, lod, mesh: MeshData, global_ids: List[int], slot_table: list,
               info: dict, warnings: List[str]) -> set:
    """Fill an empty Editable Mesh through the bulk helper: whole arrays at a time"""
    session = bulk.Session(node, mesh.verts, mesh.points, mesh.tris, mesh.tri_face, mesh.tri_corners)
    # the SDK's face flags: all three edges visible, the material id (0-based) from bit 16 up
    flags = array("I", [7 | ((global_ids[local - 1] - 1) << 16) for local in mesh.mat_ids])
    for quad in mesh.quads:                 # the diagonal of a quad: edge 3 of its first tri
        flags[quad] &= 0xFFFFFFFB           # edge 1 of its second
        flags[quad + 1] &= 0xFFFFFFFE
    session.geometry(array("I", mesh.groups), flags)
    written = set()
    with _Timed("uv"):
        flat_sets, offsets = _uv_arrays(lod)
        precise = None
        for set_index, flat in sorted(flat_sets.items()):
            if not 0 <= set_index <= 7:
                warnings.append("%s: UV set %d ignored (only sets 0..7 are supported)" % (info["lod"], set_index))
                continue
            if mesh.dropped:                # look at the faces of the mesh only, as the slow way does
                precise = precise or face_uvs(lod)
                used = any(u or v for face in mesh.faces for u, v in precise[set_index][face])
            else:
                used = any(flat)
            if used:                        # all zero (geometry LODs): nothing to keep
                session.uv(set_index + 1, flat, offsets)
                written.add(set_index + 1)
    with _Timed("selections: write"):
        points, faces = len(lod.points), len(lod.faces)
        for channel_index, slots in slot_table:
            slots = (list(slots) + [None, None, None])[:3]
            session.data(channel_index,
                         [_dense(slot.point_part, points) if slot is not None else None for slot in slots],
                         [_dense(slot.face_part, faces) if slot is not None else None for slot in slots])
            written.add(channel_index)
    return written


def _fill_slow(lod, mesh: MeshData, name: str, global_ids: List[int], slot_table: list,
               info: dict, warnings: List[str]):
    """The same mesh through MAXScript, an element at a time"""
    node = rt.zaslehBuildMesh(
        _points3(mesh.verts), _triangles(mesh.tris), [quad + 1 for quad in mesh.quads],
        [global_ids[local - 1] for local in mesh.mat_ids],
        [group - 0x100000000 if group >= 0x80000000 else group for group in mesh.groups],
        name)
    written = set()
    for set_index, per_face in sorted(face_uvs(lod).items()):
        if not 0 <= set_index <= 7:
            warnings.append("%s: UV set %d ignored (only sets 0..7 are supported)" % (info["lod"], set_index))
            continue
        if not any(u or v for face in mesh.faces for u, v in per_face[face]):
            continue                                   # all zero (geometry LODs): nothing to keep
        channel = mesh.uv_channel(per_face)
        rt.zaslehSetChannel(node, set_index + 1, _points3(channel.verts), _triangles(channel.tris))
        written.add(set_index + 1)
    point3 = rt.Point3
    for channel_index, slots in slot_table:
        sparse = mesh.sparse_channel(slots)
        changed = sorted(sparse.tris.items())
        rt.zaslehSetSparseChannel(
            node, channel_index,
            [vertex + 1 for vertex in sparse.base], [point3(*value) for value in sparse.base.values()],
            [point3(*value) for value in sparse.extra],
            [tri + 1 for tri, _corners in changed],
            [point3(a + 1, b + 1, c + 1) for _tri, (a, b, c) in changed])
        written.add(channel_index)
    return node, written


def _build_mesh(lod, mesh: MeshData, name: str, registry: reg.Registry, materials: _Materials,
                info: dict, warnings: List[str], face_ids: bool = True):
    global_ids = [materials.id(texture, rvmat) for texture, rvmat in mesh.materials]
    with _Timed("selections: sort out"):
        slot_table = sorted(_data_slots(lod, mesh, registry, info, warnings, face_ids).items())

    node = None
    written: set = set()
    if bulk.available():
        node = bulk.new_node(name)
        mark = len(warnings)
        try:
            with _Timed("max: fill"):
                written = _fill_fast(node, lod, mesh, global_ids, slot_table, info, warnings)
        except Exception as problem:  # noqa: BLE001 - whatever went wrong, the MAXScript way still works
            rt.delete(node)
            node = None
            del warnings[mark:]
            bulk.disable(str(problem))
            warnings.append("fast mesh building failed (%s); the rest of the import takes the slow way"
                            % str(problem).replace("\n", " ")[:200])
    if node is None:
        with _Timed("max: fill (slow)"):
            node, written = _fill_slow(lod, mesh, name, global_ids, slot_table, info, warnings)
    uv_channels = sum(1 for channel_index in written if channel_index <= 8)
    # raising the channel count makes Max fill the channels in between with a default mapping
    for channel_index in range(1, int(rt.meshop.getNumMaps(node))):
        if channel_index not in written:
            rt.meshop.setMapSupport(node, channel_index, False)

    with _Timed("max: to poly"):
        rt.update(node)
        node = rt.convertToPoly(node)
    info.update(uv_channels=uv_channels, mesh_verts=int(rt.polyop.getNumVerts(node)),
                mesh_faces=int(rt.polyop.getNumFaces(node)) - mesh.carriers)
    if mesh.carriers:
        info["cloud_points"] = mesh.carriers
        node.vertexTicks = True                 # the loose points have no visible face
    rt.setAppData(node, reg.GROUPS_APPDATA_ID, json.dumps(info.pop("group_names", [])))
    # Where faces meet in ways an Editable Poly can't hold (three on one edge...)
    if info["mesh_faces"] != len(mesh.faces):
        warnings.append("%s: %d quad(s) became two triangles each (3ds Max could not join them)"
                        % (info["lod"], info["mesh_faces"] - len(mesh.faces)))
    # the object itself isn't a selection (the exporter reads this)
    rt.setUserProp(node, "zasleh_nosel", True)
    materials.nodes.append(node)
    return node


def _build_helpers(lod, loose: List[int], layer, info: dict) -> None:
    if not loose:
        return
    names_at: Dict[int, List[str]] = {point: [] for point in loose}
    bytes_at: Dict[int, List[int]] = {point: [] for point in loose}
    for selection in lod.selections:
        weights = selection.weights
        for point in loose:
            if weights[point]:
                names_at[point].append(selection.name)
                bytes_at[point].append(weights[point])
    masses = lod.mass
    red = rt.color(255, 0, 0)
    for point in loose:
        names = names_at[point]
        node = rt.Point(pos=rt.Point3(*to_scene(lod.points[point])), name=names[0] if names else UNNAMED_POINT,
                        size=10, centermarker=True, axistripod=False, cross=False, box=False,
                        constantscreensize=True, wirecolor=red)
        rt.setUserProp(node, "zasleh_point", point + 1)        # its place in the file, kept on export
        if not names:
            rt.setUserProp(node, "zasleh_nosel", True)
        elif any(byte != 1 for byte in bytes_at[point]):
            # weighted: [name, weight byte] pairs
            rt.setUserProp(node, "zasleh_sels", json.dumps([list(pair) for pair in zip(names, bytes_at[point])]))
        elif len(names) > 1:
            rt.setUserProp(node, "zasleh_sels", json.dumps(names))
        if lod.point_flags[point]:
            rt.setUserProp(node, "zasleh_flags", lod.point_flags[point])
        if masses is not None and masses[point]:
            rt.setUserProp(node, "zasleh_mass", masses[point])
        layer.addNode(node)
    info["helpers"] = len(loose)


def _import_lod(lod, model: str, registry: reg.Registry, materials: _Materials, warnings: List[str],
                face_ids: bool = True) -> dict:
    name = formats.lod_name(lod.resolution)
    layer = _layer_for(name, model)
    info = {"lod": name, "layer": str(layer.name), "points": len(lod.points), "faces": len(lod.faces)}
    with _Timed("prepare"):
        mesh = prepare(lod, CLOUD_FROM, accel=bulk if bulk.available() else None)
    info.update(dropped_faces=mesh.dropped, smoothing_wrong=mesh.smoothing_wrong)
    if mesh.dropped:
        warnings.append("%s: %d degenerate face(s) skipped" % (name, mesh.dropped))
    if mesh.smoothing_wrong:
        warnings.append("%s: %d point(s) will be shaded differently (smoothing groups cannot follow "
                        "the sharp edges there)" % (name, mesh.smoothing_wrong))
    if mesh.tris:
        layer.addNode(_build_mesh(lod, mesh, "%s_%s" % (model, name), registry, materials, info, warnings, face_ids))
    with _Timed("max: helpers"):
        _build_helpers(lod, mesh.loose, layer, info)
    set_layer_info(layer, {
        "model": model,
        "resolution": repr(lod.resolution),
        "properties": [[p.key, p.value] for p in lod.properties],
        "selections": [s.name for s in lod.selections],     # the file's order, to write them back alike
        "uv_sets": sorted(tagg.index for tagg in lod.uvsets),
    })
    return info


def import_p3d(path: str, tex_root: Optional[str] = None, preview: Optional[bool] = None,
               preview_dir: Optional[str] = None, preview_size: Optional[int] = None, face_ids: bool = True) -> dict:
    """Import a p3d file. face_ids: every face keeps its number in the file, so that a LOD taken apart
    into objects (parts.py, or Detach by hand) is written back with its faces in the file's order."""
    started = time.perf_counter()
    timing.clear()
    with _Timed("read"):
        p3d = formats.read(path)
    define_maxscript()
    model = os.path.splitext(os.path.basename(path))[0]
    registry = reg.Registry.load()
    tex_root = default_texture_root() if tex_root is None else tex_root
    enabled, folder, size = preview_settings(tex_root)
    chosen = (enabled if preview is None else preview, preview_dir or folder, preview_size or size)
    report = {"file": path, "model": model, "lods": [], "warnings": list(p3d.warnings)}
    materials = _Materials(model, tex_root, chosen, report["warnings"])
    with pymxs.undo(False):
        for lod in p3d.lods:
            report["lods"].append(_import_lod(lod, model, registry, materials, report["warnings"], face_ids))
        with _Timed("materials"):
            materials.assign()
        registry.save()
    report["materials"] = len(materials.pairs)
    report["fast"] = bulk.available()
    if not report["fast"] and os.environ.get("ZASLEH_BULK") != "0":
        report["warnings"].append("the fast mesh builder could not be used, so the import took the slow way (%s)"
                                  % bulk.error.replace("\n", " ")[:200])
    report["previews"] = materials.previews
    report["preview_dir"] = chosen[1]
    report["slots_used"] = len(registry.slots)
    report["seconds"] = round(time.perf_counter() - started, 2)
    report["timing"] = {stage: round(seconds, 2) for stage, seconds in timing.items()}
    return report


def summary(report: dict) -> str:
    lines = ["%s: %d LOD(s), %d material(s), %.1f s" % (
        report["model"], len(report["lods"]), report["materials"], report["seconds"])]
    for info in report["lods"]:
        parts = ["%d points" % info["points"], "%d faces" % info["faces"]]
        if info.get("selections"):
            parts.append("%d selections" % info["selections"])
        if info.get("helpers"):
            parts.append("%d helpers" % info["helpers"])
        if info.get("cloud_points"):
            parts.append("%d loose points in the mesh" % info["cloud_points"])
        lines.append("  %-28s %s" % (info["layer"], ", ".join(parts)))
    if report.get("previews"):
        lines.append("%d texture preview(s) made in %s" % (report["previews"], report["preview_dir"]))
    if report["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        lines += ["  " + warning for warning in report["warnings"][:15]]
        if len(report["warnings"]) > 15:
            lines.append("  ... and %d more" % (len(report["warnings"]) - 15))
    return "\n".join(lines)
