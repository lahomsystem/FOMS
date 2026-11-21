"""시공일 옮기기 "어느 날을 어느 날로" (설계서 2026-11-21-item-construction-done 8절 · N8).

스위치(``FOMS_ITEM_CONSTRUCTION_DONE_ENABLED``)가 켜져 있으면 주문 날짜 목록에서 고른 날 하나만 새 날로 바꾸고,
그 날이 적힌 제품 칸 날짜도 같이 옮긴다. 꺼져 있으면 지금처럼 주문 칸을 날 하나로 통째로 바꾼다.

부르는 곳마다 옮길 날을 준다 — 출고 화면(고른 날) · 협력사 판 확정 · 되돌리기(첫 날) · 시공 불가 다시 잡기(그 방문 날) ·
대시보드 칸(첫 날) · AI 실행(오늘 이후 가장 가까운 날). 합성 주문만.
"""
from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.services.orders.construction_schedule as schedule_mod
from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import runners
from foms.services.erp_actions.runners import SERVICE_RUNNERS, RunRequest
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.construction_schedule import (
    FROM_DATE_MISSING_MESSAGE,
    ScheduleInputError,
    first_order_date,
    move_construction_date,
    move_first_date_for_field,
    reschedule_text_after_fail,
    revert_to_partner_request,
    visit_order_date,
)
from models import Order, User

FLAG = "FOMS_ITEM_CONSTRUCTION_DONE_ENABLED"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setenv(FLAG, "0")


def _sd(order_dates: str, item_dates: list) -> dict:
    items = []
    for idx, day in enumerate(item_dates):
        item = {"product_name": f"제품{idx}"}
        if day is not None:
            item["construction_date"] = day
        items.append(item)
    return {"workflow": {"stage": "PRODUCTION"},
            "parties": {"customer": {"name": "합성손님", "phone": "010-0000-0000"}},
            "site": {"address_full": "합성 주소", "address_main": "합성 주소"},
            "items": items, "schedule": {"construction": {"date": order_dates, "time": ""}}, "shipment": {}}


# ── 순수 함수 ─────────────────────────────────────────────────────────────
def test_두_날_주문은_고른_날_하나와_그_날_제품만_옮긴다():
    sd = _sd("2026-12-05, 2026-12-17", ["2026-12-05", "2026-12-17", None, "2026-12-05, 2026-12-17"])
    moved = move_construction_date(sd, from_date="2026-12-17", to_date="2026-12-20")
    assert moved == "2026-12-17"
    assert sd["schedule"]["construction"]["date"] == "2026-12-05, 2026-12-20"
    assert [it.get("construction_date") for it in sd["items"]] == [
        "2026-12-05", "2026-12-20", None, "2026-12-05, 2026-12-20"]


def test_옮긴_날이_다른_날과_겹치면_하나로_합치고_정렬한다():
    sd = _sd("2026-12-17, 2026-12-05", ["2026-12-05", "2026-12-17"])
    move_construction_date(sd, from_date="2026-12-17", to_date="2026-12-01")
    assert sd["schedule"]["construction"]["date"] == "2026-12-01, 2026-12-05"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-12-05", "2026-12-01"]


def test_날_하나_주문은_지금처럼_새_날이_되고_그_날_제품도_같이_옮긴다():
    sd = _sd("2026-12-05", ["2026-12-05", "2026-12-09"])
    assert move_construction_date(sd, from_date=None, to_date="2026-12-10") == "2026-12-05"
    assert sd["schedule"]["construction"]["date"] == "2026-12-10"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-12-10", "2026-12-09"]


def test_옮길_날이_없으면_오늘_이후_가장_가까운_날():
    sd = _sd("2026-11-05, 2026-12-17", ["2026-11-05", "2026-12-17"])
    moved = move_construction_date(sd, from_date="", to_date="2026-12-24", today=datetime.date(2026, 11, 21))
    assert moved == "2026-12-17"
    assert sd["schedule"]["construction"]["date"] == "2026-11-05, 2026-12-24"
    # 모두 지났으면 마지막 날
    sd = _sd("2026-11-05, 2026-11-17", ["2026-11-05", "2026-11-17"])
    assert move_construction_date(sd, from_date=None, to_date="2026-12-24",
                                  today=datetime.date(2026, 11, 21)) == "2026-11-17"


