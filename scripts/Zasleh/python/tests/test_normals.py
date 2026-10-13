"""Tests for the Object Builder normal calculation and for comparing models by meaning"""

import copy
import math
import unittest

from zasleh.formats import LOD, P3D, Face, Selection, SharpEdges, UVSet, dumps, loads, normals
from zasleh.formats.compare import diff_lods, diff_models
from zasleh.formats.flags import FACE_FLATLIGHT, FACE_REVERSELIGHT, POINT_SPECIAL_LOCKNORMAL


def grid_lod(columns=2, rows=1, sharp=()):
    """Flat grid in the x-z plane"""
    lod = LOD(1.0)
    width = columns + 1
    lod.points = [(float(i), 0.0, float(j)) for j in range(rows + 1) for i in range(width)]
    lod.point_flags = [0] * len(lod.points)
    lod.normals = [(0.0, 0.0, 0.0)]
    for j in range(rows):
        for i in range(columns):
            a = j * width + i
            lod.faces.append(Face.new((a, a + width, a + width + 1, a + 1), (0, 0, 0, 0)))
    if sharp:
        lod.taggs.append(SharpEdges(list(sharp)))
    return lod


class Normals(unittest.TestCase):
    def test_flat_surface_has_one_normal_per_point(self):
        lod = grid_lod(2, 2)
        normals.recalculate(lod)
        self.assertEqual(len(lod.normals), 9)                       # one fan around every point
        for normal in lod.normals:
            self.assertEqual(tuple(round(c, 6) for c in normal), (0.0, 1.0, 0.0))
        for face in lod.faces:
            self.assertEqual(len(set(face.normals)), 4)

    def test_sharp_edge_splits_the_fans(self):
        lod = grid_lod(2, 1, sharp=[(1, 4)])                        # the edge between the two quads
        normals.recalculate(lod)
        self.assertEqual(len(lod.normals), 8)                       # points 1 and 4 now have two each
        left, right = lod.faces
        self.assertFalse(set(left.normals) & set(right.normals))

    def test_a_fold_gets_a_blended_normal_weighted_by_face_size(self):
        lod = grid_lod(2, 1)
        # fold the right quad up by 90 degrees and make it three times as long
        lod.points[2] = (1.0, 3.0, 0.0)
        lod.points[5] = (1.0, 3.0, 1.0)
        normals.recalculate(lod)
        shared = lod.normals[lod.faces[0].normals[lod.faces[0].points.index(1)]]
        self.assertAlmostEqual(math.sqrt(sum(c * c for c in shared)), 1.0, places=6)
        self.assertGreater(abs(shared[0]), abs(shared[1]))          # the bigger face wins

    def test_flat_light_face_keeps_its_own_normal(self):
        lod = grid_lod(2, 1)
        lod.points[2] = (2.0, 1.0, 0.0)
        lod.points[5] = (2.0, 1.0, 1.0)
        lod.faces[1].flags = FACE_FLATLIGHT
        normals.recalculate(lod)
        self.assertEqual(len(set(lod.faces[1].normals)), 1)
        self.assertFalse(set(lod.faces[1].normals) & set(lod.faces[0].normals))

    def test_reverse_light_flips_the_face(self):
        lod = grid_lod(1, 1)
        lod.faces[0].flags = FACE_REVERSELIGHT
        normals.recalculate(lod)
        self.assertEqual(tuple(round(c, 6) for c in lod.normals[lod.faces[0].normals[0]]), (0.0, -1.0, 0.0))

    def test_back_side_of_a_face_gets_its_own_normals(self):
        lod = grid_lod(1, 1)
        lod.faces.append(Face.new(tuple(reversed(lod.faces[0].points)), (0, 0, 0, 0)))
        normals.recalculate(lod)
        front = {tuple(round(c, 6) for c in lod.normals[i]) for i in lod.faces[0].normals}
        back = {tuple(round(c, 6) for c in lod.normals[i]) for i in lod.faces[1].normals}
        self.assertEqual(front, {(0.0, 1.0, 0.0)})
        self.assertEqual(back, {(0.0, -1.0, 0.0)})

    def test_locked_normal_is_kept(self):
        lod = grid_lod(2, 1)
        lod.point_flags[1] = POINT_SPECIAL_LOCKNORMAL
        lod.normals = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
        for face in lod.faces:
            values = list(face.v)
            values[4 * face.points.index(1) + 1] = 1                # point 1 refers to the kept normal
            face.v = tuple(values)
        normals.recalculate(lod)
        for face in lod.faces:
            self.assertEqual(lod.normals[face.normals[face.points.index(1)]], (1.0, 0.0, 0.0))
        normals.recalculate(lod, {1: (0.0, 0.0, 1.0)})              # or given from outside
        self.assertEqual(lod.normals[lod.faces[0].normals[lod.faces[0].points.index(1)]], (0.0, 0.0, 1.0))

    def test_result_survives_writing_and_is_stable(self):
        lod = grid_lod(3, 2, sharp=[(1, 5), (5, 9)])
        normals.recalculate(lod)
        model = P3D()
        model.lods.append(lod)
        again = loads(dumps(model)).lods[0]
        before = [face.normals for face in again.faces]
        normals.recalculate(again)
        self.assertEqual([face.normals for face in again.faces], before)


