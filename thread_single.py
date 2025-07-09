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
            use_textline_orientation=False,
            text_detection_model_dir="./module/PP-OCRv5_server_det",
            text_recognition_model_dir="./module/PP-OCRv5_server_rec"
        )
        self.app = current_app
    def submit_ocr(self, **kwargs):
        return self.submit(self.infer, **kwargs).result()

    def infer(self, **kwargs):
        result=self.paddleocr.predict(**kwargs)
        self.print_order_no(result)
        return result

    def print_order_no(self,result):
        for res in result:
            rec_boxes=res["rec_boxes"]
            rec_texts=res["rec_texts"]
            now_line = 0
            line = 0
            i = 0
            for rec_boxe  in rec_boxes:
                if int(rec_boxe[1]) - now_line >= line-20:
                    line = int(rec_boxe[3] - rec_boxe[1])
                    # 换行
                    print("\n"+rec_texts[i],end="")
                    now_line = int(rec_boxe[1])
                else:
                    #不换行
                    print("     "+rec_texts[i], end="")
                i=i+1
            print("-----------\n")

            # order_exist = False
            # for text in res['rec_texts']:
            #     if "订单号" in text or "流水" in text or "小票号" in text or "单据号" in text or "No." in text or "订单编号" in text:
            #         self.app.logger.info(text)
            #         order_exist=True
            # if not order_exist:
            #     self.app.logger.info(res['rec_texts'])

            self.app.logger.info("-------------------")

