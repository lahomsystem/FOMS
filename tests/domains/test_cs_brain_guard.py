"""두뇌 막는 장치(검수 R7) — 보내기 전 최악값 예약 · 바로잡기 · 시간 초과는 다시 보내지 않음(R7-3), 선점 전 준비 확인 ·
401 · 403 은 준비 안 됨(R7-4), 본문을 쓰는 디버그 로거 여섯 + 그 아래 로거(R7-10).

가짜 클라이언트만(네트워크 · 키 없음). 재료 · 가짜는 ``test_cs_brain`` 과 같다. 손으로 꾸민 합성 글만.
"""

from __future__ import annotations

import contextlib
import json
import logging
from decimal import Decimal

import anthropic
import httpx2
import pytest

from db import db_session
from foms.services.cs_agent import brain
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent.knowledge_doc import ApprovedKnowledge
from tests.domains.test_cs_brain import KNOWLEDGE, NOW, FakeClient, api_error, message, put_spend, request, spend

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
TODAY = "2026-10-28"


@pytest.fixture(autouse=True)
def _brain_env(monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")
    monkeypatch.setattr(brain, "_sleep", lambda _seconds: None)


def transport_error(cls, cause):
    """SDK 가 전송 오류를 감싸 올리는 꼴 그대로(``raise … from err``)."""
    exc = cls(request=_REQUEST)
    exc.__cause__ = cause
    return exc


class SnapshotClient(FakeClient):
    """보낼 때마다 돈 줄의 커밋된 예약을 찍는다 — 되돌려도 남아야 보내기 전에 커밋된 것이다."""

    def __init__(self, *outcomes):
        super().__init__(*outcomes)
        self.reserved_at_send = []
        send = self.beta.messages.create

        def create(**params):
            db_session.rollback()
            self.reserved_at_send.append(Decimal(spend()["reserved"]))
            return send(**params)

        self.beta.messages.create = create


def call(client, **overrides):
    return brain.draft_reply(request(**overrides), client=client, session=db_session, now=NOW)


@contextlib.contextmanager
def debug_on(name):
    log = logging.getLogger(name)
    old = log.level
    log.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        log.setLevel(old)


# ── R7-3 예약 · 바로잡기 · 다시 보내기 ──────────────────────────────────


@pytest.mark.parametrize("realtime", [False, True])
def test_a_timeout_keeps_its_worst_case_reservation_and_is_never_resent(app, realtime):
    client = SnapshotClient(transport_error(anthropic.APITimeoutError, httpx2.ReadTimeout("합성")))
    with pytest.raises(brain.BrainUnavailable) as excinfo:
        call(client, realtime=realtime)
    (reserved,) = client.reserved_at_send  # 한 번만 보냈고, 보내기 전에 최악값이 커밋돼 있었다
    assert excinfo.value.code == "timeout" and reserved > Decimal("0.40")  # 출력 상한 16000 × $25/M 만으로도 0.40
    assert (Decimal(spend()["usd"]), Decimal(spend()["reserved"]), spend()["calls"]) == (reserved, 0, 1)
    assert brain.spent_today(db_session, now=NOW) == reserved  # 서버가 생성했을 수 있으니 0 으로 세지 않는다


def test_an_answer_replaces_the_reservation_with_the_real_cost(app):
    client = SnapshotClient(message())
    assert call(client).cost_usd == Decimal("0.014")
    assert client.reserved_at_send[0] > Decimal("0.014")  # 부르는 동안은 최악값
    assert (Decimal(spend()["usd"]), Decimal(spend()["reserved"])) == (Decimal("0.014"), 0)


@pytest.mark.parametrize("error", [
    lambda: api_error(anthropic.InternalServerError, 500, "api_error", "합성"),
    lambda: api_error(anthropic.RateLimitError, 429, "rate_limit_error", "합성"),
    lambda: transport_error(anthropic.APITimeoutError, httpx2.ConnectTimeout("합성")),  # 보내기 전 시간 초과
], ids=["500", "429", "connect-timeout"])
def test_an_error_answer_or_an_unsent_request_releases_the_reservation(app, error):
    client = SnapshotClient(error())
    with pytest.raises(brain.BrainUnavailable):
        call(client)
    assert len(client.calls) == 1 and Decimal(spend()["usd"]) == Decimal(spend()["reserved"]) == 0


def test_only_a_connection_that_never_sent_a_byte_is_retried_on_the_night_path(app):
    refused = lambda: transport_error(anthropic.APIConnectionError, httpx2.ConnectError("합성 연결 거절"))  # noqa: E731
    client = SnapshotClient(refused(), message())
    assert call(client).intent == "hours" and len(client.calls) == 2
    assert client.reserved_at_send[0] == client.reserved_at_send[1]  # 첫 예약은 풀고(0원 확실) 다시 예약했다
    assert (Decimal(spend()["usd"]), Decimal(spend()["reserved"]), spend()["calls"]) == (Decimal("0.014"), 0, 2)
    realtime = SnapshotClient(refused(), message())
    with pytest.raises(brain.BrainUnavailable):  # 실시간 길은 다시 하지 않는다
        call(realtime, realtime=True)
    assert len(realtime.calls) == 1
    cut = SnapshotClient(transport_error(anthropic.APIConnectionError, httpx2.ReadError("합성 끊김")), message())
    with pytest.raises(brain.BrainUnavailable):  # 보낸 뒤 끊김 — 생성됐을 수 있어 다시 하지 않고 예약을 돈으로
        call(cut)
    assert len(cut.calls) == 1 and Decimal(spend()["reserved"]) == 0
    assert Decimal(spend()["usd"]) == Decimal("0.014") + cut.reserved_at_send[0]


def test_a_reservation_that_would_pass_the_cap_is_never_sent(app, monkeypatch):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "0.6")
    put_spend({"date": TODAY, "usd": "0.05", "reserved": "0.20", "calls": 1})  # 다른 바퀴가 부르는 중
    assert brain.check_budget(db_session, cap=Decimal("0.6"), now=NOW) == Decimal("0.25")  # 예약 없이 보면 남는다
    client = FakeClient()
    with pytest.raises(brain.SpendCapReached) as excinfo:  # 0.25 + 최악값(출력만 0.40) > 0.6 — 보내지 않는다
        call(client)
    assert excinfo.value.code == "daily_cap_reached" and client.calls == []
    assert spend() == {"date": TODAY, "usd": "0.05", "reserved": "0.20", "calls": 1}  # 되돌렸다 — 예약도 안 더함


