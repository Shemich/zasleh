"""Texture previews on import, in headless 3ds Max"""
import json
import os
import shutil
import struct
import sys
import traceback

import pymxs

rt = pymxs.runtime
out = {"checks": {}}


def check(name, condition, detail=None):
    out["checks"][name] = bool(condition) if detail is None else [bool(condition), detail]


try:
    sys.path.insert(0, os.path.join(str(rt.getDir(rt.Name("scripts"))), "Zasleh", "python"))
    from zasleh import formats
    from zasleh.formats import LOD, P3D, Face
    from zasleh import exporter, importer
    from tests import paa_samples

    work = os.path.join(os.environ["ZASLEH_TMP"], "zasleh_preview_test")
    shutil.rmtree(work, ignore_errors=True)
    cache = os.path.join(work, "cache")
    os.makedirs(os.path.join(work, "proj", "data"))
    with open(os.path.join(work, "proj", "data", "hull_co.paa"), "wb") as stream:
        stream.write(paa_samples.red_blue_paa())
    with open(os.path.join(work, "proj", "data", "broken_co.paa"), "wb") as stream:
        stream.write(b"\x01\xff" + b"junk")

    HULL, COLOUR, MISSING, BROKEN = ("proj\\data\\hull_co.paa", "#(argb,8,8,3)color(1,0,0.5,1.0,co)",
                                     "proj\\data\\missing_co.paa", "proj\\data\\broken_co.paa")
    model = P3D()
    lod = LOD(1.0)
    for index, texture in enumerate((HULL, COLOUR, MISSING, BROKEN)):
        base = len(lod.points)
        x = 2.0 * index
        lod.points += [(x, 0.0, 0.0), (x + 1.0, 0.0, 0.0), (x + 1.0, 0.0, 1.0)]
        lod.faces.append(Face.new((base, base + 1, base + 2), (0, 0, 0), ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),
                                  texture=texture, material=""))
    lod.point_flags = [0] * len(lod.points)
    lod.normals = [(0.0, 1.0, 0.0)]
    model.lods.append(lod)
    path = os.path.join(work, "model.p3d")
    formats.write(model, path)

    def imported(**options):
        rt.resetMaxFile(rt.Name("noPrompt"))
        report = importer.import_p3d(path, tex_root=work, preview_dir=cache, preview_size=4, **options)
        node = [n for n in rt.objects if rt.classOf(n) == rt.Editable_Poly][0]
        found = {}
        for material in node.material.materialList:
            attributes = rt.custAttributes.get(material, rt.zaslehArmaMaterialCA)
            bitmap = material.base_color_map
            colour = material.base_color
            found[str(attributes.texture)] = (str(bitmap.filename) if bitmap is not None else None,
                                              (round(colour.r), round(colour.g), round(colour.b)))
        return report, found

    report, found = imported(preview=True)
    expected = os.path.join(cache, "proj", "data", "hull_co.4.png")
    png = open(expected, "rb").read() if os.path.isfile(expected) else b""
    check("a .paa gets a preview: the mipmap that fits the size, as a .png in the cache",
          found[HULL][0] == expected and png[:8] == b"\x89PNG\r\n\x1a\n" and
          struct.unpack_from(">II", png, 16) == (4, 4) and report["previews"] == 1, [found[HULL], report.get("previews")])
    check("a procedural colour becomes the colour of the material", found[COLOUR] == (None, (255, 0, 128)), found[COLOUR])
    check("a texture that is not there gets no bitmap", found[MISSING][0] is None)
    check("a .paa that cannot be read gets no bitmap, and the report says why",
          found[BROKEN][0] is None and any("broken_co.paa" in w for w in report["warnings"]), report["warnings"])
    textures = sorted({face.texture for face in exporter.build_model()[0].lods[0].faces})
    check("the export writes the Arma paths, not the previews", textures == sorted((HULL, COLOUR, MISSING, BROKEN)), textures)
    text = importer.summary(report)
    check("the import summary names the cache", "1 texture preview(s) made in " + cache in text, text)

    report, found = imported(preview=True)
    check("a second import uses the picture that is there", report["previews"] == 0 and found[HULL][0] == expected)
    report, found = imported(preview=False)
    check("previews can be turned off", found[HULL][0] is None and report["previews"] == 0, found[HULL])
    source = os.path.join(work, "proj", "data", "hull_co.png")
    formats.paa.write_png(source, 1, 1, b"\x10\x20\x30")
    report, found = imported(preview=True)
    check("a source picture next to the .paa is preferred", found[HULL][0] == source, found[HULL])
    # a texture of the game: not under the project's root, found under the game data folder
    from zasleh import settings
    game = os.path.join(work, "game")
    os.makedirs(os.path.join(game, "proj", "data"))
    os.replace(os.path.join(work, "proj", "data", "hull_co.paa"), os.path.join(game, "proj", "data", "hull_co.paa"))
    os.remove(source)
    kept = settings.get("gameRoot")
    settings.put("gameRoot", game)
    try:
        report, found = imported(preview=True)
    finally:
        settings.put("gameRoot", kept)
    check("a texture found under the game data folder gets its preview", found[HULL][0] == expected and report["previews"] == 0,
          [found[HULL], report["previews"]])
    shutil.rmtree(work, ignore_errors=True)
    out["ok"] = all((v if isinstance(v, bool) else v[0]) for v in out["checks"].values())
except Exception as error:  # noqa: BLE001
    out["ok"] = False
    out["error"] = "%s: %s" % (type(error).__name__, error)
    out["trace"] = traceback.format_exc()
with open(os.environ["ZASLEH_OUT"], "w", encoding="utf-8") as stream:
    json.dump(out, stream, indent=1, default=str)