def test_주문에_없는_날을_고르면_거절하고_고치지_않는다():
    sd = _sd("2026-12-05, 2026-12-17", ["2026-12-05", "2026-12-17"])
    for bad in ("2026-12-06", "엉터리"):
        with pytest.raises(ScheduleInputError) as exc:
            move_construction_date(sd, from_date=bad, to_date="2026-12-20")
        assert str(exc.value) == FROM_DATE_MISSING_MESSAGE == "옮길 날을 다시 골라 주세요."
    assert sd["schedule"]["construction"]["date"] == "2026-12-05, 2026-12-17"


def test_제품_칸에만_있는_날도_옮길_수_있다():
    sd = _sd("2026-12-05", ["2026-12-05", "2026-12-17"])
    move_construction_date(sd, from_date="2026-12-17", to_date="2026-12-19")
    assert sd["schedule"]["construction"]["date"] == "2026-12-05"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-12-05", "2026-12-19"]


def test_시공일이_하나도_없으면_지금처럼_새_날을_쓴다():
    sd = {"items": [{"product_name": "가"}]}
    assert move_construction_date(sd, from_date="2026-12-05", to_date="2026-12-10") == ""
    assert sd["schedule"]["construction"]["date"] == "2026-12-10"


def test_주문_칸이_비면_제품_칸은_그대로_두고_주문_칸만_쓴다(flag_on):
    sd = _sd("", ["2026-12-05", "2026-12-17"])
    assert move_construction_date(sd, from_date="2026-12-05", to_date="2026-12-10") == ""
    assert sd["schedule"]["construction"]["date"] == "2026-12-10"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-12-05", "2026-12-17"]
    assert move_first_date_for_field(_sd("", ["2026-12-05", "2026-12-17"]), "2026-12-10") is None


def test_이틀_연속_주문은_나눠_시공이_아니라_지금처럼_통째로(flag_on):
    sd = _sd("2026-12-05, 2026-12-06", [None, None])
    assert move_first_date_for_field(sd, "2026-12-20") is None
    assert move_construction_date(sd, from_date="2026-12-06", to_date="2026-12-20") == ""
    assert sd["schedule"]["construction"]["date"] == "2026-12-20"
    assert reschedule_text_after_fail(_sd("2026-12-05, 2026-12-06", [None]), "2026-12-20", None) == "2026-12-20"


def test_새_날이_이미_날_목록에_있고_옮길_날이_없으면_날은_그대로():
    sd = _sd("2026-12-05,2026-12-17", ["2026-12-05", "2026-12-17"])
    assert move_construction_date(sd, from_date=None, to_date="2026-12-17") == ""
    assert sd["schedule"]["construction"]["date"] == "2026-12-05,2026-12-17"


def test_옮겨도_날_목록이_같으면_원래_글을_둔다():
    sd = _sd("2026-12-05,2026-12-17", ["2026/12/05", "2026-12-17"])
    assert move_construction_date(sd, from_date="2026-12-05", to_date="2026-12-05") == ""
    assert sd["schedule"]["construction"]["date"] == "2026-12-05,2026-12-17"
    assert [it["construction_date"] for it in sd["items"]] == ["2026/12/05", "2026-12-17"]


def test_첫_날은_정렬하지_않고_글에_처음_적힌_날(flag_on):
    assert first_order_date(_sd("2026-12-17, 2026-12-05", [])) == "2026-12-17"
    assert first_order_date(_sd("엉터리, 2026-12-09", [])) == "2026-12-09"
    assert first_order_date(_sd("", [])) == ""
    sd = _sd("2026-12-17, 2026-12-05", ["2026-12-05", "2026-12-17"])
    assert move_first_date_for_field(sd, "2026-12-20") == "2026-12-17"
    assert sd["schedule"]["construction"]["date"] == "2026-12-05, 2026-12-20"


def test_방문_날은_그날_이하_가장_늦은_시공일_없으면_뒤_가장_가까운_날(flag_on):
    sd = _sd("2026-11-05, 2026-11-17", ["2026-11-05", "2026-11-17"])
    assert visit_order_date(sd, datetime.date(2026, 11, 6)) == "2026-11-05"   # 늦게 온 방문
    assert visit_order_date(sd, datetime.date(2026, 11, 17)) == "2026-11-17"
    assert visit_order_date(sd, datetime.date(2026, 11, 3)) == "2026-11-05"   # 일찍 온 방문
    assert visit_order_date(sd, datetime.date(2026, 11, 30)) == "2026-11-17"
    # 11/05 방문을 하루 늦게(11/06 한국 오전) 시작했다가 시공 불가 — 11/05 를 옮긴다(11/17 은 그대로)
    started = datetime.datetime(2026, 11, 6, 0, 30)  # UTC 00:30 = 한국 09:30
    assert reschedule_text_after_fail(sd, "2026-11-25", started) == "2026-11-17, 2026-11-25"
    assert [it["construction_date"] for it in sd["items"]] == ["2026-11-25", "2026-11-17"]


