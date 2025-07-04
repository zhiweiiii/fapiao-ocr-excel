import logging
import os
import time

import numpy
from PIL import Image
from paddleocr import PaddleOCR

from flask import Flask, request, make_response,abort
import cv2
import json
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# 创建Flask应用实例
app = Flask(__name__)

logging.getLogger().setLevel(logging.DEBUG)
# logging.getLogger('werkzeug').disabled = True

os.environ["PADDLE_PDX_CACHE_HOME"] = "./module"
os.environ["PADDLE_PDX_LOCAL_FONT_FILE_PATH"] = "./module/simfang.ttf"

paddleocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    text_detection_model_dir = "./module/PP-OCRv5_server_det",
    text_recognition_model_dir = "./module/PP-OCRv5_server_rec")

# limiter = Limiter(
#     app=app,
#     key_func=get_remote_address,
#     default_limits=["300 per day", "50 per hour"])

def file_storage_to_ndarray(file_storage):
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    if img.mode in ('P', 'L'):
        img = img.convert('RGB')  # 统一维度为H×W×3
    return numpy.array(img)  # 自动生成dtype=uint8

def print_order_no(result):
    for res in result:
        order_exist = False
        for text in res['rec_texts']:
            if "订单号" in text or "流水" in text:
                logging.info(text)
                order_exist=True
        if not order_exist:
            logging.info(res['rec_texts'])
        logging.info("-------------------")

# class DisableLoggingFilter(logging.Filter):
#     def filter(self, record):
#         if request.path == '/a/nanny/getdatav2.php':
#             return False
#         return True

# @app.before_request
# def add_logging_filter():
#     app.logger.addFilter(DisableLoggingFilter())
#
# @app.route("/a/nanny/getdatav2.php")
# @limiter.limit("0 per day")
# def slow():
#     return ""

# 定义路由和视图函数
@app.route('/ocr', methods=['GET'])
def ocr():
    logging.info("开始")
    ### 使用url
    img_url = request.values.get('img_url')
    if img_url is None:
        filelist =request.files.getlist('img_file')
        for file in filelist:
            logging.info(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            result = paddleocr.predict(input=file_storage_to_ndarray(file))
            print_order_no(result)
    else:
        logging.info(img_url)
        result = paddleocr.predict(input=img_url)
        print_order_no(result)
    return json.dumps({"text": result[0]['rec_texts'], "poly": [i.tolist() for i in result[0]['rec_polys']]}, indent=4,
                      ensure_ascii=False)


# 启动应用
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80)
