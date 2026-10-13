"""Named selections of an Editable Poly: assign, remove, check, undo"""

from __future__ import annotations

import contextlib
import json
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pymxs

from . import registry as reg
from .scene import COMPONENT, define_maxscript, from_bits, to_bits

rt = pymxs.runtime

_MAXSCRIPT = r'''
fn zaslehFaceVerts p = (for f = 1 to (polyop.getNumFaces p) collect (polyop.getFaceVerts p f))
fn zaslehPartFaces p faces = (for f in faces collect (polyop.getFaceVerts p f))
fn zaslehPartMapFaces p ch faces = (for f in faces collect (polyop.getMapFace p ch f))
fn zaslehGetMapVerts p ch idx = (for i in idx collect (polyop.getMapVert p ch i))
fn zaslehHasChannel p ch = ((polyop.getNumMaps p) > ch and (polyop.getMapSupport p ch))
-- a plain channel: a map vert per vert, all zero. Returns true if it had to be made.
fn zaslehEnsureChannel p ch =
(
    if zaslehHasChannel p ch then false else
    (
        if (polyop.getNumMaps p) <= ch do polyop.setNumMaps p (ch + 1) keep:true
        polyop.setMapSupport p ch true
        polyop.defaultMapFaces p ch
        for i = 1 to (polyop.getNumMapVerts p ch) do polyop.setMapVert p ch i [0, 0, 0]
        true
    )
)
-- take back what zaslehPatchChannel did: the faces get their old map faces
fn zaslehUnpatchChannel p ch faceIdx faceMaps restoreIdx restoreVals count =
(
    for k = 1 to faceIdx.count do polyop.setMapFace p ch faceIdx[k] faceMaps[k]
    for k = 1 to restoreIdx.count do polyop.setMapVert p ch restoreIdx[k] restoreVals[k]
    if (polyop.getNumMapVerts p ch) > count do polyop.setNumMapVerts p ch count keep:true
)
-- new map verts are only ever added, after the existing ones
fn zaslehPatchChannel p ch newVals faceIdx faceMaps zeroIdx =
(
    local n = polyop.getNumMapVerts p ch
    if newVals.count > 0 do
    (
        polyop.setNumMapVerts p ch (n + newVals.count) keep:true
        for k = 1 to newVals.count do polyop.setMapVert p ch (n + k) newVals[k]
    )
    for k = 1 to faceIdx.count do polyop.setMapFace p ch faceIdx[k] faceMaps[k]
    for i in zeroIdx do polyop.setMapVert p ch i [0, 0, 0]
)
-- group numbers present in a layer
fn zaslehLayerNumbers p ch =
(
    local found = #{}
    for i = 1 to (polyop.getNumMapVerts p ch) do
    (
        local x = (polyop.getMapVert p ch i).x
        if x > 0.5 do found[(x + 0.5) as integer] = true
    )
    found as array
)
-- (verts, faces) of one group in a layer
fn zaslehLayerMembers p ch number check =
(
    local verts = #{}
    local faces = #{}
    local hit = #{}
    local tolerance = 0.000001 * check + 0.000001
    for i = 1 to (polyop.getNumMapVerts p ch) do
    (
        local v = polyop.getMapVert p ch i
        if (abs (v.x - number)) < 0.0001 and (abs (v.y - check)) <= tolerance do hit[i] = true
    )
    if not hit.isEmpty do
        for f = 1 to (polyop.getNumFaces p) do
        (
            local mv = polyop.getMapFace p ch f
            local inside = true
            local gv = undefined
            for k = 1 to mv.count do
            (
                if hit[mv[k]] then
                (
                    if gv == undefined do gv = polyop.getFaceVerts p f
                    verts[gv[k]] = true
                    if (polyop.getMapVert p ch mv[k]).z < 0.5 do inside = false
                )
                else inside = false
            )
            if inside do faces[f] = true
        )
    #(verts, faces)
)
-- (verts, faces) of a weighted group: component comp (1..3) of a slot channel
fn zaslehSlotMembers p ch comp =
(
    local verts = #{}
    local faces = #{}
    for f = 1 to (polyop.getNumFaces p) do
    (
        local mv = polyop.getMapFace p ch f
        local gv = polyop.getFaceVerts p f
        local inside = true
        for k = 1 to mv.count do
        (
            local v = (polyop.getMapVert p ch mv[k])[comp]
            if v >= 1.5 then v -= 2.0 else inside = false
            if v > 0.0 do verts[gv[k]] = true
        )
        if inside do faces[f] = true
    )
    #(verts, faces)
)
fn zaslehChannelMax p ch =
(
    local top = [0, 0, 0]
    for i = 1 to (polyop.getNumMapVerts p ch) do
    (
        local v = polyop.getMapVert p ch i
        if v.x > top.x do top.x = v.x
        if v.y > top.y do top.y = v.y
        if v.z > top.z do top.z = v.z
    )
    top
)
-- A look at a whole layer, for the Check button: (verts in a group
fn zaslehLayerCheck p ch =
(
    local nv = polyop.getNumMapVerts p ch
    local numbers = for i = 1 to nv collect 0
    local low = #{}
    local bad = #{}
    for i = 1 to nv do
    (
        local v = polyop.getMapVert p ch i
        if v.z < 0.5 do low[i] = true
        if v.x > 0.0001 or v.y > 0.0001 do
        (
            local n = (v.x + 0.5) as integer
            local c = (n as float) * (n as float)
            if n >= 1 and (abs (v.x - n)) <= 0.0001 and (abs (v.y - c)) <= (0.000001 * c + 0.000001) then numbers[i] = n
            else bad[i] = true
        )
    )
    local owner = for i = 1 to (polyop.getNumVerts p) collect 0
    local grouped = #{}
    local blended = #{}
    local torn = #{}
    local openFaces = #()
    local openNumbers = #()
    local withFaces = #{}
    for f = 1 to (polyop.getNumFaces p) do
    (
        local mv = polyop.getMapFace p ch f
        if mv.count > 0 do
        (
            local gv = polyop.getFaceVerts p f
            local first = numbers[mv[1]]
            local same = first != 0
            local flagged = true
            for k = 1 to mv.count do
            (
                local m = mv[k]
                local n = numbers[m]
                if bad[m] do blended[gv[k]] = true
                if n != 0 do
                (
                    grouped[gv[k]] = true
                    if owner[gv[k]] == 0 then owner[gv[k]] = n
                    else if owner[gv[k]] != n do torn[gv[k]] = true
                )
                if n != first do same = false
                if low[m] do flagged = false
            )
            if same do
            (
                if flagged then withFaces[first] = true
                else (append openFaces f; append openNumbers first)
            )
        )
    )
    #(grouped, blended - grouped, torn, openFaces, openNumbers, withFaces)
)
-- (verts with a weight, verts with blended values only) in the listed components
fn zaslehSlotCheck p ch comps =
(
    local hit = #{}
    local bad = #{}
    for i = 1 to (polyop.getNumMapVerts p ch) do
    (
        local v = polyop.getMapVert p ch i
        for c in comps do
        (
            local w = v[c]
            if w >= 1.5 do w -= 2.0
            if w > 1.001 or w < -0.001 then bad[i] = true
            else if w > 0.0 do hit[i] = true
        )
    )
    local verts = #{}
    local blended = #{}
    if not (hit.isEmpty and bad.isEmpty) do
        for f = 1 to (polyop.getNumFaces p) do
        (
            local mv = polyop.getMapFace p ch f
            local gv = undefined
            for k = 1 to mv.count where (hit[mv[k]] or bad[mv[k]]) do
            (
                if gv == undefined do gv = polyop.getFaceVerts p f
                if hit[mv[k]] then verts[gv[k]] = true else blended[gv[k]] = true
            )
        )
    #(verts, blended - verts)
)
fn zaslehBigFaces p =
(
    local found = #{}
    for f = 1 to (polyop.getNumFaces p) where (polyop.getFaceDeg p f) > 4 do found[f] = true
    found
)
-- paint verts in a map channel of its own and show that channel as vert colours
fn zaslehShowColors p ch verts colors background =
(
    if (polyop.getNumMaps p) <= ch do polyop.setNumMaps p (ch + 1) keep:true
    polyop.setMapSupport p ch true
    polyop.defaultMapFaces p ch                 -- a map vertex per vertex, with the same number
    for i = 1 to (polyop.getNumMapVerts p ch) do polyop.setMapVert p ch i background
    for k = 1 to verts.count do polyop.setMapVert p ch verts[k] colors[k]
    p.vertexColorType = #map_channel
    p.vertexColorMapChannel = ch
    p.vertexColorsShaded = false
    p.showVertexColors = true
    redrawViews()
)
fn zaslehHideColors p ch =
(
    if (polyop.getNumMaps p) > ch and (polyop.getMapSupport p ch) do polyop.setMapSupport p ch false
    p.showVertexColors = false
    redrawViews()
)
'''
_defined = False


