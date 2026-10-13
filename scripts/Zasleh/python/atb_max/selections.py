"""What the Selections tab asks for: one action on the selected objects in, what the tab shows next out"""

from __future__ import annotations

import json
from typing import List, Set, Tuple

import pymxs

from . import groups, importer, mass, materials, settings
from . import registry as reg
from .groups import (GroupError, assign, cached_names, check, clear, delete, find_components, groups_on, hide, new,
                     recorded, redefine, remove, rename, rename_here, select, show, shown, target_nodes, touch,
                     undo_last, ungrouped)

rt = pymxs.runtime

_LABELS = {"assign": "Assign", "new": "New", "set": "Redefine", "remove": "Remove", "clear": "Delete",
           "delete": "Delete (All LODs)", "rename_here": "Rename", "rename": "Rename (All LODs)",
           "components": "Find components", "mass_set": "Set mass"}


_EDITS = ("assign", "new", "set", "remove", "clear", "delete", "rename_here", "rename", "components", "mass_set")
_ONE_OBJECT = ("select", "ungrouped", "mass_set", "mass_get")
_QUIET = ("auto", "refresh", "select", "check", "ungrouped", "mass_get", "show", "hide")


def _edit(node, registry: reg.Registry, action: str, name: str, new_name: str, weight: float, kilograms: float) -> str:
    if action == "assign":
        return assign(node, registry, name, weight)
    if action == "new":
        return new(node, registry, name, weight)
    if action == "set":
        return redefine(node, registry, name, weight)
    if action == "remove":
        return remove(node, registry, name)
    if action == "clear":
        return clear(node, registry, name)
    if action == "rename_here":
        status = rename_here(node, registry, name, new_name)
        if shown(node) == name.strip():
            rt.setAppData(node, reg.SHOWN_APPDATA_ID, new_name.strip())
        return status
    if action == "components":
        return find_components(node, registry)
    if action == "mass_set":
        return mass.set_mass(node, registry, kilograms)
    raise GroupError("unknown action " + action)


def run(action: str, name: str = "", new_name: str = "", weight: float = 1.0,
        mode: str = "replace", kilograms: float = 0.0) -> dict:
    """One action of the panel on the selected objects; returns what the panel shows afterwards"""
    nodes: list = []
    registry = None
    names: List[str] = []
    status = ""
    report = ""
    try:
        registry = reg.Registry.load()
        if action == "undo":                # works whatever is selected
            status = undo_last()
            registry = reg.Registry.load()
            action = "auto"
            try:
                nodes = target_nodes()
            except GroupError:
                raise GroupError(status)
        else:
            nodes = target_nodes()
        several = len(nodes) > 1
        if several and action in _ONE_OBJECT:
            raise GroupError("%d objects are selected: this works on one." % len(nodes))
        if action == "refresh":
            for node in nodes:
                groups_on(node, registry, rescan=True)
        elif action == "select":
            status = select(nodes[0], registry, name, mode)
        elif action == "check":
            found = [(str(node.name),) + check(node, registry) for node in nodes]
            status = found[0][1] if not several else "Checked %d objects, see the log." % len(found)
            report = "\n\n".join((label + ":\n" if several else "") + text for label, _status, text in found if text)
        elif action == "ungrouped":
            status = ungrouped(nodes[0], registry)
        elif action == "mass_get":
            kilograms, count = mass.get_mass(nodes[0], registry)
            status = "Mass of the %d picked points: %g kg" % (count, kilograms)
        elif action in ("show", "hide"):
            with pymxs.undo(False):
                for node in nodes:
                    status = show(node, registry, name) if action == "show" else hide(node)
        elif action in _EDITS:
            with recorded(_LABELS.get(action, action)):
                for node in nodes:
                    touch(node)
                if action == "delete":
                    status = delete(registry, name)
                elif action == "rename":
                    status = rename(registry, name, new_name)
                    for node in nodes:
                        cached = cached_names(node)
                        if cached is not None:
                            rt.setAppData(node, reg.GROUPS_APPDATA_ID,
                                          json.dumps([new_name.strip() if n == name.strip() else n for n in cached]))
                        if shown(node) == name.strip():
                            rt.setAppData(node, reg.SHOWN_APPDATA_ID, new_name.strip())
                else:
                    done, problem = 0, None
                    for node in nodes:
                        try:
                            status = _edit(node, registry, action, name, new_name, weight, kilograms)
                            done += 1
                        except GroupError as error:
                            if not several:
                                raise
                            problem = error             # e.g. this object does not have the group
                    if not done and problem is not None:
                        raise problem
                    if several:
                        status = "%d of %d objects - %s" % (done, len(nodes), status)
                registry.save()
        elif action != "auto":
            raise GroupError("unknown action " + action)
        if action not in _QUIET:
            for node in nodes:
                painted = shown(node)
                if painted:
                    with pymxs.undo(False):         # keep the colours in step with the edit
                        try:
                            show(node, registry, painted)
                        except GroupError:
                            hide(node)
        names, unread = listed(nodes, registry, rescan=action not in ("auto", "select", "show", "hide"))
        if unread:
            status = status or "Right click the list > Refresh to read this object's groups."
    except (GroupError, reg.OldScene) as error:
        status = str(error)
        if nodes and registry is not None:
            names, _unread = listed(nodes, registry, rescan=False)
    return {"names": names,
            "weighted": {n for n in names if registry is not None and registry.is_weighted(n)},
            "object": "" if not nodes else str(nodes[0].name) if len(nodes) == 1 else "%d objects" % len(nodes),
            "status": status, "report": report,
            "shown": shown(nodes[0]) if len(nodes) == 1 else "",
            "kilograms": kilograms}


