# Railway Railpack 우회: "Error creating build plan with Railpack" 발생 시 Dockerfile 빌드 사용
# Python 3.12 + requirements.txt + start.sh (railway.toml과 동일)
FROM python:3.12-slim

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_NO_CACHE_DIR=1

# 시스템 의존성 (PostgreSQL 클라이언트, gevent 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치 — base image pip(25.x) 유지, 별도 pip self-upgrade 생략(Railway BrokenPipe 회피)
COPY requirements.txt .
RUN set -eux; \
    for attempt in 1 2 3 4 5; do \
      python -m pip install --timeout 120 --retries 10 setuptools wheel && \
      python -m pip install --timeout 120 --retries 10 -r requirements.txt && \
      exit 0; \
      echo "pip install attempt ${attempt} failed, retrying..."; \
      sleep $((attempt * 5)); \
    done; \
    exit 1

# CUTOVER-MODE-01: in-image compatibility 정본을 explicit COPY (docs/ excluded 파일에
# 의존하지 않도록 tracked foms/build_compatibility.json 을 명시적으로 이미지에 넣는다).
# 아래 COPY . . 도 포함하지만, .dockerignore 회귀에도 이 파일은 항상 존재하게 보장한다.
COPY foms/build_compatibility.json /app/foms/build_compatibility.json

# 앱 코드 복사
COPY . .

# start.sh 실행 (railway.toml startCommand와 동일)
# USE_RQ_WORKER=1 → rq worker, 아니면 gunicorn
CMD ["sh", "start.sh"]