def test_빈_새_날은_그_날만_뺀다():
    sd = _sd("2026-12-05, 2026-12-17", ["2026-12-05", "2026-12-17"])
    move_construction_date(sd, from_date="2026-12-05", to_date="")
    assert sd["schedule"]["construction"]["date"] == "2026-12-17"
    assert sd["items"][0]["construction_date"] == ""


def test_대시보드_칸_도우미는_스위치가_꺼지거나_여러_날이면_손대지_않는다(monkeypatch):
    sd = _sd("2026-12-05, 2026-12-17", ["2026-12-05", "2026-12-17"])
    monkeypatch.setenv(FLAG, "0")
    assert move_first_date_for_field(sd, "2026-12-08") is None
    assert reschedule_text_after_fail(sd, "2026-12-08", None) == "2026-12-08"
    monkeypatch.setenv(FLAG, "1")
    assert move_first_date_for_field(sd, "2026-12-08, 2026-12-09") is None
    assert move_first_date_for_field(sd, "") is None
    assert sd["schedule"]["construction"]["date"] == "2026-12-05, 2026-12-17"
    assert move_first_date_for_field(sd, "2026-12-08") == "2026-12-05"
    assert sd["schedule"]["construction"]["date"] == "2026-12-08, 2026-12-17"
    assert sd["items"][0]["construction_date"] == "2026-12-08"


# ── DB · API ──────────────────────────────────────────────────────────────
def _user(username: str, *, role: str = "ADMIN", team: str | None = None) -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
                name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _order(order_dates: str, item_dates: list, *, stage: str = "PRODUCTION", partner_org_id=None) -> int:
    sd = _sd(order_dates, item_dates)
    sd["workflow"]["stage"] = stage
    order = Order(received_date="2026-07-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="붙박이장", status=stage, manager_name="담당", is_erp_order=True, structured_data=sd,
                  erp_stage_code=stage, partner_org_id=partner_org_id)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _saved(order_id: int) -> tuple[str, list]:
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    return sd["schedule"]["construction"]["date"], [it.get("construction_date") for it in sd["items"]]


def _post_schedule(client, order_id: int, body: dict):
    return client.post(f"/api/orders/{order_id}/construction-schedule", json=body)


def test_출고_화면_길은_고른_날만_옮기고_응답에_새_날_목록(client, flag_on):
    _login(client, _user("mv_route"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)])
    resp = _post_schedule(client, oid, {"date": _day(12), "time": "오전", "from_date": _day(10)})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["date"] == f"{_day(3)}, {_day(12)}"
    assert _saved(oid) == (f"{_day(3)}, {_day(12)}", [_day(3), _day(12)])
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_construction_date == _day(3)


def test_출고_화면_길_옮길_날이_없으면_가장_가까운_날_틀리면_400(client, flag_on):
    _login(client, _user("mv_route2"))
    oid = _order(f"{_day(-5)}, {_day(4)}", [_day(-5), _day(4)])
    resp = _post_schedule(client, oid, {"date": _day(6), "time": ""})
    assert resp.status_code == 200, resp.get_json()
    assert _saved(oid) == (f"{_day(-5)}, {_day(6)}", [_day(-5), _day(6)])
    bad = _post_schedule(client, oid, {"date": _day(8), "time": "", "from_date": _day(4)})
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "옮길 날을 다시 골라 주세요." and bad.get_json()["success"] is False
    assert _saved(oid) == (f"{_day(-5)}, {_day(6)}", [_day(-5), _day(6)])


def test_스위치를_끄면_지금처럼_통째로_바꾸고_제품_칸은_그대로(client, flag_off):
    _login(client, _user("mv_off"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)])
    resp = _post_schedule(client, oid, {"date": _day(12), "time": "", "from_date": _day(99)})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["date"] == _day(12)
    assert _saved(oid) == (_day(12), [_day(3), _day(10)])


