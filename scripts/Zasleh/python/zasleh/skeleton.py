"""What the scene offers for a model.cfg: selection names, memory points, object links"""

import re

import pymxs

from zasleh import formats

from . import exporter, groups
from . import registry as reg
from .scene import layer_info, layer_resolution, user_prop
from .memory import names_of

rt = pymxs.runtime
_SKIP = re.compile(r"^(component\d+|proxy:.*)$", re.I)


def scene_names() -> tuple:
    """(selection names of the mesh LODs, names of the Memory LOD), sorted"""
    try:
        registry = reg.Registry.load()
    except reg.OldScene:
        return [], []
    names, memory = set(), set()
    for candidate in exporter.candidate_layers():
        if not candidate["checked"]:
            continue
        layer = rt.LayerManager.getLayerFromName(candidate["layer"])
        resolution = layer_resolution(layer)
        target = memory if formats.lod_name(resolution) == "Memory" else names
        for node in rt.zaslehLayerNodes(layer):
            if rt.classOf(node) == rt.Point:
                target.update(names_of(node))
            elif rt.superClassOf(node) == rt.GeometryClass:
                if rt.classOf(node.baseobject) == rt.Editable_Poly:
                    listed = groups.groups_on(node, registry)
                    if listed is None:
                        listed = groups.groups_on(node, registry, rescan=True)
                    target.update(listed)
                if user_prop(node, "nosel") is not True:
                    target.add(str(node.name))
    clean = lambda found: sorted((n for n in found if n and not _SKIP.match(n)), key=str.lower)     # noqa: E731
    return clean(names), clean(memory)


def bones_from_links() -> list:
    """(object, its parent) for the linked geometry of the scene: the old way to lay out a skeleton"""
    pairs = []
    for node in rt.objects:
        if rt.superClassOf(node) == rt.GeometryClass:
            parent = node.parent
            pairs.append((str(node.name), str(parent.name) if parent is not None else ""))
    linked = {name for name, parent in pairs if parent} | {parent for _name, parent in pairs if parent}
    return [(name, parent) for name, parent in pairs if name in linked]


def model_name() -> str:
    for candidate in exporter.candidate_layers():
        info = layer_info(rt.LayerManager.getLayerFromName(candidate["layer"]))
        if info.get("model"):
            return str(info["model"])
    name = str(rt.maxFileName or "")
    return name.rsplit(".", 1)[0] if name else "model"
