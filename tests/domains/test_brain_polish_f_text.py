"""회사 지식 다듬기 2차 — 서버 글 · 카드 템플릿 화면 글(일꾼 F · F1 ~ F6).

- F1: 화면에 나가는 '항목' → '지식'(다시 확인 줄 · 오늘 이미 확인 · 실패 말), 옛 이름 '제안함' 없음, 등급 B 확인 말.
- F2: 수정 기록 되돌리기 단추 '이 버전으로 되돌리기 제안' · 표 머리 '판(하루 묶음)' · 고치기 단추 풀이(title) 해요체.
- F3: 물어보기 설정 도움말 해요체 · 쉬운 말(칸 이름 · 고르기 값 · 기본값 · 키는 그대로 — 대조군).
- F4: 머리 글 — 관리자는 '회사 지식 N개가 있어요', 그 밖은 '내가 볼 수 있는 N개만 보여요'(대조군).
- F5: 위험 등급 이름표 'B(가벼움)'.
- F6: 카드 연결 규칙 줄 — 최소 · 최대 모두 0 인 규칙은 안 보이고, 나머지는 끝에 '개'(대조군).
합성 계정 · 합성 지식만.
"""

from __future__ import annotations

import re

import pytest

from db import db_session
from foms.services.brain import actions
from foms.services.brain.action_runner import perform
from foms.services.brain.chat_settings import DEFAULTS, FIELDS, STAGES
from foms.services.brain.display import GRADE_LABELS
from foms.services.brain.recheck import summary_line
from tests.support.brain_support import NOW, create, person

HANJA = re.compile("[" + chr(0x3400) + "-" + chr(0x9FFF) + chr(0xF900) + "-" + chr(0xFAFF) + "]")  # 한자(한글은 밖)
OLD_WORDS = ("제안함", "에이전트", "ADMIN", "MANAGER", "env")
DECISION_NO = re.compile(r"D\d+")
#: 사람이 누르는 단추 이름(액션 이름은 저장 값 — 바뀌면 안 된다).
UI_NAMES = ["propose_edit", "propose_retire", "propose_delete", "item_rollback", "apply", "edit_apply", "reject",
            "bulk_apply", "recheck", "release_rollback"]


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


# ── F1 · F2 서버 글 ─────────────────────────────────────────────────────
def test_screen_failure_messages_say_knowledge_and_waiting_for_approval():
    assert actions.FAILURES["BRAIN_OPEN_PROPOSAL"] == "이 지식에 승인을 기다리는 제안이 있어요 — '승인 대기'에서 먼저 정해 주세요."
    assert actions.FAILURES["BRAIN_BASE_CHANGED"].startswith("제안을 만든 뒤 지식이 바뀌었어요")
    assert actions.FAILURES["BRAIN_CONFIRM"] == "등급 B 는 핵심 값 확인 칸을 눌러야 승인돼요."
    for code, text in actions.FAILURES.items():
        assert "항목" not in text and "제안함" not in text and not HANJA.search(text), code


def test_recheck_lines_say_knowledge():
    assert summary_line({"total": 0}) == "다시 볼 지식이 없어요."
    assert summary_line({"total": 3, "overdue": 1, "soon": 2}).startswith("다시 볼 지식 3개 — ")


def test_propose_button_hints_are_polite_and_use_screen_words():
    ui = {a["name"]: a for a in actions.specs()}
    assert list(ui) == UI_NAMES  # 이름 · 차례 그대로(저장 값)
    assert ui["item_rollback"]["label"] == "이 버전으로 되돌리기 제안"
    assert ui["propose_edit"]["summary"] == "고칠 내용을 '승인 대기'에 올려요. 승인되면 바뀌어요."
    assert ui["propose_retire"]["summary"] == "승인되면 AI 가 이 지식을 더는 쓰지 않아요."
    assert ui["propose_delete"]["summary"] == "승인되면 이 지식을 지워요(수정 기록은 남아요)."
    for name in ("propose_edit", "propose_retire", "propose_delete"):
        text = ui[name]["summary"]
        assert text.endswith(("요.", "요).")) and "항목" not in text and "제안함" not in text and "에이전트" not in text, name
    assert [ui[n]["label"] for n in ("propose_edit", "propose_retire", "propose_delete")] == [
        "고칠 말 제안", "은퇴 제안", "지우기 제안"]  # 대조군: 단추 이름은 그대로


