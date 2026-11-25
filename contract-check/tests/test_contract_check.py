import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as m
import pdf_extract as pe

def _make_pdfs():
    """reportlab 只用于造样例 PDF；缺库时跳过相关用例，不让整套测试导入失败。"""
    try:
        import make_pdfs
        return make_pdfs
    except ModuleNotFoundError:
        raise unittest.SkipTest("缺 reportlab，跳过样例 PDF 生成（pip install reportlab）")


class T(unittest.TestCase):
    def test_grade_two_hard_high(self):
        iss = [("a", "高", "", "", ""), ("b", "高", "", "", "")]
        self.assertEqual(m.grade(iss, 10), "高")

    def test_grade_one_hard_small_is_mid(self):
        self.assertEqual(m.grade([("a", "高", "", "", "")], 20), "中")

    def test_grade_one_hard_big_is_high(self):
        self.assertEqual(m.grade([("a", "高", "", "", "")], 80), "高")

    def test_grade_none(self):
        self.assertEqual(m.grade([], 10), "无")

    def test_pdf_field_extract(self):
        path = os.path.join(m.PDFS, "contract_A.pdf")
        if not os.path.exists(path):
            mp = _make_pdfs()
            mp.build("contract_A", mp.TRUTH["contract_A"])
        pages = pe.extract_pages(path)
        f, where = pe.parse_fields(pages)
        self.assertGreaterEqual(len(pages), 2)
        self.assertEqual(int(f["prepay_ratio"]), 45)
        self.assertEqual(where["prepay_ratio"], 1)

    def test_pdf_defect_detected(self):
        path = os.path.join(m.PDFS, "contract_C.pdf")
        if not os.path.exists(path):
            mp = _make_pdfs()
            mp.build("contract_C", mp.TRUTH["contract_C"])
        f, _ = pe.parse_fields(pe.extract_pages(path))
        self.assertNotIn("warranty_months", f)   # 字段名拼错必须抽不到，不能猜

if __name__ == "__main__":
    unittest.main()
