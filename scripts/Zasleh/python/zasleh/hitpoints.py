"""The hit point LOD: clouds of points inside objects, and how far each hit point reaches"""

from __future__ import annotations

from array import array
from typing import Dict, List, Tuple

import pymxs

from . import bulk, reader, volume
from .formats import hitpoints as config
from .formats.meshprep import to_scene
from .scene import define_maxscript, layer_info, set_layer_info, user_prop

rt = pymxs.runtime
LAYER = "HitPoints"
ANY = ""                    # the radius of points whose selections have none of their own
MAX_SPHERES = 30000


class HitPointError(Exception):
    pass


def layer(create: bool = False):
    found = rt.LayerManager.getLayerFromName(LAYER)
    if found is None and create:
        found = rt.LayerManager.newLayerFromName(LAYER)
    return found


# -- clouds

def cloud(source, spacing) -> Tuple[List[tuple], int]:
    """(world positions of grid points inside a closed object, lines given up where the mesh is open).
    The grid follows the object's own axes; spacing (x, y, z) is in scene units."""
    if rt.superClassOf(source) != rt.GeometryClass:
        raise HitPointError("Select the closed object to fill with points.")
    transform = source.objectTransform
    back = rt.inverse(transform)
    scale = [float(rt.length(row)) or 1.0 for row in (transform.row1, transform.row2, transform.row3)]
    mesh = rt.snapshotAsMesh(source)
    try:
        get_vert, get_face = rt.getVert, rt.getFace
        verts = []
        for index in range(1, int(mesh.numverts) + 1):
            local = get_vert(mesh, index) * back
            verts.append((float(local.x), float(local.y), float(local.z)))
        triangles = []
        for index in range(1, int(mesh.numfaces) + 1):
            face = get_face(mesh, index)
            triangles.append((verts[int(face.x) - 1], verts[int(face.y) - 1], verts[int(face.z) - 1]))
    finally:
        rt.delete(mesh)
    inside, skipped = volume.fill(triangles, [max(1e-6, float(s)) / k for s, k in zip(spacing, scale)])
    world = [rt.Point3(*point) * transform for point in inside]
    return [(float(p.x), float(p.y), float(p.z)) for p in world], skipped


def _mesh(name: str, verts: array, tris: array):
    """An Editable Mesh of the given verts ('f', 3 each) and triangles ('i', 3 each)"""
    count = len(tris) // 3
    if bulk.available():
        node = bulk.new_node(name)
        bulk.set_geometry(node, verts, tris, array("I", bytes(4 * count)), array("I", [7 | (1 << 16)]) * count)
    else:
        if len(verts) > 60000:
            raise HitPointError("That many points need the fast mesh builder, which is not there: %s" % bulk.error)
        points = [rt.Point3(*verts[i:i + 3]) for i in range(0, len(verts), 3)]
        faces = [rt.Point3(tris[i] + 1, tris[i + 1] + 1, tris[i + 2] + 1) for i in range(0, len(tris), 3)]
        node = rt.mesh(vertices=rt.Array(*points), faces=rt.Array(*faces), name=name)
    rt.update(node)
    return node


def make_cloud(positions, name: str):
    """The points as one object on the hit point layer: a triangle of no size per point.
    The object is named after the selection and, having no other mark, is that selection in the p3d."""
    define_maxscript()
    verts = array("f", [value for position in positions for value in position * 3])
    with pymxs.undo(False):
        node = rt.convertToPoly(_mesh(name, verts, array("i", range(3 * len(positions)))))
        node.vertexTicks = True
        node.wirecolor = rt.color(255, 60, 60)
        layer(create=True).addNode(node)
    return node


# -- what the LOD holds

def _lod():
    found = layer()
    return None if found is None else reader.read_layer(found)


def selections() -> List[Tuple[str, int]]:
    """(selection, number of its points) of the hit point LOD"""
    lod = _lod()
    if lod is None:
        return []
    return [(s.name, len(s.weights) - s.weights.count(0)) for s in lod.selections]