def define() -> None:
    global _defined
    define_maxscript()
    if not _defined:
        rt.execute(_MAXSCRIPT)
        _defined = True


class GroupError(Exception):
    """Something the user has to change"""


def _weight(value: float) -> float:
    return value - reg.FACE_FLAG if value >= reg.FACE_THRESHOLD else value


def faces_around(node, vertices: Iterable[int]) -> List[int]:
    return from_bits(rt.polyop.getFacesUsingVert(node, to_bits(vertices)))


# The panel's own undo history

HISTORY_DEPTH = 20
HISTORY_FACES = 500000                      # and no more than this many edited faces in all (memory)
_history: List[dict] = []                   # finished edits, the latest last
_recording: Optional[dict] = None           # the edit being made


def touch(node) -> None:
    """Note, once per edit, the list of groups kept on an object, before the edit changes it"""
    if _recording is not None:
        handle = int(rt.getHandleByAnim(node))
        if handle not in _recording["lists"]:
            raw = rt.getAppData(node, reg.GROUPS_APPDATA_ID)
            _recording["lists"][handle] = (node, None if raw is None else str(raw))


def _restore(entry: dict) -> None:
    """Put back what the steps of an edit replaced, the last step first"""
    point3 = rt.Point3
    for step in reversed(entry["steps"]):
        if step["kind"] == "write":
            rt.zaslehUnpatchChannel(step["node"], step["channel"], step["faces"],
                                 [rt.Array(*mapped) for mapped in step["old"]],
                                 rt.Array(*[index for index, _value in step["zeroed"]]),
                                 [point3(*value) for _index, value in step["zeroed"]], step["base"])
        else:                               # the channel was made for the edit
            rt.polyop.setMapSupport(step["node"], step["channel"], False)
    if entry["registry"] is None:
        rt.deleteAppData(rt.rootNode, reg.APPDATA_ID)
    else:
        rt.setAppData(rt.rootNode, reg.APPDATA_ID, entry["registry"])
    for node, raw in entry["lists"].values():
        if rt.isValidNode(node):
            if raw is None:
                rt.deleteAppData(node, reg.GROUPS_APPDATA_ID)
            else:
                rt.setAppData(node, reg.GROUPS_APPDATA_ID, raw)


