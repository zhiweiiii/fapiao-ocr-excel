import logging
import socket
import threading
import time
import webbrowser
from datetime import datetime

from flask import Flask, request, render_template, send_file, jsonify
import io
import tempfile
import os
import uuid
import numpy as np
import re
import pandas as pd

from thread_single import PaddleOCRModelManager

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# paddle 导入时会调高 root logger 的级别，这里显式设置，保证本模块的 INFO 日志能输出
logger.setLevel(logging.INFO)
app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# 允许上传的文件扩展名
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.pdf'}

# 延迟初始化的 PaddleOCR 管理器：避免在模块导入时就要求安装 paddleocr，
# 也避免在非 `python main.py` 直接启动（如 WSGI）场景下 paddleocr 未初始化就被引用
paddleocr = None

def get_ocr_manager():
    global paddleocr
    if paddleocr is None:
        paddleocr = PaddleOCRModelManager(app)
    return paddleocr

# 配置socket超时
socket.setdefaulttimeout(600)  # 设置默认socket超时为10分钟

# 添加请求处理时间记录的中间件
@app.before_request
def before_request():
    request.start_time = time.time()
    app.logger.info(f"收到请求: {request.path} 来源: {request.remote_addr}")

@app.after_request
def after_request(response):
    processing_time = time.time() - request.start_time
    app.logger.info(f"处理请求: {request.path} 状态码: {response.status_code} 耗时: {processing_time:.2f}秒")
    return response

# 添加全局异常处理
@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, socket.timeout):
        app.logger.error(f"连接超时: {str(e)} 来源: {request.remote_addr}")
    elif isinstance(e, ConnectionResetError):
        app.logger.warning(f"连接被重置: {str(e)} 来源: {request.remote_addr}")
    else:
        app.logger.exception(f"处理请求时发生异常 来源: {request.remote_addr}")
    return jsonify({"error": "服务器内部错误"}), 500

# 限制最大请求大小
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64MB

