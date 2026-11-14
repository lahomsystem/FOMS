"""지식 카드 '쓰인 곳'(설계서 2026-11-14-foms-graft 3.8) — 수 · 순서 · 가린 글만 · 볼 수 없는 제안 · 이어진 ERP 물건.

1. 지난 14일 읽은 쪽마다 수(15일 전 줄은 빠짐 — 대조군) · 최근 네 줄 새것 먼저 · 찾을 수 없는 차례는 건너뜀.
2. 글은 가린 글만(상담 차례 ``masked_question`` 앞부분 · 제안 제목 · 물어보기 가린 질문) — 가림 검사에 걸리는 글은 빈 글. 묻는 사람 ·
   보낸 직원 번호는 없다.
3. 볼 수 없는 할 일 제안(``actions`` 스위치 끔)은 줄에 없다 — 켠 ADMIN 은 본다(대조군).
4. 이어진 ERP 물건: 적용 대상 제품 라인 → 주문 품목(수는 세지 않음) · 공정 단계 → ERP 단계 이름 짝 · 항목 자신.
5. 볼 수 없는 · 없는 항목은 ``None``.
합성 항목 · 합성 계정 · 지어낸 글만.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.brain.models import BrainQuestion
from foms.persistence.graft.models import ErpActionProposal
from foms.services.brain.scope import viewer_of
from foms.services.brain.usage_events import record_uses
from foms.services.brain.usage_view import item_usage
from foms.services.graft_flags import FLAGS
from models import CsAgentTurn
from tests.support.brain_screen_support import TODAY, world
from tests.support.brain_support import create, link

NOW = datetime.datetime(2026, 11, 2, 3, 0)
LEAKY = "연락처 01" + "0-5550-7319 로 주세요"  # 가림 검사에 걸리는 글(실행 때 만든다)


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)


def _turn(question, outcome):
    row = CsAgentTurn(brand="lahome", chat_id="uc-syn", last_user_message_id=f"m-{question[:4]}", state="posted",
                      masked_question=question, outcome=outcome, sent_by_user_id=77)
    db_session.add(row)
    db_session.flush()
    return row.id


def _proposal(status):
    row = ErpActionProposal(action="add_construction_note", proposed_by="agent:cs", order_id=None, params={},
                            level=2, status=status, dedupe_key=f"add_construction_note:-:{status}")
    db_session.add(row)
    db_session.flush()
    return row.id


def _question(text, unknown):
    row = BrainQuestion(asked_at=NOW, asker_id=55, masked_question=text, answer="합성 답", unknown=unknown)
    db_session.add(row)
    db_session.flush()
    return row.id


@pytest.fixture
def who(app):
    people = world(db_session)
    admin = people["admin"]
    create(db_session, admin, "common/cut", item_type="process_step", name="도어 재단",
           payload={"erp_stage": "PRODUCTION", "step_order": 3})
    link(db_session, admin, "at_step", "common/fresh", "common/cut")
    link(db_session, admin, "applies_to", "common/fresh", "common/door")
    key = "common/fit"
    uses = [  # (읽은 쪽, 종류, 번호, 몇 시간 전)
        ("cs_draft", "cs_turn", _turn("슬라이딩 문 깊이 55cm 도 되나요", "as_is"), 1),
        ("erp_action", "proposal", _proposal("rejected"), 2),
        ("chatbot", "question", _question("문짝 맞춤 규칙이 뭐예요?", False), 3),
        ("cs_draft", "cs_turn", _turn("드레스룸도 미닫이 돼요?", "edited"), 4),
        ("cs_draft", "cs_turn", _turn(LEAKY, None), 5),
        ("cs_draft", "cs_turn", "999999", 6),  # 지워진 차례 — 줄에서 건너뛴다(수에는 든다)
        ("chatbot", "question", _question("옛 질문", True), 24 * 15),  # 14일 밖 — 수에 안 든다
    ]
    for reader, kind, ref, hours in uses:
        record_uses(db_session, [key], reader, kind, ref, NOW - datetime.timedelta(hours=hours))
    db_session.commit()
    return people


def _usage(user, key="common/fit"):
    return item_usage(db_session, viewer_of(user), user, key, today=TODAY, now_utc=NOW)


def test_counts_by_reader_in_the_last_14_days(who):
    out = _usage(who["admin"])
    assert out["days"] == 14
    assert out["by_reader"] == {"cs_draft": 4, "erp_action": 1, "chatbot": 1}  # 15일 전 물어보기는 빠진다


def test_recent_rows_are_newest_first_masked_and_skip_hidden_proposals(who):
    rows = _usage(who["admin"])["recent"]  # actions 스위치 끔 — 제안 줄은 볼 수 없다
    assert [(r["reader"], r["agent_label"], r["text"], r["state"], r["tone"]) for r in rows] == [
        ("cs_draft", "상담 AI", "슬라이딩 문 깊이 55cm 도 되나요", "보냄", "success"),
        ("chatbot", "지식 물어보기", "문짝 맞춤 규칙이 뭐예요?", "답함", "success"),
        ("cs_draft", "상담 AI", "드레스룸도 미닫이 돼요?", "고쳐 보냄", "primary"),
        ("cs_draft", "상담 AI", "", "초안", "primary"),  # 가림 검사에 걸린 글은 빈 글
    ]
    assert all(r["day"] == "2026-11-02" for r in rows)
    flat = repr(rows)
    assert "7319" not in flat and "77" not in flat and "55" not in flat.replace("55cm", "")  # 전화 · 사람 번호 없음


def test_proposal_rows_show_for_people_who_may_see_proposals(who, monkeypatch):
    for env in ("FOMS_GRAFT_BRAIN_UI", "FOMS_GRAFT_ACTIONS"):
        monkeypatch.setenv(f"{env}_ENABLED", "1")
        monkeypatch.setenv(f"{env}_COHORT", "all")
    rows = _usage(who["admin"])["recent"]
    assert [(r["reader"], r["agent_label"], r["text"], r["state"], r["tone"]) for r in rows][1] == (
        "erp_action", "상담 AI", "시공 메모 더하기", "거절", "danger")
    assert len(rows) == 4 and rows[-1]["text"] == "드레스룸도 미닫이 돼요?"
    viewer_rows = _usage(who["cs_mgr"])["recent"]  # 상담 팀장은 ERP_EDIT 정책을 지난다 — 같이 보인다
    assert any(r["reader"] == "erp_action" for r in viewer_rows)


def test_erp_links_pair_product_lines_and_process_steps(who):
    fit = _usage(who["admin"])["erp_links"]
    assert fit == [{"rel": "applies_to", "type": "erp:order_item", "type_label": "주문 품목", "label": "여닫이 문짝",
                    "note": "주문 품목 이름과 이어져요"}]
    fresh = _usage(who["admin"], "common/fresh")["erp_links"]
    assert {(r["rel"], r["label"], r["note"]) for r in fresh} == {
        ("applies_to", "여닫이 문짝", "주문 품목 이름과 이어져요"), ("at_step", "도어 재단", "ERP 단계 · 생산")}
    own = _usage(who["admin"], "common/cut")["erp_links"]
    assert own == [{"rel": "at_step", "type": "erp:order", "type_label": "주문", "label": "도어 재단",
                    "note": "ERP 단계 · 생산", "stage": "PRODUCTION"}]
    assert _usage(who["admin"], "common/door")["erp_links"][0]["type"] == "erp:order_item"  # 제품 라인 자신
    assert all("count" not in r for r in fit + fresh)  # 진행 중 주문 수는 세지 않는다


def test_hidden_or_missing_item_is_none(who):
    assert _usage(who["cs_mgr"], "common/discount") is None  # 가격 재량 — 상담 팀장 범위 밖
    assert _usage(who["admin"], "common/discount") is not None  # 대조군
    assert _usage(who["admin"], "common/nothing") is None
    empty = _usage(who["admin"], "common/slide")
    assert empty["by_reader"] == {"cs_draft": 0, "erp_action": 0, "chatbot": 0} and empty["recent"] == []
