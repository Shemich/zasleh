"""Read a LOD layer of the scene into a p3d LOD: the reading half of the exporter"""

from __future__ import annotations

import json
from itertools import accumulate, chain
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pymxs

from zasleh import formats
from zasleh.formats import LOD, Face, Mass, Property, Selection, SharpEdges, UVSet, weight_to_byte
from zasleh.formats import normals as normals_module
from zasleh.formats.flags import POINT_SPECIAL_LOCKNORMAL
from zasleh.formats.meshprep import flag_from_code, from_scene

from . import bulk
from . import registry as reg
from .scene import UNNAMED_POINT, define_maxscript, layer_info, layer_resolution, user_prop

rt = pymxs.runtime

TextureLookup = Callable[[object, int], Tuple[str, str]]


class SceneError(Exception):
    """The scene holds something a p3d can't store"""


def _channel(node, channel: int, live_faces: List[int]):
    """(map verts, map faces) of a channel, or None when the object doesn't have it"""
    polyop = rt.polyop
    if channel >= int(polyop.getNumMaps(node)) or not polyop.getMapSupport(node, channel):
        return None
    get_vert = polyop.getMapVert
    verts = []
    for index in range(1, int(polyop.getNumMapVerts(node, channel)) + 1):
        value = get_vert(node, channel, index)
        verts.append((value.x, value.y, value.z))
    get_face = polyop.getMapFace
    faces = [[int(m) - 1 for m in get_face(node, channel, f)] for f in live_faces]
    return verts, faces