def test_대시보드_칸은_첫_날을_옮긴다(client, flag_on):
    _login(client, _user("mv_field"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)], stage="RECEIVED")
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "scheduled_date", "value": _day(5)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid) == (f"{_day(5)}, {_day(10)}", [_day(5), _day(10)])


def test_대시보드_칸_스위치_끄면_통째로(client, flag_off):
    _login(client, _user("mv_field_off"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)], stage="RECEIVED")
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "scheduled_date", "value": _day(5)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid) == (_day(5), [_day(3), _day(10)])


def test_시공_불가_다시_잡기는_그_방문_날을_옮긴다(client, flag_on):
    _login(client, _user("mv_fail", role="STAFF", team="CONSTRUCTION"))
    oid = _order(f"{_day(0)}, {_day(10)}", [_day(0), _day(10)], stage="CONSTRUCTION")
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200
    resp = client.post(f"/api/orders/{oid}/construction/fail",
                       json={"reason": "site_issue", "detail": "현장 재방문", "reschedule_date": _day(3)})
    assert resp.status_code == 200, resp.get_json()
    assert _saved(oid) == (f"{_day(3)}, {_day(10)}", [_day(3), _day(10)])
    db_session.expire_all()
    assert db_session.get(Order, oid).structured_data["schedule"]["construction"]["rescheduled"] is True


def test_시공_불가_다시_잡기_스위치_끄면_통째로(client, flag_off):
    _login(client, _user("mv_fail_off", role="STAFF", team="CONSTRUCTION"))
    oid = _order(f"{_day(0)}, {_day(10)}", [_day(0), _day(10)], stage="CONSTRUCTION")
    assert client.post(f"/api/orders/{oid}/construction/start", json={}).status_code == 200
    resp = client.post(f"/api/orders/{oid}/construction/fail",
                       json={"reason": "site_issue", "detail": "현장 재방문", "reschedule_date": _day(3)})
    assert resp.status_code == 200, resp.get_json()
    assert _saved(oid) == (_day(3), [_day(0), _day(10)])


def test_협력사_판_되돌리기는_통째로_비우고_확정은_옮길_날_없이(app, flag_on, monkeypatch):
    admin = _user("mv_partner")
    seen: list = []
    real = schedule_mod.write_construction_schedule
    monkeypatch.setattr(schedule_mod, "write_construction_schedule",
                        lambda *a, **k: (seen.append(k.get("from_date")), real(*a, **k))[1])
    oid = _order(f"{_day(4)}, {_day(9)}", [_day(4), _day(9)], stage="CONFIRM")
    revert_to_partner_request(db_session, db_session.get(Order, oid), admin)
    db_session.commit()
    assert seen == [None]
    assert _saved(oid) == ("", [_day(4), _day(9)])  # 주문 칸만 통째로 빈다(지금과 같다)

    # 확정: 확정 대기 주문은 시공일이 비어 있어 옮길 날 없이(빈 글) 지금처럼 쓴다.
    monkeypatch.setattr(schedule_mod, "request_open", lambda sd, stage: True)
    oid3 = _order("", [None], stage="CONFIRM")
    schedule_mod.confirm_partner_request(db_session, db_session.get(Order, oid3), admin, date=_day(5), time="")
    db_session.commit()
    assert seen[-1] == ""
    assert _saved(oid3) == (_day(5), [None])


def test_AI_실행은_오늘_이후_가장_가까운_날을_옮긴다(app, flag_on, monkeypatch):
    monkeypatch.setattr(runners, "finalize_schedule_notifications", lambda db, result: None)
    admin = _user("mv_ai")
    oid = _order(f"{_day(-3)}, {_day(4)}, {_day(9)}", [_day(-3), _day(4), _day(9)], stage="CONFIRM")
    req = RunRequest(proposal_id=41, action="move_construction", order_id=oid,
                     params={"date": _day(6), "time": ""}, actor=admin, now=now_utc_naive())
    out = SERVICE_RUNNERS["move_construction"](db_session, req)
    assert out.status == "executed", out.message
    assert _saved(oid) == (f"{_day(-3)}, {_day(6)}, {_day(9)}", [_day(-3), _day(6), _day(9)])


