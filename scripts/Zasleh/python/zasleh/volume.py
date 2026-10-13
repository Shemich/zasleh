"""Points on a grid inside closed meshes: the cloud of a hit point LOD. No 3ds Max needed."""

from bisect import bisect_right
from typing import Dict, List, Sequence, Tuple

Point = Tuple[float, float, float]
Triangle = Tuple[Point, Point, Point]
# the test lines run a hair off the grid, so that none goes exactly through an edge or a vertex
_OFF_Y, _OFF_Z = 3.1e-7, 7.3e-7


def axis(low: float, high: float, spacing: float) -> List[float]:
    """Grid values between two bounds: the middles of as many cells of this size as fit, centred"""
    extent = high - low
    count = max(1, int(extent / spacing + 1e-9)) if spacing > 0 else 1
    start = low + (extent - (count - 1) * spacing) / 2.0
    return [start + i * spacing for i in range(count)]


def _crossings(triangles, y: float, z: float) -> List[Tuple[float, int]]:
    """Where the line through (y, z) along x goes through the triangles: (x, +1 going in / -1 coming out)"""
    found = []
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in triangles:
        d = (by - ay) * (cz - az) - (bz - az) * (cy - ay)      # x of the normal: its sign tells in from out
        if d == 0.0:
            continue                                            # seen edge-on
        u = ((y - ay) * (cz - az) - (z - az) * (cy - ay)) / d
        v = ((by - ay) * (z - az) - (bz - az) * (y - ay)) / d
        if u >= 0.0 and v >= 0.0 and u + v <= 1.0:
            found.append((ax + u * (bx - ax) + v * (cx - ax), -1 if d > 0.0 else 1))
    return found


def _depths(crossings: List[Tuple[float, int]]) -> Tuple[List[float], List[int]]:
    """Sorted x of the crossings and, after each, how many shells one is inside of"""
    crossings.sort()
    places, depths, depth = [], [], 0
    for x, step in crossings:
        depth += step
        places.append(x)
        depths.append(depth)
    return places, depths


def _bounds(triangles) -> Tuple[List[float], List[float]]:
    corners = [corner for triangle in triangles for corner in triangle]
    return [min(c[i] for c in corners) for i in range(3)], [max(c[i] for c in corners) for i in range(3)]


def fill(triangles: Sequence[Triangle], spacing: Sequence[float]) -> Tuple[List[Point], int]:
    """(grid points inside the mesh, lines given up because the mesh is open there).
    Shells may overlap: a point inside any of them is inside."""
    if not triangles:
        return [], 0
    low, high = _bounds(triangles)
    size = max(high[i] - low[i] for i in range(3)) or 1.0
    xs, ys, zs = (axis(low[i], high[i], spacing[i]) for i in range(3))
    points: List[Point] = []
    skipped = 0
    margin = size * 1e-6
    for y in ys:
        slab = [t for t in triangles if min(t[0][1], t[1][1], t[2][1]) - margin <= y <= max(t[0][1], t[1][1], t[2][1]) + margin]
        for z in zs:
            places, depths = _depths(_crossings(slab, y + size * _OFF_Y, z + size * _OFF_Z))
            if depths and depths[-1] != 0:
                skipped += 1                            # in on one side and never out: a hole in the mesh
                continue
            for x in xs:
                at = bisect_right(places, x)
                if at and depths[at - 1] != 0:
                    points.append((x, y, z))
    return points, skipped


def contains(triangles: Sequence[Triangle], point: Point) -> bool:
    low, high = _bounds(triangles)
    if any(not low[i] <= point[i] <= high[i] for i in range(3)):
        return False
    size = max(high[i] - low[i] for i in range(3)) or 1.0
    places, depths = _depths(_crossings(triangles, point[1] + size * _OFF_Y, point[2] + size * _OFF_Z))
    at = bisect_right(places, point[0])
    return bool(at) and depths[at - 1] != 0 and depths[-1] == 0


# -- a mesh made of several closed pieces: each one on a grid of its own

def elements(faces: Sequence[Sequence[int]]) -> List[List[int]]:
    """Faces grouped into the pieces that share no vertex"""
    parent: Dict[int, int] = {}

    def find(vertex: int) -> int:
        while parent.setdefault(vertex, vertex) != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    for face in faces:
        first = find(face[0])
        for vertex in face[1:]:
            parent[find(vertex)] = first
    groups: Dict[int, List[int]] = {}
    for index, face in enumerate(faces):
        groups.setdefault(find(face[0]), []).append(index)
    return list(groups.values())


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    length = _dot(a, a) ** 0.5
    return (a[0] / length, a[1] / length, a[2] / length) if length > 0.0 else (0.0, 0.0, 0.0)


def frame(triangles: Sequence[Triangle]) -> Tuple[Point, Point, Point]:
    """Axes of a piece, taken from its biggest flat sides: a box gives its own, however it is turned.
    They come in the order x, y, z of the world axes they are closest to."""
    areas: Dict[tuple, float] = {}
    for a, b, c in triangles:
        normal = _cross([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
        area = _dot(normal, normal) ** 0.5
        if area <= 0.0:
            continue
        normal = _unit(normal)
        lead = max(range(3), key=lambda i: abs(normal[i]))
        if normal[lead] < 0.0:
            normal = tuple(-value for value in normal)          # a side and the one across are one direction
        key = tuple(round(value, 2) for value in normal)
        areas[key] = areas.get(key, 0.0) + area
    ranked = sorted(areas.items(), key=lambda item: -item[1])
    first = _unit(ranked[0][0]) if ranked else (1.0, 0.0, 0.0)
    second = None
    for normal, _area in ranked[1:]:
        if abs(_dot(first, normal)) < 0.3:                      # the biggest side that stands across the first
            second = normal
            break
    if second is None:
        second = (0.0, 0.0, 1.0) if abs(first[2]) < 0.9 else (1.0, 0.0, 0.0)
    second = _unit([second[i] - _dot(first, second) * first[i] for i in range(3)])
    axes = [first, second, _unit(_cross(first, second))]
    ordered: List[Point] = [(0.0, 0.0, 0.0)] * 3
    left = list(range(3))
    for world in sorted(range(3), key=lambda i: -max(abs(a[i]) for a in axes)):
        best = max(left, key=lambda k: abs(axes[k][world]))
        left.remove(best)
        ordered[world] = axes[best] if axes[best][world] >= 0.0 else tuple(-value for value in axes[best])
    return ordered[0], ordered[1], ordered[2]


def fill_elements(verts: Sequence[Point], faces: Sequence[Sequence[int]],
                  spacing: Sequence[float]) -> Tuple[List[Point], int, int]:
    """Every closed piece of the mesh filled on a grid along its own axes.
    (points, lines given up at holes, pieces). Where pieces overlap, the later one leaves that room to the earlier."""
    points: List[Point] = []
    skipped = 0
    done: List[List[Triangle]] = []
    pieces = sorted(elements(faces), key=lambda piece: min(piece))
    for piece in pieces:
        world = [tuple(verts[index] for index in faces[face]) for face in piece]
        x_axis, y_axis, z_axis = frame(world)
        local = [tuple((_dot(p, x_axis), _dot(p, y_axis), _dot(p, z_axis)) for p in triangle) for triangle in world]
        inside, holes = fill(local, spacing)
        skipped += holes
        for x, y, z in inside:
            point = tuple(x * x_axis[i] + y * y_axis[i] + z * z_axis[i] for i in range(3))
            if not any(contains(earlier, point) for earlier in done):
                points.append(point)
        done.append(world)
    return points, skipped, len(pieces)
