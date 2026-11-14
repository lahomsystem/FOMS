"""채널톡 작은 창 접목 두 줄(설계서 2026-11-14-foms-graft 3.9 · 판 ⑤) — 근거 칩 · 할 일 제안 줄([같이 넣기] · [빼기]).

완료 기준: 관리 칸 끔이면 ``cs.draft.get`` · ``cs.draft.send`` 값과 틀이 지금과 같음 · 근거 주소가 FOMS 절대 주소 · 답 보내기가
실패하면 실행 안 함 · 성공하면 서명된 상담원에 이어진 직원 이름으로 승인 · 한 번만 · [빼기]는 거절(``other``) · 이어진 사용자 없음 ·
권한 없음 · 다른 차례의 제안 번호는 받지 않음 · 로그에 손님 글 · 넣을 글 없음. 채널톡 · 보내기 · 알림은 가짜(네트워크 0), 합성 글만.
"""

from __future__ import annotations

import datetime
import logging

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.brain.models import BrainObject
from foms.persistence.graft.models import ErpActionProposal
from foms.services.brain.usage_events import record_uses
from foms.services.cs_agent import wam_functions
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.graft_settings import GRAFT_ACTIONS_FIELD, GRAFT_EVIDENCE_FIELD
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import lifecycle, runners
from foms.services.erp_actions.runners import SERVICE_RUNNERS
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.construction_note import note_lines
from models import ChannelManagerLink, Order, SecurityLog, SystemSetting, User
from tests.domains.test_cs_drafting import DRAFT, channel  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_send import FakeSender, posted, ready  # noqa: F401 — ready 는 fixture
from tests.domains.test_cs_wam_send import call
from tests.support.cs_agent_fakes import api_message, at, keys  # noqa: F401 — keys 는 fixture

NOTE = "채널톡 상담: 합성 문 소리 표지 — 시공 때 확인"  # 넣을 글 표지 — 로그에 나오면 안 된다
BASE = "https://foms.example.test"
OLD_GET_KEYS = {"code", "ok", "blocked", "draft", "fresh_note", "checking", "edit_reasons", "max_text", "detail",
                "max_detail"}


@pytest.fixture(autouse=True)
def quiet_notifications(monkeypatch):
    """시공 메모 실행 뒤 도면팀 알림 마무리(푸시)는 가짜 — 바깥으로 아무것도 나가지 않는다."""
    calls: list = []
    monkeypatch.setattr(runners, "finalize_note_notifications", lambda db, result: calls.append(result))
    return calls


def graft(*, evidence=True, actions=True):
    row = db_session.get(SystemSetting, st.SETTINGS_KEY)
    row.setting_value = {**row.setting_value, GRAFT_EVIDENCE_FIELD: evidence, GRAFT_ACTIONS_FIELD: actions}
    db_session.commit()


