"""Filling an Editable Mesh in one go"""

from __future__ import annotations

import os
from array import array
from itertools import accumulate, chain
from typing import Iterable, List, Optional, Sequence, Tuple

import pymxs

from zasleh.formats import meshprep, smoothing

rt = pymxs.runtime

# C# 5 only: that's what the compiler shipped with the .NET Framework understands.
_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Bulk.cs")

_MAXSCRIPT = r'''
global zaslehBulkError = ""
global zaslehBulkMethods = #()
fn zaslehBulkCompile source =
(
    zaslehBulkError = ""
    try
    (
        local provider = dotNetObject "Microsoft.CSharp.CSharpCodeProvider"
        local options = dotNetObject "System.CodeDom.Compiler.CompilerParameters"
        options.GenerateInMemory = true
        options.CompilerOptions = "/unsafe /optimize"
        options.ReferencedAssemblies.Add "System.dll"
        options.ReferencedAssemblies.Add "System.Core.dll"
        options.ReferencedAssemblies.Add ((getDir #maxroot) + "Autodesk.Max.dll")
        local result = provider.CompileAssemblyFromSource options #(source)
        if result.Errors.Count > 0 then zaslehBulkError = (result.Errors.Item[0]).ToString()
        else
        (
            local helper = result.CompiledAssembly.GetType "ZaslehBulk"
            zaslehBulkMethods = for name in #("Geometry", "Channel", "Begin", "Uv", "Data", "Flags", "Sheets", "Smoothing", "PolyInfo", "PolyGeometry", "PolyChannelSize", "PolyChannel", "Normals", "SharpFromGroups", "Slot", "Layer") collect (helper.GetMethod name)
        )
    )
    catch (zaslehBulkError = getCurrentException())
    zaslehBulkError == ""
)
fn zaslehBulkNode objName = (local m = mesh numverts:0 numfaces:0; m.name = objName; m)
fn zaslehBulkHandle n = n.inode.handle
fn zaslehBulkGeometry h v nv t nt s f = (zaslehBulkMethods[1].Invoke undefined #(h, v, nv, t, nt, s, f))
fn zaslehBulkChannel h ch v nv t nt = (zaslehBulkMethods[2].Invoke undefined #(h, ch, v, nv, t, nt))
fn zaslehBulkBegin h p nv t tf tc nt = (zaslehBulkMethods[3].Invoke undefined #(h, p, nv, t, tf, tc, nt))
fn zaslehBulkUv ch uv offset = (zaslehBulkMethods[4].Invoke undefined #(ch, uv, offset))
fn zaslehBulkData ch p0 p1 p2 f0 f1 f2 = (zaslehBulkMethods[5].Invoke undefined #(ch, p0, p1, p2, f0, f1, f2))
fn zaslehBulkFlags h n = (zaslehBulkMethods[6].Invoke undefined #(h, n))
fn zaslehBulkSheets fp fs nf pos np cv vp = (zaslehBulkMethods[7].Invoke undefined #(fp, fs, nf, pos, np, cv, vp))
fn zaslehBulkSmoothing fp fs nf np sharp ns groups = (zaslehBulkMethods[8].Invoke undefined #(fp, fs, nf, np, sharp, ns, groups))
fn zaslehBulkPolyInfo h = (zaslehBulkMethods[9].Invoke undefined #(h))
fn zaslehBulkPolyGeometry h m v d x s i = (zaslehBulkMethods[10].Invoke undefined #(h, m, v, d, x, s, i))
fn zaslehBulkPolyChannelSize h ch = (zaslehBulkMethods[11].Invoke undefined #(h, ch))
fn zaslehBulkPolyChannel h ch v f = (zaslehBulkMethods[12].Invoke undefined #(h, ch, v, f))
fn zaslehBulkNormals fp fs nf pos np pf ff sh ns lk oi on_ = (zaslehBulkMethods[13].Invoke undefined #(fp, fs, nf, pos, np, pf, ff, sh, ns, lk, oi, on_))
fn zaslehBulkSharp fp fs nf np g o = (zaslehBulkMethods[14].Invoke undefined #(fp, fs, nf, np, g, o))
fn zaslehBulkSlot mv mc mf fv dg nf nv c num ov of_ = (zaslehBulkMethods[15].Invoke undefined #(mv, mc, mf, fv, dg, nf, nv, c, num, ov, of_))
fn zaslehBulkLayer mv mc mf fv dg nf nv ov of_ = (zaslehBulkMethods[16].Invoke undefined #(mv, mc, mf, fv, dg, nf, nv, ov, of_))
fn zaslehBulkMatrix n = (local m = n.objectTransform; #(m.row1.x, m.row1.y, m.row1.z, m.row2.x, m.row2.y, m.row2.z, m.row3.x, m.row3.y, m.row3.z, m.row4.x, m.row4.y, m.row4.z))
'''

