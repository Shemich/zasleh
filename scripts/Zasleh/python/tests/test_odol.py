import os
import shutil
import tempfile
import unittest

from zasleh import formats
from zasleh.formats import LOD, Face, P3D, odol


def fake_tool(folder, body):
    """A stand-in for the debinarizer: a batch file called as "tool inFolder outFolder\""""
    path = os.path.join(folder, "tool.bat")
    with open(path, "w") as stream:
        stream.write("@echo off\n" + body + "\n")
    return path


@unittest.skipUnless(os.name == "nt", "the stand-in tool is a batch file")
class OdolTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="zasleh_odol_")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.binarized = os.path.join(self.folder, "car.p3d")
        with open(self.binarized, "wb") as stream:
            stream.write(b"ODOL" + bytes(64))
        model = P3D()
        lod = LOD(1.0)
        lod.points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
        lod.point_flags = [0, 0, 0]
        lod.normals = [(0.0, 1.0, 0.0)]
        lod.faces.append(Face.new((0, 1, 2), (0, 0, 0), ((0.0, 0.0),) * 3, texture="", material=""))
        model.lods.append(lod)
        self.editable = os.path.join(self.folder, "editable.p3d")
        formats.write(model, self.editable)
        self.work = os.path.join(self.folder, "work")

    def test_signature(self):
        self.assertTrue(odol.is_odol(self.binarized))
        self.assertFalse(odol.is_odol(self.editable))

    def test_reading_one_directly_says_what_it_is(self):
        with self.assertRaises(formats.P3DError) as caught:
            formats.read(self.binarized)
        self.assertIn("ODOL", str(caught.exception))

    def test_converted_file_keeps_the_name(self):
        tool = fake_tool(self.folder, 'copy /y "%~dp0editable.p3d" "%~2\\car_mlod.p3d" >nul')
        made = odol.to_mlod(self.binarized, tool, self.work)
        self.assertEqual(os.path.basename(made), "car.p3d")
        self.assertEqual(len(formats.read(made).lods), 1)
        self.assertTrue(odol.is_odol(os.path.join(self.work, "in", "car.p3d")))      # the tool got a copy

    def test_no_tool(self):
        for tool in ("", os.path.join(self.folder, "missing.exe")):
            with self.assertRaises(formats.P3DError) as caught:
                odol.to_mlod(self.binarized, tool, self.work)
            self.assertIn("debinarizer", str(caught.exception))

    def test_tool_that_makes_nothing(self):
        with self.assertRaises(formats.P3DError) as caught:
            odol.to_mlod(self.binarized, fake_tool(self.folder, "rem nothing"), self.work)
        self.assertIn("made no editable p3d", str(caught.exception))

    def test_tool_that_hands_the_binarized_file_back(self):
        tool = fake_tool(self.folder, 'copy /y "%~1\\car.p3d" "%~2\\car.p3d" >nul')
        with self.assertRaises(formats.P3DError):
            odol.to_mlod(self.binarized, tool, self.work)


if __name__ == "__main__":
    unittest.main()
