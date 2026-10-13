"""Multi-structure: a big model cut into parts, each exported around its own origin.

Every part gets a memory point pos_<name> at its home position; the part's p3d is written
with that point at the origin, and the base model puts the parts back by those points
(multiStructureParts[] of the config)."""

from __future__ import annotations

import json
import os
from typing import List, Optional

import pymxs

from zasleh import formats
from zasleh.formats import P3D

from . import exporter, mass, memory, reader
from . import registry as reg
from .scene import define_maxscript, set_layer_info

rt = pymxs.runtime
APPDATA_ID = 0x41544206
GEOMETRY = 1.0e13


class Part:
    def __init__(self, node, cls: str = "", mass_kg: float = 0.0):
        self.node, self.cls, self.mass = node, cls or str(node.name), mass_kg


class Parts:
    """The part list, kept with the scene"""

    def __init__(self):
        self.prefix = "pos_"
        self.items: List[Part] = []

    @classmethod
    def load(cls) -> "Parts":
        parts = cls()
        raw = rt.getAppData(rt.rootNode, APPDATA_ID)
        if raw:
            try:
                data = json.loads(str(raw))
            except ValueError:
                return parts
            parts.prefix = data.get("prefix", "pos_")
            for row in data.get("parts", []):
                node = rt.maxOps.getNodeByHandle(int(row["handle"]))
                if node is not None and rt.isValidNode(node):
                    parts.items.append(Part(node, row.get("cls", ""), float(row.get("mass", 0.0))))
        return parts

    def save(self) -> None:
        self.items = [part for part in self.items if rt.isValidNode(part.node)]
        data = {"prefix": self.prefix,
                "parts": [{"handle": int(part.node.inode.handle), "cls": part.cls, "mass": part.mass} for part in self.items]}
        rt.setAppData(rt.rootNode, APPDATA_ID, json.dumps(data))

    def point_name(self, part: Part) -> str:
        return self.prefix + str(part.node.name)

    def add_selected(self) -> int:
        have = {int(part.node.inode.handle) for part in self.items}
        added = 0
        for node in rt.selection:
            if rt.superClassOf(node) == rt.GeometryClass and int(node.inode.handle) not in have:
                self.items.append(Part(node))
                added += 1
        return added

    def cfg_line(self) -> str:
        pairs = ",".join('{"%s","%s"}' % (part.cls, self.point_name(part)) for part in self.items)
        return "multiStructureParts[] = {%s};" % pairs


def find_point(name: str):
    return next((node for node in rt.objects if rt.classOf(node) == rt.Point and str(node.name) == name), None)


def build_points(parts: Parts) -> int:
    """A memory point at the bounding-box centre of every part"""
    for part in parts.items:
        name = parts.point_name(part)
        centre = part.node.center
        point = find_point(name)
        if point is None:
            memory.add_point((centre.x, centre.y, centre.z), name)
        else:
            point.pos = centre
            memory.layer(create=True).addNode(point)
    rt.redrawViews()
    return len(parts.items)


def centre(part: Part) -> None:
    """Move the part to the origin, as it will be exported"""
    part.node.pos -= part.node.center


def restore(parts: Parts, part: Part) -> bool:
    point = find_point(parts.point_name(part))
    if point is None:
        return False
    part.node.pos += point.pos - part.node.center
    return True


