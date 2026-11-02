"""주간 고침 안(설계서 17.6.1 (e) · (f) 시험 7 · 사장님 결정 D94) — 근거 관문 · 자동 반영 0 · 사장님 승인만 · 떼어 둔 줄 0 ·
주 한 번 · 숫자 세탁 막기 · 부딪침 판정.

합성 차례 · 합성 승인 지식(:data:`tests.domains.test_cs_drafting.KNOWLEDGE`) · 가짜 모델(구조화 출력)만 — 네트워크 · 손님 글 ·
직원 이름 · 금액 없음. 시각은 2026-11 KST(11-02 월 — 창 안은 04:00).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from db import db_session
from foms.services.cs_agent import brain_spend, turns, weekly_fix, weekly_fix_gates, weekly_fix_store
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.edit_detail_settings import DETAIL_FIELDS, WEEKLY_FIELD
from foms.services.cs_agent.knowledge import load_approved, read_stored
from models import CsAgentTurn, CsAgentTurnPhoto, SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_send import user
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys, naive  # noqa: F401

NOW = at(2, 4)  # 월요일 KST 04:00
NEW_TEXT = "평일 낮에 상담을 도와 드립니다. 주말 문의는 다음 평일 낮에 이어서 안내드립니다."
NO_CONFLICT = {"verdicts": [{"index": 0, "conflict": False}]}


def panel(**extra):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, WEEKLY_FIELD: True, "learning_cap_usd_panel": "5.00", **extra}))
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "on", "draft": "memo"}))
    db_session.commit()


def edited(n: int, *, chat: str, staff: int, held_out: bool = False, reason="missing", detail="합성 — 주말 안내가 빠졌다",
           intent="hours", when=None) -> int:
    row = CsAgentTurn(brand="LAHOM", chat_id=chat, last_user_message_id=f"m-{n}", state="posted", outcome="edited",
                      intent=intent, edit_reason=reason, edit_detail_masked=detail, sent_by_user_id=staff,
                      masked_question="합성 주말에도 상담돼요?", staff_reply_masked="합성 고친 답 — 주말 문의는 평일에 이어서",
                      sent_at=naive(when or at(1, 10)), held_out=held_out)
    db_session.add(row)
    db_session.commit()
    return row.id


def proposal(ids, text=NEW_TEXT, item_id="hours-day", group=0):
    return {"proposals": [{"group": group, "item_id": item_id, "proposed_text": text,
                           "why": "합성 — 주말 문의 안내가 빠져 직원이 고쳤다", "evidence_turn_ids": list(ids)}]}


def stored():
    return weekly_fix_store.list_proposals(db_session)


@pytest.fixture
def ready(channel):  # noqa: F811
    panel()
    return channel


@pytest.fixture
def two_by_two(ready):
    """서로 다른 손님 2 · 직원 2 묶음(근거 관문을 넘는다)."""
    return [edited(1, chat="uc-1", staff=11), edited(2, chat="uc-2", staff=12)]


# ── 근거 관문 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("chats, staff", [(("uc-1", "uc-1"), (11, 12)), (("uc-1", "uc-2"), (11, 11))])
def test_one_customer_or_one_staff_alone_does_not_pass_and_nothing_is_called(ready, chats, staff):
    ids = [edited(n, chat=c, staff=s) for n, (c, s) in enumerate(zip(chats, staff), start=1)]
    client = FakeAnthropic(proposal(ids), NO_CONFLICT)
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=client)
    assert (counts["groups"], counts["evidence_ok"], counts["stored"]) == (1, 0, 0)
    assert client.params == [] and stored() == []


def test_held_out_rows_are_never_read(ready):
    for n, (chat, staff) in enumerate((("uc-1", 11), ("uc-2", 12)), start=1):
        edited(n, chat=chat, staff=staff, held_out=True)
    client = FakeAnthropic(proposal([1, 2]), NO_CONFLICT)
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=client)
    assert counts["groups"] == 0 and client.params == [] and stored() == []
    assert weekly_fix.collect_groups(db_session, NOW) == []


def test_only_edited_cases_with_a_reason_detail_or_photo_note_are_read(ready):
    edited(1, chat="uc-1", staff=11, reason=None, detail=None)  # 까닭 · 이유 · 사진 설명 모두 없음 — 읽지 않음
    with_note = edited(2, chat="uc-2", staff=12, reason=None, detail=None)
    db_session.add(CsAgentTurnPhoto(turn_id=with_note, seq=1, storage_key=None, content_type="image/jpeg", bytes=1,
                                    width=1, height=1, sha256="0" * 64, no_personal=True, desc_state="done",
                                    desc_masked="합성 계산기 화면 — 선반 깊이 칸", uploaded_by=12))
    db_session.add(CsAgentTurn(brand="LAHOM", chat_id="uc-3", last_user_message_id="m-3", state="posted",
                               outcome="as_is", edit_reason="tone", sent_by_user_id=13, sent_at=naive(at(1, 10))))
    edited(4, chat="uc-4", staff=14, when=at(1, 10).replace(month=10, day=20))  # 7일보다 오래됨
    db_session.commit()
    (group,) = weekly_fix.collect_groups(db_session, NOW)
    assert [c["turn_id"] for c in group.cases] == [with_note] and group.cases[0]["photos"] == ["합성 계산기 화면 — 선반 깊이 칸"]


# ── 만들기 → 제안함(자동 반영 0) ──────────────────────────────────────────
def test_a_passing_group_becomes_a_pending_owner_proposal_and_knowledge_is_untouched(two_by_two):
    panel(**{f.name: True for f in DETAIL_FIELDS if f.kind == "bool"})  # 모든 켬 · 끔 칸을 켠 상태에서도
    before = read_stored(db_session, "LAHOM")
    client = FakeAnthropic(proposal(two_by_two), NO_CONFLICT)
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=client)
    assert (counts["evidence_ok"], counts["proposed"], counts["stored"]) == (1, 1, 1) and len(client.params) == 2
    (item,) = stored()
    assert item["state"] == "pending_owner" and item["proposed_text"] == NEW_TEXT and item["item_id"] == "hours-day"
    assert item["evidence_turn_ids"] == sorted(two_by_two) and item["decided_by_user_id"] is None
    assert item["gates"] == {"form": "pass", "mask": "pass", "evidence": "pass", "conflict": "pass",
                             "eval": "unavailable"}
    after = read_stored(db_session, "LAHOM")
    assert (after.version, after.document) == (before.version, before.document)  # 사람 승인 전 지식은 그대로
    assert load_approved(db_session, "LAHOM").get("hours-day").text != NEW_TEXT
    judge = client.params[1]
    assert judge["model"] == weekly_fix_gates.MODEL_HAIKU and NEW_TEXT in judge["messages"][0]["content"][0]["text"]
    learning = brain_spend.today_spend(db_session, now=NOW, key=brain_spend.LEARNING_SPEND_KEY)
    assert learning["calls"] == 2


def test_it_runs_once_per_week_and_only_in_the_monday_window(two_by_two):
    for when in (at(3, 4), at(2, 7), at(2, 2, 59)):  # 화요일 · 월요일 창 뒤 · 창 앞
        client = FakeAnthropic(proposal(two_by_two), NO_CONFLICT)
        assert weekly_fix.run_weekly_fix(db_session, now=when, client=client) == {"off": "not_window"}
        assert client.params == []
    assert weekly_fix.run_weekly_fix(db_session, now=NOW, client=FakeAnthropic(proposal(two_by_two), NO_CONFLICT)
                                     )["stored"] == 1
    again = FakeAnthropic(proposal(two_by_two), NO_CONFLICT)
    assert weekly_fix.run_weekly_fix(db_session, now=at(2, 5), client=again) == {"off": "already_this_week"}
    assert again.params == []


@pytest.mark.parametrize("change", ["switch_off", "emergency_stop", "no_learning_cap"])
def test_switches_and_the_learning_cap_close_it(two_by_two, change):
    if change == "switch_off":
        panel(**{WEEKLY_FIELD: False})
    elif change == "no_learning_cap":
        panel(learning_cap_usd_panel=None)
    else:
        db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "off", "draft": "memo"}))
        db_session.commit()
    client = FakeAnthropic(proposal(two_by_two), NO_CONFLICT)
    assert weekly_fix.run_weekly_fix(db_session, now=NOW, client=client) == {"off": change}
    assert client.params == []


# ── 관문(가림 · 숫자 · 근거 · 부딪침) ─────────────────────────────────────
@pytest.mark.parametrize("text, item_id, gate", [
    ("주말 문의는 " + "9" * 4 + "원 추가입니다.", "hours-day", "mask"),  # 승인 지식에 없는 숫자 — 세탁 막기
    ("주말 문의는 (이름) 고객님께 따로 안내드립니다.", "hours-day", "mask"),  # 빈칸 꼴
    (NEW_TEXT, "shelf-depth", "form"),  # 기준 답 문구가 아닌 항목
    (NEW_TEXT, "no-such-item", "form"),
])
def test_bad_proposals_fail_their_gate_and_are_not_stored(two_by_two, text, item_id, gate):
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW,
                                       client=FakeAnthropic(proposal(two_by_two, text=text, item_id=item_id), NO_CONFLICT))
    assert counts["gate_failed"] == {gate: 1} and counts["stored"] == 0 and stored() == []


def test_a_number_already_in_approved_knowledge_is_allowed(two_by_two):
    text = "합성 선반 깊이는 350mm 입니다. 주말 문의는 다음 평일에 이어서 안내드립니다."
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=FakeAnthropic(proposal(two_by_two, text=text),
                                                                                   NO_CONFLICT))
    assert counts["stored"] == 1


def test_evidence_must_come_from_the_group_and_span_two_customers_and_two_staff(two_by_two):
    other = edited(9, chat="uc-9", staff=19, intent="other", reason="tone")
    for ids in ([two_by_two[0]], [two_by_two[0], other]):
        db_session.query(SystemSetting).filter_by(setting_key=weekly_fix_store.PROPOSALS_KEY).delete()
        db_session.commit()
        counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=FakeAnthropic(proposal(ids), NO_CONFLICT))
        assert counts["gate_failed"] == {"evidence": 1} and stored() == []


@pytest.mark.parametrize("judge", [{"verdicts": [{"index": 0, "conflict": True}]}, {"verdicts": []}, {"broken": 1}])
def test_a_conflict_or_a_missing_verdict_fails_the_proposal(two_by_two, judge):
    counts = weekly_fix.run_weekly_fix(db_session, now=NOW, client=FakeAnthropic(proposal(two_by_two), judge))
    assert counts["gate_failed"] == {"conflict": 1} and counts["stored"] == 0


# ── 사장님 결정(로그인 ADMIN 만) ─────────────────────────────────────────
def _one_pending(two_by_two):
    weekly_fix.run_weekly_fix(db_session, now=NOW, client=FakeAnthropic(proposal(two_by_two), NO_CONFLICT))
    (item,) = stored()
    return item["id"]


def test_only_a_logged_in_admin_decides_and_approval_makes_a_new_knowledge_version(two_by_two):
    pid = _one_pending(two_by_two)
    staff = user()
    assert weekly_fix_store.decide(db_session, pid, decision="approve", user=staff, note=None, now=NOW).status == 403
    assert weekly_fix_store.decide(db_session, pid, decision="approve", user=None, note=None, now=NOW).status == 403
    assert stored()[0]["state"] == "pending_owner" and read_stored(db_session, "LAHOM").version == 1
    admin = user(role="ADMIN", team=None, name="owner")
    result = weekly_fix_store.decide(db_session, pid, decision="approve", user=admin, note=None, now=NOW)
    assert (result.code, result.version) == ("approved", 2)
    item = stored()[0]
    assert (item["state"], item["decided_by_user_id"], item["applied_version"]) == ("approved", admin.id, 2)
    assert load_approved(db_session, "LAHOM").get("hours-day").text == NEW_TEXT
    again = weekly_fix_store.decide(db_session, pid, decision="reject", user=admin, note="x", now=NOW)
    assert again.code == "already"


def test_a_rejected_proposal_is_not_proposed_again(two_by_two):
    pid = _one_pending(two_by_two)
    admin = user(role="ADMIN", team=None, name="owner")
    assert weekly_fix_store.decide(db_session, pid, decision="reject", user=admin, note="합성 까닭\n둘째 줄",
                                   now=NOW).code == "rejected"
    item = stored()[0]
    assert (item["state"], item["decision_note"]) == ("rejected", "합성 까닭")
    knowledge = load_approved(db_session, "LAHOM")
    groups = weekly_fix.collect_groups(db_session, NOW)
    raw = proposal(two_by_two)["proposals"]
    passed, failed = weekly_fix_gates.check_proposals(raw, groups, knowledge,
                                                      rejected=weekly_fix_store.rejected_prints(db_session),
                                                      week="2026-W46", brand="LAHOM", now=at(9, 4))
    assert passed == [] and failed == {"rejected": 1}


def test_the_decide_route_ignores_a_free_text_approver(app, client, two_by_two):
    if "cs_agent_fix_api.cs_agent_fix_decide" not in app.view_functions:
        pytest.skip("블루프린트 등록 전(foms/platform/blueprints.py)")
    pid = _one_pending(two_by_two)
    staff = user()
    with client.session_transaction() as sess:
        sess["user_id"] = staff.id
    url = f"/api/admin/cs-agent/fix-proposals/{pid}/decide"
    denied = client.post(url, json={"decision": "approve", "approved_by": "사장님", "user_id": 1})
    assert denied.status_code == 403 and stored()[0]["state"] == "pending_owner"
    admin = user(role="ADMIN", team=None, name="owner")
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
    no_decision = client.post(url, json={"approved_by": "사장님", "approved": True})
    assert no_decision.status_code == 400 and stored()[0]["state"] == "pending_owner"
    listed = client.get("/api/admin/cs-agent/fix-proposals").get_json()
    assert listed["success"] is True and listed["data"]["proposals"][0]["id"] == pid
    ok = client.post(url, json={"decision": "approve", "approved_by": "다른 사람"}).get_json()
    assert ok["data"]["code"] == "approved" and stored()[0]["decided_by_user_id"] == admin.id


def test_there_is_no_automatic_apply_path():
    """제안함 → 지식 문서로 가는 길은 decide(로그인 ADMIN) 하나뿐이다 — 바퀴 쪽 모듈은 지식을 쓰지 않는다."""
    root = Path(__file__).resolve().parents[2] / "foms/services/cs_agent"
    for name in ("weekly_fix.py", "weekly_fix_gates.py", "learning_pass.py", "photo_desc.py", "loop.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "save_document" not in source and "decide(" not in source, name
