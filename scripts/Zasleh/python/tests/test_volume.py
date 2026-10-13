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
};
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


class HitPointsTest(unittest.TestCase):
    def test_radius_of_a_hit_point_class(self):
        self.assertEqual(hitpoints.radii(CONFIG), {"int_ammo_hit": 0.15, "engine_hit": 0.25})


if __name__ == "__main__":
    unittest.main()
