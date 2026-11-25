import os, sys, unittest, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as m

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kp, qp = m.ensure_data()
        cls.docs = [{"doc_id": r["doc_id"], "title": r["title"], "content": r["content"]}
                    for r in csv.DictReader(open(kp, encoding="utf-8-sig"))]
        cls.score = staticmethod(m.bm25(cls.docs))

    def test_tokenizer(self):
        t = m.tok("空压机 OC 报警")
        self.assertIn("空压", t); self.assertIn("oc", t)

    def test_synonym_expand(self):
        self.assertIn("异响", m.expand("电机嗡嗡响"))

    def test_top1_correct(self):
        top = self.score("空压机排气温度高报警")[0][1]
        self.assertEqual(top["doc_id"], "KB-02")

    def test_overlap_gate(self):
        top = self.score("中午食堂几点开饭")[0][1]
        self.assertLess(m.overlap("中午食堂几点开饭", top), 2)

if __name__ == "__main__":
    unittest.main()
