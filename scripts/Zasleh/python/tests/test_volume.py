import math
import unittest

from zasleh import volume
from zasleh.formats import hitpoints

CONFIG = """
class HitPoints {
    class HitHull: HitHull {
        armor = -190; material = -1;
        name = "int_ammo_hit";   // the selection
        visual = "dmg_hull"; passThrough = 10; minimalHit = 0.14;
        radius = 0.15;
    };
    class HitEngine { name = "engine_hit"; radius = 2.5e-1; };
    class HitFuel { name = "fuel_hit"; };      /* radius = 9; */
    class HitTurret: HitHull {
        name = "turret_hit"; hitpoint[] = {"a", "b"};
        class Effects { name = "smoke"; radius = 7; };
        radius = 0.18;
    };
};
class Turrets { class MainTurret { class HitPoints { class HitGun { name = "gun_hit"; radius = 0.2; }; }; }; };
"""


def box(low, high):
    """The twelve triangles of an axis-aligned box"""
    (x0, y0, z0), (x1, y1, z1) = low, high
    c = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return [(c[a], c[b], c[d]) for a, b, d, _e in quads] + [(c[a], c[d], c[e]) for a, _b, d, e in quads]


class AxisTest(unittest.TestCase):
    def test_cells_centred_in_the_extent(self):
        self.assertEqual(volume.axis(0.0, 1.0, 0.25), [0.125, 0.375, 0.625, 0.875])
        self.assertEqual([round(v, 9) for v in volume.axis(0.0, 1.0, 0.4)], [0.3, 0.7])

    def test_smaller_than_a_cell(self):
        self.assertEqual([round(v, 9) for v in volume.axis(2.0, 2.2, 0.5)], [2.1])


class FillTest(unittest.TestCase):
    def test_a_box_is_filled(self):
        points, skipped = volume.fill(box((0, 0, 0), (1, 1, 1)), (0.5, 0.5, 0.5))
        self.assertEqual(skipped, 0)
        self.assertEqual(sorted(points), sorted((x, y, z) for x in (0.25, 0.75) for y in (0.25, 0.75) for z in (0.25, 0.75)))

    def test_spacing_per_axis(self):
        points, _skipped = volume.fill(box((0, 0, 0), (2, 1, 1)), (0.5, 1.0, 1.0))
        self.assertEqual(sorted(points), [(x, 0.5, 0.5) for x in (0.25, 0.75, 1.25, 1.75)])

    def test_only_what_is_inside(self):
        # an L: a 2 x 1 x 1 bar and a 1 x 1 x 1 block on top of its end; the grid covers the whole 2 x 2 x 1 box
        shape = box((0, 0, 0), (2, 1, 1)) + box((0, 1, 0), (1, 2, 1))
        points, skipped = volume.fill(shape, (1.0, 1.0, 1.0))
        self.assertEqual(skipped, 0)
        self.assertEqual(sorted(points), [(0.5, 0.5, 0.5), (0.5, 1.5, 0.5), (1.5, 0.5, 0.5)])

    def test_an_open_mesh_is_said_not_guessed(self):
        opened = box((0, 0, 0), (1, 1, 1))[1:]
        points, skipped = volume.fill(opened, (0.5, 0.5, 0.5))
        self.assertGreater(skipped, 0)
        self.assertLess(len(points), 8)

    def test_nothing(self):
        self.assertEqual(volume.fill([], (1, 1, 1)), ([], 0))


def turned(points, degrees):
    """Points turned about the z axis"""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(x * c - y * s, x * s + y * c, z) for x, y, z in points]


def box_mesh(low, high, degrees=0.0, first=0):
    """(verts, faces) of a box, turned about z; faces count their verts from first"""
    (x0, y0, z0), (x1, y1, z1) = low, high
    verts = turned([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], degrees)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    faces = [(a, b, d) for a, b, d, _e in quads] + [(a, d, e) for a, _b, d, e in quads]
    return verts, [tuple(index + first for index in face) for face in faces]


class PiecesTest(unittest.TestCase):
    def test_boxes_that_overlap_are_filled_through(self):
        shape = box((0, 0, 0), (2, 1, 1)) + box((1, 0, 0), (3, 1, 1))
        points, skipped = volume.fill(shape, (1.0, 1.0, 1.0))
        self.assertEqual(skipped, 0)
        self.assertEqual(sorted(points), [(0.5, 0.5, 0.5), (1.5, 0.5, 0.5), (2.5, 0.5, 0.5)])

    def test_a_box_gives_its_own_axes_however_it_is_turned(self):
        verts, faces = box_mesh((0, 0, 0), (3, 2, 1), 30.0)
        x_axis, y_axis, z_axis = volume.frame([tuple(verts[i] for i in face) for face in faces])
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        for got, wanted in ((x_axis, (c, s, 0.0)), (y_axis, (-s, c, 0.0)), (z_axis, (0.0, 0.0, 1.0))):
            self.assertTrue(all(abs(a - b) < 0.02 for a, b in zip(got, wanted)), (got, wanted))

    def test_every_piece_on_a_grid_of_its_own(self):
        a_verts, a_faces = box_mesh((0, 0, 0), (1, 1, 1))
        b_verts, b_faces = box_mesh((5, 0, 0), (7, 1, 1), 30.0, first=8)
        points, skipped, pieces = volume.fill_elements(a_verts + b_verts, a_faces + b_faces, (0.5, 0.5, 0.5))
        self.assertEqual((skipped, pieces, len(points)), (0, 2, 8 + 16))
        # the turned box holds its 4 x 2 x 2 points evenly: their middle is the middle of the box
        far = [p for p in points if p[0] > 2.0]
        middle = [sum(p[i] for p in far) / len(far) for i in range(3)]
        wanted = turned([(6.0, 0.5, 0.5)], 30.0)[0]
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(middle, wanted)), (middle, wanted))

    def test_where_pieces_overlap_the_points_are_not_doubled(self):
        a_verts, a_faces = box_mesh((0, 0, 0), (1, 1, 1))
        b_verts, b_faces = box_mesh((0, 0, 0), (1, 1, 1), first=8)
        points, _skipped, pieces = volume.fill_elements(a_verts + b_verts, a_faces + b_faces, (0.5, 0.5, 0.5))
        self.assertEqual((pieces, len(points)), (2, 8))

    def test_pieces_are_told_apart_by_shared_verts(self):
        self.assertEqual(sorted(sorted(piece) for piece in volume.elements([(0, 1, 2), (2, 3, 4), (7, 8, 9)])), [[0, 1], [2]])


class HitPointsTest(unittest.TestCase):
    def test_radius_of_a_hit_point_class(self):
        self.assertEqual(hitpoints.radii(CONFIG), {"int_ammo_hit": 0.15, "engine_hit": 0.25, "turret_hit": 0.18,
                                                   "smoke": 7.0, "gun_hit": 0.2})


if __name__ == "__main__":
    unittest.main()
