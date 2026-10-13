"""Vert groups check in headless 3ds Max: create, edit"""
import json
import os
import sys
import traceback

import pymxs

rt = pymxs.runtime
out = {"checks": {}}


def check(name, condition, detail=None):
    out["checks"][name] = bool(condition) if detail is None else [bool(condition), detail]


try:
    scripts = str(rt.getDir(rt.Name("scripts")))
    sys.path.insert(0, os.path.join(scripts, "Zasleh", "python"))

    import atb_p3d
    from atb_p3d import compare
    from atb_max import exporter, groups, importer, reader, selections
    from atb_max import registry as reg

    rt.resetMaxFile(rt.Name("noPrompt"))
    polyop = rt.polyop
    plane = rt.convertToPoly(rt.Plane(length=6, width=6, lengthsegs=6, widthsegs=6, name="hull"))
    layer = rt.LayerManager.newLayerFromName("1")
    layer.addNode(plane)
    registry = reg.Registry.load()
    position = {i: polyop.getVert(plane, i) for i in range(1, int(polyop.getNumVerts(plane)) + 1)}
    face_verts = {f: [int(v) for v in polyop.getFaceVerts(plane, f)] for f in range(1, int(polyop.getNumFaces(plane)) + 1)}
    check("plane is 49 vertices, 36 quads", (len(position), len(face_verts)) == (49, 36))

    # verts: the left three columns of verts (x <= -1)
    left = sorted(i for i, p in position.items() if p.x <= -1 + 1e-4)
    groups.assign(plane, registry, "left", 1.0, "verts", left)
    weights, faces = groups.members(plane, registry, "left")
    inside = {f for f, verts in face_verts.items() if all(v in left for v in verts)}
    check("assign vertices: those vertices", sorted(weights) == left and set(groups.weights(plane, registry, "left").values()) == {1.0})
    check("assign vertices: polygons they close come along", faces == inside and len(inside) == 12, len(faces))

    # polys: one quad in the right half; its neighbours stay out although they share verts
    panel = next(f for f, verts in face_verts.items() if all(position[v].x >= 1 - 1e-4 for v in verts))
    groups.assign(plane, registry, "panel", 1.0, "faces", [panel])
    weights, faces = groups.members(plane, registry, "panel")
    check("assign polygon: exactly that polygon and its vertices", faces == {panel} and sorted(weights) == sorted(face_verts[panel]))
    # four quads around a fifth: the one in the middle has all its verts in, but was not picked
    middle = next(f for f, verts in face_verts.items()
                  if all(abs(position[v].x - 1.5) <= 0.5 + 1e-4 and abs(position[v].y - 0.5) <= 0.5 + 1e-4 for v in verts))
    ring = sorted(f for f, verts in face_verts.items()
                  if f != middle and len(set(verts) & set(face_verts[middle])) == 2)
    groups.assign(plane, registry, "ell", 1.0, "faces", ring)
    weights, faces = groups.members(plane, registry, "ell")
    check("polygons are taken as picked, not guessed from vertices", len(ring) == 4 and faces == set(ring) and
          all(v in weights for v in face_verts[middle]), [sorted(faces), ring, middle])
    block = ring
    found = groups.inspect(plane, registry)
    check("inspect: the polygon inside a group by its vertices, but not in it, is reported",
          found["open"] == {"ell": [middle]} and not found["torn"] and not found["blended"] and not found["ngons"],
          {k: v for k, v in found.items() if k != "ungrouped"})
    grouped = set(left) | set(face_verts[panel]) | {v for f in ring for v in face_verts[f]}
    check("inspect: vertices in no group", found["ungrouped"] == sorted(set(position) - grouped), len(found["ungrouped"]))

    # weights
    soft = left[:7]
    groups.assign(plane, registry, "soft", 0.5, "verts", soft)
    weights, faces = groups.members(plane, registry, "soft")
    check("weighted group", registry.get("soft")["kind"] == reg.WEIGHTED and sorted(weights) == soft and
          all(abs(w - 0.5) < 1e-6 for w in groups.weights(plane, registry, "soft").values()), registry.get("soft"))
    check("other groups in the same channel are untouched",
          groups.members(plane, registry, "left")[1] == inside and groups.members(plane, registry, "panel")[1] == {panel})

    check("an object without a kept list is not scanned behind the user's back", groups.groups_on(plane, registry) is None)
    listed = groups.groups_on(plane, registry, rescan=True)
    check("groups are listed", listed == ["ell", "left", "panel", "soft"], listed)
    # a plain group becomes a weighted one when a weight below 1 is assigned
    groups.assign(plane, registry, "panel", 0.25, "verts", [face_verts[panel][0]])
    panel_weights = groups.weights(plane, registry, "panel")
    check("plain group turned weighted keeps its members", registry.is_weighted("panel") and
          sorted(panel_weights) == sorted(face_verts[panel]) and
          sorted(round(w, 3) for w in panel_weights.values()) == [0.25, 1.0, 1.0, 1.0] and
          groups.members(plane, registry, "panel")[1] == {panel}, panel_weights)

    # "left" and "blocker" overlap, so they can't share a layer; both must stay whole
    overlap = left[:10]
    groups.assign(plane, registry, "blocker", 1.0, "verts", overlap)
    check("overlapping groups both keep their vertices",
          set(overlap) <= groups.members(plane, registry, "blocker")[0] and
          groups.members(plane, registry, "left")[0] == set(left) and groups.members(plane, registry, "left")[1] == inside)
    # growing "blocker" over more of "left": wherever it lives, it must end up complete, faces too
    more = left[:21]
    groups.assign(plane, registry, "blocker", 1.0, "verts", more)
    blocker_faces = {f for f, verts in face_verts.items() if all(v in more for v in verts)}
    check("a group that grows into another group's vertices stays complete",
          groups.members(plane, registry, "blocker") == (set(more), blocker_faces) and
          groups.members(plane, registry, "left") == (set(left), inside),
          [len(groups.members(plane, registry, "blocker")[0]), len(blocker_faces)])
    groups.clear(plane, registry, "blocker")

    # remove
    edge_column = [i for i in left if abs(position[i].x + 1) < 1e-4]            # the x = -1 column
    groups.remove(plane, registry, "left", "verts", edge_column)
    weights, faces = groups.members(plane, registry, "left")
    check("remove vertices: they and the polygons using them leave",
          not set(edge_column) & set(weights) and len(faces) == 6 and len(weights) == 14, [len(weights), len(faces)])
    groups.remove(plane, registry, "ell", "faces", block[:2])
    weights, faces = groups.members(plane, registry, "ell")
    check("remove polygons: vertices no remaining polygon uses leave too",
          faces == set(block[2:]) and sorted(weights) == sorted({v for f in block[2:] for v in face_verts[f]}),
          [sorted(faces), sorted(weights)])

    # select
    groups.select(plane, registry, "left")
    check("select sets the vertex and polygon selection",
          {int(i) for i in rt.atbBits(polyop.getVertSelection(plane))} == set(groups.members(plane, registry, "left")[0]) and
          len(list(rt.atbBits(polyop.getFaceSelection(plane)))) == 6)

    def picked_verts(node):
        return {int(i) for i in rt.atbBits(polyop.getVertSelection(node))}

    left_now, ell_now = groups.members(plane, registry, "left")[0], groups.members(plane, registry, "ell")[0]
    groups.select(plane, registry, "ell", "add")
    added = picked_verts(plane)
    groups.select(plane, registry, "left", "subtract")
    check("select: add to the selection, take out of it",
          added == left_now | ell_now and picked_verts(plane) == ell_now - left_now and len(ell_now) > 0)

    # set: the group becomes exactly what is picked
    corner_a, corner_b = face_verts[1], face_verts[36]
    groups.redefine(plane, registry, "spot", 1.0, "verts", corner_a)
    groups.redefine(plane, registry, "spot", 1.0, "verts", corner_b)
    check("set: a plain group is exactly the picked vertices", groups.members(plane, registry, "spot") == (set(corner_b), {36}),
          groups.members(plane, registry, "spot"))
    groups.redefine(plane, registry, "spot", 0.75, "faces", [1])
    spot = groups.weights(plane, registry, "spot")
    check("set: with a weight, on polygons", sorted(spot) == sorted(corner_a) and
          all(abs(w - 0.75) < 1e-6 for w in spot.values()) and groups.members(plane, registry, "spot")[1] == {1}, spot)
    groups.clear(plane, registry, "spot")
    check("set: cleared afterwards", groups.members(plane, registry, "spot") == (set(), set()))

    # show in colour: a channel of its own, a map vert per vert
    status = groups.show(plane, registry, "soft")
    soft_now = groups.weights(plane, registry, "soft")
    same_topology = all([int(m) for m in polyop.getMapFace(plane, reg.DISPLAY_CHANNEL, f)] == face_verts[f] for f in face_verts)

    def colour(vertex):
        value = polyop.getMapVert(plane, reg.DISPLAY_CHANNEL, vertex)
        return (round(value.x, 3), round(value.y, 3), round(value.z, 3))

    inside_colour = {colour(v) for v in soft_now}
    outside_colour = {colour(v) for v in position if v not in soft_now}
    check("show: members get the colour of their weight, the rest is grey",
          same_topology and inside_colour == {(0.0, 1.0, 0.0)} and outside_colour == {(0.22, 0.22, 0.22)} and
          groups.heat(1.0) == (1.0, 0.0, 0.0) and groups.heat(0.0) == (0.0, 0.0, 1.0),
          [same_topology, sorted(inside_colour), sorted(outside_colour), status])
    check("show: the object displays that channel", bool(plane.showVertexColors) and
          int(plane.vertexColorMapChannel) == reg.DISPLAY_CHANNEL and groups.shown(plane) == "soft")
    groups.hide(plane)
    check("hide: colours off, channel gone", not bool(plane.showVertexColors) and groups.shown(plane) == "" and
          not polyop.getMapSupport(plane, reg.DISPLAY_CHANNEL))

    # rename on this object only: the group moves to the new name here, other objects keep the old one
    registry.save()
    kept = (groups.members(plane, registry, "left"), groups.members(plane, registry, "soft"),
            sorted(groups.weights(plane, registry, "soft").items()))
    groups.rename_here(plane, registry, "left", "left_here")
    groups.rename_here(plane, registry, "soft", "soft_here")
    check("rename here: a plain and a weighted group keep their vertices, polygons and weights",
          groups.members(plane, registry, "left_here") == kept[0] and groups.members(plane, registry, "left") == (set(), set()) and
          groups.members(plane, registry, "soft_here") == kept[1] and
          sorted(groups.weights(plane, registry, "soft_here").items()) == kept[2] and
          groups.members(plane, registry, "soft") == (set(), set()) and registry.is_weighted("soft_here"),
          [len(kept[0][0]), len(kept[0][1]), kept[2][:2]])
    try:
        groups.rename_here(plane, registry, "ell", "left_here")
        check("rename here: refused onto a group the object has", False)
    except groups.GroupError as error:
        check("rename here: refused onto a group the object has", "already has a group" in str(error), str(error))
    groups.rename_here(plane, registry, "left_here", "left")
    groups.rename_here(plane, registry, "soft_here", "soft")
    check("rename here: and back", groups.members(plane, registry, "left") == kept[0] and
          groups.members(plane, registry, "soft") == kept[1] and
          sorted(groups.weights(plane, registry, "soft").items()) == kept[2])
    try:
        groups.new(plane, registry, "left", 1.0, "verts", [1])
        check("new: refused when the object has the group", False)
    except groups.GroupError as error:
        check("new: refused when the object has the group", "Use Redefine" in str(error), str(error))

    # undo: the panel's own history (3ds Max keeps no undo record for map channels)
    registry.save()

    def snapshot():
        names = ("left", "ell", "soft", "panel")
        channels = [c for c in range(10, int(polyop.getNumMaps(plane))) if polyop.getMapSupport(plane, c)]
        return ({n: groups.members(plane, registry, n) for n in names},
                {n: sorted((v, round(w, 4)) for v, w in groups.weights(plane, registry, n).items()) for n in ("soft", "panel")},
                {c: int(polyop.getNumMapVerts(plane, c)) for c in channels})

    before = snapshot()
    with groups.recorded("Assign"):
        groups.assign(plane, registry, "undo_me", 1.0, "verts", left[:12])      # overlaps "left": takes a layer of its own
        registry.save()
    with groups.recorded("Remove"):
        groups.remove(plane, registry, "left", "verts", left[:5])
        registry.save()
    with groups.recorded("Set"):
        groups.redefine(plane, registry, "soft", 0.5, "verts", left[10:14])
        registry.save()
    edited = snapshot()
    said = [groups.undo_last(), groups.undo_last(), groups.undo_last()]
    registry = reg.Registry.load()
    check("undo: three steps taken back, the mesh and the scene table are as before",
          said == ["Undone: Set", "Undone: Remove", "Undone: Assign"] and edited != before and snapshot() == before and
          "undo_me" not in registry.ids, [said, snapshot()[2], before[2]])
    try:
        groups.undo_last()
        check("undo: nothing left", False)
    except groups.GroupError as error:
        check("undo: nothing left", "Nothing to undo" in str(error), str(error))
    try:
        with groups.recorded("Assign"):
            groups.assign(plane, registry, "undo_me", 1.0, "verts", left[:12])
            raise groups.GroupError("stopped half-way")
    except groups.GroupError:
        pass
    registry = reg.Registry.load()
    check("undo: an edit that fails half-way is taken back at once", snapshot() == before and not groups._history)

    # rename, then export: the groups are named selections of the LOD
    groups.rename(registry, "panel", "camo1")
    registry.save()
    model, _report = exporter.build_model(["1"])
    lod = model.lods[0]
    names = sorted(s.name for s in lod.selections)
    check("export: groups are selections; the object name is one too", names == ["camo1", "ell", "hull", "left", "soft"], names)
    check("export: weights", sorted(set(lod.selection("soft").weights)) == [0, 128] and
          len(lod.selection("left").point_indices()) == 14 and len(lod.selection("left").face_indices()) == 6)
    check("export: camo1 is one face, four points",
          (len(lod.selection("camo1").point_indices()), len(lod.selection("camo1").face_indices())) == (4, 1))
    check("export: hull is everything", len(lod.selection("hull").point_indices()) == 49 and len(lod.selection("hull").face_indices()) == 36)

    # the mesh is edited afterwards: groups follow
    before = len(groups.members(plane, registry, "left")[0])
    polyop.extrudeFaces(plane, rt.execute("#{%s}" % ",".join(str(f) for f in sorted(groups.members(plane, registry, "left")[1]))), 0.5)
    for edge in range(1, 9):
        polyop.divideEdge(plane, edge, 0.5)
    weights, faces = groups.members(plane, registry, "left")
    check("after extrude and edge splits the group is still there and grew with the new vertices",
          len(weights) > before and len(faces) >= 6, [before, len(weights), len(faces)])
    try:
        exporter.build_model(["1"])
        check("the edited mesh still exports (or says why not)", True)
    except reader.SceneError as error:
        check("the edited mesh still exports (or says why not)", "more than 4 corners" in str(error), str(error))

    # clear
    groups.clear(plane, registry, "soft")
    check("clear takes the object out of the group", groups.members(plane, registry, "soft") == (set(), set()) and
          "soft" not in groups.groups_on(plane, registry) and "soft" not in groups.scan(plane, registry))

    # errors are messages, not crashes
    for label, call in (("empty name", lambda: groups.assign(plane, registry, "  ", 1.0, "verts", [1])),
                        ("name with #", lambda: groups.assign(plane, registry, "#x", 1.0, "verts", [1])),
                        ("unknown group", lambda: groups.remove(plane, registry, "nope", "verts", [1])),
                        ("nothing picked", lambda: groups.assign(plane, registry, "x", 1.0, "verts", [])),
                        ("rename onto an existing name", lambda: groups.rename(registry, "left", "camo1"))):
        try:
            call()
            check("refused: " + label, False)
        except groups.GroupError:
            check("refused: " + label, True)

    # check: what modelling does to groups. A strip of two quads: left column "port", right column "star".
    probe = rt.convertToPoly(rt.Plane(length=2, width=2, lengthsegs=2, widthsegs=1, name="probe"))
    rt.setUserProp(probe, "atb_nosel", True)
    where = {i: polyop.getVert(probe, i) for i in range(1, int(polyop.getNumVerts(probe)) + 1)}
    port = sorted(i for i, p in where.items() if p.x < 0)
    star = sorted(i for i, p in where.items() if p.x > 0)
    groups.assign(probe, registry, "port", 1.0, "verts", port)
    groups.assign(probe, registry, "star", 1.0, "verts", star)
    found = groups.inspect(probe, registry)
    check("check: a clean object has nothing to report", (len(port), len(star)) == (3, 3) and
          not any(found[key] for key in ("ungrouped", "torn", "blended", "open", "ngons")), found)
    check("check: says so", groups.check(probe, registry) == ("Checked: nothing to fix.", ""))
    # a new vert on an edge between the two groups belongs to neither
    edge = next(e for e in range(1, int(polyop.getNumEdges(probe)) + 1)
                if {int(v) for v in polyop.getEdgeVerts(probe, e)} == {port[0], star[0]})
    polyop.divideEdge(probe, edge, 0.5)
    new_vertex = int(polyop.getNumVerts(probe))
    found = groups.inspect(probe, registry)
    check("check: a vertex made between two groups is reported, and the polygon it turned into a 5-gon",
          found["blended"] == [new_vertex] and found["ungrouped"] == [new_vertex] and not found["torn"] and
          len(found["ngons"]) >= 1, found)
    status, report = groups.check(probe, registry)
    check("check: the report names it and selects it", "border of a group" in report and "more than 4 corners" in report and
          picked_verts(probe) == {new_vertex} and status.startswith("Checked: "), [status, report])
    status = groups.ungrouped(probe, registry)
    check("ungrouped: selects them", picked_verts(probe) == {new_vertex} and status.startswith("1 vertices"), status)
    groups.assign(probe, registry, "port", 1.0, "verts", [new_vertex])
    check("check: assigning the vertex settles it", not groups.inspect(probe, registry)["blended"] and
          new_vertex in groups.members(probe, registry, "port")[0])
    # two objects, each a group of its own, attached and welded along the seam
    seam = rt.convertToPoly(rt.Plane(length=2, width=2, lengthsegs=1, widthsegs=1, name="seam"))
    other = rt.convertToPoly(rt.Plane(length=2, width=2, lengthsegs=1, widthsegs=1, pos=rt.Point3(2, 0, 0)))
    groups.assign(seam, registry, "port", 1.0, "faces", [1])
    groups.assign(other, registry, "star", 1.0, "faces", [1])
    polyop.attach(seam, other)
    polyop.weldVertsByThreshold(seam, rt.execute("#{1..8}"))
    found = groups.inspect(seam, registry)
    torn = found["torn"]
    status, report = groups.check(seam, registry)
    check("check: seam vertices welded from two groups are reported and selected", int(polyop.getNumVerts(seam)) == 6 and
          len(torn) == 2 and "claimed by two groups" in report and picked_verts(seam) == set(torn), [found, report])
    groups.assign(seam, registry, "port", 1.0, "verts", torn)
    groups.assign(seam, registry, "star", 1.0, "verts", torn)
    found = groups.inspect(seam, registry)
    check("check: assigning them to both groups settles it", not found["torn"] and
          set(torn) <= groups.members(seam, registry, "port")[0] and set(torn) <= groups.members(seam, registry, "star")[0] and
          len(groups.members(seam, registry, "port")[0]) == 4 and len(groups.members(seam, registry, "star")[0]) == 4, found)
    rt.delete(seam)
    # a strip of three quads with the outer two in a group: the middle one is inside by its verts
    strip = rt.convertToPoly(rt.Plane(length=3, width=1, lengthsegs=3, widthsegs=1, name="strip"))
    ends = [f for f in (1, 2, 3) if len({int(v) for v in polyop.getFaceVerts(strip, f)} &
                                        {int(v) for g in (1, 2, 3) if g != f for v in polyop.getFaceVerts(strip, g)}) == 2]
    groups.assign(strip, registry, "gap", 1.0, "faces", ends)
    status, report = groups.check(strip, registry)
    hole = [f for f in (1, 2, 3) if f not in ends]
    check("check: a polygon left out of a group that has all its vertices", len(ends) == 2 and
          groups.inspect(strip, registry)["open"] == {"gap": hole} and "\"gap\" 1" in report, report)
    groups.select(strip, registry, "gap")
    groups.assign(strip, registry, "gap", 1.0, "verts", sorted(picked_verts(strip)))
    check("check: select, then assign at vertex level, takes it in", not groups.inspect(strip, registry)["open"] and
          groups.members(strip, registry, "gap")[1] == {1, 2, 3})
    # the panel refuses to undo an edit once the mesh was changed after it
    registry.save()
    with groups.recorded("Assign"):
        groups.assign(strip, registry, "late", 1.0, "faces", [1])
        registry.save()
    polyop.divideEdge(strip, 1, 0.5)
    try:
        groups.undo_last()
        check("undo: refused after the mesh was changed", False)
    except groups.GroupError as error:
        check("undo: refused after the mesh was changed", "changed after that step" in str(error) and not groups._history and
              len(groups.members(strip, registry, "late")[1]) >= 1, str(error))
    rt.delete(strip)

    # delete: out of every object of the scene; a weighted group gives its slot back
    twin = rt.convertToPoly(rt.Plane(length=2, width=2, lengthsegs=1, widthsegs=1, name="twin"))
    rt.setUserProp(twin, "atb_nosel", True)
    groups.assign(twin, registry, "port", 1.0, "verts", [1, 2])
    groups.assign(twin, registry, "fade", 0.5, "verts", [1, 2, 3])
    groups.assign(probe, registry, "fade", 0.5, "verts", [1])
    status = groups.delete(registry, "port")
    check("delete: the group leaves every object", status == "port: taken out of 2 object(s)" and
          groups.members(probe, registry, "port") == (set(), set()) and groups.members(twin, registry, "port") == (set(), set()) and
          "port" not in groups.scan(probe, registry) and len(groups.members(probe, registry, "star")[0]) == 3, status)
    status = groups.delete(registry, "fade")
    check("delete: a weighted group gives its slot back", registry.get("fade") is None and
          "fade" not in groups.scan(twin, registry) and "fade" not in groups.scan(probe, registry), status)
    rt.delete(twin)
    rt.delete(probe)

    # components: three boxes attached into one object
    first = rt.convertToPoly(rt.Box(length=1, width=1, height=1, name="geo"))
    for x in (3, 6):
        polyop.attach(first, rt.convertToPoly(rt.Box(length=1, width=1, height=1, pos=rt.Point3(x, 0, 0))))
    rt.setUserProp(first, "atb_nosel", True)
    geometry = rt.LayerManager.newLayerFromName("Geometry")
    geometry.addNode(first)
    status = groups.find_components(first, registry)
    registry.save()
    model, _report = exporter.build_model(["Geometry"])
    lod = model.lods[0]
    found = {s.name: (len(s.point_indices()), len(s.face_indices())) for s in lod.selections}
    check("find components: one per piece", status == "3 component(s)" and
          found == {"Component01": (8, 6), "Component02": (8, 6), "Component03": (8, 6)}, [status, found])
    check("components are listed", groups.groups_on(first, registry) == ["Component01", "Component02", "Component03"])
    # finding them again replaces them instead of piling up
    polyop.attach(first, rt.convertToPoly(rt.Box(length=1, width=1, height=1, pos=rt.Point3(9, 0, 0))))
    again = groups.find_components(first, registry)
    registry.save()
    check("find components again: four, none left over", again == "4 component(s)" and
          groups.groups_on(first, registry) == ["Component01", "Component02", "Component03", "Component04"] and
          all(len(groups.members(first, registry, "Component%02d" % n)[0]) == 8 for n in range(1, 5)), again)
    model, _report = exporter.build_model(["Geometry"])
    lod = model.lods[0]
    check("mass tag written for the geometry LOD", lod.mass == [0.0] * 32)

    # what the panel calls, with the object selected (object level: the whole object)
    rt.select(plane)
    state = selections.run("assign", "everything")
    check("panel: assign at object level", state["object"] == "hull" and "everything" in state["names"] and
          "polygons assigned" in state["status"], state)
    count = len(groups.members(plane, reg.Registry.load(), "everything")[1])
    check("the whole object went in", count == int(polyop.getNumFaces(plane)), count)
    check("select reports counts", "polygons" in selections.run("select", "everything")["status"])
    check("selection change shows the kept list", "everything" in selections.run("auto")["names"])
    shown_first = selections.run("show", "everything")["shown"]
    same_topology = all([int(m) for m in polyop.getMapFace(plane, reg.DISPLAY_CHANNEL, f)] ==
                        [int(v) for v in polyop.getFaceVerts(plane, f)] for f in range(1, int(polyop.getNumFaces(plane)) + 1))
    state = selections.run("assign", "everything")                  # an edit repaints
    check("panel: show in colour, also on the edited mesh", shown_first == "everything" and same_topology and
          state["shown"] == "everything" and bool(plane.showVertexColors), [shown_first, same_topology])
    state = selections.run("hide")
    check("panel: colours off", state["shown"] == "" and not bool(plane.showVertexColors))
    state = selections.run("check")
    check("panel: check", state["status"].startswith("Checked: "), [state["status"], state["report"][:200]])
    rt.subobjectLevel = 0
    polyop.setFaceSelection(plane, rt.execute("#{1}"))
    state = selections.run("set", "one")
    check("panel: redefine at object level takes the whole object", "now the" in state["status"] and "one" in state["names"],
          state["status"])
    state = selections.run("delete", "one")
    check("panel: delete everywhere", "taken out of" in state["status"] and "one" not in state["names"] and
          "everything" in state["names"], state["status"])
    state = selections.run("mass_set", kilograms=80.0)
    got = selections.run("mass_get")
    check("panel: mass", state["status"].startswith("Mass: 80 kg") and abs(got["kilograms"] - 80.0) < 1e-3,
          [state["status"], got["status"]])
    check("panel: undo", selections.run("undo")["status"] == "Undone: Set mass")
    # several objects at once: whole objects go in and out of a group
    other = rt.convertToPoly(rt.Plane(length=2, width=2, lengthsegs=1, widthsegs=1, name="other"))
    rt.select(rt.Array(plane, other))
    state = selections.run("assign", "both")
    registry_now = reg.Registry.load()
    check("several objects: assign puts every one in", state["object"] == "2 objects" and "2 of 2 objects" in state["status"] and
          len(groups.members(other, registry_now, "both")[1]) == 1 and
          len(groups.members(plane, registry_now, "both")[1]) == int(polyop.getNumFaces(plane)) and
          "both" in state["names"] and "everything" in state["names"], state)
    state = selections.run("rename_here", "everything", "all_of_it")
    check("several objects: an object without the group is passed over", "1 of 2 objects" in state["status"] and
          len(groups.members(plane, reg.Registry.load(), "all_of_it")[1]) > 0, state["status"])
    check("several objects: what needs one object says so", "works on one" in selections.run("select", "both")["status"])
    state = selections.run("undo")
    state = selections.run("undo")
    registry_now = reg.Registry.load()
    check("several objects: undo takes back the edit on all of them", state["status"] == "Undone: Assign" and
          "both" not in registry_now.ids and len(groups.members(plane, registry_now, "everything")[1]) > 0, state["status"])
    rt.delete(other)
    rt.clearSelection()
    state = selections.run("refresh")
    check("no object selected: a message, an empty list", state["status"] == "Select one Editable Poly object." and
          state["names"] == [], state["status"])
    # Undo isn't checked here: "max undo" crashes headless 3ds Max even for a plain vert move.

    # an imported model: add verts to one of its groups, export, and nothing else may change
    sample = os.environ.get("ATB_SAMPLE", "")
    if sample and os.path.isfile(sample):
        rt.resetMaxFile(rt.Name("noPrompt"))
        source = atb_p3d.read(sample)
        result = importer.import_p3d(sample)
        registry = reg.Registry.load()
        before_model, _r = exporter.build_model()
        info = next(row for row in result["lods"] if row.get("selections"))
        layer = rt.LayerManager.getLayerFromName(info["layer"])
        node = [n for n in rt.atbLayerNodes(layer) if rt.superClassOf(n) == rt.GeometryClass][0]
        listed = groups.groups_on(node, registry)                  # kept by the importer: no scan
        check("imported model: the kept list is what a scan finds", listed == [n for n in groups.scan(node, registry)
                                                                              if not n.startswith("#")], len(listed or []))
        check("imported model: its groups are listed", len(listed) > 0, len(listed))
        target = listed[0]
        had_weights, had_faces = groups.members(node, registry, target)
        outside = [v for v in range(1, int(polyop.getNumVerts(node)) + 1) if v not in had_weights][:5]
        groups.assign(node, registry, target, 1.0, "verts", outside)
        registry.save()
        after_model, _r = exporter.build_model()
        differences = compare.diff_models(before_model, after_model)
        changed = [(atb_p3d.lod_name(res), d) for res, d in differences]
        only_that = (len(changed) == 1 and set(changed[0][1]) == {"selections_changed"} and
                     [c[0] for c in changed[0][1]["selections_changed"]] == [target])
        check("imported model: editing one group changes that selection only", only_that, str(changed)[:300])
        out["sample_group"] = [target, len(had_weights), len(outside)]
    out["ok"] = all((v if isinstance(v, bool) else v[0]) for v in out["checks"].values())
except Exception as error:  # noqa: BLE001
    out["ok"] = False
    out["error"] = "%s: %s" % (type(error).__name__, error)
    out["trace"] = traceback.format_exc()
with open(os.environ["ATB_OUT"], "w", encoding="utf-8") as stream:
    json.dump(out, stream, indent=1, default=str)
