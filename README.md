# 项目简介

本项目是一个基于 PaddleOCR 的自动识别发票内容，导出Excel。

![alt text](img/image.png)
![alt text](img/image-1.png)
![alt text](img/image-2.png)
![alt text](img/image-3.png)
![alt text](img/image-4.png)
## 功能特点
- **发票 OCR 识别**：利用 PaddleOCR 技术，实现对发票图片（jpg、png、pdf等）的文字识别，支持多种发票类型。
- **数据清洗**：对识别出的文字进行清洗，去除噪声和异常值，确保数据质量。
- **Excel 导出**：将处理后的数据导出为 Excel 格式，方便用户查看和分析。

## 技术栈
- **后端**：Flask 框架
- **前端**：HTML、CSS、JavaScript
- **OCR 识别**：PaddleOCR
- **数据处理**：Python 语言

## 安装与运行

### 方式一：Docker（推荐用于部署）
安装docker环境，运行项目
```bash
sh build.sh
```
体验地址：http://zhiwei3306.com/fapiao
本地访问地址：http://localhost:80/fapiao
具体功能介绍文章：https://mp.weixin.qq.com/s/dMCdKKOAvlYM8u8h2hiJTw

### 方式二：Windows 一键启动（双击运行）
1. 在 [Releases](https://github.com/zhiweiiii/fapiao-ocr-excel/releases) 页面下载最新的 `fapiao-ocr-windows-*.zip`（或直接 clone 本仓库）
2. 解压到**纯英文路径**（如 `D:\fapiao-ocr`），电脑需已安装 64 位 Python 3.9 ~ 3.13
3. 双击 `start.bat`：首次运行会自动创建虚拟环境并安装依赖（5~20 分钟），之后双击即可秒开，并自动打开浏览器

详见压缩包内的 `README_Windows.txt`。发布新版本：推送 `v*` 格式的 tag，或在 GitHub 的 Actions 页面手动运行「Windows 发布包」并填写版本号（如 `v1.0.1`）。GitHub Actions 会自动打包、在 Windows 环境中实际安装运行并识别示例发票，测试通过后发布到 Releases。

### 方式三：本地直接运行（不使用 Docker）
模型权重文件已经放在仓库的 `module/` 目录下，不需要额外下载，只需要装好 Python 依赖即可。

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 安装依赖（paddleocr 体积较大，第一次安装会比较慢）
pip install -r requirements.txt
# paddleocr 依赖 paddlepaddle，需要单独安装（请固定 3.1.1，3.3.x 在 CPU 上会报错）：
pip install paddlepaddle==3.1.1 # 如果有 GPU，请参照 https://www.paddlepaddle.org.cn/ 安装对应的 paddlepaddle-gpu

# 启动服务（默认监听 80 端口，Linux 上非 root 用户监听 80 端口可能需要权限；
# 可以用 PORT 环境变量换成其他端口，比如本地开发常用的 8080）
PORT=8080 python3 main.py
```
启动后访问 http://localhost:8080/fapiao 即可使用。

### 运行测试
```bash
pip install -r requirements-dev.txt

# 纯逻辑单元测试（不需要安装 paddleocr，几秒内跑完）
pytest tests/test_main_helpers.py tests/test_extract_invoice_info.py

# 真实 OCR 识别准确率测试（需要已安装 paddleocr，会调用真实模型，比较慢）
python3 -m tests.test_ocr_compare
```

目前只测试了标准的发票文件，对于手拍的文件或者其他文件，暂未测试过
未来如果有提供数据的，可以尝试进一步优化

目前使用的服务器性能有限，所以处理速度较慢，一个文件10s左右，请耐心等待
欢迎交流
![alt text](img/pubapp.png)