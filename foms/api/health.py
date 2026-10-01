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

import json
import os
import time

from flask import Blueprint, jsonify, session

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


#: 보정 작업량. 바꾸면 perf_budgets.json 의 cpu_calib_ref_ms 를 다시 시드해야 한다.
CPU_CALIB_ROUNDS = 400
_CPU_CALIB_PAYLOAD = [{"id": i, "name": f"row-{i}", "tags": ["a", "b", str(i)]} for i in range(50)]


@health_bp.route("/healthz/cpu", methods=["GET"])
def healthz_cpu() -> tuple[object, int]:
    """늘 같은 순수 계산을 돌려 이 순간 컨테이너의 CPU 빠르기를 잰다 (PERF-GATE-ST).

    Railway 공유 호스트는 이웃이 바쁘면 같은 렌더도 2배 느려진다(2026-10-02 실측: 서비스
    CPU 5% 인데 대시보드 서버 시간 100→190ms). 성능 게이트가 이 값으로 예산을 보정해
    "기계가 느린 날"과 "코드가 느려진 날"을 가른다. DB·Redis 는 건드리지 않는다.
    로그인 사용자만 — 무인증으로 열면 공짜 CPU 소모 엔드포인트가 된다.

    Returns:
        (JSON, 200) ``{"success": True, "data": {"cpu_ms": <float>}}``, 비로그인이면 403.
    """
    if not session.get("user_id"):
        return jsonify({"success": False, "data": None, "error": "login required"}), 403
    t0 = time.perf_counter()
    acc = 0
    for _ in range(CPU_CALIB_ROUNDS):
        acc += len(json.dumps(_CPU_CALIB_PAYLOAD, sort_keys=True))
    cpu_ms = (time.perf_counter() - t0) * 1000
    return jsonify({"success": True, "data": {"cpu_ms": round(cpu_ms, 2), "work": acc}, "error": None}), 200
