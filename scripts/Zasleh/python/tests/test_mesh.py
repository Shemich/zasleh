"""Tests for smoothing groups and mesh preparation (no 3ds Max needed)"""

import unittest

from atb_p3d import LOD, Face, Selection, SharpEdges, UVSet, normals
from atb_p3d.meshprep import Slot, face_uvs, flag_code, flag_from_code, prepare
from atb_p3d.smoothing import (interior_edges, shading_differences, sharp_edges,
                               sharp_edges_from_normals, to_smoothing_groups)

# a cube: 8 points, 6 quads
CUBE = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]


def grid(columns, rows):
    """Quads of a columns x rows grid"""
    width = columns + 1
    return [(j * width + i, j * width + i + 1, (j + 1) * width + i + 1, (j + 1) * width + i)
            for j in range(rows) for i in range(columns)]


class SmoothingGroups(unittest.TestCase):
    def check(self, faces, sharp):
        groups, wrong = to_smoothing_groups(faces, sharp)
        self.assertEqual(wrong, 0)
        wanted = {tuple(sorted(e)) for e in sharp} & interior_edges(faces)
        self.assertEqual(sharp_edges(faces, groups), wanted)
        return groups

    def test_all_smooth(self):
        groups = self.check(CUBE, [])
        self.assertEqual(len(set(groups)), 1)
        self.assertNotEqual(groups[0], 0)

    def test_all_sharp_is_group_zero(self):
        groups = self.check(CUBE, interior_edges(CUBE))
        self.assertEqual(groups, [0] * 6)

    def test_one_hard_face(self):
        top = {(4, 5), (5, 6), (6, 7), (4, 7)}
        groups = self.check(CUBE, top)
        self.assertEqual(groups[1], 0)                      # the face behind those edges is faceted
        self.assertEqual(len({g for i, g in enumerate(groups) if i != 1}), 1)

    def test_two_smooth_halves(self):
        faces = grid(4, 2)
        # a crease across the whole strip, between column 1 and column 2
        sharp = [(2, 7), (7, 12)]
        groups = self.check(faces, sharp)
        left = {groups[i] for i in (0, 1, 4, 5)}
        right = {groups[i] for i in (2, 3, 6, 7)}
        self.assertEqual((len(left), len(right)), (1, 1))
        self.assertFalse(left.pop() & right.pop())

    def test_crease_that_does_not_cut_the_surface(self):
        # 4 x 4 grid, a crease running from the border to the centre only
        faces = grid(4, 4)
        sharp = [(2, 7), (7, 12)]
        self.check(faces, sharp)

    def test_crease_in_the_middle(self):
        faces = grid(6, 6)
        sharp = [(17, 24), (24, 31)]                        # touches no border
        groups = self.check(faces, sharp)
        self.assertTrue(all(groups))                        # every face still smooths with someone

    def test_many_patches_need_few_bits(self):
        # a 12 x 12 grid cut into 3 x 3 hard-edged patches of 4 x 4 quads
        columns = rows = 12
        faces = grid(columns, rows)
        width = columns + 1
        sharp = set()
        for cut in (4, 8):
            for k in range(rows):
                sharp.add((k * width + cut, (k + 1) * width + cut))         # vertical cuts
                sharp.add((cut * width + k, cut * width + k + 1))           # horizontal cuts
        groups = self.check(faces, sharp)
        used = 0
        for group in groups:
            used |= group
        self.assertLessEqual(bin(used).count("1"), 6)

    def test_sharp_edges_that_are_not_edges_are_ignored(self):
        groups, wrong = to_smoothing_groups(CUBE, [(0, 6), (100, 200)])
        self.assertEqual(wrong, 0)
        self.assertEqual(len(set(groups)), 1)

    def test_lone_sharp_edge_changes_nothing(self):
        # one marked edge inside a smooth surface: both its ends stay smooth all the way round
        faces = grid(4, 4)
        sharp = [(12, 13)]
        groups, wrong = to_smoothing_groups(faces, sharp)
        self.assertEqual(wrong, 0)
        self.assertEqual(shading_differences(faces, sharp, sharp_edges(faces, groups)), 0)

    def test_shading_differences_are_counted(self):
        faces = grid(4, 2)
        sharp = [(2, 7), (7, 12)]
        self.assertEqual(shading_differences(faces, sharp, []), 3)             # points 2, 7 and 12
        groups = to_smoothing_groups(faces, sharp)[0]
        self.assertEqual(shading_differences(faces, sharp, sharp_edges(faces, groups)), 0)

    def test_faces_wound_the_same_way_never_shade_together(self):
        # two tris sharing edge 0-1 but both running 0 -> 1 along it (one is flipped)
        faces = [(0, 1, 2), (0, 1, 3)]
        groups, wrong = to_smoothing_groups(faces, [])
        self.assertEqual(wrong, 0)
        self.assertEqual(groups, [0, 0])
        self.assertEqual(sharp_edges(faces, [1, 1]), set())                     # not an edge between neighbours

    def test_from_normal_indices(self):
        faces = [(0, 1, 2), (0, 2, 3)]
        self.assertEqual(sharp_edges_from_normals(faces, [(0, 1, 2), (0, 2, 3)]), set())
        self.assertEqual(sharp_edges_from_normals(faces, [(0, 1, 2), (4, 5, 3)]), {(0, 2)})
        self.assertEqual(sharp_edges_from_normals(faces, [(0, 1, 2), (0, 5, 3)]), {(0, 2)})


