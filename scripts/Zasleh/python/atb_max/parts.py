"""Selections split off a LOD's mesh into objects of their own: proxies, wheels... An export joins them again."""

from __future__ import annotations

from fnmatch import fnmatchcase
from glob import escape
from typing import Dict, Iterable, List, Optional, Tuple

import pymxs

from . import bulk, groups
from . import registry as reg
from .scene import PROXY_PREFIX, define_maxscript, layer_info, layers, to_bits

rt = pymxs.runtime


def patterns_of(text: str, proxies: bool = False) -> List[str]:
    """Patterns typed into a field ("wheel_*, otocvez"); the one for proxies goes first if asked"""
    typed = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    return ([PROXY_PREFIX + "*"] if proxies else []) + typed


def matching(names: Iterable[str], patterns: Iterable[str]) -> List[str]:
    """The names that fit a pattern (* and ?, any case), pattern by pattern, each name once"""
    names = list(names)
    out: List[str] = []
    for pattern in patterns:
        for name in names:
            if name not in out and fnmatchcase(name.lower(), pattern.lower()):
                out.append(name)
    return out


def _faces(node, registry: reg.Registry, names: List[str]) -> Dict[str, List[int]]:
    """Faces (1-based) of each group on the object"""
    raw = bulk.read_poly(node)
    if raw is not None:
        try:
            out: Dict[str, List[int]] = {name: [] for name in names}
            numbers = {registry.ids[name]: name for name in names if name in registry.ids}
            for channel in registry.layers:
                data = raw.channel(channel)
                if data is None:
                    continue
                for face, number in enumerate(raw.layer(data)[1], 1):
                    if number in numbers:
                        out[numbers[number]].append(face)
            for name in names:
                if registry.is_weighted(name):
                    channel, component = reg.Registry.place(registry.get(name)["slot"])
                    data = raw.channel(channel)
                    if data is not None:
                        inside = raw.slot(data, component, False)[1]
                        out[name] = sorted(set(out[name]) | {face for face, on in enumerate(inside, 1) if on})
            return out
        except Exception as problem:  # noqa: BLE001 - MAXScript still reads any object
            bulk.poly_error = str(problem).replace("\n", " ")[:300]
    return {name: sorted(groups.members(node, registry, name)[1]) for name in names
            if name in registry.ids or registry.is_weighted(name)}


def split(node, registry: reg.Registry, names: List[str], layer=None) -> list:
    """Detach the faces of each group into an object named after it. A face goes with the first group that has it."""
    define_maxscript()
    faces_of = _faces(node, registry, names)
    total = int(rt.polyop.getNumFaces(node))
    taken: set = set()
    made = []
    for name in names:
        faces = [face for face in faces_of.get(name, ()) if face not in taken]
        if not faces or len(faces) == total:        # nothing of it here, or the object is this part already
            continue
        before = int(rt.objects.count)
        rt.polyop.detachFaces(node, to_bits(faces), delete=False, asNode=True, name=name)
        if int(rt.objects.count) == before:
            continue
        part = rt.objects[before]
        part.name = name                            # 3ds Max numbers a name another LOD has already
        part.material = node.material
        part.wirecolor = node.wirecolor
        rt.setUserProp(part, "atb_nosel", True)     # the selection is in the map channels, as in the LOD's mesh
        rt.setUserProp(part, "atb_part", name)
        (layer or node.layer).addNode(part)
        made.append(part)
        taken.update(faces)
    if not taken:
        return made
    rest = []
    if len(taken) == total:
        rt.delete(node)                             # all of it went into parts
    else:
        rt.polyop.deleteFaces(node, to_bits(taken), delIsoVerts=True)
        rt.polyop.collapseDeadStructs(node)
        rest = [node]
    for each in made + rest:
        groups.groups_on(each, registry, rescan=True)
    return made


def split_layer(layer, registry: reg.Registry, patterns: Iterable[str]) -> int:
    names = matching(layer_info(layer).get("selections", []), patterns)
    count = 0
    if names:
        for node in list(rt.atbLayerNodes(layer)):
            whole = rt.getUserProp(node, "atb_part") is None          # a part isn't split again
            if whole and rt.classOf(node.baseobject) == rt.Editable_Poly and int(node.modifiers.count) == 0:
                count += len(split(node, registry, names, layer))
    return count


def split_scene(patterns: Iterable[str], layer_names: Optional[Iterable[str]] = None) -> Dict[str, int]:
    """Split the LOD layers (all, or the named ones): {layer: objects made}"""
    define_maxscript()
    patterns = list(patterns)
    wanted = None if layer_names is None else set(layer_names)
    registry = reg.Registry.load()
    out: Dict[str, int] = {}
    with pymxs.undo(False):
        for layer in layers():
            if patterns and (wanted is None or str(layer.name) in wanted):
                made = split_layer(layer, registry, patterns)
                if made:
                    out[str(layer.name)] = made
    return out


def by_bones(bones: List[Tuple[str, str]]) -> Tuple[Dict[str, int], int]:
    """Lay a skeleton out in the scene: the selection of every (bone, parent) becomes an object,
    linked to the object of its parent bone in the same LOD. Gives ({layer: objects made}, links made)."""
    define_maxscript()
    parent_of = {name.lower(): parent.lower() for name, parent in bones}

    def depth(name: str) -> int:
        steps, seen = 0, set()
        while parent_of.get(name) and name not in seen:
            seen.add(name)
            name = parent_of[name]
            steps += 1
        return steps

    # the deepest first: a face that a bone shares with its parent goes with the bone
    names = sorted((name for name, _parent in bones), key=lambda name: -depth(name.lower()))
    made = split_scene([escape(name) for name in names])
    links = 0
    with pymxs.undo(False):
        for layer in layers():
            found = {}
            for node in rt.atbLayerNodes(layer):
                part = rt.getUserProp(node, "atb_part")
                if part is not None:
                    found.setdefault(str(part).lower(), node)
            for name, node in found.items():
                parent, seen = parent_of.get(name, ""), {name}
                while parent and parent not in found and parent not in seen:     # a bone with nothing in this LOD
                    seen.add(parent)
                    parent = parent_of.get(parent, "")
                if parent in found and parent not in seen and node.parent != found[parent]:
                    node.parent = found[parent]
                    links += 1
    return made, links
