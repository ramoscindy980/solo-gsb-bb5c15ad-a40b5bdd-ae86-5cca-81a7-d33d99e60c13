FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖安装纳入镜像构建流程
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 服务启动纳入容器启动流程
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
