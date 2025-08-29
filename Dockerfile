FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1
LABEL authors="11786"
RUN pip install paddleocr==3.1.1  -i https://mirrors.aliyun.com/pypi/simple/
RUN pip install Flask==3.1.1  -i https://mirrors.aliyun.com/pypi/simple/
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
COPY . .
RUN chmod +x main.py
EXPOSE 80
CMD ["python", "main.py"]

