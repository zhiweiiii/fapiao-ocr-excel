import logging

import numpy
from PIL import Image

from flask import Flask, request, render_template, send_file
import json
import tempfile
import os
import uuid
import numpy as np
import re
import pandas as pd
from datetime import datetime

from thread_single import PaddleOCRModelManager

logging.getLogger('werkzeug').disabled = True
app = Flask(__name__)


def file_storage_to_ndarray(file_storage):
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    if img.mode in ('P', 'L'):
        img = img.convert('BGR')  # 统一维度为H×W×3
    return numpy.array(img)  # 自动生成dtype=uint8


# 定义路由和视图函数
@app.route('/ocr', methods=['GET'])
def ocr():
    app.logger.info("开始")
    ### 使用url
    img_url = request.values.get('img_url')
    result = ''
    if img_url is None:
        filelist = request.files.getlist('img_file')
        for file in filelist:
            app.logger.info('文件处理'+file.filename)
            # result = paddleocr.submit_ocr(input=file_storage_to_ndarray(file))
            # 创建临时文件（自动删除）
            with tempfile.NamedTemporaryFile(delete=True, suffix=os.path.splitext(file.filename)[1] ) as temp_file:
                # 保存上传的文件到临时文件
                file.save(temp_file.name)
                result,_ = paddleocr.submit_ocr(input=temp_file.name)
        return result
    else:
        # 文件处理逻辑...
        app.logger.info(img_url)
        result,_ = paddleocr.submit_ocr(input=img_url)
    return result

def create_invoices_with_pandas(data_list, output_path=None):
   

    main_field_map = {
        "invoice_type": "发票类型",
        "invoice_number": "发票号码",
        "invoice_date": "开票日期",
        "buyer_name": "购买方名称",
        "buyer_tax_id": "购买方统一社会信用代码/纳税人识别号",
        "seller_name": "销售方名称",
        "seller_tax_id": "销售方统一社会信用代码/纳税人识别号",
        "total_amount": "合计金额",
        "total_tax": "合计税额",
        "total_with_tax_cn": "价税合计（大写）",
        "total_with_tax_num": "价税合计（小写）",
        "remark": "备注",
        "issuer": "开票人"
    }
    # 明细表字段映射，按你的要求补全
    detail_field_map = {
        "product_name": "项目名称",
        "specification": "规格型号",
        "unit": "单位",
        "quantity": "数量",
        "unit_price": "单价",
        "amount": "金额",
        "tax_rate": "税率/征收率",
        "tax_amount": "税额"
    }

    if output_path is None:
        output_path = f"发票批量导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    main_fields = list(main_field_map.keys())
    for data in data_list:
        for k in data.keys():
            if k != 'items' and k not in main_fields:
                main_fields.append(k)
    main_columns = ['发票序号'] + [main_field_map.get(k, k) for k in main_fields]

    # 明细表字段按顺序补全
    detail_fields = list(detail_field_map.keys())
    for data in data_list:
        for item in data.get('items', []):
            for k in item.keys():
                if k not in detail_fields:
                    detail_fields.append(k)
    detail_columns = ['发票序号'] + [detail_field_map.get(k, k) for k in detail_fields]

    main_table_rows = []
    detail_table_rows = []

    for idx, data in enumerate(data_list):
        main_row = {'发票序号': idx + 1}
        for k in main_fields:
            main_row[main_field_map.get(k, k)] = data.get(k, '')
        main_table_rows.append(main_row)

        for item in data.get('items', []):
            detail_row = {'发票序号': idx + 1}
            for k in detail_fields:
                detail_row[detail_field_map.get(k, k)] = item.get(k, '')
            detail_table_rows.append(detail_row)

    main_df = pd.DataFrame(main_table_rows, columns=main_columns)
    detail_df = pd.DataFrame(detail_table_rows, columns=detail_columns)

    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            main_df.to_excel(writer, sheet_name='发票主表', index=False)
            detail_df.to_excel(writer, sheet_name='发票明细', index=False)
    except Exception as e:
        print(f"创建Excel文件时出错: {e}")
        raise
    return output_path

