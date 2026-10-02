"""按 data/电票1.pdf 的版式生成带真值的合成发票，用于评估识别准确率。

生成结果已提交在 tests/eval/synthetic/ 下，平时不需要重新生成；
修改用例后重新生成：pip install reportlab && python tests/eval/gen_synthetic.py
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_DIR = Path(__file__).resolve().parents[2] / "module" / "fonts"
pdfmetrics.registerFont(TTFont("FS", str(FONT_DIR / "simfang.ttf")))
pdfmetrics.registerFont(TTFont("PF", str(FONT_DIR / "PingFang-SC-Regular.ttf")))
RED = Color(0.55, 0.05, 0.05)
W, H = 600, 400


def money_upper(v: Decimal) -> str:
    digits = "零壹贰叁肆伍陆柒捌玖"
    units = ["", "拾", "佰", "仟"]
    v = v.quantize(Decimal("0.01"))
    yuan, cents = divmod(int(v * 100), 100)
    out = ""
    if yuan:
        groups, s = [], str(yuan)
        while s:
            groups.insert(0, s[-4:]); s = s[:-4]
        big = ["", "万", "亿"]
        for gi, g in enumerate(groups):
            part, zero = "", False
            for i, ch in enumerate(g.zfill(4)):
                d = int(ch)
                if d == 0:
                    zero = bool(part)
                else:
                    if zero:
                        part += "零"; zero = False
                    part += digits[d] + units[3 - i]
            if part:
                out += part + big[len(groups) - gi - 1]
        out += "元"
    jiao, fen = divmod(cents, 10)
    if not jiao and not fen:
        return out + "整"
    if jiao:
        out += digits[jiao] + "角"
    elif yuan:
        out += "零"
    if fen:
        out += digits[fen] + "分"
    return out


def T(c, x, y, s, size=10.5, color=black, anchor="left", font="FS"):
    """y 为距页面顶部的文字中线位置（pt）。"""
    c.setFillColor(color); c.setFont(font, size)
    base = H - y - size * 0.35
    {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[anchor](x, base, s)


def draw(case, path):
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setStrokeColor(RED); c.setLineWidth(0.8)
    T(c, 290, 35, case["invoice_type"], 18, RED, "center")
    c.line(188, H - 54, 392, H - 54); c.line(188, H - 57, 392, H - 57)
    T(c, 440, 40, "发票号码：", 8.5, RED); T(c, 486, 40, case["invoice_number"], 8.5)
    T(c, 440, 57, "开票日期：", 8.5, RED); T(c, 486, 57, case["invoice_date"], 8.5)

    c.rect(15, H - 355.5, 570, 355.5 - 88.5)
    c.line(15, H - 150, 585, H - 150)
    for x in (33, 301, 319):
        c.line(x, H - 88.5, x, H - 150)
    for i, ch in enumerate("购买方信息"):
        T(c, 24, 98 + i * 11, ch, 8.5, RED, "center")
    for i, ch in enumerate("销售方信息"):
        T(c, 310, 98 + i * 11, ch, 8.5, RED, "center")
    T(c, 35, 107, "名称：", 8.5, RED); T(c, 62, 106, case["buyer_name"], 9)
    T(c, 322, 107, "名称：", 8.5, RED); T(c, 349, 106, case["seller_name"], 9)
    T(c, 35, 134, "统一社会信用代码/纳税人识别号：", 8.5, RED); T(c, 169, 134, case["buyer_tax_id"], 9)
    T(c, 322, 134, "统一社会信用代码/纳税人识别号：", 8.5, RED); T(c, 456, 134, case["seller_tax_id"], 9)

    for x, s in [(65, "项目名称"), (139, "规格型号"), (205, "单  位"), (279, "数  量"), (349, "单  价"),
                 (421, "金  额"), (473, "税率/征收率"), (568, "税  额")]:
        T(c, x, 159, s, 8.5, RED, "center")
    y = 173
    for it in case["items"]:
        name_lines = it.get("_name_lines", [it["product_name"]])
        for li, nl in enumerate(name_lines):
            T(c, 16, y + li * 11, nl, 9)
        T(c, 139, y, it["specification"], 9, anchor="center")
        T(c, 205, y, it["unit"], 9, anchor="center")
        T(c, 291, y, it["quantity"], 9, anchor="right")
        T(c, 361, y, it["unit_price"], 9, anchor="right")
        T(c, 433, y, it["amount"], 9, anchor="right")
        T(c, 475, y, it["tax_rate"], 9, anchor="center")
        T(c, 582, y, it["tax_amount"], 9, anchor="right")
        y += 13 + 11 * (len(name_lines) - 1)

    T(c, 65, 270, "合", 9, RED, "center"); T(c, 110, 270, "计", 9, RED, "center")
    T(c, 433, 271, "¥" + case["total_amount"], 9, anchor="right", font="PF")
    T(c, 582, 271, "¥" + case["total_tax"], 9, anchor="right", font="PF")
    c.line(15, H - 276.5, 585, H - 276.5); c.line(15, H - 298.5, 585, H - 298.5); c.line(162, H - 276.5, 162, H - 298.5)
    T(c, 88, 288, "价税合计（大写）", 8.5, RED, "center")
    c.circle(174, H - 288, 5); c.line(170.5, H - 284.5, 177.5, H - 291.5); c.line(170.5, H - 291.5, 177.5, H - 284.5)
    T(c, 184, 288, case["total_with_tax_cn"], 9)
    T(c, 415, 288, "（小写）", 8.5, RED); T(c, 446, 288, "¥ " + case["total_with_tax_num"], 9, font="PF")
    c.line(33, H - 298.5, 33, H - 355.5)
    T(c, 24, 318, "备", 8.5, RED, "center"); T(c, 24, 335, "注", 8.5, RED, "center")
    if case["remark"]:
        T(c, 40, 312, case["remark"], 9)
    T(c, 58, 374, "开票人：", 8.5, RED); T(c, 93, 374, case["issuer"], 9)
    c.showPage(); c.save()


def item(name, spec, unit, qty, price, rate, wrap_at=None, amount=None):
    if amount is None:
        amount = (Decimal(qty) * Decimal(price)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    amount = Decimal(amount)
    tax = (amount * Decimal(rate.rstrip("%")) / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    d = {"product_name": name, "specification": spec, "unit": unit, "quantity": qty, "unit_price": price,
         "amount": f"{amount}", "tax_rate": rate, "tax_amount": f"{tax}"}
    if wrap_at:
        d["_name_lines"] = [name[:wrap_at], name[wrap_at:]]
    return d


def case(cid, items, invoice_type="电子发票（普通发票）", buyer=("上海星辰科技有限公司", "91310115MA1K4ABCD2"),
         seller=("北京云帆软件服务有限公司", "91110108MA01XYZW3Q"), remark="", number="24312000000123456789",
         date="2024年09月18日", issuer="王芳"):
    amt = sum(Decimal(i["amount"]) for i in items); tax = sum(Decimal(i["tax_amount"]) for i in items)
    return {"id": cid, "invoice_type": invoice_type, "invoice_number": number, "invoice_date": date,
            "buyer_name": buyer[0], "buyer_tax_id": buyer[1], "seller_name": seller[0], "seller_tax_id": seller[1],
            "total_amount": f"{amt:.2f}", "total_tax": f"{tax:.2f}", "total_with_tax_cn": money_upper(amt + tax),
            "total_with_tax_num": f"{amt + tax:.2f}", "remark": remark, "issuer": issuer, "items": items}


CASES = [
    case("A_单行明细", [item("*信息技术服务*软件开发服务", "", "", "1", "5000.00", "6%")]),
    case("B_三行明细含规格单位", [
        item("*纸制品*复印纸", "A4 70g", "箱", "10", "125.00", "13%"),
        item("*办公用品*中性笔", "0.5mm", "盒", "20", "18.50", "13%"),
        item("*现代服务*快递服务", "", "次", "3", "15.00", "6%")],
        number="24312000000987654321", date="2024年10月08日"),
    case("C_品名过长换行", [
        item("*计算机网络设备*千兆以太网交换机（24口带管理功能）", "S5720", "台", "2", "3280.00", "13%", wrap_at=11),
        item("*信息技术服务*运维服务", "", "项", "1", "1200.00", "6%")],
        buyer=("深圳市南山区未来智能制造研究院有限公司", "91440300MA5F8KLM9X")),
    case("D_专票长名称有备注", [item("*运输服务*国内道路货物运输服务", "", "吨", "35", "260.00", "9%")],
         invoice_type="电子发票（增值税专用发票）",
         buyer=("中国建筑第八工程局有限公司华东分公司苏州项目部", "91320500MA1N2PQR7T"),
         seller=("江苏顺达物流供应链管理集团股份有限公司", "91320594MA20STUV8Y"),
         remark="起运地：苏州 到达地：南京 车牌号：苏E12345", issuer="李建国"),
    case("E_六行明细", [
        item("*食品*矿泉水", "550ml", "箱", "30", "28.00", "13%"),
        item("*食品*咖啡豆", "1kg", "袋", "4", "168.00", "13%"),
        item("*日用品*纸巾", "", "提", "15", "32.90", "13%"),
        item("*餐饮服务*餐费", "", "", "1", "860.00", "6%"),
        item("*电子产品*无线鼠标", "M330", "个", "8", "79.00", "13%"),
        item("*日用品*垃圾袋", "", "卷", "50", "3.50", "13%")],
        date="2024年11月21日", number="24312000000555666777"),
    # 折扣行：数量、单价为空，金额和税额为负数
    case("F_折扣行", [
        item("*办公设备*激光打印机", "M1136", "台", "2", "1580.00", "13%"),
        item("*办公设备*激光打印机", "", "", "", "", "13%", amount="-160.00")],
        number="24312000000222333444", date="2024年12月02日"),
    # 按次计费的服务：没有数量、单价、单位
    case("G_无数量单价", [
        item("*咨询服务*管理咨询服务费", "", "", "", "", "6%", amount="28000.00"),
        item("*会议服务*会议服务费", "", "", "", "", "6%", amount="3500.00")],
        seller=("杭州远见企业管理咨询有限公司", "91330106MA2H9JKL5P"), issuer="陈晓"),
]

if __name__ == "__main__":
    out = Path(__file__).parent / "synthetic"
    out.mkdir(exist_ok=True)
    for cs in CASES:
        draw(cs, out / f"{cs['id']}.pdf")
        truth = {k: v for k, v in cs.items() if k != "id"}
        truth["items"] = [{k: v for k, v in it.items() if not k.startswith("_")} for it in cs["items"]]
        (out / f"{cs['id']}.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    print("generated", len(CASES), "cases in", out)
