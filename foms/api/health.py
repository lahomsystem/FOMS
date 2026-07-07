"""Railway 라이브니스 프로브 blueprint.

배포 인프라 tail latency 근본 대응(2026-07-02): Railway가 `healthcheckPath`로
이 엔드포인트가 200을 반환할 때까지 새 컨테이너를 대기시켜, 앱 워엄업 전
트래픽 라우팅으로 인한 cold-start 스파이크를 차단한다.

의도적으로 **DB·세션·인증을 건드리지 않는다**(순수 liveness). gunicorn gevent
워커가 요청을 받을 수 있게 된 즉시 200을 반환해야 하므로, 무거운 readiness
체크(DB ping 등)를 넣지 않는다. 로그인 데코레이터도 없어야 프로브가 302가
아닌 200을 받는다.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
def healthz() -> tuple[object, int]:
    """앱 프로세스 라이브니스. Railway healthcheck 및 keep-warm 프로브용.

    ``commit`` 은 현재 컨테이너가 서빙 중인 배포 커밋 SHA(Railway 표준 주입
    ``RAILWAY_GIT_COMMIT_SHA``)다. perf-gate CI 의 배포 완료 대기
    (``tools/perf/wait_staging_deploy.py``)가 이 값을 GITHUB_SHA 와 대조해
    "새 컨테이너가 실제 트래픽을 받는지" 확인한다. env 부재(로컬/비Railway)면
    빈 문자열이라 기존 최소 응답 계약(status=ok, 200)은 그대로 보존된다.

    Returns:
        (JSON 응답, 200): ``{"status": "ok", "commit": "<sha>"}``.
    """
    return (
        jsonify({"status": "ok", "commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")}),
        200,
    )