def clean_value(val):
    # 所有常见字段名及其单字、部分、拆分形式
    field_words = [
        "发票号码", "开票日期", "购买方名称", "购买方统一社会信用代码", "购买方纳税人识别号",
        "统一社会信用代码", "纳税人识别号", "销售方名称", "销售方统一社会信用代码", "销售方纳税人识别号",
        "合计金额", "合计税额", "价税合计", "大写", "小写", "金额", "税额", "税率/征收率", "税率",
        "项目名称", "规格型号", "单位", "数量", "单价", "备注", "开票人"
    ]
    # 拆分为单字和部分
    field_parts = []
    for w in field_words:
        field_parts.append(w)
        field_parts.extend(list(w))
        # 也加上前2~4字的部分匹配
        for i in range(2, min(5, len(w))):
            field_parts.append(w[:i])
    # 去重
    field_parts = list(set(field_parts))
    # 构造正则，允许前面有各种符号、空格、括号、冒号、分号等
    prefix_pattern = r'^([¥￥\(\)（）\[\]\{\}\s:：;；\-_,，.。/\\]*)(' + '|'.join(map(re.escape, field_parts)) + r')+([¥￥\(\)（）\[\]\{\}\s:：;；\-_,，.。/\\]*)'
    # 多次去除前缀
    while True:
        new_val = re.sub(prefix_pattern, '', val)
        if new_val == val:
            break
        val = new_val
    val = val.strip()
    return val

