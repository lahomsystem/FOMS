"""물어보기 순수 함수 node 시험(static/js/brain/brain-ask-view.js — 설계서 10절 · ⑤-5).

- 답 → 모름 표시 · 근거 칩(카드를 열 수 있는 사람만 링크) · 확신 줄 · 확인 중 항목 · 고칠 말 제안 링크.
- 피드백 본문(틀림만 고칠 말) · 피드백 주소 · 남은 질문 글 · 상태 줄 · 설정 바뀐 칸만 · 빈 지식 줄.
표시 표는 서버 :func:`foms.services.brain.display.display_table` 그대로 싣는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.brain.chat_settings import ChatSettings, DEFAULTS, settings_view
from foms.services.brain.display import display_table

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "static/js/brain/brain-ask-view.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _node(expr: str, data: object = None):
    script = (f"const v = require({json.dumps(str(VIEW))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


ANSWER = {"id": 7, "answer": "합성 규격 650mm 입니다.", "unknown": False, "confidence": "confirmed", "certainty": "high",
          "evidence": [{"key": "common/sliding", "name": "슬라이딩 깊이", "type": "spec", "confidence": "confirmed",
                        "checked_at": "2026-10-30"}],
          "checks": [{"key": "common/old", "name": "옛 몰딩 조건", "type": "build_rule", "why": "확인 날이 지남"}],
          "card_links": True}


@NODE
def test_answer_view_chips_links_and_confidence():
    display = display_table()
    got = _node("[v.answerView(data.a, data.d, '/brain/items/'), v.answerView(Object.assign({}, data.a, {card_links: false}),"
                " data.d, '/brain/items/'), v.answerView({id: 8, answer: '모름 글', unknown: true, evidence: []}, data.d, '')]",
                {"a": ANSWER, "d": display})
    shown, staff, unknown = got
    assert shown["cls"] == "is-answer" and shown["badge"] == "" and shown["text"] == "합성 규격 650mm 입니다."
    assert shown["confidence"] == "근거: 확정 · 답이 맞을 가능성: 높음"
    assert shown["chips"] == [{"key": "common/sliding", "name": "슬라이딩 깊이", "type": "spec",
                               "href": "/brain/items/common/sliding", "meta": "확정 · 마지막 확인 2026-10-30"}]
    assert shown["checks"] == "확인 중이라 안 쓴 지식: 옛 몰딩 조건(확인 날이 지남)"
    assert shown["fixLink"] == "/brain/items/common/sliding#brain-card-propose"
    assert [f["value"] for f in shown["feedback"]] == ["helpful", "not_helpful", "wrong"]
    assert staff["chips"][0]["href"] is None and staff["fixLink"] is None  # 카드를 못 여는 직원은 링크 없음
    assert unknown["cls"] == "is-unknown" and unknown["badge"] == "모름" and unknown["confidence"] == ""


@NODE
def test_feedback_body_url_and_lines():
    got = _node("[v.feedbackBody('wrong', ' 650 이 아니라 600 '), v.feedbackBody('helpful', '무시'), v.feedbackBody('x'),"
                " v.feedbackUrl('/api/brain/chat/questions/0/feedback', 42), v.leftText(3), v.leftText(-1),"
                " v.stateText({enabled: false, is_admin: true}), v.stateText({enabled: true, is_admin: true, cap_ready: false}),"
                " v.stateText({enabled: true, can_ask: true})]")
    assert got[0] == {"feedback": "wrong", "note": "650 이 아니라 600"}
    assert got[1] == {"feedback": "helpful"} and got[2] is None
    assert got[3] == "/api/brain/chat/questions/42/feedback"
    assert got[4] == "오늘 남은 질문 3번" and got[5] == "오늘 남은 질문 0번"
    assert "꺼져 있어요" in got[6] and "하루 돈 상한" in got[7] and got[8] == ""


@NODE
def test_settings_changes_only_sends_changed_valid_fields():
    fields = settings_view(ChatSettings(dict(DEFAULTS), 3))["fields"]
    raw = {"enabled": True, "stage": "leads", "per_person_daily": "20", "daily_cap_usd": "2.50", "max_tokens": "abc",
           "model": "claude-sonnet-5-5"}
    got = _node("v.settingsChanges(data.f, data.r)", {"f": fields, "r": raw})
    assert got["changes"] == {"enabled": True, "stage": "leads", "daily_cap_usd": "2.50"}
    assert got["bad"] == ["max_tokens"]


@NODE
def test_gap_rows_text():
    gaps = {"week": "2026-11-02", "questions": 3, "layers": {"common": [
        {"label": "사무 생활 질문", "count": 2, "wrong": 1, "last": "2026-11-02", "question_ids": [1, 2]}], "cs": []}}
    got = _node("v.gapRows(data.g, data.d)", {"g": gaps, "d": display_table()})
    assert got == [{"layer": "common", "text": "공통 바탕 · 사무 생활 질문 — 2건(틀림 1) · 마지막 2026-11-02"}]