@contextlib.contextmanager
def recorded(label: str):
    """Everything edited inside becomes one step of the panel's undo history"""
    global _recording
    raw = rt.getAppData(rt.rootNode, reg.APPDATA_ID)
    entry = _recording = {"label": label, "steps": [], "lists": {}, "registry": None if raw is None else str(raw)}
    try:
        yield
    except BaseException:
        _recording = None
        _restore(entry)
        raise
    _recording = None
    now = rt.getAppData(rt.rootNode, reg.APPDATA_ID)
    if not entry["steps"] and entry["registry"] == (None if now is None else str(now)):
        return                              # nothing was changed
    entry["size"] = sum(len(step.get("faces", ())) for step in entry["steps"])
    _history.append(entry)
    del _history[:-HISTORY_DEPTH]
    while len(_history) > 1 and sum(e["size"] for e in _history) > HISTORY_FACES:
        del _history[0]                     # whole-object edits of heavy meshes are big to keep


def undo_last() -> str:
    """Take back the latest edit made through recorded()"""
    define()
    if not _history:
        raise GroupError("Nothing to undo (only changes made with this panel are kept).")
    entry = _history[-1]
    polyop = rt.polyop
    refused = "The mesh was changed after that step, so it cannot be taken back. The panel's undo history is cleared."
    latest: Dict[tuple, dict] = {}
    for step in entry["steps"]:
        if not rt.isValidNode(step["node"]):
            del _history[:]
            raise GroupError("An object of that step is gone. The panel's undo history is cleared.")
        if step["kind"] == "write":
            latest[(int(rt.getHandleByAnim(step["node"])), step["channel"])] = step
    for step in latest.values():            # is the mesh still as the edit left it?
        node, channel = step["node"], step["channel"]
        same = (rt.zaslehHasChannel(node, channel) and
                (int(polyop.getNumVerts(node)), int(polyop.getNumFaces(node))) == step["counts"] and
                int(polyop.getNumMapVerts(node, channel)) == step["after"])
        if same:
            now = [[int(m) for m in polyop.getMapFace(node, channel, face)] for face in step["faces"]]
            same = now == step["new"]
        if not same:
            del _history[:]
            raise GroupError(refused)
    _history.pop()
    _restore(entry)
    return "Undone: %s" % entry["label"]


class Patch:
    """The corners of some faces in one map channel, for editing"""

    def __init__(self, node, channel: int, faces: List[int]):
        define()
        self.node = node
        self.channel = channel
        touch(node)
        self.created = bool(rt.zaslehEnsureChannel(node, channel))
        if self.created and _recording is not None:
            _recording["steps"].append({"kind": "channel", "node": node, "channel": channel})
        self.face_ids = faces
        bits = to_bits(faces)
        self.face_verts = [[int(v) for v in face] for face in rt.zaslehPartFaces(node, bits)]
        self.map_faces = [[int(m) for m in face] for face in rt.zaslehPartMapFaces(node, channel, bits)]
        wanted = sorted({m for face in self.map_faces for m in face})
        found = rt.zaslehGetMapVerts(node, channel, rt.Array(*wanted)) if wanted else []
        value_of = {index: (v.x, v.y, v.z) for index, v in zip(wanted, found)}
        self.original = [[value_of[m] for m in face] for face in self.map_faces]
        self.values = [[list(value) for value in face] for face in self.original]
        self._at: Optional[Dict[int, List[Tuple[int, int]]]] = None

    def corners_at(self) -> Dict[int, List[Tuple[int, int]]]:
        """vert -> [(index of the face in this patch, corner index)]"""
        if self._at is None:
            self._at = {}
            for i, face in enumerate(self.face_verts):
                for k, vertex in enumerate(face):
                    self._at.setdefault(vertex, []).append((i, k))
        return self._at

    def write(self, picked: Iterable[int] = ()) -> None:
        """Store the changed corners"""
        picked = set(picked)
        base = int(rt.polyop.getNumMapVerts(self.node, self.channel))
        new_values: List[tuple] = []
        pending: Dict[tuple, int] = {}
        face_ids, face_maps = [], []
        old_maps: List[List[int]] = []
        new_maps: List[List[int]] = []
        referenced: Set[int] = set()
        old_at_picked: Set[int] = set()
        for i, face in enumerate(self.face_verts):
            mapped = list(self.map_faces[i])
            changed = False
            for k, vertex in enumerate(face):
                value = tuple(self.values[i][k])
                if value != self.original[i][k]:
                    key = (vertex,) + value
                    index = pending.get(key)
                    if index is None:
                        new_values.append(value)
                        index = pending[key] = base + len(new_values)
                    if vertex in picked:
                        old_at_picked.add(mapped[k])
                    mapped[k] = index
                    changed = True
            referenced.update(mapped)
            if changed:
                face_ids.append(self.face_ids[i])
                face_maps.append(rt.Array(*mapped))
                old_maps.append(list(self.map_faces[i]))
                new_maps.append(mapped)
        if not face_ids:
            return
        zeroed = sorted(old_at_picked - referenced)
        if _recording is not None:
            value_of = {m: value for mapped, values in zip(self.map_faces, self.original)
                        for m, value in zip(mapped, values)}
            polyop = rt.polyop
            _recording["steps"].append({
                "kind": "write", "node": self.node, "channel": self.channel,
                "base": base, "after": base + len(new_values),
                "faces": list(face_ids), "old": old_maps, "new": new_maps,
                "zeroed": [(m, value_of[m]) for m in zeroed],
                "counts": (int(polyop.getNumVerts(self.node)), int(polyop.getNumFaces(self.node)))})
        point3 = rt.Point3
        rt.zaslehPatchChannel(self.node, self.channel, [point3(*value) for value in new_values],
                           face_ids, face_maps, rt.Array(*zeroed))

    # layer editing: x = group number, y = its check value, z = face flag

    def numbers_at(self, vertices: Iterable[int]) -> Set[int]:
        found: Set[int] = set()
        at = self.corners_at()
        for vertex in vertices:
            for i, k in at.get(vertex, ()):
                x, y, _z = self.values[i][k]
                found.add(reg.group_number(x, y))
        return found

    def layer_set(self, vertices: Iterable[int], number: int) -> None:
        check = reg.check_value(number) if number else 0.0
        at = self.corners_at()
        for vertex in vertices:
            for i, k in at.get(vertex, ()):
                triple = self.values[i][k]
                triple[0], triple[1] = float(number), check

    def layer_flag(self, positions: Iterable[int], on: bool) -> None:
        """positions: indices into this patch"""
        for i in positions:
            for triple in self.values[i]:
                triple[2] = 1.0 if on else 0.0

    def layer_faces_of(self, number: int, flagged_only: bool) -> List[int]:
        """Patch positions of the faces all of whose corners are in the group"""
        out = []
        for i, values in enumerate(self.values):
            if all(reg.group_number(t[0], t[1]) == number and (t[2] >= 0.5 or not flagged_only) for t in values):
                out.append(i)
        return out

    def layer_clear(self, number: int, vertices: Iterable[int]) -> None:
        """Take the verts out of the group"""
        at = self.corners_at()
        touched: Set[int] = set()
        for vertex in vertices:
            for i, k in at.get(vertex, ()):
                triple = self.values[i][k]
                if reg.group_number(triple[0], triple[1]) == number:
                    triple[0] = triple[1] = 0.0
                    touched.add(i)
        self.layer_flag(touched, False)

    # slot editing: value = weight + 2 if the face is in

    def slot_set(self, component: int, vertices: Iterable[int], weight: float) -> Set[int]:
        at = self.corners_at()
        touched: Set[int] = set()
        for vertex in vertices:
            for i, k in at.get(vertex, ()):
                triple = self.values[i][k]
                triple[component] = weight + (reg.FACE_FLAG if triple[component] >= reg.FACE_THRESHOLD else 0.0)
                touched.add(i)
        return touched

    def slot_flag(self, component: int, positions: Iterable[int], on: bool) -> None:
        for i in positions:
            for triple in self.values[i]:
                weight = _weight(triple[component])
                triple[component] = weight + reg.FACE_FLAG if on else weight

    def slot_full(self, component: int, positions: Iterable[int]) -> List[int]:
        return [i for i in positions if all(_weight(t[component]) > 0.0 for t in self.values[i])]

    def slot_flagged(self, component: int) -> List[int]:
        return [i for i, values in enumerate(self.values) if all(t[component] >= reg.FACE_THRESHOLD for t in values)]


