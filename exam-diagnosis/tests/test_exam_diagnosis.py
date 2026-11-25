import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as m

class T(unittest.TestCase):
    def test_level_thresholds(self):
        self.assertEqual(m.level(0.30), "薄弱")
        self.assertEqual(m.level(0.60), "待巩固")
        self.assertEqual(m.level(0.90), "已掌握")

    def test_rule_type_concept(self):
        t, ev = m.rule_error_type("直接代入x=1得3")
        self.assertEqual(t, "概念不清"); self.assertTrue(ev)

    def test_rule_type_short_text(self):
        self.assertEqual(m.rule_error_type("略")[0], "未作答")

    def test_rule_type_unknown(self):
        t, ev = m.rule_error_type("过程省略，结论正确")
        self.assertIn(t, ("表达不规范", "规则不确定"))

    def test_mask_deterministic(self):
        self.assertEqual(m.mask_id("S01"), m.mask_id("S01"))
        self.assertNotEqual(m.mask_id("S01"), m.mask_id("S02"))

if __name__ == "__main__":
    unittest.main()
