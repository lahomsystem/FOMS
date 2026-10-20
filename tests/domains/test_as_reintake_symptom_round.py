"""재접수 화면 회귀 (production #3455, 2026-10-20).

1. 접수 원문을 고치면 상단 "증상" 줄도 따라 바뀐다.
2. 건 기록 이전에 끝난 옛 AS(as_content 글만 남음)가 있으면 재접수 건은 2차로 보인다.
"""

from db import db_session
from models import Order
from foms.services.orders.as_round_chart import build_as_round_chart_view

from tests.domains.test_as_log_api import _as_log, _create_as_order, _login_as_admin


def _sd(order_id):
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data


def test_reception_edit_updates_symptom(client):
    _login_as_admin(client, username="as-reintake-symptom-admin")
    order_id = _create_as_order(status="CS").id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "서랍 안열림"}).status_code == 200
    rec = next(e for e in _as_log(order_id) if e["type"] == "reception")

    res = client.patch(f"/api/orders/{order_id}/as/log/{rec['id']}", json={"text": "서랍 안닫힘"})
    assert res.status_code == 200, res.get_data(as_text=True)

    sd = _sd(order_id)
    assert sd["shipment"]["as_content"] == "서랍 안닫힘"
    assert build_as_round_chart_view(sd)["symptom_preview"] == "서랍 안닫힘"


def test_symptom_prefers_current_reception_even_if_as_content_stale():
    sd = {
        "as_lifecycle": {"current_cycle_id": "c1", "cycles": [
            {"cycle_id": "c1", "initial_content": "안열림", "transitions": []}]},
        "shipment": {"as_content": "안열림", "as_log": [
            {"id": "r1", "type": "reception", "text": "안닫힘", "round": 1, "cycle_id": "c1",
             "ts": "2026-10-20T00:15:36"}]},
    }
    assert build_as_round_chart_view(sd)["symptom_preview"] == "안닫힘"


def test_reintake_after_pre_cycle_as_shows_round_two(client):
    _login_as_admin(client, username="as-reintake-round-admin")
    order_id = _create_as_order(status="CS", shipment_extra={"as_content": "막음판 누락 미시공"}).id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "서랍 안열림"}).status_code == 200

    view = build_as_round_chart_view(_sd(order_id))
    assert view["current_display_round"] == 2


def test_first_as_without_legacy_stays_round_one(client):
    _login_as_admin(client, username="as-reintake-round1-admin")
    order_id = _create_as_order(status="CS").id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "서랍 안열림"}).status_code == 200

    assert build_as_round_chart_view(_sd(order_id))["current_display_round"] == 1


def test_unedited_reintake_same_legacy_text_stays_round_one(client):
    _login_as_admin(client, username="as-reintake-same-admin")
    order_id = _create_as_order(status="CS", shipment_extra={"as_content": "서랍 안열림"}).id
    assert client.post(f"/api/orders/{order_id}/as/register",
                       json={"as_content": "서랍 안열림"}).status_code == 200

    assert build_as_round_chart_view(_sd(order_id))["current_display_round"] == 1


def test_as_push_text_uses_edited_reception():
    from types import SimpleNamespace

    from foms.services.channel_as_message import build_as_push_text

    sd = {
        "as_lifecycle": {"current_cycle_id": "c1", "cycles": [
            {"cycle_id": "c1", "initial_content": "안열림", "transitions": []}]},
        "shipment": {"as_content": "안열림", "as_log": [
            {"id": "r1", "type": "reception", "text": "안닫힘", "round": 1, "cycle_id": "c1",
             "ts": "2026-10-20T00:15:36"}]},
    }
    text = build_as_push_text(SimpleNamespace(structured_data=sd))
    assert "내용 : 안닫힘" in text and "안열림" not in text
