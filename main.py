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
                result,_ = paddleocr.submit_ocr(input=temp_file.name)
        return result
    else:
        # 文件处理逻辑...
        app.logger.info(img_url)
        result,_ = paddleocr.submit_ocr(input=img_url)
    return result


import pandas as pd
from datetime import datetime


def create_invoice_with_pandas(data, output_path=None):
    """使用pandas创建发票，包含容错处理"""
    if output_path is None:
        output_path = f"发票_pandas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # 确保data是字典类型
    if not isinstance(data, dict):
        data = {}

    # 创建商品明细DataFrame，处理可能的缺失数据
    items_data = data.get('items', [])
    if not isinstance(items_data, list):
        items_data = []

    items_df = pd.DataFrame(items_data)

    # 处理可能缺失的列
    if not items_df.empty:
        items_df['序号'] = range(1, len(items_df) + 1)
        # 添加可能缺失的列
        for col in ['product_name', 'specification', 'unit', 'quantity', 'unit_price', 'tax_rate']:
            if col not in items_df.columns:
                items_df[col] = ''

        # 重新排列列顺序
        items_df = items_df[['序号', 'product_name', 'specification', 'unit',
                             'quantity', 'unit_price', '金额', 'tax_rate', '税额']]

        # 重命名列
        items_df.columns = ['序号', '货物或应税劳务名称', '规格型号', '单位',
                            '数量', '单价', '金额', '税率', '税额']
    else:
        # 创建空的DataFrame
        items_df = pd.DataFrame(columns=['序号', '货物或应税劳务名称', '规格型号', '单位',
                                         '数量', '单价', '金额', '税率', '税额'])

    # 创建Excel写入器
    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 写入商品明细
            items_df.to_excel(writer, sheet_name='发票明细', index=False, startrow=10)

            # 获取工作表进行格式设置
            workbook = writer.book
            worksheet = writer.sheets['发票明细']

            # 添加发票头信息，使用get方法提供默认值
            worksheet['A1'] = '增值税专用发票'
            worksheet['A3'] = f"发票代码: {data.get('invoice_code', '')}"
            worksheet['C3'] = f"发票号码: {data.get('invoice_number', '')}"
            worksheet['A4'] = f"购买方: {data.get('buyer_name', '')}"
            worksheet['C4'] = f"纳税人识别号: {data.get('buyer_tax_id', '')}"
            worksheet['A5'] = f"销售方: {data.get('seller_name', '')}"
            worksheet['C5'] = f"纳税人识别号: {data.get('seller_tax_id', '')}"

    except Exception as e:
        # 处理文件写入错误
        print(f"创建Excel文件时出错: {e}")
        # 可以选择重新抛出异常或返回错误信息
        raise

    return output_path


def extract_invoice_info(texts,boxes) -> dict[str, any]:
    """
    从OCR数据中提取发票结构化信息
    参数:
        df: 包含OCR数据的DataFrame
    返回:
        结构化发票信息字典
    """ 
    # = {"items":[{'product_name':"1", 'specification':"2", 'unit':"3",
    #              'quantity':"4", 'unit_price':"5", '金额':"6", 'tax_rate':"7", '税额':"8"}],
    #         "'invoice_number":"2423","buyer_name":"323","buyer_tax_id":"54534",
    #         "seller_name":"35456","seller_tax_id":"3434"
    #         }
    invoice_info = {}
    # 提取发票号码
    invoice_no_texts = texts[texts.str.contains('发票号码')]['text'].values
    if len(invoice_no_texts) > 0:
        invoice_info['发票号码'] = invoice_no_texts[0].split('：')[-1] if '：' in invoice_no_texts[0] else \
        invoice_no_texts[0]

    # 提取开票日期
    date_texts = texts[texts.str.contains('开票日期')]['text'].values
    if len(date_texts) > 0:
        invoice_info['开票日期'] = date_texts[0].split('：')[-1] if '：' in date_texts[0] else date_texts[0]

    # 提取购买方名称
    buyer_name_texts = texts[(texts.str.contains('名称：')) & (~texts.str.contains('销售方'))]
    if len(buyer_name_texts) > 0:
        # 假设购买方名称在"名称："后面
        name_idx = buyer_name_texts.index[0]
        # 查找可能的下一个文本块作为名称
        next_texts = texts[(texts['center_y'] > buyer_name_texts.loc[name_idx, 'center_y'] - 20) &
                        (texts['center_y'] < buyer_name_texts.loc[name_idx, 'center_y'] + 20) &
                        (texts['center_x'] > buyer_name_texts.loc[name_idx, 'center_x'])]
        if len(next_texts) > 0:
            invoice_info['购买方名称'] = next_texts.iloc[0]['text']

    # 提取销售方名称
    seller_name_texts = texts[texts.str.contains('销售方信息')]
    if len(seller_name_texts) > 0:
        seller_idx = seller_name_texts.index[0]
        # 在销售方信息下面查找名称
        name_texts = texts[(texts['center_y'] > seller_name_texts.loc[seller_idx, 'center_y']) &
                        (texts.str.contains('名称：'))]
        if len(name_texts) > 0:
            name_idx = name_texts.index[0]
            next_texts = texts[(texts['center_y'] > name_texts.loc[name_idx, 'center_y'] - 20) &
                            (texts['center_y'] < name_texts.loc[name_idx, 'center_y'] + 20) &
                            (texts['center_x'] > name_texts.loc[name_idx, 'center_x'])]
            if len(next_texts) > 0:
                invoice_info['销售方名称'] = next_texts.iloc[0]['text']

    # 提取金额信息
    amount_texts = texts[texts.str.contains('价税合计')]
    if len(amount_texts) > 0:
        amount_idx = amount_texts.index[0]
        # 查找金额数值
        amount_value_texts = texts[(texts['center_y'] > amount_texts.loc[amount_idx, 'center_y']) &
                                (texts.str.contains('￥'))]
        if len(amount_value_texts) > 0:
            invoice_info['价税合计'] = amount_value_texts.iloc[0]['text']

    return invoice_info


# 定义路由和视图函数
@app.route('/ocr_excel', methods=['POST'])
def ocr_excel():
    app.logger.info("开始")
    ### 使用url
    result = ''
    filelist = request.files.getlist('img_file')
    for file in filelist:
        app.logger.info('文件处理'+file.filename)
        # result = paddleocr.submit_ocr(input=file_storage_to_ndarray(file))
        # 创建临时文件（自动删除）
        with (tempfile.NamedTemporaryFile(delete=True, suffix=os.path.splitext(file.filename)[1] ) as temp_file):
            # 保存上传的文件到临时文件
            file.save(temp_file.name)
            result,result_all = paddleocr.submit_ocr(input=temp_file.name)
            data= extract_invoice_info(result_all[0]["rec_texts"],result_all[0]["rec_boxes"]) 
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
