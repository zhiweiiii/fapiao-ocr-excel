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
    """
    批量生成发票Excel，主表和子表分别保存在同一个Excel文件的两个sheet中，字段自动收集，表头为中文
    :param data_list: list of dict，每个dict为结构化发票信息
    :param output_path: 输出文件路径
    :return: 输出文件路径
    """


    # key到中文的映射
    main_field_map = {
        "invoice_number": "发票号码",
        "invoice_date": "开票日期",
        "buyer_name": "购买方名称",
        "buyer_tax_id": "购买方税号",
        "seller_name": "销售方名称",
        "seller_tax_id": "销售方税号",
        "total_amount": "合计金额",
        "total_tax": "合计税额",
        "total_with_tax_cn": "价税合计（大写）",
        "total_with_tax_num": "价税合计（小写）",
        "remark": "备注",
        "issuer": "开票人"
    }
    detail_field_map = {
        "product_name": "货物或应税劳务名称",
        "specification": "规格型号",
        "unit": "单位",
        "quantity": "数量",
        "unit_price": "单价",
        "amount": "金额",
        "tax_rate": "税率",
        "tax_amount": "税额"
    }

    if output_path is None:
        output_path = f"发票批量导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # 自动收集主表字段
    main_fields = []
    for data in data_list:
        for k in data.keys():
            if k != 'items' and k not in main_fields:
                main_fields.append(k)
    # 中文表头
    main_columns = ['发票序号'] + [main_field_map.get(k, k) for k in main_fields]

    # 自动收集明细表字段
    detail_fields = []
    for data in data_list:
        for item in data.get('items', []):
            for k in item.keys():
                if k not in detail_fields:
                    detail_fields.append(k)
    detail_columns = ['发票序号'] + [detail_field_map.get(k, k) for k in detail_fields]

    # 主表数据
    main_table_rows = []
    # 子表数据
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
def extract_invoice_info(result_all):
    import numpy as np
    import re

    # 关键词与字段的映射
    KEYWORDS = {
        "invoice_number": ["发票号码"],
        "invoice_date": ["开票日期"],
        "buyer_name": ["购买方信息", "名称"],
        "buyer_tax_id": ["统一社会信用代码", "纳税人识别号"],
        "seller_name": ["销售方信息", "名称"],
        "seller_tax_id": ["统一社会信用代码", "纳税人识别号"],
        "total_amount": ["合", "金额"],
        "total_tax": ["计", "税额"],
        "total_with_tax_cn": ["价税合计", "大写"],
        "total_with_tax_num": ["小写"],
        "remark": ["备注"],
        "issuer": ["开票人"]
    }

    # 位置区间
    FIELD_POS = {
        "invoice_number": {"x": (70, 95), "y": (3, 12)},
        "invoice_date": {"x": (70, 95), "y": (10, 18)},
        "buyer_name": {"x": (5, 35), "y": (22, 32)},
        "buyer_tax_id": {"x": (5, 35), "y": (30, 38)},
        "seller_name": {"x": (60, 95), "y": (30, 38)},
        "seller_tax_id": {"x": (60, 95), "y": (35, 45)},
        "item_header": {"x": (5, 25), "y": (38, 48)},
        "item_row": {"x": (5, 95), "y": (45, 65)},
        "total_amount": {"x": (5, 35), "y": (80, 88)},
        "total_tax": {"x": (5, 35), "y": (80, 88)},
        "total_with_tax_cn": {"x": (40, 65), "y": (85, 92)},
        "total_with_tax_num": {"x": (70, 95), "y": (85, 92)},
        "remark": {"x": (5, 35), "y": (90, 98)},
        "issuer": {"x": (70, 95), "y": (95, 100)},
    }

    def get_percent(box, min_x, min_y, width, height):
        x0, y0, x1, y1 = box
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        return (cx - min_x) / width * 100, (cy - min_y) / height * 100

    def find_nearest_text(idx, texts, boxes, direction='right', max_dist=300):
        x0, y0, x1, y1 = boxes[idx]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        candidates = []
        for i, b in enumerate(boxes):
            if i == idx:
                continue
            tx0, ty0, tx1, ty1 = b
            tcx, tcy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
            if direction == 'right' and tcx > cx and abs(tcy - cy) < 30:
                dist = tcx - cx
                if dist < max_dist:
                    candidates.append((dist, i))
            elif direction == 'below' and tcy > cy and abs(tcx - cx) < 100:
                dist = tcy - cy
                if dist < max_dist:
                    candidates.append((dist, i))
        if candidates:
            candidates.sort()
            return texts[candidates[0][1]]
        return ""

    results = []
    for result in result_all:
        texts = result["rec_texts"]
        boxes = result["rec_boxes"]
        min_x, min_y = np.min(boxes, axis=0)[0], np.min(boxes, axis=0)[1]
        max_x, max_y = np.max(boxes, axis=0)[2], np.max(boxes, axis=0)[3]
        width = max_x - min_x
        height = max_y - min_y
        percents = [get_percent(b, min_x, min_y, width, height) for b in boxes]

        invoice_info = {}

        # 先用关键词查找
        for field, keywords in KEYWORDS.items():
            found = False
            for i, txt in enumerate(texts):
                if any(kw in txt for kw in keywords):
                    # 右侧或下方查找
                    value = find_nearest_text(i, texts, boxes, 'right')
                    if not value:
                        value = find_nearest_text(i, texts, boxes, 'below')
                    invoice_info[field] = re.sub(r".*?[:：]", "", value).strip() if value else ""
                    found = True
                    break
            if not found:
                # 用位置区间归类
                pos = FIELD_POS.get(field)
                if pos:
                    for j, (x, y) in enumerate(percents):
                        if pos["x"][0] <= x <= pos["x"][1] and pos["y"][0] <= y <= pos["y"][1]:
                            invoice_info[field] = re.sub(r".*?[:：]", "", texts[j]).strip()
                            break

        # 明细表
        item_header_idx = None
        for i, (x, y) in enumerate(percents):
            if FIELD_POS["item_header"]["x"][0] <= x <= FIELD_POS["item_header"]["x"][1] and \
               FIELD_POS["item_header"]["y"][0] <= y <= FIELD_POS["item_header"]["y"][1]:
                if "项目名称" in texts[i]:
                    item_header_idx = i
                    break
        items = []
        if item_header_idx is not None:
            header_fields = re.split(r'[\s,，\*]+', texts[item_header_idx])
            key_map = {
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
            for i, (x, y) in enumerate(percents):
                if FIELD_POS["item_row"]["x"][0] <= x <= FIELD_POS["item_row"]["x"][1] and \
                   FIELD_POS["item_row"]["y"][0] <= y <= FIELD_POS["item_row"]["y"][1]:
                    line = texts[i]
                    if any(x in line for x in ["合计", "价税合计", "备注", "开票人"]):
                        continue
                    cells = re.split(r'[\s,，\*]+', line)
                    if len(cells) < len(header_fields):
                        cells += [''] * (len(header_fields) - len(cells))
                    item = {}
                    for j, col in enumerate(header_fields):
                        k = key_map.get(col, col)
                        item[k] = cells[j] if j < len(cells) else ""
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
