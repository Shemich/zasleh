"""Unit tests for the p3d core"""

import struct
import unittest

from zasleh.formats import (LOD, P3D, WEIGHT_OF_BYTE, Animation, Face, Mass, P3DError, Property, Selection,
                     SharpEdges, Tagg, UVSet, dumps, has_mass, is_point_lod, is_shadow_lod, loads,
                     lod_name, lod_resolution, weight_to_byte)


def f32(value):
    """The value after a trip through a 32-bit float, as the file stores it"""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def sample_model():
    p3d = P3D()
    p3d.encoding = "cp1252"

    lod = LOD(1.0)
    lod.points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0), (0.5, 0.5, 1.0)]
    lod.point_flags = [0, 0, 0x2000000, 0, 0x10000]
    lod.normals = [(0.0, 0.0, 1.0), (0.0, -1.0, 0.0)]
    lod.faces = [
        Face.new((0, 1, 2, 3), (0, 0, 0, 0), ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
                 flags=0x300, texture="a3\\data_f\\default_co.paa", material="a3\\data_f\\default.rvmat"),
        Face.new((0, 4, 1), (1, 1, 1), ((0.0, 0.0), (0.5, 1.0), (1.0, 0.0))),
    ]
    lod.taggs = [
        SharpEdges([(0, 1), (1, 2)]),
        Selection("camo1", bytes([1, 1, 1, 1, 0]), bytes([1, 0])),
        Selection("soft", bytes([0, 1, 128, 255, 2]), bytes([0, 0])),
        Property("lodnoshadow", "1"),
        Property("class", "house"),
        Tagg("#Mystery#", b"\x01\x02\x03"),
        UVSet(0, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]),
        UVSet(1, [(0.25, 0.25)] * 7),
    ]
    p3d.lods.append(lod)

    geometry = LOD(1.0e13)
    geometry.points = [(0.0, 0.0, 0.0), (0.0, 2.0, 0.0)]
    geometry.point_flags = [0, 0]
    geometry.taggs = [Mass([10.0, 2.5]), Animation(0.5, [(0.0, 0.0, 0.0), (0.0, 2.0, 1.0)])]
    p3d.lods.append(geometry)

    memory = LOD(1.0e15)
    memory.points = [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    memory.point_flags = [0, 0]
    memory.taggs = [Selection("axis", bytes([1, 1]), b""), Selection("pos", bytes([1, 0]), b"")]
    p3d.lods.append(memory)
    return p3d


class RoundTrip(unittest.TestCase):
    def test_synthetic_model_survives(self):
        data = dumps(sample_model())
        again = loads(data, "cp1252")
        self.assertEqual(dumps(again), data)
        self.assertEqual(again.warnings, [])
        self.assertEqual(len(again.lods), 3)

        lod = again.lods[0]
        self.assertEqual(lod.resolution, 1.0)
        self.assertEqual(lod.points[4], (0.5, 0.5, 1.0))
        self.assertEqual(lod.point_flags, [0, 0, 0x2000000, 0, 0x10000])
        self.assertEqual(lod.normals[1], (0.0, -1.0, 0.0))
        quad, triangle = lod.faces
        self.assertEqual((quad.n, quad.points, quad.normals), (4, (0, 1, 2, 3), (0, 0, 0, 0)))
        self.assertEqual(quad.uvs, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)))
        self.assertEqual((quad.flags, quad.texture, quad.material),
                         (0x300, "a3\\data_f\\default_co.paa", "a3\\data_f\\default.rvmat"))
        self.assertEqual((triangle.n, triangle.points, triangle.texture), (3, (0, 4, 1), ""))
        self.assertEqual(lod.sharp_edges, [(0, 1), (1, 2)])
        self.assertEqual([s.name for s in lod.selections], ["camo1", "soft"])
        self.assertEqual(lod.selection("CAMO1").point_indices(), [0, 1, 2, 3])
        self.assertEqual(lod.selection("camo1").face_indices(), [0])
        self.assertFalse(lod.selection("camo1").is_weighted)
        self.assertTrue(lod.selection("soft").is_weighted)
        self.assertEqual([(p.key, p.value) for p in lod.properties], [("lodnoshadow", "1"), ("class", "house")])
        self.assertEqual(lod.get_property("Class"), "house")
        self.assertIsNone(lod.get_property("missing"))
        self.assertEqual([u.index for u in lod.uvsets], [0, 1])
        self.assertEqual(lod.uvsets[1].uvs[6], (0.25, 0.25))
        self.assertEqual(lod.problems(), [])

        self.assertEqual(again.lods[1].mass, [10.0, 2.5])
        animation = again.lods[1].find(Animation)
        self.assertEqual((animation.time, animation.points[1]), (0.5, (0.0, 2.0, 1.0)))
        self.assertEqual(again.lods[2].resolution, f32(1.0e15))
        self.assertEqual(again.lods[2].faces, [])

    def test_unknown_tag_and_tag_order_are_kept(self):
        lod = loads(dumps(sample_model()), "cp1252").lods[0]
        self.assertEqual([type(t).__name__ for t in lod.taggs],
                         ["SharpEdges", "Selection", "Selection", "Property", "Property", "Tagg", "UVSet", "UVSet"])
        mystery = lod.taggs[5]
        self.assertEqual((mystery.name, mystery.data), ("#Mystery#", b"\x01\x02\x03"))

    def test_tag_with_wrong_size_is_kept_raw(self):
        p3d = sample_model()
        p3d.lods[0].taggs.append(Tagg("broken_selection", b"\x01\x01"))     # 2 bytes, needs 5 + 2
        p3d.lods[0].taggs.append(Tagg("#Mass#", b"\x00" * 6))
        data = dumps(p3d)
        again = loads(data, "cp1252")
        self.assertEqual(dumps(again), data)
        self.assertEqual(len(again.warnings), 2)
        self.assertIs(type(again.lods[0].taggs[-2]), Tagg)
        self.assertIsNone(again.lods[0].selection("broken_selection"))
        self.assertIsNone(again.lods[0].mass)

    def test_editor_state_tags_are_not_named_selections(self):
        p3d = sample_model()
        p3d.lods[2].taggs.insert(0, Selection("#Selected#", bytes([1, 0]), b""))
        again = loads(dumps(p3d), "cp1252")
        self.assertEqual([s.name for s in again.lods[2].selections], ["axis", "pos"])
        self.assertIs(type(again.lods[2].taggs[0]), Selection)
        self.assertFalse(again.lods[2].taggs[0].is_named)

    def test_trailer_and_header_extras_are_kept(self):
        p3d = sample_model()
        p3d.trailer = b"O2 editor settings"
        p3d.lods[1].head_extra = b"\xAA\xBB\xCC\xDD"
        p3d.lods[1].flags = 7
        data = dumps(p3d)
        again = loads(data, "cp1252")
        self.assertEqual(dumps(again), data)
        self.assertEqual(again.trailer, b"O2 editor settings")
        self.assertEqual((again.lods[1].head_extra, again.lods[1].flags), (b"\xAA\xBB\xCC\xDD", 7))

    def test_old_style_tag_header(self):
        # 64-byte name field instead of 0x01 + asciiz (O2 LoadTag accepts both)
        data = dumps(sample_model())
        marker = b"\x01camo1\0"
        self.assertEqual(data.count(marker), 1)
        fixed = data.replace(marker, b"camo1".ljust(64, b"\0"))
        again = loads(fixed, "cp1252")
        self.assertEqual(again.lods[0].selection("camo1").point_indices(), [0, 1, 2, 3])
        self.assertEqual(dumps(again), fixed)
        again.lods[0].selection("camo1").name = "camo2"         # renamed: written the modern way
        self.assertIn(b"\x01camo2\0", dumps(again))