def test_check_budget_counts_reservations_and_a_broken_reservation_refuses(app):
    put_spend({"date": TODAY, "usd": "0.2", "reserved": "4.8", "calls": 3})
    with pytest.raises(brain.SpendCapReached):
        brain.check_budget(db_session, cap=Decimal("5"), now=NOW)
    assert brain.spent_today(db_session, now=NOW) == Decimal("5.0")
    db_session.get(brain.SystemSetting, brain.SPEND_KEY).setting_value = {"date": TODAY, "usd": "0", "reserved": "-1"}
    db_session.commit()
    with pytest.raises(brain.BrainNotReady) as excinfo:
        call(FakeClient())
    assert excinfo.value.code == "spend_record_invalid"


def test_worst_case_is_max_tokens_at_the_top_output_price_plus_the_input_estimate():
    params = {"model": brain.MODEL, "max_tokens": 16000, "messages": [{"role": "user", "content": "가" * 3000}]}
    tokens = len(json.dumps(params, ensure_ascii=False)) + bp.RESERVE_OVERHEAD_TOKENS
    expected = (Decimal(tokens) * Decimal("10") + Decimal(16000) * Decimal("25")) / 10**6
    assert bp.worst_case_cost(params) == expected  # 입력은 가장 비싼 입력 쪽 값(1시간 캐시 쓰기 $10), 출력은 $25


# ── R7-4 준비 확인 · 401 · 403 ───────────────────────────────────────────


def test_check_ready_runs_before_any_row_and_returns_the_cap(app, monkeypatch):
    monkeypatch.setenv(brain.KEY_ENV, "synthetic-placeholder")
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW) == Decimal("5")
    cases = [({"brand": "HAUD"}, "brand_not_enabled"), ({"knowledge": ApprovedKnowledge("LAHOM", 0)}, "no_knowledge"),
             ({"knowledge": ApprovedKnowledge("HAUD", 1, KNOWLEDGE.items)}, "brand_mismatch")]
    for overrides, code in cases:
        args = {"brand": "LAHOM", "knowledge": KNOWLEDGE, **overrides}
        with pytest.raises(brain.BrainNotReady) as excinfo:
            brain.check_ready(args["brand"], args["knowledge"], session=db_session, now=NOW)
        assert excinfo.value.code == code
    monkeypatch.delenv(brain.KEY_ENV)
    with pytest.raises(brain.BrainNotReady) as excinfo:
        brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW)
    assert excinfo.value.code == "no_api_key"
    assert brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW, client=object()) == Decimal("5")
    monkeypatch.delenv(brain.DAILY_CAP_ENV)
    with pytest.raises(brain.BrainNotReady) as excinfo:
        brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW, client=object())
    assert excinfo.value.code == "daily_cap_missing" and spend() is None  # 확인만 — 돈 줄을 만들지 않는다


@pytest.mark.parametrize("cls,status", [(anthropic.AuthenticationError, 401), (anthropic.PermissionDeniedError, 403)])
def test_a_rejected_key_is_not_ready_and_costs_nothing(app, cls, status):
    client = FakeClient(api_error(cls, status, "authentication_error", "합성 거절"))
    with pytest.raises(brain.BrainNotReady) as excinfo:
        call(client)
    assert (excinfo.value.code, excinfo.value.status, len(client.calls)) == ("api_auth", status, 1)
    assert Decimal(spend()["usd"]) == Decimal(spend()["reserved"]) == 0


# ── R7-10 본문을 쓰는 디버그 로거 ────────────────────────────────────────


@pytest.mark.parametrize("name", [*brain.SDK_BODY_LOGGERS, "httpcore2.connection"])
def test_any_body_logging_logger_at_debug_blocks_the_call_and_the_ready_check(app, monkeypatch, name):
    assert set(brain.SDK_BODY_LOGGERS) == {"anthropic", "anthropic._base_client", "httpx2", "httpcore2", "httpx",
                                           "httpcore"}
    monkeypatch.setenv(brain.KEY_ENV, "synthetic-placeholder")
    client = FakeClient()
    with debug_on(name):  # 위 로거는 그대로 두고 이 로거만 DEBUG
        with pytest.raises(brain.BrainNotReady) as excinfo:
            call(client)
        with pytest.raises(brain.BrainNotReady) as ready:
            brain.check_ready("LAHOM", KNOWLEDGE, session=db_session, now=NOW)
    assert excinfo.value.code == ready.value.code == "sdk_debug_logging" and client.calls == []
    assert call(FakeClient()).intent == "hours"  # 음성 대조: 되돌리면 부른다
