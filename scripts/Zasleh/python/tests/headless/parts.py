"""Selections split off into objects (atb_max/parts.py), in headless 3ds Max: the scene, and the p3d it gives back"""
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
    sys.path.insert(0, os.path.join(str(rt.getDir(rt.Name("scripts"))), "Zasleh", "python"))
    import atb_p3d
    from atb_p3d import LOD, Face, P3D, Selection, compare
    from atb_max import exporter, groups, importer, parts
    from atb_max import registry as reg

    check("patterns: typed ones after the one for proxies",
          parts.patterns_of(" wheel_*; otocvez ,", True) == ["proxy:*", "wheel_*", "otocvez"] and parts.patterns_of("") == [])
    check("matching: by pattern, any case, each name once, in the order of the patterns",
          parts.matching(["Wheel_1", "hull", "proxy:a.001", "wheel_2"], ["proxy:*", "WHEEL_?", "wheel_1"]) ==
          ["proxy:a.001", "Wheel_1", "wheel_2"])

    # a strip of four quads, a proxy triangle apart from it; "left" and "middle" share a quad, "soft" has weights
    work = os.path.join(os.environ["ATB_TMP"], "atb_parts_test")
    os.makedirs(work, exist_ok=True)
    lod = LOD(1.0)
    lod.points = [(float(x), 0.0, float(z)) for x in range(5) for z in (0, 1)] + [(9.0, 0.0, 0.0), (9.0, 1.0, 0.0), (9.0, 0.0, 1.0)]
    lod.point_flags = [0] * len(lod.points)
    lod.normals = [(0.0, 1.0, 0.0)]
    for x in range(4):
        a = 2 * x
        lod.faces.append(Face.new((a, a + 1, a + 3, a + 2), (0,) * 4, ((0.0, 0.0),) * 4, texture="t.paa", material=""))
    lod.faces.append(Face.new((10, 11, 12), (0,) * 3, ((0.0, 0.0),) * 3, texture="", material=""))

    def selection(name, faces, weight=1):
        points = sorted({p for f in faces for p in lod.faces[f].points})
        weights = bytearray(len(lod.points))
        for point in points:
            weights[point] = weight
        flags = bytearray(len(lod.faces))
        for face in faces:
            flags[face] = 1
        return Selection(name, bytes(weights), bytes(flags))

    lod.taggs += [selection("left", [0, 1]), selection("middle", [1, 2]), selection("soft", [3], 128),
                  selection("proxy:\\a3\\x\\driver.001", [4]), selection("all", [0, 1, 2, 3, 4])]
    lod.taggs.append(atb_p3d.SharpEdges([]))
    source = os.path.join(work, "strip.p3d")
    model = P3D()
    model.lods.append(lod)
    atb_p3d.write(model, source)

    def written():
        built, _report = exporter.build_model()
        return atb_p3d.loads(atb_p3d.dumps(built))

    def round_trip(patterns):
        """Import, write, split, write again: what the split changed in the p3d"""
        rt.resetMaxFile(rt.Name("noPrompt"))
        report = importer.import_p3d(source)
        whole = written()
        made = parts.split_scene(patterns, [info["layer"] for info in report["lods"]])
        names = sorted(str(node.name) for node in rt.objects)
        again = written()
        return made, names, compare.diff_models(whole, again), again

    made, names, differences, again = round_trip(["proxy:*"])
    check("a proxy becomes an object named after it", made == {"1": 1} and names == ["proxy:\\a3\\x\\driver.001", "strip_1"],
          [made, names])
    proxy = rt.getNodeByName("proxy:\\a3\\x\\driver.001")
    registry = reg.Registry.load()
    hull = rt.getNodeByName("strip_1")
    check("the part is in the LOD's layer, with its face, its selections and the material",
          proxy is not None and str(proxy.layer.name) == "1" and int(rt.polyop.getNumFaces(proxy)) == 1 and
          groups.groups_on(proxy, registry) == ["all", "proxy:\\a3\\x\\driver.001"] and proxy.material == hull.material and
          int(rt.polyop.getNumFaces(hull)) == 4 and "proxy:\\a3\\x\\driver.001" not in groups.groups_on(hull, registry),
          [groups.groups_on(proxy, registry) if proxy is not None else None, groups.groups_on(hull, registry)])
    check("the p3d written from the split scene is the one that was read", not differences and
          len(again.lods[0].points) == len(lod.points), differences)

    made, names, differences, again = round_trip(["left", "middle", "soft", "nothing_like_it"])
    check("parts that touch: a face goes with the first selection that has it",
          made == {"1": 3} and names == ["left", "middle", "soft", "strip_1"] and
          [int(rt.polyop.getNumFaces(rt.getNodeByName(n))) for n in ("left", "middle", "soft", "strip_1")] == [2, 1, 1, 1],
          [made, names])
    check("points shared by parts are one point each again in the p3d", not differences and
          len(again.lods[0].points) == len(lod.points) and
          [s.name for s in again.lods[0].selections] == [s.name for s in lod.selections],
          [differences, len(again.lods[0].points)])
    registry = reg.Registry.load()
    check("a second split of the same scene changes nothing",
          parts.split_scene(["left", "middle", "soft"]) == {} and len(list(rt.objects)) == 4)

    made, names, differences, again = round_trip(["all"])
    check("a selection that is the whole object is left alone", made == {} and names == ["strip_1"] and not differences, [made, names])
    made, names, differences, again = round_trip(["left", "middle", "soft", "proxy:*"])
    check("when every face goes into a part, the emptied object is removed", made == {"1": 4} and
          names == ["left", "middle", "proxy:\\a3\\x\\driver.001", "soft"] and not differences, [made, names, differences])

    # a skeleton laid out in the scene: bone objects, linked like the bones
    from atb_max import skeleton
    rt.resetMaxFile(rt.Name("noPrompt"))
    importer.import_p3d(source)
    whole = written()
    made, links = parts.by_bones([("left", ""), ("middle", "left"), ("soft", "middle"), ("no_such", "soft")])
    node = {str(n.name): n for n in rt.objects}
    check("bones become objects, the deepest first, linked like the skeleton",
          made == {"1": 3} and links == 2 and str(node["soft"].parent.name) == "middle" and
          str(node["middle"].parent.name) == "left" and node["left"].parent is None and
          [int(rt.polyop.getNumFaces(node[n])) for n in ("left", "middle", "soft")] == [1, 2, 1],
          [made, links, sorted(node)])
    check("the links read back as the skeleton, the p3d is unchanged",
          sorted(skeleton.bones_from_links()) == [("left", ""), ("middle", "left"), ("soft", "middle")] and
          not compare.diff_models(whole, written()), skeleton.bones_from_links())
    check("laying it out again changes nothing", parts.by_bones([("left", ""), ("middle", "left"), ("soft", "middle")]) == ({}, 0))

    sample = os.environ.get("ATB_SAMPLE", "")
    if sample and os.path.isfile(sample):
        rt.resetMaxFile(rt.Name("noPrompt"))
        report = importer.import_p3d(sample)
        whole = written()
        made = parts.split_scene(["proxy:*"])
        differences = compare.diff_models(whole, written())
        out["sample_parts"] = made
        check("a real model: split by proxies, the export is the same as without the split",
              sum(made.values()) > 0 and not differences, [made, differences[:3]])
    out["ok"] = all((v if isinstance(v, bool) else v[0]) for v in out["checks"].values())
except Exception as error:  # noqa: BLE001
    out["ok"] = False
    out["error"] = "%s: %s" % (type(error).__name__, error)
    out["trace"] = traceback.format_exc()
with open(os.environ["ATB_OUT"], "w", encoding="utf-8") as stream:
    json.dump(out, stream, indent=1, default=str)