# -- radius: per selection, kept with the layer

def radii() -> Dict[str, float]:
    found = layer()
    stored = layer_info(found).get("radii", {}) if found is not None else {}
    return {str(name): float(radius) for name, radius in stored.items()}


def set_radii(wanted: Dict[str, float]) -> None:
    """Radius per selection (ANY: of all the other points); 0 takes one away"""
    found = layer(create=True)
    info = layer_info(found)
    stored = dict(info.get("radii", {}))
    for name, radius in wanted.items():
        if radius > 0.0:
            stored[name.lower()] = float(radius)
        else:
            stored.pop(name.lower(), None)
    info["radii"] = stored
    set_layer_info(found, info)
    if shown():
        show(True)


def radii_from_config(text: str) -> List[str]:
    """Take the radius of every hit point class of a config.cpp whose selection the LOD has; gives their names"""
    have = {name.lower(): name for name, _count in selections()}
    found = {name: radius for name, radius in config.radii(text).items() if name.lower() in have}
    if found:
        set_radii(found)
    return [have[name.lower()] for name in found]


# -- showing the radius: one mesh of little spheres, for the eye only

def _unit_sphere() -> Tuple[List[tuple], List[tuple]]:
    verts = [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]
    faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    middles: Dict[tuple, int] = {}

    def middle(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key not in middles:
            point = [(verts[a][i] + verts[b][i]) / 2.0 for i in range(3)]
            length = sum(value * value for value in point) ** 0.5
            verts.append(tuple(value / length for value in point))
            middles[key] = len(verts) - 1
        return middles[key]

    finer = []
    for a, b, c in faces:
        ab, bc, ca = middle(a, b), middle(b, c), middle(c, a)
        finer += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
    return verts, finer


def _display_nodes() -> list:
    found = layer()
    if found is None:
        return []
    define_maxscript()
    return [node for node in rt.zaslehLayerNodes(found) if user_prop(node, "display") is not None]


def shown() -> bool:
    return bool(_display_nodes())


def show(on: bool = True) -> int:
    """A sphere of its radius around every hit point that has one; gives how many"""
    with pymxs.undo(False):
        old = _display_nodes()
        if old:
            rt.delete(rt.Array(*old))
        if not on:
            rt.redrawViews()
            return 0
        lod = _lod()
        known = radii()
        spheres: List[Tuple[int, float]] = []
        if lod is not None and known:
            free = bytearray([1]) * len(lod.points)
            for selection in lod.selections:
                radius = known.get(selection.name.lower(), 0.0)
                if radius > 0.0:
                    for point, weight in enumerate(selection.weights):
                        if weight:
                            spheres.append((point, radius))
                            free[point] = 0
            if known.get(ANY, 0.0) > 0.0:
                spheres += [(point, known[ANY]) for point in range(len(lod.points)) if free[point]]
        if len(spheres) > MAX_SPHERES:
            raise HitPointError("%d spheres would be drawn; give a radius to fewer selections." % len(spheres))
        if spheres:
            unit, faces = _unit_sphere()
            verts = array("f")
            tris = array("i")
            flat = [index for face in faces for index in face]
            for at, (point, radius) in enumerate(spheres):
                x, y, z = to_scene(lod.points[point])
                for ux, uy, uz in unit:
                    verts.extend((x + radius * ux, y + radius * uy, z + radius * uz))
                tris.extend([index + at * len(unit) for index in flat])
            node = _mesh("hit point radius", verts, tris)
            rt.setUserProp(node, "zasleh_display", True)
            node.xray = True
            node.renderable = False
            node.wirecolor = rt.color(255, 190, 40)
            node.showFrozenInGray = False
            layer().addNode(node)
            node.isFrozen = True
    rt.redrawViews()
    return len(spheres)