# 超时检测装饰器
def timeout_check(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        processing_time = time.time() - start_time
        if processing_time > 600:  # 如果处理时间超过10分钟，记录警告
            app.logger.warning(f"请求 {request.path} 处理时间过长: {processing_time:.2f}秒 来源: {request.remote_addr}")
        return result
    wrapper.__name__ = func.__name__
    return wrapper

def allowed_file(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    return ext in ALLOWED_EXTENSIONS


# 定义路由和视图函数
@app.route('/fapiao/ocr', methods=['GET'])
@timeout_check
def ocr():
    app.logger.info("开始")
    ### 使用url
    img_url = request.values.get('img_url')
    if img_url is None:
        filelist = request.files.getlist('img_file')
        if not filelist:
            return jsonify({"error": "未上传文件"}), 400
        results = []
        for file in filelist:
            if not allowed_file(file.filename):
                return jsonify({"error": f"不支持的文件类型: {file.filename}"}), 400
            app.logger.info('文件处理'+file.filename)
            # 创建临时文件（自动删除）
            with tempfile.NamedTemporaryFile(delete=True, suffix=os.path.splitext(file.filename)[1] ) as temp_file:
                # 保存上传的文件到临时文件
                file.save(temp_file.name)
                result, _ = get_ocr_manager().submit_ocr(input=temp_file.name)
                results.append(result)
        return "\n".join(results)
    else:
        # 文件处理逻辑...
        app.logger.info(img_url)
        result, _ = get_ocr_manager().submit_ocr(input=img_url)
        return result

# 导出供外部复用的Excel字段映射
MAIN_FIELD_MAP = {
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
DETAIL_FIELD_MAP = {
    "product_name": "项目名称",
    "specification": "规格型号",
    "unit": "单位",
    "quantity": "数量",
    "unit_price": "单价",
    "amount": "金额",
    "tax_rate": "税率/征收率",
    "tax_amount": "税额"
}

def create_invoices_with_pandas(data_list, output_path=None):
    # 复用模块级映射，避免测试重复维护
    main_field_map = MAIN_FIELD_MAP
    detail_field_map = DETAIL_FIELD_MAP

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
        logger.error(f"创建Excel文件时出错: {e}")
        raise
    return output_path

# 提供给外部复用的字段映射常量（原先在 extract_invoice_info 内部）
KEYWORDS = {
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

# clean_value 用到的字段名前缀清洗规则：只需在模块加载时构造一次，
# 避免每次调用（每个OCR文本单元格都会调用一次）都重新拼接/编译正则，带来不必要的开销
_SYMBOL_CHARS = r'¥￥\(\)（）\[\]\{\}\s:：;；\-_,，.。/\\'
_FIELD_WORDS = [
    "发票号码", "开票日期", "购买方名称", "购买方统一社会信用代码", "购买方纳税人识别号",
    "统一社会信用代码", "纳税人识别号", "销售方名称", "销售方统一社会信用代码", "销售方纳税人识别号",
    "合计金额", "合计税额", "价税合计", "大写", "小写", "金额", "税额", "税率/征收率", "税率",
    "项目名称", "规格型号", "单位", "数量", "单价", "备注", "开票人",
    "电子发票（普通发票）", "电子发票普通发票", "电子发票", "普通发票", "国家税务总局"
]


def _build_field_parts(field_words):
    field_parts = []
    for w in field_words:
        field_parts.append(w)
        field_parts.extend(list(w))
        for i in range(2, min(5, len(w))):
            field_parts.append(w[:i])
    return list(set(field_parts))


_PREFIX_PATTERN = re.compile(
    r'^([' + _SYMBOL_CHARS + r']*)'
    r'(' + '|'.join(map(re.escape, _build_field_parts(_FIELD_WORDS))) + r')*'
    r'([' + _SYMBOL_CHARS + r']*)'
)
_LEADING_SYMBOLS_PATTERN = re.compile(r'^[' + _SYMBOL_CHARS + r']+')


def clean_value(val):
    # 多次去除前缀（字段名、常见符号）
    while True:
        new_val = _PREFIX_PATTERN.sub('', val)
        if new_val == val:
            break
        val = new_val
    # 最后再去除一次所有前缀符号（防止只剩符号的情况）
    val = _LEADING_SYMBOLS_PATTERN.sub('', val)
    val = val.strip()
    return val

def extract_invoice_info(result_all):
    # 使用模块级常量 KEYWORDS 和 ITEM_KEY_MAP（原本在函数内定义）
    global KEYWORDS, ITEM_KEY_MAP
    INVOICE_TYPE_CANDIDATES = [
        "增值税专用发票", "增值税普通发票", "电子普通发票", "增值税电子普通发票", "机动车销售统一发票"
    ]

    def group_lines(texts, boxes, y_thresh=15):
        """按照 thread_single.py 的思路重构分行逻辑：基于行高判断换行"""
        # 1. 按y坐标排序
        cy_list = [((b[1] + b[3]) / 2) for b in boxes]
        idx_sorted = np.argsort(cy_list)
        
        lines = []
        line_boxes = []
        
        if len(idx_sorted) == 0:
            return lines, line_boxes
            
        # 2. 计算行高作为换行阈值：使用中位数而非平均数，
        # 因为发票上常见竖排的分区标签（如“购买方信息”）等极高/极窄的文本框，
        # 平均数会被这类离群值拉高，导致阈值过大、把本应分开的多行错误合并成一行
        heights = [b[3] - b[1] for b in boxes]
        line_height_ref = np.median(heights) if heights else 15
        line_height_threshold = line_height_ref * 0.95  # 使用95%行高作为换行阈值
        
        # 3. 按y坐标分组
        current_line = []
        current_boxes = []
        current_y = cy_list[idx_sorted[0]]
        
        for idx in idx_sorted:
            y_center = cy_list[idx]
            
            # 判断是否换行：y坐标差大于行高阈值
            if abs(y_center - current_y) > line_height_threshold:
                # 换行，保存当前行
                if current_line:
                    # 按x坐标排序当前行
                    x_sorted = np.argsort([((b[0] + b[2]) / 2) for b in current_boxes])
                    lines.append([current_line[i] for i in x_sorted])
                    line_boxes.append([current_boxes[i] for i in x_sorted])
                
                # 开始新行
                current_line = [texts[idx]]
                current_boxes = [boxes[idx]]
                current_y = y_center
            else:
                # 同一行，添加到当前行
                current_line.append(texts[idx])
                current_boxes.append(boxes[idx])
        
        # 处理最后一行
        if current_line:
            x_sorted = np.argsort([((b[0] + b[2]) / 2) for b in current_boxes])
            lines.append([current_line[i] for i in x_sorted])
            line_boxes.append([current_boxes[i] for i in x_sorted])
        
        return lines, line_boxes

    results = []
    for result in result_all:
        texts = result["rec_texts"]
        boxes = result["rec_boxes"]
        lines, line_boxes = group_lines(texts, boxes)

        invoice_info = {}

        # --- 合计金额兼容拆字，排除价税合计 ---
        total_amount_line_idx = -1
        total_amount_y = -1
        total_amount_value = ""
        for i, line in enumerate(lines):
            line_str = "".join(line)
            # 跳过包含“价税合计”“大写”“小写”的行
            if any(x in line_str for x in ["价税合计", "大写", "小写"]):
                continue
            if "合计" in line_str or "合 计" in line_str or re.search(r"合\s*计", line_str):
                y_center = np.mean([b[1] + (b[3] - b[1]) / 2 for b in line_boxes[i]])
                if y_center > total_amount_y:
                    total_amount_y = y_center
                    total_amount_line_idx = i

        if total_amount_line_idx != -1:
            line = lines[total_amount_line_idx]
            idx = -1
            for j in range(len(line) - 1):
                if (line[j] == "合" and line[j + 1] == "计") or \
                   (line[j] == "合" and re.match(r"\s*", line[j + 1]) and j + 2 < len(line) and line[j + 2] == "计"):
                    idx = j + 1 if line[j + 1] == "计" else j + 2
                    break
            if idx == -1:
                for j, t in enumerate(line):
                    if "合计" in t:
                        idx = j
                        break
            if idx != -1 and idx + 1 < len(line):
                total_amount_value = clean_value(line[idx + 1])
            elif len(line) > 1:
                total_amount_value = clean_value(line[-1])
            else:
                total_amount_value = ""
            invoice_info["total_amount"] = total_amount_value

        # --- 合计税额 ---
        total_tax_value = ""
        if total_amount_line_idx != -1:
            line = lines[total_amount_line_idx]
            line_box = line_boxes[total_amount_line_idx]
            # 找到“合计”或“合 计”后的位置
            idx = -1
            for j in range(len(line) - 1):
                if (line[j] == "合" and line[j + 1] == "计") or \
                   (line[j] == "合" and re.match(r"\s*", line[j + 1]) and j + 2 < len(line) and line[j + 2] == "计"):
                    idx = j + 1 if line[j + 1] == "计" else j + 2
                    break
            if idx == -1:
                for j, t in enumerate(line):
                    if "合计" in t:
                        idx = j
                        break
            # 合计金额右侧的字段即为合计税额
            if idx != -1 and idx + 2 < len(line):
                total_tax_value = clean_value(line[idx + 2])
            elif idx != -1 and idx + 1 < len(line):
                total_tax_value = clean_value(line[-1])
            invoice_info["total_tax"] = total_tax_value

        # 发票类型识别：优先取第一行正中间偏左文本，遍历匹配候选类型
        invoice_type = ""
        if lines:
            first_line = lines[0]
            n = len(first_line)
            candidates = []
            # 优先取正中间偏左和正中间
            if n >= 2:
                candidates.append(first_line[n // 2 - 1])
            if n >= 1:
                candidates.append(first_line[n // 2])
            # 再遍历整行
            candidates += first_line
            found = False
            for text in candidates:
                candidate = text.replace(" ", "").replace("（", "(").replace("）", ")")
                for t in INVOICE_TYPE_CANDIDATES:
                    if t in candidate:
                        invoice_type = t
                        found = True
                        break
                if found:
                    break
            if not invoice_type and candidates:
                invoice_type = candidates[0]
        invoice_info["invoice_type"] = invoice_type

         # --- 价税合计（小写）兼容处理 ---
        total_with_tax_num = ""
        total_with_tax_cn_idx = -1
        for i, line in enumerate(lines):
            line_str = "".join(line)
            if "价税合计" in line_str and "大写" in line_str:
                total_with_tax_cn_idx = i
                break
        if total_with_tax_cn_idx != -1:
            line = lines[total_with_tax_cn_idx]
            idx = -1
            for j, t in enumerate(line):
                if "价税合计" in t and "大写" in t:
                    idx = j
                    break
            # 取右侧的（小写）或金额
            if idx != -1:
                # 查找右侧第一个带“小写”或金额特征的文本
                for k in range(idx + 1, len(line)):
                    if "小写" in line[k] or re.search(r"[¥￥]\s*\d", line[k]):
                        total_with_tax_num = clean_value(line[k])
                        break
                # 如果没找到，兜底取最后一个
                if not total_with_tax_num and len(line) > idx + 1:
                    total_with_tax_num = clean_value(line[-1])
        invoice_info["total_with_tax_num"] = total_with_tax_num

        
        item_header = None
        item_header_idx = None
        for i, line in enumerate(lines):
            line_str = " ".join(line)
            # 记录本行已被某个字段消费掉的文本框下标：购买方/销售方常常同行出现
            # （如“名称：买方公司”与“名称：卖方公司”在同一行），二者共用通用关键词
            # “名称”，如果不排除已消费的下标，后处理的字段会重新匹配到已经用过的
            # 文本框，导致购买方和销售方的取值互相覆盖成同一个值
            used_token_idx = set()
            for field, kws in KEYWORDS.items():
                # 如果已经有合计金额，后续不再覆盖
                if field in invoice_info:
                    continue
                for kw in kws:
                    if kw not in line_str:
                        continue
                    idx = next((j for j, t in enumerate(line) if kw in t and j not in used_token_idx), None)
                    if idx is None:
                        continue
                    # 合计金额特殊处理：只取“合计”或“合计金额”同一行的下一个文本
                    if field == "total_amount":
                        if idx + 1 < len(line):
                            value = clean_value(line[idx + 1])
                        else:
                            # 如果没有下一个，取该行最后一个文本
                            value = clean_value(line[-1])
                    else:
                        # 多数字段的标签与值是同一个文本框（如“开票日期：2024年07月04日”、
                        # “名称：杭州xxx公司”），优先用匹配到的文本框自身去掉标签后的值；
                        # 只有当该文本框去掉标签后为空（说明标签和值确实是分开的文本框，
                        # 例如“合”“计”分开识别）时，才去取行内下一个文本框
                        value_in_place = clean_value(line[idx])
                        if value_in_place:
                            value = value_in_place
                        elif idx + 1 < len(line):
                            value = clean_value(line[idx + 1])
                        else:
                            value = clean_value(line_str.replace(kw, "").strip())
                    invoice_info[field] = value
                    used_token_idx.add(idx)
                    break
            if not item_header and any(h in line_str for h in ITEM_KEY_MAP.keys()):
                item_header = line
                item_header_idx = i

        items = []
        if item_header:
            # 1. 计算每一列的x中心
            header_boxes = line_boxes[item_header_idx]
            col_centers = [((b[0] + b[2]) / 2) for b in header_boxes]
            header_fields = [ITEM_KEY_MAP.get(h, h) for h in item_header]
            header_len = len(header_fields)
            for line, boxes in zip(lines[item_header_idx + 1:], line_boxes[item_header_idx + 1:]):
                # 跳过合计、价税合计、备注、开票人等行；这里必须用无分隔符拼接，
                # 否则当“合”“计”被识别成两个独立文本框时，带空格拼接会破坏
                # “合计”这个子串匹配，导致合计行混入商品明细表
                line_str = "".join(line)
                if any(x in line_str for x in ["合计", "价税合计", "备注", "开票人"]):
                    continue
                # 2. 按x坐标将每个cell归入最近的表头
                row_cells = [''] * header_len
                for cell, box in zip(line, boxes):
                    cell_center = (box[0] + box[2]) / 2
                    col_idx = np.argmin([abs(cell_center - c) for c in col_centers])
                    # 若该列已有内容，合并（防止误归并）
                    if row_cells[col_idx]:
                        row_cells[col_idx] += " " + cell
                    else:
                        row_cells[col_idx] = cell

                # === 新增：数量和单价拆分 ===
                try:
                    idx_quantity = header_fields.index("quantity")
                    idx_unit_price = header_fields.index("unit_price")
                    val = row_cells[idx_quantity]
                    # 匹配“数字 空格 数字/小数”或“数字\t数字”
                    m = re.match(r'^\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$', val)
                    if m:
                        row_cells[idx_quantity] = m.group(1)
                        row_cells[idx_unit_price] = m.group(2)
                except Exception:
                    pass
                try:
                    idx_quantity = header_fields.index("quantity")
                    idx_unit_price = header_fields.index("unit_price")
                    val = row_cells[idx_unit_price]
                    # 匹配“数字 空格 数字/小数”或“数字\t数字”
                    m = re.match(r'^\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$', val)
                    if m:
                        row_cells[idx_quantity] = m.group(1)
                        row_cells[idx_unit_price] = m.group(2)
                except Exception:
                    pass

                # 3. 构造 item，字段名与表头一一对应；过滤全空行
                item_values = [clean_value(row_cells[j]) for j in range(header_len)]
                if all(v == '' for v in item_values):
                    continue
                item = {header_fields[j]: item_values[j] for j in range(header_len)}
                items.append(item)
        invoice_info["items"] = items
        results.append(invoice_info)
    return results
@app.route('/fapiao/ocr_excel', methods=['POST'])
@timeout_check
def ocr_excel():
    app.logger.info("开始")
    filelist = request.files.getlist('img_file')
    if not filelist:
        return jsonify({"error": "未上传文件"}), 400
    for file in filelist:
        if not allowed_file(file.filename):
            return jsonify({"error": f"不支持的文件类型: {file.filename}"}), 400

    path = "ocr_img_file" + str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix=path) as dir_name:
        app.logger.info(f"临时目录: {dir_name}")
        for file in filelist:
            filename = os.path.basename(file.filename)
            file_path = os.path.join(dir_name, filename)
            file.save(file_path)
        _, result_all = get_ocr_manager().submit_ocr(input=dir_name)
        ocr_fp_list = extract_invoice_info(result_all)
        app.logger.info(f"提取到 {len(ocr_fp_list)} 张发票信息")

    # 直接在内存中生成 Excel（文件只有几十KB），不落临时文件：
    # Windows 下 send_file 发送期间文件被占用，请求结束时无法删除，会在 %TEMP% 里越积越多
    excel_buffer = io.BytesIO()
    create_invoices_with_pandas(ocr_fp_list, output_path=excel_buffer)
    excel_buffer.seek(0)

    return send_file(
        excel_buffer,
        as_attachment=True,
        download_name=f"发票_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



@app.route('/fapiao', methods=['GET'])
def fapiao():
    return render_template('fapiao.html')



def _open_browser_when_ready(url, port, timeout=60):
    # 等服务真正开始监听端口后再打开浏览器，避免浏览器先打开看到“无法访问”
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.5)
    logger.warning(f"服务在 {timeout} 秒内未就绪，请手动在浏览器打开 {url}")


# 启动应用
if __name__ == '__main__':
    get_ocr_manager()  # 启动时预热模型，首个请求无需等待初始化
    # HOST 默认 0.0.0.0 供 Docker 部署使用；桌面版启动器会设为 127.0.0.1，
    # 只允许本机访问，也避免 Windows 防火墙弹窗
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 80))
    if os.environ.get("OPEN_BROWSER") == "1":
        url = f"http://127.0.0.1:{port}/fapiao"
        logger.info(f"服务启动后将自动打开浏览器: {url}")
        threading.Thread(target=_open_browser_when_ready, args=(url, port), daemon=True).start()
    app.run(host=host, port=port)
