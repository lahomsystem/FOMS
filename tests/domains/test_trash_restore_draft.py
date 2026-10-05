"""휴지통 복원은 작성 중 초안을 되살리지 않는다 (사용자 결정 (다), 2026-10-05).

운영 #5078: 새 주문 화면에서 '버리기'로 지운 초안을 휴지통에서 복원하자 status 만 RECEIVED 로
바뀌고 ``meta.draft`` 표식이 남아 어느 화면에도 안 보이는 주문이 됐다(설계서
``docs/specs/2026-10-05-hidden-draft-orders-fix_SPEC.md`` §1). 고정하는 계약:

* 복원 2길(``POST /restore_orders`` 일괄 · ``POST /api/orders/<id>/mobile-restore``)이 초안 행을
  **서버에서** 거절하고 그 행은 한 글자도 안 바뀐다(status·original_status·deleted_at·표식·버전).
  초안 모양 5가지(옛 버리기·새 버리기/정리 크론·표식 없는 옛 행·정본 삭제된 초안·정본 삭제된
  숨은 모양)를 다 본다.
* **음성 대조군**: 초안이 아닌 주문은 두 갈래(옛 status 미러·정본 삭제) 모두 지금처럼 복원되고
  status 를 지킨다.
* 복원 기록: 주문마다 ``ORDER_RESTORED`` 감사행(``target_id``), 요약 줄 "주문 N개 복원" 의
  ``detail`` 에 ``order_ids``·``rejected_draft_ids``.
* 버리기 기록: ``original_status='DRAFT'`` + ``ORDER_DRAFT_DISCARDED`` 이벤트 1건.
* 휴지통 목록: 초안 행은 "작성 중 초안 — 복원 불가" + 이름 없는 비활성 체크박스.
"""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.draft_guard import (
    DRAFT_NOT_RESTORABLE_CODE,
    DRAFT_NOT_RESTORABLE_LABEL,
)
from foms.services.orders.soft_delete import EVENT_RESTORED, soft_delete_order
from models import Order, OrderEvent, SecurityLog, User

_TRASHED_AT = "2026-10-05 00:22:46"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _login(client, username: str, *, role: str = "ADMIN") -> int:
    """사용자를 만들고 세션에 로그인한 뒤 id 를 돌려준다."""
    user = User(
        username=username, password=generate_password_hash("pw"), role=role, team="CS",
        name=username, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = int(user.id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role
    return user_id


def _order(*, name: str, status: str, draft: bool, original_status=None, deleted_at=None,
           stage: str = "RECEIVED") -> int:
    """휴지통 행 1건을 만든다(id 만 돌려준다 — 요청 뒤 ORM 객체는 세션이 끊긴다)."""
    meta = {"draft": True, "created_via": "ADD_ORDER_AUTOSAVE"} if draft else {"draft": False}
    order = Order(
        received_date="2026-10-05", customer_name=name, phone="010-3333-4444",
        address="서울 테헤란로 1", product="붙박이장", status=status,
        original_status=original_status, deleted_at=deleted_at, is_erp_order=True,
        erp_stage_code=stage,
        structured_data={"meta": meta, "workflow": {"stage": stage}},
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _canonical_trashed(*, name: str, status: str, draft: bool, actor_id: int) -> int:
    """정본 ``soft_delete_order`` 로 휴지통에 넣은 행(status 보존·deleted_at 세팅)."""
    order_id = _order(name=name, status=status, draft=draft, stage=status if status != "DRAFT"
                      else "RECEIVED")
    soft_delete_order(db_session, order_id=order_id, actor_user_id=actor_id)
    db_session.commit()
    return order_id


def _row(order_id: int) -> tuple:
    """'그대로'를 비교할 값."""
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = order.structured_data or {}
    return (
        order.status, order.original_status, order.deleted_at,
        (sd.get("meta") or {}).get("draft"), int(order.mutation_version or 0),
    )


def _visible(order_id: int) -> bool:
    db_session.expire_all()
    return (
        db_session.query(Order).filter(Order.active_filter(), Order.id == order_id).first()
        is not None
    )


def _event_count(order_id: int, event_type: str) -> int:
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .count()
    )


def _restore(client, *order_ids: int):
    return client.post(
        "/restore_orders", data={"selected_order": [str(oid) for oid in order_ids]},
        follow_redirects=False,
    )


def _restored_audit_ids() -> list[int]:
    db_session.expire_all()
    rows = db_session.query(SecurityLog).filter(SecurityLog.action == "ORDER_RESTORED").all()
    return sorted(int(row.target_id) for row in rows)


def _summary_detail() -> dict:
    db_session.expire_all()
    row = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.message.like("주문 %개 복원"))
        .order_by(SecurityLog.id.desc())
        .first()
    )
    assert row is not None
    return row.detail or {}


def _flashes(client) -> list:
    with client.session_transaction() as sess:
        return list(sess.get("_flashes") or [])


