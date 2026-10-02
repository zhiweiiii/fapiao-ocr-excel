import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

class PaddleOCRModelManager(ThreadPoolExecutor):

    def __init__(self, current_app, **kwargs):
        # 增加线程池大小并设置线程名称
        super(PaddleOCRModelManager, self).__init__(max_workers=1, thread_name_prefix="paddle_ocr_", **kwargs)
        os.environ["PADDLE_PDX_CACHE_HOME"] = "./module"
        self.logger = current_app.logger
        self.logger.info("初始化PaddleOCR模型管理器...")
        try:
            # 延迟导入：paddleocr 依赖体积巨大（需要 paddlepaddle），
            # 放在这里而不是模块顶层，这样在未安装 paddleocr 的环境下
            # 仍可以 import 本模块（以及依赖它的 main.py）用于跑纯逻辑单元测试
            from paddleocr import PaddleOCR
            self.paddleocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                textline_orientation_model_dir="./module/PP-LCNet_x1_0_textline_ori_infer",
                text_detection_model_dir="./module/PP-OCRv5_server_det",
                text_recognition_model_dir="./module/PP-OCRv5_server_rec"
            )
            self.logger.info("PaddleOCR模型初始化成功")
        except Exception as e:
            self.logger.error(f"PaddleOCR模型初始化失败: {str(e)}")
            raise
        self.app = current_app
        self.active_tasks = 0
    
    def submit_ocr(self, **kwargs):
        self.active_tasks += 1
        self.logger.info(f"提交OCR任务，当前活跃任务数: {self.active_tasks}")
        try:
            # 添加超时参数，防止单个任务阻塞过长时间
            future = self.submit(self.infer, **kwargs)
            result = future.result(timeout=600)  # 设置10分钟超时
            return result
        except TimeoutError:
            self.logger.error(f"OCR任务执行超时")
            raise TimeoutError("OCR处理超时，请检查输入图像质量和服务器负载")
        except Exception as e:
            self.logger.error(f"OCR任务执行异常: {str(e)}")
            raise
        finally:
            self.active_tasks -= 1
            self.logger.info(f"OCR任务完成，当前活跃任务数: {self.active_tasks}")

    def run_exclusive(self, fn, *args):
        # pdfium 不是线程安全的，PaddleOCR 渲染 PDF 时也在本线程池里用它，
        # 读取 PDF 文本层等操作也放到这个单线程池里串行执行
        return self.submit(fn, *args).result(timeout=600)

    def infer(self, **kwargs):
        start_time = time.time()
        input_path = kwargs.get('input', '')
        self.logger.info(f"开始OCR推理，输入: {input_path}")
        try:
            result_str = self.paddleocr.predict(**kwargs)
            processing_time = time.time() - start_time
            self.logger.info(f"OCR推理完成，处理时间: {processing_time:.2f}秒")
            result = self.print_order_no(result_str)
            self.logger.info(f"OCR推理结果: {result}")
            return result, result_str
        except Exception as e:
            self.logger.error(f"OCR推理异常: {str(e)}")
            raise

    def print_order_no(self, result):
        res_str = ""
        try:
            for res in result:
                rec_boxes = res["rec_boxes"]
                rec_texts = res["rec_texts"]
                now_line = 0
                line = 0
                i = 0
                for rec_boxe in rec_boxes:
                    line = int(rec_boxe[3] - rec_boxe[1]) * 0.95
                    if int(rec_boxe[1]) - now_line >= line:
                        # 换行
                        res_str = res_str + "\n"+rec_texts[i]
                    else:
                        #不换行
                        res_str = res_str + " "+rec_texts[i]
                    now_line = int(rec_boxe[1])
                    i = i+1
                res_str = res_str + "-----------\n"
            self.logger.info(f"OCR结果处理完成，识别文本数: {sum(len(res['rec_texts']) for res in result)}")
            return res_str
        except Exception as e:
            self.logger.error(f"OCR结果处理异常: {str(e)}")
            raise

