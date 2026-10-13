import os
import shutil
import tempfile
import unittest

import atb_p3d
from atb_p3d import LOD, Face, P3D, Selection
from atb_p3d.__main__ import main, selection_names


class NamesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="atb_names_")
        self.addCleanup(shutil.rmtree, self.folder, True)
        model = P3D()
        for resolution, names in ((1.0, ["otocvez", "Component01", "proxy:\\a3\\x.001", "-sel", "Box029", "camo1"]),
                                  (2.0, ["OtocVez", "zbytek", "12"])):
            lod = LOD(resolution)
            lod.points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
            lod.point_flags = [0, 0, 0]
            lod.normals = [(0.0, 1.0, 0.0)]
            lod.faces.append(Face.new((0, 1, 2), (0, 0, 0), ((0.0, 0.0),) * 3, texture="", material=""))
            lod.taggs += [Selection(name, bytes([1, 1, 1]), bytes([1])) for name in names]
            model.lods.append(lod)
        self.path = os.path.join(self.folder, "tank.p3d")
        atb_p3d.write(model, self.path)

    def test_names_of_all_lods_once_without_what_is_no_name(self):
        self.assertEqual(selection_names([self.path]), ["camo1", "otocvez", "zbytek"])

    def test_a_folder_and_a_file_to_write(self):
        out = os.path.join(self.folder, "tank.txt")
        self.assertEqual(main(["names", self.folder, "-o", out, "-t", "a tank"]), 0)
        with open(out, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "# a tank\ncamo1\notocvez\nzbytek\n")


if __name__ == "__main__":
    unittest.main()