class Compare(unittest.TestCase):
    def sample(self):
        lod = grid_lod(2, 2, sharp=[(1, 4), (4, 7)])
        lod.taggs.append(Selection("left", bytes([1, 1, 0, 1, 1, 0, 1, 1, 0]), bytes([1, 0, 1, 0])))
        lod.taggs.append(UVSet(0, [(0.0, 0.0)] * 16))
        normals.recalculate(lod)
        return lod

    def test_equal(self):
        self.assertEqual(diff_lods(self.sample(), self.sample()), {})

    def test_order_of_tags_and_empty_selections_do_not_matter(self):
        a, b = self.sample(), self.sample()
        b.taggs.reverse()
        b.taggs.append(Selection("nothing", bytes(9), bytes(4)))
        self.assertEqual(diff_lods(a, b), {})

    def test_face_starting_at_another_corner_is_only_noted(self):
        a, b = self.sample(), self.sample()
        face = b.faces[0]
        b.faces[0] = Face(4, face.v[4:] + face.v[:4], face.flags, face.texture, face.material)
        self.assertEqual(diff_lods(a, b), {"note_faces_start_at_another_corner": 1})

    def test_changes_are_reported(self):
        a, b = self.sample(), self.sample()
        b.selection("left").weights[2] = 1
        b.faces[1].texture = "other.paa"
        b.point_flags[0] = 1
        difference = diff_lods(a, b)
        self.assertEqual(difference["selections_changed"], [("left", 1, 0)])
        self.assertEqual((difference["face_materials"], difference["point_flags"]), (1, 1))

    def test_selection_names_are_compared_exactly(self):
        a, b = self.sample(), self.sample()
        b.selection("left").name = "Left"
        difference = diff_lods(a, b)
        self.assertEqual((difference["selections_missing"], difference["selections_extra"]), (["left"], ["Left"]))

    def test_a_sharp_edge_that_changes_nothing_is_no_difference(self):
        a = grid_lod(3, 3)
        b = grid_lod(3, 3, sharp=[(5, 6)])                          # one marked edge inside a smooth surface
        normals.recalculate(a)
        normals.recalculate(b)
        self.assertEqual(diff_lods(a, b), {})
        c = grid_lod(3, 3, sharp=[(1, 5), (5, 9), (9, 13)])         # a crease right across
        normals.recalculate(c)
        difference = diff_lods(a, c)
        self.assertEqual(difference["points_shaded_differently"], 4)
        self.assertNotIn("corner_normals", difference)              # the surface is flat: same vectors

    def test_models_are_matched_by_resolution(self):
        one, two = P3D(), P3D()
        one.lods = [self.sample(), grid_lod(1, 1)]
        one.lods[1].resolution = 2.0
        two.lods = [copy.copy(one.lods[0])]
        self.assertEqual(diff_models(one, one), [])
        self.assertEqual(diff_models(one, two), [(2.0, {"lod": "missing in the second model"})])


if __name__ == "__main__":
    unittest.main()