def listed(nodes, registry: reg.Registry, rescan: bool) -> Tuple[List[str], bool]:
    """The groups of the objects together; True as well if some object's list is not known"""
    names: Set[str] = set()
    unread = False
    for node in nodes:
        found = groups_on(node, registry)
        if found is None and rescan:
            found = groups_on(node, registry, rescan=True)
        if found is None:
            unread = True
        else:
            names.update(found)
    return sorted(names, key=str.lower), unread


def face_materials(name: str) -> dict:
    """What the faces of a selection of the selected object carry: {"pairs": [(texture, rvmat, faces)], "status"}"""
    try:
        node = target_nodes()[0]
        _verts, faces = groups.members(node, reg.Registry.load(), name)
    except (GroupError, reg.OldScene, IndexError) as error:
        return {"pairs": [], "status": str(error)}
    if not faces:
        return {"pairs": [], "status": "%s has no faces on this object" % name}
    pairs = materials.of_faces(node, sorted(faces), settings.default_texture_root())
    status = "" if len(pairs) == 1 else "%s: %d different textures / materials on its faces, the most used is shown" % (name, len(pairs))
    return {"pairs": pairs, "status": status}


def set_face_materials(name: str, texture: str, rvmat: str) -> str:
    """The faces of a selection get this texture and this .rvmat, on every selected object that has it"""
    try:
        nodes = target_nodes()
        registry = reg.Registry.load()
    except (GroupError, reg.OldScene) as error:
        return str(error)
    done = 0
    with pymxs.undo(True):
        for node in nodes:
            try:
                _verts, faces = groups.members(node, registry, name)
            except GroupError:
                continue
            if faces:
                materials.put_on_faces(node, sorted(faces), texture.strip(), rvmat.strip(), importer.arma_material)
                done += len(faces)
    rt.redrawViews()
    if not done:
        return "%s has no faces on the selected object(s)" % name
    return "%s: %d face(s) now have %s%s" % (name, done, texture.strip() or "no texture",
                                           " and " + rvmat.strip() if rvmat.strip() else "")
