"""Memory points: Point helpers on a point LOD layer (Memory, Land Contact ...)"""

import json

import pymxs

from . import groups
from .scene import UNNAMED_POINT, define_maxscript, from_bits, to_bits

rt = pymxs.runtime
DEFAULT_LAYER = "Memory"

_TOOL = r'''
tool atbPlacePoint
(
    on mousePoint clickno do
    (
        python.Execute ("import atb_max.memory as m\nm.placed(" + (worldPoint.x as string) + ", " + (worldPoint.y as string) + ", " + (worldPoint.z as string) + ")")
    )
)
'''
_tool_ready = False
_placing = {"name": "", "layer": DEFAULT_LAYER, "done": None}


class MemoryError_(Exception):
    pass


def names_of(node) -> list:
    """The selections a point helper is in"""
    extra = rt.getUserProp(node, "atb_sels")
    if extra:
        try:
            return [str(item[0]) if isinstance(item, list) else str(item) for item in json.loads(str(extra))]
        except (ValueError, IndexError, TypeError):
            pass
    if rt.getUserProp(node, "atb_nosel") or str(node.name) == UNNAMED_POINT:
        return []
    return [str(node.name)]


def set_names(node, names) -> None:
    names = [name.strip() for name in names if name.strip()]
    node.name = names[0] if names else UNNAMED_POINT
    rt.setUserProp(node, "atb_nosel", not names)
    rt.setUserProp(node, "atb_sels", json.dumps(names) if len(names) > 1 else "")


def layer(name: str = DEFAULT_LAYER, create: bool = False):
    found = rt.LayerManager.getLayerFromName(name)
    if found is None and create:
        found = rt.LayerManager.newLayerFromName(name)
    return found


def points(layer_name: str = DEFAULT_LAYER) -> list:
    """The point helpers of a layer, as (node, names, (x, y, z))"""
    define_maxscript()
    found = layer(layer_name)
    if found is None:
        return []
    out = []
    for node in rt.atbLayerNodes(found):
        if rt.classOf(node) == rt.Point:
            position = node.pos
            out.append((node, names_of(node), (position.x, position.y, position.z)))
    return sorted(out, key=lambda row: (", ".join(row[1]).lower(), row[2]))


def add_point(position, name: str = "", layer_name: str = DEFAULT_LAYER):
    node = rt.Point(pos=rt.Point3(*position), size=10, centermarker=True, axistripod=False, cross=False, box=False,
                    constantscreensize=True, wirecolor=rt.color(255, 0, 0))
    set_names(node, [name])
    layer(layer_name, create=True).addNode(node)
    return node


def picked_positions() -> list:
    """World positions of what is picked: the verts of an Editable Poly at a sub-object level,
    else the centres of the selected objects"""
    nodes = [node for node in rt.selection if rt.classOf(node) != rt.Point]
    level = rt.subobjectLevel
    if len(nodes) == 1 and rt.classOf(nodes[0].baseobject) == rt.Editable_Poly and level is not None and int(level) > 0:
        node = nodes[0]
        what, indices = groups.picked(node)
        if what == "faces":
            indices = from_bits(rt.polyop.getVertsUsingFace(node, to_bits(indices)))
        get = rt.polyop.getVert
        return [(p.x, p.y, p.z) for p in (get(node, index) for index in indices)]
    return [(c.x, c.y, c.z) for c in (node.center for node in nodes)]


def add_at_centre(name: str = "", layer_name: str = DEFAULT_LAYER):
    """One point in the middle of what is picked"""
    found = picked_positions()
    if not found:
        raise MemoryError_("Pick vertices, or select an object, to place the point at.")
    centre = tuple(sum(p[axis] for p in found) / len(found) for axis in range(3))
    return add_point(centre, name, layer_name)


def add_at_verts(name: str = "", layer_name: str = DEFAULT_LAYER) -> list:
    """A point on every picked vert"""
    found = picked_positions()
    if not found:
        raise MemoryError_("Pick vertices to place the points on.")
    if len(found) > 200:
        raise MemoryError_("%d vertices are picked; that many memory points is surely a mistake." % len(found))
    return [add_point(position, name, layer_name) for position in found]


def make_axis(nodes, name: str) -> None:
    """Two points under one name: an axis"""
    if len(nodes) != 2:
        raise MemoryError_("An axis is two points: pick two in the list.")
    if not name.strip():
        raise MemoryError_("Type a name for the axis.")
    for node in nodes:
        set_names(node, [name])


def delete(nodes) -> int:
    nodes = [node for node in nodes if rt.isValidNode(node)]
    if nodes:
        rt.delete(rt.Array(*nodes))
    return len(nodes)


def select(nodes) -> None:
    nodes = [node for node in nodes if rt.isValidNode(node)]
    if nodes:
        rt.select(rt.Array(*nodes))
    else:
        rt.clearSelection()
    rt.redrawViews()


def set_size(size: float, layer_name: str = DEFAULT_LAYER) -> None:
    for node, _names, _position in points(layer_name):
        node.size = size
    rt.redrawViews()


def view(hide_points=None, hide_geometry=None, xray=None) -> None:
    """Hide the point helpers or the geometry, or see the points through the geometry"""
    for node in rt.objects:
        if rt.classOf(node) == rt.Point:
            if hide_points is not None:
                node.isHidden = hide_points
            if xray is not None:
                node.drawontop = xray
        elif rt.superClassOf(node) == rt.GeometryClass:
            if hide_geometry is not None:
                node.isHidden = hide_geometry
            if xray is not None:
                node.xray = xray
    rt.redrawViews()


def place(name: str = "", layer_name: str = DEFAULT_LAYER, done=None) -> None:
    """Place points with the mouse; a right click ends it"""
    global _tool_ready
    if not _tool_ready:
        rt.execute(_TOOL)
        _tool_ready = True
    _placing.update(name=name, layer=layer_name, done=done)
    rt.startTool(rt.atbPlacePoint)


def placed(x: float, y: float, z: float) -> None:
    add_point((x, y, z), _placing["name"], _placing["layer"])
    rt.redrawViews()
    if _placing["done"] is not None:
        _placing["done"]()
