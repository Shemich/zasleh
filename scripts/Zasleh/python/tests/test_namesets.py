import os
import unittest

from zasleh.formats import namesets

SETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "NameSets")


class NameSetsTest(unittest.TestCase):
    def test_lines(self):
        text = "# a tank\n\notocVez = turret, turns\n  koloL1=left wheel = the first  \nzbytek\nOTOCVEZ = again\n = no name\n"
        self.assertEqual(namesets.parse(text),
                         [("otocVez", "turret, turns"), ("koloL1", "left wheel = the first"), ("zbytek", "")])

    def test_a_folder_that_is_not_there(self):
        self.assertEqual(namesets.available(os.path.join(SETS, "nowhere")), [])
        self.assertEqual(namesets.read(SETS, "no such set"), [])

    def test_the_sets_that_come_with_the_toolbox(self):
        names = namesets.available(SETS)
        self.assertTrue({"tank", "car", "plane", "helicopter", "boat", "weapon", "house", "character"} <= set(names), names)
        for name in names:
            entries = namesets.read(SETS, name)
            self.assertTrue(5 <= len(entries) <= 60, (name, len(entries)))     # a set is a short list, not a dump
            for selection, what in entries:
                self.assertTrue(what, (name, selection))                        # every entry says what it is
                self.assertNotIn("=", selection)


if __name__ == "__main__":
    unittest.main()
