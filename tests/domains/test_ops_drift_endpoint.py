"""OPS-DRIFT-01 계약: ``/api/foms/ops/drift-audit`` (admin 전용 드리프트 감사 조회).

drift-audit-daily 워크플로가 매일 이 엔드포인트 하나만 본다. 그래서 잠글 것은 네 가지다:

1. 미인증 **401**(JSON 계약 — 로그인 리다이렉트 금지)
2. 로그인했지만 ``role != ADMIN`` → **403**
3. ADMIN → 200 + 워크플로가 읽는 키 전부 존재
4. **양성/음성 대조군** — 드리프트를 일부러 만든 주문이 있으면 총합이 정확히 그 건수이고,
   같은 모집단에서 드리프트를 빼면 0 이다. 양성만 보면 "언제나 1 이상" 인 카운터도 통과한다.

드리프트의 정의(무엇을 세고 무엇을 안 세는가)는 ``foms/api/ops_drift.py`` 모듈 docstring 이
정본이며, 이 파일은 그 정의가 **실제 행으로** 재현되는지만 확인한다.
"""

from __future__ import annotations

from typing import Any

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, User

DRIFT_URL = "/api/foms/ops/drift-audit"


def _clean_order(**kwargs: Any) -> Order:
    """flat 컬럼·AS 투영이 모두 정본과 일치하는 ERP 주문을 만든다(대조군 재료).

    Args:
        **kwargs: ``Order`` 생성 인자 override(``structured_data`` 등).

    Returns:
        커밋된 주문. 라이브 쓰기 경로와 **같은** ``sync_erp_flat_columns`` 를 한 번
        태우므로 정의상 CLEAN 이다(감사가 쓰는 기대값 산출과 동일 함수).
    """
    defaults: dict[str, Any] = dict(
        received_date="2026-09-01",
        customer_name="드리프트-고객",
        phone="010-1111-2222",
        address="서울시 강남구",
        product="붙박이장",
        status="MEASURE",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "MEASURE"}},
    )
    defaults.update(kwargs)
    order = Order(**defaults)
    db_session.add(order)
    db_session.flush()
    sync_erp_flat_columns(order, order.structured_data)
    db_session.commit()
    return order


def _fetch(auth_client) -> dict[str, Any]:
    """ADMIN 으로 조회해 ``data`` 를 돌려준다(200·success 확인 포함)."""
    resp = auth_client.get(DRIFT_URL)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True, body
    return body["data"]


# --------------------------------------------------------------------------- #
# 인가 (rum/report 와 동일 규약)
# --------------------------------------------------------------------------- #
def test_drift_audit_unauthenticated_401(client):
    """미인증 요청은 401 JSON — 로그인 페이지로 리다이렉트하지 않는다."""
    resp = client.get(DRIFT_URL)
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_drift_audit_non_admin_403(app):
    """로그인했어도 ADMIN 이 아니면 403(감사 결과는 운영 전수 통계다)."""
    if not db_session.query(User).filter_by(username="drift_viewer").first():
        db_session.add(
            User(
                username="drift_viewer",
                password=generate_password_hash("pw"),
                role="MEASURE",  # ADMIN 이 아닌 아무 역할
                name="Viewer",
            )
        )
        db_session.commit()
    client = app.test_client()
    client.post(
        "/login",
        data={"username": "drift_viewer", "password": "pw"},
        follow_redirects=True,
    )

    resp = client.get(DRIFT_URL)
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


# --------------------------------------------------------------------------- #
# 응답 계약
# --------------------------------------------------------------------------- #
def test_drift_audit_admin_returns_required_keys(auth_client):
    """ADMIN 200 + 워크플로/조회 도구가 읽는 키가 전부 있다."""
    data = _fetch(auth_client)

    assert set(data) >= {"as_axis", "erp_flat", "drift_total", "truncated", "elapsed_ms"}
    assert isinstance(data["drift_total"], int)
    assert data["truncated"] is False  # 상한이 없다 = 절단 없음(조용한 절단 금지)
    assert set(data["as_axis"]) >= {
        "checked", "mismatch", "missing_projection", "legacy_only", "samples", "drift",
    }
    assert set(data["erp_flat"]) >= {
        "total", "clean", "safe", "ambiguous", "drift", "ambiguous_reasons", "samples",
    }


