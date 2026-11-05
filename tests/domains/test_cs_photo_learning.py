"""읽은 손님 사진 → 회사 지식 제안(설계서 17.11.1 의 7 · 사장님 D172) — 근거 관문 · 제안 길로만(직접 쓰기 0) · 숫자 세탁 막기 ·
가림 · 주 한 번 · 처음 끔 · 같은 안 다시 안 냄.

합성 차례 · 합성 그림 읽기 결과 · 합성 회사 지식 · 가짜 학습 모델 · 가짜 부딪침 판정자만(네트워크 0). 손님 글 · 직원 이름 · 금액
없음. 시각은 2026-11 KST(11-02 월 — 창 안은 04:00).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.store import current_object
from foms.services.cs_agent import learning_pass, photo_learning
from foms.services.cs_agent.edit_detail_settings import PHOTO_LEARN_FIELD
from foms.services.cs_agent.photo_learning_prompt import INSTRUCTIONS
from models import CsAgentTurn
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_photo_cases import read_row
from tests.domains.test_cs_photo_read import PHONE
from tests.domains.test_cs_weekly_fix import NOW, panel
from tests.support.brain_support import agent_judge, create, person
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys, naive  # noqa: F401 — keys 는 fixture

SITUATION_TEXT = "손님이 문 처짐 사진을 보내면 경첩 조정 안내 영상을 먼저 보내고 담당자가 방문 여부를 확인한다"


def done_turn(chat: str, staff: int, *, outcome="direct", intent="defect", held_out=False) -> int:
    """끝난 차례 하나(가린 질문 · 직원이 보낸 가린 답) + 그 차례가 읽은 사진 하나."""
    row = CsAgentTurn(brand="LAHOM", chat_id=chat, last_user_message_id=f"m-{chat}-{staff}", state="stored",
                      outcome=outcome, intent=intent, sent_by_user_id=staff, held_out=held_out,
                      masked_question="합성 문이 처졌어요", staff_reply_masked="합성 경첩 조정 안내 드립니다",
                      updated_at=naive(at(1, 10)))
    db_session.add(row)
    db_session.commit()
    read_row(row.id, chat=chat)
    return row.id


def on(**extra):
    panel(**{PHOTO_LEARN_FIELD: True, **extra})


@pytest.fixture
def world(channel):
    """회사 지식(합성) — 제품 라인 하나 · 상황 하나(반영된 것)."""
    admin = person(db_session, "photo-learn-admin")
    create(db_session, admin, "common/door-hinged", item_type="product_line", layer="common", brand="COMMON",
           name="합성 여닫이")
    create(db_session, admin, "lahom/sit-door", item_type="situation", layer="cs", brand="LAHOM", name="합성 문 처짐",
           text="합성 문 처짐 상황")
    db_session.commit()
    return admin


@pytest.fixture
def evidence(world):
    """서로 다른 손님 2 · 직원 2 사진 차례(근거 관문을 넘는다)."""
    return [done_turn("uc-1", 11), done_turn("uc-2", 12, outcome="edited")]


def ask(ids, **fields):
    base = {"group": 0, "kind": "new_situation", "key": "", "target_key": "", "name": "합성 문 처짐 사진",
            "text": SITUATION_TEXT, "aliases": [], "why": "합성 — 두 손님 모두 문 처짐 사진과 같은 안내",
            "evidence_turn_ids": list(ids)}
    return {**base, **fields}


def changes():
    db_session.expire_all()
    return list(db_session.scalars(select(BrainChange).where(BrainChange.proposed_by == "agent:cs_photo")
                                   .order_by(BrainChange.id)))


# ── 끄고 켜기 · 주 한 번 ─────────────────────────────────────────────────
def test_off_by_default_outside_the_window_and_once_a_week(evidence):
    client = FakeAnthropic({"proposals": []})
    panel()
    assert photo_learning.run_photo_learning(db_session, now=NOW, client=client) == {"off": "switch_off"}
    on()
    assert photo_learning.run_photo_learning(db_session, now=at(3, 4), client=client) == {"off": "not_window"}
    first = photo_learning.run_photo_learning(db_session, now=NOW, client=client)
    assert (first["groups"], first["evidence_ok"], first["filed"]) == (1, 1, 0) and len(client.params) == 1
    again = photo_learning.run_photo_learning(db_session, now=at(2, 5), client=client)
    assert again == {"off": "already_this_week"} and len(client.params) == 1


@pytest.mark.parametrize("people", [(("uc-1", 11), ("uc-1", 12)), (("uc-1", 11), ("uc-2", 11))])
def test_one_customer_or_one_staff_alone_never_reaches_the_model(world, people):
    on()
    for chat, staff in people:
        done_turn(chat, staff)
    done_turn("uc-3", 13, held_out=True)  # 떼어 둔 줄은 읽지 않는다
    done_turn("uc-4", 14, outcome="copied")  # 복사 · 버림은 학습 재료가 아니다
    client = FakeAnthropic({"proposals": []})
    counts = photo_learning.run_photo_learning(db_session, now=NOW, client=client)
    assert (counts["groups"], counts["evidence_ok"], client.params) == (1, 0, [])


def test_groups_are_photo_kind_and_intent_and_the_prompt_quotes_material(evidence):
    on()
    (group,) = photo_learning.collect_photo_groups(db_session, NOW)
    assert (group.kind, group.intent, [c["turn_id"] for c in group.cases]) == ("site_photo", "defect", evidence)
    client = FakeAnthropic({"proposals": []})
    photo_learning.run_photo_learning(db_session, now=NOW, client=client)
    (params,) = client.params
    body = params["messages"][0]["content"][0]["text"].split("\n")
    assert "[common/door-hinged] product_line 합성 여닫이: 합성 설명 합성 여닫이" in body
    head = body.index(f"사례 {evidence[0]} 손님이 보낸 사진(읽은 것):")
    assert body[head + 1].startswith("| 현장 사진: 합성 현장 사진") and PHONE not in "\n".join(body)
    assert params["system"][0]["text"] == INSTRUCTIONS and params["model"] == "claude-sonnet-5-5"


# ── 제안 길로만 ──────────────────────────────────────────────────────────
def test_passing_ideas_become_open_agent_proposals_and_nothing_is_applied(evidence):
    on()
    client = FakeAnthropic({"proposals": [
        ask(evidence),
        ask(evidence, kind="alias", key="common/door-hinged", name="", text="", aliases=["합성 문짝 처짐"]),
        ask(evidence, kind="link", key="lahom/sit-door", target_key="common/door-hinged", name="", text=""),
        ask(evidence, kind="update", key="lahom/sit-door", name="", text="합성 문 처짐 상황 — 사진이 오면 경첩 안내"),
    ]})
    with agent_judge():
        counts = photo_learning.run_photo_learning(db_session, now=NOW, client=client)
    assert (counts["proposed"], counts["filed"], counts["blocked"]) == (4, 4, {})
    rows = changes()
    assert [(c.op, c.item_type, c.status) for c in rows] == [("create", "situation", "open"),
                                                              ("update", "product_line", "open"),
                                                              ("link_add", "situation", "open"),
                                                              ("update", "situation", "open")]
    assert all(c.evidence == [f"case:{i}" for i in evidence] for c in rows)  # 근거는 차례 번호뿐
    assert rows[0].item_key.startswith("lahom/photo-2026-w45-") and rows[0].layer == "cs"
    assert rows[1].fields["payload"]["after"]["aliases"] == ["합성 문짝 처짐"]
    assert current_object(db_session, rows[0].item_key) is None  # 승인 전엔 아무것도 바뀌지 않는다
    assert (current_object(db_session, "common/door-hinged").payload or {}).get("aliases") in (None, [])


@pytest.mark.parametrize("bad, code", [
    ({"text": SITUATION_TEXT + " 보증 37개월"}, "mask"),  # 지식에 없는 숫자 — 세탁 막기
    ({"why": f"연락처 {PHONE}"}, "mask"),
    ({"evidence_turn_ids": [999]}, "evidence"),
    ({"group": 5}, "form"),
    ({"kind": "update", "key": "common/door-hinged"}, "target"),  # 제품 글은 사진 학습이 고치지 않는다
    ({"kind": "link", "key": "lahom/sit-door", "target_key": "lahom/none"}, "target"),
    ({"kind": "alias", "key": "common/door-hinged", "aliases": []}, "target"),
])
def test_blocked_ideas_are_counted_and_never_filed(evidence, bad, code):
    on()
    client = FakeAnthropic({"proposals": [ask(evidence, **bad)]})
    with agent_judge():
        counts = photo_learning.run_photo_learning(db_session, now=NOW, client=client)
    assert counts["filed"] == 0 and counts["blocked"] == {code: 1} and changes() == []


def test_the_brain_gates_still_block_and_the_same_open_idea_is_not_filed_twice(evidence):
    on()
    raw = [ask(evidence)]
    counts = photo_learning.file_proposals(db_session, raw, photo_learning.collect_photo_groups(db_session, NOW),
                                           week="2026-W45", now=NOW, known="")
    assert counts == {"filed": 0, "brain_gate": 1} and changes() == []  # 부딪침 판정을 못 하면 넣지 않는다(제안 길)
    with agent_judge():
        first = photo_learning.file_proposals(db_session, raw, photo_learning.collect_photo_groups(db_session, NOW),
                                              week="2026-W45", now=NOW, known="")
        again = photo_learning.file_proposals(db_session, raw, photo_learning.collect_photo_groups(db_session, NOW),
                                              week="2026-W46", now=NOW, known="")
    assert first == {"filed": 1} and again == {"filed": 0, "open_proposal": 1} and len(changes()) == 1


def test_the_learning_pass_runs_photo_learning_and_stays_quiet_when_off(evidence):
    panel()
    out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None, client=FakeAnthropic({}))
    assert out is None or "photo_learning" not in out  # 꺼진 길은 요약에 싣지 않는다
    on()
    client = FakeAnthropic({"proposals": []})
    out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None, client=client)
    assert out["photo_learning"]["evidence_ok"] == 1
