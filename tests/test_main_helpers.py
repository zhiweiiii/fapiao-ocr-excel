"""main.py 中纯逻辑函数 / Flask 路由的单元测试。

这些测试完全不依赖 paddleocr（main.py 已经把 paddleocr 的导入延迟到真正
创建 PaddleOCRModelManager 的时候），因此可以在任何本地环境或 CI 中直接跑：
    pytest tests/test_main_helpers.py
"""
import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_clean_value_strips_field_label_and_symbols():
    assert main.clean_value("发票号码：20882407041644048604") == "20882407041644048604"
    assert main.clean_value("名称：杭州常威商业管理有限公司") == "杭州常威商业管理有限公司"
    assert main.clean_value("¥0.02") == "0.02"
    assert main.clean_value("  ") == ""


def test_clean_value_leaves_plain_value_untouched():
    assert main.clean_value("339901999999142") == "339901999999142"


@pytest.mark.parametrize("text,expected", [
    ("贰分", "0.02"), ("伍仟叁佰元整", "5300"), ("捌仟陆佰捌拾肆元捌角", "8684.8"),
    ("壹佰元零伍分", "100.05"), ("壹拾万零贰佰元整", "100200"), ("拾元整", "10"), ("壹亿贰仟万元整", "120000000"),
])
def test_parse_cn_money(text, expected):
    from decimal import Decimal
    assert main.parse_cn_money(text) == Decimal(expected)


def test_parse_cn_money_rejects_garbage():
    assert main.parse_cn_money("开票人") is None
    assert main.parse_cn_money("") is None


def test_split_merged_qty_price_uses_amount():
    item = {"quantity": "", "unit_price": "10.0183486238532", "amount": "0.02"}
    main.split_merged_qty_price(item)
    assert (item["quantity"], item["unit_price"]) == ("1", "0.0183486238532")


@pytest.mark.parametrize("qty,price,amount", [
    ("", "5000.00", "5000.00"),   # 数量省略，单价等于金额
    ("2", "79.00", "158.00"),     # 数量、单价都有
    ("", "", "-160.00"),          # 折扣行
])
def test_split_merged_qty_price_leaves_normal_rows(qty, price, amount):
    item = {"quantity": qty, "unit_price": price, "amount": amount}
    main.split_merged_qty_price(item)
    assert (item["quantity"], item["unit_price"]) == (qty, price)


def test_split_stacked_cells_only_splits_inside_item_table():
    import numpy as np
    rows = [("*电子产品*鼠标", "8", "632.00"), ("*日用品*垃圾袋", "50", "175.00")]
    texts, boxes = ["项目名称", "金额"], [np.array([30, 300, 160, 320]), np.array([800, 300, 860, 320])]
    for r, (name, qty, amount) in enumerate(rows):
        top = 330 + r * 20
        texts += [name, qty, amount]
        boxes += [np.array([30, top, 190, top + 20]), np.array([560, top, 585, top + 20]),
                  np.array([808, top, 868, top + 20])]
    texts += ["个卷", "备注"]
    boxes += [np.array([400, 330, 420, 370]), np.array([35, 400, 55, 460])]

    out_texts, out_boxes = main.split_stacked_cells(texts, boxes)
    # 明细区域里粘连的"个卷"拆成两行；表格下方竖排的"备注"标签保持不变（OCR 漏识别合计行时也一样）
    assert out_texts[-3:] == ["个", "卷", "备注"]
    assert out_boxes[-3][3] == out_boxes[-2][1] == 350


def _valid_invoice():
    return {
        "invoice_number": "24312000000123456789", "invoice_date": "2024年09月18日",
        "buyer_name": "上海星辰科技有限公司", "buyer_tax_id": "91310115MA1K4ABCD2",
        "seller_name": "北京云帆软件服务有限公司", "seller_tax_id": "91110108MA01XYZW3Q",
        "total_amount": "3000.00", "total_tax": "390.00",
        "total_with_tax_cn": "叁仟叁佰玖拾元整", "total_with_tax_num": "3390.00",
        "items": [
            {"quantity": "2", "unit_price": "1580.00", "amount": "3160.00", "tax_amount": "410.80"},
            {"quantity": "", "unit_price": "", "amount": "-160.00", "tax_amount": "-20.80"},
        ],
    }