_state: Optional[bool] = None       # None: not tried yet
error = ""                          # why the helper isn't available


def _read_source() -> str:
    with open(_SOURCE, encoding="utf-8") as stream:
        return stream.read()


def available() -> bool:
    """Is the fast path there? Builds the helper on first use (a fraction of a second)"""
    global _state, error
    if _state is None:
        if os.environ.get("ZASLEH_BULK") == "0":
            _state, error = False, "turned off by ZASLEH_BULK=0"
        else:
            try:
                rt.execute(_MAXSCRIPT)
                _state = bool(rt.zaslehBulkCompile(_read_source()))
                error = "" if _state else str(rt.zaslehBulkError)
            except Exception as problem:  # noqa: BLE001 - any failure means: use the MAXScript path
                _state, error = False, str(problem)
    return _state


def disable(reason: str) -> None:
    """Stop using the fast path for the rest of the session"""
    global _state, error
    _state, error = False, reason


def new_node(name: str):
    """An empty Editable Mesh to fill"""
    return rt.zaslehBulkNode(name)


def _address(data: Optional[array]) -> str:
    return "0" if data is None else str(data.buffer_info()[0])


def set_geometry(node, verts: array, tris: array, smoothing: array, flags: array) -> None:
    """verts: 'f', 3 per vert"""
    rt.zaslehBulkGeometry(int(rt.zaslehBulkHandle(node)), _address(verts), len(verts) // 3,
                       _address(tris), len(tris) // 3, _address(smoothing), _address(flags))


def set_channel(node, channel: int, verts: array, tris: array) -> None:
    """A ready-made map channel: verts 'f', 3 per map vert"""
    rt.zaslehBulkChannel(int(rt.zaslehBulkHandle(node)), channel, _address(verts), len(verts) // 3,
                      _address(tris), len(tris) // 3)


def face_flags(node, count: int) -> list:
    """The SDK flags of the first faces of an Editable Mesh"""
    return [int(value) for value in str(rt.zaslehBulkFlags(int(rt.zaslehBulkHandle(node)), count)).split()]


# The heavy steps of meshprep.prepare, done by the helper

def _faces_flat(faces: Iterable[Sequence[int]]) -> Tuple[array, array]:
    """(the points of all faces in a row, where each face starts in it)"""
    faces = list(faces)
    return (array("i", chain.from_iterable(faces)),
            array("i", accumulate(chain((0,), map(len, faces)))))


def split_into_sheets(kept: List[Tuple[int, tuple]], positions: Sequence[Sequence[float]],
                      points_out: List[int]) -> List[List[int]]:
    """meshprep.split_into_sheets, see there"""
    if not available():
        return meshprep.split_into_sheets(kept, positions, points_out)
    flat, starts = _faces_flat(points for _index, points in kept)
    where = array("d", chain.from_iterable(positions))
    corner_vertex = array("i", bytes(4 * len(flat)))
    vertex_point = array("i", bytes(4 * len(flat)))
    try:
        count = int(rt.zaslehBulkSheets(_address(flat), _address(starts), len(kept), _address(where), len(positions),
                                     _address(corner_vertex), _address(vertex_point)))
    except Exception as problem:  # noqa: BLE001 - the Python way still works
        disable(str(problem))
        return meshprep.split_into_sheets(kept, positions, points_out)
    points_out.extend(vertex_point[:count])
    corners = corner_vertex.tolist()
    return [corners[begin:end] for begin, end in zip(starts, starts[1:])]


def to_smoothing_groups(faces: Sequence[Sequence[int]], sharp: Iterable[Tuple[int, int]]) -> Tuple[List[int], int]:
    """smoothing.to_smoothing_groups, see there"""
    if not available():
        return smoothing.to_smoothing_groups(faces, sharp)
    flat, starts = _faces_flat(faces)
    point_count = (max(flat) + 1) if flat else 0
    # an edge between points no face uses can't matter (and a damaged tag may hold anything)
    sharp = [(a, b) for a, b in sharp if 0 <= a < point_count and 0 <= b < point_count]
    edges = array("i", chain.from_iterable(sharp))
    groups = array("I", bytes(4 * len(faces)))
    try:
        wrong = int(rt.zaslehBulkSmoothing(_address(flat), _address(starts), len(faces), point_count,
                                        _address(edges), len(sharp), _address(groups)))
    except Exception as problem:  # noqa: BLE001
        disable(str(problem))
        return smoothing.to_smoothing_groups(faces, sharp)
    return groups.tolist(), wrong


# Reading an Editable Poly, for the export

poly_error = ""                     # why reading through the helper was given up, if it was
_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


class PolyData:
    """An Editable Poly as flat arrays"""

    def __init__(self, node, handle: int, vert_count: int, face_count: int, corners: int, map_count: int):
        self.node = node
        self.handle = handle
        self.vert_count, self.face_count, self.corners, self.map_count = vert_count, face_count, corners, map_count
        self.positions = array("f", bytes(12 * vert_count))
        self.degrees = array("i", bytes(4 * face_count))
        self.vertices = array("i", bytes(4 * corners))          # of all faces, in a row
        self.smoothing = array("I", bytes(4 * face_count))
        self.material_ids = array("i", bytes(4 * face_count))   # 1-based

    def channel(self, channel: int) -> Optional[Tuple[array, array]]:
        """(map verts 'f' 3 each, the map vert of every face corner 'i')"""
        if channel >= self.map_count or not rt.polyop.getMapSupport(self.node, channel):
            return None
        size = int(rt.zaslehBulkPolyChannelSize(self.handle, channel))
        if size < 0:
            return None
        verts = array("f", bytes(12 * size))
        faces = array("i", bytes(4 * self.corners))
        rt.zaslehBulkPolyChannel(self.handle, channel, _address(verts), _address(faces))
        return verts, faces

    def slot(self, data: Tuple[array, array], component: int, numeric: bool) -> Tuple[List[float], list]:
        """A slot of a channel() per vert and per face, as reader._decode gives it"""
        verts, corners = data
        per_vert = array("d", bytes(8 * self.vert_count))
        per_face = array("d", bytes(8 * self.face_count))
        rt.zaslehBulkSlot(_address(verts), len(verts) // 3, _address(corners), _address(self.vertices),
                       _address(self.degrees), self.face_count, self.vert_count, component, int(numeric),
                       _address(per_vert), _address(per_face))
        return per_vert.tolist(), per_face.tolist() if numeric else [value != 0.0 for value in per_face]

    def layer(self, data: Tuple[array, array]) -> Tuple[List[int], List[int]]:
        """The group nr per vert and per face of a layer channel()"""
        verts, corners = data
        per_vert = array("i", bytes(4 * self.vert_count))
        per_face = array("i", bytes(4 * self.face_count))
        rt.zaslehBulkLayer(_address(verts), len(verts) // 3, _address(corners), _address(self.vertices),
                        _address(self.degrees), self.face_count, self.vert_count, _address(per_vert), _address(per_face))
        return per_vert.tolist(), per_face.tolist()


def read_poly(node) -> Optional[PolyData]:
    """The geometry of an Editable Poly node w/o modifiers, read in one go"""
    global poly_error
    if poly_error or not available():
        return None
    try:
        handle = int(rt.zaslehBulkHandle(node))
        vert_count, face_count, corners, dead_verts, dead_faces, map_count = (
            int(value) for value in str(rt.zaslehBulkPolyInfo(handle)).split())
        if dead_verts or dead_faces:
            return None                 # the numbering has gaps
        data = PolyData(node, handle, vert_count, face_count, corners, map_count)
        rows = [float(value) for value in rt.zaslehBulkMatrix(node)]
        matrix = None if tuple(rows) == _IDENTITY else array("f", rows)
        rt.zaslehBulkPolyGeometry(handle, _address(matrix), _address(data.positions), _address(data.degrees),
                               _address(data.vertices), _address(data.smoothing), _address(data.material_ids))
        return data
    except Exception as problem:  # noqa: BLE001 - MAXScript still reads any object
        poly_error = str(problem).replace("\n", " ")[:300]
        return None


def compute_normals(points, point_flags, faces, face_flags, sharp, locked):
    """normals.compute, see there"""
    from zasleh.formats import normals
    from zasleh.formats.flags import POINT_SPECIAL_ANGLENORMAL
    if not available() or not faces or any(flags & POINT_SPECIAL_ANGLENORMAL for flags in point_flags):
        return normals.compute(points, point_flags, faces, face_flags, sharp, locked)
    flat, starts = _faces_flat(faces)
    count = len(points)
    if min(flat) < 0 or max(flat) >= count:
        return normals.compute(points, point_flags, faces, face_flags, sharp, locked)
    sharp = [(a, b) for a, b in sharp if 0 <= a < count and 0 <= b < count]
    kept = array("d", bytes(24 * count))
    for point, vector in locked.items():
        if 0 <= point < count:
            kept[3 * point], kept[3 * point + 1], kept[3 * point + 2] = vector
    arrays = (flat, starts, array("d", chain.from_iterable(points)), array("I", [f & 0xFFFFFFFF for f in point_flags]),
              array("I", [f & 0xFFFFFFFF for f in face_flags]), array("i", chain.from_iterable(sharp)), kept,
              array("i", bytes(4 * len(flat))), array("d", bytes(24 * (len(flat) + len(faces) + 1))))
    try:
        made = int(rt.zaslehBulkNormals(_address(flat), _address(starts), len(faces), _address(arrays[2]), count,
                                     _address(arrays[3]), _address(arrays[4]), _address(arrays[5]), len(sharp),
                                     _address(kept), _address(arrays[7]), _address(arrays[8])))
    except Exception as problem:  # noqa: BLE001
        disable(str(problem))
        return normals.compute(points, point_flags, faces, face_flags, sharp, locked)
    out = arrays[8]
    vectors = list(zip(out[0:3 * made:3], out[1:3 * made:3], out[2:3 * made:3]))
    corners = arrays[7].tolist()
    return vectors, [corners[begin:end] for begin, end in zip(starts, starts[1:])]


def sharp_edges(faces: Sequence[Sequence[int]], groups: Sequence[int]) -> set:
    """smoothing.sharp_edges, see there"""
    if not available() or not faces:
        return smoothing.sharp_edges(faces, groups)
    flat, starts = _faces_flat(faces)
    if min(flat) < 0:
        return smoothing.sharp_edges(faces, groups)
    masks = array("I", [g & 0xFFFFFFFF for g in groups])
    pairs = array("i", bytes(8 * len(flat)))
    try:
        made = int(rt.zaslehBulkSharp(_address(flat), _address(starts), len(faces), max(flat) + 1, _address(masks), _address(pairs)))
    except Exception as problem:  # noqa: BLE001
        disable(str(problem))
        return smoothing.sharp_edges(faces, groups)
    return set(zip(pairs[0:2 * made:2], pairs[1:2 * made:2]))


class Session:
    """One mesh being built: its geometry, then map channels worked out by the helper from what the"""

    def __init__(self, node, verts: Sequence[Sequence[float]], points: Sequence[int],
                 tris: Sequence[Sequence[int]], tri_face: Sequence[int], tri_corners: Sequence[Sequence[int]]):
        self.node = node
        # the arrays must stay alive for as long as the helper may read them
        self.verts = array("f", chain.from_iterable(verts))
        self.points = array("i", points)
        self.tris = array("i", chain.from_iterable(tris))
        self.tri_face = array("i", tri_face)
        self.tri_corners = array("b", chain.from_iterable(tri_corners))
        self.kept: list = []

    def geometry(self, smoothing: array, flags: array) -> None:
        set_geometry(self.node, self.verts, self.tris, smoothing, flags)
        rt.zaslehBulkBegin(int(rt.zaslehBulkHandle(self.node)), _address(self.points), len(self.points),
                        _address(self.tris), _address(self.tri_face), _address(self.tri_corners), len(self.tri_face))

    def uv(self, channel: int, uvs: array, face_offset: array) -> int:
        """uvs: 'f', (u, v) per face corner of the file"""
        return int(rt.zaslehBulkUv(channel, _address(uvs), _address(face_offset)))

    def data(self, channel: int, point_parts: Sequence[Optional[array]], face_parts: Sequence[Optional[array]]) -> int:
        """Up to three values per face corner: point_parts[i][p3d point] + face_parts[i][p3d face]"""
        return int(rt.zaslehBulkData(channel, *[_address(part) for part in list(point_parts) + list(face_parts)]))
