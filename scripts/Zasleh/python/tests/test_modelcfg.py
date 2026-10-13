import unittest

from atb_p3d import modelcfg
from atb_p3d.modelcfg import Animation, ModelCfg

SAMPLE = '''
// a hand-written file
#include "basicDefines.hpp"
class CfgSkeletons
{
    class Default;
    class Tank : Default
    {
        isDiscrete = 1;
        skeletonInherit = "";
        skeletonBones[] = {"otocvez", "", "otochlaven", "otocvez", /* gun */ "zasleh", "otochlaven"};
    };
};
class CfgModels
{
    class Default { sectionsInherit = ""; sections[] = {}; skeletonName = ""; };
    class t34 : Default
    {
        skeletonName = "Tank";
        sections[] = {"camo1", "zasleh"};
        class Animations
        {
            class MainTurret
            {
                type = "rotationY"; source = "mainTurret"; selection = "otocvez"; axis = "osaveze";
                memory = 1; minValue = "rad -360"; maxValue = "rad +360"; angle0 = "rad -360"; angle1 = "rad +360";
            };
            class Recoil { type = translation; source = recoil; selection = "otochlaven"; axis = "osa_hlavne";
                           minValue = 0; maxValue = 1; offset0 = 0; offset1 = -0.2; };
        };
    };
};
'''


class Generating(unittest.TestCase):
    def test_parents_come_first(self):
        bones = [("gun", "turret"), ("turret", "hull"), ("hull", ""), ("wheel", "ghost"), ("a", "b"), ("b", "a")]
        ordered = modelcfg.sorted_bones(bones)
        names = [name for name, _parent in ordered]
        self.assertLess(names.index("hull"), names.index("turret"))
        self.assertLess(names.index("turret"), names.index("gun"))
        self.assertEqual(sorted(ordered), sorted(bones))            # nothing lost, the loop a <-> b included

    def test_round_trip(self):
        cfg = ModelCfg(model="t34", skeleton="Tank", bones=[("gun", "turret"), ("turret", "")], sections=["camo1", "camo2"],
                       animations=[Animation("Turret", "rotationY", "mainTurret", "turret", "axis_turret", True, 0.0, 1.0,
                                             {"angle0": "0", "angle1": "rad 360"}),
                                   Animation("Hatch", "hide", "user", "hatch", "", False, 0.0, 1.0, {"hideValue": "0.5"})])
        text = modelcfg.generate(cfg)
        self.assertIn('"turret", "",\n\t\t\t"gun", "turret"', text)
        self.assertIn('angle1 = "rad 360";', text)
        self.assertIn("hideValue = 0.5;", text)
        self.assertNotIn("axis = \"\"", text)
        back = modelcfg.parse(text)
        self.assertEqual(len(back), 1)
        again = back[0]
        self.assertEqual((again.model, again.skeleton, again.sections), ("t34", "Tank", ["camo1", "camo2"]))
        self.assertEqual(again.bones, [("turret", ""), ("gun", "turret")])
        self.assertEqual(again.animations, [cfg.animations[0], cfg.animations[1]])

    def test_empty(self):
        text = modelcfg.generate(ModelCfg())
        self.assertIn("skeletonBones[] = {};", text)
        self.assertIn("sections[] = {};", text)
        self.assertEqual(modelcfg.parse(text)[0].bones, [])


class Reading(unittest.TestCase):
    def test_hand_written_file(self):
        found = modelcfg.parse(SAMPLE)
        self.assertEqual(len(found), 1)
        cfg = found[0]
        self.assertEqual((cfg.model, cfg.skeleton), ("t34", "Tank"))
        self.assertEqual(cfg.bones, [("otocvez", ""), ("otochlaven", "otocvez"), ("zasleh", "otochlaven")])
        self.assertEqual(cfg.sections, ["camo1", "zasleh"])
        turret, recoil = cfg.animations
        self.assertEqual((turret.type, turret.source, turret.selection, turret.axis, turret.memory),
                         ("rotationY", "mainTurret", "otocvez", "osaveze", True))
        self.assertEqual(turret.extra, {"minValue": "rad -360", "maxValue": "rad +360", "angle0": "rad -360", "angle1": "rad +360"})
        self.assertEqual((recoil.type, recoil.source, recoil.min_value, recoil.max_value), ("translation", "recoil", 0.0, 1.0))
        self.assertEqual(recoil.extra, {"offset0": "0", "offset1": "-0.2"})

    def test_skeleton_only(self):
        found = modelcfg.parse('class CfgSkeletons { class S { skeletonBones[] = {"a", "", "b", "a"}; }; };')
        self.assertEqual([(c.skeleton, c.bones) for c in found], [("S", [("a", ""), ("b", "a")])])

    def test_broken_file(self):
        with self.assertRaises(modelcfg.CfgError) as caught:
            modelcfg.parse("class CfgModels {\n class A { sections[] = ; };\n};")
        self.assertIn("line 2", str(caught.exception))