# What the user has picked

def target_nodes() -> list:
    """The selected Editable Poly objects, or a GroupError saying what to select"""
    chosen = [node for node in rt.selection if rt.classOf(node) != rt.Point]
    if not chosen:
        raise GroupError("Select one Editable Poly object.")
    for node in chosen:
        if rt.classOf(node.baseobject) != rt.Editable_Poly:
            raise GroupError("\"%s\" is not an Editable Poly. Convert it first (To Editable Poly)." % node.name)
    return chosen


def target_node():
    """The single selected Editable Poly"""
    chosen = target_nodes()
    if len(chosen) != 1:
        raise GroupError("Select one Editable Poly object.")
    return chosen[0]


def picked(node) -> Tuple[str, List[int]]:
    """("verts" | "faces", 1-based indices) from the current sub-object level"""
    define()
    polyop = rt.polyop
    level = rt.subobjectLevel
    level = int(level) if level is not None else 0
    if level == 1:
        return "verts", from_bits(polyop.getVertSelection(node))
    if level in (2, 3):
        return "verts", from_bits(polyop.getVertsUsingEdge(node, polyop.getEdgeSelection(node)))
    if level in (4, 5):
        return "faces", from_bits(polyop.getFaceSelection(node))
    return "faces", list(range(1, int(polyop.getNumFaces(node)) + 1))


# Where a group is on an object

def _layers_on(node, registry: reg.Registry) -> List[int]:
    define()
    return [channel for channel in registry.layers if rt.zaslehHasChannel(node, channel)]


def _homes(node, registry: reg.Registry, number: int) -> List[int]:
    """Layers of the object in which the group has verts"""
    return [channel for channel in _layers_on(node, registry)
            if number in {int(n) for n in rt.zaslehLayerNumbers(node, channel)}]


def _layer_members(node, channel: int, number: int) -> Tuple[List[int], List[int]]:
    found = rt.zaslehLayerMembers(node, channel, float(number), reg.check_value(number))
    return from_bits(found[0]), from_bits(found[1])


def _slot_of(registry: reg.Registry, name: str) -> Optional[Tuple[int, int]]:
    entry = registry.get(name)
    if entry is None or entry["kind"] != reg.WEIGHTED:
        return None
    return reg.Registry.place(entry["slot"])


def members(node, registry: reg.Registry, name: str) -> Tuple[Set[int], Set[int]]:
    """(verts, faces) of a group on an object"""
    define()
    name = name.strip()
    verts: Set[int] = set()
    faces: Set[int] = set()
    number = registry.ids.get(name)
    slot = _slot_of(registry, name)
    if number is None and slot is None:
        raise GroupError("There is no group \"%s\"." % name)
    if number is not None:
        for channel in _layers_on(node, registry):      # a layer w/o the group answers at once
            found_verts, found_faces = _layer_members(node, channel, number)
            verts.update(found_verts)
            faces.update(found_faces)
    if slot is not None and rt.zaslehHasChannel(node, slot[0]):
        found = rt.zaslehSlotMembers(node, slot[0], slot[1] + 1)
        verts.update(from_bits(found[0]))
        faces.update(from_bits(found[1]))
    return verts, faces


