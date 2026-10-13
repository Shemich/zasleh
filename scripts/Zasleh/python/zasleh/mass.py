"""Mass of a geometry LOD, set the way Object Builder's Mass window sets it: pick verts"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pymxs

from zasleh import formats

from . import registry as reg
from .groups import GroupError, Patch, define, faces_around, selection_of
from .scene import layer_resolution

rt = pymxs.runtime


def _points(node, registry: reg.Registry, vertices: List[int], around: List[int]) -> List[List[int]]:
    """The picked verts, grouped into p3d points"""
    ids: Dict[int, float] = {}
    entry = registry.get(reg.POINT_ID)
    if entry is not None:
        channel, component = reg.Registry.place(entry["slot"])
        if rt.zaslehHasChannel(node, channel):
            patch = Patch(node, channel, around)
            for vertex, corners in patch.corners_at().items():
                i, k = corners[0]
                ids[vertex] = patch.values[i][k][component]
    get_vert = rt.polyop.getVert
    points: Dict[tuple, List[int]] = {}
    for vertex in vertices:
        value = ids.get(vertex, 0.0)
        number = int(round(value))
        if number > 0 and abs(value - number) < 1e-3:
            position = get_vert(node, vertex)
            key = (number, position.x, position.y, position.z)
        else:
            key = (0, vertex)
        points.setdefault(key, []).append(vertex)
    return list(points.values())


def _slot(registry: reg.Registry) -> Tuple[int, int]:
    try:
        entry = registry.allocate(reg.MASS, reg.NUMBER)
    except reg.RegistryFull as error:
        raise GroupError(str(error))
    return reg.Registry.place(entry["slot"])


def _keeps_mass(node) -> bool:
    """Is the object on a layer whose LOD stores mass?"""
    resolution = layer_resolution(node.layer)
    return resolution is not None and formats.has_mass(resolution)


def set_mass(node, registry: reg.Registry, total: float,
             what: Optional[str] = None, indices: Optional[List[int]] = None) -> str:
    """Spread ``total`` kilograms evenly over the picked points (the whole object at object level)"""
    define()
    total = float(total)
    if total < 0.0:
        raise GroupError("Mass cannot be negative.")
    _what, _indices, vertices = selection_of(node, what, indices)
    around = faces_around(node, vertices)
    channel, component = _slot(registry)
    patch = Patch(node, channel, around)
    at = patch.corners_at()
    vertices = [vertex for vertex in vertices if vertex in at]
    if not vertices:
        raise GroupError("The picked vertices belong to no polygon; such vertices cannot carry mass.")
    points = _points(node, registry, vertices, around)
    each = total / len(points)
    for vertex in vertices:
        for i, k in at[vertex]:
            patch.values[i][k][component] = each
    patch.write(vertices)
    text = "Mass: %g kg over %d points (%g kg each)" % (total, len(points), each)
    if not _keeps_mass(node):
        text += ". Note: only a Geometry LOD keeps mass in a p3d"
    return text


def get_mass(node, registry: reg.Registry,
             what: Optional[str] = None, indices: Optional[List[int]] = None) -> Tuple[float, int]:
    """(kilograms, nr of points) of the picked points (the whole object at object level)"""
    define()
    _what, _indices, vertices = selection_of(node, what, indices)
    entry = registry.get(reg.MASS)
    around = faces_around(node, vertices)
    points = _points(node, registry, vertices, around)
    if entry is None:
        return 0.0, len(points)
    channel, component = reg.Registry.place(entry["slot"])
    if not rt.zaslehHasChannel(node, channel):
        return 0.0, len(points)
    patch = Patch(node, channel, around)
    at = patch.corners_at()
    total = 0.0
    for same in points:
        corners = at.get(same[0])
        if corners:
            i, k = corners[0]
            total += patch.values[i][k][component]
    return total, len(points)
