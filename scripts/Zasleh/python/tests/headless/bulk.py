"""The bulk helper (zasleh/bulk.py), in headless 3ds Max: it builds"""
import json
import os
import sys
import traceback
from array import array

import pymxs

rt = pymxs.runtime
out = {"checks": {}}


def check(name, condition, detail=None):
    out["checks"][name] = bool(condition) if detail is None else [bool(condition), detail]


try:
    sys.path.insert(0, os.path.join(str(rt.getDir(rt.Name("scripts"))), "Zasleh", "python"))
    from zasleh import formats
    from zasleh.formats import meshprep, smoothing
    from zasleh import bulk, importer

    importer.define_maxscript()
    check("the helper builds", bulk.available(), bulk.error)

    # a quad (two tris) and a tri: material ids 2 and 5, smoothing groups 1 and 0x80000001
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0)]
    tris = [(0, 1, 2), (0, 2, 3), (1, 4, 2)]
    map_verts = [(0.1 * i, 0.2 * i, 0.0) for i in range(6)]
    map_tris = [(0, 1, 2), (0, 2, 3), (4, 5, 2)]
    point3 = rt.Point3
    reference = rt.zaslehBuildMesh([point3(*v) for v in verts], [point3(a + 1, b + 1, c + 1) for a, b, c in tris],
                                [1], [2, 2, 5], [1, 1, 0x80000001 - 0x100000000], "reference")
    rt.zaslehSetChannel(reference, 1, [point3(*v) for v in map_verts], [point3(a + 1, b + 1, c + 1) for a, b, c in map_tris])
    rt.update(reference)
    node = bulk.new_node("filled")
    flags = array("I", [3 | (1 << 16), 6 | (1 << 16), 7 | (4 << 16)])
    bulk.set_geometry(node, array("f", [c for v in verts for c in v]), array("i", [i for t in tris for i in t]),
                      array("I", [1, 1, 0x80000001]), flags)
    bulk.set_channel(node, 1, array("f", [c for v in map_verts for c in v]), array("i", [i for t in map_tris for i in t]))
    rt.update(node)

    def describe(mesh):
        rt.execute("global zaslehBulkTestMesh = undefined")
        rt.zaslehBulkTestMesh = mesh
        return str(rt.execute('''(
            local m = zaslehBulkTestMesh
            local s = stringStream ""
            format "v=% f=% " m.numverts m.numfaces to:s
            for i = 1 to m.numverts do format "% " (getVert m i) to:s
            for f = 1 to m.numfaces do format "| % id=% sg=% vis=%,%,% " (getFace m f) (getFaceMatID m f) (getFaceSmoothGroup m f) (getEdgeVis m f 1) (getEdgeVis m f 2) (getEdgeVis m f 3) to:s
            format "| maps=% tv=% " (meshop.getNumMaps m) (meshop.getNumMapVerts m 1) to:s
            for i = 1 to (meshop.getNumMapVerts m 1) do format "% " (meshop.getMapVert m 1 i) to:s
            for f = 1 to m.numfaces do format "% " (meshop.getMapFace m 1 f) to:s
            s as string
        )'''))

    check("a mesh filled through the helper is the mesh MAXScript builds", describe(node) == describe(reference),
          [describe(node), describe(reference)])
    check("the face flags are those 3ds Max sets itself", bulk.face_flags(node, 3) == bulk.face_flags(reference, 3),
          [bulk.face_flags(node, 3), bulk.face_flags(reference, 3)])
    poly = rt.convertToPoly(node)
    check("as an Editable Poly: a quad and a triangle",
          [int(rt.polyop.getFaceDeg(poly, f)) for f in (1, 2)] == [4, 3])

    # map channels worked out by the helper: a UV set and a data channel
    session_node = bulk.new_node("session")
    session = bulk.Session(session_node, verts, [10, 11, 12, 13, 14], tris, [0, 0, 1], [(0, 1, 2), (0, 2, 3), (0, 1, 2)])
    session.geometry(array("I", [0, 0, 0]), array("I", [3, 6, 7]))
    # p3d face 0 is the quad (4 corners), face 1 the tri; the shared verts 1 and 2 have other UVs there
    uvs = array("f", [0, 0, 1, 0, 1, 1, 0, 1, 0.5, 0.5, 0.75, 0.5, 0.75, 0.25])
    made = session.uv(1, uvs, array("i", [0, 4, 7]))
    seen_uv = [(round(v.x, 3), round(v.y, 3)) for v in (rt.meshop.getMapVert(session_node, 1, i) for i in range(1, made + 1))]
    seen_faces = [[int(i) for i in rt.meshop.getMapFace(session_node, 1, f)] for f in (1, 2, 3)]
    check("uv: a map vertex per different (vertex, u, v), v turned upside down",
          made == 7 and seen_uv == [(0, 1), (1, 1), (1, 0), (0, 0), (0.5, 0.5), (0.75, 0.5), (0.75, 0.75)] and
          seen_faces == [[1, 2, 3], [1, 3, 4], [5, 6, 7]], [made, seen_uv, seen_faces])
    # x: a number per p3d point; z: 2 on face 0 only -> verts 1 and 2 need a second map vert for the tri
    numbers = array("d", bytes(8 * 15))
    for point in (10, 11, 12, 13, 14):
        numbers[point] = float(point)
    made = session.data(12, [numbers, None, None], [None, None, array("d", [2.0, 0.0])])
    values = [(v.x, v.y, v.z) for v in (rt.meshop.getMapVert(session_node, 12, i) for i in range(1, made + 1))]
    faces12 = [[int(i) for i in rt.meshop.getMapFace(session_node, 12, f)] for f in (1, 2, 3)]
    check("data: point part + face part per corner, extra map vertices only where a vertex needs two values",
          made == 7 and values[:5] == [(10, 0, 2), (11, 0, 2), (12, 0, 2), (13, 0, 2), (14, 0, 0)] and
          sorted(values[5:]) == [(11, 0, 0), (12, 0, 0)] and faces12[:2] == [[1, 2, 3], [1, 3, 4]] and
          faces12[2][1] == 5 and sorted(faces12[2]) == [5, 6, 7], [made, values, faces12])

    # mesh preparation: the helper against the Python reference
    def same(lod):
        reference = meshprep.prepare(lod, 1000)
        fast = meshprep.prepare(lod, 1000, accel=bulk)
        for field in ("points", "verts", "faces", "tris", "tri_face", "tri_corners", "quads", "mat_ids", "groups",
                      "smoothing_wrong", "loose", "carriers", "dropped"):
            a, b = getattr(reference, field), getattr(fast, field)
            if isinstance(a, list):
                a, b = [tuple(x) if isinstance(x, (list, tuple)) else x for x in a], \
                       [tuple(x) if isinstance(x, (list, tuple)) else x for x in b]
            if a != b:
                return field
        return ""

    # a double-sided quad, a fin on one of its edges (three faces on an edge) and a far tri
    from zasleh.formats import LOD, Face
    lod = LOD(1.0)
    lod.points = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1), (0.5, 1, 0.5), (5, 0, 0), (6, 0, 0), (6, 0, 1)]
    lod.point_flags = [0] * 8
    lod.normals = [(0.0, 1.0, 0.0)]
    for points in ((0, 1, 2, 3), (3, 2, 1, 0), (0, 1, 4), (5, 6, 7)):
        lod.faces.append(Face.new(points, (0,) * len(points), ((0.0, 0.0),) * len(points), texture="", material=""))
    lod.taggs.append(formats.SharpEdges([(0, 1)]))
    check("prepare: a double-sided face with a fin, same as the reference", same(lod) == "", same(lod))
    # more than 32 separately smoothed surfaces at one point: the count of wrongly shaded points too
    fan = LOD(1.0)
    fan.points = [(0.0, 0.0, 0.0)]
    count = 40
    for i in range(count):
        fan.points += [(float(i), 1.0, 0.0), (float(i), 1.0, 1.0), (float(i), 2.0, 0.5)]
        a, b, c = 1 + 3 * i, 2 + 3 * i, 3 + 3 * i
        fan.faces.append(Face.new((0, a, b), (0, 0, 0), ((0.0, 0.0),) * 3, texture="", material=""))
        fan.faces.append(Face.new((b, a, c), (0, 0, 0), ((0.0, 0.0),) * 3, texture="", material=""))
    fan.point_flags = [0] * len(fan.points)
    fan.normals = [(0.0, 1.0, 0.0)]
    fan.taggs.append(formats.SharpEdges([]))
    reference_groups, reference_wrong = smoothing.to_smoothing_groups([f.points for f in fan.faces], [])
    fast_groups, fast_wrong = bulk.to_smoothing_groups([f.points for f in fan.faces], [])
    check("smoothing: 40 surfaces at a point, the same groups and the same count of points that cannot be right",
          fast_groups == reference_groups and fast_wrong == reference_wrong and reference_wrong > 0,
          [reference_wrong, fast_wrong])
    check("smoothing: sharp edges between points no face uses are ignored",
          bulk.to_smoothing_groups([(0, 1, 2), (2, 1, 3)], [(7, 9), (-1, 2)]) ==
          smoothing.to_smoothing_groups([(0, 1, 2), (2, 1, 3)], [(7, 9), (-1, 2)]))

    # normals and sharp edges for the export: the helper against the Python reference
    from zasleh.formats import normals

    def same_normals(lod):
        faces = [face.points for face in lod.faces]
        flags = [face.flags for face in lod.faces]
        reference = normals.compute(lod.points, lod.point_flags, faces, flags, lod.sharp_edges, {})
        fast = bulk.compute_normals(lod.points, lod.point_flags, faces, flags, lod.sharp_edges, {})
        if [tuple(n) for n in reference[0]] != [tuple(n) for n in fast[0]]:
            return "normals"
        if [list(i) for i in reference[1]] != [list(i) for i in fast[1]]:
            return "indices"
        made, _wrong = smoothing.to_smoothing_groups(faces, lod.sharp_edges)
        return "" if smoothing.sharp_edges(faces, made) == bulk.sharp_edges(faces, made) else "sharp edges"

    check("normals: a double-sided face with a fin and a fan of 40 surfaces, same as the reference",
          same_normals(lod) == "" and same_normals(fan) == "", [same_normals(lod), same_normals(fan)])

    sample = os.environ.get("ZASLEH_SAMPLE", "")
    if sample and os.path.isfile(sample):
        model = formats.read(sample)
        different = [formats.lod_name(l.resolution) + ": " + same(l) for l in model.lods if same(l)]
        check("prepare: every LOD of a real model, same as the reference", not different, different)
        different = [formats.lod_name(l.resolution) + ": " + same_normals(l) for l in model.lods
                     if l.faces and same_normals(l)]
        check("normals: every LOD of a real model, same as the reference", not different, different)

    # reading an Editable Poly for the export: the helper against MAXScript
    from zasleh import groups, reader
    from zasleh import registry as reg
    rt.resetMaxFile(rt.Name("noPrompt"))
    barrel = rt.convertToPoly(rt.Cylinder(radius=1, height=2, sides=8, heightsegs=2, mapcoords=True, name="barrel"))
    barrel.rotation = rt.EulerAngles(30, 45, 60)
    barrel.pos = rt.Point3(5, -3, 2)
    barrel.scale = rt.Point3(1.5, 1, 0.5)
    registry = reg.Registry.load()
    groups.assign(barrel, registry, "ring", 1.0, "faces", [3, 4, 5])
    groups.assign(barrel, registry, "soft", 0.4, "verts", [1, 2, 3, 9])
    registry.save()

    def read():
        mesh = reader._Mesh(barrel, registry, lambda material, material_id: ("tex%d" % material_id, ""))
        return {"points": mesh.points, "faces": mesh.faces, "groups": mesh.groups, "materials": mesh.face_materials,
                "uv": mesh.uv, "slots": mesh.slots, "layers": mesh.layers, "ngons": mesh.ngons, "split": mesh.split}

    fast = read()
    used_helper = bulk.poly_error == ""
    bulk.poly_error = "switched off by the test"
    slow = read()
    bulk.poly_error = ""
    far = max(abs(a - b) for p, q in zip(fast["points"], slow["points"]) for a, b in zip(p, q))
    rest = [key for key in fast if key != "points" and fast[key] != slow[key]]
    check("reading an Editable Poly: the helper gives what MAXScript gives",
          used_helper and len(fast["points"]) == len(slow["points"]) and far < 1e-5 and not rest and
          fast["split"] == 2 and len(fast["uv"]) == 1 and len(fast["layers"]) >= 1 and "soft" in fast["slots"],
          [used_helper, bulk.poly_error, far, rest, fast["split"], sorted(fast["slots"])])

    # when the helper is off, the same calls take the Python way
    bulk.disable("switched off by the test")
    check("switched off: prepare still works through the same calls", same(lod) == "" and not bulk.available())
    out["ok"] = all((v if isinstance(v, bool) else v[0]) for v in out["checks"].values())
except Exception as error:  # noqa: BLE001
    out["ok"] = False
    out["error"] = "%s: %s" % (type(error).__name__, error)
    out["trace"] = traceback.format_exc()
with open(os.environ["ZASLEH_OUT"], "w", encoding="utf-8") as stream:
    json.dump(out, stream, indent=1, default=str)
