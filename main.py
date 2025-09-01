import logging

import numpy
from PIL import Image

from flask import Flask, request, render_template, send_file
import json
import tempfile
import os
import uuid

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


from datetime import datetime
def create_invoices_with_pandas(data_list, output_path=None):
    """
    批量生成发票Excel，主表和子表分别保存在同一个Excel文件的两个sheet中，子表sheet包含字段名
    :param data_list: list of dict，每个dict为结构化发票信息
    :param output_path: 输出文件路径
    :return: 输出文件路径
    """
    import pandas as pd
    from datetime import datetime

    if output_path is None:
        output_path = f"发票批量导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # 主表数据
    main_table_rows = []
    # 子表数据
    detail_table_rows = []

    for idx, data in enumerate(data_list):
        # 主表
        main_row = {
            '发票序号': idx + 1,
            '发票号码': data.get('invoice_number', ''),
            '开票日期': data.get('invoice_date', ''),
            '购买方名称': data.get('buyer_name', ''),
            '购买方税号': data.get('buyer_tax_id', ''),
            '销售方名称': data.get('seller_name', ''),
            '销售方税号': data.get('seller_tax_id', '')
        }
        main_table_rows.append(main_row)

        # 子表
        for item in data.get('items', []):
            detail_row = {
                '发票序号': idx + 1,
                '货物或应税劳务名称': item.get('product_name', ''),
                '规格型号': item.get('specification', ''),
                '单位': item.get('unit', ''),
                '数量': item.get('quantity', ''),
                '单价': item.get('unit_price', ''),
                '金额': item.get('金额', ''),
                '税率': item.get('tax_rate', ''),
                '税额': item.get('税额', '')
            }
            detail_table_rows.append(detail_row)

    # DataFrame
    main_df = pd.DataFrame(main_table_rows)
    detail_df = pd.DataFrame(detail_table_rows, columns=[
        '发票序号', '货物或应税劳务名称', '规格型号', '单位', '数量', '单价', '金额', '税率', '税额'
    ])

    # 写入同一个Excel文件的两个sheet，均带字段名
    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            main_df.to_excel(writer, sheet_name='发票主表', index=False)
            detail_df.to_excel(writer, sheet_name='发票明细', index=False)
    except Exception as e:
        print(f"创建Excel文件时出错: {e}")
        raise
    return output_path