def weights(node, registry: reg.Registry, name: str) -> Dict[int, float]:
    """{vert: weight} of a group on an object (1.0 for plain groups)"""
    verts, _faces = members(node, registry, name)
    out = {vertex: 1.0 for vertex in verts}
    slot = _slot_of(registry, name.strip())
    if slot is not None and rt.zaslehHasChannel(node, slot[0]) and verts:
        patch = Patch(node, slot[0], faces_around(node, verts))
        for vertex, corners in patch.corners_at().items():
            if vertex in out:
                out[vertex] = max(_weight(patch.values[i][k][slot[1]]) for i, k in corners)
    return out


# Operations

def _user_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise GroupError("Type a name for the group.")
    if name.startswith("#"):
        raise GroupError("A group name cannot start with \"#\".")
    return name


def _known(registry: reg.Registry, name: str) -> str:
    name = name.strip()
    if name not in registry.ids and _slot_of(registry, name) is None:
        raise GroupError("There is no group \"%s\"." % name)
    return name


def selection_of(node, what: Optional[str], indices: Optional[List[int]]) -> Tuple[str, List[int], List[int]]:
    """(what, indices, verts concerned)"""
    if what is None:
        what, indices = picked(node)
    if not indices:
        raise GroupError("Nothing is selected: pick vertices or polygons first.")
    if what == "verts":
        return what, list(indices), list(indices)
    return what, list(indices), from_bits(rt.polyop.getVertsUsingFace(node, to_bits(indices)))


def _layer_write(node, channel: int, number: int, vertices: List[int], faces: Optional[List[int]]) -> None:
    """Put verts into a group in a layer"""
    patch = Patch(node, channel, faces_around(node, vertices))
    patch.layer_set(vertices, number)
    if faces is None:
        patch.layer_flag(patch.layer_faces_of(number, flagged_only=False), True)
    else:
        position = {face: i for i, face in enumerate(patch.face_ids)}
        patch.layer_flag([position[face] for face in faces if face in position], True)
    patch.write(vertices)


def _free_layer(node, registry: reg.Registry, number: int, vertices: List[int], skip: Iterable[int] = ()) -> int:
    """First layer in which none of the verts is taken by another group"""
    around = faces_around(node, vertices)
    index = 0
    while True:
        try:
            channel = registry.layer(index)
        except reg.RegistryFull as error:
            raise GroupError(str(error))
        index += 1
        if channel in skip:
            continue
        if not rt.zaslehHasChannel(node, channel):
            return channel
        if Patch(node, channel, around).numbers_at(vertices) <= {0, number}:
            return channel


def _assign_plain(node, registry: reg.Registry, name: str, what: str, indices: List[int], vertices: List[int]) -> None:
    number = registry.number(name)
    faces = indices if what == "faces" else None
    homes = _homes(node, registry, number)
    if not homes:
        _layer_write(node, _free_layer(node, registry, number, vertices), number, vertices, faces)
        return
    home = homes[0]
    if Patch(node, home, faces_around(node, vertices)).numbers_at(vertices) <= {0, number}:
        _layer_write(node, home, number, vertices, faces)
        return
    # some of the verts are taken by another group in this layer: move the whole group
    old_verts, old_faces = _layer_members(node, home, number)
    target = _free_layer(node, registry, number, sorted(set(old_verts) | set(vertices)), skip=(home,))
    patch = Patch(node, home, faces_around(node, old_verts))
    patch.layer_clear(number, old_verts)
    patch.write(old_verts)
    _layer_write(node, target, number, old_verts, old_faces)
    _layer_write(node, target, number, vertices, faces)


def _to_slot(node, registry: reg.Registry, name: str) -> Tuple[int, int]:
    """Make a group a weighted one"""
    try:
        entry = registry.allocate(name, reg.WEIGHTED)
    except reg.RegistryFull as error:
        raise GroupError(str(error))
    channel, component = reg.Registry.place(entry["slot"])
    number = registry.ids.get(name)
    if number is not None:
        for home in _homes(node, registry, number):
            old_verts, old_faces = _layer_members(node, home, number)
            patch = Patch(node, home, faces_around(node, old_verts))
            patch.layer_clear(number, old_verts)
            patch.write(old_verts)
            slot_patch = Patch(node, channel, faces_around(node, old_verts))
            slot_patch.slot_set(component, old_verts, 1.0)
            position = {face: i for i, face in enumerate(slot_patch.face_ids)}
            slot_patch.slot_flag(component, [position[f] for f in old_faces if f in position], True)
            slot_patch.write(old_verts)
    return channel, component


def assign(node, registry: reg.Registry, name: str, weight: float = 1.0,
           what: Optional[str] = None, indices: Optional[List[int]] = None) -> str:
    """Put the picked verts / faces (or the whole object) into a group"""
    define()
    name = _user_name(name)
    weight = max(0.0, min(1.0, float(weight)))
    if weight <= 0.0:
        return remove(node, registry, name, what, indices)
    what, indices, vertices = selection_of(node, what, indices)
    if weight >= 1.0 and not registry.is_weighted(name):
        _assign_plain(node, registry, name, what, indices, vertices)
    else:
        channel, component = _to_slot(node, registry, name)
        patch = Patch(node, channel, faces_around(node, vertices))
        touched = patch.slot_set(component, vertices, weight)
        if what == "verts":
            patch.slot_flag(component, patch.slot_full(component, touched), True)
        else:
            position = {face: i for i, face in enumerate(patch.face_ids)}
            patch.slot_flag(component, [position[face] for face in indices], True)
        patch.write(vertices)
    _remember(node, name)
    return "%s: %d %s assigned" % (name, len(indices), "vertices" if what == "verts" else "polygons")