def staff(name="graft", role="STAFF", team="CS", manager="mgr-7"):
    """채널톡 상담원에 이어진 합성 직원 번호."""
    user = User(username=f"wam-graft-{name}", password=generate_password_hash("pw"), role=role, team=team,
                name="합성 직원", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(ChannelManagerLink(channel_manager_id=manager, user_id=user.id, is_active=True))
    db_session.commit()
    return user.id


def order(construction_days=6):
    """시공일이 앞날인 합성 주문 번호(작은 창 함수가 공용 세션을 닫아 ORM 줄은 떨어진다 — 번호만 들고 다닌다)."""
    day = (get_today_kst() + datetime.timedelta(days=construction_days)).isoformat()
    sd = {"workflow": {"stage": "PRODUCTION"}, "schedule": {"construction": {"date": day, "time": "오전"}}}
    row = Order(received_date="2030-01-01", customer_name="합성손님", phone="010" + "-0000-" + "0000", address="합성 주소",
                product="합성 품목", status="PRODUCTION", is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(row, sd)
    db_session.add(row)
    db_session.commit()
    return row.id


def lines_of(order_id):
    db_session.expire_all()
    return note_lines(db_session.get(Order, order_id).structured_data)


def proposal(turn_id, target, *, action="add_construction_note", params=None, source_ref=None):
    made = lifecycle.propose(db_session, action=action, proposed_by="agent:cs", order=db_session.get(Order, target),
                             params=params if params is not None else {"note": NOTE}, reason="합성 이유",
                             evidence=[], source_kind="cs_turn", source_ref=source_ref or str(turn_id), level=2,
                             now=now_utc_naive())
    db_session.commit()
    return made.id


def brain_item(key, *, visibility="all", name="합성 선반 깊이"):
    db_session.add(BrainObject(item_key=key, version=1, brand="COMMON", layer="common", item_type="fact", name=name,
                               text="합성 설명", status="active", visibility=visibility, confidence="confirmed",
                               created_by="import", payload={"doc_id": key.split("/")[-1]}))
    db_session.commit()


def fresh(proposal_id):
    db_session.expire_all()
    return db_session.get(ErpActionProposal, proposal_id)


def send(app, channel, turn_id, sender, manager="mgr-7", **extra):
    return call(app, channel, "cs.draft.send", {"turn": turn_id, "chat": "uc-1", **extra}, manager=manager,
                sender=sender)["result"]


# ── 끔 = 지금 그대로 ──────────────────────────────────────────────────────
def test_switches_off_keep_get_send_and_the_frame_as_today(app, client, ready):
    turn_id = posted(ready)
    pid = proposal(turn_id, order())
    got = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert set(got) == OLD_GET_KEYS and got["draft"] == DRAFT
    sent = send(app, ready, turn_id, FakeSender(ready))
    assert set(sent) == {"code", "ok", "message", "outcome"} and sent["code"] == "sent"
    assert fresh(pid).status == "open"  # 제안은 손대지 않는다
    html = client.get("/channel/wam/cs-draft").get_data(as_text=True)
    assert "cs-wam-evidence" not in html and "cs-wam-action" not in html and "app-graft.js" not in html
    assert 'src="app.js?v=' in html and "style=" not in html


# ── 근거 칩 · 작은 창 줄 ─────────────────────────────────────────────────
def test_get_carries_three_chips_with_absolute_links_and_the_inline_action(app, ready, monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", BASE)
    graft()
    turn_id = posted(ready)
    target = order()
    for key in ("common/a-one", "common/b-two", "common/c-three"):
        brain_item(key)
    brain_item("common/z-admin", visibility="admin", name="관리자만 항목")
    record_uses(db_session, ["common/a-one", "common/z-admin", "common/b-two", "common/c-three",
                             f"erp:order/{target}"], "cs_draft", "cs_turn", turn_id, now_utc_naive())
    db_session.commit()
    pid = proposal(turn_id, target)
    got = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    chips = got["evidence"]
    assert [c["kind"] for c in chips] == ["brain", "brain", "order"]  # 셋까지 — 주문은 한 자리를 둔다
    assert all(c["href"].startswith(BASE + "/") for c in chips)  # 채널톡이 거쳐 여는 창 — 절대 주소만
    assert chips[0] == {"kind": "brain", "label": "사실 · 합성 선반 깊이", "href": BASE + "/brain/items/common/a-one"}
    assert chips[2]["href"] == f"{BASE}/erp/orders/{target}" and chips[2]["label"].startswith(f"주문 #{target} · 시공 ")
    assert "관리자만" not in str(chips)  # 보기 범위가 좁은 항목은 이름도 싣지 않는다
    assert got["action"] == {"id": pid, "label": "시공 메모 더하기", "text": f'주문 #{target} "{NOTE}"'}
    monkeypatch.delenv("FOMS_BASE_URL")
    assert all(c["href"] is None for c in call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})
               ["result"]["evidence"])  # 주소를 모르면 상대 주소 대신 글만


def test_only_the_switched_on_line_is_added(app, ready):
    graft(evidence=False, actions=True)
    turn_id = posted(ready)
    got = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert set(got) == OLD_GET_KEYS | {"action"} and got["action"] is None
    graft(evidence=True, actions=False)
    got = call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})["result"]
    assert set(got) == OLD_GET_KEYS | {"evidence"} and got["evidence"] == []


# ── [같이 넣기] · [빼기] ──────────────────────────────────────────────────
def test_with_action_runs_once_after_the_send_in_the_senders_name(app, ready):
    graft()
    person_id = staff()
    turn_id = posted(ready)
    target = order()
    pid = proposal(turn_id, target)
    sender = FakeSender(ready)
    first = send(app, ready, turn_id, sender, with_action=pid)
    assert first["code"] == "sent" and first["action"] == {"code": "executed", "ok": True, "message": "시공 메모를 더했어요."}
    row = fresh(pid)
    assert (row.status, row.decided_by) == ("executed", person_id)
    base = row.base_version
    audit = db_session.query(SecurityLog).filter_by(action="ERP_ACTION_APPROVED").one()
    assert audit.user_id == person_id and audit.detail["proposal_id"] == pid
    assert lines_of(target) == [NOTE]
    again = send(app, ready, turn_id, sender, with_action=pid)
    assert again["code"] == "already" and "action" not in again and len(sender.calls) == 1
    with pytest.raises(lifecycle.ActionError) as twice:
        lifecycle.approve(db_session, pid, actor=db_session.get(User, person_id), runners=SERVICE_RUNNERS,
                          base_version=base, now=now_utc_naive())
    assert twice.value.code == "ACTION_NOT_OPEN"
    assert lines_of(target) == [NOTE]  # 한 번만


def test_a_failed_send_never_runs_the_action(app, ready):
    graft()
    staff()
    turn_id = posted(ready)
    target = order()
    pid = proposal(turn_id, target)
    ready.messages["uc-1"].append(api_message("m-new", at(2, 8, 58), "user", "합성 새 글"))
    result = send(app, ready, turn_id, FakeSender(ready), with_action=pid)
    assert result["code"] == "new_message" and "action" not in result
    assert fresh(pid).status == "open" and lines_of(target) == []


def test_drop_rejects_the_proposal_with_other(app, ready):
    graft()
    person_id = staff()
    turn_id = posted(ready)
    pid = proposal(turn_id, order())
    result = send(app, ready, turn_id, FakeSender(ready), drop_action=pid)
    assert result["action"] == {"code": "rejected", "ok": True, "message": "할 일 제안을 뺐어요."}
    row = fresh(pid)
    assert (row.status, row.reject_code, row.decided_by) == ("rejected", "other", person_id)


