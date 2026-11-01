"""협력사 주문 '실측 예정' · '도면 요청'(사용자 결정 2026-11-01).

운영에서 협력사 주문 24건 중 13건이 실측 전에 들어와 바로 도면 단계 · 도면팀 알림 · 빈 영발로 나갔다. 이제:
실측을 마쳤고(실측일이 오늘이거나 그 전) 제품마다 가로 치수가 있을 때만 도면 단계, 아니면 실측 예정(MEASURE).
실측 예정에선 영발이 닫히고, "실측 끝 · 도면 요청"이 도면 단계로 넘기며 영발을 한 번 보낸다.
대조군: 조건이 맞는 주문 · 다른 회사 · 우리 직원 · 이미 도면 단계. 채널톡 전송은 가짜로 바꿔 끼운다.
스펙: docs/specs/2026-11-01-partner-measure-pending_SPEC.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from db import db_session
from foms.services.partners.measure_ready import drawing_request_missing
from models import Notification, Order, OrderEvent, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _PAYLOAD,
    _client,
    _create,
    world,
)
from tests.security.test_partner_channel_push import channel  # noqa: F401 — pytest fixture 재노출

ROOT = Path(__file__).resolve().parents[2]
_PRE = {**_PAYLOAD, "measured_on": "2099-11-13",
        "items": [{"product_name": "아일랜드", "internal": "상담", "spec_rows": [{"spec_width": ""}]}]}


def _make(app, world, payload) -> dict:
    resp = _create(app, world["partner_a"], payload)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _teams(order_id: int) -> set[str]:
    return {n.target_team for n in db_session.query(Notification).filter(Notification.order_id == order_id)}


def test_missing_rule_needs_past_measure_date_and_width_per_item() -> None:
    items = [{"product_name": "붙박이장", "spec_rows": [{"spec_width": "2400"}]},
             {"product_name": "아일랜드", "spec_rows": [{"spec_width": ""}]}]
    assert drawing_request_missing("2026-11-01", items[:1], today="2026-11-01") == []
    missing = drawing_request_missing("2026-11-13", items, today="2026-11-01")
    assert missing == ["실측일(2026-11-13)이 아직 오지 않았습니다.", "아일랜드의 가로 치수를 넣어 주세요."]
    assert drawing_request_missing("", items[:1], today="2026-11-01") == ["실측일을 넣어 주세요."]


def test_ready_order_still_goes_straight_to_drawing(app, world):
    data = _make(app, world, {**_PAYLOAD, "measured_done": True})
    order = db_session.get(Order, data["order_id"])
    assert data["stage"] == "DRAWING" and data["missing"] == []
    assert order.erp_stage_code == "DRAWING" and order.measurement_completed is True
    assert _teams(order.id) == {"DRAWING", "CS"}
    assert order.structured_data["partner_intake"]["measured_done"] is True


@pytest.mark.parametrize("payload", [
    {**_PRE, "measured_done": False},                       # 아직이에요
    {**_PRE, "measured_done": True},                        # 마쳤다고 했지만 실측일 미래 · 가로 치수 없음
    {**_PAYLOAD, "measured_done": False},                   # 조건은 맞지만 협력사가 아직이라고 골랐다
])
def test_pre_measure_order_waits_without_drawing_team_or_measure_push(app, world, payload):
    data = _make(app, world, payload)
    order = db_session.get(Order, data["order_id"])
    assert data["stage"] == "MEASURE"
    assert order.erp_stage_code == "MEASURE" and order.measurement_completed is False
    assert order.structured_data["assignments"]["owner_team"] == "CS"
    assert _teams(order.id) == {"CS"}  # 도면팀은 도면 요청 때
    client = _client(app, db_session.get(User, world["partner_a"]))
    state = client.get(f"/api/partner/orders/{order.id}/channel-push").get_json()["data"]["state"]
    assert state["measurement"]["open"] is False and "도면 요청" in state["measurement"]["reason"]
    resp = client.post(f"/api/partner/orders/{order.id}/channel-push", json={"kind": "measurement"})
    assert resp.status_code == 409
    page = client.get(f"/partner/orders/{order.id}").get_data(as_text=True)
    assert "data-pp-request-drawing" in page and "실측 예정" in page and "영발 도면 요청 뒤" in page


def test_request_drawing_refuses_until_measure_data_then_moves_and_pushes_once(app, world, channel):
    order_id = _make(app, world, {**_PRE, "measured_done": False})["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/request-drawing")
    assert resp.status_code == 400
    assert "아일랜드의 가로 치수를 넣어 주세요." in resp.get_json()["data"]["missing"]
    assert db_session.get(Order, order_id).erp_stage_code == "MEASURE" and channel == []

    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["partner_intake"] = {**sd["partner_intake"], "measured_on": "2026-10-01"}
    sd["items"] = [{**sd["items"][0], "spec_rows": [{"spec_width": "1800", "spec_depth": "", "spec_height": ""}]}]
    order.structured_data = sd
    db_session.commit()

    resp = client.post(f"/api/partner/orders/{order_id}/request-drawing")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["push_note"] == "영발방에 보냈습니다."
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order.erp_stage_code == "DRAWING" and order.measurement_completed is True
    assert order.structured_data["assignments"]["owner_team"] == "DRAWING"
    assert "DRAWING" in _teams(order_id)
    assert len(channel) == 1 and channel[0]["push_kind"] == "measurement" and channel[0]["is_retry"] is False
    assert not channel[0]["text"].startswith("[실측 완료]")
    events = {e.event_type for e in db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id)}
    assert "MEASUREMENT_COMPLETED" in events
    assert client.post(f"/api/partner/orders/{order_id}/request-drawing").status_code == 409  # 이미 도면 단계


def test_request_drawing_after_empty_push_resends_with_measure_done_mark(app, world, channel):
    """실측 예정 때 빈 영발이 먼저 나간 주문(운영 13건) — 도면 요청 때 "[실측 완료]" 재전송."""
    order_id = _make(app, world, {**_PAYLOAD, "measured_done": False})["order_id"]
    order = db_session.get(Order, order_id)
    order.structured_data = {**order.structured_data,
                             "channeltalk_push": {"pushed": True, "sent_at": "2026-10-31T05:13:00+00:00"}}
    db_session.commit()
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/request-drawing")
    assert resp.status_code == 200, resp.get_json()
    assert channel[-1]["is_retry"] is True
    assert channel[-1]["text"].startswith("[실측 완료]\n")
    assert channel[-1]["change_note"].startswith("[실측 완료]")


def test_request_drawing_only_own_company_and_partner_accounts(app, world):
    order_id = _make(app, world, {**_PAYLOAD, "measured_done": False})["order_id"]
    other = _client(app, db_session.get(User, world["partner_b"]))
    assert other.post(f"/api/partner/orders/{order_id}/request-drawing").status_code == 404
    staff = _client(app, db_session.get(User, world["staff"]))
    assert staff.post(f"/api/partner/orders/{order_id}/request-drawing").status_code in (302, 403)
    assert db_session.get(Order, order_id).erp_stage_code == "MEASURE"


def test_hq_queue_card_shows_partner_measure_chip_only_while_pending(app, world):
    render = app.jinja_env.get_template("partials/shared/channel_mark.html").module.partner_push_marks
    pending = {"workflow": {"stage": "MEASURE"}, "partner_intake": {"measured_on": "2026-11-13"}}
    html = str(render(pending))
    assert "협력사 실측 11-13" in html and "foms-partner-push__item--measure" in html and 'style="' not in html
    assert "item--measure" not in str(render({**pending, "workflow": {"stage": "DRAWING"}}))


def test_new_order_form_asks_measured_and_no_first_save_push_prompt() -> None:
    form = (ROOT / "templates/partner/new_order.html").read_text(encoding="utf-8")
    assert 'name="measured_done"' in form and "실측을 마쳤나요?" in form
    js = (ROOT / "static/js/partner/partner-channel-push.js").read_text(encoding="utf-8")
    assert "본사 영발방에도 지금 보낼까요" not in js and "offerAfterCreate" not in js
    assert "afterCreate" in (ROOT / "static/js/partner/partner-portal.js").read_text(encoding="utf-8")
