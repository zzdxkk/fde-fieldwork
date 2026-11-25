import os, sys, unittest
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as m

class T(unittest.TestCase):
    def test_classify_fire(self):
        self.assertEqual(m.classify("消防主机报火警，位置在5楼走廊")[0], "消防设施")

    def test_safety_forced_p1(self):
        lv, human, why = m.priority("配电箱冒烟，有烧焦味", "水电照明", False)
        self.assertEqual(lv, "P1"); self.assertTrue(human)

    def test_normal_p3(self):
        lv, human, _ = m.priority("走廊灯不亮", "水电照明", False)
        self.assertEqual(lv, "P3")   # 单盏灯不亮，不影响通行与生产
        self.assertFalse(human)

    def test_weekend_not_counted(self):
        # 2026-11-07 是周六：周六到周一之间不应计入工时
        a = datetime(2026, 11, 6, 17, 0)
        b = datetime(2026, 11, 9, 10, 0)
        self.assertAlmostEqual(m.work_hours_between(a, b), 2.0, places=1)

    def test_add_work_hours_skips_weekend(self):
        start = datetime(2026, 11, 6, 17, 0)     # 周五 17:00，SLA 4 小时
        end = m.add_work_hours(start, 4)
        self.assertEqual(end.weekday(), 0)       # 落到周一
        self.assertLessEqual(end.hour, 12)

if __name__ == "__main__":
    unittest.main()
