"""针对 extract_invoice_info 的轻量回归测试。

与 test_ocr_compare.py 不同，本文件不依赖真实安装的 paddleocr / 模型权重，
而是复用一份预先跑好的真实 OCR 输出（tests/fixtures/dianpiao1_ocr_dump.json，
来自 data/电票1.pdf），这样在没有 GPU/paddleocr 的环境（比如 CI）也能快速跑，
同时仍然是基于真实发票版式的数据，而不是凭空构造的合成数据。
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_ocr_dump(name):
    data = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    return [{
        "rec_texts": data["texts"],
        "rec_boxes": [np.array(b) for b in data["boxes"]],
    }]


def test_extract_invoice_info_main_fields():
    result_all = _load_ocr_dump("dianpiao1_ocr_dump.json")
    truth = json.loads((ROOT / "data" / "电票1.json").read_text(encoding="utf-8"))

    extracted = main.extract_invoice_info(result_all)
    assert len(extracted) == 1
    info = extracted[0]

    for key, expected in truth.items():
        if key == "items":
            continue
        assert str(info.get(key, "")).strip() == str(expected).strip(), (
            f"字段 {key} 不匹配: got={info.get(key)!r} expected={expected!r}"
        )


def test_extract_invoice_info_items_core_fields():
    result_all = _load_ocr_dump("dianpiao1_ocr_dump.json")
    truth = json.loads((ROOT / "data" / "电票1.json").read_text(encoding="utf-8"))

    extracted = main.extract_invoice_info(result_all)
    items = extracted[0]["items"]
    truth_items = truth["items"]
    assert len(items) == len(truth_items)

    # OCR 把数量"1"和单价"0.0183486238532"识别成了一串"10.0183486238532"，
    # 需要靠"数量×单价≈金额"拆开
    for got, expected_row in zip(items, truth_items):
        for key, expected in expected_row.items():
            assert str(got.get(key, "")).strip() == str(expected).strip(), (
                f"明细字段 {key} 不匹配: got={got.get(key)!r} expected={expected!r}"
            )


def test_extract_invoice_info_no_total_row_leak_into_items():
    """回归用例：合计行（“合”“计”被识别成两个独立文本框）不应混入商品明细。"""
    result_all = _load_ocr_dump("dianpiao1_ocr_dump.json")
    extracted = main.extract_invoice_info(result_all)
    items = extracted[0]["items"]
    assert len(items) == 1
