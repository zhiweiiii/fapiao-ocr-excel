import logging

import numpy
from PIL import Image

from flask import Flask, request, render_template, send_file
import json
import tempfile
import os

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
                result = paddleocr.submit_ocr(input=temp_file.name)
        return result
    else:
        # 文件处理逻辑...
        app.logger.info(img_url)
        result = paddleocr.submit_ocr(input=img_url)
    return result


import pandas as pd
from datetime import datetime


def create_invoice_with_pandas(data, output_path=None):
    """使用pandas创建发票"""
    if output_path is None:
        output_path = f"发票_pandas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # 创建商品明细DataFrame
    items_df = pd.DataFrame(data['items'])
    items_df['序号'] = range(1, len(items_df) + 1)
    # items_df['金额'] = items_df['quantity'] * items_df['unit_price']
    # items_df['税额'] = items_df['金额'] * items_df['tax_rate']

    # 重新排列列顺序
    items_df = items_df[['序号', 'product_name', 'specification', 'unit',
                         'quantity', 'unit_price', '金额', 'tax_rate', '税额']]

    # 重命名列
    items_df.columns = ['序号', '货物或应税劳务名称', '规格型号', '单位',
                        '数量', '单价', '金额', '税率', '税额']

    # 创建Excel写入器
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # 写入商品明细
        items_df.to_excel(writer, sheet_name='发票明细', index=False, startrow=10)

        # 获取工作表进行格式设置
        workbook = writer.book
        worksheet = writer.sheets['发票明细']

        # 添加发票头信息
        worksheet['A1'] = '增值税专用发票'
        worksheet['A3'] = f"发票代码: {data['invoice_code']}"
        worksheet['C3'] = f"发票号码: {data['invoice_number']}"
        worksheet['A4'] = f"购买方: {data['buyer_name']}"
        worksheet['C4'] = f"纳税人识别号: {data['buyer_tax_id']}"
        worksheet['A5'] = f"销售方: {data['seller_name']}"
        worksheet['C5'] = f"纳税人识别号: {data['seller_tax_id']}"

    return output_path

# 定义路由和视图函数
@app.route('/ocr_excel', methods=['GET'])
def ocr_excel():
    app.logger.info("开始")
    ### 使用url
    result = ''
    filelist = request.files.getlist('img_file')
    for file in filelist:
        app.logger.info('文件处理'+file.filename)
        # result = paddleocr.submit_ocr(input=file_storage_to_ndarray(file))
        # 创建临时文件（自动删除）
        with tempfile.NamedTemporaryFile(delete=True, suffix=os.path.splitext(file.filename)[1] ) as temp_file:
            # 保存上传的文件到临时文件
            file.save(temp_file.name)
            result = paddleocr.submit_ocr(input=temp_file.name)
            data = {"items":[{'product_name':"1", 'specification':"2", 'unit':"3",
                         'quantity':"4", 'unit_price':"5", '金额':"6", 'tax_rate':"7", '税额':"8"}],
                    "'invoice_number":"2423","buyer_name":"323","buyer_tax_id":"54534",
                    "seller_name":"35456","seller_tax_id":"3434"
                    }
            temp_path =create_invoice_with_pandas(data)

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