def _centroid(node):
    get = rt.polyop.getVert
    try:
        count = int(rt.polyop.getNumVerts(node))
    except Exception:  # noqa: BLE001 - not an Editable Poly
        return node.center
    if count <= 0:
        return node.center
    step = max(1, count // 20000)
    picked = range(1, count + 1, step)
    total = rt.Point3(0, 0, 0)
    for index in picked:
        total += get(node, index)
    return total / float(len(picked))


def verify(parts: Parts) -> List[str]:
    """Per part: does its memory point sit at the bbox centre, and how far is the centroid from it"""
    lines = []
    for part in parts.items:
        node = part.node
        box = node.center
        shift = _centroid(node) - box
        point = find_point(parts.point_name(part))
        if point is None:
            where = "NO POINT (the bbox centre will be used)"
        elif rt.length(point.pos - box) > 0.001:
            where = "point %s is not at the bbox centre" % point.pos
        else:
            where = "point ok"
        lines.append("%s: bbox %s, centroid off by %.4f m, %s" % (node.name, box, float(rt.length(shift)), where))
    lines.append("A centroid that is off the bbox centre is how far autocenter=1 would move the part in game.")
    return lines


def parse_props(text: str) -> list:
    """"name=value; name2=value2" as [(name, value)]"""
    found = []
    for piece in (text or "").split(";"):
        key, sep, value = piece.partition("=")
        if sep and key.strip():
            found.append((key.strip(), value.strip()))
    return found


def geometry_for(name: str) -> list:
    """Objects of the Geometry layer that belong to a part: named <part> or <part>_..."""
    layer = rt.LayerManager.getLayerFromName("Geometry")
    if layer is None:
        return []
    define_maxscript()
    low = name.lower()
    return [node for node in rt.zaslehLayerNodes(layer) if rt.superClassOf(node) == rt.GeometryClass and
            (str(node.name).lower() == low or str(node.name).lower().startswith(low + "_"))]


def _copies(nodes, offset) -> list:
    made = []
    for node in nodes:
        copy = rt.convertToPoly(rt.copy(node))
        copy.name = node.name
        copy.pos -= offset
        made.append(copy)
    return made


def _lod(nodes, resolution: float, props: list, registry, textures, notes, serial: int):
    layer = rt.LayerManager.newLayerFromName("zasleh_multistructure_tmp_%d" % serial)
    try:
        for node in nodes:
            layer.addNode(node)
        set_layer_info(layer, {"resolution": resolution, "properties": [list(pair) for pair in props]})
        return reader.read_layer(layer, registry, textures, notes)
    finally:
        for node in nodes:
            if rt.isValidNode(node):
                rt.delete(node)
        rt.LayerManager.deleteLayerByName(layer.name)


def export_parts(parts: Parts, folder: str, options: Optional[exporter.Options] = None, autocenter_off: bool = True,
                 with_geometry: bool = False, geometry_props: str = "", mass_all: float = 0.0) -> dict:
    """One p3d per part: a visual LOD and, if asked, a Geometry LOD from the Geometry layer"""
    define_maxscript()
    registry = reg.Registry.load()
    report = {"ok": [], "failed": [], "no_geometry": [], "notes": []}
    serial = 0
    for part in [p for p in parts.items if rt.isValidNode(p.node)]:
        name = str(part.node.name)
        path = os.path.join(folder, name + ".p3d")
        point = find_point(parts.point_name(part))
        offset = point.pos if point is not None else part.node.center
        if point is None:
            report["notes"].append("%s has no point %s: its bbox centre was used" % (name, parts.point_name(part)))
        try:
            textures = exporter.Textures(options, path)
            base = [("autocenter", "0")] if autocenter_off else []
            model = P3D()
            serial += 1
            model.lods.append(_lod(_copies([part.node], offset), 0.0, base, registry, textures, report["notes"], serial))
            sources = geometry_for(name) if with_geometry else []
            if with_geometry and not sources:
                report["no_geometry"].append(name)
            if sources:
                pieces = _copies(sources, offset)
                total = part.mass if part.mass > 0 else mass_all
                if total > 0:
                    counts = [int(rt.polyop.getNumVerts(piece)) for piece in pieces]
                    for piece, count in zip(pieces, counts):
                        faces = list(range(1, int(rt.polyop.getNumFaces(piece)) + 1))
                        mass.set_mass(piece, registry, total * count / float(sum(counts)), "faces", faces)
                    registry.save()
                serial += 1
                model.lods.append(_lod(pieces, GEOMETRY, base + parse_props(geometry_props), registry, textures,
                                       report["notes"], serial))
            formats.write(model, path)
            done = textures.finish()
            report["notes"] += done.get("texture_notes", [])
            report["ok"].append(name)
        except (reader.SceneError, formats.P3DError, OSError) as error:
            report["failed"].append("%s: %s" % (name, error))
    rt.redrawViews()
    return report