def extract_invoice_info(result_all):
    KEYWORDS = {
        "invoice_number": ["发票号码"],
        "invoice_date": ["开票日期"],
        "buyer_name": ["购买方名称", "名称"],
        "buyer_tax_id": ["购买方统一社会信用代码", "购买方纳税人识别号", "统一社会信用代码", "纳税人识别号"],
        "seller_name": ["销售方名称", "名称"],
        "seller_tax_id": ["销售方统一社会信用代码", "销售方纳税人识别号", "统一社会信用代码", "纳税人识别号"],
        "total_amount": ["合计金额"],
        "total_tax": ["合计税额"],
        "total_with_tax_cn": ["价税合计", "大写"],
        "total_with_tax_num": ["价税合计", "小写"],
        "remark": ["备注"],
        "issuer": ["开票人"]
    }
    ITEM_KEY_MAP = {
        "项目名称": "product_name",
        "规格型号": "specification",
        "单位": "unit",
        "数量": "quantity",
        "单价": "unit_price",
        "金额": "amount",
        "税率": "tax_rate",
        "税率/征收率": "tax_rate",
        "税额": "tax_amount"
    }
    INVOICE_TYPE_CANDIDATES = [
        "增值税专用发票", "增值税普通发票", "电子普通发票", "增值税电子普通发票", "机动车销售统一发票"
    ]

    def group_lines(texts, boxes, y_thresh=15):
        lines = []
        line_boxes = []
        cy_list = [((b[1] + b[3]) / 2) for b in boxes]
        idx_sorted = np.argsort(cy_list)
        used = set()
        for idx in idx_sorted:
            if idx in used:
                continue
            cur_y = cy_list[idx]
            cur_line = [texts[idx]]
            cur_boxes = [boxes[idx]]
            used.add(idx)
            for j in idx_sorted:
                if j in used:
                    continue
                if abs(cy_list[j] - cur_y) < y_thresh:
                    cur_line.append(texts[j])
                    cur_boxes.append(boxes[j])
                    used.add(j)
            x_sorted = np.argsort([((b[0] + b[2]) / 2) for b in cur_boxes])
            lines.append([cur_line[i] for i in x_sorted])
            line_boxes.append([cur_boxes[i] for i in x_sorted])
        y_sorted = np.argsort([np.mean([b[1] for b in line[1]]) for line in zip(lines, line_boxes)])
        return [lines[i] for i in y_sorted], [line_boxes[i] for i in y_sorted]

    results = []
    for result in result_all:
        texts = result["rec_texts"]
        boxes = result["rec_boxes"]
        lines, line_boxes = group_lines(texts, boxes)

        invoice_info = {}

        # --- 合计金额兼容拆字，排除价税合计 ---
        total_amount_line_idx = -1
        total_amount_y = -1
        total_amount_value = ""
        for i, line in enumerate(lines):
            line_str = "".join(line)
            # 跳过包含“价税合计”“大写”“小写”的行
            if any(x in line_str for x in ["价税合计", "大写", "小写"]):
                continue
            if "合计" in line_str or "合 计" in line_str or re.search(r"合\s*计", line_str):
                y_center = np.mean([b[1] + (b[3] - b[1]) / 2 for b in line_boxes[i]])
                if y_center > total_amount_y:
                    total_amount_y = y_center
                    total_amount_line_idx = i

        if total_amount_line_idx != -1:
            line = lines[total_amount_line_idx]
            idx = -1
            for j in range(len(line) - 1):
                if (line[j] == "合" and line[j + 1] == "计") or \
                   (line[j] == "合" and re.match(r"\s*", line[j + 1]) and j + 2 < len(line) and line[j + 2] == "计"):
                    idx = j + 1 if line[j + 1] == "计" else j + 2
                    break
            if idx == -1:
                for j, t in enumerate(line):
                    if "合计" in t:
                        idx = j
                        break
            if idx != -1 and idx + 1 < len(line):
                total_amount_value = clean_value(line[idx + 1])
            elif len(line) > 1:
                total_amount_value = clean_value(line[-1])
            else:
                total_amount_value = ""
            invoice_info["total_amount"] = total_amount_value

        # --- 合计税额 ---
        total_tax_value = ""
        if total_amount_line_idx != -1:
            line = lines[total_amount_line_idx]
            line_box = line_boxes[total_amount_line_idx]
            # 找到“合计”或“合 计”后的位置
            idx = -1
            for j in range(len(line) - 1):
                if (line[j] == "合" and line[j + 1] == "计") or \
                   (line[j] == "合" and re.match(r"\s*", line[j + 1]) and j + 2 < len(line) and line[j + 2] == "计"):
                    idx = j + 1 if line[j + 1] == "计" : j + 2
                    break
            if idx == -1:
                for j, t in enumerate(line):
                    if "合计" in t:
                        idx = j
                        break
            # 合计金额右侧的字段即为合计税额
            if idx != -1 and idx + 2 < len(line):
                total_tax_value = clean_value(line[idx + 2])
            elif idx != -1 and idx + 1 < len(line):
                total_tax_value = clean_value(line[-1])
            invoice_info["total_tax"] = total_tax_value

        # 发票类型识别：优先取第一行正中间偏左文本，遍历匹配候选类型
        invoice_type = ""
        if lines:
            first_line = lines[0]
            n = len(first_line)
            candidates = []
            # 优先取正中间偏左和正中间
            if n >= 2:
                candidates.append(first_line[n // 2 - 1])
            if n >= 1:
                candidates.append(first_line[n // 2])
            # 再遍历整行
            candidates += first_line
            found = False
            for text in candidates:
                candidate = text.replace(" ", "").replace("（", "(").replace("）", ")")
                for t in INVOICE_TYPE_CANDIDATES:
                    if t in candidate:
                        invoice_type = t
                        found = True
                        break
                if found:
                    break
            if not invoice_type and candidates:
                invoice_type = candidates[0]
        invoice_info["invoice_type"] = invoice_type

         # --- 价税合计（小写）兼容处理 ---
        total_with_tax_num = ""
        total_with_tax_cn_idx = -1
        for i, line in enumerate(lines):
            line_str = "".join(line)
            if "价税合计" in line_str and "大写" in line_str:
                total_with_tax_cn_idx = i
                break
        if total_with_tax_cn_idx != -1:
            line = lines[total_with_tax_cn_idx]
            idx = -1
            for j, t in enumerate(line):
                if "价税合计" in t and "大写" in t:
                    idx = j
                    break
            # 取右侧的（小写）或金额
            if idx != -1:
                # 查找右侧第一个带“小写”或金额特征的文本
                for k in range(idx + 1, len(line)):
                    if "小写" in line[k] or re.search(r"[¥￥]\s*\d", line[k]):
                        total_with_tax_num = clean_value(line[k])
                        break
                # 如果没找到，兜底取最后一个
                if not total_with_tax_num and len(line) > idx + 1:
                    total_with_tax_num = clean_value(line[-1])
        invoice_info["total_with_tax_num"] = total_with_tax_num

        
        item_header = None
        item_header_idx = None
        for i, line in enumerate(lines):
            line_str = " ".join(line)
            line_box = line_boxes[i]
            for field, kws in KEYWORDS.items():
                # 如果已经有合计金额，后续不再覆盖
                if field in invoice_info:
                    continue
                for kw in kws:
                    if kw in line_str:
                        idx = next((j for j, t in enumerate(line) if kw in t), None)
                        # 合计金额特殊处理：只取“合计”或“合计金额”同一行的下一个文本
                        if field == "total_amount":
                            if idx is not None and idx + 1 < len(line):
                                value = clean_value(line[idx + 1])
                            else:
                                # 如果没有下一个，取该行最后一个文本
                                value = clean_value(line[-1])
                        elif field in ["buyer_name", "buyer_tax_id"]:
                            left_idx = np.argmin([b[0] for b in line_box])
                            value = clean_value(line[left_idx])
                        elif idx is not None and idx + 1 < len(line):
                            value = clean_value(line[idx + 1])
                        else:
                            value = clean_value(line_str.replace(kw, "").strip())
                        invoice_info[field] = value
            if not item_header and any(h in line_str for h in ITEM_KEY_MAP.keys()):
                item_header = line
                item_header_idx = i

        items = []
        if item_header:
            header_fields = [ITEM_KEY_MAP.get(h, h) for h in item_header]
            for line in lines[item_header_idx + 1:]:
                line_str = " ".join(line)
                if any(x in line_str for x in ["合计", "价税合计", "备注", "开票人"]):
                    continue
                cells = line + [''] * (len(header_fields) - len(line))
                item = {header_fields[j]: cells[j] for j in range(len(header_fields))}
                items.append(item)
        invoice_info["items"] = items
        results.append(invoice_info)
    return results
# 定义路由和视图函数
@app.route('/ocr_excel', methods=['POST'])
def ocr_excel():
    app.logger.info("开始")
    filelist = request.files.getlist('img_file')
    path ="ocr_img_file"+str(uuid.uuid4())
    with tempfile.TemporaryDirectory( prefix=path) as dir_name:
        print(dir_name)
        for file in filelist:
            filename = os.path.basename(file.filename)
            # 完整的文件路径
            file_path = os.path.join(dir_name, filename)
            # 保存文件
            file.save(file_path)
        result,result_all = paddleocr.submit_ocr(input=dir_name)
        p=[]
        for index, result in enumerate(result_all):
            p.append({"rec_texts":result["rec_texts"], "rec_boxes":result["rec_boxes"]})
        ocr_fp_list=extract_invoice_info(result_all)
        print(ocr_fp_list)
        temp_path = create_invoices_with_pandas(ocr_fp_list)

    return send_file(
        temp_path,
        as_attachment=True,
        download_name=f"发票_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



@app.route('/fapiao', methods=['GET'])
def fapiao():
    return render_template('fapiao.html')



# 启动应用
if __name__ == '__main__':
    paddleocr = PaddleOCRModelManager(app)
    app.logger.setLevel(logging.INFO)
    app.run(host="0.0.0.0", port=80)