def test_already_checked_today_message_says_knowledge(app):
    admin = person(db_session, "polf_recheck_admin")
    create(db_session, admin, "common/polf-checked", item_type="term", name="polf-checked",
           checked_at=NOW.date().isoformat())
    db_session.commit()
    _a, out = perform(db_session, "recheck", actor=admin, now=NOW, body={"key": "common/polf-checked", "version": 1})
    assert out["already"] is True and out["message"] == "오늘 이미 확인한 지식이에요."


# ── F3 물어보기 설정 도움말 ─────────────────────────────────────────────
def test_chat_settings_help_is_polite_plain_korean():
    for field in FIELDS:
        if not field.help:
            continue
        assert not field.help.rstrip(")").endswith("다"), field.name
        assert not DECISION_NO.search(field.help) and not HANJA.search(field.help), field.name
        assert not any(word in field.help for word in OLD_WORDS), field.name
    stage = next(f for f in FIELDS if f.name == "stage")
    assert stage.choices == (("admin", "관리자만"), ("leads", "팀장까지"), ("all", "내부 직원 전부"))
    assert STAGES == ("admin", "leads", "all") and DEFAULTS["stage"] == "admin" and DEFAULTS["enabled"] is False
    assert [f.label for f in FIELDS][:3] == ["물어보기 스위치", "여는 단계", "챗봇 모델"]  # 대조군: 칸 이름 그대로


# ── F5 위험 등급 이름표 ─────────────────────────────────────────────────
def test_grade_light_label_has_brackets():
    assert GRADE_LABELS == {"A": "A", "B_LIGHT": "B(가벼움)", "B": "B"}


# ── F4 머리 글 · F2 수정 기록 · F6 연결 규칙 ─────────────────────────────
@pytest.fixture
def screen_world(app):
    admin = person(db_session, "polf_admin")
    lead = person(db_session, "polf_cs_lead", role="MANAGER", team="CS")
    create(db_session, admin, "common/polf-depth", item_type="spec", name="polf-depth",
           payload={"value": 600, "unit": "mm"})
    create(db_session, admin, "common/polf-brain-rule", item_type="price_rule", name="polf-brain-rule",
           checked_at="2026-10-20", visibility="price",
           payload={"doc_id": "polf-brain-rule", "approved_by": "합성", "approved_at": "2026-10-20", "basis": "brain"})
    db_session.commit()
    return {"admin": admin.id, "lead": lead.id}


def test_head_note_says_all_for_admin_and_visible_only_for_others(app, screen_world):
    admin_html = _client(app, screen_world["admin"]).get("/brain").get_data(as_text=True)
    assert re.search(r"회사 지식 \d+개가 있어요\.", admin_html) and "개만 보여요" not in admin_html
    lead_html = _client(app, screen_world["lead"]).get("/brain").get_data(as_text=True)
    assert re.search(r"내가 볼 수 있는 \d+개만 보여요\.", lead_html) and "개가 있어요." not in lead_html  # 대조군


def test_card_link_rules_hide_zero_rules_and_count_with_gae(app, screen_world):
    client = _client(app, screen_world["admin"])
    spec = client.get("/brain/items/common/polf-depth").get_data(as_text=True)
    assert "연결 규칙:" in spec and "값 정본 0 ~ 1개" in spec  # 대조군: 뜻 있는 규칙은 보인다
    brain_rule = client.get("/brain/items/common/polf-brain-rule").get_data(as_text=True)
    assert "<dt>위험 등급</dt>" in brain_rule
    assert "연결 규칙:" not in brain_rule and "0 ~ 0" not in brain_rule


def test_history_table_head_explains_release(app, screen_world):
    html = _client(app, screen_world["admin"]).get("/brain/items/common/polf-depth").get_data(as_text=True)
    assert '<th scope="col">판(하루 묶음)</th>' in html and '<th scope="col">판</th>' not in html
