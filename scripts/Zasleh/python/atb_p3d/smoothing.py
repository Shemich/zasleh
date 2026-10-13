"""Sharp edges <-> smoothing groups"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Set, Tuple

__all__ = ["to_smoothing_groups", "sharp_edges", "sharp_edges_from_normals", "interior_edges",
           "fans", "shading_differences"]

Edge = Tuple[int, int]
MAX_BITS = 32


def _edge(a: int, b: int) -> Edge:
    return (a, b) if a < b else (b, a)


def _directed(faces: Sequence[Sequence[int]]) -> Dict[Edge, List[int]]:
    """(from, to) -> faces that run along the edge in that direction"""
    table: Dict[Edge, List[int]] = {}
    for index, points in enumerate(faces):
        count = len(points)
        for i in range(count):
            a, b = points[i], points[(i + 1) % count]
            if a != b:
                table.setdefault((a, b), []).append(index)
    return table


def _facing_pairs(faces: Sequence[Sequence[int]]):
    """Every pair of faces that meet on an edge the way neighbours on a surface do: yields (edge"""
    table = _directed(faces)
    for (a, b), forward in table.items():
        if a < b:
            backward = table.get((b, a))
            if backward:
                yield (a, b), forward, backward


def interior_edges(faces: Sequence[Sequence[int]]) -> Set[Edge]:
    """Edges where two faces meet as neighbours - the only ones where 'sharp' means anything"""
    return {edge for edge, _forward, _backward in _facing_pairs(faces)}


def sharp_edges(faces: Sequence[Sequence[int]], groups: Sequence[int]) -> Set[Edge]:
    """Edges across which two neighbouring faces share no smoothing group bit"""
    out = set()
    for edge, forward, backward in _facing_pairs(faces):
        if any(not groups[f] & groups[b] for f in forward for b in backward if f != b):
            out.add(edge)
    return out


def sharp_edges_from_normals(faces: Sequence[Sequence[int]],
                             normals: Sequence[Sequence[int]]) -> Set[Edge]:
    """Sharp edges implied by normal indices: an edge is sharp unless two neighbouring faces use the"""
    out = set()
    for edge, forward, backward in _facing_pairs(faces):
        a, b = edge
        smooth = False
        for f in forward:
            ff, nf = faces[f], normals[f]
            at_f = (nf[ff.index(a)], nf[ff.index(b)])
            for g in backward:
                if g != f:
                    fg, ng = faces[g], normals[g]
                    if (ng[fg.index(a)], ng[fg.index(b)]) == at_f:
                        smooth = True
        if not smooth:
            out.add(edge)
    return out


class _Corners:
    """Union-find over face corners"""

    def __init__(self, faces: Sequence[Sequence[int]]):
        self.faces = faces
        self.offset = [0]
        for points in faces:
            self.offset.append(self.offset[-1] + len(points))
        self.parent = list(range(self.offset[-1]))

    def find(self, corner: int) -> int:
        parent = self.parent
        root = corner
        while parent[root] != root:
            root = parent[root]
        while parent[corner] != root:
            parent[corner], corner = root, parent[corner]
        return root

    def join(self, one: int, other: int) -> None:
        """Faces `one` and `other` shade together: join their corners at every point they share"""
        mine, theirs = self.faces[one], self.faces[other]
        for point in set(mine) & set(theirs):
            a = self.find(self.offset[one] + mine.index(point))
            b = self.find(self.offset[other] + theirs.index(point))
            if a != b:
                self.parent[b] = a

    def of_face(self, index: int) -> List[int]:
        return [self.find(self.offset[index] + i) for i in range(len(self.faces[index]))]


def _smooth_neighbours(faces: Sequence[Sequence[int]], is_smooth) -> Tuple[List[List[int]], _Corners]:
    """Faces that shade together across an edge, and the fans that follow from it"""
    neighbours: List[List[int]] = [[] for _ in faces]
    corners = _Corners(faces)
    for edge, forward, backward in _facing_pairs(faces):
        for f in forward:
            for g in backward:
                if f != g and is_smooth(edge, f, g):
                    if g not in neighbours[f]:
                        neighbours[f].append(g)
                        neighbours[g].append(f)
                    corners.join(f, g)
    return neighbours, corners


def fans(faces: Sequence[Sequence[int]], sharp: Iterable[Edge]) -> Dict[int, List[List[int]]]:
    """For every point, its faces grouped the way Object Builder gives them normals"""
    sharp_set = {_edge(a, b) for a, b in sharp}
    _neighbours, corners = _smooth_neighbours(faces, lambda edge, f, g: edge not in sharp_set)
    grouped: Dict[int, Dict[int, List[int]]] = {}
    for index, points in enumerate(faces):
        for point, fan in zip(points, corners.of_face(index)):
            grouped.setdefault(point, {}).setdefault(fan, []).append(index)
    return {point: sorted(sorted(set(fan)) for fan in by_fan.values()) for point, by_fan in grouped.items()}


def shading_differences(faces: Sequence[Sequence[int]], sharp_a: Iterable[Edge], sharp_b: Iterable[Edge]) -> int:
    """Number of points that two lists of sharp edges shade differently"""
    one, other = fans(faces, sharp_a), fans(faces, sharp_b)
    return sum(1 for point, grouping in one.items() if other[point] != grouping)


def to_smoothing_groups(faces: Sequence[Sequence[int]], sharp: Iterable[Edge]) -> Tuple[List[int], int]:
    """Smoothing group mask per face for the given sharp edges"""
    face_count = len(faces)
    sharp_set = {_edge(a, b) for a, b in sharp}
    table = _directed(faces)
    corners = _Corners(faces)
    neighbours: List[List[int]] = [[] for _ in range(face_count)]
    pairs: List[Tuple[int, int]] = []
    seen = set()
    for (a, b), forward in table.items():
        if a < b and (a, b) not in sharp_set:
            backward = table.get((b, a))
            if backward:
                for f in forward:
                    for g in backward:
                        if f != g:
                            pair = (f, g) if f < g else (g, f)
                            if pair not in seen:
                                seen.add(pair)
                                pairs.append(pair)
                                neighbours[f].append(g)
                                neighbours[g].append(f)
                                corners.join(f, g)
    del seen, table
    groups = [0] * face_count
    if not pairs:
        return groups, 0
    fan_of = [corners.of_face(index) for index in range(face_count)]

    # 1. regions
    region = [-1] * face_count
    region_fans: List[Dict[int, int]] = []             # per region: point -> the fan it holds there
    region_faces: List[List[int]] = []
    for seed in range(face_count):
        if region[seed] != -1 or not neighbours[seed]:
            continue                                    # no smooth neighbour: group 0, faceted
        current = len(region_fans)
        held: Dict[int, int] = dict(zip(faces[seed], fan_of[seed]))
        members = [seed]
        region[seed] = current
        stack = [seed]
        while stack:
            for candidate in neighbours[stack.pop()]:
                if region[candidate] != -1:
                    continue
                points, face_fans = faces[candidate], fan_of[candidate]
                for point, fan in zip(points, face_fans):
                    if held.get(point, fan) != fan:
                        break
                else:
                    region[candidate] = current
                    members.append(candidate)
                    stack.append(candidate)
                    for point, fan in zip(points, face_fans):
                        held[point] = fan
        region_fans.append(held)
        region_faces.append(members)

    # 2. regions into bits
    bit_fans: List[Dict[int, int]] = []                # per bit: point -> fan
    waiting = sorted(range(len(region_fans)), key=lambda r: -len(region_faces[r]))
    while waiting and len(bit_fans) < MAX_BITS:
        mask = 1 << len(bit_fans)
        fan_at: Dict[int, int] = {}
        left = []
        for index in waiting:
            held = region_fans[index]
            get = fan_at.get
            for point, fan in held.items():
                if get(point, fan) != fan:
                    left.append(index)
                    break
            else:
                fan_at.update(held)
                for face in region_faces[index]:
                    groups[face] |= mask
        bit_fans.append(fan_at)
        waiting = left
    del region_fans

    # 3. smooth pairs that don't share a bit yet
    def fits(face: int, fan_at: Dict[int, int]) -> bool:
        for point, fan in zip(faces[face], fan_of[face]):
            if fan_at.get(point, fan) != fan:
                return False
        return True

    def add(face: int, bit: int) -> None:
        groups[face] |= 1 << bit
        fan_at = bit_fans[bit]
        for point, fan in zip(faces[face], fan_of[face]):
            fan_at[point] = fan

    open_pairs = [pair for pair in pairs if not groups[pair[0]] & groups[pair[1]]]
    unsolved = 0
    for f, g in open_pairs:
        if groups[f] & groups[g]:
            continue                                    # an earlier pair already brought them together
        done = False
        for bit, fan_at in enumerate(bit_fans):
            mask = 1 << bit
            in_f, in_g = groups[f] & mask, groups[g] & mask
            if (in_f or fits(f, fan_at)) and (in_g or fits(g, fan_at)):
                if not in_f:
                    add(f, bit)
                if not in_g:
                    add(g, bit)
                done = True
                break
        if not done:
            if len(bit_fans) < MAX_BITS:
                bit_fans.append({})
                add(f, len(bit_fans) - 1)
                add(g, len(bit_fans) - 1)
            else:
                unsolved += 1
    if not unsolved:
        return groups, 0
    return groups, shading_differences(faces, sharp_set, sharp_edges(faces, groups))
