"""master brain 글 관문(설계서 6절 관문 ① · 상담 17.6 관문 1) — 숫자 출처는 숫자 조각 통째로 견준다(글자 일부 겹침 아님) ·
가림 · 한자 관문은 실음 칸(항목 · 링크) 안의 글도 본다(고침은 새로 들어온 글만).

숫자 · 전화 꼴은 꾸민 값이고 금액 · 손님 글 · 직원 이름이 아니다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.chat_answer import Verified, verify
from foms.services.brain.decide import apply_decision
from foms.services.brain.errors import BrainGateError
from foms.services.brain.gates import numbers_known, payload_gates, payload_texts, text_gates
from foms.services.brain.proposals import Proposer, propose_create, propose_link, propose_update
from tests.support.brain_support import NOW, REASON, TWO_SOURCES, agent_judge, create, person, values


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


# ── 실음 칸 글 관문(항목 · 링크) ──────────────────────────────────────────
PHONE = "합성 연락처 010-0000-1111"  # 전화 꼴(꾸민 번호)
HANJA = "합성 " + chr(0x6728) + " 메모"  # 한자 한 글자 — 글자는 코드 값으로 만든다


def test_payload_texts_walks_nested_values_and_skips_unchanged_ones():
    payload = {"a": "하나", "b": [{"c": "둘"}, "셋"], "n": 3, "d": {"e": {"f": "넷"}}}
    assert sorted(payload_texts(payload)) == ["넷", "둘", "셋", "하나"]
    assert payload_texts(payload, before={"a": "하나", "b": [{"c": "둘"}, "셋"]}) == ["넷"]  # 새로 들어온 글만
    deep = "끝"
    for _ in range(12):
        deep = {"x": deep}
    assert payload_texts(deep) is None and payload_gates(deep) == {"mask": "fail", "hanja": "fail"}  # 못 본 글은 실패
    assert payload_gates({"n": 1}) == {} and payload_gates(None) == {}


@pytest.mark.parametrize("payload, failed", [
    ({"note": PHONE}, "mask"),
    ({"steps": [{"say": HANJA}]}, "hanja"),
    ({"note": "합성 [이름] 님"}, "mask"),  # 가림 표시
])
def test_payload_gates_catch_personal_info_and_hanja(payload, failed):
    assert payload_gates(payload)[failed] == "fail"
    assert payload_gates({"note": "합성 메모", "day": "2026-11-02", "ref": "calc:product/1"}) == {
        "mask": "pass", "hanja": "pass"}


@pytest.fixture
def _judge():
    with agent_judge():
        yield


def test_agent_proposals_are_blocked_by_payload_text(app, _judge):
    person(db_session, "tg_admin")
    agent = Proposer.agent_named("cs_agent")
    for payload, gate in (({"note": PHONE}, "mask"), ({"steps": [HANJA]}, "hanja")):
        with pytest.raises(BrainGateError) as caught:
            propose_create(db_session, key="lahom/sit", brand="LAHOM", layer="cs", item_type="situation",
                           values=values("sit", text="합성 상황", payload=payload), reason=REASON, proposer=agent,
                           evidence=TWO_SOURCES, known="")
        assert gate in caught.value.failed
    human = propose_create(db_session, key="lahom/sit", brand="LAHOM", layer="cs", item_type="situation",
                           values=values("sit", text="합성 상황", payload={"note": PHONE}), reason=REASON,
                           proposer=Proposer.user(1), known="")
    assert human.gates["mask"] == "fail"  # 사람 제안은 남기고 승인자가 본다


def test_updates_check_only_new_payload_text(app, _judge):
    admin = person(db_session, "tg_admin")
    create(db_session, admin, "lahom/sit", item_type="situation", layer="cs", brand="LAHOM",
           payload={"old": HANJA})  # 사람이 넣은 옛 글(그때 관문 결과는 남았다)
    db_session.commit()
    agent = Proposer.agent_named("cs_agent")
    ok = propose_update(db_session, key="lahom/sit", base_version=1, reason=REASON, proposer=agent,
                        after={"payload": {"old": HANJA, "new": "합성 새 메모"}}, evidence=TWO_SOURCES, known="")
    assert ok.gates["hanja"] == "pass" and ok.gates["mask"] == "pass"
    with pytest.raises(BrainGateError):
        propose_update(db_session, key="lahom/sit", base_version=1, reason=REASON, proposer=agent,
                       after={"payload": {"old": HANJA, "new": PHONE}}, evidence=TWO_SOURCES, known="")


def test_link_payload_text_is_gated(app, _judge):
    admin = person(db_session, "tg_admin")
    create(db_session, admin, "lahom/tpl", item_type="template", layer="cs", brand="LAHOM",
           payload={"doc_id": "tpl", "intents": ["hours"], "tags": [], "approved_by": "합성", "approved_at": "2026-10-20"})
    create(db_session, admin, "lahom/sit", item_type="situation", layer="cs", brand="LAHOM")
    db_session.commit()
    agent = Proposer.agent_named("cs_agent")
    with pytest.raises(BrainGateError):
        propose_link(db_session, op="link_add", kind="answers", from_key="lahom/tpl", to_key="lahom/sit", reason=REASON,
                     proposer=agent, values={"payload": {"note": PHONE}}, evidence=TWO_SOURCES)
    human = propose_link(db_session, op="link_add", kind="answers", from_key="lahom/tpl", to_key="lahom/sit",
                         reason=REASON, proposer=Proposer.user(admin.id), values={"payload": {"note": HANJA}})
    assert human.gates["hanja"] == "fail" and human.gates["mask"] == "pass"
    plain = propose_link(db_session, op="link_add", kind="answers", from_key="lahom/tpl", to_key="lahom/sit",
                         reason=REASON + " 둘", proposer=Proposer.user(admin.id))
    assert "hanja" not in plain.gates  # 실음 칸 글이 없으면 결과 칸도 없다(예전 꼴 그대로)


def test_edit_apply_rechecks_payload_text(app):
    admin = person(db_session, "tg_admin")
    change = propose_create(db_session, key="lahom/sit", brand="LAHOM", layer="cs", item_type="situation",
                            values=values("sit", text="합성 상황"), reason=REASON, proposer=Proposer.user(admin.id),
                            known="")
    db_session.commit()
    apply_decision(db_session, change.id, actor=admin, base_version=None, edits={"payload.pref_label": HANJA}, now=NOW)
    db_session.commit()
    assert db_session.get(BrainChange, change.id).gates["hanja"] == "fail"