class Weights(unittest.TestCase):
    def test_table_matches_o2(self):
        # Selection::Save writes the negated byte; PointWeight() is byte / 255
        self.assertEqual(WEIGHT_OF_BYTE[0], 0.0)
        self.assertEqual(WEIGHT_OF_BYTE[1], 1.0)
        self.assertAlmostEqual(WEIGHT_OF_BYTE[2], 254 / 255)
        self.assertAlmostEqual(WEIGHT_OF_BYTE[128], 128 / 255)
        self.assertAlmostEqual(WEIGHT_OF_BYTE[255], 1 / 255)

    def test_every_byte_round_trips(self):
        for byte in range(256):
            self.assertEqual(weight_to_byte(WEIGHT_OF_BYTE[byte]), byte)

    def test_clamping(self):
        self.assertEqual(weight_to_byte(1.0), 1)
        self.assertEqual(weight_to_byte(7.0), 1)
        self.assertEqual(weight_to_byte(0.0), 0)
        self.assertEqual(weight_to_byte(-1.0), 0)
        self.assertEqual(weight_to_byte(0.5), 128)

    def test_point_weights(self):
        selection = Selection("soft", bytes([0, 1, 128]), b"")
        self.assertEqual(selection.point_weights(), [0.0, 1.0, 128 / 255])