class _Mesh:
    """One geometry object, read into 0-based indices local to the object"""

    def __init__(self, node, registry: reg.Registry, textures: TextureLookup):
        self.name = str(node.name)
        self._marked = user_prop(node, "nosel")      # True / False, or None when never set
        self.split = 0                                    # polys with more than 4 corners, cut up
        source, temporary = node, False
        if rt.classOf(node.baseobject) != rt.Editable_Poly or int(node.modifiers.count) > 0:
            source = rt.convertToPoly(rt.snapshot(node))
            temporary = True
        try:
            self._read(source, node, registry, textures)
            if self.ngons:
                # A p3d holds tris and quads
                self.split = self.ngons
                if not temporary:
                    source = rt.copy(node)
                    temporary = True
                limit = rt.Turn_to_Poly()
                limit.limitPolySize = True
                limit.maxPolySize = 4
                rt.addModifier(source, limit)
                source = rt.convertToPoly(source)
                self._read(source, node, registry, textures)
        finally:
            if temporary:
                rt.delete(source)

    def _read(self, node, original, registry: reg.Registry, textures: TextureLookup) -> None:
        raw = bulk.read_poly(node)
        material_ids = self._take(raw, registry) if raw is not None else None
        if material_ids is None:
            material_ids = self._read_slowly(node, registry)
        self.ngons = sum(1 for face in self.faces if len(face) not in (3, 4))

        material = original.material
        cache: Dict[int, Tuple[str, str]] = {}
        self.face_materials = []
        for material_id in material_ids:
            pair = cache.get(material_id)
            if pair is None:
                pair = cache[material_id] = textures(material, material_id)
            self.face_materials.append(pair)

        self._merge_split_points({entry["name"]: entry["kind"] for entry in registry.slots.values()})
        # Is the object a selection named after itself
        self.is_selection = (not self._marked) if self._marked is not None else not any(self.point_keys)

    def _take(self, raw, registry: reg.Registry) -> Optional[list]:
        """Everything through the bulk helper; None if it gave up (then MAXScript reads the object)"""
        try:
            positions = raw.positions                       # x, y, z per vert, world space
            self.points = list(zip(positions[0::3], positions[2::3], positions[1::3]))      # as from_scene()
            ends = list(accumulate(raw.degrees))
            spans = list(zip([0] + ends[:-1], ends))
            vertices = raw.vertices.tolist()
            self.faces = [vertices[begin:end] for begin, end in spans]
            self.groups = raw.smoothing.tolist()
            self.uv, self.slots, self.layers = {}, {}, []
            for channel in range(1, 9):
                data = raw.channel(channel)
                if data is not None:
                    verts, corners = data
                    pairs = list(zip(verts[0::3], [1.0 - v for v in verts[1::3]]))
                    flat = [pairs[m] for m in corners]
                    self.uv[channel - 1] = [tuple(flat[begin:end]) for begin, end in spans]
            for channel, entries in registry.by_channel().items():
                data = raw.channel(channel)
                if data is None:
                    continue
                for component, entry in enumerate(entries):
                    if entry is not None:
                        self.slots[entry["name"]] = raw.slot(data, component, entry["kind"] == reg.NUMBER)
            for channel in registry.layers:
                data = raw.channel(channel)
                if data is not None:
                    self.layers.append(raw.layer(data))
            return raw.material_ids.tolist()
        except Exception as problem:  # noqa: BLE001 - MAXScript still reads any object
            bulk.poly_error = str(problem).replace("\n", " ")[:300]
            return None

    def _read_slowly(self, node, registry: reg.Registry) -> list:
        """The same through MAXScript, an element at a time: any object, dead verts and faces too"""
        polyop = rt.polyop
        dead_verts = {int(i) for i in rt.zaslehBits(polyop.getDeadVerts(node))}
        dead_faces = {int(i) for i in rt.zaslehBits(polyop.getDeadFaces(node))}
        live_verts = [i for i in range(1, int(polyop.getNumVerts(node)) + 1) if i not in dead_verts]
        live_faces = [f for f in range(1, int(polyop.getNumFaces(node)) + 1) if f not in dead_faces]
        index_of = {vertex: k for k, vertex in enumerate(live_verts)}
        get_vert = polyop.getVert
        self.points = []
        for vertex in live_verts:
            position = get_vert(node, vertex)
            self.points.append(from_scene((position.x, position.y, position.z)))
        get_face = polyop.getFaceVerts
        self.faces = [[index_of[int(v)] for v in get_face(node, f)] for f in live_faces]
        get_id = polyop.getFaceMatID
        get_group = polyop.getFaceSmoothGroup
        self.groups = [int(get_group(node, f)) & 0xFFFFFFFF for f in live_faces]
        vert_count = len(self.points)

        self.uv: Dict[int, List[tuple]] = {}        # uv set index -> per face tuple of (u, v)
        for channel in range(1, 9):
            data = _channel(node, channel, live_faces)
            if data is not None:
                verts, faces = data
                self.uv[channel - 1] = [tuple((verts[m][0], 1.0 - verts[m][1]) for m in face) for face in faces]

        # slot key -> (value per point, value per face: "all corners flagged" or the face's number)
        self.slots: Dict[str, Tuple[List[float], list]] = {}
        for channel, entries in registry.by_channel().items():
            data = _channel(node, channel, live_faces)
            if data is None:
                continue
            verts, faces = data
            for component, entry in enumerate(entries):
                if entry is not None:
                    self.slots[entry["name"]] = self._decode(entry["kind"], verts, faces, component, vert_count)
        # layers: (group number per point, group number per face - 0 where the face isn't in)
        self.layers: List[Tuple[List[int], List[int]]] = []
        group_number = reg.group_number
        for channel in registry.layers:
            data = _channel(node, channel, live_faces)
            if data is None:
                continue
            verts, faces = data
            numbers = [group_number(x, y) for x, y, _z in verts]
            per_vertex = [0] * vert_count
            per_face = []
            for face, mapped in zip(self.faces, faces):
                first = numbers[mapped[0]]
                inside = first != 0
                for vertex, map_vertex in zip(face, mapped):
                    number = numbers[map_vertex]
                    if number:
                        per_vertex[vertex] = number
                    if number != first or verts[map_vertex][2] < 0.5:
                        inside = False
                per_face.append(first if inside else 0)
            self.layers.append((per_vertex, per_face))
        return [int(get_id(node, f)) for f in live_faces]

    def _decode(self, kind: str, verts, map_faces, component: int, vert_count: int):
        numeric = kind == reg.NUMBER
        per_vertex: List[Optional[float]] = [None] * vert_count
        per_face: List = []
        threshold = reg.FACE_THRESHOLD
        for face, mapped in zip(self.faces, map_faces):
            flagged = True
            first = None
            for vertex, map_vertex in zip(face, mapped):
                value = verts[map_vertex][component]
                if numeric:
                    if first is None:
                        first = value
                    if per_vertex[vertex] is None:
                        per_vertex[vertex] = value
                    continue
                if value >= threshold:
                    value -= reg.FACE_FLAG
                else:
                    flagged = False
                known = per_vertex[vertex]
                if known is None or value > known:
                    per_vertex[vertex] = value
            per_face.append(first if numeric else flagged)
        return [0.0 if value is None else value for value in per_vertex], per_face

    def _merge_split_points(self, kinds: Dict[str, str]) -> None:
        """Verts that came from one p3d point and still sit in the same place are one point"""
        ids = self.slots.get(reg.POINT_ID)
        self.point_keys: List[Optional[int]] = [None] * len(self.points)
        positions = self.points
        carrier_of: Dict[int, int] = {}                 # vert -> first vert of its zero-size tri
        for face in self.faces:
            first = positions[face[0]]
            if all(positions[vertex] == first for vertex in face[1:]):
                for vertex in face:
                    carrier_of[vertex] = face[0]
        if ids is None and not carrier_of:
            return
        merged: List[int] = []
        points: List[tuple] = []
        keys: List[Optional[int]] = []
        table: Dict[tuple, int] = {}
        for vertex, position in enumerate(self.points):
            value = ids[0][vertex] if ids is not None else 0.0
            number = int(round(value))
            original = number > 0 and abs(value - number) < 1e-3
            key = (number, position) if original else (-1, carrier_of.get(vertex, vertex))
            found = table.get(key)
            if found is None:
                found = table[key] = len(points)
                points.append(position)
                keys.append(number if original else None)
            merged.append(found)
        self.point_keys = keys
        if len(points) == len(self.points):
            return
        self.points = points
        self.faces = [[merged[vertex] for vertex in face] for face in self.faces]
        keep = [len(set(face)) == len(face) for face in self.faces]     # False: a loose point's tri
        for key, (per_vertex, per_face) in list(self.slots.items()):
            numeric = kinds[key] == reg.NUMBER
            per_point: List[Optional[float]] = [None] * len(points)
            for vertex, value in enumerate(per_vertex):
                target = merged[vertex]
                known = per_point[target]
                if known is None or (not numeric and value > known):
                    per_point[target] = value
            self.slots[key] = ([0.0 if value is None else value for value in per_point],
                               [value for value, kept in zip(per_face, keep) if kept])
        for index, (per_vertex, per_face) in enumerate(self.layers):
            per_point = [0] * len(points)
            for vertex, number in enumerate(per_vertex):
                if number:
                    per_point[merged[vertex]] = number
            self.layers[index] = (per_point, [value for value, kept in zip(per_face, keep) if kept])
        if not all(keep):
            self.faces = [face for face, kept in zip(self.faces, keep) if kept]
            self.face_materials = [value for value, kept in zip(self.face_materials, keep) if kept]
            self.groups = [value for value, kept in zip(self.groups, keep) if kept]
            self.uv = {index: [value for value, kept in zip(per_face, keep) if kept]
                       for index, per_face in self.uv.items()}


