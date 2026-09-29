#!/bin/bash
set -e  # 어떤 명령이 실패해도 즉시 종료
# Railway unified start: USE_RQ_WORKER=1이면 RQ worker, 아니면 gunicorn
#
# 마이그레이션(alembic upgrade + ensure_schema)은 여기서 실행하지 않는다.
# replica마다 부팅 시 실행하면 세션 advisory lock으로 직렬화되어 cold-start가
# 증폭되므로, 배포당 1회 실행되는 preDeployCommand(predeploy.sh)로 이관했다.
# → replica 부팅은 gunicorn 기동만 남아 즉시화된다.
if [ "$USE_RQ_WORKER" = "1" ]; then
  # Redis 부팅 레이스 방어 (2026-08-07 운영 사고 근본 수정):
  # Railway 프라이빗 네트워크/Redis 컨테이너가 워커보다 늦게 준비되면
  # `rq worker`가 첫 명령(is_suspended)에서 redis TimeoutError로 즉사한다.
  # 즉사 간격이 ~11초라 재시작 정책 ON_FAILURE(10회)가 2분 만에 소진되고
  # 서비스가 CRASHED로 고착됐다. PING 성공까지 기다린 뒤 기동한다.
  # (예산 초과 시 set -e 로 종료 → Railway 재시작 1회가 수 분을 커버)
  python tools/ops/wait_for_redis.py --url "$REDIS_URL" \
    --timeout "${FOMS_REDIS_WAIT_SECONDS:-300}"

  # 배경 작업(알림 재촉·네이버 주문 수집·자동 발송·정산 동기화·좌표 스윕·큐 소비)은 파이썬
  # 감독자가 PID 1 로 띄우고, 어떤 이유로 끝나든 대기 뒤 다시 띄운다. 작업 목록·켜짐 조건 env·
  # 기본값의 정본은 tools/ops/worker_supervisor.py 의 worker_jobs() 다.
  # 사고: 2026-09-08(rq 가 PID 1 이라 Redis 재시작에 컨테이너째 멈춤 → 셸 감시 루프),
  # 2026-09-10(`&` 로 한 번 띄운 정산 루프가 매일 죽고 배포 때만 부활 — 감독자가 rq 하나뿐이었다).
  # 설계서: docs/specs/2026-09-29-worker-loop-supervisor-spec.md
  exec python tools/ops/worker_supervisor.py
else
  exec gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 --access-logfile - --bind "0.0.0.0:${PORT:-8080}" app:app
fi
