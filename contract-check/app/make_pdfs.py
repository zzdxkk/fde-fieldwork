#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 3 份电子合同 PDF（含表单域式 ASCII 键值行），用于验证抽取链路。

为什么用 ASCII 键值：电子签平台（法大大/e签宝）导出的合同 PDF 带表单域，
字段值可直接取；中文正文/扫描件需要 OCR，那是另一个工程量级，本版不做——
报告里会明确写这条边界，不冒充"能读扫描件"。
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "pdfs")

TRUTH = {
 "contract_A": {"contract_id": "HT-A-001", "prepay_ratio": 45, "warranty_months": 12,
                "penalty_ratio": 3, "delivery_days": 45, "payment_days": 60,
                "invoice_type": "VAT_NORMAL", "accept_quantified": 0, "amount_wan": 120},
 "contract_B": {"contract_id": "HT-B-002", "prepay_ratio": 20, "warranty_months": 24,
                "penalty_ratio": 8, "delivery_days": 60, "payment_days": 30,
                "invoice_type": "VAT_SPECIAL_13", "accept_quantified": 1, "amount_wan": 48},
 "contract_C": {"contract_id": "HT-C-003", "prepay_ratio": 35, "warranty_months": 6,
                "penalty_ratio": 2, "delivery_days": 120, "payment_days": 90,
                "invoice_type": "VAT_SPECIAL", "accept_quantified": 0, "amount_wan": 8},
}


def build(name, d):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".pdf")
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFont("Helvetica-Bold", 15)
    c.drawString(60, y, "PURCHASE CONTRACT (electronic form export)")
    y -= 26
    c.setFont("Helvetica", 10)
    c.drawString(60, y, "Page 1/2  |  contract_id: %s" % d["contract_id"])
    y -= 30
    c.setFont("Helvetica", 10)
    for k in ("prepay_ratio", "warranty_months", "penalty_ratio", "delivery_days"):
        label = "warranty_month" if (name == "contract_C" and k == "warranty_months") else k
        c.drawString(70, y, "%s: %s" % (label, d[k]))
        y -= 16
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(70, y, "Clause 3.2 Payment terms apply. (body text omitted)")
    c.showPage()

    c.setFont("Helvetica", 10)
    c.drawString(60, h - 70, "Page 2/2  |  contract_id: %s" % d["contract_id"])
    y = h - 100
    keys = ("payment_days", "invoice_type", "accept_quantified", "amount_wan")
    if name == "contract_C":
        pass
    for k in keys:
        c.drawString(70, y, "%s: %s" % (k, d[k]))
        y -= 16
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(70, y, "Acceptance: quality per national standard, no quantified metrics.")
    c.save()
    return path


def main():
    for n, d in TRUTH.items():
        print("[OK]", build(n, d))
    print("[OK] 生成 3 份电子合同 PDF：", OUT)


if __name__ == "__main__":
    main()
