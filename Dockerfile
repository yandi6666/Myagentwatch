FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . /app

RUN mkdir -p /app/data

EXPOSE 10000

ENV MYAGENTWATCH_PORT=10000

CMD ["python", "app.py"]
