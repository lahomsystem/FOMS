#!/bin/bash
# Railway preDeployCommand: 새 배포가 라이브되기 전 1회만 실행되는 one-off 컨테이너.
#
# 배포 인프라 tail latency 근본 대응(2026-07-02): 기존에는 start.sh가 매 replica
# 부팅마다 `alembic upgrade head`를 실행했고, migrations/env.py의 세션 advisory
# lock이 다중 replica의 동시 upgrade를 직렬화 → replica 2는 replica 1의
# 마이그레이션이 끝날 때까지 부팅을 블록당해 cold-start가 수 초 증폭됐다.
#
# preDeployCommand는 replica가 뜨기 전 딱 1번 실행되므로, 여기서 스키마를
# 확정하고 start.sh는 gunicorn 기동만 담당하게 하여 replica 부팅을 즉시화한다.
# 이 스크립트가 실패하면(set -e) Railway가 배포를 라이브시키지 않는다(fail-closed:
# 잘못된 마이그레이션은 배포되지 않음).
set -e

# 워커 서비스(USE_RQ_WORKER=1)는 스키마를 소유하지 않으므로 마이그레이션 스킵.
if [ "$USE_RQ_WORKER" = "1" ]; then
  echo "[predeploy] worker service — skip migrations"
  exit 0
fi

echo "[predeploy] Running DB migrations..."
alembic upgrade head
echo "[predeploy] Migrations complete."

# WDPlanner V2 컬럼 보정 (alembic_version 불일치 복구)
python tools/ops/ensure_schema.py
echo "[predeploy] Schema ensure complete."