def test_no_linked_user_or_no_permission_keeps_the_proposal_open(app, ready):
    graft()
    staff(name="viewer", role="VIEWER", manager="mgr-viewer")
    turn_id = posted(ready)
    target = order()
    pid = proposal(turn_id, target)
    nobody = send(app, ready, turn_id, FakeSender(ready), manager="mgr-unlinked", with_action=pid)
    assert nobody["code"] == "sent" and nobody["action"]["code"] == "no_user" and nobody["action"]["ok"] is False
    assert fresh(pid).status == "open"
    turn_two = posted(ready, chat="uc-2")
    pid_two = proposal(turn_two, target, params={"note": "채널톡 상담: 합성 둘째 표지 — 시공 때 확인"})
    viewer = call(app, ready, "cs.draft.send", {"turn": turn_two, "chat": "uc-2", "with_action": pid_two},
                  manager="mgr-viewer", sender=FakeSender(ready))["result"]
    assert viewer["code"] == "sent" and viewer["action"]["code"] == "ACTION_FORBIDDEN"
    assert fresh(pid_two).status == "open" and lines_of(target) == []


def test_a_proposal_of_another_turn_or_a_queue_only_action_is_not_taken(app, ready):
    graft()
    staff()
    turn_id = posted(ready)
    target = order()
    other = proposal(turn_id, target, source_ref="999")  # 다른 차례의 제안 번호(작은 창 값은 믿지 않는다)
    first = send(app, ready, turn_id, FakeSender(ready), with_action=other)
    assert first["code"] == "sent" and first["action"]["code"] == "not_found" and fresh(other).status == "open"
    turn_two = posted(ready, chat="uc-2")
    day = (get_today_kst() + datetime.timedelta(days=9)).isoformat()
    queue_only = proposal(turn_two, target, action="move_construction", params={"date": day, "time": ""})
    moved = call(app, ready, "cs.draft.send", {"turn": turn_two, "chat": "uc-2", "with_action": queue_only},
                 sender=FakeSender(ready))["result"]
    assert moved["code"] == "sent" and moved["action"]["code"] == "not_found"  # 승인 대기로만 가는 할 일
    assert fresh(queue_only).status == "open"
    db_session.expire_all()
    assert db_session.get(Order, target).erp_construction_date != day


def test_an_execution_that_cannot_run_is_one_line_and_the_reply_stays_sent(app, ready):
    graft()
    staff()
    turn_id = posted(ready)
    target = order()
    pid = proposal(turn_id, target)
    row = db_session.get(Order, target)
    row.structured_data = {**row.structured_data, "notes": "글 한 칸 메모"}  # 시공 메모를 줄로 더할 수 없는 주문
    db_session.commit()
    result = send(app, ready, turn_id, FakeSender(ready), with_action=pid)
    assert result["code"] == "sent" and result["action"]["code"] == "ACTION_PRECONDITION"
    assert result["action"]["ok"] is False and "주문 화면에서 적어 주세요" in result["action"]["message"]
    assert fresh(pid).status == "open"


def test_logs_carry_no_draft_or_note_text(app, ready, caplog):
    graft()
    staff()
    turn_id = posted(ready)
    pid = proposal(turn_id, order())
    caplog.set_level(logging.DEBUG, logger="foms")
    call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"})
    send(app, ready, turn_id, FakeSender(ready), with_action=pid)
    assert "[CS 작은 창]" in caplog.text
    for mark in (DRAFT, NOTE, "합성 문 소리 표지"):
        assert mark not in caplog.text


# ── 틀 · 함수 목록 ───────────────────────────────────────────────────────
def test_the_frame_adds_two_empty_slots_and_the_script_only_when_on(app, client, ready):
    graft()
    html = client.get("/channel/wam/cs-draft/").get_data(as_text=True)
    assert 'id="cs-wam-evidence"' in html and 'id="cs-wam-action"' in html
    assert html.index('src="app-graft.js?v=') < html.index('src="app.js?v=')  # 다리를 먼저 싣는다(같은 defer 차례)
    assert "style=" not in html and 'src="/' not in html and 'href="/' not in html and "<script>" not in html
    graft(evidence=True, actions=False)
    only = client.get("/channel/wam/cs-draft/").get_data(as_text=True)
    assert 'id="cs-wam-evidence"' in only and 'id="cs-wam-action"' not in only and "app-graft.js" in only
    script = client.get("/channel/wam/cs-draft/app-graft.js")
    assert script.status_code == 200 and "FOMS_WAM_GRAFT" in script.get_data(as_text=True)
    assert "javascript" in script.mimetype


def test_the_send_function_lists_the_two_new_fields():
    (schema,) = [s for s in wam_functions.FUNCTION_SCHEMAS if s["name"] == wam_functions.SEND]
    props = schema["inputSchema"]["properties"]
    assert props["with_action"] == {"type": "integer"} and props["drop_action"] == {"type": "integer"}
