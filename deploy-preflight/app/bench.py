#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压测脚本（真实跑的并发测量，不是编数字）

做的事：起一个本机 stub 推理服务（每 token 20ms、同时最多 4 个请求在算，
超出排队），然后按 1/2/4/8/16 并发打请求，记录首包、完成、成功率、吞吐。

口径边界（必须在交付时说）：
- 测的是**服务链路 + 排队 + 客户端开销**，模型耗时由 stub 模拟；
- 换成真模型，数字会变，但方法与表格结构不变；
- 不因此推断「客户机器能跑 20 并发」。
"""
import os, sys, csv, json, time, threading, statistics
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(BASE), "out")
PORT = 18089
TOKEN_MS = 0.020        # 模拟单 token 耗时
CAPACITY = 4            # 模拟单机同时计算能力
SEM = threading.Semaphore(CAPACITY)


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        max_tokens = int(body.get("max_tokens", 128))
        SEM.acquire()                       # 超出 4 个就排队，模拟真实瓶颈
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            t = "tok"
            self.wfile.write(b"%x\r\n" % len(("{\"t\":\"%s\"}" % t).encode()) +
                             ("{\"t\":\"%s\"}" % t).encode() + b"\r\n")
            for _ in range(max_tokens - 1):
                time.sleep(TOKEN_MS)
                self.wfile.write(b"%x\r\n" % len(("{\"t\":\"%s\"}" % t).encode()) +
                                 ("{\"t\":\"%s\"}" % t).encode() + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        except Exception:
            pass
        finally:
            SEM.release()


def one_request(tokens, res, idx):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=60)
    body = json.dumps({"prompt_tokens": 512, "max_tokens": tokens})
    t0 = time.time()
    ok = False
    first = None
    try:
        c.request("POST", "/generate", body, {"Content-Type": "application/json"})
        r = c.getresponse()
        while True:
            chunk = r.read(1) or r.read1(4096) if hasattr(r, "read1") else r.read(4096)
            if not chunk:
                break
            if first is None:
                first = time.time() - t0
        ok = r.status == 200
    except Exception:
        pass
    finally:
        c.close()
    res[idx] = (first, time.time() - t0, ok)


def pct(vals, p):
    if not vals:
        return 0
    k = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * p))))
    return sorted(vals)[k]


def run():
    os.makedirs(OUT, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Stub)
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    time.sleep(0.3)

    rows = []
    for conc in (1, 2, 4, 8, 16):
        res = [None] * conc
        t0 = time.time()
        ts = [threading.Thread(target=one_request, args=(128, res, i)) for i in range(conc)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        wall = time.time() - t0
        first = [x[0] for x in res if x and x[0]]
        total = [x[1] for x in res if x]
        ok = sum(1 for x in res if x and x[2])
        rows.append({
            "concurrency": conc,
            "first_p50": int(pct(first, 0.5) * 1000),
            "first_p95": int(pct(first, 0.95) * 1000),
            "total_p95": int(pct(total, 0.95) * 1000),
            "success_rate": round(ok * 100.0 / conc, 1),
            "rps": round(conc / wall, 2) if wall else 0,
        })

    srv.shutdown()
    with open(os.path.join(OUT, "bench_result.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    md = ["# 压测结果（本机实跑）\n",
          "口径：stub 每 token 20ms、单机同时计算上限 %d，超出排队；客户端本机回环。\n" % CAPACITY,
          "| 并发 | 首包 P50 | 首包 P95 | 完成 P95 | 成功率 | 吞吐 |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| %d | %d ms | %d ms | %d ms | %.1f%% | %.2f req/s |"
                  % (r["concurrency"], r["first_p50"], r["first_p95"],
                     r["total_p95"], r["success_rate"], r["rps"]))
    base = min(r["first_p95"] for r in rows if r["concurrency"] <= CAPACITY)
    peak = max(r["rps"] for r in rows if r["concurrency"] <= CAPACITY)
    over = [r for r in rows if r["concurrency"] > CAPACITY]
    jump = min(r["first_p95"] for r in over) if over else 0
    md.append("\n**能读出什么**：并发 ≤%d 时首包 P95 最低 %d ms（含本机抖动）、吞吐峰值 %.2f req/s；"
              "并发超过 %d 后首包 P95 抬到 %d ms、吞吐不再增长（停在 %.2f req/s 附近）——"
              "这条曲线就是「该加机器」的依据，也是跟客户谈容量时唯一可信的口径。"
              % (CAPACITY, base, peak, CAPACITY, jump,
                 max(r["rps"] for r in over) if over else 0))
    md.append("\n**不能读出什么**：不能推断真模型吞吐；不能推断客户机器性能；"
              "stub 不含 prefill/decode 差异。")
    with open(os.path.join(OUT, "bench_result.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("\n".join(md))
    print("\n[OK] out/bench_result.csv、out/bench_result.md")


if __name__ == "__main__":
    run()