def test_출고팀_화면은_시공일_목록을_data_칸으로_받는다(client, flag_on):
    import html
    import json

    _login(client, _user("mv_ship", role="STAFF", team="SHIPMENT"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)], stage="RECEIVED")
    body = client.get(f"/edit/{oid}?open=erp-order").get_data(as_text=True)
    assert 'data-erp-construction-only="true"' in body
    marker = 'data-erp-construction-dates="'
    raw = body[body.index(marker) + len(marker):].split('"', 1)[0]
    assert json.loads(html.unescape(raw)) == [_day(3), _day(10)]


def test_출고팀_화면_스위치_끄면_빈_목록(client, flag_off):
    _login(client, _user("mv_ship_off", role="STAFF", team="SHIPMENT"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)], stage="RECEIVED")
    body = client.get(f"/edit/{oid}?open=erp-order").get_data(as_text=True)
    assert 'data-erp-construction-dates="[]"' in body


def _date_changes(order_id: int) -> int:
    from models import OrderFieldChange

    db_session.expire_all()
    return (db_session.query(OrderFieldChange)
            .filter(OrderFieldChange.order_id == order_id, OrderFieldChange.path == "schedule.construction.date")
            .count())


def test_출고_화면_시간만_바꾸면_날은_그대로_날_바뀜_기록_없음(client, flag_on):
    _login(client, _user("mv_time"))
    oid = _order(f"{_day(3)},{_day(10)}", [_day(3), _day(10)])
    resp = _post_schedule(client, oid, {"date": _day(10), "time": "오후"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["from_date"] == "" and data["split"] is True
    assert data["all_construction_dates"] == [_day(3), _day(10)]
    assert _saved(oid) == (f"{_day(3)},{_day(10)}", [_day(3), _day(10)])
    db_session.expire_all()
    assert db_session.get(Order, oid).structured_data["schedule"]["construction"]["time"] == "오후"
    assert _date_changes(oid) == 0
    # 같은 날로 옮기기(옮길 날 = 새 날)도 날 목록이 같아 기록 · 알림이 없다
    same = _post_schedule(client, oid, {"date": _day(3), "time": "오후", "from_date": _day(3)})
    assert same.status_code == 200 and same.get_json()["data"]["from_date"] == ""
    assert _date_changes(oid) == 0


def test_출고_화면_응답의_날_목록은_옮긴_뒤_목록(client, flag_on):
    _login(client, _user("mv_resp"))
    oid = _order(f"{_day(3)}, {_day(10)}", [_day(3), _day(10)])
    data = _post_schedule(client, oid, {"date": _day(12), "time": "", "from_date": _day(3)}).get_json()["data"]
    assert data["from_date"] == _day(3) and data["all_construction_dates"] == [_day(10), _day(12)]
    assert _date_changes(oid) == 1


def test_대시보드_칸_이틀_연속_주문은_지금처럼_통째로(client, flag_on):
    _login(client, _user("mv_consec"))
    oid = _order(f"{_day(3)}, {_day(4)}", [None], stage="RECEIVED")
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "scheduled_date", "value": _day(20)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid) == (_day(20), [None])


def test_대시보드_칸_주문_칸이_비면_제품_칸은_그대로(client, flag_on):
    _login(client, _user("mv_empty"))
    oid = _order("", [_day(3), _day(10)], stage="RECEIVED")
    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "scheduled_date", "value": _day(5)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid) == (_day(5), [_day(3), _day(10)])


def test_AI_미리보기는_옮길_날_새_날_끝남은_새_날이_목록에_있음(app, flag_on, monkeypatch):
    from foms.services.erp_actions import preview

    oid = _order(f"{_day(-3)}, {_day(4)}, {_day(9)}", [_day(-3), _day(4), _day(9)], stage="CONFIRM")
    order = db_session.get(Order, oid)
    params = {"date": _day(6), "time": ""}
    row = preview._preview_schedule(order, params, first=False)[0]
    assert row["before"] == preview._when(_day(4), "") and row["after"] == preview._when(_day(6), "")
    assert preview._verify_schedule(order, params, first=False) is False
    sd = dict(order.structured_data)
    sd["schedule"] = {"construction": {"date": f"{_day(-3)}, {_day(6)}, {_day(9)}", "time": ""}}
    order.structured_data = sd
    assert preview._verify_schedule(order, params, first=False) is True
    monkeypatch.setenv(FLAG, "0")
    assert preview._verify_schedule(order, params, first=False) is False  # 꺼지면 지금처럼 글 전체가 같아야