def remove(node, registry: reg.Registry, name: str,
           what: Optional[str] = None, indices: Optional[List[int]] = None) -> str:
    define()
    name = _known(registry, name)
    what, indices, vertices = selection_of(node, what, indices)
    around = faces_around(node, vertices)
    number = registry.ids.get(name)
    if number is not None:
        for home in _homes(node, registry, number):
            patch = Patch(node, home, around)
            if what == "verts":
                patch.layer_clear(number, vertices)
            else:
                position = {face: i for i, face in enumerate(patch.face_ids)}
                patch.layer_flag([position[face] for face in indices], False)
                kept = {v for i in patch.layer_faces_of(number, flagged_only=True) for v in patch.face_verts[i]}
                patch.layer_clear(number, [v for v in vertices if v not in kept])
            patch.write(vertices)
    slot = _slot_of(registry, name)
    if slot is not None and rt.zaslehHasChannel(node, slot[0]):
        channel, component = slot
        patch = Patch(node, channel, around)
        if what == "verts":
            patch.slot_flag(component, patch.slot_set(component, vertices, 0.0), False)
        else:
            position = {face: i for i, face in enumerate(patch.face_ids)}
            patch.slot_flag(component, [position[face] for face in indices], False)
            kept = {v for i in patch.slot_flagged(component) for v in patch.face_verts[i]}
            patch.slot_set(component, [v for v in vertices if v not in kept], 0.0)
        patch.write(vertices)
    return "%s: %d %s removed" % (name, len(indices), "vertices" if what == "verts" else "polygons")


def _wipe(node, registry: reg.Registry, name: str) -> bool:
    """Take everything the object has out of a group"""
    verts, faces = members(node, registry, name)
    if faces:                   # first the faces: a group may hold faces w/o their verts
        remove(node, registry, name, "faces", sorted(faces))
        verts, _faces = members(node, registry, name)
    if verts:
        remove(node, registry, name, "verts", sorted(verts))
    return bool(verts or faces)


def clear(node, registry: reg.Registry, name: str) -> str:
    """Take the whole object out of a group"""
    define()
    name = _known(registry, name)
    _wipe(node, registry, name)
    _forget(node, name)
    return "%s: removed from this object" % name


def redefine(node, registry: reg.Registry, name: str, weight: float = 1.0,
             what: Optional[str] = None, indices: Optional[List[int]] = None) -> str:
    """Make the group, on this object, exactly the picked verts / faces"""
    define()
    name = _user_name(name)
    if float(weight) <= 0.0:
        raise GroupError("Weight 0 means \"not in the group\": use Clear to empty the group.")
    what, indices, _vertices = selection_of(node, what, indices)
    if name in registry.ids or _slot_of(registry, name) is not None:
        _wipe(node, registry, name)
    assign(node, registry, name, weight, what, indices)
    return "%s: now the %d picked %s" % (name, len(indices), "vertices" if what == "verts" else "polygons")


def delete(registry: reg.Registry, name: str) -> str:
    """Take a group out of every object of the scene"""
    define()
    name = _known(registry, name)
    edited = other = helpers = 0
    for node in list(rt.objects):
        if rt.classOf(node) == rt.Point:
            helpers += str(node.name) == name
            continue
        if rt.superClassOf(node) != rt.GeometryClass:
            continue
        if rt.classOf(node.baseobject) != rt.Editable_Poly:
            other += 1
            continue
        edited += _wipe(node, registry, name)
        _forget(node, name)
    if not other and registry.is_weighted(name):
        del registry.slots[name]                    # nothing uses the slot any more
    text = "%s: taken out of %d object(s)" % (name, edited)
    if other:
        text += "; %d object(s) that are not Editable Poly were not looked at" % other
    if helpers:
        text += "; %d point helper(s) still have this name" % helpers
    return text


def new(node, registry: reg.Registry, name: str, weight: float = 1.0,
        what: Optional[str] = None, indices: Optional[List[int]] = None) -> str:
    """Make a new group of the picked verts / faces"""
    define()
    name = _user_name(name)
    if name in registry.ids or _slot_of(registry, name) is not None:
        if any(members(node, registry, name)):
            raise GroupError("This object already has a group \"%s\". Use Redefine to replace it." % name)
    return assign(node, registry, name, weight, what, indices)


def rename_here(node, registry: reg.Registry, old: str, new: str) -> str:
    """Rename a group on this object only: its verts"""
    define()
    old = _known(registry, old)
    new = _user_name(new)
    if new == old:
        return "%s: same name" % new
    verts, faces = members(node, registry, old)
    if not verts and not faces:
        raise GroupError("\"%s\" has nothing on this object." % old)
    if (new in registry.ids or _slot_of(registry, new) is not None) and any(members(node, registry, new)):
        raise GroupError("This object already has a group \"%s\"." % new)
    if registry.is_weighted(old):
        weight_of = weights(node, registry, old)
        channel, component = _to_slot(node, registry, new)
        around = sorted(set(faces_around(node, verts)) | faces) if verts else sorted(faces)
        patch = Patch(node, channel, around)
        by_weight: Dict[float, List[int]] = {}
        for vertex, weight in weight_of.items():
            by_weight.setdefault(weight, []).append(vertex)
        for weight, vertices in by_weight.items():
            patch.slot_set(component, vertices, weight)
        position = {face: i for i, face in enumerate(patch.face_ids)}
        patch.slot_flag(component, [position[face] for face in faces], True)
        patch.write(verts)
    else:
        _assign_plain(node, registry, new, "faces", sorted(faces), sorted(verts))
    _wipe(node, registry, old)
    _forget(node, old)
    _remember(node, new)
    return "%s: renamed to %s on this object" % (old, new)


