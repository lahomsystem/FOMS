"""AS 접수 취소 — 접수 전 값으로 되돌리기 (설계서 2026-11-20-multi-item-split-schedule §4.4).

새 건 접수는 덮기 전 값을 건의 ``pre_register`` 에 남기고(상태 글 · AS 축 · 접수일 · 완료일 · 상차일 · 시공자 ·
비용 판정 · 전달 배정), 취소는 그 값으로 되돌린다. 그 값이 없는 건(이 기능 전에 접수된 건)은 남은 건 · 본 흐름 단계로
되돌리고, 앞선 AS 기록이 건 없이 남아 있으면 접수 전 상태를 알 수 없어 막는다.
기본 계약(권한 · 상태 · 건 장부 · 기록 줄 · 단추)은 tests/domains/test_as_cancel.py. 이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.orders import sales_delivery_link as sdl
from foms.services.orders.as_cycle_cancel import PRIOR_UNKNOWN_MESSAGE
from foms.services.orders.state_axes import read_as_status
from models import OrderEvent
from tests.domains.test_as_cancel import _cancel, _login, _order, _register, _reload


def _edit_sd(order_id: int, change) -> None:
    """주문 structured_data 를 사본으로 고쳐 다시 넣는다(시험 준비용)."""
    order = _reload(order_id)
    sd = copy.deepcopy(order.structured_data)
    change(sd)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _strip_pre_register(order_id: int) -> None:
    """이 기능 전에 접수된 건처럼 만든다 — 건에서 접수 전 값을 뗀다."""
    _edit_sd(order_id, lambda sd: [c.pop("pre_register", None) for c in sd["as_lifecycle"]["cycles"]])


def _add_old_log_line(order_id: int) -> None:
    line = {"id": "al_old_1", "ts": "2020-01-01T00:00:00", "by": "가짜옛사람", "by_id": None,
            "type": "memo", "text": "옛 AS 기록", "round": 1}
    _edit_sd(order_id, lambda sd: sd["shipment"]["as_log"].insert(0, line))


def test_cancel_restores_a_finished_legacy_as_that_had_no_cycle_record(client) -> None:
    """건 기록 없이 끝나 있던 옛 AS(AS_COMPLETED)에 잘못 재접수 → 취소하면 끝난 AS 그대로 돌아온다."""
    _login(client)
    oid = _order(stage="CS", status="AS_COMPLETED")
    legacy = _reload(oid)
    legacy.as_axis_status, legacy.as_received_date, legacy.as_completed_date = "COMPLETED", "2026-09-01", "2026-09-10"
    db_session.commit()

    _register(client, oid, "잘못 누른 재접수")
    mid = _reload(oid)
    assert mid.status == "AS_RECEIVED" and mid.as_completed_date is None
    prior = mid.structured_data["as_lifecycle"]["cycles"][0]["pre_register"]
    assert prior["status"] == "AS_COMPLETED" and prior["as_axis_status"] == "COMPLETED"
    assert prior["as_received_date"] == "2026-09-01" and prior["as_completed_date"] == "2026-09-10"

    resp = _cancel(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    saved = _reload(oid)
    assert saved.status == "AS_COMPLETED" and saved.as_axis_status == "COMPLETED"
    assert saved.as_received_date == "2026-09-01" and saved.as_completed_date == "2026-09-10"
    assert saved.structured_data["as_lifecycle"]["cycles"] == []
    event = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="AS_CANCELLED").one()
    assert event.payload["restored_from"] == "pre_register"


def test_cancel_restores_a_legacy_logistics_status(client) -> None:
    """접수 전 SCHEDULED(옛 물류 글)였던 주문은 취소 뒤 SCHEDULED 로 돌아온다 — 단계 글(CONSTRUCTION)이 아니다."""
    _login(client)
    oid = _order(stage="CONSTRUCTION", status="SCHEDULED")
    _register(client, oid)
    assert _reload(oid).status == "AS_RECEIVED"
    assert _cancel(client, oid).status_code == 200
    saved = _reload(oid)
    assert saved.status == "SCHEDULED" and saved.as_axis_status is None
    assert saved.structured_data["workflow"]["stage"] == "CONSTRUCTION"


def test_cancel_puts_back_the_workers_and_loading_date_the_reception_overwrote(client) -> None:
    # 2026-11-23: 접수는 시공자 칸을 비운다(시공이 끝난 주문만) — 접수한 사람 이름을 넣지 않는다.
    _login(client)
    oid = _order(stage="CS")
    order = _reload(oid)
    order.shipping_scheduled_date = "2026-11-10"
    db_session.commit()
    _register(client, oid, source_screen="erp_construction_dashboard", shipping_scheduled_date="2026-12-05")
    mid = _reload(oid)
    assert mid.structured_data["shipment"]["construction_workers"] == []
    assert mid.shipping_scheduled_date == "2026-12-05"

    assert _cancel(client, oid).status_code == 200
    saved = _reload(oid)
    assert saved.structured_data["shipment"]["construction_workers"] == ["가짜기사"]
    assert saved.shipping_scheduled_date == "2026-11-10" and saved.status == "CS"

    # 대조군 1: 시공이 아직 남은 주문(본 흐름 열림)은 접수가 시공자 칸을 건드리지 않는다 — 남은 시공일의 시공자다.
    still_building = _order(stage="CONSTRUCTION")
    _register(client, still_building, source_screen="erp_construction_dashboard")
    assert _reload(still_building).structured_data["shipment"]["construction_workers"] == ["가짜기사"]

    # 대조군 2: 다시 접수(열린 건에 한 번 더)는 정해 둔 AS 담당을 지우지 않는다.
    again = _order(stage="CS")
    _register(client, again)
    _edit_sd(again, lambda sd: sd["shipment"].update(construction_workers=["가짜AS기사"]))
    _register(client, again, content="가짜 문짝 처짐 — 다시 접수")
    assert _reload(again).structured_data["shipment"]["construction_workers"] == ["가짜AS기사"]

    # 대조군 3: 접수 뒤에 누가 시공자를 다시 고쳤으면 취소가 그 값을 덮지 않는다.
    edited = _order(stage="CS")
    _register(client, edited, source_screen="erp_construction_dashboard")
    _edit_sd(edited, lambda sd: sd["shipment"].update(construction_workers=["가짜새기사"]))
    assert _cancel(client, edited).status_code == 200
    assert _reload(edited).structured_data["shipment"]["construction_workers"] == ["가짜새기사"]


def test_cycle_without_pre_register_is_refused_when_older_as_records_remain(client) -> None:
    """접수 전 값이 없는 건(이 기능 전에 접수)에서 앞선 AS 기록이 건 없이 남아 있으면 접수 전 상태를 모른다 — 막는다.
    대조군: 앞선 기록이 없으면 본공정 단계로 되돌린다."""
    _login(client)
    blocked = _order(stage="CS")
    _register(client, blocked)
    _strip_pre_register(blocked)
    _add_old_log_line(blocked)
    resp = _cancel(client, blocked)
    assert resp.status_code == 409 and resp.get_json()["error"] == PRIOR_UNKNOWN_MESSAGE
    still = _reload(blocked)
    assert still.status == "AS_RECEIVED" and len(still.structured_data["as_lifecycle"]["cycles"]) == 1

    clean = _order(stage="CS")
    _register(client, clean)
    _strip_pre_register(clean)
    assert _cancel(client, clean).status_code == 200
    saved = _reload(clean)
    assert saved.status == "CS" and saved.as_axis_status is None
    event = db_session.query(OrderEvent).filter_by(order_id=clean, event_type="AS_CANCELLED").one()
    assert event.payload["restored_from"] == "stage"


def test_cancel_keeps_a_hold_set_after_the_reception(client) -> None:
    """열린 AS + 보류(ON_HOLD) → 취소해도 보류는 남는다(상태 글이 AS 글일 때만 되돌린다)."""
    _login(client)
    for strip in (False, True):  # 접수 전 값이 있는 건 · 없는 건 모두
        oid = _order(stage="PRODUCTION")
        _register(client, oid)
        if strip:
            _strip_pre_register(oid)
        resp = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "ON_HOLD"})
        assert resp.status_code == 200 and _reload(oid).status == "ON_HOLD"

        assert _cancel(client, oid).status_code == 200
        saved = _reload(oid)
        assert saved.status == "ON_HOLD" and saved.as_axis_status is None, strip
        assert saved.structured_data["as_lifecycle"]["cycles"] == [] and read_as_status(saved) == "NONE"


@pytest.mark.parametrize("with_pre_register", [True, False])
def test_cancel_drops_a_billing_decision_made_inside_the_cancelled_cycle(client, with_pre_register) -> None:
    """취소한 건에서 확정한 유상 판정은 걷는다 — 남으면 정산에 잡힌다. 건 이전의 옛 확정은 그대로 둔다(대조군)."""
    _login(client)
    oid = _order(stage="CS")
    _register(client, oid)
    resp = client.post(f"/api/orders/{oid}/as/billing", json={"type": "paid", "amount": 30000, "reason": "고객 과실"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    billing = _reload(oid).structured_data["shipment"]["as_billing"]
    assert billing["type"] == "paid" and billing["confirmed"] is True and billing["amount"] == 30000
    if not with_pre_register:
        _strip_pre_register(oid)
    assert _cancel(client, oid).status_code == 200
    assert "as_billing" not in _reload(oid).structured_data["shipment"]

    old_billing = {"type": "paid", "confirmed": True, "amount": 70000, "reason": "옛 판정",
                   "decided_by": "가짜옛사람", "decided_at": "2026-01-05T00:00:00"}
    keep = _order(stage="CS", sd_extra={"shipment": {"as_billing": dict(old_billing)}})
    _register(client, keep)
    if not with_pre_register:
        _strip_pre_register(keep)
    assert _cancel(client, keep).status_code == 200
    assert _reload(keep).structured_data["shipment"]["as_billing"] == old_billing


def test_cancel_puts_the_sales_delivery_assignment_back(client) -> None:
    """취소한 건에서 만든 전달 배정은 치우고, 접수 전에 있던 배정(남은 건의 전달 기록)은 그대로 되돌린다."""
    _login(client)

    def _write_link(order_id: int, ref: int) -> None:
        _edit_sd(order_id, lambda sd: sdl.write_link(sd, ref_order_id=ref, ref_date="2026-12-01",
                                                     ref_manager="가짜영업", actor_user_id=None, actor_name="가짜사람"))

    fresh = _order(stage="CS")
    _register(client, fresh)
    _write_link(fresh, 901)
    assert _cancel(client, fresh).status_code == 200
    assert sdl.read_link(_reload(fresh).structured_data) is None  # 다음 접수 뒤 옛 배정이 살아나지 않는다

    kept = _order(stage="CS")
    _write_link(kept, 902)           # 접수 전부터 있던 배정
    _register(client, kept)
    _write_link(kept, 903)           # 취소할 건에서 바꾼 배정
    assert _cancel(client, kept).status_code == 200
    assert sdl.read_link(_reload(kept).structured_data)["ref_order_id"] == 902

    old = _order(stage="CS")         # 접수 전 값이 없는 건: 이 건을 연 뒤의 배정만 치운다
    _register(client, old)
    _write_link(old, 904)
    _strip_pre_register(old)
    assert _cancel(client, old).status_code == 200
    assert sdl.read_link(_reload(old).structured_data) is None


def test_cancel_reason_longer_than_500_is_400(client) -> None:
    _login(client)
    oid = _order(stage="CS")
    _register(client, oid)
    resp = _cancel(client, oid, "가" * 501)
    assert resp.status_code == 400 and "500자" in resp.get_json()["error"]
    assert _reload(oid).status == "AS_RECEIVED"
    assert _cancel(client, oid, "가" * 500).status_code == 200


def test_cancel_script_closes_the_window_first_and_clears_the_reception_draft() -> None:
    """창 안 단추: 사유를 묻기 전에 창을 닫고(Bootstrap 포커스 가둠), 성공하면 그 주문의 접수 초안을 지운다."""
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-as-cancel.js").read_text(encoding="utf-8")
    handler = js[js.index("document.addEventListener('click'"):]
    assert handler.index("closeHostModal(btn") < handler.index("askReason(")
    assert "hidden.bs.modal" in js and "inst.hide()" in js
    send = js[js.index("async function sendCancel"):js.index("document.addEventListener('click'")]
    assert send.index("await clearReceiveDraft(orderId)") < send.index("window.location.reload()")
    assert "window.fomsAsReceiveDraft" in js and "window.__erpAsReceiveDraftKey = ''" in js
    draft = (root / "static/js/orders/as-receive-draft.js").read_text(encoding="utf-8")
    assert "window.fomsAsReceiveDraft = {" in draft and "clear: clear" in draft and "__erpAsReceiveDraftKey" in draft
