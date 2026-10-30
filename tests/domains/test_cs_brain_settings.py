"""두뇌가 관리 패널 설정을 쓴다(설계서 16.1 · 단계 1) — 모델 · 깊이 · 출력 · 15분 루프 시간 · 캐시 · 대체 · 하루 상한.
잠긴 칸(의도 고르기 · 실시간 길)은 처음 값 그대로. 줄이 없으면 예전 그대로(음성 대조). 공식 가격표 값 · Haiku 5.5 긴 프롬프트
값 · 최악값 예약은 고른 모델 단가(대체를 보낼 때만 대체 대상과 견주고 입력 · 출력 두 번) · 준비 확인은 초안 한 번 부를 만큼
남았는지 본다 · 결과는 캐시 표시를 실었는지 알린다(검수 R9).

가짜 클라이언트만(네트워크 · 키 없음). 재료는 ``test_cs_brain`` 과 같은 합성 글이다. 초안 바퀴 쪽은 ``test_cs_panel_drafting``.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from db import db_session
from foms.services.cs_agent import brain
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import settings as st
from models import User
from tests.domains.test_cs_brain import DAY, KNOWLEDGE, NOW, FakeClient, answer, message, put_spend, request, spend, \
    usage


@pytest.fixture
def actor(app, monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")
    monkeypatch.setattr(brain, "_sleep", lambda _seconds: None)
    user = User(username="cs-brain-settings", password="x", role="ADMIN", name="합성 관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def configure(actor_id, **values):
    version = st.read_settings(db_session).version
    st.save_settings(db_session, values, expected_version=version, actor_user_id=actor_id)
    db_session.commit()


def call(req=None, *outcomes, now=NOW):
    fake = FakeClient(*outcomes)
    return brain.draft_reply(req or request(), client=fake, session=db_session, now=now), fake


class ReserveSnapshot(FakeClient):
    """보낼 때 돈 줄에 커밋된 예약을 찍는다(예약은 보내기 전에 커밋된다)."""

    def __init__(self, *outcomes):
        super().__init__(*outcomes)
        self.reserved_at_send = []
        send = self.beta.messages.create

        def create(**params):
            db_session.rollback()
            self.reserved_at_send.append(Decimal(spend()["reserved"]))
            return send(**params)

        self.beta.messages.create = create


# ── 두뇌 ─────────────────────────────────────────────────────────────────
def test_the_brain_sends_what_the_panel_chose(actor):
    configure(actor, draft_model=bp.MODEL_SONNET, draft_effort="medium", draft_max_tokens=12000, batch_timeout_s=60,
              cache_policy="always", fallback_enabled=False)
    result, fake = call(None, message(model=bp.MODEL_SONNET, use=usage(1000, 500)))
    sent = fake.calls[0]
    assert (sent["model"], sent["output_config"]["effort"], sent["max_tokens"]) == ("claude-sonnet-5-5", "medium", 12000)
    assert sent["thinking"] == {"type": "adaptive"} and sent["output_config"]["format"]["type"] == "json_schema"
    assert "betas" not in sent and "fallbacks" not in sent  # 대체 끔
    assert sent["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}  # '늘' — 밤에도 단다
    assert fake.options == [{"timeout": 60.0, "max_retries": 0}]
    assert (result.model, result.effort) == ("claude-sonnet-5-5", "medium")
    assert result.cost_usd == Decimal("0.007")  # Sonnet 5.5: 1000 × $2 + 500 × $10
    _, realtime = call(request(realtime=True), message(model=bp.MODEL_SONNET))
    assert realtime.options == [{"timeout": 45.0, "max_retries": 0}]  # 실시간 길 시간 상한은 고르지 않았으니 처음 값
    configure(actor, realtime_timeout_s=30)  # 빠른 길(C10-1)이 생겨 시간 상한은 잠금을 풀었다(다시 시도는 잠김 — 0)
    _, realtime = call(request(realtime=True), message(model=bp.MODEL_SONNET))
    assert realtime.options == [{"timeout": 30.0, "max_retries": 0}]


def test_without_a_row_the_request_is_exactly_as_before(actor):
    _, fake = call()
    sent = fake.calls[0]
    assert (sent["model"], sent["output_config"]["effort"], sent["max_tokens"]) == (brain.MODEL, "high", 16000)
    assert sent["betas"] == [brain.FALLBACK_BETA] and sent["fallbacks"] == "default"
    assert "cache_control" not in str(sent["system"]) and fake.options == [{"timeout": 90.0, "max_retries": 0}]


def test_haiku_never_sends_fallbacks_and_the_locked_intent_path_keeps_its_constants(actor):
    configure(actor, draft_model=bp.MODEL_HAIKU)  # 대체는 켬 그대로
    _, draft = call(None, message(model=bp.MODEL_HAIKU))
    assert draft.calls[0]["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in draft.calls[0] and "betas" not in draft.calls[0]  # Haiku 5.5 에는 보내지 않는다
    _, intent = call(request(purpose="intent"))
    sent = intent.calls[0]  # 의도 고르기는 잠긴 칸 — 초안 모델을 바꿔도 처음 값(Opus · low · 8000) 그대로
    assert (sent["model"], sent["output_config"]["effort"], sent["max_tokens"]) == (brain.MODEL, "low", 8000)
    assert sent["fallbacks"] == "default"  # 음성 대조: Opus 에는 대체를 보낸다


def test_cache_policy_off_drops_the_daytime_marker(actor):
    configure(actor, cache_policy="off")
    _, fake = call(request(daytime=True), now=DAY)
    assert "cache_control" not in str(fake.calls[0]["system"])
    configure(actor, cache_policy="daytime")
    _, fake = call(request(daytime=True), now=DAY)
    assert fake.calls[0]["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


# ── 캐시 길이(사장님 결정 10-29 — 처음 값 1시간) ─────────────────────────
def test_the_cache_ttl_starts_at_one_hour_and_five_minutes_can_be_chosen(actor):
    _, fake = call(request(daytime=True), now=DAY)
    sent = fake.calls[0]
    assert sent["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}  # 처음 값 1시간
    assert json.dumps(sent, ensure_ascii=False).count("cache_control") == 1  # 앞부분 끝에 하나만
    configure(actor, cache_ttl="5m")
    _, fake = call(request(daytime=True), now=DAY)
    assert fake.calls[0]["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    _, night = call(request(daytime=False), now=NOW)
    assert "cache_control" not in json.dumps(night.calls[0])  # 방침이 운영 시간만이면 밤에는 길이와 상관없이 없다


@pytest.mark.parametrize("policy,daytime,marked", [
    ("daytime", True, True), ("daytime", False, False), ("always", False, True), ("off", True, False),
])
def test_the_result_says_whether_the_request_carried_the_cache_marker(actor, policy, daytime, marked):
    if policy != "daytime":
        configure(actor, cache_policy=policy)
    result, fake = call(request(daytime=daytime), now=DAY if daytime else NOW)
    assert ("cache_control" in fake.calls[0]["system"][-1]) is marked
    assert result.cache_marked is marked  # 초안 바퀴는 표시를 실은 요청의 캐시 읽기 0 만 센다


@pytest.mark.parametrize("ttl", ["1h", "5m"])
def test_changing_text_comes_after_the_cache_marker(actor, ttl):
    if ttl != "1h":
        configure(actor, cache_ttl=ttl)
    first = call(request(daytime=True, chat_id="chat-alpha-1"), now=DAY)[1].calls[0]
    later = DAY.replace(hour=16, minute=7)
    second = call(request(daytime=True, chat_id="chat-beta-2", messages=[("user", "다른 합성 문의")]), now=later)[1].calls[0]
    cached = [json.dumps(sent["system"], ensure_ascii=False) for sent in (first, second)]
    assert cached[0] == cached[1]  # 표시까지 앞부분은 바이트까지 같다(지시문 · 지식 · 교훈만)
    assert first["system"][-1]["cache_control"]["ttl"] == ttl and "tools" not in first  # 도구 없음 — system 다음 messages
    for volatile in ("chat-alpha-1", "2026-10-28", "14:00", "16:07"):
        assert volatile not in cached[0]
    assert "chat-alpha-1" in first["messages"][0]["content"] and "16:07" in second["messages"][0]["content"]
    assert "cache_control" not in json.dumps(first["messages"])  # 바뀌는 글(뒷부분)에는 표시가 없다


@pytest.mark.parametrize("model,one_hour,five_minutes", [
    (bp.MODEL, "0.008", "0.005"), (bp.MODEL_SONNET, "0.004", "0.0025"), (bp.MODEL_HAIKU, "0.0002", "0.000125"),
])
def test_one_hour_and_five_minute_cache_writes_are_priced_apart(model, one_hour, five_minutes):
    assert bp.Tokens(write_1h=1000).cost(model) == Decimal(one_hour)  # 1시간 쓰기 = 입력 × 2
    assert bp.Tokens(write_5m=1000).cost(model) == Decimal(five_minutes)  # 5분 쓰기 = 입력 × 1.25
    assert bp.PRICES[model].cache_write_1h == max(bp.PRICES[model].input, bp.PRICES[model].cache_write_5m,
                                                  bp.PRICES[model].cache_write_1h)  # 최악값 예약의 입력 쪽 단가


def test_the_lower_of_env_and_panel_cap_stops_the_call(actor, monkeypatch):
    put_spend({"date": "2026-10-28", "usd": "0.01", "calls": 1})
    configure(actor, daily_cap_usd_panel="0.01")
    fake = FakeClient()
    with pytest.raises(brain.SpendCapReached):
        brain.draft_reply(request(), client=fake, session=db_session, now=NOW)
    assert fake.calls == []
    configure(actor, daily_cap_usd_panel=None)
    assert call()[0].intent == "hours"  # 음성 대조: 화면 값을 비우면 env 5 로 부른다
    configure(actor, daily_cap_usd_panel="3")
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "0.01")  # 저장한 뒤 env 를 낮춘다
    with pytest.raises(brain.SpendCapReached):  # env 가 천장 — 화면 값이 더 높아도 env 로 자른다
        brain.draft_reply(request(), client=FakeClient(), session=db_session, now=NOW)


def test_haiku_answers_are_priced_on_the_haiku_card(actor):
    configure(actor, draft_model=bp.MODEL_HAIKU)
    result, fake = call(None, message(answer(), model=bp.MODEL_HAIKU, use=usage(1000, 500)))
    assert fake.calls[0]["model"] == "claude-haiku-5-5" and result.model == "claude-haiku-5-5"
    assert result.cost_usd == Decimal("0.00035")  # 1000 × $0.10 + 500 × $0.50


# ── 값표 · 예약 ──────────────────────────────────────────────────────────
def test_official_prices_and_the_haiku_long_prompt_card():
    assert bp.PRICES[bp.MODEL_SONNET] == bp.Price(*map(Decimal, ("2", "10", "0.10", "2.50", "4")))
    assert bp.PRICES[bp.MODEL_HAIKU] == bp.Price(*map(Decimal, ("0.10", "0.50", "0.01", "0.125", "0.20")))
    assert bp.PRICES[bp.MODEL] == bp.Price(*map(Decimal, ("4", "20", "0.20", "5", "8")))
    at_limit = bp.Tokens(input=50_000, cache_read=50_000)  # 딱 10만 — 보통 값
    assert at_limit.cost(bp.MODEL_HAIKU) == Decimal("0.0055")  # 50000 × $0.10 + 50000 × $0.01
    over = bp.Tokens(input=90_000, output=1000, cache_read=10_000, write_1h=1)  # 캐시 읽기 · 쓰기도 길이에 든다
    assert over.cost(bp.MODEL_HAIKU) == Decimal("0.048001")  # 90000×0.5 + 1000×2.5 + 10000×0.05 + 1×1
    assert over.cost(bp.MODEL_SONNET) == Decimal("0.191004")  # 긴 값은 Haiku 만 — Sonnet 은 그대로


@pytest.mark.parametrize("model,fallbacks,input_price,output_price", [
    (bp.MODEL, None, "8", "20"),  # Opus 5.5 단가만
    (bp.MODEL, "default", "10", "25"),  # 대체를 보내면 대체 대상(Opus 5 · 4.8)과 견주어 큰 쪽 · 입력 · 출력 두 번
    (bp.MODEL_SONNET, None, "4", "10"),
    (bp.MODEL_SONNET, "default", "4", "10"),  # Sonnet 5 와 견줘도 같다
    (bp.MODEL_HAIKU, None, "1", "2.50"),  # Haiku 는 대체를 보내지 않으니 Haiku 단가만(긴 프롬프트 값까지)
    ("claude-unknown-9", None, "10", "25"),  # 표에 없는 모델은 가장 비싼 값
    ("claude-sonnet-5", "default", "10", "25"),  # 대체 대상을 모르는 모델에 대체를 보내면 가장 비싼 값
])
def test_the_reservation_uses_the_chosen_model_price(model, fallbacks, input_price, output_price):
    params = {"model": model, "max_tokens": 1000, "messages": [{"role": "user", "content": "가" * 100}]}
    if fallbacks:
        params["fallbacks"] = fallbacks
    tokens = len(json.dumps(params, ensure_ascii=False)) + bp.RESERVE_OVERHEAD_TOKENS
    attempts = 2 if fallbacks else 1  # 대체를 보내면 시도마다 따로 청구된다 — 입력 · 출력 모두(검수 R9)
    expected = (Decimal(tokens) * Decimal(input_price) + Decimal(1000) * Decimal(output_price)) * attempts / 10**6
    assert bp.worst_case_cost(params) == expected


def test_a_haiku_call_reserves_haiku_money(actor):
    configure(actor, draft_model=bp.MODEL_HAIKU)
    haiku = ReserveSnapshot(message(model=bp.MODEL_HAIKU))
    brain.draft_reply(request(), client=haiku, session=db_session, now=NOW)
    assert haiku.reserved_at_send == [bp.worst_case_cost(haiku.calls[0])]
    configure(actor, draft_model=bp.MODEL)
    opus = ReserveSnapshot()
    brain.draft_reply(request(), client=opus, session=db_session, now=NOW)
    assert haiku.reserved_at_send[0] * 5 < opus.reserved_at_send[0]  # 음성 대조: Opus(대체 켬)는 훨씬 크게 예약한다


# ── 준비 확인: 초안 한 번 부를 만큼 남았나 ───────────────────────────────
def test_check_ready_stops_when_one_draft_would_not_fit(actor, monkeypatch):
    monkeypatch.setenv(brain.KEY_ENV, "synthetic-placeholder")
    put_spend({"date": "2026-10-28", "usd": "4.8", "calls": 9})  # 5 - 4.8 = 0.2 < Opus 16천 토큰 한 번(대체 켬 약 0.84)
    with pytest.raises(brain.SpendCapReached) as excinfo:
        brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW)
    assert excinfo.value.code == "daily_cap_reached"
    configure(actor, draft_model=bp.MODEL_HAIKU)  # Haiku 한 번(약 0.04)은 남은 돈에 들어간다
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW) == Decimal("5")
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "4.8")  # 다 썼다 — 모델과 상관없이 멈춘다
    with pytest.raises(brain.SpendCapReached):
        brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW)


def test_the_floor_counts_both_attempts_while_the_fallback_is_on(actor, monkeypatch):
    monkeypatch.setenv(brain.KEY_ENV, "synthetic-placeholder")
    smallest = {"model": bp.MODEL, "max_tokens": 16000}  # 준비 확인의 가장 작은 요청(처음 값)
    both = bp.worst_case_cost({**smallest, "fallbacks": "default"})
    assert both == Decimal("0.84146")  # (2073 × $10 + 16000 × $25) × 두 번 — 대체 켬(_floor_reserve 와 같은 칸)
    assert bp.worst_case_cost(smallest) == Decimal("0.336392")  # 대체 끔: 2049 × $8 + 16000 × $20 — 한 번
    put_spend({"date": "2026-10-28", "usd": "4.5", "calls": 9})  # 남은 0.5 — 한 번 몫(0.42)은 들지만
    with pytest.raises(brain.SpendCapReached):  # 대체 켬이면 입력 · 출력 두 번(0.84)이라 안 든다(검수 R9)
        brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW)
    configure(actor, fallback_enabled=False)  # 음성 대조: 대체 끔이면 Opus 5.5 단가로 한 번(0.336392)
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW) == Decimal("5")