class Properties(unittest.TestCase):
    def test_padding_garbage_is_kept_until_the_value_changes(self):
        raw = b"class\0junk".ljust(64, b"\xCD") + b"house\0".ljust(64, b"\xCD")
        p3d = sample_model()
        p3d.lods[0].taggs.append(Tagg("#Property#", raw))
        again = loads(dumps(p3d), "cp1252")
        prop = again.lods[0].taggs[-1]
        self.assertEqual((type(prop), prop.key, prop.value), (Property, "class", "house"))
        self.assertIn(raw, dumps(again))
        prop.value = "tree"
        data = dumps(again)
        self.assertNotIn(raw, data)
        self.assertIn(b"class".ljust(64, b"\0") + b"tree".ljust(64, b"\0"), data)

    def test_too_long(self):
        p3d = sample_model()
        p3d.lods[0].taggs.append(Property("x" * 64, "1"))
        with self.assertRaises(P3DError):
            dumps(p3d)


class Errors(unittest.TestCase):
    def test_rejects_other_files(self):
        with self.assertRaisesRegex(P3DError, "binarized"):
            loads(b"ODOL" + b"\0" * 64)
        with self.assertRaisesRegex(P3DError, "not an MLOD"):
            loads(b"PK\x03\x04" + b"\0" * 64)
        with self.assertRaises(P3DError):
            loads(b"MLOD")

    def test_truncated_first_lod(self):
        data = dumps(sample_model())
        for cut in (20, 60, 200, 330):
            with self.assertRaises(P3DError):
                loads(data[:cut], "cp1252")

    def test_truncated_later_lod_keeps_the_good_ones(self):
        data = dumps(sample_model())
        again = loads(data[:-30], "cp1252")
        self.assertEqual(len(again.lods), 2)
        self.assertEqual(len(again.warnings), 1)

    def test_wrong_selection_length_cannot_be_written(self):
        p3d = sample_model()
        p3d.lods[0].selection("camo1").weights.append(1)
        with self.assertRaisesRegex(P3DError, "camo1"):
            dumps(p3d)

    def test_wrong_mass_and_uv_counts_cannot_be_written(self):
        p3d = sample_model()
        p3d.lods[1].mass.append(1.0)
        with self.assertRaises(P3DError):
            dumps(p3d)
        p3d = sample_model()
        p3d.lods[0].uvsets[1].uvs.pop()
        with self.assertRaises(P3DError):
            dumps(p3d)

    def test_names(self):
        p3d = sample_model()
        p3d.lods[0].faces[0].texture = "тест\\дерево_co.paa"
        with self.assertRaisesRegex(P3DError, "code page"):
            dumps(p3d, "cp1252")
        data = dumps(p3d, "cp1251")
        self.assertEqual(loads(data, "cp1251").lods[0].faces[0].texture, "тест\\дерево_co.paa")
        self.assertEqual(dumps(loads(data, "cp1252"), "cp1252"), data)      # wrong guess is still lossless
        self.assertEqual(dumps(loads(data, "utf-8"), "utf-8"), data)

    def test_problems_are_reported(self):
        p3d = sample_model()
        lod = p3d.lods[0]
        lod.faces.append(Face.new((0, 1, 99), (0, 0, 5)))
        for selection in lod.selections:
            selection.faces.append(0)
        lod.taggs = [t for t in lod.taggs if type(t) is not UVSet]
        lod.find(SharpEdges).edges.append((0, 77))
        problems = lod.problems()
        self.assertEqual(len(problems), 3)
        dumps(p3d)      # still writable: problems are for the consumer to handle


