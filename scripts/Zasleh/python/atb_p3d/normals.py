"""Normals as Object Builder computes them when it saves a model"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from .flags import (FACE_BOTHSIDESLIGHT, FACE_FLATLIGHT, FACE_LIGHT_MASK, FACE_REVERSELIGHT, FACE_SKYLIGHT,
                    POINT_SPECIAL_ANGLENORMAL, POINT_SPECIAL_LOCKNORMAL)
from .mlod import LOD

__all__ = ["recalculate", "compute"]

Vec3 = Tuple[float, float, float]
_SPECIAL = (FACE_BOTHSIDESLIGHT, FACE_SKYLIGHT, FACE_FLATLIGHT)


def _normalized(x: float, y: float, z: float) -> List[float]:
    length = math.sqrt(x * x + y * y + z * z)
    if length > 0.0:
        return [x / length, y / length, z / length]
    return [0.0, 0.0, 0.0]


def compute(points: Sequence[Vec3], point_flags: Sequence[int], faces: Sequence[Sequence[int]],
            face_flags: Sequence[int], sharp: Sequence[Tuple[int, int]],
            locked: Dict[int, Vec3]) -> Tuple[List[Vec3], List[List[int]]]:
    """(normals, normal index of every face corner) for the given geometry"""
    face_count = len(faces)
    light = [flags & FACE_LIGHT_MASK for flags in face_flags]
    special = [value in _SPECIAL for value in light]
    sharp_set = {(a, b) if a < b else (b, a) for a, b in sharp}

    # faces around each point (only those shaded the ordinary way)
    at_point: Dict[int, List[int]] = {}
    for index, corners in enumerate(faces):
        if not special[index]:
            for point in corners:
                users = at_point.setdefault(point, [])
                if not users or users[-1] != index:
                    users.append(index)

    # neighbours: faces sharing an edge that isn't sharp, running along it in opposite directions
    graph: List[List[int]] = [[] for _ in range(face_count)]
    for index, corners in enumerate(faces):
        count = len(corners)
        for j in range(count):
            point = corners[j]
            following = corners[j + 1 if j + 1 < count else 0]
            edge = (point, following) if point < following else (following, point)
            if edge in sharp_set:
                continue
            for other in at_point.get(point, ()):
                if other != index:
                    theirs = faces[other]
                    if theirs[theirs.index(point) - 1] == following and other not in graph[index]:
                        graph[index].append(other)

    normals: List[List[float]] = []
    indices: List[List[int]] = [[0] * len(corners) for corners in faces]
    visited = set()
    reserved: Dict[int, int] = {}
    for index, corners in enumerate(faces):
        count = len(corners)
        if count < 3 or (count == 3 and len(set(corners)) != 3):
            continue                                    # degenerate: O2 leaves its corners on normal 0
        kind = light[index]
        if kind == FACE_BOTHSIDESLIGHT:
            for j in range(count):
                before, here, after = points[corners[j - 1]], points[corners[j]], points[corners[(j + 1) % count]]
                indices[index][j] = len(normals)
                normals.append([(before[k] + after[k]) * 0.5 - here[k] for k in range(3)])
        elif kind == FACE_SKYLIGHT:
            for j in range(count):
                indices[index][j] = len(normals)
                normals.append(_normalized(*points[corners[j]]))
        elif kind == FACE_FLATLIGHT:
            x = y = z = 0.0
            for j in range(count):
                p0, p1, p2 = points[corners[j - 1]], points[corners[j]], points[corners[(j + 1) % count]]
                ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
                bx, by, bz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
                x += ay * bz - az * by
                y += az * bx - ax * bz
                z += ax * by - ay * bx
            indices[index] = [len(normals)] * count
            normals.append(_normalized(x, y, z))
        else:
            for j, point in enumerate(corners):
                if point_flags[point] & POINT_SPECIAL_LOCKNORMAL:
                    slot = reserved.get(point)
                    if slot is None:
                        slot = reserved[point] = len(normals)
                        normals.append([0.0, 0.0, 0.0])
                    indices[index][j] = slot
                elif (index, point) not in visited:
                    # walk the fan of faces around this point; all of it shares the new normal
                    new = len(normals)
                    visited.add((index, point))
                    stack = [index]
                    while stack:
                        for other in graph[stack.pop()]:
                            theirs = faces[other]
                            if point in theirs:
                                if (other, point) not in visited:
                                    visited.add((other, point))
                                    stack.append(other)
                                indices[other][theirs.index(point)] = new
                    indices[index][j] = new
                    normals.append([0.0, 0.0, 0.0])

    for index, corners in enumerate(faces):
        if special[index] or not normals:
            continue
        count = len(corners)
        reverse = light[index] == FACE_REVERSELIGHT
        alone = -1
        for j in range(count):
            point = corners[j]
            here, before, after = points[point], points[corners[j - 1]], points[corners[(j + 1) % count]]
            ax, ay, az = before[0] - here[0], before[1] - here[1], before[2] - here[2]
            bx, by, bz = after[0] - here[0], after[1] - here[1], after[2] - here[2]
            x, y, z = by * az - bz * ay, bz * ax - bx * az, bx * ay - by * ax        # after x before
            flags = point_flags[point]
            if flags & POINT_SPECIAL_ANGLENORMAL:
                lengths = math.sqrt((ax * ax + ay * ay + az * az) * (bx * bx + by * by + bz * bz))
                cosine = (ax * bx + ay * by + az * bz) / lengths if lengths > 0.0 else 1.0
                angle = math.acos(max(-1.0, min(1.0, cosine)))
                x, y, z = (value * angle for value in _normalized(x, y, z))
            if reverse:
                x, y, z = -x, -y, -z
            slot = indices[index][j]
            if flags & POINT_SPECIAL_LOCKNORMAL:
                normals[slot] = list(locked.get(point, (0.0, 0.0, 0.0)))
                continue
            normal = normals[slot]
            sx, sy, sz = normal[0] + x, normal[1] + y, normal[2] + z
            if sx * sx + sy * sy + sz * sz < 1e-12 and (normal[0] or normal[1] or normal[2]):
                # this face would cancel the normal out (the back side of a face in the same fan)
                if alone == -1:
                    alone = len(normals)
                    normals.append([x, y, z])
                indices[index][j] = alone
            else:
                normal[0], normal[1], normal[2] = sx, sy, sz
    return [tuple(_normalized(*normal)) for normal in normals], indices


def recalculate(lod: LOD, locked: Optional[Dict[int, Vec3]] = None, compute_with=None) -> None:
    """Replace the LOD's normals (and every face's normal indices) with freshly computed ones"""
    faces = [face.points for face in lod.faces]
    if locked is None:
        old = lod.normals
        locked = {}
        for face, corners in zip(lod.faces, faces):
            for j, point in enumerate(corners):
                if lod.point_flags[point] & POINT_SPECIAL_LOCKNORMAL:
                    index = face.normals[j]
                    locked[point] = old[index] if 0 <= index < len(old) else (0.0, 0.0, 0.0)
    normals, indices = (compute_with or compute)(lod.points, lod.point_flags, faces, [face.flags for face in lod.faces],
                                                 lod.sharp_edges, locked)
    if lod.faces and not normals:
        normals = [(0.0, 0.0, 0.0)]
    lod.normals = normals
    for face, corner_normals in zip(lod.faces, indices):
        values = list(face.v)
        for j, normal in enumerate(corner_normals):
            values[4 * j + 1] = normal
        face.v = tuple(values)
