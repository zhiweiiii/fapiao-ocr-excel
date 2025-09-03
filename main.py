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
    import pandas as pd
    from datetime import datetime

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

def extract_invoice_info(result_all):
    import numpy as np
    import re

    # 字段关键词映射
    KEYWORDS = {
        "invoice_type": ["发票类型", "增值税专用发票", "增值税普通发票", "电子普通发票"],
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
        item_header = None
        item_header_idx = None
        # 主表字段识别
        for i, line in enumerate(lines):
            line_str = " ".join(line)
            for field, kws in KEYWORDS.items():
                if field in invoice_info:
                    continue
                for kw in kws:
                    if kw in line_str:
                        idx = next((j for j, t in enumerate(line) if kw in t), None)
                        if idx is not None and idx + 1 < len(line):
                            value = line[idx + 1]
                        else:
                            value = line_str.replace(kw, "").strip()
                        invoice_info[field] = re.sub(r".*?[:：]", "", value).strip()
            if not item_header and any(h in line_str for h in ITEM_KEY_MAP.keys()):
                item_header = line
                item_header_idx = i

        # 明细表内容识别
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
