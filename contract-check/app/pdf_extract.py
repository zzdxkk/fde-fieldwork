#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 文本抽取（纯标准库：zlib 解压内容流 + 解析 Tj/TJ）

适用范围（明确边界）：
- 有文本层/表单域的电子合同：可抽（本版验证对象）
- 扫描件/图片型 PDF：抽不出来，需 OCR（未实现，报告里如实标注）

返回：按页的文本块，便于把问题定位到「第几页」。
"""
import os, re, zlib, base64


def _decode(raw):
    """按常见 Filter 链解码：Flate / ASCII85+Flate / 无压缩。
    现场 PDF 多数是这几种；加密或 JBIG2 的流本函数不处理，交由上层标注「抽取失败」。"""
    raw = raw.strip(b"\r\n")
    try:
        return zlib.decompress(raw)
    except Exception:
        pass
    try:                                     # ASCII85（reportlab 自带 ~> 结尾）
        dec = base64.a85decode(raw, adobe=True)
        try:
            return zlib.decompress(dec)
        except Exception:
            return dec
    except Exception:
        pass
    try:                                     # ASCII85 无结尾标记，补 <~ ~>
        dec = base64.a85decode(b"<~" + raw + b"~>", adobe=True)
        try:
            return zlib.decompress(dec)
        except Exception:
            return dec
    except Exception:
        return None


def _streams(data):
    """取出所有 stream 对象的可解码字节（解码失败的直接丢弃，不伪造内容）。"""
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        dec = _decode(data[start:end])
        if dec:
            out.append(dec)
    return out


_ESC = {b"\\n": b"\n", b"\\r": b"\r", b"\\t": b"\t", b"\\(": b"(", b"\\)": b")", b"\\\\": b"\\"}


def _unescape(s):
    for k, v in _ESC.items():
        s = s.replace(k, v)
    s = re.sub(rb"\\[0-7]{1,3}", lambda m: bytes([int(m.group(0)[1:], 8)]), s)
    return s


def _text_from_stream(stream):
    """提取 Tj / TJ 里的字面量字符串，按出现顺序拼接。"""
    chunks = []
    # TJ 数组：[(a) -20 (b)] TJ  -> 取其中所有 (...) 串
    for m in re.finditer(rb"\[(.*?)\]\s*TJ", stream, re.S):
        inner = m.group(1)
        parts = re.findall(rb"\((.*?)\)", inner, re.S)
        chunks.append(b"".join(_unescape(p) for p in parts))
    # Tj： (a) Tj
    for m in re.finditer(rb"\((.*?)\)\s*Tj", stream, re.S):
        chunks.append(_unescape(m.group(1)))
    return b"\n".join(chunks).decode("latin-1", errors="ignore")


def extract_pages(path):
    data = open(path, "rb").read()
    pages = []
    for s in _streams(data):
        if b"Tj" in s or b"TJ" in s:
            t = _text_from_stream(s).strip()
            if t:
                pages.append(t)
    return pages


def extract_text(path):
    return "\n".join(extract_pages(path))


FIELD_PATTERNS = {
    "contract_id": r"contract_id:\s*([A-Za-z0-9\-]+)",
    "prepay_ratio": r"prepay_ratio:\s*(\d+(?:\.\d+)?)",
    "warranty_months": r"warranty_months:\s*(\d+)",
    "penalty_ratio": r"penalty_ratio:\s*(\d+(?:\.\d+)?)",
    "delivery_days": r"delivery_days:\s*(\d+)",
    "payment_days": r"payment_days:\s*(\d+)",
    "invoice_type": r"invoice_type:\s*([A-Za-z0-9_]+)",
    "accept_quantified": r"accept_quantified:\s*(\d)",
    "amount_wan": r"amount_wan:\s*(\d+(?:\.\d+)?)",
}

NUMERIC = {"prepay_ratio", "warranty_months", "penalty_ratio", "delivery_days",
           "payment_days", "accept_quantified", "amount_wan"}


def parse_fields(pages):
    """返回 (字段字典, 字段所在页码字典)"""
    fields, where = {}, {}
    for idx, page in enumerate(pages, 1):
        for k, pat in FIELD_PATTERNS.items():
            m = re.search(pat, page)
            if not m:
                continue
            v = m.group(1).strip()
            fields[k] = float(v) if k in NUMERIC else v
            where[k] = idx
    return fields, where


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print("===", os.path.basename(p))
        pages = extract_pages(p)
        f, w = parse_fields(pages)
        print(f, w)
