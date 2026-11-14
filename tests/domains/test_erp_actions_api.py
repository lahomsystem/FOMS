"""승인 대기 ERP 할 일 API(설계서 2026-11-14-foms-graft 3.6, 머리 ``/api/erp-actions``) — 답 꼴 · 캐시 머리글 · 길 일곱.

- 읽기: 수(``on`` · 할 일 이름 셋) · 주문 칩(100개까지 · 넘으면 400) · 카드(수 · 거절 까닭 · 어림 초) · 자세히(이유 · 바뀌는 칸 ·
  차례 · 2주 승인율 · 넣을 값 고를 값 · 기준 판 · 사유 물음).
- 쓰기: 승인(실행기는 가짜) · 두 번 누름 409 · 기준 판 바뀜 409 + 새 카드 · 실패는 ``success`` 거짓 · 꼴 400 · 거절 · 나중에.
- 승인 대기 읽기는 되맞추기를 먼저 돌린다. 스위치 끔 → 모든 길 404 · 로그인 안 함 → 401.
요청이 끝나면 세션이 닫혀 ORM 객체가 떨어지므로 시험은 번호 · 값만 들고 다닌다. 합성 계정 · 합성 주문 · 합성 글만.
"""

from __future__ import annotations

import dataclasses
import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.erp_action_runners import RUNNERS
from foms.persistence.graft.models import ErpActionProposal
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import registry
from foms.services.erp_actions.lifecycle import propose
from foms.services.erp_actions.runners import RunOutcome
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, User