def rename(registry: reg.Registry, old: str, new: str) -> str:
    """Rename a group everywhere in the scene (the data in the meshes isn't touched)"""
    old = _known(registry, old)
    new = _user_name(new)
    if new == old:
        return "%s: same name" % new
    if new in registry.ids or registry.get(new) is not None:
        raise GroupError("There already is a group \"%s\"." % new)
    registry.rename(old, new)
    return "renamed to %s (in the whole scene)" % new


def _pick(node, verts: Optional[Iterable[int]], faces: Optional[Iterable[int]] = None,
          vertex_level: bool = False) -> None:
    """Make these the object's vert / poly selection and let the user see it"""
    polyop = rt.polyop
    if verts is not None:
        polyop.setVertSelection(node, to_bits(sorted(verts)))
    if faces is not None:
        polyop.setFaceSelection(node, to_bits(sorted(faces)))
    level = rt.subobjectLevel
    if level is None or int(level) == 0 or (vertex_level and int(level) != 1):
        try:
            rt.subobjectLevel = 1
        except Exception:  # noqa: BLE001 - the Modify panel is not showing this object
            pass
    rt.redrawViews()


def select(node, registry: reg.Registry, name: str, mode: str = "replace") -> str:
    """Make the group the object's current vert and poly selection"""
    verts, faces = members(node, registry, name)
    chosen_verts, chosen_faces = verts, faces
    note = ""
    if mode in ("add", "subtract"):
        polyop = rt.polyop
        now_verts = set(from_bits(polyop.getVertSelection(node)))
        now_faces = set(from_bits(polyop.getFaceSelection(node)))
        if mode == "add":
            chosen_verts, chosen_faces = now_verts | verts, now_faces | faces
            note = ", added to the selection"
        else:
            chosen_verts, chosen_faces = now_verts - verts, now_faces - faces
            note = ", taken out of the selection"
    _pick(node, chosen_verts, chosen_faces)
    return "%s: %d vertices, %d polygons%s" % (name.strip(), len(verts), len(faces), note)


# Looking for trouble

def inspect(node, registry: reg.Registry) -> dict:
    """What a look at the whole mesh finds (verts and faces 1-based)"""
    define()
    polyop = rt.polyop
    grouped: Set[int] = set()
    blended: Set[int] = set()
    torn: Set[int] = set()
    open_faces: Dict[str, List[int]] = {}
    for channel in _layers_on(node, registry):
        found = rt.zaslehLayerCheck(node, channel)
        grouped.update(from_bits(found[0]))
        blended.update(from_bits(found[1]))
        torn.update(from_bits(found[2]))
        with_faces = set(from_bits(found[5]))
        for face, number in zip(found[3], found[4]):
            name = registry.name_of(int(number)) if int(number) in with_faces else None
            if name is not None:
                open_faces.setdefault(name, []).append(int(face))
    for channel, entries in registry.by_channel().items():
        components = [i + 1 for i, e in enumerate(entries) if e is not None and e["kind"] == reg.WEIGHTED]
        if components and rt.zaslehHasChannel(node, channel):
            found = rt.zaslehSlotCheck(node, channel, rt.Array(*components))
            grouped.update(from_bits(found[0]))
            blended.update(from_bits(found[1]))
    alive = set(range(1, int(polyop.getNumVerts(node)) + 1)) - set(from_bits(polyop.getDeadVerts(node)))
    return {"ungrouped": sorted(alive - grouped), "torn": sorted(torn), "blended": sorted(blended),
            "open": open_faces, "ngons": from_bits(rt.zaslehBigFaces(node))}


def check(node, registry: reg.Registry) -> Tuple[str, str]:
    """Look the object over"""
    found = inspect(node, registry)
    lines: List[str] = []
    if found["torn"]:
        lines.append("%d vertices are claimed by two groups that are stored together (this happens after "
                     "welding or attaching). Only one of the groups will keep each of them on export. "
                     "They are selected now: assign them to every group they belong to." % len(found["torn"]))
    if found["blended"]:
        lines.append("%d vertices sit on the border of a group without being in it: new vertices made by "
                     "cutting across the border, or by collapsing vertices of different groups into one.%s "
                     "Assign them if they belong to the group."
                     % (len(found["blended"]), "" if found["torn"] else " They are selected now."))
    if found["ngons"]:
        lines.append("%d polygon(s) have more than 4 corners; a p3d holds triangles and quads only."
                     % len(found["ngons"]))
    listed = sorted(found["open"].items(), key=lambda item: (-len(item[1]), item[0].lower()))
    if listed:              # imported models have these too
        text = ", ".join("\"%s\" %d" % (name, len(faces)) for name, faces in listed[:6])
        if len(listed) > 6:
            text += " and %d more group(s)" % (len(listed) - 6)
        lines.append("Polygons that have all their vertices in a group but are not in it: %s. "
                     "If they should be in: Select the group, then Assign at vertex level." % text)
    if found["ungrouped"]:
        lines.append("%d vertices are in no group (the Ungrouped button selects them)." % len(found["ungrouped"]))
    wanted = found["torn"] or found["blended"]
    if wanted:
        _pick(node, wanted, vertex_level=True)
    if not lines:
        return "Checked: nothing to fix.", ""
    return "Checked: %d note(s)." % len(lines), "\n\n".join(lines)


def ungrouped(node, registry: reg.Registry) -> str:
    """Select the verts that are in no group"""
    found = inspect(node, registry)["ungrouped"]
    _pick(node, found, vertex_level=True)
    return "%d vertices are in no group%s" % (len(found), " - selected" if found else "")