def extract_invoice_info(texts, boxes):
    """
    从OCR结果（文本和对应box）中提取结构化发票信息，兼容多种布局和字段变化。
    参数:
        texts: list[str]
        boxes: list[list]
    返回:
        dict，包含发票结构化信息
    """
    import re

    def find_near_text(keyword, prefer_right=True, prefer_below=False):
        """寻找与关键字最近的文本，支持左右/上下优先"""
        indices = [i for i, t in enumerate(texts) if keyword in t]
        if not indices:
            return None, None
        idx = indices[0]
        x0, y0, x1, y1 = boxes[idx]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

        min_dist, min_idx = float('inf'), None
        for i, (t, b) in enumerate(zip(texts, boxes)):
            if i == idx or not t.strip() or t == keyword:
                continue
            tx0, ty0, tx1, ty1 = b
            tcx, tcy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
            dx, dy = tcx - cx, tcy - cy
            # 优先右侧或下方
            if prefer_right and dx < 0:
                continue
            if prefer_below and dy < 0:
                continue
            dist = (dx ** 2 + dy ** 2) ** 0.5
            if dist < min_dist:
                min_dist, min_idx = dist, i
        return texts[min_idx] if min_idx is not None else None, min_idx

    invoice_info = {}

    # 1. 发票号码
    invoice_number = None
    for t in texts:
        m = re.search(r'发票号码[:：]?\s*([0-9A-Za-z]+)', t)
        if m:
            invoice_number = m.group(1)
            break
    if not invoice_number:
        # 容错: 只找包含20位数字的字符串
        for t in texts:
            m = re.match(r'\d{20}', t)
            if m:
                invoice_number = m.group(0)
                break
    invoice_info['invoice_number'] = invoice_number or ""

    # 2. 开票日期
    invoice_date = ""
    for t in texts:
        m = re.search(r'开票日期[:：]?\s*([0-9]{8})', t)
        if m:
            invoice_date = m.group(1)
            break
        m = re.search(r'开票日期[:：]?\s*([0-9\-年月日]+)', t)
        if m:
            invoice_date = m.group(1)
            break
    invoice_info['invoice_date'] = invoice_date

    # 3. 购买方/销售方名称、税号（信用代码）
    buyer_name, buyer_tax_id = "", ""
    seller_name, seller_tax_id = "", ""
    # 找到"购买方信息"和"销售方信息"的索引
    buyer_idx = next((i for i, t in enumerate(texts) if '购买方' in t), None)
    seller_idx = next((i for i, t in enumerate(texts) if '销售方' in t), None)

    # 搜索购买方信息区域
    if buyer_idx is not None:
        for i in range(buyer_idx, min(buyer_idx + 5, len(texts))):
            if '名称' in texts[i]:
                name, _ = find_near_text('名称', prefer_right=True)
                if name: buyer_name = name
            if '纳税人识别号' in texts[i] or '统一社会信用代码' in texts[i]:
                s = texts[i]
                match = re.search(r'([0-9A-Za-z]{8,})', s)
                if match: buyer_tax_id = match.group(1)
    # 搜索销售方信息区域
    if seller_idx is not None:
        for i in range(seller_idx, min(seller_idx + 5, len(texts))):
            if '名称' in texts[i]:
                name, _ = find_near_text('名称', prefer_right=True)
                if name: seller_name = name
            if '纳税人识别号' in texts[i] or '统一社会信用代码' in texts[i]:
                s = texts[i]
                match = re.search(r'([0-9A-Za-z]{8,})', s)
                if match: seller_tax_id = match.group(1)
    # 容错: 全局找
    if not buyer_name:
        for t in texts:
            if re.match(r'^[\u4e00-\u9fa5A-Za-z0-9（）()]+$', t) and 2 < len(t) < 30 and ('公司' in t or '店' in t):
                buyer_name = t
                break
    if not seller_name:
        for t in texts[::-1]:
            if re.match(r'^[\u4e00-\u9fa5A-Za-z0-9（）()]+$', t) and 2 < len(t) < 30 and ('公司' in t or '店' in t):
                seller_name = t
                break

    invoice_info['buyer_name'] = buyer_name
    invoice_info['buyer_tax_id'] = buyer_tax_id
    invoice_info['seller_name'] = seller_name
    invoice_info['seller_tax_id'] = seller_tax_id

    # 4. 明细项目提取
    # 动态发现表头行
    head_keywords = ['项目名称', '规格', '单位', '数量', '单价', '金额', '税率', '税额']
    header_row = None
    for i, t in enumerate(texts):
        if sum([kw in t for kw in head_keywords]) >= 4:
            header_row = i
            break
    items = []
    if header_row is not None:
        # 动态确定各列顺序
        header_text = texts[header_row]
        columns = []
        for kw in head_keywords:
            if kw in header_text:
                columns.append(kw)
        # 明细行区间
        for i in range(header_row+1, len(texts)):
            line = texts[i]
            if any(x in line for x in ['合计', '价税合计', '备注', '开票人']):
                break
            # 提取数字或内容
            # 可根据常见分隔符优化
            cells = re.split(r'[\s,，\*]+', line)
            # 容错: 数量足够才解析
            if len(cells) >= len(columns):
                item = {}
                for j, col in enumerate(columns):
                    val = cells[j] if j < len(cells) else ""
                    # 标准化key
                    key_map = {
                        '项目名称': 'product_name',
                        '规格型号': 'specification',
                        '规格': 'specification',
                        '单位': 'unit',
                        '数量': 'quantity',
                        '单价': 'unit_price',
                        '金额': '金额',
                        '税率': 'tax_rate',
                        '税额': '税额'
                    }
                    item[key_map.get(col, col)] = val
                items.append(item)
    invoice_info['items'] = items

    return invoice_info

# 定义路由和视图函数
@app.route('/ocr_excel', methods=['POST'])
def ocr_excel():
    app.logger.info("开始")
    filelist = request.files.getlist('img_file')
    ocr_fp_list = []
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
        ocr_fp_list.append(extract_invoice_info(result_all["rec_texts"],result_all["rec_boxes"]))
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