class Faces(unittest.TestCase):
    def test_new_pads_triangles(self):
        face = Face.new((5, 6, 7), (1, 2, 3))
        self.assertEqual(face.v, (5, 1, 0.0, 0.0, 6, 2, 0.0, 0.0, 7, 3, 0.0, 0.0, 0, 0, 0.0, 0.0))
        self.assertEqual((face.points, face.normals, len(face.uvs)), ((5, 6, 7), (1, 2, 3), 3))

    def test_new_rejects_bad_input(self):
        with self.assertRaises(P3DError):
            Face.new((1, 2), (0, 0))
        with self.assertRaises(P3DError):
            Face.new((1, 2, 3), (0, 0))


class LodNames(unittest.TestCase):
    def test_special_lods(self):
        self.assertEqual(lod_name(f32(1.0e15)), "Memory")
        self.assertEqual(lod_name(f32(1.0e13)), "Geometry")
        self.assertEqual(lod_name(f32(4.0e13)), "Geometry PhysX")
        self.assertEqual(lod_name(f32(5.0e15)), "HitPoints")
        self.assertEqual(lod_name(f32(2.1e16)), "Wreck")
        self.assertEqual(lod_name(1100.0), "View Pilot")
        self.assertEqual(lod_name(f32(-1.0e13)), "Geometry")

    def test_indexed_lods(self):
        self.assertEqual(lod_name(10000.0), "Shadow Volume 0")
        self.assertEqual(lod_name(10010.0), "Shadow Volume 10")
        self.assertEqual(lod_name(11000.0), "Shadow Buffer 0")
        self.assertEqual(lod_name(20001.0), "Edit 1")

    def test_resolution_lods(self):
        self.assertEqual(lod_name(1.0), "1")
        self.assertEqual(lod_name(2.5), "2.5")
        self.assertEqual(lod_name(0.0), "0")
        self.assertEqual(lod_name(f32(0.1)), "0.1")

    def test_names_map_back(self):
        for resolution in (1.0, 2.5, 1000.0, 1100.0, 1200.0, 10000.0, 10010.0, 11000.0, 11010.0, 20000.0,
                           1.0e13, 2.0e13, 3.0e13, 4.0e13, 1.0e15, 2.0e15, 3.0e15, 4.0e15, 5.0e15, 6.0e15,
                           7.0e15, 8.0e15, 9.0e15, 1.0e16, 1.1e16, 1.2e16, 1.3e16, 1.4e16, 1.5e16,
                           1.6e16, 1.7e16, 1.8e16, 1.9e16, 2.0e16, 2.1e16):
            self.assertEqual(lod_resolution(lod_name(f32(resolution))), resolution)
        self.assertEqual(lod_resolution("  memory "), 1.0e15)
        self.assertIsNone(lod_resolution("Layer001"))
        self.assertIsNone(lod_resolution("Shadow Volume x"))

    def test_kinds(self):
        self.assertTrue(is_point_lod(f32(1.0e15)))
        self.assertFalse(is_point_lod(1.0))
        self.assertTrue(is_shadow_lod(10010.0))
        self.assertTrue(is_shadow_lod(f32(1.9e16)))
        self.assertFalse(is_shadow_lod(f32(1.0e13)))
        self.assertTrue(has_mass(f32(1.0e13)))
        self.assertTrue(has_mass(f32(4.0e13)))
        self.assertFalse(has_mass(1.0))


if __name__ == "__main__":
    unittest.main()
