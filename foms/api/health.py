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

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
def healthz() -> tuple[object, int]:
    """앱 프로세스 라이브니스. Railway healthcheck 및 keep-warm 프로브용.

    Returns:
        (JSON 응답, 200): 워커가 요청 처리 가능 상태임을 알리는 최소 응답.
    """
    return jsonify({"status": "ok"}), 200
