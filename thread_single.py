from paddleocr import PaddleOCR
import os


from concurrent.futures import ThreadPoolExecutor


class PaddleOCRModelManager(ThreadPoolExecutor):

    def __init__(self,current_app, **kwargs):
        super(PaddleOCRModelManager, self).__init__(max_workers= 1,thread_name_prefix="test_",**kwargs)
        os.environ["PADDLE_PDX_CACHE_HOME"] = "./module"
        # os.environ["PADDLE_PDX_LOCAL_FONT_FILE_PATH"] = "./module/simfang.ttf"
        # os.environ["FLAGS_allocator_strategy"] = "naive_best_fit"
        # os.environ["FLAGS_eager_delete_tensor_gb"] = "0"
        self.paddleocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            textline_orientation_model_dir= "./module/PP-LCNet_x1_0_textline_ori_infer",
            text_detection_model_dir="./module/PP-OCRv5_server_det",
            text_recognition_model_dir="./module/PP-OCRv5_server_rec"
        )
        self.app = current_app
    def submit_ocr(self, **kwargs):
        result =self.submit(self.infer, **kwargs)
        self.app.logger.info('识别结果：',str(result))
        return result.result()

    def infer(self, **kwargs):
        result = self.paddleocr.predict(**kwargs)
        result = self.print_order_no(result)
        return result

    def print_order_no(self,result):
        res_str = ""
        for res in result:
            rec_boxes=res["rec_boxes"]
            rec_texts=res["rec_texts"]
            now_line = 0
            line = 0
            i = 0
            for rec_boxe  in rec_boxes:
                line = int(rec_boxe[3] - rec_boxe[1]) * 0.95
                if int(rec_boxe[1]) - now_line >= line:
                    # 换行
                    res_str = res_str + "\n"+rec_texts[i]
                else:
                    #不换行
                    res_str = res_str + " "+rec_texts[i]
                now_line = int(rec_boxe[1])
                i=i+1
            res_str = res_str + "-----------\n"
        self.app.logger.info(res_str)
        return res_str

