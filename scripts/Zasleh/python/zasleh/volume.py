"""Points on a grid inside a closed mesh: the cloud of a hit point LOD. No 3ds Max needed."""

from bisect import bisect_right
from typing import List, Sequence, Tuple

Point = Tuple[float, float, float]
# the test lines run a hair off the grid, so that none goes exactly through an edge or a vertex
_OFF_Y, _OFF_Z = 3.1e-7, 7.3e-7


def axis(low: float, high: float, spacing: float) -> List[float]:
    """Grid values between two bounds: the middles of as many cells of this size as fit, centred"""
    extent = high - low
    count = max(1, int(extent / spacing + 1e-9)) if spacing > 0 else 1
    start = low + (extent - (count - 1) * spacing) / 2.0
    return [start + i * spacing for i in range(count)]


def _crossings(triangles, y: float, z: float) -> List[float]:
    """Where the line through (y, z) along x goes through the triangles"""
    found = []
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in triangles:
        d = (by - ay) * (cz - az) - (bz - az) * (cy - ay)
        if d == 0.0:
            continue                                    # seen edge-on
        u = ((y - ay) * (cz - az) - (z - az) * (cy - ay)) / d
        v = ((by - ay) * (z - az) - (bz - az) * (y - ay)) / d
        if u >= 0.0 and v >= 0.0 and u + v <= 1.0:
            found.append(ax + u * (bx - ax) + v * (cx - ax))
    return found


def fill(triangles: Sequence[Tuple[Point, Point, Point]], spacing: Sequence[float]) -> Tuple[List[Point], int]:
    """(grid points inside the mesh, lines given up because the mesh is open there)"""
    corners = [corner for triangle in triangles for corner in triangle]
    if not corners:
        return [], 0
    low = [min(c[i] for c in corners) for i in range(3)]
    high = [max(c[i] for c in corners) for i in range(3)]
    size = max(high[i] - low[i] for i in range(3)) or 1.0
    xs, ys, zs = (axis(low[i], high[i], spacing[i]) for i in range(3))
    points: List[Point] = []
    skipped = 0
    margin = size * 1e-6
    for y in ys:
        slab = [t for t in triangles if min(t[0][1], t[1][1], t[2][1]) - margin <= y <= max(t[0][1], t[1][1], t[2][1]) + margin]
        for z in zs:
            crossings = sorted(_crossings(slab, y + size * _OFF_Y, z + size * _OFF_Z))
            if len(crossings) % 2:
                skipped += 1                            # in on one side and never out: a hole in the mesh
                continue
            points += [(x, y, z) for x in xs if bisect_right(crossings, x) % 2]
    return points, skipped
