import re
import unittest

from zasleh.formats import rvmat


def stages(text):
    return re.findall(r'class Stage(\d+)\s*\{\s*texture="([^"]*)";', text)


class RvmatTest(unittest.TestCase):
    def test_every_preset_is_well_formed(self):
        for preset in rvmat.PRESETS:
            text = rvmat.text(preset)
            self.assertEqual(text.count("{"), text.count("}"), preset)
            self.assertEqual(text.count('"') % 2, 0, preset)
            self.assertEqual(len(re.findall(r"PixelShaderID=", text)), 1, preset)
            for line in text.splitlines():
                self.assertRegex(line, r"^(//.*|\w+(\[\])?=.*;|class \w+|\s*[{}];?)$|^\s+\w+(\[\])?=.*;$|^\s+class \w+$", preset)
            numbers = [int(number) for number, _texture in stages(text)]
            self.assertEqual(numbers, list(range(1, len(numbers) + 1)), preset)

    def test_super_puts_the_maps_into_its_own_stages(self):
        text = rvmat.text("Super", "a\\x_nohq.paa", "a\\x_smdi.paa")
        self.assertIn('PixelShaderID="Super"', text)
        found = dict(stages(text))
        self.assertEqual(len(found), 7)
        self.assertEqual(found["1"], "a\\x_nohq.paa")
        self.assertEqual(found["2"], rvmat.DETAIL)
        self.assertEqual(found["5"], "a\\x_smdi.paa")
        self.assertIn('useWorldEnvMap="true"', text)

    def test_the_old_two_stage_layout_has_its_own_shader(self):
        text = rvmat.text("NormalSpecular", "n.paa", "s.paa")
        self.assertIn('PixelShaderID="NormalMapSpecularDIMap"', text)
        self.assertEqual(stages(text), [("1", "n.paa"), ("2", "s.paa")])

    def test_detail(self):
        text = rvmat.text("Detail", "n.paa", "s.paa", "d.paa")
        self.assertEqual(stages(text), [("1", "n.paa"), ("2", "d.paa"), ("3", "s.paa")])

    def test_maps_left_out_become_plain_values(self):
        found = dict(stages(rvmat.text("Super")))
        self.assertEqual((found["1"], found["5"]), (rvmat.NOHQ, rvmat.SMDI))

    def test_glass_has_no_maps_of_the_material(self):
        text = rvmat.text("Glass", "n.paa", "s.paa")
        self.assertNotIn("n.paa", text)
        self.assertNotIn("uvTransform", text)
        self.assertEqual(rvmat.MAPS["Glass"], ())

    def test_unknown_preset(self):
        with self.assertRaises(ValueError):
            rvmat.text("Shiny")


if __name__ == "__main__":
    unittest.main()
