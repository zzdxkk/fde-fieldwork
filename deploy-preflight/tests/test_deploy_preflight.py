import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import check_env as c

class T(unittest.TestCase):
    def test_mem_gb_positive(self):
        self.assertGreater(c.mem_gb(), 0)

    def test_cuda_is_str(self):
        self.assertIsInstance(c.cuda_version(), str)

    def test_bench_reader_safe(self):
        r = c.read_bench()
        self.assertTrue(r is None or isinstance(r, list))

    def test_gpu_info_is_list(self):
        self.assertIsInstance(c.gpu_info(), list)

if __name__ == "__main__":
    unittest.main()
