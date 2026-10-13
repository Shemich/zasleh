"""Getting selected objects ready for export"""

import pymxs

rt = pymxs.runtime


def _geometry() -> list:
    return [node for node in rt.selection if rt.superClassOf(node) == rt.GeometryClass]


def reset_xform() -> int:
    nodes = _geometry()
    for node in nodes:
        rt.ResetXForm(node)
        rt.convertToPoly(node)
    return len(nodes)


def reset_pivots() -> int:
    nodes = _geometry()
    for node in nodes:
        rt.ResetPivot(node)
        rt.CenterPivot(node)
        rt.WorldAlignPivot(node)
    return len(nodes)


def to_poly() -> int:
    nodes = _geometry()
    for node in nodes:
        rt.convertToPoly(node)
    return len(nodes)


def clean() -> int:
    """Drop loose verts and faces with fewer than three corners; returns how many faces went"""
    polyop = rt.polyop
    gone = 0
    for node in _geometry():
        if rt.classOf(node) != rt.Editable_Poly:
            rt.convertToPoly(node)
        bad = [f for f in range(1, int(polyop.getNumFaces(node)) + 1) if int(polyop.getFaceDeg(node, f)) < 3]
        if bad:
            polyop.deleteFaces(node, rt.execute("#{%s}" % ",".join(map(str, bad))))
            gone += len(bad)
        polyop.deleteIsoVerts(node)
    return gone
