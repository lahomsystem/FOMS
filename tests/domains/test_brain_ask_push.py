"""물어보기 [○○팀에 묻기] 폰 알림(사용자 결정 D240) — 잠금화면 글 · 여는 주소 · 꼬리표, 발송기 갈래.

질문 글(가린 글이라도) · 묻는 사람 · 답은 잠금화면에 싣지 않는다. 자료는 모두 지어낸 것.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from foms.services.brain import chat_team_ask
from foms.services.notifications import brain_ask_push as bap
from foms.services.notifications import push_sender

ROOT = Path(__file__).resolve().parents[2]


def _notif(question_id: int = 34, *, team: str = "도면팀", nid: int = 701):
    message = "\n".join((bap.team_ask_first_line(question_id), "[질문] 합성 질문 — 문짝 홈 깊이는 몇 mm 인가요? [전화]",
                         "[할 일] 아는 것을 물은 사람에게 알려 주세요"))
    return SimpleNamespace(id=nid, is_urgent=False, notification_type=bap.BRAIN_ASK_TEAM_TYPE, order_id=None,
                           message=message, title=bap.team_ask_title(team), created_at=None, target_user_id=3)


def test_first_line_round_trip_gives_link_and_tag():
    line = bap.team_ask_first_line(34)
    assert line == "[물어보기] /brain/ask?question=34"
    assert bap.team_ask_link(line + "\n[질문] 합성") == "/brain/ask?question=34"
    assert bap.brain_ask_deep_link(line) == "/brain/ask?question=34" and bap.brain_ask_tag(line) == "foms-brain-ask-34"
    # 알림 만드는 쪽과 같은 꼴 · 같은 종류
    assert chat_team_ask._first_line(34) == line and chat_team_ask.question_path(34) == "/brain/ask?question=34"
    assert chat_team_ask.BRAIN_ASK_TEAM_TYPE == bap.BRAIN_ASK_TEAM_TYPE and chat_team_ask.team_ask_link is bap.team_ask_link


def test_odd_values_fall_back_to_generic_text_and_the_ask_screen():
    for odd in ("", None, "합성 글", "[물어보기] /brain/ask?question=x", "[물어보기] https://evil/brain/ask?question=1"):
        assert bap.team_ask_link(odd) is None and bap.brain_ask_deep_link(odd) == "/brain/ask" and bap.brain_ask_tag(odd) is None
    for odd in ("", None, "합성 제목", "도면 팀 에 물어본 질문이 왔어요", "도면팀에 물어본 질문이 왔어요\n덧붙인 줄"):
        assert bap.brain_ask_push_text(odd) == ("회사 지식 물어보기", bap.BRAIN_ASK_GENERIC_BODY)
    assert bap.brain_ask_push_text(bap.team_ask_title("회계팀")) == ("회사 지식 물어보기", "회계팀에 물어본 질문이 왔어요")


def test_module_imports_no_other_service():
    source = (ROOT / "foms/services/notifications/brain_ask_push.py").read_text(encoding="utf-8")
    assert "\nimport foms" not in source and "\nfrom foms" not in source and "\nfrom models" not in source


def test_payload_has_no_question_text_and_opens_the_question():
    payload = push_sender._build_payload(_notif(), "가짜손님")
    assert payload["title"] == "회사 지식 물어보기" and payload["body"] == "도면팀에 물어본 질문이 왔어요"
    assert payload["data"] == {"notification_id": 701, "deep_link": "/brain/ask?question=34"}
    assert payload["tag"] == "foms-brain-ask-34" and "requireInteraction" not in payload
    text = json.dumps(payload, ensure_ascii=False)
    for leak in ("합성 질문", "문짝", "[전화]", "가짜손님", "[할 일]"):
        assert leak not in text


def test_type_is_pushed_with_normal_urgency(monkeypatch):
    monkeypatch.delenv("FOMS_PUSH_P1_TYPES", raising=False)
    notif = _notif(7)
    assert push_sender._should_push(notif) is True and bap.BRAIN_ASK_TEAM_TYPE in push_sender._DEFAULT_P1_TYPES
    assert push_sender._deep_link(notif) == "/brain/ask?question=7" and push_sender._urgency(notif) == "normal"
