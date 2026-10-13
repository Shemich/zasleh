"""LOD layers: add, rename, duplicate, delete, show one at a time"""

import pymxs

import atb_p3d
from atb_p3d import lods

from .scene import define_maxscript, layer_info, set_layer_info

rt = pymxs.runtime


class LodError(Exception):
    pass


def standard_names() -> list:
    """Names to offer for a new LOD"""
    names = [str(n) for n in range(1, 7)]
    return names + ["Shadow Volume 0", "Shadow Volume 10"] + [name for _resolution, name in lods.SPECIAL_LODS]


def _layer(name: str):
    layer = rt.LayerManager.getLayerFromName(name)
    if layer is None:
        raise LodError("There is no layer \"%s\"." % name)
    return layer


def _free(name: str) -> str:
    name = name.strip()
    if not name:
        raise LodError("Type a name for the LOD.")
    if rt.LayerManager.getLayerFromName(name) is not None:
        raise LodError("There already is a layer \"%s\"." % name)
    return name


def add(name: str):
    layer = rt.LayerManager.newLayerFromName(_free(name))
    layer.current = True
    return layer


def rename(old: str, new: str) -> None:
    layer = _layer(old)
    if old == "0":
        raise LodError("The default layer cannot be renamed.")
    layer.setName(_free(new))


def duplicate(source: str, name: str) -> int:
    """Copy a LOD with everything on it into a new layer; returns the number of objects"""
    define_maxscript()
    layer = _layer(source)
    target = rt.LayerManager.newLayerFromName(_free(name))
    nodes = list(rt.atbLayerNodes(layer))
    count = 0
    if nodes:
        done, copies = rt.maxOps.cloneNodes(rt.Array(*nodes), cloneType=rt.Name("copy"), newNodes=pymxs.byref(None))
        for original, copy in zip(nodes, copies or []):
            copy.name = original.name       # keep the name: it may be a selection
            target.addNode(copy)
            count += 1
    info = dict(layer_info(layer))
    if info:
        resolution = lods.lod_resolution(name.split(" [")[0])
        if resolution is not None:
            info["resolution"] = resolution
        else:
            info.pop("resolution", None)
        set_layer_info(target, info)
    return count


def delete(name: str) -> int:
    """Delete a LOD layer with its objects; returns the number of objects"""
    define_maxscript()
    if name == "0":
        raise LodError("The default layer cannot be deleted.")
    layer = _layer(name)
    nodes = list(rt.atbLayerNodes(layer))
    if layer.current:
        rt.LayerManager.getLayer(0).current = True
    if nodes:
        rt.delete(rt.Array(*nodes))
    rt.LayerManager.deleteLayerByName(name)
    return len(nodes)


def show_only(name: str) -> None:
    """Hide every other layer and make this one current"""
    chosen = _layer(name)
    manager = rt.LayerManager
    for index in range(int(manager.count)):
        other = manager.getLayer(index)
        other.ishidden = other.name != chosen.name
    chosen.current = True
    rt.redrawViews()


def show_all() -> None:
    manager = rt.LayerManager
    for index in range(int(manager.count)):
        manager.getLayer(index).ishidden = False
    rt.redrawViews()


def describe(name: str) -> str:
    resolution = lods.lod_resolution(name.split(" [")[0])
    return atb_p3d.lod_name(resolution) if resolution is not None else ""


def properties(name: str) -> list:
    """The named properties of a LOD, as (key, value)"""
    return [(str(key), str(value)) for key, value in layer_info(_layer(name)).get("properties", [])]


def set_properties(name: str, text: str) -> int:
    """Named properties from lines of "key = value"; gives how many there are"""
    found = []
    for number, line in enumerate(text.replace(";", "\n").split("\n"), 1):
        key, sep, value = line.partition("=")
        if not line.strip():
            continue
        if not sep or not key.strip():
            raise LodError("Line %d is not \"key = value\": %s" % (number, line.strip()))
        if any(key.strip().lower() == known.lower() for known, _value in found):
            raise LodError("The property \"%s\" is there twice." % key.strip())
        found.append((key.strip(), value.strip()))
    layer = _layer(name)
    info = layer_info(layer)
    info["properties"] = [list(pair) for pair in found]
    set_layer_info(layer, info)
    return len(found)
