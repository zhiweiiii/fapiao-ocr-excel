# 项目简介

本项目是一个基于 PaddleOCR 的自动识别发票内容，导出Excel。

![alt text](image.png)
![alt text](image-1.png)
![alt text](image-2.png)
![alt text](image-3.png)
![alt text](image-4.png)
## 功能特点
- **发票 OCR 识别**：利用 PaddleOCR 技术，实现对发票图片的文字识别，支持多种发票类型。
- **数据清洗**：对识别出的文字进行清洗，去除噪声和异常值，确保数据质量。
- **Excel 导出**：将处理后的数据导出为 Excel 格式，方便用户查看和分析。

## 技术栈
- **后端**：Flask 框架
- **前端**：HTML、CSS、JavaScript
- **OCR 识别**：PaddleOCR
- **数据处理**：Python 语言

## 安装与运行
安装docker环境，运行项目
```bash
sh build.sh
```
访问地址：http://localhost/fapiao