# status 를 DELETED 로 덮은 초안 모양 3가지(정본 삭제 갈래 2가지는 아래 시험이 따로 본다).
_DRAFT_SHAPES = {
    "discard_before_fix": dict(status="DELETED", original_status=None),   # #5078 의 재료
    "discard_or_cron": dict(status="DELETED", original_status="DRAFT"),   # 새 버리기·정리 크론
    "flag_missing_old_row": dict(status="DELETED", original_status="DRAFT", draft=False),
}


# --------------------------------------------------------------------------- #
# 1. 일괄 복원 /restore_orders — 초안 거절, 행 그대로
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shape", sorted(_DRAFT_SHAPES))
def test_restore_orders_rejects_status_mirrored_draft(client, shape):
    _login(client, f"rd_bulk_{shape}")
    spec = dict(_DRAFT_SHAPES[shape])
    draft = spec.pop("draft", True)
    order_id = _order(name=f"초안-{shape}", draft=draft, deleted_at=_TRASHED_AT, **spec)
    before = _row(order_id)

    resp = _restore(client, order_id)

    assert resp.status_code in (302, 303)
    assert _row(order_id) == before
    assert not _visible(order_id)
    assert _event_count(order_id, EVENT_RESTORED) == 0
    assert _restored_audit_ids() == []
    assert _summary_detail()["rejected_draft_ids"] == [order_id]
    assert any(cat == "warning" and f"#{order_id}" in msg for cat, msg in _flashes(client))


@pytest.mark.parametrize("status", ["DRAFT", "MEASURE"])
def test_restore_orders_rejects_canonical_trashed_draft(client, status):
    """정본 삭제 갈래(status 보존)도 막는다 — DRAFT 초안과 이미 숨은 모양(MEASURE+표식) 모두."""
    actor_id = _login(client, f"rd_canon_{status}")
    order_id = _canonical_trashed(name=f"정본초안-{status}", status=status, draft=True,
                                  actor_id=actor_id)
    before = _row(order_id)
    assert before[2] is not None  # 휴지통에 있다

    resp = _restore(client, order_id)

    assert resp.status_code in (302, 303)
    assert _row(order_id) == before
    assert _event_count(order_id, EVENT_RESTORED) == 0


def test_restore_orders_negative_control_legacy_mirror_restores_original_status(client):
    """음성 대조군 1 — 초안 아닌 옛 갈래(status DELETED + original MEASURE)는 지금처럼 복원."""
    _login(client, "rd_ctrl_legacy")
    order_id = _order(name="정상-옛갈래", status="DELETED", original_status="MEASURE",
                      deleted_at=_TRASHED_AT, draft=False, stage="MEASURE")

    resp = _restore(client, order_id)

    assert resp.status_code in (302, 303)
    status, original_status, deleted_at, flag, _version = _row(order_id)
    assert (status, original_status, deleted_at, flag) == ("MEASURE", None, None, False)
    assert _visible(order_id)
    assert _event_count(order_id, "ORDER_CREATED") == 0
    assert _restored_audit_ids() == [order_id]
    db_session.expire_all()
    audit = db_session.query(SecurityLog).filter(SecurityLog.action == "ORDER_RESTORED").one()
    assert audit.target_type == "order"
    assert audit.detail["from_status"] == "DELETED"
    assert audit.detail["to_status"] == "MEASURE"
    assert audit.detail["original_status"] == "MEASURE"
    assert "정상-옛갈래" not in audit.message  # 감사 문장에 고객 이름 없음


def test_restore_orders_negative_control_canonical_order_keeps_status(client):
    """음성 대조군 2 — 정본 삭제된 DRAWING 주문은 DRAWING 그대로 복원돼 화면에 보인다."""
    actor_id = _login(client, "rd_ctrl_canon")
    order_id = _canonical_trashed(name="정상-정본", status="DRAWING", draft=False,
                                  actor_id=actor_id)

    resp = _restore(client, order_id)

    assert resp.status_code in (302, 303)
    assert _row(order_id)[:3] == ("DRAWING", None, None)
    assert _visible(order_id)
    assert _event_count(order_id, EVENT_RESTORED) == 1
    assert _restored_audit_ids() == [order_id]


def test_restore_orders_mixed_restores_only_non_draft(client):
    _login(client, "rd_mixed")
    draft_id = _order(name="섞임-초안", status="DELETED", original_status=None,
                      deleted_at=_TRASHED_AT, draft=True)
    normal_id = _order(name="섞임-정상", status="DELETED", original_status="DRAWING",
                       deleted_at=_TRASHED_AT, draft=False, stage="DRAWING")
    draft_before = _row(draft_id)

    resp = _restore(client, draft_id, normal_id)

    assert resp.status_code in (302, 303)
    assert _row(draft_id) == draft_before
    assert _visible(normal_id) and _row(normal_id)[0] == "DRAWING"
    detail = _summary_detail()
    assert detail["count"] == 1
    assert detail["order_ids"] == [normal_id]
    assert detail["rejected_draft_ids"] == [draft_id]
    assert _restored_audit_ids() == [normal_id]
    categories = sorted(cat for cat, _msg in _flashes(client))
    assert categories == ["success", "warning"]


