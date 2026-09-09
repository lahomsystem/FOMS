"""OPS-HEARTBEAT-02 — 워커 루프 하트비트의 admin 전용 조회로(읽기 전용 JSON).

``worker-heartbeat-daily`` 워크플로가 매일 "워커 루프가 살아 있는가" 를 확인하는 **유일한
외부 조회로**다. 운영 DB DSN 은 GitHub 에 넣지 않기로 했고(등록된 비밀은 스테이징 로그인
2개뿐), 그래서 :mod:`foms.api.ops_drift` 가 쓴 방식을 그대로 따른다 — 앱이 자기 세션으로
표를 읽고 **요약만** 돌려준다.

인가 규약은 ``/api/foms/ops/drift-audit`` 와 동일하다: 미인증 **401**, ``role != "ADMIN"``
**403**(로그인 리다이렉트 금지).

왜 필요한가
===========

:mod:`tools.ops.check_sidefx_readiness` 는 사람이 명령을 쳐야만 판정한다. 2026-02 워커
offline 과 2026-08-31 SIDEFX 미배포는 **두 번 다 사용자가 화면에서 먼저 발견**했다. 재는
도구를 만들어도 재는 사람이 없으면 없는 것과 같다.

판정 규약(정본)
===============

* **필수 kind** = :data:`foms.services.sidefx_worker.WORKER_KINDS`(outbox 3종). 행이 없으면
  not-ready 다 — 소비 프로세스가 안 도는 상태이므로 fail-closed 가 맞다.
* **관측된 kind** = 표에 행이 있는 나머지 loop kind. 행이 있으면 신선도를 본다.
* 신선도 예산은 판정부(:meth:`~foms.services.sidefx_worker.ReadinessThresholds.
  heartbeat_age_limit`)가 정한다 — 루프가 신고한 ``interval_seconds`` x 3 과 등록부 값 중
  큰 쪽이다. 그래서 간격을 env 로 바꿔도 살아 있는 루프를 죽었다고 하지 않는다.
* 등록부에 없는 kind 가 표에 있으면 판정할 수 없으므로 ``unknown_kinds`` 로 싣는다(조회
  도구가 시끄럽게 실패한다). 조용히 지나가면 "아무도 안 읽는" 상태로 되돌아간다.
* **결론(``ready``)은 여기서 새로 만들지 않는다.** CLI 가 쓰는
  :func:`~foms.services.sidefx_worker.evaluate_readiness` 를 그대로 부른다 — 하트비트
  유무·신선도만이 아니라 **scan lag·큐 적체(`oldest_pending_lag`)·DEAD 수**까지 같은
  네 축으로 본다. 2026-09-09 이전에는 이 조회가 앞의 두 축만 봐서, CLI 는 not-ready 인데
  일일 보고는 "전부 신선" 이라 말할 수 있었다(같은 사실을 두 판정부가 다르게 읽는 결함).

**한계(명시)**: 한 번도 하트비트를 쓴 적 없는 loop 는 이 조회로 보이지 않는다. 그 축은
``tests/domains/test_loop_heartbeat_wiring.py`` 가 막는다 — ``start.sh`` 가 띄우는 모든
``--loop`` 러너는 등록부 kind 를 선언해야 하고, 안 하면 CI 가 빨개진다.

이 조회는 **읽기 전용**이다(SELECT 만, 커밋 없음).
"""

from __future__ import annotations

import time
from typing import Any

from flask import Blueprint, g, jsonify

from db import get_db
from foms.services.sidefx_worker import (
    WORKER_KIND_SPECS,
    WORKER_KINDS,
    ReadinessThresholds,
    collect_readiness_observations,
    evaluate_readiness,
)

ops_worker_heartbeat_bp = Blueprint("ops_worker_heartbeat", __name__)


