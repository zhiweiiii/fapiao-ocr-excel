"""从电子发票 PDF 的文本层直接读取文字和坐标，代替 OCR。

税务系统生成的电子发票 PDF 自带精确的文本层：直接读取比 OCR 快两个数量级，
不会认错字，也不会把相邻的数量、单价粘成一串。输出与 PaddleOCR 结果同构
（每页一个 {"rec_texts", "rec_boxes"}），可直接交给 extract_invoice_info。
扫描件等没有可用文本层的 PDF 返回 None，由调用方回退到 OCR。

注意：pdfium 不是线程安全的，PaddleOCR 渲染 PDF 时也会用到它，
调用方需保证与 OCR 在同一线程中串行执行。
"""
import math
import re
import unicodedata

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

# 与 PaddleOCR 渲染 PDF 的分辨率保持一致（600pt 宽的发票约渲染为 1200px），
# 这样 extract_invoice_info 里按像素计算的阈值对两种来源都适用
SCALE = 2.0
# 弧形排列的发票监制章文字是逐字旋转的，与正文区分开
MAX_CHAR_ANGLE_DEG = 3
MIN_SEGMENTS = 10
VERTICAL_LABELS = {"购买方信息", "销售方信息", "购买方", "销售方", "购方信息", "销方信息", "备注", "密码区"}
_CJK = r"一-鿿"
# 只处理逐字加空格排版的标签（如"单  位""税  额"），备注等自由文本里的空格要保留
_SPACED_OUT = re.compile(rf"^[{_CJK}](?:\s+[{_CJK}])+$")


def _normalize_char(ch):
    # 部分发票 PDF 用康熙部首等兼容字符（如"⼦"U+2F26）显示汉字，转回标准汉字；
    # 其他字符（如全角括号）保持原样，与人工录入的真值写法一致
    code = ord(ch)
    if 0x2E80 <= code <= 0x2FDF or 0xF900 <= code <= 0xFAFF:
        return unicodedata.normalize("NFKC", ch)
    return ch


def _is_upright(textpage, index):
    angle = math.degrees(pdfium_c.FPDFText_GetCharAngle(textpage.raw, index)) % 360
    return min(angle, 360 - angle) <= MAX_CHAR_ANGLE_DEG


def _page_segments(page):
    """按 PDF 中独立绘制的文字片段切分（pdfium 在片段之间插入"生成的"空格/换行）。"""
    height = page.get_height()
    textpage = page.get_textpage()
    segments, chars, upright = [], [], True

    def flush():
        nonlocal chars, upright
        text = "".join(c for c, _ in chars).strip()
        if text and upright:
            boxes = np.array([b for c, b in chars if not c.isspace()])
            segments.append([text, [boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max()]])
        chars, upright = [], True

    for i in range(textpage.count_chars()):
        ch = chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, i))
        if pdfium_c.FPDFText_IsGenerated(textpage.raw, i) or ch in "\r\n":
            flush()
            continue
        if ch.isspace():
            if chars:
                chars.append((" ", None))
            continue
        left, bottom, right, top = textpage.get_charbox(i)
        box = [left * SCALE, (height - top) * SCALE, right * SCALE, (height - bottom) * SCALE]
        upright = upright and _is_upright(textpage, i)
        chars.append((_normalize_char(ch), box))
    flush()
    return segments


def _merge_vertical_labels(segments):
    """把逐字竖排的标签（如"购/买/方/信/息"、"备/注"）合并成一个文本框，与 OCR 的输出保持一致。

    只合并已知的竖排标签：明细表同一列里逐行排列的单字（如单位"箱/盒/次"）
    在位置上和竖排标签几乎无法区分，不能按几何关系合并。
    """
    singles = sorted((s for s in segments if len(s[0]) == 1 and re.match(rf"[{_CJK}]", s[0])),
                     key=lambda s: s[1][1])
    merged, used = [], set()
    for i in range(len(singles)):
        if i in used:
            continue
        column, last = [i], singles[i][1]
        for j in range(i + 1, len(singles)):
            box = singles[j][1]
            height = last[3] - last[1]
            same_x = abs((box[0] + box[2]) / 2 - (last[0] + last[2]) / 2) < height * 0.5
            close_below = 0 <= box[1] - last[3] < height * 1.5
            if j not in used and same_x and close_below:
                column.append(j)
                last = box
        while column and "".join(singles[k][0] for k in column) not in VERTICAL_LABELS:
            column.pop()
        if len(column) > 1:
            used.update(column)
            boxes = np.array([singles[k][1] for k in column])
            merged.append(["".join(singles[k][0] for k in column),
                           [boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max()]])
    merged_ids = {id(singles[k]) for k in used}
    return [s for s in segments if id(s) not in merged_ids] + merged


def extract_pages(path):
    """返回与 PaddleOCR 结果同构的逐页列表；PDF 没有可用文本层或无法解析时返回 None。"""
    try:
        pdf = pdfium.PdfDocument(path)
    except pdfium.PdfiumError:
        return None
    try:
        pages = []
        for page in pdf:
            segments = _merge_vertical_labels(_page_segments(page))
            texts = [re.sub(r"\s+", "", t) if _SPACED_OUT.match(t) else t for t, _ in segments]
            if len(segments) < MIN_SEGMENTS or "发票" not in "".join(texts):
                return None
            pages.append({"rec_texts": texts, "rec_boxes": [np.array(b) for _, b in segments]})
        return pages or None
    finally:
        pdf.close()
