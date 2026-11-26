"""밤 배우기 지식 목록 아껴 보내기(설계 글 2026-11-26 6절) — 처음 끔이면 요청이 예전과 글자까지 같다 · 켜면 지시문 + 그 밤 굳힌
목록이 ``system`` 두 블록(뒤 블록에만 1시간 캐시 표시)이고 부르기 사이에 글자 하나 안 바뀐다 · 밤 중에 넣은 지식은 다음 부르기
사용자 글 꼬리 줄로 보인다(그 밤 두 벌 막기) · 다음 날은 새로 굳힌다 · 굳힐 차례는 파이썬 글자 차례 · 캐시 읽은 · 쓴 토큰은 로그
줄에 · 값은 캐시 읽기 · 1시간 쓰기 단가로 · 상한 예약은 캐시를 믿지 않는다 · 상담 초안 쪽 캐시 표시는 그대로.

합성 차례 · 합성 지식 · 가짜 학습 모델만(네트워크 0 — 모델 API 는 부르지 않는다). 손님 글 · 직원 이름 · 실제 금액 없음.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaMessage

from db import db_session
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import brain_spend
from foms.services.cs_agent import handoff_learning as hl
from foms.services.cs_agent import handoff_learning_cache as cache
from foms.services.cs_agent import handoff_learning_prompt as hp
from foms.services.cs_agent.brain_media import media_tokens
from foms.services.cs_agent.handoff_learn_settings import CACHE_FIELD, CASES_FIELD
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.settings import read_settings
from models import SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.domains.test_cs_handoff_learning import NOW, admin, handed, on, run, two  # noqa: F401 — admin · two 는 fixture
from tests.support.brain_support import create
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys  # noqa: F401 — keys 는 fixture

ANSWER = {"proposals": [], "ontology": []}
HOUR_MARK = {"type": "ephemeral", "ttl": "1h"}
OLD_KNOWLEDGE_HEAD = "회사 지식(지금 반영된 것 — 키는 대괄호 안):"


def old_build_params(blocks, knowledge, pending, *, model, cfg, ontology=(), differs=(), effort="medium", images=()):
    """바꾸기 전 :func:`.handoff_learning_prompt.build_params` 그대로(11-26 스테이징 기준) — 끄면 이 꼴과 글자까지 같아야 한다."""
    body = [OLD_KNOWLEDGE_HEAD, *(knowledge or ["(없음)"]),
            "온톨로지 목록(상황 · 제작 조건 · 제품 · 옵션 — 키는 대괄호 안):", *(ontology or ["(없음)"]),
            "이미 낸 제안(승인 기다림 — 같은 것을 다시 내지 않는다):", *(pending or ["(없음)"]),
            "이미 모아 둔 다른 말(키 · 대상 항목 키 · 직원이 한 말 — 같은 말이 또 나오면 repeats 에 그 키):",
            *(differs or ["(없음)"]),
            "직원이 직접 답한 상담 사례(넘김 · 고쳐 보냄 · 초안 안 씀 · 초안 없음 — 가린 글):"]
    for block in blocks:
        body += block
    params = {"model": model, "max_tokens": 16000, "thinking": {"type": "adaptive"},
              "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": hp._schema()}},
              "system": [{"type": "text", "text": hp.INSTRUCTIONS}],
              "messages": [{"role": "user", "content": [*(dict(b) for b in images),
                                                        {"type": "text", "text": "\n".join(body)}]}]}
    if cfg.fallback_on(model):
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    return params


def text_of(params) -> str:
    return params["messages"][0]["content"][-1]["text"]


def between(text: str, start: str, end: str) -> list[str]:
    """``start`` 줄 다음부터 ``end`` 줄 앞까지."""
    lines = text.split("\n")
    first = lines.index(start) + 1
    return lines[first:lines.index(end, first)]


def as_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


PICS = [{"type": "text", "text": "사진 1"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}]
CASES = [["사례 1 합성:", "| 합성 사례 글"]]


# ── 끔(처음 값) — 예전과 글자까지 같다 ───────────────────────────────────
@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"])
def test_off_the_request_is_the_old_one_letter_for_letter(admin, model):  # noqa: F811
    cfg = read_settings(db_session, log=False)
    args = (CASES, ["[k-1] 사실 합성 이름: 합성 글"], ["- 합성 제안: 합성 글"])
    extra = {"ontology": ["[o-1] situation 합성 상황: 합성 글"], "differs": ["- [c-1] 대상 [k-1]: 합성 말"],
             "effort": "medium", "images": PICS}
    for kwargs in ({}, extra):
        new = hp.build_params(*args, model=model, cfg=cfg, **kwargs)
        assert as_json(new) == as_json(old_build_params(*args, model=model, cfg=cfg, **kwargs))
        assert hp.build_params(*args, model=model, cfg=cfg, frozen=None, **kwargs) == new
        assert "cache_control" not in as_json(new)


def test_off_by_default_the_night_never_touches_the_list_row(two):  # noqa: F811
    assert read_settings(db_session, log=False).get(CACHE_FIELD) is False  # 처음 값 끔
    on()
    client = FakeAnthropic(ANSWER)
    counts = run(client)
    (params,) = client.params
    assert len(params["system"]) == 1 and "cache_control" not in as_json(params)
    assert text_of(params).startswith(OLD_KNOWLEDGE_HEAD) and "[lahom/shelf-depth]" in text_of(params)
    assert db_session.get(SystemSetting, cache.STORE_KEY) is None  # 끄면 굳힌 목록 줄을 읽지도 만들지도 않는다
    assert (counts["cache_read"], counts["cache_write"]) == (0, 0)


# ── 켬 — 굳힌 목록 · 꼬리 줄 ─────────────────────────────────────────────
def test_on_the_list_is_frozen_for_the_night_and_new_knowledge_rides_the_tail(two, admin):  # noqa: F811
    on(**{CACHE_FIELD: True, CASES_FIELD: 2})
    client = FakeAnthropic(ANSWER)
    run(client)
    create(db_session, admin, "lahom/night-fact", item_type="fact", brand="LAHOM", name="합성 밤 새 사실",
           text="합성 밤에 새로 들어간 사실 글",  # 그 밤 바로 반영된 지식(배운 것 바로 반영과 같은 자리)
           payload={"doc_id": "night-fact", "approved_by": "합성", "approved_at": "2026-10-20"})
    create(db_session, admin, "lahom/night-sit", item_type="situation", layer="cs", brand="LAHOM", name="합성 밤 새 상황",
           text="합성 밤에 새로 들어간 상황 글")
    db_session.commit()
    handed("uc-3")
    run(client, now=at(11, 2, 15))
    first, second = client.params
    assert as_json(first["system"]) == as_json(second["system"])  # 부르기 사이에 앞부분 글자 하나 안 바뀐다
    instructions, frozen = first["system"]
    assert instructions == {"type": "text", "text": hp.INSTRUCTIONS}  # 지시문 글 그대로 · 표시 없음
    assert frozen["cache_control"] == HOUR_MARK and frozen["text"].startswith(hp.FROZEN_HEADS[0])
    assert "[lahom/shelf-depth]" in frozen["text"] and "[lahom/night-fact]" not in frozen["text"]
    assert "cache_control" not in as_json(first["messages"])  # 표시는 굳힌 목록 끝 하나뿐
    for params in (first, second):  # 목록은 사용자 글에 다시 가지 않는다
        assert OLD_KNOWLEDGE_HEAD not in text_of(params) and "[lahom/shelf-depth]" not in text_of(params)
    assert between(text_of(first), hp.TAIL_HEADS[0], hp.TAIL_HEADS[1]) == ["(없음)"]
    tail = between(text_of(second), hp.TAIL_HEADS[0], hp.TAIL_HEADS[1])
    assert [line.split("]")[0] for line in tail] == ["[lahom/night-fact"]  # 밤 중에 넣은 지식이 다음 부르기에 보인다
    onto_tail = between(text_of(second), hp.TAIL_HEADS[1], "이미 낸 제안(승인 기다림 — 같은 것을 다시 내지 않는다):")
    assert [line.split("]")[0] for line in onto_tail] == ["[lahom/night-sit"]
    stored = db_session.get(SystemSetting, cache.STORE_KEY, populate_existing=True).setting_value
    assert stored["day"] == "2026-11-11" and hp.frozen_text(stored["knowledge"], stored["ontology"]) == frozen["text"]
    handed("uc-4")
    run(client, now=at(12, 1))  # 다음 밤 — 새로 굳힌다(어젯밤 넣은 지식이 목록 안으로)
    third = client.params[2]
    assert third["system"][1]["text"] != frozen["text"] and "[lahom/night-fact]" in third["system"][1]["text"]
    assert "[lahom/night-sit]" in third["system"][1]["text"]
    assert between(text_of(third), hp.TAIL_HEADS[0], hp.TAIL_HEADS[1]) == ["(없음)"]
    assert db_session.get(SystemSetting, cache.STORE_KEY, populate_existing=True).setting_value["day"] == "2026-11-12"


def row(key, item_type="fact", brand="LAHOM", text="합성 글"):
    return SimpleNamespace(item_key=key, item_type=item_type, brand=brand, status="active", visibility="all",
                           name=f"합성 {key}", text=text, payload={})


def test_the_frozen_order_is_python_letter_order_and_changed_lines_go_to_the_tail(admin):  # noqa: F811
    rows = [row("lahom/나"), row("common/b", "template", "COMMON"), row("lahom/b", "policy"), row("lahom/a"),
            row("common/a", "owner_decision", "COMMON")]
    assert [r.item_key for r in cache.ordered(rows)] == ["lahom/a", "lahom/b", "lahom/나", "common/a", "common/b"]
    assert cache.ordered(list(reversed(rows))) == cache.ordered(rows)  # 들어온 차례와 상관없다
    cfg = read_settings(db_session, log=False)
    frozen = cache.NightLists(tuple(hp.knowledge_lines(cache.ordered(rows))), ("[o-1] situation 합성 상황: 합성 글",))
    changed = [*hp.knowledge_lines([*rows[:-1], row("common/a", "owner_decision", "COMMON", "합성 바뀐 글")])]
    plain = hp.build_params(CASES, changed, [], model="claude-sonnet-5-5", cfg=cfg, ontology=frozen.ontology,
                            frozen=frozen)
    tail = between(text_of(plain), hp.TAIL_HEADS[0], hp.TAIL_HEADS[1])
    assert tail == [line for line in changed if "common/a" in line] and "합성 바뀐 글" in tail[0]
    assert between(text_of(plain), hp.TAIL_HEADS[1], "이미 낸 제안(승인 기다림 — 같은 것을 다시 내지 않는다):") == ["(없음)"]
    with_pics = hp.build_params(CASES, changed, [], model="claude-sonnet-5-5", cfg=cfg, ontology=frozen.ontology,
                                frozen=frozen, images=PICS)
    assert with_pics["system"] == plain["system"]  # 사진은 사용자 글 앞 — 캐시 앞부분(system)에 닿지 않는다
    assert with_pics["messages"][0]["content"] == [*PICS, *plain["messages"][0]["content"]]
    assert {k: v for k, v in plain.items() if k not in ("system", "messages")} == {
        k: v for k, v in old_build_params(CASES, changed, [], model="claude-sonnet-5-5", cfg=cfg).items()
        if k not in ("system", "messages")}  # 모델 · 생각 · 세기 · 구조 출력 · 대체는 그대로


# ── 돈 · 로그 ────────────────────────────────────────────────────────────
class CachedAnthropic(FakeAnthropic):
    """캐시 읽기 · 1시간 쓰기 토큰이 든 응답을 내는 가짜 학습 모델."""

    def create(self, **params):
        self.params.append(params)
        return BetaMessage.model_validate({
            "id": "msg_synthetic", "type": "message", "role": "assistant", "model": params["model"],
            "content": [{"type": "text", "text": json.dumps(ANSWER)}], "stop_reason": "end_turn",
            "stop_sequence": None, "stop_details": None,
            "usage": {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 50000,
                      "cache_creation_input_tokens": 3000,
                      "cache_creation": {"ephemeral_1h_input_tokens": 3000, "ephemeral_5m_input_tokens": 0}}})


def test_cache_tokens_are_logged_and_priced_at_the_cache_rates(two, caplog):  # noqa: F811
    on(**{CACHE_FIELD: True})
    caplog.set_level(logging.INFO, logger=hl.logger.name)
    client = CachedAnthropic(ANSWER)
    counts = run(client)
    assert client.params[0]["model"] == "claude-sonnet-5-5"
    assert (counts["cache_read"], counts["cache_write"]) == (50000, 3000)
    assert "cache_read=50000 cache_write=3000" in caplog.text
    learning = brain_spend.today_spend(db_session, now=NOW, key=brain_spend.LEARNING_SPEND_KEY)
    # Sonnet 5.5: 1000 × $2 + 200 × $10 + 50000 × $0.10(읽기) + 3000 × $4(1시간 쓰기) = 21,000 µ$
    assert Decimal(learning["usd"]) == Decimal("0.021") and Decimal(learning["reserved"]) == 0


def test_the_reserve_never_trusts_the_cache(admin):  # noqa: F811
    cfg = read_settings(db_session, log=False)
    knowledge = [f"[k-{n}] 사실 합성 이름: 합성 글 {n}" for n in range(50)]
    frozen = cache.NightLists(tuple(knowledge), ())
    for model in ("claude-sonnet-5-5", "claude-opus-5-5"):
        off = hp.build_params(CASES, knowledge, [], model=model, cfg=cfg)
        on_ = hp.build_params(CASES, knowledge, [], model=model, cfg=cfg, frozen=frozen)
        assert bp.worst_case_cost(on_) >= bp.worst_case_cost(off)  # 캐시를 켜도 예약은 줄지 않는다
        assert on_["fallbacks"] == "default"  # 예비 모델이 켜져 있으면 시도 두 번 값 그대로
    tiny = {"model": "claude-sonnet-5-5", "max_tokens": 0}
    stripped, _media = media_tokens(tiny)
    expected = (len(as_json(stripped)) + bp.RESERVE_OVERHEAD_TOKENS) * bp.PRICES["claude-sonnet-5-5"].cache_write_1h
    assert bp.worst_case_cost(tiny) == expected / Decimal(1_000_000)  # 입력은 1시간 쓰기 값(입력의 2배)으로 잡는다


def test_the_draft_side_cache_marker_is_unchanged(channel):  # noqa: F811
    knowledge = load_approved(db_session, "LAHOM")
    for ttl in ("1h", "5m"):
        blocks = bp.system_blocks("LAHOM", knowledge, cache_ttl=ttl)
        assert [b.get("cache_control") for b in blocks] == [None, {"type": "ephemeral", "ttl": ttl}]
    plain = bp.system_blocks("LAHOM", knowledge, cache_ttl=None)
    assert plain == [{"type": "text", "text": bp.instructions("LAHOM", knowledge=knowledge)},
                     {"type": "text", "text": bp.knowledge_text(knowledge)}]
    with pytest.raises(ValueError):
        bp.system_blocks("LAHOM", knowledge, cache_ttl="2h")
    assert bp.CACHE_CONTROL_DAY == HOUR_MARK