def sample_lod():
    lod = LOD(1.0)
    # points 0..3 a quad, 4 the tip of a tri, 5 and 6 loose
    lod.points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0),
                  (0.5, 1.0, 0.5), (9.0, 9.0, 9.0), (8.0, 8.0, 8.0)]
    lod.point_flags = [0] * 7
    lod.normals = [(0.0, 1.0, 0.0)]
    lod.faces = [
        Face.new((0, 1, 2, 3), (0, 0, 0, 0), ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), texture="a.paa"),
        Face.new((0, 4, 1), (0, 0, 0), ((0.0, 0.0), (0.5, 0.25), (1.0, 0.0)), texture="b.paa", material="b.rvmat"),
        Face.new((1, 1, 2), (0, 0, 0)),                         # degenerate: dropped
        Face.new((1, 4, 2), (0, 0, 0), ((1.0, 0.0), (0.5, 0.25), (1.0, 1.0)), texture="a.paa"),
    ]
    lod.taggs = [SharpEdges([(0, 1)]),
                 Selection("quad", bytes([1, 1, 1, 1, 0, 0, 0]), bytes([1, 0, 0, 0])),
                 Selection("soft", bytes([0, 128, 0, 0, 1, 1, 0]), bytes([0, 0, 0, 0]))]
    return lod


