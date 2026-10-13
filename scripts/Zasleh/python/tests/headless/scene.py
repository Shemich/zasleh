"""Exporter check in headless 3ds Max on a scene built by hand"""
import json
import os
import shutil
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
    from atb_p3d import lods
    from atb_max import exporter, reader

    rt.resetMaxFile(rt.Name("noPrompt"))
    manager = rt.LayerManager
    layer1 = manager.newLayerFromName("1")
    body = rt.convertToPoly(rt.Box(length=2, width=4, height=1, name="body"))
    material = rt.PhysicalMaterial(name="body_mat")
    material.base_color_map = rt.Bitmaptexture(filename=exporter.default_texture_root() + "test\\data\\body_co.tga")
    body.material = material
    rt.rotate(body, rt.EulerAngles(0, 0, 90))
    wheel = rt.convertToPoly(rt.Sphere(radius=0.5, segs=8, name="wheel"))
    rt.move(wheel, rt.Point3(3, 0, 0))
    layer1.addNode(body)
    layer1.addNode(wheel)
    layer2 = manager.newLayerFromName("2")
    layer2.addNode(rt.Box(length=1, width=1, height=1, name="prim"))            # not collapsed
    memory = manager.newLayerFromName("Memory")
    for x in (0.0, 1.0):
        memory.addNode(rt.Point(pos=rt.Point3(x, 5, 0), name="axis_wheel"))
    memory.addNode(rt.Point(pos=rt.Point3(9, 9, 9), name="pos_driver"))
    geometry = manager.newLayerFromName("Geometry")
    geometry.addNode(rt.convertToPoly(rt.Box(length=2, width=4, height=1, name="Component01")))
    junk = manager.newLayerFromName("my helpers")                                 # not a LOD name
    junk.addNode(rt.convertToPoly(rt.Box(name="junk")))

    candidates = {c["layer"]: c for c in exporter.candidate_layers()}
    out["candidates"] = candidates
    check("LOD layers are recognised", all(candidates[n]["checked"] for n in ("1", "2", "Memory", "Geometry")))
    check("a layer that is not a LOD is offered unchecked", candidates["my helpers"]["checked"] is False)

    folder = os.environ["ATB_TMP"]
    path = os.path.join(folder, "atb_scene_test.p3d")
    exporter.export_p3d(path, [name for name, c in candidates.items() if c["checked"]])
    check("file written", os.path.isfile(path))
    model = atb_p3d.read(path)
    os.remove(path)
    by_name = {lods.lod_name(lod.resolution): lod for lod in model.lods}
    check("four LODs, sorted", [lods.lod_name(l.resolution) for l in model.lods] == ["1", "2", "Geometry", "Memory"],
          [lods.lod_name(l.resolution) for l in model.lods])

    one = by_name["1"]
    sphere_points = len(one.points) - 8
    check("LOD 1: object names became selections", sorted(s.name for s in one.selections) == ["body", "wheel"])
    body_selection, wheel_selection = one.selection("body"), one.selection("wheel")
    check("LOD 1: body = 8 points, 6 faces", (len(body_selection.point_indices()), len(body_selection.face_indices())) == (8, 6))
    check("LOD 1: wheel has the rest", len(wheel_selection.point_indices()) == sphere_points and sphere_points > 8)
    textures = sorted({face.texture for face in one.faces})
    check("LOD 1: texture path from the bitmap, as the old exporter makes it",
          textures == ["", "test\\data\\body_co.paa"], textures)
    xs = [one.points[i][0] for i in wheel_selection.point_indices()]
    check("moved object is exported where it stands", abs(min(xs) - 2.5) < 1e-4 and abs(max(xs) - 3.5) < 1e-4, [min(xs), max(xs)])
    box = [one.points[i] for i in body_selection.point_indices()]
    span = [max(p[k] for p in box) - min(p[k] for p in box) for k in range(3)]
    # box 4 (x) by 2 (y) by 1 (z) in Max, turned 90 degrees about z: 2 by 4 by 1; p3d is (x, z, y)
    check("rotated object is exported as it stands", [round(v, 3) for v in span] == [2.0, 1.0, 4.0], span)
    box_faces = [one.faces[i].points for i in body_selection.face_indices()]
    box_sharp = {tuple(sorted(e)) for e in one.sharp_edges if e[0] in body_selection.point_indices()}
    check("box edges are sharp, sphere is smooth", len(box_sharp) == 12 and len(one.sharp_edges) == 12, len(one.sharp_edges))
    check("normals written for every corner", len(one.normals) > 8 and all(
        0 <= n < len(one.normals) for face in one.faces for n in face.normals))
    check("no problems in LOD 1", one.problems() == [], one.problems())
    # a box corner has three normals (one per side), each of length 1
    lengths = [sum(c * c for c in n) ** 0.5 for n in one.normals]
    check("normals are unit vectors", all(abs(v - 1.0) < 1e-4 for v in lengths))

    two = by_name["2"]
    check("primitive read through a snapshot: 8 points, 6 quads",
          (len(two.points), [f.n for f in two.faces]) == (8, [4] * 6))
    check("primitive: its name is a selection", [s.name for s in two.selections] == ["prim"])

    mem = by_name["Memory"]
    check("memory points", len(mem.points) == 3 and len(mem.faces) == 0)
    check("memory selections", {s.name: len(s.point_indices()) for s in mem.selections} == {"axis_wheel": 2, "pos_driver": 1},
          {s.name: len(s.point_indices()) for s in mem.selections})
    geo = by_name["Geometry"]
    check("geometry: Component01 and a mass tag", [s.name for s in geo.selections] == ["Component01"] and geo.mass == [0.0] * 8)
    check("no mass tag outside geometry LODs", one.mass is None and mem.mass is None)

    # polys with more than four corners are written as tris and quads; the scene keeps them
    layer3 = manager.newLayerFromName("3")
    barrel = rt.convertToPoly(rt.Cylinder(radius=1, height=1, sides=8, name="barrel"))
    layer3.addNode(barrel)
    polyop = rt.polyop

    def degrees(node):
        return [int(polyop.getFaceDeg(node, f)) for f in range(1, int(polyop.getNumFaces(node)) + 1)]

    scene_faces = degrees(barrel)
    model3, report3 = exporter.build_model(["3"])
    three = model3.lods[0]
    check("n-gons are cut into triangles and quads", max(scene_faces) > 4 and all(f.n in (3, 4) for f in three.faces) and
          len(three.faces) > len(scene_faces) and len(three.points) == int(polyop.getNumVerts(barrel)) and
          three.problems() == [], [sorted(set(scene_faces)), len(scene_faces), len(three.faces), three.problems()])
    check("n-gons: the scene is left as it was, and the report says what was done",
          degrees(barrel) == scene_faces and len(list(rt.atbLayerNodes(layer3))) == 1 and
          any("barrel" in note for note in report3["notes"]) and
          len(three.selection("barrel").face_indices()) == len(three.faces), report3["notes"])

    # mass: kilograms spread over the picked points of a geometry LOD
    from atb_max import mass
    from atb_max import registry as reg
    check("a geometry LOD without mass is pointed out",
          any("mass is 0" in note for note in exporter.build_model(["Geometry"])[1]["notes"]))
    registry = reg.Registry.load()
    component = rt.getNodeByName("Component01")
    status = mass.set_mass(component, registry, 1200.0, "faces", list(range(1, 7)))
    registry.save()
    kilograms, count = mass.get_mass(component, registry, "verts", [1, 2, 3, 4])
    model_g, report_g = exporter.build_model(["Geometry"])
    geo = model_g.lods[0]
    check("mass: spread evenly over the object", status == "Mass: 1200 kg over 8 points (150 kg each)" and
          all(abs(m - 150.0) < 1e-3 for m in geo.mass) and report_g["lods"][0]["mass"] == 1200.0 and
          not report_g["notes"], [status, geo.mass, report_g])
    check("mass: of the picked vertices", abs(kilograms - 600.0) < 1e-3 and count == 4, [kilograms, count])
    mass.set_mass(component, registry, 100.0, "verts", [1, 2, 3, 4])
    geo = exporter.build_model(["Geometry"])[0].lods[0]
    check("mass: set on some vertices only", sorted(round(m, 3) for m in geo.mass) == [25.0] * 4 + [150.0] * 4 and
          [s.name for s in geo.selections] == ["Component01"], geo.mass)
    check("mass: outside a geometry LOD there is a note",
          "only a Geometry LOD" in mass.set_mass(body, registry, 10.0, "faces", [1]))

    # export options for materials made in 3ds Max: plain paths, .paa paths, .rvmat, deploy
    work = os.path.join(folder, "atb_export_test")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "proj", "src"))
    os.makedirs(os.path.join(work, "proj", "model"))
    source = os.path.join(work, "proj", "src", "hull_co.png")
    with open(source, "wb") as stream:
        stream.write(b"not really a picture")
    hull = rt.convertToPoly(rt.Box(length=1, width=1, height=1, name="hull"))
    hull_material = rt.Standardmaterial(name="hull_mat")
    hull_material.diffuseMap = rt.Bitmaptexture(filename=source)
    hull.material = hull_material
    manager.newLayerFromName("4").addNode(hull)
    target = os.path.join(work, "proj", "model", "hull.p3d")

    def written():
        return sorted({(face.texture, face.material) for face in atb_p3d.read(target).lods[0].faces})

    report4 = exporter.export_p3d(target, ["4"], exporter.Options(tex_root=work, convert_paa=False))
    check("options: the bitmap's own path, relative to the texture root",
          written() == [("proj\\src\\hull_co.png", "")] and "rvmats" not in report4 and "deploy" not in report4 and
          not os.path.isdir(os.path.join(work, "proj", "model", "data")), written())
    full = exporter.Options(tex_root=work, gen_rvmat=True, deploy=True, deploy_dir="data")
    report4 = exporter.export_p3d(target, ["4"], full)
    data = os.path.join(work, "proj", "model", "data")
    rvmat = os.path.join(data, "hull.rvmat")
    rvmat_text = open(rvmat).read() if os.path.isfile(rvmat) else ""
    check("options: .paa paths into the deploy folder, and an .rvmat on the faces",
          written() == [("proj\\model\\data\\hull_co.paa", "proj\\model\\data\\hull.rvmat")], written())
    check("options: the .rvmat is written and names the normal and specular maps", report4.get("rvmats") == 1 and
          "hull_nohq.paa" in rvmat_text and "hull_smdi.paa" in rvmat_text and "Super" in rvmat_text and
          rvmat_text.count("class Stage") == 7, rvmat_text[:200])
    deploy = report4.get("deploy", {})
    check("options: without ImageToPAA nothing is passed off as a .paa; maps without a source are left to the user",
          not os.path.isfile(os.path.join(data, "hull_co.paa")) and
          {k: deploy.get(k) for k in ("converted", "copied", "kept", "by_hand", "failed")} ==
          {"converted": 0, "copied": 0, "kept": 0, "by_hand": 2, "failed": 1} and
          any("ImageToPAA" in note for note in report4["notes"]), [deploy, report4["notes"]])
    plain = exporter.Options(tex_root=work, convert_paa=False, deploy=True, deploy_dir="data2")
    report4 = exporter.export_p3d(target, ["4"], plain)
    data2 = os.path.join(work, "proj", "model", "data2")
    check("options: deploy without conversion copies the file",
          written() == [("proj\\model\\data2\\hull_co.png", "")] and os.path.isfile(os.path.join(data2, "hull_co.png")) and
          report4["deploy"]["copied"] == 1, [written(), report4["deploy"]])
    report4 = exporter.export_p3d(target, ["4"], plain)
    text4 = exporter.summary(report4)
    check("options: a second export keeps the deployed file", report4["deploy"]["kept"] == 1 and
          report4["deploy"]["copied"] == 0 and "Textures -> " in text4, text4)
    with open(rvmat, "a") as stream:
        stream.write("// edited by hand\n")
    text4 = exporter.summary(exporter.export_p3d(target, ["4"], full))
    check("options: an .rvmat that is there already is kept, the faces still name it",
          ".rvmat files written: 0, already there (kept): 1" in text4 and "edited by hand" in open(rvmat).read() and
          written() == [("proj\\model\\data\\hull_co.paa", "proj\\model\\data\\hull.rvmat")], text4)
    os.remove(rvmat)
    detail = exporter.Options(tex_root=work, gen_rvmat=True, deploy=True, deploy_dir="data", rvmat_preset="Detail")
    text4 = exporter.summary(exporter.export_p3d(target, ["4"], detail))
    check("options: the summary counts the .rvmat files, the preset is the asked one",
          ".rvmat files written: 1" in text4 and "kept" not in text4.split(".rvmat files written")[1].splitlines()[0] and
          "NormalMapDetailSpecularDIMap" in open(rvmat).read(), text4)
    shutil.rmtree(work, ignore_errors=True)
    try:
        exporter.build_model(["my helpers"])
        check("a layer that is not a LOD is refused", False)
    except reader.SceneError as error:
        check("a layer that is not a LOD is refused", "my helpers" in str(error), str(error))
    out["ok"] = all((v if isinstance(v, bool) else v[0]) for v in out["checks"].values())
except Exception as error:  # noqa: BLE001
    out["ok"] = False
    out["error"] = "%s: %s" % (type(error).__name__, error)
    out["trace"] = traceback.format_exc()
with open(os.environ["ATB_OUT"], "w", encoding="utf-8") as stream:
    json.dump(out, stream, indent=1, default=str)
