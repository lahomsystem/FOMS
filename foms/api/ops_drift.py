"""OPS-DRIFT-01 — 드리프트 감사 2종의 admin 전용 조회로(읽기 전용 JSON).

``drift-audit-daily`` 워크플로가 매일 운영 DB 의 정합 드리프트를 확인하는 **유일한 외부
조회로**다. 운영 DB DSN 은 GitHub 에 넣지 않기로 결정했고(등록된 비밀은 스테이징 로그인
2개뿐), 그래서 rum-daily 가 Redis 를 다룬 방식을 그대로 따른다 — 앱이 자기 세션으로 감사를
돌리고 **요약 정수만** 돌려준다.

인가 규약은 :mod:`foms.api.foms_rum` 의 ``/api/foms/rum/report`` 와 동일하다: JSON
엔드포인트이므로 미인증 **401**, ``role != "ADMIN"`` **403**(로그인 리다이렉트 금지).

두 감사와 '드리프트' 의 정의
============================

**① AS 축 투영**(:func:`foms.services.orders.audit_as_axis_drift.audit_session`)

* 세는 값 = ``mismatch`` — 컬럼 ``orders.as_axis_status`` 가
  :func:`~foms.services.orders.state_axes.derive_as_axis_status` 유도값과 다른 주문 수.
* 안 세는 값 = ``missing_projection``·``legacy_only``. 둘 다 "유도값 있음 + 컬럼 NULL"
  이라 정의상 ``mismatch`` 의 **부분집합**이고, 더하면 같은 행을 두세 번 센다.
* 후보에서 빠지는 주문 = AS 이력이 전혀 없고 컬럼도 NULL 인 주문(유도값도 NULL → 일치),
  그리고 ``deleted_at`` 이 있는 주문(감사 대상 아님 — 기존 CLI 규약 그대로).

**② ERP flat 컬럼**(:func:`foms.services.orders.erp_flat_audit.audit_orders`)

* 세는 값 = ``SAFE + AMBIGUOUS`` (= ``total - CLEAN``). 근거는
  ``foms/services/orders/erp_flat_audit.py`` 의 분류 규칙이다:

  - ``CLEAN`` = structured_data(SSOT)에서 파생한 기대값과 flat 컬럼이 **전부 일치**
    → 드리프트 아님.
  - ``SAFE`` = 파생 컬럼이 어긋났고 금전 컬럼(``payment_amount``)은 안 걸림
    → 드리프트(자동 재동기 가능).
  - ``AMBIGUOUS`` = ``payment_amount`` 가 어긋났거나(``PAYMENT_AMOUNT_DRIFT``)
    ``structured_data`` 가 dict 가 아님(``MALFORMED_STRUCTURED_DATA``) → **드리프트**.
    자동으로 못 고친다는 뜻이지 "안 어긋났다" 는 뜻이 아니므로 센다. 이걸 빼면 사람이
    봐야 할 건이 매일 초록으로 덮인다.

* 안 세는 값 = 비-ERP 주문과 ``structured_data is None`` 주문. ``sync_erp_flat_columns``
  이 no-op 이라 **기대 파생값 자체가 없고**, ``classify_order`` 가 ``None`` 을 돌려
  ``total`` 에도 들어가지 않는다(분모에서 제외 = 분자에서도 제외).

``drift_total`` = ① + ②. 서로 다른 컬럼군을 보므로 두 감사 사이의 이중 계수는 없다.

부하·타임아웃
=============

② 는 전 주문 스캔이다(``yield_per`` 스트리밍, 쓰기 0). **상한을 두지 않는다** — 상한을
두면 "0건" 이 거짓이 될 수 있고, 조용한 절단은 매일 도는 게이트에서 가장 나쁜 실패다.
대신 gunicorn ``--timeout 120`` 을 넘기면 요청이 죽고 조회 도구가 exit 3(job fail)로
시끄럽게 실패한다 — **거짓 초록이 나오는 경로가 없다**. ``elapsed_ms`` 를 함께 실어
여유가 얼마나 남았는지 매일 눈에 보이게 한다.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from flask import Blueprint, g, jsonify

from db import get_db
from foms.services.orders.audit_as_axis_drift import audit_session
from foms.services.orders.erp_flat_audit import AMBIGUOUS, SAFE, AuditReport, audit_orders

ops_drift_bp = Blueprint("ops_drift", __name__)

# 요약에 싣는 진단 표본 상한(총계는 언제나 전수 — 표본만 자른다).
SAMPLE_LIMIT = 20


def _as_axis_summary(session: Any) -> dict[str, Any]:
    """AS 축 투영 드리프트 요약 + ``drift`` 총건(= ``mismatch``).

    Args:
        session: 앱 요청 세션(``scoped_session`` 프록시 그대로).

    Returns:
        :func:`~foms.services.orders.audit_as_axis_drift.audit_session` 의 요약에
        ``drift`` 를 더한 dict. ``drift`` 는 ``mismatch`` 하나다 —
        ``missing_projection``·``legacy_only`` 는 둘 다 ``mismatch`` 의 부분집합이라
        더하면 같은 행을 두세 번 센다(모듈 docstring §① 가 정본).
    """
    summary = audit_session(session)
    return {**summary, "drift": summary["mismatch"]}


def _flat_samples(report: AuditReport) -> list[dict[str, Any]]:
    """ERP flat 드리프트 진단 표본(SAFE 먼저, 그다음 AMBIGUOUS). PII 없음.

    Args:
        report: :func:`~foms.services.orders.erp_flat_audit.audit_orders` 결과.

    Returns:
        ``order_id``/``classification``/``drift_columns``/``reason`` dict 최대
        ``SAMPLE_LIMIT`` 개(주문 id·컬럼명·사유코드만 — 고객 정보 미포함).
    """
    picked = (report.safe_audits + report.ambiguous_audits)[:SAMPLE_LIMIT]
    return [
        {
            "order_id": audit.order_id,
            "classification": audit.classification,
            "drift_columns": list(audit.drift_columns),
            "reason": audit.reason,
        }
        for audit in picked
    ]


def _erp_flat_summary(session: Any) -> dict[str, Any]:
    """ERP flat 컬럼 정합 요약 + ``drift`` 총건(= SAFE + AMBIGUOUS).

    Args:
        session: 읽기 전용으로 쓸 세션(요청 scoped_session).

    Returns:
        ``total``/``clean``/``safe``/``ambiguous``/``drift``/``ambiguous_reasons``/
        ``samples``. 무엇을 세고 무엇을 안 세는지는 모듈 docstring §② 가 정본이다.
    """
    report = audit_orders(session)
    counts = report.masked_counts()
    reasons = Counter(a.reason or "UNKNOWN" for a in report.ambiguous_audits)
    return {
        "total": counts["total"],
        "clean": counts["clean"],
        "safe": counts["safe"],
        "ambiguous": counts["ambiguous"],
        "drift": report.counts[SAFE] + report.counts[AMBIGUOUS],
        "ambiguous_reasons": dict(sorted(reasons.items())),
        "samples": _flat_samples(report),
    }


@ops_drift_bp.route("/api/foms/ops/drift-audit", methods=["GET"])
def drift_audit() -> tuple[Any, int]:
    """admin 전용 드리프트 감사 2종 요약(JSON, 읽기 전용).

    미인증 **401**, ``role != ADMIN`` **403**(JSON 계약 — 리다이렉트 금지).

    Returns:
        200 ``{"success": True, "data": {as_axis, erp_flat, drift_total, truncated,
        elapsed_ms}}``. ``drift_total`` 이 워크플로 판정용 정수 하나이고,
        ``truncated`` 는 상한이 없으므로 **항상 False** 다 — 그래도 키를 두는 이유는
        조회 도구가 절단 여부를 명시적으로 확인하게 만들어, 나중에 누가 상한을 넣어도
        조용히 넘어가지 못하게 하기 위함이다. 드리프트의 정의는 모듈 docstring.
    """
    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"success": False, "error": "unauthorized"}), 401
    if getattr(user, "role", None) != "ADMIN":
        return jsonify({"success": False, "error": "forbidden"}), 403

    session = get_db()
    started = time.perf_counter()
    as_axis = _as_axis_summary(session)
    erp_flat = _erp_flat_summary(session)
    session.rollback()  # 읽기 전용 보장: 감사 중 만들어진 트랜잭션을 커밋 없이 닫는다.

    data = {
        "as_axis": as_axis,
        "erp_flat": erp_flat,
        "drift_total": as_axis["drift"] + erp_flat["drift"],
        "truncated": False,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
    return jsonify({"success": True, "data": data}), 200
