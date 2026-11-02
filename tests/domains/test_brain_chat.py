"""회사 지식 물어보기 — 답하는 길(설계서 10.2 순서 고정 · D88 · D99 · 12절) 가짜 모델 시험.

1. 답은 찾은 후보의 키만 근거로 단다 — 밖 키 · 근거 0 · 숫자 출처 밖이면 '모름 + 누구에게'.
2. 볼 수 없는 항목은 후보 · 두뇌에 간 글 · 근거 · 쓰인 횟수 어디에도 없다(음성 대조군 — 같은 질문 ADMIN 은 본다).
3. 가림이 모델 · 기록보다 먼저 — 가림이 못 지운 글은 기록 · 모델 모두 없음.
4. '확인 필요'(낡음 · 열린 제안)는 사실만 가고 근거로 쓸 수 없다.
5. 돈 상한(챗봇 줄 — 상담 초안 줄과 따로) · 사람마다 하루 질문 수 · 시간 상한이 두뇌 부르기에 간다.
합성 지식 · 합성 계정만.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainObject, BrainQuestion, BrainUsage
from foms.services.brain.chat_answer import ChatError, ask
from foms.services.brain.chat_settings import SPEND_KEY
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.cs_agent.brain_spend import SPEND_KEY as CS_SPEND_KEY
from models import SystemSetting
from tests.support.brain_chat_support import NOW_KST, candidates_of, chat_on, chat_world, fixed, reply
from tests.support.brain_support import NOW, REASON

Q_SLIDE = "슬라이딩 문 깊이는 얼마예요?"


@pytest.fixture
def people(app):
    return chat_world(db_session)


def _ask(user, question=Q_SLIDE, client=None, **kw):
    out = ask(db_session, user, question, client=client, now=NOW_KST, **kw)
    db_session.commit()
    return out


def _rows():
    return db_session.execute(select(BrainQuestion).order_by(BrainQuestion.id)).scalars().all()


# ── 1. 근거는 찾은 키만 ──────────────────────────────────────────────────
def test_answer_cites_only_retrieved_keys_logs_and_counts_usage(people):
    client = fixed(reply(answer="슬라이딩 깊이는 합성 규격 650mm 입니다.", evidence_ids=["common/sliding"], unknown=False,
                         confidence="high"))
    out = _ask(people["admin"], client=client)
    assert out["unknown"] is False and [c["key"] for c in out["evidence"]] == ["common/sliding"]
    assert out["confidence"] == "confirmed" and out["certainty"] == "high" and out["card_links"] is True
    params = client.calls[0]
    assert params["model"] == "claude-sonnet-5-5" and params["output_config"]["effort"] == "low"  # D99 · 보수적 처음 값
    assert "tools" not in params and "fallbacks" not in params  # 도구 없음 · 대체 없음
    schema = params["output_config"]["format"]["schema"]
    assert "common/sliding" in schema["properties"]["evidence_ids"]["items"]["enum"]
    assert client.options[0] == {"timeout": 30, "max_retries": 0}  # 시간 상한 · 다시 보내지 않음
    row = _rows()[-1]
    assert (row.unknown, row.evidence_keys, row.asker_id, row.model) == (False, ["common/sliding"], people["admin"].id,
                                                                         "claude-sonnet-5-5")
    usage = db_session.execute(select(BrainUsage.item_key, BrainUsage.reader, BrainUsage.count)).all()
    assert usage == [("common/sliding", "chatbot", 1)]
    versions = db_session.scalar(select(func.count()).select_from(BrainObject).where(
        BrainObject.item_key == "common/sliding"))
    assert versions == 1  # 쓰인 횟수는 판 줄을 새로 만들지 않는다


def test_key_outside_the_retrieved_set_discards_the_answer(people):
    client = fixed(reply(answer="재량 할인 폭은 비밀 값입니다.", evidence_ids=["common/discount"], unknown=False))
    out = _ask(people["admin"], client=client)  # ADMIN 이 볼 수 있는 항목이라도 이번 후보에 없는 키를 대면 버린다
    assert out["unknown"] is True and out["evidence"] == [] and "회사 지식에 아직 없어요" in out["answer"]
    assert db_session.scalar(select(func.count()).select_from(BrainUsage)) == 0


def test_no_evidence_means_unknown_and_who_to_ask(people):
    client = fixed(reply(answer="모르겠어요", ask_team="DRAWING", layer="drawing"))
    out = _ask(people["admin"], client=client)
    assert out["unknown"] is True and out["ask_team"] == "DRAWING"
    assert out["answer"] == "이 내용은 회사 지식에 아직 없어요 — 도면팀 팀장에게 물어보세요."
    nothing = fixed(reply())
    none = _ask(people["admin"], "주차 요금은 얼마예요?", client=nothing)  # 후보 0 — 두뇌를 부르지 않는다(돈 0)
    assert none["unknown"] is True and nothing.calls == [] and none["answer"].endswith("사장님께 물어보세요.")
    assert db_session.get(SystemSetting, SPEND_KEY).setting_value["calls"] == 1  # 앞 질문 한 번만 불렀다


def test_numbers_must_come_from_the_evidence(people):
    client = fixed(reply(answer="슬라이딩 깊이는 700mm 입니다.", evidence_ids=["common/sliding"], unknown=False))
    out = _ask(people["admin"], client=client)
    assert out["unknown"] is True  # 700 은 근거에 없다
    ok = _ask(people["admin"], client=fixed(reply(answer="합성 규격 650mm 예요.", evidence_ids=["common/sliding"],
                                                    unknown=False)))
    assert ok["unknown"] is False  # 대조군: 근거 글의 숫자


def test_erp_questions_are_not_answered(people):
    out = _ask(people["admin"], client=fixed(reply(kind="erp", unknown=True, evidence_ids=[])))
    assert out["unknown"] is True and out["ask_team"] == "erp" and "주문 화면에서 확인" in out["answer"]


# ── 2. 볼 수 없는 항목(음성 대조군) ──────────────────────────────────────
def test_unseen_items_never_reach_candidates_answers_or_counts(people):
    chat_on(db_session, stage="leads")
    question = "재량 할인 폭은 얼마예요? 도면 재단 여유도"
    client = fixed(reply(answer="재량 할인 폭은 합성 비밀 규칙입니다.", evidence_ids=["common/discount"], unknown=False))
    out = _ask(people["sales_mgr"], question, client=client)
    sent = json.dumps(client.calls, ensure_ascii=False) if client.calls else ""
    assert "재량 할인 폭" not in sent and "도면 재단 여유" not in sent and "common/discount" not in sent
    assert out["unknown"] is True and out["evidence"] == []
    assert db_session.scalar(select(func.count()).select_from(BrainUsage)) == 0
    admin_client = fixed(reply(answer="재량 할인 폭은 합성 비밀 규칙입니다.", evidence_ids=["common/discount"],
                               unknown=False))
    seen = _ask(people["admin"], question, client=admin_client)  # 대조군: 같은 질문 · ADMIN 은 본다
    block = candidates_of(admin_client.calls[0])
    assert {c["key"] for c in block["usable"]} >= {"common/discount", "drawing/bom"}
    assert seen["unknown"] is False and [c["key"] for c in seen["evidence"]] == ["common/discount"]
    dr = fixed(reply())
    _ask(people["dr_mgr"], question, client=dr)  # 도면팀 MANAGER — 팀 범위는 보고 가격 재량은 못 본다
    keys = {c["key"] for c in candidates_of(dr.calls[0])["usable"]}
    assert "drawing/bom" in keys and "common/discount" not in keys


# ── 3. 가림이 먼저 ───────────────────────────────────────────────────────
def test_question_is_masked_before_the_model_and_the_log(people):
    raw = "고객 010-2345-6789 님 집 슬라이딩 문 깊이는 얼마예요?"
    client = fixed(reply())
    _ask(people["admin"], raw, client=client)
    sent = json.dumps(client.calls[0]["messages"], ensure_ascii=False)
    assert "010-2345-6789" not in sent and "2345" not in sent and "[전화]" in sent
    row = _rows()[-1]
    assert "2345" not in row.masked_question and "[전화]" in row.masked_question


def test_unmaskable_text_is_neither_sent_nor_logged(people, monkeypatch):
    import foms.services.brain.chat_answer as chat_answer

    monkeypatch.setattr(chat_answer, "mask", lambda text: text)  # 가림이 고장 나도 검사가 막는다
    client = fixed(reply())
    with pytest.raises(ChatError) as caught:
        ask(db_session, people["admin"], "연락처 010-2345-6789 슬라이딩", client=client, now=NOW_KST)
    assert caught.value.code == "mask" and client.calls == [] and _rows() == []


# ── 4. 확인 필요 ─────────────────────────────────────────────────────────
def test_needs_check_items_go_as_facts_only(people):
    propose_update(db_session, key="common/hinge", base_version=1, after={"text": "여닫이 경첩 고침 제안"}, reason=REASON,
                   proposer=Proposer.user(people["admin"].id), now=NOW, known="")
    db_session.commit()
    client = fixed(reply(answer="몰딩 높이는 40mm 예요.", evidence_ids=["common/old-rule"], check_ids=["common/old-rule"],
                         unknown=False))
    out = _ask(people["admin"], "몰딩 높이와 여닫이 경첩 조건, 슬라이딩 깊이", client=client)
    block = candidates_of(client.calls[0])
    assert [c["key"] for c in block["usable"]] == ["common/sliding"]
    checks = {c["key"]: c["check"] for c in block["needs_check"]}
    assert checks == {"common/old-rule": "확인 날이 지남", "common/hinge": "고치는 제안이 열려 있음"}
    sent = json.dumps(block, ensure_ascii=False)
    assert "40mm" not in sent and "경첩 셋" not in sent  # 값 · 글은 가지 않는다
    assert "common/old-rule" not in client.calls[0]["output_config"]["format"]["schema"]["properties"]["evidence_ids"][
        "items"]["enum"]
    assert out["unknown"] is True and [c["key"] for c in out["checks"]] == ["common/old-rule"]  # 근거로 대면 버린다
    only = fixed(reply())
    facts = _ask(people["admin"], "몰딩 높이와 여닫이 경첩 조건", client=only)  # 확인 필요뿐 — 부르지 않고 사실만
    assert only.calls == [] and facts["unknown"] is True
    assert {c["key"] for c in facts["checks"]} == {"common/old-rule", "common/hinge"}


# ── 5. 돈 · 사람 상한 ────────────────────────────────────────────────────
def test_money_cap_is_separate_and_closed_by_default(people):
    chat_on(db_session, daily_cap_usd=None)
    with pytest.raises(ChatError) as caught:
        _ask(people["admin"], client=fixed(reply()))
    assert (caught.value.code, caught.value.reason) == ("not_ready", "chat_cap_missing")
    chat_on(db_session, daily_cap_usd="0.01")  # 한 번의 최악값보다 작다 — 예약에서 막힌다
    client = fixed(reply())
    with pytest.raises(ChatError) as caught:
        _ask(people["admin"], client=client)
    assert caught.value.code == "money_cap" and client.calls == []
    chat_on(db_session)
    _ask(people["admin"], client=fixed(reply()))
    spend = db_session.get(SystemSetting, SPEND_KEY, populate_existing=True).setting_value
    assert spend["calls"] == 1 and spend["reserved"] == "0.000000" and float(spend["usd"]) > 0
    assert db_session.get(SystemSetting, CS_SPEND_KEY) is None  # 상담 초안 돈 줄과 따로


def test_per_person_daily_question_cap(people):
    chat_on(db_session, per_person_daily=2)
    _ask(people["admin"], "주차 요금", client=fixed(reply()))
    second = _ask(people["admin"], "점심 메뉴", client=fixed(reply()))
    assert second["left_today"] == 0
    with pytest.raises(ChatError) as caught:
        _ask(people["admin"], "회식 장소", client=fixed(reply()))
    assert caught.value.code == "person_cap"
    assert _ask(people["admin2"], "회식 장소", client=fixed(reply()))["left_today"] == 1  # 대조군: 다른 사람


def test_switch_off_and_stage_close_the_service(people):
    chat_on(db_session, enabled=False)
    with pytest.raises(ChatError) as caught:
        _ask(people["admin"], client=fixed(reply()))
    assert caught.value.code == "forbidden"
    chat_on(db_session, stage="admin")
    for name in ("cs_mgr", "staff", "viewer", "partner", "off"):
        with pytest.raises(ChatError):
            _ask(people[name], client=fixed(reply()))
    chat_on(db_session, stage="leads")
    _ask(people["sales_mgr"], client=fixed(reply()))
    with pytest.raises(ChatError):
        _ask(people["staff"], client=fixed(reply()))
    chat_on(db_session, stage="all")
    for name in ("staff", "viewer"):
        _ask(people[name], client=fixed(reply()))
    for name in ("partner", "off"):  # 바깥 역할 · 꺼진 계정은 어느 단계에서도
        with pytest.raises(ChatError):
            _ask(people[name], client=fixed(reply()))
