"""发票识别准确率评估：逐字段对比真值，输出每个用例和汇总的准确率。

用例来源：
  - data/*.pdf + 同名 .json（真实发票）
  - tests/eval/synthetic/*.pdf + 同名 .json（按真实版式生成的合成发票）
  - 由部分合成发票渲染出的扫描图、模拟手机拍照图、旋转 90° 图（仅 auto/ocr 模式）

用法：
  python -m tests.eval.eval_accuracy                 # 与线上一致：PDF 优先读文本层，其余走 OCR
  python -m tests.eval.eval_accuracy --source ocr    # 全部强制走 OCR
  python -m tests.eval.eval_accuracy --source text   # 只评估 PDF 文本层（不需要 OCR 模型，几秒跑完）
"""
import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402
import pdf_text  # noqa: E402

IMAGE_VARIANT_CASES = ["A_单行明细", "B_三行明细含规格单位"]


def _render(pdf_path, scale):
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return pdf[0].render(scale=scale).to_pil().convert("RGB")
    finally:
        pdf.close()


def _photo_like(img):
    img = img.rotate(3, expand=True, fillcolor=(205, 205, 200))
    img = img.filter(ImageFilter.GaussianBlur(1.0))
    canvas = Image.new("RGB", (img.width + 120, img.height + 120), (190, 190, 185))
    canvas.paste(img, (60, 60))
    return canvas


def collect_cases(with_images, workdir):
    cases = []
    for pdf in sorted((ROOT / "data").glob("*.pdf")) + sorted((ROOT / "tests" / "eval" / "synthetic").glob("*.pdf")):
        truth = pdf.with_suffix(".json")
        if truth.exists():
            cases.append((f"{pdf.stem} [PDF]", pdf, truth))
    if with_images:
        synthetic = ROOT / "tests" / "eval" / "synthetic"
        for stem in IMAGE_VARIANT_CASES:
            pdf, truth = synthetic / f"{stem}.pdf", synthetic / f"{stem}.json"
            scan = workdir / f"{stem}_scan.png"
            _render(pdf, 200 / 72).save(scan)
            photo = workdir / f"{stem}_photo.jpg"
            _photo_like(_render(pdf, 2)).save(photo, quality=55)
            cases += [(f"{stem} [扫描PNG]", scan, truth), (f"{stem} [拍照JPG]", photo, truth)]
        rot = workdir / "A_rot90.png"
        _render(synthetic / "A_单行明细.pdf", 2).rotate(90, expand=True).save(rot)
        cases.append(("A_单行明细 [旋转90°]", rot, synthetic / "A_单行明细.json"))
    return cases


def read_pages(path, source):
    if source == "text":
        return pdf_text.extract_pages(str(path)) or []
    if source == "ocr":
        return main.get_ocr_manager().submit_ocr(input=str(path))[1]
    return main.read_invoice_file(str(path))


def score(extracted, truth):
    got = extracted[0] if extracted else {}
    main_keys = [k for k in main.MAIN_FIELD_MAP if k in truth]
    main_bad = [(k, got.get(k, ""), truth[k]) for k in main_keys
                if str(got.get(k, "")).strip() != str(truth[k]).strip()]
    item_bad, got_items = [], got.get("items", [])
    for i, row in enumerate(truth["items"]):
        g = got_items[i] if i < len(got_items) else {}
        item_bad += [(i, k, g.get(k, ""), row[k]) for k in main.DETAIL_FIELD_MAP
                     if str(g.get(k, "")).strip() != str(row[k]).strip()]
    return {
        "main_ok": len(main_keys) - len(main_bad), "main_n": len(main_keys),
        "item_ok": len(truth["items"]) * len(main.DETAIL_FIELD_MAP) - len(item_bad),
        "item_n": len(truth["items"]) * len(main.DETAIL_FIELD_MAP),
        "rows": f"{len(got_items)}/{len(truth['items'])}", "pages": len(extracted),
        "main_bad": main_bad, "item_bad": item_bad,
        "all_correct": not main_bad and not item_bad and len(got_items) == len(truth["items"]),
        "review": got.get("review", ""),
    }


def main_cli():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["auto", "ocr", "text"], default="auto")
    parser.add_argument("--verbose", action="store_true", help="打印每个不匹配的字段")
    parser.add_argument("--report", type=Path, help="把完整结果写入 JSON 文件")
    args = parser.parse_args()
    logging.disable(logging.INFO)

    with tempfile.TemporaryDirectory() as tmp:
        cases = collect_cases(with_images=args.source != "text", workdir=Path(tmp))
        results, totals = [], {"main_ok": 0, "main_n": 0, "item_ok": 0, "item_n": 0}
        for label, path, truth_path in cases:
            truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
            r = score(main.extract_invoice_info(read_pages(path, args.source)), truth)
            r["label"] = label
            results.append(r)
            for k in totals:
                totals[k] += r[k]
            print(f"{label:30s} 主表 {r['main_ok']:2d}/{r['main_n']}  明细 {r['item_ok']:3d}/{r['item_n']:3d}  "
                  f"明细行数 {r['rows']}  复核提示：{r['review'] or '无'}", flush=True)
            if args.verbose:
                for k, g, t in r["main_bad"]:
                    print(f"    主表 {k}: 识别={g!r} 真值={t!r}")
                for i, k, g, t in r["item_bad"]:
                    print(f"    明细[{i}] {k}: 识别={g!r} 真值={t!r}")

    print(f"\n[{args.source}] 合计：主表字段 {totals['main_ok']}/{totals['main_n']} "
          f"= {totals['main_ok'] / totals['main_n']:.1%}，明细字段 {totals['item_ok']}/{totals['item_n']} "
          f"= {totals['item_ok'] / totals['item_n']:.1%}")
    wrong = [r for r in results if not r["all_correct"]]
    right = [r for r in results if r["all_correct"]]
    print(f"复核提示：有错的发票被提示 {sum(bool(r['review']) for r in wrong)}/{len(wrong)}，"
          f"全对的发票被误提示 {sum(bool(r['review']) for r in right)}/{len(right)}")
    if args.report:
        args.report.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return totals


if __name__ == "__main__":
    main_cli()