def read_layer(layer, registry: Optional[reg.Registry] = None,
               textures: Optional[TextureLookup] = None, notes: Optional[List[str]] = None) -> LOD:
    """The LOD held by a layer, complete with normals, ready to be written"""
    define_maxscript()
    registry = registry or reg.Registry.load()
    textures = textures or (lambda material, material_id: ("", ""))
    info = layer_info(layer)
    resolution = layer_resolution(layer, info)
    if resolution is None:
        raise SceneError("layer \"%s\" is not a LOD: its name is neither a number nor a LOD name" % layer.name)

    nodes = list(rt.zaslehLayerNodes(layer))
    helpers = [node for node in nodes if rt.classOf(node) == rt.Point]
    meshes = [_Mesh(node, registry, textures) for node in nodes
              if rt.superClassOf(node) == rt.GeometryClass and rt.classOf(node) != rt.Targetobject
              and user_prop(node, "display") is None]              # not what is only drawn for the eye
    ngons = ["%s (%d)" % (mesh.name, mesh.ngons) for mesh in meshes if mesh.ngons]
    if ngons:
        raise SceneError("layer \"%s\": polygons with more than 4 corners in %s could not be cut into "
                         "triangles and quads. A p3d holds triangles and quads only." % (layer.name, ", ".join(ngons)))
    if notes is not None:
        for mesh in meshes:
            if mesh.split:
                notes.append("%s: %d polygon(s) with more than 4 corners in \"%s\" were written as triangles "
                             "and quads (the scene is unchanged)" % (layer.name, mesh.split, mesh.name))

    # every point, in the order of the file it came from; new points go last
    entries: List[Tuple[int, int, int, int]] = []          # (0 keyed / 1 new, key, mesh or -1, local index)
    # a point of the file held by two objects (a part split off the LOD's mesh) is still one point
    twins: List[Tuple[int, int, int]] = []                  # (mesh, local index, the entry it is the same point as)
    seen: Dict[tuple, int] = {}
    for m, mesh in enumerate(meshes):
        for local, key in enumerate(mesh.point_keys):
            if key is None:
                entries.append((1, 0, m, local))
                continue
            first = seen.setdefault((key, mesh.points[local]), len(entries)) if len(meshes) > 1 else len(entries)
            if first == len(entries):
                entries.append((0, key, m, local))
            else:
                twins.append((m, local, first))
    for h, node in enumerate(helpers):
        key = user_prop(node, "point")
        entries.append((0, int(key), -1, h) if key else (1, 0, -1, h))
    order = sorted(range(len(entries)), key=lambda i: (entries[i][0], entries[i][1], i))
    mesh_index: List[List[int]] = [[0] * len(mesh.points) for mesh in meshes]
    helper_index = [0] * len(helpers)
    lod = LOD(resolution)
    final_of = [0] * len(entries)
    for final, i in enumerate(order):
        _new, _key, m, local = entries[i]
        final_of[i] = final
        if m >= 0:
            mesh_index[m][local] = final
            lod.points.append(meshes[m].points[local])
        else:
            helper_index[local] = final
            position = helpers[local].pos
            lod.points.append(from_scene((position.x, position.y, position.z)))
    for m, local, first in twins:
        mesh_index[m][local] = final_of[first]
    point_count = len(lod.points)
    lod.point_flags = [0] * point_count

    face_groups: List[int] = []
    face_at: List[Sequence[int]] = []                       # per mesh: where each of its faces is in the LOD
    made: List[List[Face]] = []
    for m, mesh in enumerate(meshes):
        index = mesh_index[m]
        uvs = mesh.uv.get(0)
        made.append([])
        for k, corners in enumerate(mesh.faces):
            texture, rvmat = mesh.face_materials[k]
            points = tuple(index[c] for c in corners)
            made[m].append(Face.new(points, (0,) * len(points), uvs[k] if uvs else (),
                                    texture=texture, material=rvmat))
    numbered = [mesh.slots.get(reg.FACE_ID) for mesh in meshes]
    if any(numbered):
        # the file's face numbers put the faces back in the file's order, however the LOD was taken apart
        def file_number(spot: Tuple[int, int]) -> Tuple[bool, int]:
            m, k = spot
            number = int(round(numbered[m][1][k] or 0.0)) if numbered[m] else 0
            return number <= 0, number

        spots = sorted(((m, k) for m, faces in enumerate(made) for k in range(len(faces))), key=file_number)
        face_at = [[0] * len(faces) for faces in made]
        for final, (m, k) in enumerate(spots):          # faces made since go last, in the scene's order
            face_at[m][k] = final
            lod.faces.append(made[m][k])
            face_groups.append(meshes[m].groups[k])
    else:
        for m, mesh in enumerate(meshes):
            face_at.append(range(len(lod.faces), len(lod.faces) + len(made[m])))
            lod.faces += made[m]
            face_groups += mesh.groups
    face_count = len(lod.faces)

    selections: Dict[str, Selection] = {}

    def selection(name: str) -> Selection:
        found = selections.get(name)
        if found is None:
            found = selections[name] = Selection(name, bytes(point_count), bytes(face_count))
        return found

    masses = [0.0] * point_count
    locked: Dict[int, List[float]] = {}
    for entry in sorted(registry.slots.values(), key=lambda e: e["slot"]):
        key = entry["name"]
        kind = entry["kind"]
        for m, mesh in enumerate(meshes):
            decoded = mesh.slots.get(key)
            if decoded is None:
                continue
            per_point, per_face = decoded
            index, at = mesh_index[m], face_at[m]
            if kind == reg.WEIGHTED:
                target = None
                for local, value in enumerate(per_point):
                    byte = weight_to_byte(value) if value else 0
                    if byte:
                        target = target or selection(entry["name"])
                        target.weights[index[local]] = byte
                for k, flagged in enumerate(per_face):
                    if flagged:
                        target = target or selection(entry["name"])
                        target.faces[at[k]] = 1
            elif key == reg.MASS:
                for local, value in enumerate(per_point):
                    masses[index[local]] = value
            elif key in reg.POINT_FLAGS:
                shift = 8 * reg.POINT_FLAGS.index(key)
                for local, value in enumerate(per_point):
                    lod.point_flags[index[local]] |= flag_from_code(value) << shift
            elif key in reg.FACE_FLAGS:
                shift = 8 * reg.FACE_FLAGS.index(key)
                for k, value in enumerate(per_face):
                    lod.faces[at[k]].flags |= flag_from_code(value or 0.0) << shift
            elif key in reg.LOCKED_NORMAL:
                axis = reg.LOCKED_NORMAL.index(key)
                for local, value in enumerate(per_point):
                    locked.setdefault(index[local], [0.0, 0.0, 0.0])[axis] = value

    def group(number: int, found: dict) -> Optional[Selection]:
        if number not in found:
            name = registry.name_of(number)
            found[number] = None if name is None else selection(name)
        return found[number]

    for m, mesh in enumerate(meshes):
        index, at = mesh_index[m], face_at[m]
        for per_point, per_face in mesh.layers:
            found: Dict[int, Optional[Selection]] = {}
            for local, number in enumerate(per_point):
                if number:
                    target = group(number, found)
                    if target is not None:
                        target.weights[index[local]] = 1
            for k, number in enumerate(per_face):
                if number:
                    target = group(number, found)
                    if target is not None:
                        target.faces[at[k]] = 1

    for m, mesh in enumerate(meshes):
        if mesh.is_selection:                       # scenes made for the old exporter: object = selection
            target = selection(mesh.name)
            for final in mesh_index[m]:
                target.weights[final] = 1
            for final in face_at[m]:
                target.faces[final] = 1

    for h, node in enumerate(helpers):
        point = helper_index[h]
        names: List[Tuple[str, int]] = []
        extra = user_prop(node, "sels")
        if extra:
            try:
                for item in json.loads(str(extra)):           # "name" or ["name", weight byte]
                    names.append((str(item[0]), int(item[1]) & 0xFF) if isinstance(item, list) else (str(item), 1))
            except (ValueError, IndexError, TypeError):
                names = []
        if not names and not user_prop(node, "nosel") and str(node.name) != UNNAMED_POINT:
            names = [(str(node.name), 1)]
        for name, byte in names:
            selection(name).weights[point] = byte
        flags = user_prop(node, "flags")
        if flags:
            lod.point_flags[point] = int(flags)
        mass = user_prop(node, "mass")
        if mass:
            masses[point] = float(mass)

    # tags, in the order Object Builder writes them
    sharp = sorted(bulk.sharp_edges([face.points for face in lod.faces], face_groups))
    if sharp:
        lod.taggs.append(SharpEdges(sharp))
    written = set()
    for name in info.get("selections", []):          # first the file's own order
        found = selections.get(name)
        if found is not None and name not in written:
            written.add(name)
            lod.taggs.append(found)
    for key, found in selections.items():
        if key not in written:
            lod.taggs.append(found)
    lod.taggs[:] = [t for t in lod.taggs if type(t) is not Selection or any(t.weights) or any(t.faces)]
    for key, value in info.get("properties", []):
        lod.taggs.append(Property(key, value))
    if formats.has_mass(resolution):
        lod.taggs.append(Mass(masses))
    used_sets = sorted({0} | set(info.get("uv_sets", [])) | {s for mesh in meshes for s in mesh.uv})
    for set_index in used_sets:
        of_face: List[Sequence[tuple]] = [()] * face_count
        for m, mesh in enumerate(meshes):
            per_face = mesh.uv.get(set_index)
            for k, final in enumerate(face_at[m]):
                of_face[final] = per_face[k] if per_face else ((0.0, 0.0),) * len(mesh.faces[k])
        lod.taggs.append(UVSet(set_index, chain.from_iterable(of_face)))

    lod.normals = [(0.0, 0.0, 0.0)]
    keep = {point: tuple(vector) for point, vector in locked.items()
            if lod.point_flags[point] & POINT_SPECIAL_LOCKNORMAL}
    normals_module.recalculate(lod, keep, bulk.compute_normals)
    return lod
