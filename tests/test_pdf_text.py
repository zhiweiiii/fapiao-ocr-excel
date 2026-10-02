"""PDF 文本层识别的回归测试：不需要 OCR 模型，几秒内跑完。"""
import json
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402
import pdf_text  # noqa: E402

CASES = sorted((ROOT / "data").glob("*.pdf")) + sorted((ROOT / "tests" / "eval" / "synthetic").glob("*.pdf"))


@pytest.mark.parametrize("pdf", CASES, ids=[p.stem for p in CASES])
def test_text_layer_extraction_matches_truth(pdf):
    truth = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    pages = pdf_text.extract_pages(str(pdf))
    assert pages, "电子发票 PDF 应该能读到文本层"

    info = main.extract_invoice_info(pages)[0]
    for key, expected in truth.items():
        if key != "items":
            assert info.get(key, "") == expected, key
    assert info["items"] == truth["items"]


def test_scanned_pdf_without_text_layer_falls_back(tmp_path):
    src = pdfium.PdfDocument(str(CASES[0]))
    image = src[0].render(scale=2).to_pil().convert("RGB")
    src.close()
    scanned = tmp_path / "scanned.pdf"
    image.save(scanned, "PDF")
    assert pdf_text.extract_pages(str(scanned)) is None


def test_unreadable_pdf_falls_back(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 not really a pdf")
    assert pdf_text.extract_pages(str(broken)) is None
