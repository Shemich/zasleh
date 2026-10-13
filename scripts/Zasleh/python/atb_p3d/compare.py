"""Compare two models by what they mean, not by their bytes"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .mlod import LOD, P3D
from .smoothing import shading_differences

__all__ = ["diff_lods", "diff_models"]


def _rotation(a: tuple, b: tuple) -> Optional[int]:
    """r such that b == a rotated left by r, or None"""
    if a == b:
        return 0
    count = len(a)
    if count != len(b):
        return None
    for r in range(1, count):
        if a[r:] + a[:r] == b:
            return r
    return None


def _named(lod: LOD) -> Dict[str, object]:
    return {s.name: s for s in lod.selections if any(s.weights) or any(s.faces)}


def diff_lods(a: LOD, b: LOD, uv_tolerance: float = 1e-6, normal_tolerance: float = 1e-3) -> Dict[str, object]:
    """What differs between two LODs"""
    out: Dict[str, object] = {}
    if a.resolution != b.resolution:
        out["resolution"] = [a.resolution, b.resolution]

    if len(a.points) != len(b.points):
        out["point_count"] = [len(a.points), len(b.points)]
        return out
    moved = sum(1 for p, q in zip(a.points, b.points) if p != q)
    if moved:
        out["points_in_another_order" if sorted(a.points) == sorted(b.points) else "positions"] = moved
        return out
    flags = sum(1 for p, q in zip(a.point_flags, b.point_flags) if p != q)
    if flags:
        out["point_flags"] = flags

    if len(a.faces) != len(b.faces):
        out["face_count"] = [len(a.faces), len(b.faces)]
        return out

    a_sets = {t.index: t.uvs for t in a.uvsets}
    b_sets = {t.index: t.uvs for t in b.uvsets}
    if set(a_sets) != set(b_sets):
        out["uv_sets"] = [sorted(a_sets), sorted(b_sets)]
    shared_sets = sorted(set(a_sets) & set(b_sets))

    wrong_faces = wrong_material = wrong_flags = wrong_normals = 0
    uv_error = 0.0
    rotations: List[int] = []
    at = 0
    a_normals, b_normals = a.normals, b.normals
    for fa, fb in zip(a.faces, b.faces):
        pa, pb = fa.points, fb.points
        count = len(pa)
        r = _rotation(pa, pb)
        rotations.append(r or 0)
        if r is None:
            wrong_faces += 1
            at += count
            continue
        if (fa.texture.lower(), fa.material.lower()) != (fb.texture.lower(), fb.material.lower()):
            wrong_material += 1
        if fa.flags != fb.flags:
            wrong_flags += 1
        ua, ub = fa.uvs, fb.uvs
        na, nb = fa.normals, fb.normals
        for j in range(count):
            k = (j + r) % count                     # corner j of b is corner k of a
            uv_error = max(uv_error, abs(ua[k][0] - ub[j][0]), abs(ua[k][1] - ub[j][1]))
            if 0 <= na[k] < len(a_normals) and 0 <= nb[j] < len(b_normals):
                va, vb = a_normals[na[k]], b_normals[nb[j]]
                if max(abs(va[0] - vb[0]), abs(va[1] - vb[1]), abs(va[2] - vb[2])) > normal_tolerance:
                    wrong_normals += 1
            else:
                wrong_normals += 1
            for set_index in shared_sets:
                sa, sb = a_sets[set_index][at + k], b_sets[set_index][at + j]
                uv_error = max(uv_error, abs(sa[0] - sb[0]), abs(sa[1] - sb[1]))
        at += count
    if wrong_faces:
        out["faces"] = wrong_faces
    if wrong_material:
        out["face_materials"] = wrong_material
    if wrong_flags:
        out["face_flags"] = wrong_flags
    if wrong_normals:
        out["corner_normals"] = wrong_normals
    if uv_error > uv_tolerance:
        out["uv_max_error"] = uv_error
    rotated = sum(1 for r in rotations if r)
    if rotated:
        out["note_faces_start_at_another_corner"] = rotated

    # shading: do the two lists of sharp edges split the faces around each point the same way?
    faces = [face.points for face in a.faces]
    sharp_a = {tuple(sorted(e)) for e in a.sharp_edges}
    sharp_b = {tuple(sorted(e)) for e in b.sharp_edges}
    if sharp_a != sharp_b:
        shaded = shading_differences(faces, sharp_a, sharp_b)
        if shaded:
            out["points_shaded_differently"] = shaded

    named_a, named_b = _named(a), _named(b)
    missing = sorted(set(named_a) - set(named_b))
    extra = sorted(set(named_b) - set(named_a))
    if missing:
        out["selections_missing"] = missing
    if extra:
        out["selections_extra"] = extra
    changed: List[Tuple[str, int, int]] = []
    for name in sorted(set(named_a) & set(named_b)):
        sa, sb = named_a[name], named_b[name]
        points = sum(1 for x, y in zip(sa.weights, sb.weights) if x != y)
        in_faces = sum(1 for x, y in zip(sa.faces, sb.faces) if bool(x) != bool(y))
        if points or in_faces:
            changed.append((name, points, in_faces))
    if changed:
        out["selections_changed"] = changed

    props_a = [(p.key, p.value) for p in a.properties]
    props_b = [(p.key, p.value) for p in b.properties]
    if props_a != props_b:
        out["properties"] = [props_a, props_b]

    mass_a = a.mass or [0.0] * len(a.points)
    mass_b = b.mass or [0.0] * len(b.points)
    heavy = sum(1 for x, y in zip(mass_a, mass_b) if abs(x - y) > 1e-6 * max(1.0, abs(x)))
    if heavy:
        out["mass"] = heavy
    return out


def diff_models(a: P3D, b: P3D) -> List[Tuple[float, Dict[str, object]]]:
    """Differences per LOD (matched by resolution, in order)"""
    out: List[Tuple[float, Dict[str, object]]] = []
    used = set()
    for lod in a.lods:
        match = next((i for i, other in enumerate(b.lods)
                      if i not in used and other.resolution == lod.resolution), None)
        if match is None:
            out.append((lod.resolution, {"lod": "missing in the second model"}))
            continue
        used.add(match)
        difference = diff_lods(lod, b.lods[match])
        if difference:
            out.append((lod.resolution, difference))
    for i, other in enumerate(b.lods):
        if i not in used:
            out.append((other.resolution, {"lod": "only in the second model"}))
    return out
