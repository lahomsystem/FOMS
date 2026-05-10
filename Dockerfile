# Railway Railpack 우회: "Error creating build plan with Railpack" 발생 시 Dockerfile 빌드 사용
# Python 3.12 + requirements.txt + start.sh (railway.toml과 동일)
FROM python:3.12-slim

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

# 시스템 의존성 (PostgreSQL 클라이언트, gevent 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

# 앱 코드 복사
COPY . .

# start.sh 실행 (railway.toml startCommand와 동일)
# USE_RQ_WORKER=1 → rq worker, 아니면 gunicorn
CMD ["sh", "start.sh"]
