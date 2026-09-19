FROM python:3.12.14-slim-trixie@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG SOURCE_COMMIT=unknown
ARG DEPENDENCY_LOCK_SHA256=unknown

LABEL org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      xyz.yl617.ai-study.dependency-lock-sha256="${DEPENDENCY_LOCK_SHA256}"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt requirements-ai.txt constraints-prod.lock ./
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple \
    --timeout 180 --retries 8 \
    --constraint constraints-prod.lock \
    -r requirements.txt -r requirements-ai.txt \
    && pip check

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