# --------------------------------------------------------------------------- #
# 2. 모바일 되돌리기 — 같은 술어로 409
# --------------------------------------------------------------------------- #
def test_mobile_restore_rejects_canonical_trashed_draft(client):
    actor_id = _login(client, "rd_mobile_draft")
    order_id = _canonical_trashed(name="모바일-초안", status="DRAFT", draft=True,
                                  actor_id=actor_id)
    before = _row(order_id)

    resp = client.post(f"/api/orders/{order_id}/mobile-restore", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == DRAFT_NOT_RESTORABLE_CODE
    assert _row(order_id) == before
    assert _event_count(order_id, EVENT_RESTORED) == 0


def test_mobile_restore_rejects_discarded_draft_with_draft_code(client):
    """버린 초안(status DELETED)은 옛 미러 문구(LEGACY_DELETED)가 아니라 초안 이유로 막힌다."""
    _login(client, "rd_mobile_discard")
    order_id = _order(name="모바일-버림", status="DELETED", original_status="DRAFT",
                      deleted_at=_TRASHED_AT, draft=True)
    before = _row(order_id)

    resp = client.post(f"/api/orders/{order_id}/mobile-restore", json={})

    assert resp.status_code == 409
    assert resp.get_json()["code"] == DRAFT_NOT_RESTORABLE_CODE
    assert _row(order_id) == before


def test_mobile_restore_negative_control_normal_order_restores(client):
    actor_id = _login(client, "rd_mobile_ctrl")
    order_id = _canonical_trashed(name="모바일-정상", status="MEASURE", draft=False,
                                  actor_id=actor_id)

    resp = client.post(f"/api/orders/{order_id}/mobile-restore", json={})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _row(order_id)[:3] == ("MEASURE", None, None)
    assert _visible(order_id)


# --------------------------------------------------------------------------- #
# 3. 버리기 기록 + 버린 초안의 왕복
# --------------------------------------------------------------------------- #
def _autosave_draft(client, token: str) -> int:
    resp = client.post(
        "/api/orders/erp/draft/autosave",
        data=json.dumps({"draft_token": token, "structured_data": {
            "entity_type": "order_structured", "schema_version": 1,
            "parties": {"customer": {"name": "버릴 고객", "phone": "010-5555-6666"}},
            "site": {"address_full": "인천 1", "address_main": "인천 1", "address_detail": ""},
            "schedule": {}, "items": [],
        }}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    order_id = resp.get_json()["order_id"]
    assert order_id
    return int(order_id)


def test_discard_records_original_status_and_event_then_restore_is_rejected(client):
    user_id = _login(client, "rd_discard")
    order_id = _autosave_draft(client, "tok-rd-discard")

    discard = client.post("/api/orders/erp/draft/discard", json={"draft_token": "tok-rd-discard"})
    assert discard.status_code == 200 and discard.get_json()["success"] is True

    status, original_status, deleted_at, flag, _version = _row(order_id)
    assert (status, original_status, flag) == ("DELETED", "DRAFT", True)
    assert deleted_at
    db_session.expire_all()
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "ORDER_DRAFT_DISCARDED")
        .all()
    )
    assert len(events) == 1
    assert events[0].created_by_user_id == user_id
    assert events[0].payload == {"via": "erp_draft"}

    # 같은 직원이 몇 분 뒤 휴지통에서 복원을 눌러도(#5078 의 순서) 숨은 주문이 생기지 않는다.
    before = _row(order_id)
    resp = _restore(client, order_id)
    assert resp.status_code in (302, 303)
    assert _row(order_id) == before
    assert not _visible(order_id)


# --------------------------------------------------------------------------- #
# 4. 휴지통 목록 표시
# --------------------------------------------------------------------------- #
def test_trash_list_marks_draft_rows_unrestorable(client):
    _login(client, "rd_list")
    draft_id = _order(name="목록초안고객", status="DELETED", original_status=None,
                      deleted_at=_TRASHED_AT, draft=True)
    normal_id = _order(name="목록정상고객", status="DELETED", original_status="MEASURE",
                       deleted_at=_TRASHED_AT, draft=False, stage="MEASURE")

    resp = client.get("/trash")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.count(f'<span class="badge bg-secondary">{DRAFT_NOT_RESTORABLE_LABEL}</span>') == 1
    assert f'<input type="checkbox" disabled title="{DRAFT_NOT_RESTORABLE_LABEL}"' in html
    assert f'name="selected_order" value="{normal_id}"' in html
    assert f'name="selected_order" value="{draft_id}"' not in html
