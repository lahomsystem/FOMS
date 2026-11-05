"""master brain 글 관문(설계서 6절 관문 ① · 상담 17.6 관문 1) — 숫자 출처는 숫자 조각 통째로 견준다(글자 일부 겹침 아님).

순수 함수 시험 — DB 없음. 숫자는 꾸민 값이고 금액 · 손님 글 · 직원 이름이 아니다.
"""

from __future__ import annotations

import pytest

from foms.services.brain.chat_answer import Verified, verify
from foms.services.brain.gates import numbers_known, text_gates


@pytest.mark.parametrize("text, known, ok", [
    ("깊이 240", "깊이 2400", False),  # 예전에는 '2400' 안에 '240' 이 있어 지났다
    ("깊이 2400", "깊이 240", False),
    ("값 2,400", "값 2400", True),  # 쉼표는 떼고 같은 수
    ("값 2400", "값 2,400", True),
    ("1500 부터", "합성 1,500원 부터", True),
    ("값 150", "합성 1,500원", False),
    ("두께 1.5", "두께 1.50", True),  # 소수는 수로 견준다
    ("두께 1.5", "두께 11.55", False),
    ("두께 1", "두께 1.5", False),
    ("5일 뒤", "2026-11-05 정함", True),  # 날짜 조각의 앞 0 은 같은 수
    ("숫자 없음", "", True),
    ("판 1.2.3", "판 1.2.3", True),  # 수가 아닌 꼴은 글 그대로 견준다
    ("판 1.2.3", "판 1.2.30", False),
])
def test_numbers_are_compared_as_whole_numbers(text, known, ok):
    assert numbers_known(text, known) is ok


def test_text_gates_number_gate_uses_whole_numbers():
    assert text_gates(["합성 폭 240"], "합성 폭 2400")["numbers"] == "fail"
    assert text_gates(["합성 폭 2,400"], "합성 폭 2400")["numbers"] == "pass"


def test_chat_answer_check_uses_whole_numbers(monkeypatch):
    """챗봇 답 검사(:func:`foms.services.brain.chat_answer.verify`)도 같은 함수 — 근거 글에 없는 수면 '모름'."""
    import foms.services.brain.chat_answer as ca
    monkeypatch.setattr(ca, "known_numbers_text", lambda _retrieval, _evidence: "합성 길이 2400")

    class Retrieval:
        usable = [type("C", (), {"key": "common/x"})()]
        checks = []

    def answer(text):
        return {"check_ids": [], "evidence_ids": ["common/x"], "kind": "fact", "unknown": False, "answer": text,
                "layer": "common", "confidence": "confirmed"}

    monkeypatch.setattr(ca, "_unknown", lambda _r, _o, why, _c: why)
    assert verify(answer("합성 길이 240"), Retrieval()) == "numbers"
    assert isinstance(verify(answer("합성 길이 2,400"), Retrieval()), Verified)
