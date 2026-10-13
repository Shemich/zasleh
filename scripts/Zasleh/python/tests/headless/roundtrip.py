"""Round trip in headless 3ds Max: p3d -> scene -> p3d, compared with the original by meaning"""
import copy
import json
import os
import sys
import time
import traceback

import pymxs

sys.path.insert(0, os.environ.get("ZASLEH_PKG") or os.path.join(
    str(pymxs.runtime.getDir(pymxs.runtime.Name("scripts"))), "Zasleh", "python"))

from zasleh import formats  # noqa: E402
from zasleh.formats import compare, mlod  # noqa: E402
from zasleh.formats import normals as normals_module  # noqa: E402
from zasleh import exporter, importer, parts, scene  # noqa: E402

rt = pymxs.runtime
OUT = os.environ["ZASLEH_OUT"]
report = {"files": []}
log = open(OUT + ".log", "w", encoding="utf-8")
T0 = time.perf_counter()
PARTS = parts.patterns_of(os.environ.get("ZASLEH_PARTS", ""))      # selections to split off after the import


def note(message):
    log.write("%7.2f  %s\n" % (time.perf_counter() - T0, message))
    log.flush()


def save():
    with open(OUT, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=1, default=str)


def normalized(lod):
    """The LOD as Object Builder would re-save it, minus what the importer skips on purpose"""
    out = copy.copy(lod)
    count = len(lod.points)
    keep = []
    for index, face in enumerate(lod.faces):
        points = face.points
        ok = face.n in (3, 4) and min(points) >= 0 and max(points) < count and len(set(points)) == face.n
        keep.append(ok)
    out.faces = [copy.copy(face) for face, ok in zip(lod.faces, keep) if ok]
    out.taggs = []
    for tagg in lod.taggs:
        if type(tagg) is mlod.Selection:
            tagg = mlod.Selection(tagg.name, tagg.weights, bytes(b for b, ok in zip(tagg.faces, keep) if ok))
        elif type(tagg) is mlod.UVSet:
            uvs = []
            at = 0
            for face, ok in zip(lod.faces, keep):
                n = max(0, min(face.n, 4))
                if ok:
                    uvs += tagg.uvs[at:at + n]
                at += n
            tagg = mlod.UVSet(tagg.index, uvs)
        elif type(tagg) is mlod.Mass and not formats.has_mass(lod.resolution):
            continue
        out.taggs.append(tagg)
    if not out.uvsets:
        out.taggs.append(mlod.UVSet(0, [uv for face in out.faces for uv in face.uvs]))
    normals_module.recalculate(out)
    return out


def classify(difference, src_lod, info):
    """Split a LOD's differences into expected ones (documented limits) and real ones"""
    expected, real = {}, {}
    loose = set(range(len(src_lod.points)))
    for face in src_lod.faces:
        loose.difference_update(face.points)
    for key, value in difference.items():
        if key == "note_faces_start_at_another_corner":
            expected[key] = value
        elif key == "selections_changed":
            rest = []
            for name, points, faces in value:
                partition = scene.COMPONENT.match(name) or name.lower().startswith(scene.PROXY_PREFIX)
                if partition and points == 0:
                    expected.setdefault("partition_faces_derived", 0)
                    expected["partition_faces_derived"] += 1
                else:
                    rest.append((name, points, faces))
            if rest:
                real[key] = rest[:6] + ([("...", len(rest), 0)] if len(rest) > 6 else [])
        elif key in ("points_shaded_differently", "corner_normals") and info.get("smoothing_wrong"):
            expected[key] = value
        elif key == "face_count" and info.get("mesh_faces", 0) != info.get("faces", 0) - info.get("dropped_faces", 0):
            expected["quads_split_by_max"] = value
        else:
            real[key] = value
    return expected, real


with open(os.environ["ZASLEH_FILES"], encoding="utf-8") as stream:
    paths = [line.strip() for line in stream if line.strip()]

for path in paths:
    entry = {"file": path}
    report["files"].append(entry)
    note("BEGIN " + path)
    try:
        rt.resetMaxFile(rt.Name("noPrompt"))
        src = formats.read(path)
        result = importer.import_p3d(path)
        entry["import_s"] = result["seconds"]
        if PARTS:
            started = time.perf_counter()
            entry["parts"] = sum(parts.split_scene(PARTS).values())
            entry["split_s"] = round(time.perf_counter() - started, 2)
        info_by_resolution = {}
        for lod, info in zip(src.lods, result["lods"]):
            info_by_resolution.setdefault(lod.resolution, info)
        model, exported = exporter.build_model()
        entry["export_s"] = exported["seconds"]
        data = formats.dumps(model)
        entry["bytes"] = [os.path.getsize(path), len(data)]
        again = formats.loads(data)
        expected_model = mlod.P3D()
        seen = set()
        for lod in sorted(src.lods, key=lambda l: l.resolution):
            if lod.resolution not in seen:               # the scene holds one layer per LOD name
                seen.add(lod.resolution)
                expected_model.lods.append(normalized(lod))
        entry["lods"] = len(expected_model.lods)
        entry["lod_order_same"] = [l.resolution for l in again.lods] == [l.resolution for l in expected_model.lods]
        rows = []
        for resolution, difference in compare.diff_models(expected_model, again):
            source_lod = next(l for l in src.lods if l.resolution == resolution) if any(
                l.resolution == resolution for l in src.lods) else None
            if source_lod is None or "lod" in difference:
                rows.append({"lod": formats.lod_name(resolution), "real": difference, "expected": {}})
                continue
            expected, real = classify(difference, source_lod, info_by_resolution.get(resolution, {}))
            rows.append({"lod": formats.lod_name(resolution), "real": real, "expected": expected})
        entry["differences"] = rows
        entry["ok"] = all(not row["real"] for row in rows)
    except Exception as error:  # noqa: BLE001
        entry["ok"] = False
        entry["error"] = "%s: %s" % (type(error).__name__, error)
        entry["trace"] = traceback.format_exc()
    note("END   ok=%s" % entry.get("ok"))
    save()

rt.resetMaxFile(rt.Name("noPrompt"))
report["finished"] = True
save()
note("DONE")
log.close()