def test_validate_invoice_passes_consistent_invoice():
    assert main.validate_invoice(_valid_invoice()) == []


def test_validate_invoice_flags_inconsistencies():
    info = _valid_invoice()
    info["items"][0]["amount"] = "3100.00"           # 明细之和与合计不符，且数量×单价≠金额
    info["total_with_tax_cn"] = "叁仟叁佰玖拾壹元整"  # 大小写不一致
    info["buyer_tax_id"] = "入识别号：91310115"       # 税号格式异常
    problems = main.validate_invoice(info)
    assert any("明细金额之和" in p for p in problems)
    assert "第1行数量×单价≠金额" in problems
    assert "价税合计大小写不一致" in problems
    assert "购买方税号格式异常" in problems


def test_create_invoices_with_pandas_writes_two_sheets(tmp_path):
    data_list = [{
        "invoice_type": "电子发票（普通发票）",
        "invoice_number": "123456",
        "items": [
            {"product_name": "测试商品", "amount": "10.00"},
        ],
    }]
    output_path = tmp_path / "invoices.xlsx"
    result_path = main.create_invoices_with_pandas(data_list, output_path=str(output_path))

    assert os.path.exists(result_path)
    xl = pd.ExcelFile(result_path)
    assert set(xl.sheet_names) == {"发票主表", "发票明细"}

    main_df = xl.parse("发票主表")
    assert str(main_df.loc[0, "发票号码"]) == "123456"

    detail_df = xl.parse("发票明细")
    assert detail_df.loc[0, "项目名称"] == "测试商品"


@pytest.fixture
def client():
    main.app.config["TESTING"] = True
    return main.app.test_client()


def test_fapiao_page_renders(client):
    resp = client.get("/fapiao")
    assert resp.status_code == 200


def test_ocr_excel_rejects_empty_upload(client):
    resp = client.post("/fapiao/ocr_excel", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_ocr_excel_rejects_disallowed_file_type(client):
    data = {"img_file": (io.BytesIO(b"not an image"), "evil.exe")}
    resp = client.post("/fapiao/ocr_excel", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_ocr_excel_success_returns_excel_without_temp_files(client, monkeypatch, tmp_path):
    import json
    import tempfile

    import numpy as np

    dump = json.loads((ROOT / "tests" / "fixtures" / "dianpiao1_ocr_dump.json").read_text(encoding="utf-8"))
    result_all = [{"rec_texts": dump["texts"], "rec_boxes": [np.array(b) for b in dump["boxes"]]}]

    class FakeOCRManager:
        def run_exclusive(self, fn, *args):
            return fn(*args)

        def submit_ocr(self, **kwargs):
            return "", result_all

    monkeypatch.setattr(main, "get_ocr_manager", lambda: FakeOCRManager())
    # 把临时目录指到独立目录，便于检查请求结束后没有残留的 Excel 文件
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    data = {"img_file": (io.BytesIO(b"%PDF-1.4 fake"), "invoice.pdf")}
    resp = client.post("/fapiao/ocr_excel", data=data, content_type="multipart/form-data")

    assert resp.status_code == 200
    main_df = pd.read_excel(io.BytesIO(resp.data), sheet_name="发票主表", dtype=str)
    assert main_df.loc[0, "发票号码"] == "20882407041644048604"
    assert main_df.loc[0, "销售方名称"] == "杭州爱信诺航天信息有限公司(新模式开票)"
    assert list(tmp_path.glob("**/*.xlsx")) == []


def test_ocr_rejects_empty_upload(client):
    resp = client.get("/fapiao/ocr", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.get_json()