def summarize_heartbeats(
    observations: dict[str, Any], thresholds: ReadinessThresholds | None = None
) -> dict[str, Any]:
    """관측치를 kind 별 판정 요약으로 바꾼다(순수 함수 — DB 접근 없음).

    Args:
        observations: :func:`~foms.services.sidefx_worker.collect_readiness_observations`
            결과.
        thresholds: 임계값 묶음(생략 시 기본 — kind 별 등록부 예산을 쓴다).

    Returns:
        ``{"kinds": {kind: {...}}, "not_ready": [...], "not_ready_count": int,
        "unknown_kinds": [...], "ready": bool, "failures": [...],
        "oldest_pending_lag": int|None, "dead_count": int}``.

        각 kind 항목은 ``age_seconds``·``interval_seconds``(루프가 신고한 값, 없으면
        ``None``)·``limit_seconds``·``ready``·``reason``(``ok``/``missing``/``stale``)·
        ``required``.

        ``ready`` 는 **kind 표만의 결론이 아니다** — :func:`evaluate_readiness` 가
        보는 네 축(하트비트 유무·신선도·scan lag·큐 적체/DEAD)을 그대로 받는다.
    """
    thresholds = thresholds or ReadinessThresholds()
    heartbeats = observations.get("heartbeats", {}) or {}
    unknown = sorted(k for k in heartbeats if k not in WORKER_KIND_SPECS)

    judged = sorted(set(WORKER_KINDS) | (set(heartbeats) - set(unknown)))
    kinds: dict[str, Any] = {}
    for kind in judged:
        observed = heartbeats.get(kind)
        declared = (observed or {}).get("interval_seconds")
        limit = thresholds.heartbeat_age_limit(kind, declared)
        if observed is None:
            kinds[kind] = {
                "age_seconds": None, "interval_seconds": None, "limit_seconds": limit,
                "ready": False, "reason": "missing", "required": True,
            }
            continue
        age = int(observed.get("age_seconds") or 0)
        fresh = age < limit
        kinds[kind] = {
            "age_seconds": age,
            "interval_seconds": declared,
            "limit_seconds": limit,
            "ready": fresh,
            "reason": "ok" if fresh else "stale",
            "required": kind in WORKER_KINDS,
        }

    not_ready = sorted(k for k, v in kinds.items() if not v["ready"])

    # 결론은 여기서 새로 만들지 않는다. CLI(check_sidefx_readiness)가 쓰는 판정 함수를
    # 그대로 부른다 — 위 표는 하트비트 축만 보므로, 큐가 적체되거나 DEAD 가 쌓여
    # CLI 가 not-ready 라고 말하는 상태를 이 조회는 "전부 신선" 이라 보고했다
    # (같은 사실을 두 판정부가 다르게 읽는 결함 — 2026-09-08 헛알림과 같은 계열).
    report = evaluate_readiness(observations, thresholds, kinds=judged)

    return {
        "kinds": kinds,
        "not_ready": not_ready,
        "not_ready_count": len(not_ready),
        "unknown_kinds": unknown,
        "ready": report.ready and not unknown,
        "failures": report.failures,
        "oldest_pending_lag": observations.get("oldest_pending_lag"),
        "dead_count": int(observations.get("dead_count") or 0),
    }


@ops_worker_heartbeat_bp.route("/api/foms/ops/worker-heartbeats", methods=["GET"])
def worker_heartbeats() -> tuple[Any, int]:
    """admin 전용 워커 루프 하트비트 요약(JSON, 읽기 전용).

    미인증 **401**, ``role != ADMIN`` **403**(JSON 계약 — 리다이렉트 금지).

    Returns:
        200 ``{"success": True, "data": {kinds, not_ready, not_ready_count,
        unknown_kinds, ready, failures, oldest_pending_lag, dead_count,
        elapsed_ms}}``. 워크플로가 읽는 판정값은 ``ready`` 다 — 하트비트 축만 보는
        ``not_ready_count`` 와 달리 큐 적체·DEAD 까지 포함한다. 규약은 모듈
        docstring 이 정본.
    """
    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"success": False, "error": "unauthorized"}), 401
    if getattr(user, "role", None) != "ADMIN":
        return jsonify({"success": False, "error": "forbidden"}), 403

    session = get_db()
    started = time.perf_counter()
    observations = collect_readiness_observations(session)
    session.rollback()  # 읽기 전용 보장: 조회 트랜잭션을 커밋 없이 닫는다.

    data = summarize_heartbeats(observations)
    data["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return jsonify({"success": True, "data": data}), 200