BASE = "/api/erp-actions"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def switches(monkeypatch):
    """접목판 스위치를 모두 끈 뒤 회사 지식 새 화면 · 할 일만 모두에게 켠다."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for env in ("FOMS_GRAFT_BRAIN_UI", "FOMS_GRAFT_ACTIONS"):
        monkeypatch.setenv(f"{env}_ENABLED", "1")
        monkeypatch.setenv(f"{env}_COHORT", "all")
    return monkeypatch


def _order(stage: str, construction=None) -> Order:
    sd = {"workflow": {"stage": stage}}
    if construction:
        sd["schedule"] = {"construction": {"date": construction[0], "time": construction[1]}}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _propose(order, action, agent, params, level) -> dict:
    row = propose(db_session, action=action, proposed_by=agent, order=order, params=params, reason="합성 이유",
                  evidence=[{"kind": "order", "ref": f"erp:order/{order.id}", "label": "주문"}], source_kind="sweep",
                  source_ref="1", level=level, now=now_utc_naive())
    db_session.commit()
    assert row is not None
    return {"id": row.id, "base_version": row.base_version, "preview": list(row.preview)}


@pytest.fixture
def world(app, switches):
    admin = User(username="api_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                 is_active=True)
    db_session.add(admin)
    db_session.commit()
    orders = [_order("RECEIVED"), _order("CONFIRM", construction=(_day(3), "오전")), _order("DRAWING")]
    rows = [
        _propose(orders[0], "schedule_construction", "agent:schedule", {"date": _day(9), "time": "오전"}, 2),
        _propose(orders[1], "add_construction_note", "agent:cs", {"note": "자재 먼저 내림"}, 2),
        _propose(orders[2], "assign_draftsman", "agent:ops", {}, 1),
    ]
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
    return {"client": client, "admin_id": admin.id, "order_ids": [order.id for order in orders], "rows": rows}


def _as_link(monkeypatch, name: str = "assign_draftsman") -> None:
    """판 1 끝에는 바로가기 할 일이 없다(D206 · T14) — 바로가기 꼴은 하나를 바꿔 끼워 본다."""
    monkeypatch.setitem(registry.ACTIONS, name, dataclasses.replace(registry.ACTIONS[name], mode=registry.MODE_LINK))


def _data(resp, status=200):
    assert resp.status_code == status, resp.get_data(as_text=True)
    assert resp.headers["Cache-Control"] == "private, no-store"
    body = resp.get_json()
    assert set(body) == {"success", "data", "error"}
    return body


def test_badge_counts_labels_and_switch_state(world):
    body = _data(world["client"].get(f"{BASE}/badge"))
    assert body["success"] is True and body["error"] is None
    data = body["data"]
    assert data["on"] == {"actions": True, "pc": False, "tablet": False, "mobile": False}
    assert data["actions"] == 3 and data["total"] == data["actions"] + data["knowledge"]
    assert set(data["labels"]) == {"시공 잡기", "시공 메모 더하기", "도면 담당 맡기기"}


def test_open_chips_one_query_and_limit(world, monkeypatch):
    _as_link(monkeypatch)
    a, b, c = world["order_ids"]
    items = _data(world["client"].get(f"{BASE}/open?order_ids={a},{b},{c},x,{a}"))["data"]["items"]
    assert set(items) == {str(a), str(b), str(c)}
    assert items[str(a)]["label"] == "시공 잡기" and items[str(a)]["can_decide"] is True
    assert items[str(a)]["agent_label"] == "일정 AI" and items[str(c)]["can_decide"] is False
    many = ",".join(str(n) for n in range(1, 102))
    assert _data(world["client"].get(f"{BASE}/open?order_ids={many}"), 400)["data"]["fields"] == ["order_ids"]


def test_inbox_cards_counts_and_reject_codes(world):
    data = _data(world["client"].get(f"{BASE}/inbox"))["data"]
    assert len(data["cards"]) == 3 and data["counts"]["total"] == 3 and data["counts"]["snoozed"] == 0
    assert data["counts"]["by_agent"] == {"cs": 1, "schedule": 1, "ops": 1}
    assert [code["value"] for code in data["reject_codes"]] == ["wrong_date", "misread", "no_slot", "already_done",
                                                               "other"]
    assert data["est_seconds"] == 90
    first = next(card for card in data["cards"] if card["action"] == "schedule_construction")
    keys = {"id", "action", "action_label", "agent", "agent_label", "title", "created_at", "order_id", "order_href",
            "field", "before", "after", "evidence", "level", "mode", "phone_ok", "base_changed", "status", "snoozed"}
    assert set(first) == keys and first["mode"] == "run" and first["base_changed"] is False
    assert first["title"].startswith(f"시공 잡기 — #{first['order_id']} ")
    assert first["evidence"] == [{"kind": "order", "label": "주문", "href": f"/erp/orders/{first['order_id']}"}]


def test_detail_has_reason_changes_steps_rate_params(world):
    row = world["rows"][0]
    data = _data(world["client"].get(f"{BASE}/proposals/{row['id']}"))["data"]
    assert data["reason"] == "합성 이유" and data["changes"] == row["preview"]
    assert data["base_version"] == row["base_version"] and data["source_label"] == "훑기 규칙에서 나옴"
    assert data["rate"] == {"days": 14, "decided": 0, "approved": 0, "pct": None}
    assert data["steps"][0].startswith("FOMS 시공일")
    time_param = next(p for p in data["params"] if p["name"] == "time")
    assert time_param["value"] == "오전" and [c["value"] for c in time_param["choices"]] == ["", "오전", "오후", "종일"]
    assert data["change_reason"]["required"] is False and data["result"] is None
    assert _data(world["client"].get(f"{BASE}/proposals/{row['id'] + 99}"), 404)["error"] == "찾을 수 없습니다."


def test_approve_runs_once_then_409(world, monkeypatch):
    calls = []
    monkeypatch.setitem(RUNNERS, "schedule_construction",
                        lambda session, req: (calls.append(req.actor_id), RunOutcome.executed("합성 실행"))[1])
    row = world["rows"][0]
    body = {"base_version": row["base_version"], "view_ms": 2000, "decided_by": 999}
    data = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/approve", json=body))["data"]
    assert data["status"] == "executed" and data["message"] == "합성 실행"
    assert calls == [world["admin_id"]]  # 본문의 사람 칸은 읽지 않는다
    again = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/approve", json=body), 409)
    assert again["data"] == {"code": "ACTION_NOT_OPEN"} and len(calls) == 1
    rate = _data(world["client"].get(f"{BASE}/proposals/{row['id']}"))["data"]["rate"]
    assert rate == {"days": 14, "decided": 1, "approved": 1, "pct": 100}


def test_approve_base_changed_returns_new_card(world, monkeypatch):
    monkeypatch.setitem(RUNNERS, "add_construction_note", lambda s, r: pytest.fail("실행하면 안 된다"))
    order, row = db_session.get(Order, world["order_ids"][1]), world["rows"][1]
    order.structured_data = {**order.structured_data, "notes": {"construction_note": "새로 적힌 메모"}}
    db_session.commit()
    body = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/approve",
                                      json={"base_version": row["base_version"]}), 409)
    assert body["data"]["code"] == "ACTION_BASE_CHANGED" and body["data"]["card"]["id"] == row["id"]
    assert body["data"]["card"]["changes"][0]["before"] == "1줄"


def test_approve_failed_and_shape_errors(world, monkeypatch):
    monkeypatch.setitem(RUNNERS, "schedule_construction", lambda s, r: RunOutcome.failed(sent=False))
    row, link = world["rows"][0], world["rows"][2]
    failed = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/approve",
                                        json={"base_version": row["base_version"]}))
    assert failed["success"] is False and failed["data"]["status"] == "failed" and failed["error"]
    missing = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/approve", json={}), 400)
    assert missing["data"] == {"code": "ACTION_SHAPE", "fields": ["base_version"]}
    _as_link(monkeypatch)
    shape = _data(world["client"].post(f"{BASE}/proposals/{link['id']}/approve",
                                       json={"base_version": link["base_version"]}), 400)
    assert shape["data"] == {"code": "ACTION_SHAPE", "fields": ["action"]}


def test_reject_and_snooze_routes(world):
    row, other = world["rows"][0], world["rows"][1]
    bad = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/reject", json={"code": "lazy"}), 400)
    assert bad["data"]["fields"] == ["code"]
    done = _data(world["client"].post(f"{BASE}/proposals/{row['id']}/reject", json={"code": "wrong_date"}))["data"]
    assert done == {"id": row["id"], "status": "rejected", "reject_code": "wrong_date"}
    snoozed = _data(world["client"].post(f"{BASE}/proposals/{other['id']}/snooze"))["data"]
    assert snoozed["status"] == "open" and snoozed["snoozed_until"].endswith("06:00")
    counts = _data(world["client"].get(f"{BASE}/inbox"))["data"]["counts"]
    assert (counts["total"], counts["snoozed"]) == (1, 1)
    assert _data(world["client"].get(f"{BASE}/badge"))["data"]["actions"] == 1


def test_inbox_read_reconciles_stuck_rows(world):
    pid = world["rows"][0]["id"]
    stuck = db_session.get(ErpActionProposal, pid)
    stuck.status, stuck.decided_at, stuck.decided_by = "executing", now_utc_naive() - datetime.timedelta(minutes=9), 1
    db_session.commit()
    _data(world["client"].get(f"{BASE}/inbox"))
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, pid).status == "open"


def test_switch_off_is_404_and_signed_out_is_401(app, world, monkeypatch):
    pid = world["rows"][0]["id"]
    paths = [("get", f"{BASE}/badge"), ("get", f"{BASE}/open?order_ids=1"), ("get", f"{BASE}/inbox"),
             ("get", f"{BASE}/proposals/{pid}"), ("post", f"{BASE}/proposals/{pid}/approve"),
             ("post", f"{BASE}/proposals/{pid}/reject"), ("post", f"{BASE}/proposals/{pid}/snooze")]
    for method, path in paths:
        assert _data(getattr(app.test_client(), method)(path, json={}), 401)["error"] == "로그인이 필요합니다."
    monkeypatch.setenv("FOMS_GRAFT_ACTIONS_ENABLED", "0")
    for method, path in paths:
        assert _data(getattr(world["client"], method)(path, json={"base_version": 1, "code": "other"}), 404)
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, pid).status == "open"