INHERITED = '''
class CfgSkeletons {
    class Default { isDiscrete = 1; skeletonInherit = ""; skeletonBones[] = {}; };
    class Vehicle: Default {};
    class TankBase: Vehicle { skeletonInherit = "Vehicle"; skeletonBones[] = {"otocvez", "", "otochlaven", "otocvez"}; };
    class Tank: TankBase { skeletonInherit = "TankBase"; skeletonBones[] = {"damageHide", "", "OtocHlaven", "otocvez"}; };
    class Mine: Tank { skeletonInherit = "Tank"; skeletonBones[] = {"flag", "otocvez"}; };
    class Loop: Loop { skeletonInherit = "Loop"; skeletonBones[] = {"a", ""}; };
};
class Rotation;
class CfgModels {
    class Default { sectionsInherit = ""; sections[] = {}; skeletonName = ""; };
    class Vehicle: Default { sections[] = {"clan", "zasleh"}; };
    class Tank: Vehicle {
        sectionsInherit = "Vehicle";
        sections[] = {"Zasleh", "camo1"};
        skeletonName = "Tank";
        class Animations {
            class damageHide { type = "hide"; source = "damage"; selection = "damageHide"; hideValue = 1.0; };
            class Wheel_L1 { type = "rotationX"; source = "wheelL"; selection = "kolL1"; axis = ""; angle1 = "rad 360"; };
            class Wheel_L2: Wheel_L1 { selection = "kolL2"; };
        };
    };
    class Mine: Tank {
        skeletonName = "Mine";
        sectionsInherit = "Tank";
        sections[] = {"camo2"};
        class Animations: Animations {
            class Flag { type = "rotation"; source = "user"; selection = "flag"; axis = "flag_axis"; };
            class damageHide: damageHide { hideValue = 0.5; };
        };
    };
    class Plain: Tank {};
};
'''


class InheritanceTest(unittest.TestCase):
    def setUp(self):
        self.models = {cfg.model: cfg for cfg in modelcfg.parse(INHERITED)}

    def test_bones_come_with_those_of_the_inherited_skeletons(self):
        self.assertEqual(self.models["Mine"].bones,
                         [("otocvez", ""), ("otochlaven", "otocvez"), ("damageHide", ""), ("flag", "otocvez")])
        self.assertEqual(self.models["Tank"].bones, [("otocvez", ""), ("otochlaven", "otocvez"), ("damageHide", "")])

    def test_a_model_takes_its_skeleton_from_its_parent_class(self):
        plain = self.models["Plain"]
        self.assertEqual(plain.skeleton, "Tank")
        self.assertEqual(plain.bones, self.models["Tank"].bones)

    def test_sections_come_with_the_inherited_ones(self):
        self.assertEqual(self.models["Mine"].sections, ["clan", "zasleh", "camo1", "camo2"])
        self.assertEqual(self.models["Plain"].sections, ["clan", "zasleh", "camo1"])

    def test_animations_of_the_parent_models_and_of_parent_animations(self):
        mine = {a.name: a for a in self.models["Mine"].animations}
        self.assertEqual(list(mine), ["Wheel_L1", "Wheel_L2", "Flag", "damageHide"])
        self.assertEqual((mine["Wheel_L2"].type, mine["Wheel_L2"].source, mine["Wheel_L2"].selection,
                          mine["Wheel_L2"].extra.get("angle1")), ("rotationX", "wheelL", "kolL2", "rad 360"))
        self.assertEqual((mine["damageHide"].type, mine["damageHide"].extra.get("hideValue")), ("hide", "0.5"))
        tank = {a.name: a for a in self.models["Tank"].animations}
        self.assertEqual(tank["damageHide"].extra.get("hideValue"), "1")

    def test_what_is_written_needs_no_other_class(self):
        again = modelcfg.parse(modelcfg.generate(self.models["Mine"]))[0]
        self.assertEqual(again, self.models["Mine"])
        self.assertEqual((again.skeleton_inherit, again.sections_inherit), ("", ""))

    def test_a_skeleton_that_inherits_itself_does_not_hang(self):
        loop = modelcfg.parse("class CfgSkeletons { class Loop { skeletonInherit = \"Loop\"; skeletonBones[] = {\"a\", \"\"}; }; };")
        self.assertEqual(loop[0].bones, [("a", "")])


if __name__ == "__main__":
    unittest.main()
