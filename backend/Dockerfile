FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple \
    --timeout 180 --retries 8 \
    -r requirements.txt -r requirements-ai.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
