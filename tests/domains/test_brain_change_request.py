"""문장으로 고치기 — 시작 → 미리 보기 → 반영 → 보고 → 되돌리기(설계서 2026-11-18-brain-sentence-change 2절 · 7절 · 11절) 가짜 AI 시험.

1. 11-17 문장 꼴(지식 항목 고침 하나 + AI 직원 수준 표 두 칸 0)이 한 묶음으로 나오고, 한 줄 빼고 반영 → 보고 값 → 되돌리기 →
   전 값으로 돌아온다(수준 표 · 항목 판 모두).
2. 묶음 되돌리기는 이 묶음이 반영한 것만 — 같은 날 다른 승인은 그대로, 그 뒤 다른 고침이 얹힌 줄은 되돌리지 않고 까닭을 적는다.
3. 가림이 새면 멈춤(묶음 줄 · AI 모두 없음) · 원문 저장 안 함 · AI 답이 틀 밖이면 반영 0 · 돈 상한 · 되물음 → 답 → 다시 분석.
4. 팀장(층 승인자)이 넣으면 다른 층 줄은 '같이 볼 것'으로, 설정 줄은 못 고친 것으로. 넣은 사람이 반영할 수 없는 줄은 승인 대기.
합성 지식 · 합성 계정만(금액 · 손님 글 · 직원 이름 없음).
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainChangeRequest
from foms.services.ai_staff.registry import level_of
from foms.services.brain import change_request as cr
from foms.services.brain.apply import apply_change
from foms.services.brain.change_request_model import SPEND_KEY
from foms.services.brain.chat_settings import CHANGE_CAP_FIELD, DEFAULTS, SETTINGS_KEY
from foms.services.brain.chat_settings import SPEND_KEY as CHAT_SPEND_KEY
from foms.services.brain.errors import BrainPermissionError
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.store import current_object
from foms.services.graft_flags import FLAGS
from foms.services.brain.change_request_store import STUCK_AFTER
from foms.services.notifications.brain_change_notice import BRAIN_CHANGE_REQUEST_TYPE, request_link
from models import Notification, NotificationUserState, SecurityLog, SystemSetting
from tests.support.brain_chat_support import FakeClient, fixed
from tests.support.brain_screen_support import people as make_people
from tests.support.brain_support import NOW, REASON, create

SENTENCE = "도면 담당은 도면팀에서 자율적으로 해. 협력사 시공일도 출고 담당이 출고 스케줄 보고 조율해"
NEW_TEXT = "도면 담당은 도면팀이 스스로 정한다."
OLD_TEXT = "도면 담당은 운영 AI 가 제안하고 사장님이 정한다."
START_AT = NOW  # 모든 묶음 함수의 시각은 UTC naive 하나(한국 2026-11-02 10시)
APPLY_AT = NOW + datetime.timedelta(minutes=5)
REVERT_AT = NOW + datetime.timedelta(minutes=30)


def flags_on(monkeypatch, cohort="all"):
    """스위치 둘(새 회사 지식 화면 · 문장으로 고치기)을 켠다."""
    for short in ("brain_ui", "brain_change_request"):
        monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
        monkeypatch.setenv(f"{FLAGS[short]}_COHORT", cohort)


def world(session):
    """사람(역할 × 팀) + 합성 항목(공통 제작 조건 둘 · 도면 규칙 · 제품 둘 · 도면팀만 보는 상담 배운 점). 커밋한다."""
    who = make_people(session)
    admin = who["admin"]
    create(session, admin, "common/rule/assign", item_type="build_rule", name="도면 담당 정하기", text=OLD_TEXT)
    create(session, admin, "common/rule/old", item_type="build_rule", name="옛 도면 담당 규칙", text="도면 담당은 영업이 고른다.")
    create(session, admin, "drawing/rule/assign", item_type="drawing_rule", layer="drawing", name="도면팀 담당 나눔",
           text="도면팀 안에서 담당을 나눈다.")
    create(session, admin, "common/door", name="여닫이 문짝")
    create(session, admin, "common/slide", name="미닫이 문짝")
    create(session, admin, "cs/lesson/hidden", item_type="lesson", layer="cs", name="도면팀만 보는 배운 점",
           visibility="team:DRAWING")
    session.commit()
    return who


def answer_text(**fields):
    """가짜 AI 답(3절 꼴 — 처음 값은 빈 칸들)."""
    out = {"summary": "도면 담당은 도면팀이 정하고 시공일은 출고 담당이 맞춘다", "updates": [], "creates": [], "retires": [],
           "links": [], "settings": [], "needs_code": [], "questions": [], "also_look": []}
    out.update(fields)
    return json.dumps(out, ensure_ascii=False)


def upd(key, text="", name="", why="문장대로 고침"):
    return {"key": key, "after": {"name": name, "text": text, "valid_from": "", "valid_to": ""}, "why": why}


def lvl(name, value, area="ai_staff_levels"):
    return {"area": area, "name": name, "value": value, "why": "사람이 직접 맡음"}


OWNER_ANSWER = dict(
    updates=[upd("common/rule/assign", text=NEW_TEXT)],
    retires=[{"key": "common/rule/old", "why": "옛 규칙"}],
    settings=[lvl("ops.assign_draftsman", 0), lvl("schedule.schedule_construction", 0)],
    needs_code=["밤 훑기 규칙 둘은 코드 상수라 사람이 끈다"],
    also_look=["common/door — 같이 볼 것"])


@pytest.fixture
def who(app, monkeypatch):
    flags_on(monkeypatch)
    return world(db_session)


def _start(user, text=SENTENCE, client=None):
    out = cr.start(db_session, user, text, client=client, now=START_AT)
    db_session.commit()
    return out


def _requests():
    return db_session.execute(select(BrainChangeRequest).order_by(BrainChangeRequest.id)).scalars().all()


# ── 1. 11-17 문장 — 처음부터 끝까지 ──────────────────────────────────────
def test_owner_sentence_makes_one_bundle_applies_reports_and_reverts(who):
    admin = who["admin"]
    client = fixed(answer_text(**OWNER_ANSWER))
    view = _start(admin, client=client)
    assert view["status"] == "ready" and view["mine"] is True and view["can_apply"] is True
    assert [(l["no"], l["kind"], l["state"]) for l in view["lines"]] == [
        (1, "update", "preview"), (2, "retire", "preview"), (3, "setting", "preview"), (4, "setting", "preview")]
    first = view["lines"][0]
    assert first["before"] == {"text": OLD_TEXT} and first["after"] == {"text": NEW_TEXT} and first["check"] is None
    assert view["lines"][2]["before"] == {"level": 2} and view["lines"][2]["after"] == {"level": 0}
    assert view["needs_code"] == ["밤 훑기 규칙 둘은 코드 상수라 사람이 끈다"]
    assert view["also_look"] == [{"key": "common/door", "label": "여닫이 문짝", "why": "같이 볼 것"}]
    params = client.calls[0]
    assert "주어진 키만 써라" in params["system"][0]["text"] and "모르면 고치지 말고 questions 에 적어라" in params["system"][0]["text"]
    assert "금액 숫자를 글에 넣지 마라" in params["system"][0]["text"] and "tools" not in params
    schema = params["output_config"]["format"]["schema"]
    assert "common/rule/assign" in schema["properties"]["updates"]["items"]["properties"]["key"]["enum"]
    assert "ops.assign_draftsman" in schema["properties"]["settings"]["items"]["properties"]["name"]["enum"]
    assert client.options[0] == {"timeout": 60, "max_retries": 0}
    assert db_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.request_id.is_not(None))) == 0  # 미리 보기는 제안 줄을 남기지 않는다(모의 실행은 되돌림)
    assert db_session.get(SystemSetting, SPEND_KEY).setting_value["calls"] == 1
    assert db_session.get(SystemSetting, CHAT_SPEND_KEY) is None  # 물어보기 돈 줄과 따로

    done = cr.apply(db_session, admin, view["id"], skip=[2], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied" and done["can_apply"] is False and done["can_revert"] is True
    assert [(l["no"], l["state"]) for l in done["lines"]] == [(1, "applied"), (2, "skipped"), (3, "applied"),
                                                               (4, "applied")]
    assert current_object(db_session, "common/rule/assign").text == NEW_TEXT
    assert current_object(db_session, "common/rule/old").status == "active"  # 뺀 줄은 그대로
    assert level_of(db_session, "ops", "assign_draftsman") == 0 == level_of(db_session, "schedule", "schedule_construction")
    made = db_session.execute(select(BrainChange).where(BrainChange.request_id == view["id"])).scalars().all()
    assert [(c.op, c.status, c.proposed_by, c.decided_by) for c in made] == [
        ("update", "applied", f"user:{admin.id}", admin.id)]
    report = cr.view(db_session, admin, view["id"])
    assert report["settings"] == [
        {"no": 3, "area": "ai_staff_levels", "name": "ops.assign_draftsman", "before": 2, "after": 0, "applied": True,
         "reverted": False},
        {"no": 4, "area": "ai_staff_levels", "name": "schedule.schedule_construction", "before": 2, "after": 0,
         "applied": True, "reverted": False}]
    assert report["not_done"] == [] and report["counts"]["applied"] == 3
    apply_audit = db_session.query(SecurityLog).filter_by(action="BRAIN_APPLY", target_id=made[0].id).one()
    assert apply_audit.detail["request"] == view["id"]  # 반영 감사 줄에 묶음 번호
    assert db_session.query(SecurityLog).filter_by(action="AI_STAFF_LEVELS_SAVED").count() == 2
    note = db_session.query(Notification).filter_by(notification_type=BRAIN_CHANGE_REQUEST_TYPE).one()
    assert (note.title, note.target_user_id, note.order_id) == ("문장으로 고치기", admin.id, None)
    assert note.message == f"[문장으로 고치기] /brain/requests/{view['id']}\n3곳을 고쳤어요"
    assert request_link(note.message) == f"/brain/requests/{view['id']}"
    assert NEW_TEXT not in note.message and SENTENCE[:6] not in note.message  # 문장 · 고친 글은 싣지 않는다
    assert [s.user_id for s in db_session.query(NotificationUserState).filter_by(notification_id=note.id)] == [admin.id]

    back = cr.revert(db_session, admin, view["id"], now=REVERT_AT)
    db_session.commit()
    assert back["status"] == "reverted" and back["can_revert"] is False
    assert [(l["no"], l["state"]) for l in back["lines"]] == [(1, "reverted"), (2, "skipped"), (3, "reverted"),
                                                               (4, "reverted")]
    assert current_object(db_session, "common/rule/assign").text == OLD_TEXT  # 전 값으로(새 판)
    assert current_object(db_session, "common/rule/assign").version == 3
    assert level_of(db_session, "ops", "assign_draftsman") == 2 == level_of(db_session, "schedule", "schedule_construction")
    actions = [r.action for r in db_session.query(SecurityLog).filter(
        SecurityLog.action.like("BRAIN_REQUEST_%")).order_by(SecurityLog.id)]
    assert actions == ["BRAIN_REQUEST_START", "BRAIN_REQUEST_APPLY", "BRAIN_REQUEST_REVERT"]
    assert all(SENTENCE[:10] not in (r.message or "") for r in db_session.query(SecurityLog))  # 감사 줄은 번호 · 수만


# ── 2. 이 묶음만 되돌린다 ────────────────────────────────────────────────
def test_revert_only_touches_this_bundle_and_skips_lines_with_later_changes(who):
    admin = who["admin"]
    answer = answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT), upd("common/rule/old", text="옛 규칙 새 글")])
    view = _start(admin, client=fixed(answer))
    cr.apply(db_session, admin, view["id"], now=APPLY_AT)
    db_session.commit()
    other = propose_update(db_session, key="common/door", base_version=1, after={"text": "같은 날 다른 승인"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=APPLY_AT, known="")
    apply_change(db_session, other.id, actor=admin, now=APPLY_AT)
    later = propose_update(db_session, key="common/rule/old", base_version=2, after={"text": "그 뒤 다른 고침"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=APPLY_AT, known="")
    apply_change(db_session, later.id, actor=admin, now=APPLY_AT)
    db_session.commit()
    back = cr.revert(db_session, admin, view["id"], now=REVERT_AT)
    db_session.commit()
    assert [(l["no"], l["state"]) for l in back["lines"]] == [(1, "reverted"), (2, "revert_blocked")]
    assert back["lines"][1]["check"]["code"] == "later_change" and back["not_done"][0]["no"] == 2
    assert current_object(db_session, "common/rule/assign").text == OLD_TEXT
    assert current_object(db_session, "common/rule/old").text == "그 뒤 다른 고침"  # 뒤 고침은 덮지 않는다
    assert current_object(db_session, "common/door").text == "같은 날 다른 승인"  # 같은 날 다른 승인은 그대로


# ── 3. 가림 · 원문 · 틀 밖 · 돈 · 되물음 ─────────────────────────────────
def test_mask_leak_stops_before_any_row_or_model_call(who, monkeypatch):
    monkeypatch.setattr(cr, "mask", lambda text: text)  # 가림이 고장 나도 검사가 막는다
    client = fixed(answer_text())
    with pytest.raises(cr.ChangeRequestError) as caught:
        cr.start(db_session, who["admin"], "연락처 010-2345-6789 도면 담당", client=client, now=START_AT)
    assert caught.value.code == "mask" and client.calls == [] and _requests() == []


def test_only_the_masked_sentence_is_sent_and_stored(who):
    client = fixed(answer_text())
    view = _start(who["admin"], "고객 010-2345-6789 님 건 도면 담당은 도면팀이 정해", client=client)
    sent = json.dumps(client.calls[0]["messages"], ensure_ascii=False)
    assert "010-2345-6789" not in sent and "2345" not in sent and "[전화]" in sent
    row = _requests()[-1]
    assert "2345" not in row.masked_text and "[전화]" in row.masked_text and view["text"] == row.masked_text


@pytest.mark.parametrize("bad", ["글이 아니다", json.dumps({"updates": "x"}), json.dumps([1, 2]),
                                 json.dumps({"settings": [{"area": "ai_staff_levels", "name": "ops.x", "value": "0"}]})])
def test_answer_outside_the_frame_applies_nothing(who, bad):
    view = _start(who["admin"], client=fixed(bad))
    assert view["status"] == "failed" and view["error_code"] == "bad_response" and view["lines"] == []
    assert view["error_text"] and view["can_apply"] is False and view["can_discard"] is True
    with pytest.raises(cr.ChangeRequestError) as caught:
        cr.apply(db_session, who["admin"], view["id"], now=APPLY_AT)
    assert caught.value.code == "state"
    assert db_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.request_id.is_not(None))) == 0


def _cap(value):
    db_session.add(SystemSetting(setting_key=SETTINGS_KEY, setting_value={**DEFAULTS, CHANGE_CAP_FIELD: value},
                                 description="합성"))
    db_session.commit()


def test_empty_daily_cap_turns_it_off_and_a_tiny_cap_fails_the_bundle(who):
    assert DEFAULTS[CHANGE_CAP_FIELD] == "2.00"  # 처음 값 2달러(설계서 6절)
    _cap(None)
    client = fixed(answer_text())
    with pytest.raises(cr.ChangeRequestError) as caught:
        cr.start(db_session, who["admin"], SENTENCE, client=client, now=START_AT)
    assert caught.value.code == "off" and _requests() == [] and client.calls == []
    db_session.get(SystemSetting, SETTINGS_KEY).setting_value = {**DEFAULTS, CHANGE_CAP_FIELD: "0.01"}
    db_session.commit()
    view = _start(who["admin"], client=client)  # 한 번의 최악값보다 작다 — 예약에서 막힌다
    assert view["status"] == "failed" and view["error_code"] == "money_cap" and client.calls == []


def test_question_then_answer_reanalyzes_the_same_bundle(who):
    replies = iter([answer_text(questions=["도면 담당을 누가 정하나요?"]),
                    answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT)])])
    client = FakeClient(lambda _params: next(replies))
    view = _start(who["admin"], "도면 담당 바뀜", client=client)
    assert view["status"] == "asked" and view["can_answer"] is True and view["can_apply"] is False
    again = cr.answer(db_session, who["admin"], view["id"], "도면팀이 스스로 정해요", client=client, now=START_AT)
    db_session.commit()
    assert again["id"] == view["id"] and again["status"] == "ready" and again["lines"][0]["state"] == "preview"
    assert again["answers"] == [{"question": "도면 담당을 누가 정하나요?", "answer": "도면팀이 스스로 정해요"}]
    assert "도면팀이 스스로 정해요" in client.calls[1]["messages"][0]["content"]
    assert len(_requests()) == 1
    with pytest.raises(cr.ChangeRequestError) as caught:  # 물음이 없으면 답할 것이 없다
        cr.answer(db_session, who["admin"], view["id"], "더", client=client, now=START_AT)
    assert caught.value.code == "state"


def test_discard_before_apply_only(who):
    view = _start(who["admin"], client=fixed(answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT)])))
    gone = cr.discard(db_session, who["admin"], view["id"], now=APPLY_AT)
    db_session.commit()
    assert gone["status"] == "discarded" and gone["can_apply"] is False
    assert current_object(db_session, "common/rule/assign").text == OLD_TEXT
    with pytest.raises(cr.ChangeRequestError):
        cr.apply(db_session, who["admin"], view["id"], now=APPLY_AT)
    assert db_session.query(SecurityLog).filter_by(action="BRAIN_REQUEST_DISCARD").count() == 1


# ── 4. 팀장 · 승인 대기 ──────────────────────────────────────────────────
def test_team_lead_other_layer_goes_to_also_look_and_settings_are_blocked(who):
    lead = who["dr_mgr"]
    client = fixed(answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT),
                                        upd("drawing/rule/assign", text="도면팀 담당은 팀이 스스로 나눈다.")],
                               settings=[lvl("ops.assign_draftsman", 0)]))
    view = _start(lead, client=client)
    assert view["status"] == "ready"
    assert [(l["kind"], l["key"], l["state"]) for l in view["lines"]] == [
        ("update", "drawing/rule/assign", "preview"), ("setting", "ops.assign_draftsman", "blocked")]
    assert view["lines"][1]["check"]["code"] == "setting_admin"
    assert view["also_look"][0]["key"] == "common/rule/assign" and "공통 바탕" in view["also_look"][0]["why"]
    assert _requests()[-1].layer_scope == "drawing"
    done = cr.apply(db_session, lead, view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied" and done["lines"][0]["state"] == "applied"
    assert current_object(db_session, "drawing/rule/assign").text == "도면팀 담당은 팀이 스스로 나눈다."
    assert current_object(db_session, "common/rule/assign").text == OLD_TEXT
    assert level_of(db_session, "ops", "assign_draftsman") == 2


def test_lines_the_person_may_not_apply_wait_for_approval_and_revert_withdraws_them(who, monkeypatch):
    import foms.services.brain.apply as apply_module
    import foms.services.notifications.push_sender as push_sender

    pushed = []
    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", lambda *a, **k: pushed.append(a))

    real = apply_module.check_permission

    def guarded(actor, **kw):
        if kw.get("types") == ["build_rule"] and kw.get("op") == "retire":
            raise BrainPermissionError("합성 — 승인자 몫")
        return real(actor, **kw)

    monkeypatch.setattr(apply_module, "check_permission", guarded)
    admin = who["admin"]
    view = _start(admin, client=fixed(answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT)],
                                                  retires=[{"key": "common/rule/old", "why": "옛 규칙"}])))
    done = cr.apply(db_session, admin, view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "partial" and [l["state"] for l in done["lines"]] == ["applied", "pending"]
    waiting = db_session.get(BrainChange, done["lines"][1]["change_id"])
    assert waiting.status == "open" and waiting.request_id == view["id"]  # 승인 대기에 열린 채
    note = db_session.query(Notification).filter_by(notification_type=BRAIN_CHANGE_REQUEST_TYPE).one()
    assert note.message.endswith("\n1곳을 고쳤어요 · 1곳은 승인을 기다려요") and pushed == []  # 폰 알림 없음
    back = cr.revert(db_session, admin, view["id"], now=REVERT_AT)
    db_session.commit()
    assert [l["state"] for l in back["lines"]] == ["reverted", "withdrawn"]
    db_session.expire_all()
    closed = db_session.get(BrainChange, waiting.id)
    assert closed.status == "expired" and closed.decided_action == "withdraw"
    assert current_object(db_session, "common/rule/old").status == "active"


def test_a_failing_line_does_not_stop_the_others(who):
    admin = who["admin"]
    view = _start(admin, client=fixed(answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT),
                                                           upd("common/rule/old", text="옛 규칙 새 글")])))
    moved = propose_update(db_session, key="common/rule/old", base_version=1, after={"text": "먼저 들어간 고침"},
                           reason=REASON, proposer=Proposer.user(admin.id), now=NOW, known="")
    apply_change(db_session, moved.id, actor=admin, now=NOW)
    db_session.commit()
    done = cr.apply(db_session, admin, view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "partial" and [l["state"] for l in done["lines"]] == ["applied", "failed"]
    assert done["lines"][1]["check"]["code"] == "BRAIN_BASE_CHANGED" and done["lines"][1]["change_id"] is None
    assert db_session.scalar(select(func.count()).select_from(BrainChange).where(
        BrainChange.request_id == view["id"])) == 1  # 실패한 줄은 제안 줄도 남기지 않는다


def test_list_page_shows_mine_and_admin_sees_all(who):
    _start(who["admin"], client=fixed(answer_text()))
    _start(who["dr_mgr"], client=fixed(answer_text()))
    mine = cr.list_page(db_session, who["dr_mgr"], 1)
    every = cr.list_page(db_session, who["admin"], 1)
    assert mine["total"] == 1 and mine["items"][0]["mine"] is True
    assert every["total"] == 2 and [i["mine"] for i in every["items"]] == [False, True]
    with pytest.raises(cr.ChangeRequestError):
        cr.view(db_session, who["dr_mgr"], every["items"][1]["id"])  # 남의 묶음은 없는 것과 같다
    assert cr.view(db_session, who["admin"], mine["items"][0]["id"])["mine"] is False


# ── 5. 멈춘 분석 ─────────────────────────────────────────────────────────
def test_an_unexpected_error_during_analysis_closes_the_bundle_as_failed(who, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("합성 고장")

    monkeypatch.setattr(cr, "check_bundle", broken)
    view = _start(who["admin"], client=fixed(answer_text(updates=[upd("common/rule/assign", text=NEW_TEXT)])))
    assert view["status"] == "failed" and view["error_code"] == "error:RuntimeError" and view["lines"] == []
    assert view["error_text"] and view["can_discard"] is True
    db_session.expire_all()
    assert _requests()[-1].status == "failed"


def test_bundles_stuck_in_analyzing_are_closed_when_read(who):
    admin = who["admin"]
    old = BrainChangeRequest(created_by=admin.id, layer_scope="all", masked_text="합성 문장", status="analyzing",
                             created_at=NOW, bundle={"analyzing_at": NOW.isoformat()})
    fresh = BrainChangeRequest(created_by=admin.id, layer_scope="all", masked_text="합성 문장", status="analyzing",
                               created_at=NOW, bundle={"analyzing_at": (NOW + STUCK_AFTER).isoformat()})
    db_session.add_all([old, fresh])
    db_session.commit()
    later = NOW + STUCK_AFTER + datetime.timedelta(minutes=1)
    seen = cr.view(db_session, admin, old.id, now=later)
    db_session.commit()
    assert seen["status"] == "failed" and seen["error_code"] == "stuck" and seen["error_text"]
    listed = cr.list_page(db_session, admin, 1, now=later)
    assert {i["id"]: i["status"] for i in listed["items"]} == {old.id: "failed", fresh.id: "analyzing"}
