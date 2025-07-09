import logging

import numpy
from PIL import Image

from flask import Flask, request
import json

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
            result = paddleocr.submit_ocr(input=file_storage_to_ndarray(file))
        return result
    else:
        app.logger.info(img_url)
        result = paddleocr.submit_ocr(input=img_url)
    return json.dumps({"text": result[0]['rec_texts'], "poly": [i.tolist() for i in result[0]['rec_polys']]}, indent=4,
                      ensure_ascii=False)


# 启动应用
if __name__ == '__main__':
    paddleocr = PaddleOCRModelManager(app)
    app.logger.setLevel(logging.INFO)
    app.run(host="0.0.0.0", port=80)