class Prepare(unittest.TestCase):
    def test_geometry(self):
        mesh = prepare(sample_lod())
        self.assertEqual(mesh.dropped, 1)
        self.assertEqual(mesh.loose, [5, 6])
        self.assertEqual(mesh.points, [0, 1, 2, 3, 4])
        self.assertEqual(mesh.verts[4], (0.5, 0.5, 1.0))        # y and z swapped
        self.assertEqual(mesh.faces, [0, 1, 3])
        self.assertEqual(mesh.tris, [(0, 1, 2), (0, 2, 3), (0, 4, 1), (1, 4, 2)])
        self.assertEqual(mesh.tri_face, [0, 0, 1, 3])
        self.assertEqual(mesh.quads, [0])
        self.assertEqual(mesh.materials, [("a.paa", ""), ("b.paa", "b.rvmat")])
        self.assertEqual(mesh.mat_ids, [1, 1, 2, 1])

    def test_double_sided_surface_is_two_separate_sheets(self):
        # 2 x 2 quads with a back side: an Editable Poly can't hold both sides on the same verts
        lod = LOD(1.0)
        lod.points = [(float(i % 3), 0.0, float(i // 3)) for i in range(9)]
        lod.point_flags = [0] * 9
        lod.normals = [(0.0, 1.0, 0.0)]
        front = grid(2, 2)
        lod.faces = ([Face.new(q, (0, 0, 0, 0)) for q in front] +
                     [Face.new(tuple(reversed(q)), (0, 0, 0, 0)) for q in front])
        mesh = prepare(lod)
        self.assertEqual(mesh.points, [p for p in range(9) for _side in range(2)])      # sides adjacent
        front_vertices = {v for tri in mesh.tris[:8] for v in tri}
        back_vertices = {v for tri in mesh.tris[8:] for v in tri}
        self.assertEqual((len(front_vertices), len(back_vertices), len(front_vertices & back_vertices)), (9, 9, 0))
        self.assertEqual(len(mesh.quads), 8)

    def test_thin_wedge_stays_one_surface(self):
        # two faces folded onto each other along an edge, but not each other's back side
        lod = LOD(1.0)
        lod.points = [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (1.0, 0.001, 0.0)]
        lod.point_flags = [0] * 4
        lod.normals = [(0.0, 1.0, 0.0)]
        lod.faces = [Face.new((0, 1, 2), (0, 0, 0)), Face.new((1, 0, 3), (0, 0, 0))]
        self.assertEqual(prepare(lod).points, [0, 1, 2, 3])

    def test_third_face_on_an_edge_is_separated_there(self):
        # two coplanar tris and a fin standing on their shared edge: the flat pair stays joined
        lod = LOD(1.0)
        lod.points = [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        lod.point_flags = [0] * 5
        lod.normals = [(0.0, 1.0, 0.0)]
        lod.faces = [Face.new((0, 1, 2), (0, 0, 0)), Face.new((1, 0, 3), (0, 0, 0)), Face.new((0, 1, 4), (0, 0, 0))]
        mesh = prepare(lod)
        self.assertEqual(mesh.points, [0, 0, 1, 1, 2, 3, 4])
        flat_a, flat_b, fin = (set(tri) for tri in mesh.tris)
        self.assertEqual((len(flat_a & flat_b), len(fin & (flat_a | flat_b))), (2, 0))

    def test_ordinary_mesh_is_not_split(self):
        lod = LOD(1.0)
        lod.points = [(float(i % 4), 0.0, float(i // 4)) for i in range(12)]
        lod.point_flags = [0] * 12
        lod.normals = [(0.0, 1.0, 0.0)]
        lod.faces = [Face.new(q, (0, 0, 0, 0)) for q in grid(3, 2)]
        mesh = prepare(lod)
        self.assertEqual(mesh.points, list(range(12)))
        self.assertEqual(len(mesh.quads), 6)

    def test_smoothing_follows_sharp_edges(self):
        mesh = prepare(sample_lod())
        self.assertEqual(mesh.smoothing_wrong, 0)
        self.assertFalse(mesh.sharp_from_normals)
        quad, triangle, other = mesh.groups[0], mesh.groups[2], mesh.groups[3]
        self.assertEqual(mesh.groups[1], quad)
        self.assertFalse(quad & triangle)                       # edge 0-1 is sharp
        self.assertTrue(quad & other)                           # edge 1-2 isn't
        self.assertTrue(triangle & other)                       # edge 1-4 isn't

    def test_without_sharp_tag_object_builder_normals_mean_no_sharp_edges(self):
        lod = sample_lod()
        lod.taggs = [t for t in lod.taggs if type(t) is not SharpEdges]
        normals.recalculate(lod)                                # as Object Builder saves it
        mesh = prepare(lod)
        self.assertFalse(mesh.sharp_from_normals)
        self.assertEqual(len(set(mesh.groups)), 1)              # all smooth

    def test_without_sharp_tag_foreign_normals_are_followed(self):
        # another tool: no tag, but the tri on edge 0-1 has a normal of its own
        lod = sample_lod()
        lod.taggs = [t for t in lod.taggs if type(t) is not SharpEdges]
        lod.normals = [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]
        lod.faces[1] = Face.new((0, 4, 1), (1, 1, 1))
        mesh = prepare(lod)
        self.assertTrue(mesh.sharp_from_normals)
        quad, triangle, other = mesh.groups[0], mesh.groups[2], mesh.groups[3]
        self.assertFalse(quad & triangle)
        self.assertFalse(other & triangle)
        self.assertTrue(quad & other)

    def test_uv_channel_welds_equal_uvs(self):
        lod = sample_lod()
        mesh = prepare(lod)
        channel = mesh.uv_channel(face_uvs(lod)[0])
        self.assertEqual(len(channel.tris), 4)
        self.assertEqual(channel.verts[0], (0.0, 1.0, 0.0))     # v is flipped
        self.assertEqual(len(channel.verts), 5)                 # shared corners with equal uv are welded
        self.assertEqual(channel.tris[0][0], channel.tris[2][0])

    def test_uvset_tags_win_over_face_uvs(self):
        lod = sample_lod()
        lod.taggs.append(UVSet(0, [(0.5, 0.5)] * 13))
        lod.taggs.append(UVSet(1, [(0.25, 0.75)] * 13))
        sets = face_uvs(lod)
        self.assertEqual(sorted(sets), [0, 1])
        self.assertEqual(sets[0][0], ((0.5, 0.5),) * 4)
        self.assertEqual(sets[1][3], ((0.25, 0.75),) * 3)

    def test_data_channel_per_vertex(self):
        lod = sample_lod()
        mesh = prepare(lod)
        soft = lod.selection("soft")
        channel = mesh.data_channel([Slot(point_part=soft.point_weights())])
        self.assertEqual(channel.tris, mesh.tris)               # no face part: same topology as the mesh
        self.assertEqual([v[0] for v in channel.verts], [0.0, 128 / 255, 0.0, 0.0, 1.0])

    def test_data_channel_with_face_part_splits_at_the_border(self):
        lod = sample_lod()
        mesh = prepare(lod)
        quad = lod.selection("quad")
        weights = quad.point_weights()
        flags = [2.0 if b else 0.0 for b in quad.faces]
        channel = mesh.data_channel([None, Slot(weights, flags)])
        # vert 1 is used by the quad (in the selection's faces) and by two tris (not in them)
        values_at_1 = {channel.verts[m][1] for tri, mapped in zip(mesh.tris, channel.tris)
                       for vertex, m in zip(tri, mapped) if vertex == 1}
        self.assertEqual(values_at_1, {3.0, 1.0})
        self.assertEqual({v[0] for v in channel.verts}, {0.0})
        self.assertEqual(len(channel.verts), 4 + 4)             # quad corners + 0, 1, 2, 4 seen from outside


class FlagCodes(unittest.TestCase):
    def test_every_byte_round_trips(self):
        for byte in range(256):
            self.assertEqual(flag_from_code(flag_code(byte)), byte)

    def test_average_of_two_codes_is_never_a_code(self):
        codes = [flag_code(byte) for byte in range(256)]
        valid = set(codes)
        for a in codes:
            for b in codes:
                if a != b:
                    self.assertNotIn((a + b) / 2, valid)

    def test_interpolated_value_reads_as_no_flags(self):
        self.assertEqual(flag_from_code((flag_code(2) + flag_code(0)) / 2), 0)
        self.assertEqual(flag_from_code(flag_code(0x10) * 0.3), 0)
        self.assertEqual(flag_from_code(flag_code(0x81) + 0.0004), 0x81)       # float noise is fine


if __name__ == "__main__":
    unittest.main()