# Showing a group in colour

_OUTSIDE = (0.22, 0.22, 0.22)
_RAMP = ((0.0, 0.0, 1.0), (0.0, 1.0, 1.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 0.0, 0.0))


def heat(weight: float) -> Tuple[float, float, float]:
    """Colour of a weight: blue (just above 0) - cyan - green - yellow - red (1)"""
    place = max(0.0, min(1.0, weight)) * (len(_RAMP) - 1)
    index = min(int(place), len(_RAMP) - 2)
    part = place - index
    low, high = _RAMP[index], _RAMP[index + 1]
    return tuple(a + (b - a) * part for a, b in zip(low, high))


def shown(node) -> str:
    """The group the object shows in colour, "" if none"""
    raw = rt.getAppData(node, reg.SHOWN_APPDATA_ID)
    return str(raw) if raw else ""


def show(node, registry: reg.Registry, name: str) -> str:
    """Show a group in the viewport as vert colours: grey outside, blue to red by weight"""
    define()
    name = _known(registry, name)
    found = weights(node, registry, name)
    verts = sorted(found)
    point3 = rt.Point3
    rt.zaslehShowColors(node, reg.DISPLAY_CHANNEL, rt.Array(*verts),
                     rt.Array(*[point3(*heat(found[v])) for v in verts]), point3(*_OUTSIDE))
    rt.setAppData(node, reg.SHOWN_APPDATA_ID, name)
    return "%s: %d vertices shown in colour (red = weight 1, blue = near 0)" % (name, len(verts))


def hide(node) -> str:
    define()
    rt.zaslehHideColors(node, reg.DISPLAY_CHANNEL)
    rt.deleteAppData(node, reg.SHOWN_APPDATA_ID)
    return "Colours off."


def find_components(node, registry: reg.Registry) -> str:
    """Make every separate piece of the mesh a component (Component01, 02 ...), as geometry LODs need"""
    define()
    polyop = rt.polyop
    polyop.collapseDeadStructs(node)
    face_verts = [[int(v) for v in face] for face in rt.zaslehFaceVerts(node)]
    if not face_verts:
        raise GroupError("The object has no polygons.")
    all_faces = list(range(1, len(face_verts) + 1))
    all_verts = sorted({v for face in face_verts for v in face})
    for channel in _layers_on(node, registry):                    # old components go
        stale = [int(n) for n in rt.zaslehLayerNumbers(node, channel)
                 if COMPONENT.match(registry.name_of(int(n)) or "")]
        if stale:
            patch = Patch(node, channel, all_faces)
            for number in stale:
                patch.layer_clear(number, all_verts)
            patch.write(all_verts)
    parent = list(range(int(polyop.getNumVerts(node)) + 1))

    def find(vertex: int) -> int:
        while parent[vertex] != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    for face in face_verts:
        first = find(face[0])
        for vertex in face[1:]:
            other = find(vertex)
            if other != first:
                parent[other] = first
    channel = _free_layer(node, registry, -1, all_verts)
    patch = Patch(node, channel, all_faces)
    numbers: Dict[int, int] = {}
    for i, face in enumerate(face_verts):
        root = find(face[0])
        number = numbers.get(root)
        if number is None:
            number = numbers[root] = registry.number("Component%02d" % (len(numbers) + 1))
        check = reg.check_value(number)
        for triple in patch.values[i]:
            triple[0], triple[1], triple[2] = float(number), check, 1.0
    patch.write(all_verts)
    rt.setAppData(node, reg.GROUPS_APPDATA_ID, json.dumps(scan(node, registry)))
    return "%d component(s)" % len(numbers)


# Listing

def scan(node, registry: reg.Registry) -> List[str]:
    """Names of the groups the object has something in, read from the mesh"""
    define()
    names: Set[str] = set()
    for channel in _layers_on(node, registry):
        for number in rt.zaslehLayerNumbers(node, channel):
            name = registry.name_of(int(number))
            if name is not None:
                names.add(name)
    for channel, entries in registry.by_channel().items():
        if not rt.zaslehHasChannel(node, channel):
            continue
        weighted = [(i, e) for i, e in enumerate(entries) if e is not None and e["kind"] == reg.WEIGHTED]
        if weighted:
            top = rt.zaslehChannelMax(node, channel)
            for i, entry in weighted:
                if (top.x, top.y, top.z)[i] > 0.0:
                    names.add(entry["name"])
    return sorted(names, key=str.lower)


def cached_names(node) -> Optional[List[str]]:
    raw = rt.getAppData(node, reg.GROUPS_APPDATA_ID)
    if not raw:
        return None
    try:
        return [str(name) for name in json.loads(str(raw))]
    except ValueError:
        return None


def _remember(node, name: str) -> None:
    names = cached_names(node)
    if names is not None and name not in names:
        rt.setAppData(node, reg.GROUPS_APPDATA_ID, json.dumps(sorted(names + [name], key=str.lower)))


def _forget(node, name: str) -> None:
    names = cached_names(node)
    if names is not None and name in names:
        rt.setAppData(node, reg.GROUPS_APPDATA_ID, json.dumps([n for n in names if n != name]))


def groups_on(node, registry: reg.Registry, rescan: bool = False) -> Optional[List[str]]:
    """Names of the object's groups: the list kept on the object, or - with rescan"""
    names = None if rescan else cached_names(node)
    if names is None and rescan:
        names = scan(node, registry)
        rt.setAppData(node, reg.GROUPS_APPDATA_ID, json.dumps(names))
    if names is None:
        return None
    return sorted((n for n in names if not n.startswith("#")), key=str.lower)
