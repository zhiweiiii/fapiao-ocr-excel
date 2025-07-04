FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.0.0
LABEL authors="11786"
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
COPY . .
RUN chmod +x main.py
RUN echo "Asia/shanghai" > /etc/timezone
EXPOSE 80
CMD ["python", "main.py"]