# --------------------------------------------------------------------------- #
# 음성 대조군 / 양성 대조군
# --------------------------------------------------------------------------- #
def test_drift_total_zero_when_population_is_clean(auth_client):
    """**음성 대조군** — 같은 모양의 주문이 있어도 어긋난 게 없으면 총합 0.

    빈 DB 로 0 을 보는 것은 대조군이 아니다(아무것도 안 세도 0 이다). 아래 양성
    테스트와 **동일한 생성 경로**로 만든 주문 2건을 모집단에 두고 0 을 확인한다.
    """
    _clean_order()
    _clean_order(customer_name="드리프트-고객2")

    data = _fetch(auth_client)
    assert data["erp_flat"]["total"] == 2, data["erp_flat"]
    assert data["erp_flat"]["clean"] == 2, data["erp_flat"]
    assert data["as_axis"]["drift"] == 0, data["as_axis"]
    assert data["erp_flat"]["drift"] == 0, data["erp_flat"]
    assert data["drift_total"] == 0, data


def test_as_axis_drift_counted(auth_client):
    """**양성** — 컬럼값이 유도값과 다르면 AS 축 드리프트로 잡힌다."""
    _clean_order()  # 대조 주문(같은 모집단)
    drifted = _clean_order(customer_name="AS드리프트-고객")
    drifted.as_axis_status = "COMPLETED"  # AS 이력이 없으니 유도값은 None
    db_session.commit()
    drifted_id = drifted.id  # 조회가 요청 세션을 rollback 하므로 id 를 미리 잡는다

    data = _fetch(auth_client)
    assert data["as_axis"]["checked"] == 1, data["as_axis"]
    assert data["as_axis"]["mismatch"] == 1, data["as_axis"]
    assert data["as_axis"]["drift"] == 1, data["as_axis"]
    assert data["as_axis"]["samples"][0]["order_id"] == drifted_id
    # as_axis_status 는 flat 파생 컬럼이 아니다 → ERP flat 은 여전히 깨끗하다.
    assert data["erp_flat"]["drift"] == 0, data["erp_flat"]
    assert data["drift_total"] == 1, data


def test_erp_flat_safe_drift_counted(auth_client):
    """**양성** — 파생 컬럼(erp_stage_code)이 SSOT 와 어긋나면 SAFE 드리프트."""
    _clean_order()  # 대조 주문
    drifted = _clean_order(customer_name="FLAT드리프트-고객")
    drifted.erp_stage_code = "DRAWING"  # structured_data.workflow.stage 는 MEASURE
    db_session.commit()
    drifted_id = drifted.id  # 조회가 요청 세션을 rollback 하므로 id 를 미리 잡는다

    data = _fetch(auth_client)
    assert data["erp_flat"]["total"] == 2, data["erp_flat"]
    assert data["erp_flat"]["safe"] == 1, data["erp_flat"]
    assert data["erp_flat"]["clean"] == 1, data["erp_flat"]
    assert data["erp_flat"]["drift"] == 1, data["erp_flat"]
    assert data["erp_flat"]["samples"][0]["order_id"] == drifted_id
    assert "erp_stage_code" in data["erp_flat"]["samples"][0]["drift_columns"]
    assert data["as_axis"]["drift"] == 0, data["as_axis"]
    assert data["drift_total"] == 1, data


def test_erp_flat_ambiguous_payment_drift_counted(auth_client):
    """**양성** — AMBIGUOUS(금전 컬럼 drift)도 드리프트로 **센다**.

    자동으로 못 고친다는 뜻이지 "안 어긋났다" 는 뜻이 아니다. 여기서 안 세면 사람이
    봐야 할 건이 매일 초록으로 덮인다.
    """
    _clean_order()  # 대조 주문
    drifted = _clean_order(
        customer_name="금액드리프트-고객",
        structured_data={"workflow": {"stage": "MEASURE"}, "payment": {"deposit": 500000}},
    )
    assert drifted.payment_amount == 500000, "sync 가 예약금을 flat 으로 파생해야 한다"
    drifted.payment_amount = 111  # 다른 흐름이 금전 컬럼을 덮은 형태
    db_session.commit()

    data = _fetch(auth_client)
    assert data["erp_flat"]["ambiguous"] == 1, data["erp_flat"]
    assert data["erp_flat"]["safe"] == 0, data["erp_flat"]
    assert data["erp_flat"]["drift"] == 1, data["erp_flat"]
    assert data["erp_flat"]["ambiguous_reasons"] == {"PAYMENT_AMOUNT_DRIFT": 1}
    assert data["drift_total"] == 1, data
