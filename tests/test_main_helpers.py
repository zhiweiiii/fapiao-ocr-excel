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
