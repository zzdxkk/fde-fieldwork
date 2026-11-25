import os
import sys
import shutil
import platform
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import check_env as c


class ProbeTest(unittest.TestCase):
    """探测函数的「合理性」断言。

    为什么单独写这一组：这个项目真正出过的事故不是崩溃，而是「静默返回 0」——
    Windows 上 mem_gb() 没有写分支，直接 return 0.0，程序照跑、报告照出。
    只断言「不报错」的测试抓不住它，必须断言「值在合理范围内」。
    这一组在 Ubuntu / Windows / macOS 上都要跑过才算数（等价于 CI 的三平台矩阵）。
    """

    def test_mem_reasonable(self):
        m = c.mem_gb()
        self.assertGreater(m, 0, "内存读到 0：这台机器的分支没写，或取值失败（Windows 曾报 0.0GB）")
        self.assertLess(m, 8192, "内存读到 %sGB：检查单位换算（字节 / KB / GB）" % m)

    def test_cpu_count_reasonable(self):
        n = os.cpu_count() or 0
        self.assertGreater(n, 0, "CPU 核数读到 0")
        self.assertLessEqual(n, 512, "CPU 核数读到 %s：检查解析方式" % n)

    def test_disk_reasonable(self):
        free_gb = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__))).free / 1024 ** 3
        self.assertGreater(free_gb, 0, "可用磁盘读到 0")

    def test_ntp_reports_something(self):
        s = c.ntp_ok()
        self.assertIsInstance(s, str)
        self.assertTrue(s.strip(), "时间源探测返回空串：这台机器没落进任何分支")

    def test_firewall_reports_something(self):
        s = c.firewall_note()
        self.assertIsInstance(s, str)
        self.assertTrue(s.strip(), "防火墙探测返回空串：这台机器没落进任何分支")

    def test_current_platform_is_covered(self):
        """三个系统都必须有明确分支，不许落到兜底的「未检测」。"""
        sysname = platform.system()
        if sysname in ("Darwin", "Windows", "Linux"):
            self.assertNotEqual(c.ntp_ok(), "未检测", "时间源没有 %s 分支" % sysname)
            self.assertNotEqual(c.firewall_note(), "未检测", "防火墙没有 %s 分支" % sysname)

    def test_gpu_absent_is_string_not_zero(self):
        """没有 GPU 时必须是「未检测到」这种明确说法，不能返回 0 让下游算错显存档位。"""
        self.assertIsInstance(c.gpu_info(), list)
        self.assertIsInstance(c.cuda_version(), str)


if __name__ == "__main__":
    unittest.main()
