"""AS 화면 'AS도면' 칸 [도면팀 부탁] (설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §4.4).

AS 접수를 다시 저장하지 않고, 열린 AS 접수에 AS 도면 부탁(차수 WAITING)만 붙인다.
접수 창 체크(흐름 1)와 같은 차수 · 같은 알림 · 같은 폰 알림이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import foms.services.orders.as_drawing_notify as notify_mod
from db import db_session
from foms.services.orders import as_drawing as asd
from models import Notification, Order, SecurityLog
from tests.domains.test_as_drawing_round import (  # noqa: F401 - 픽스처도 함께 가져온다
    _as,
    _notices,
    _order,
    _reset_cache_runtime,
    _sd,
    _start,
    _user,
)

ROOT = Path(__file__).resolve().parents[2]
_PC_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130"}


def _request(client, oid, **body):
    return client.post(f"/api/orders/{oid}/drawing/as/request", json=body)


def _register(client, oid, content="문 처짐"):
    res = client.post(f"/api/orders/{oid}/as/register", json={"as_content": content})
    assert res.status_code == 200, res.get_json()


def _row(html: str, oid: int) -> str:
    m = re.search(rf'<tr id="as-row-{oid}".*?</tr>', html, re.S)
    assert m, f"AS 화면에 주문 {oid} 줄이 없다"
    return m.group(0)


def test_request_opens_waiting_round_without_reregistering_as(client, monkeypatch):
    pushed: list = []
    monkeypatch.setattr(notify_mod, "enqueue_push_for_notification",
                        lambda nid, db=None: pushed.append(db_session.get(Notification, nid).notification_type))
    admin = _user("asq_admin1", role="ADMIN", team="CS")
    drafter = _user("asq_draw1")
    oid = _order(name="부탁고객", drawing_ids=[drafter.id])
    _as(client, admin)
    _register(client, oid)
    before = _sd(oid)

    res = _request(client, oid, memo="오른쪽 문짝 1짝")

    body = res.get_json()
    assert res.status_code == 200, body
    assert body["success"] is True and body["error"] is None
    assert body["data"]["round"]["status"] == asd.STATUS_WAITING
    assert body["data"]["state"]["words"] == ["1차", "대기중"]
    after = _sd(oid)
    rnd = asd.current_round(after)
    assert rnd["source"] == asd.SOURCE_AS_REQUEST and rnd["memo"] == "오른쪽 문짝 1짝"
    assert rnd["cycle_id"] and rnd["cycle_id"] == asd.open_as_cycle_id(after)
    assert after[asd.AS_DRAWING_STATUS_KEY] == asd.STATUS_WAITING
    # AS 접수는 다시 저장하지 않는다 — 접수 기록 · AS 내용 · AS 건이 그대로다.
    assert after["shipment"]["as_log"] == before["shipment"]["as_log"]
    assert after["shipment"].get("as_content") == before["shipment"].get("as_content")
    assert asd.open_as_cycle_id(after) == asd.open_as_cycle_id(before)
    # 도면 담당에게 부탁 알림 + 폰 알림(흐름 1 과 같은 종류).
    notes = _notices(oid)
    assert [(n.title, n.target_type, n.target_user_id) for n in notes] == [("AS 도면 부탁", "USER", drafter.id)]
    assert pushed == ["AS_DRAWING_REQUEST"]
    logs = db_session.query(SecurityLog).filter_by(target_id=oid, action="AS_DRAWING_REQUESTED").all()
    assert len(logs) == 1 and "AS 도면 부탁" in (logs[0].message or "")


def test_request_without_drawing_assignee_goes_to_drawing_team(client):
    admin = _user("asq_admin2", role="ADMIN", team="CS")
    oid = _order(name="부탁고객2")
    _as(client, admin)
    _register(client, oid)

    assert _request(client, oid).status_code == 200

    rnd = asd.current_round(_sd(oid))
    assert rnd["memo"] == ""   # 비우면 화면이 AS 내용을 대신 보여 준다(흐름 1 과 같다)
    assert [(n.target_team) for n in _notices(oid)] == ["DRAWING"]


def test_request_refusals(client):
    admin = _user("asq_admin3", role="ADMIN", team="CS")
    _as(client, admin)

    building = _order(stage="CONSTRUCTION", name="시공중고객")
    _register(client, building)
    res = _request(client, building)
    assert res.status_code == 409 and res.get_json()["code"] == "NOT_AS_STAGE"

    no_as = _order(name="접수없는고객")
    res = _request(client, no_as)
    assert res.status_code == 409 and res.get_json()["code"] == "AS_NOT_OPEN"
    assert asd.rounds(_sd(no_as)) == []

    taken = _order(name="이미부탁고객")
    _register(client, taken)
    assert _request(client, taken).status_code == 200
    res = _request(client, taken, memo="또")
    body = res.get_json()
    assert res.status_code == 409 and body["code"] == "AS_DRAWING_OPEN" and body["success"] is False
    assert body["data"]["state"]["words"] == ["1차", "대기중"]   # 화면이 칸 글자를 지금 상태로 맞춘다
    assert len(asd.rounds(_sd(taken))) == 1

    partner = _order(name="협력사고객")
    _register(client, partner)
    db_session.get(Order, partner).partner_org_id = 999
    db_session.commit()
    res = _request(client, partner)
    assert res.status_code == 409 and res.get_json()["code"] == "PARTNER_ORDER"


def test_request_needs_sales_or_cs(client):
    admin = _user("asq_admin4", role="ADMIN", team="CS")
    drafter = _user("asq_draw4")
    oid = _order(name="권한고객")
    _as(client, admin)
    _register(client, oid)

    _as(client, drafter)
    res = _request(client, oid)

    assert res.status_code == 403
    assert asd.rounds(_sd(oid)) == []


def test_dashboard_cell_offers_request_only_when_allowed(client):
    admin = _user("asq_admin5", role="ADMIN", team="CS")
    drafter = _user("asq_draw5")
    _as(client, admin)
    ready = _order(name="부탁가능고객")
    _register(client, ready)
    asked = _order(name="부탁한고객")
    _register(client, asked)
    assert _request(client, asked).status_code == 200
    building = _order(stage="CONSTRUCTION", name="시공중줄고객")
    _register(client, building)
    started = _order(name="도면팀시작고객")
    _as(client, drafter)
    assert _start(client, started, memo="m", as_register={"content": "문 처짐"}).status_code == 200
    _as(client, admin)

    html = client.get("/erp/as?tab=incomplete", headers=_PC_UA).get_data(as_text=True)

    assert "data-as-drawing-request" in _row(html, ready)
    assert 'data-as-received="' in _row(html, ready)
    for oid in (asked, building, started):
        assert "data-as-drawing-request" not in _row(html, oid), oid
    assert '<span class="text-nowrap">1차</span> <span class="text-nowrap">대기중</span>' in _row(html, asked)
    # 'AS도면' 체크 칸 뜻은 그대로다(약식 도면 표시).
    assert 'class="form-check-input as-blueprint-checkbox"' in _row(html, ready)
    assert "js/cs/as-dashboard-drawing-request.js') }}?v=" not in html  # 렌더된 주소
    assert "/static/js/cs/as-dashboard-drawing-request.js?v=20261112a" in html


def test_dashboard_request_script_contract():
    js = (ROOT / "static/js/cs/as-dashboard-drawing-request.js").read_text(encoding="utf-8")
    assert "/drawing/as/request" in js and "data-as-drawing-request" in js
    assert "data.success" in js and "try {" in js            # fetch 는 try/catch + success 확인
    assert "AS_DRAWING_OPEN" in js                            # 이미 그리는 중이면 칸 글자를 맞춘다
    assert "innerHTML" not in js                              # 글자는 textContent 로만
    assert "__fomsAsDrawingRequestWired" in js                # fragment 재실행 가드
    css = (ROOT / "static/css/contexts/cs/as-dashboard-body.css").read_text(encoding="utf-8")
    assert ".erp-as-drawing-req-btn" in css
    # 칸이 54px 라 안내 글은 칸 안이 아니라 같은 화면 저장 알림(#saveToast)으로 낸다(로컬 실화면 11-12).
    assert "saveToast" in js
