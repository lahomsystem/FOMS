"""T12 요약 크로스 스트립 — 커널 계약 테스트(SETTLE-CHANNEL-01 v1.1 §2.2·§5.1).

이 파일이 red 로 잡아야 하는 것:

1. **스키마 드리프트** — ``view=strip`` 응답의 최상위 키와 ``strip`` 키 집합은 정확 일치다.
   ``channel.js`` 의 ``mountStrip`` 이 키 하나에 화면 조각 하나씩을 걸고 있다.
2. **스트립과 탭이 갈라지는 것(핵심)** — 같은 구간을 스트립과 채널 탭이 서로 다른 숫자로
   말하면, 요약 화면과 채널 화면 중 어느 쪽이 맞는지 사람이 알 수 없다.
   :func:`build_channel_strip` 은 :func:`build_channel_dashboard` 와 **같은 헬퍼**를
   통과하므로 이 동일성은 구성상 보장이어야 한다 — 여기서 못 박는다.
3. **스트립이 탭만큼 비싸지는 것** — 스트립은 요약 탭 첫 화면에서 무조건 1회 뜬다. 전기
   구간·원장·수수료·부가세까지 끌어오면 요약 탭 TTFB 가 통째로 느려진다.
4. **결측을 0 으로 그리기** — 한 번도 동기화하지 않았으면 ``sync.never`` 가 True 여야 한다
   (계약 D-10). 0원과 미동기화는 다른 사실이다.

**W2-A 핸드셰이크(중요)**: 아래 "HTTP 라우트" 절은 W1-A 의 소유가 아닌
``foms/api/cs/settlement_channel.py`` 를 대상으로 한다(파일 소유권 표 §8.2). 그래서
그 모듈에 ``STRIP_VIEW = "strip"`` 이 등장하기 전까지 **자동 skip** 된다 —
W2-A 가 라우트를 올리는 순간 이 절이 **스스로 켜진다**(테스트를 다시 손댈 필요 없음).
커널 절은 지금부터 항상 돈다.

테스트 데이터 규율: 시드 헬퍼는 ``tests/domains/test_settlement_channel_api.py`` 의 것을
그대로 쓴다(복제 금지 — 두 파일이 각자 시드를 만들면 한쪽만 갱신된다).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Callable

import pytest
from sqlalchemy import event

import foms.api.cs.settlement_channel as api_module
from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from foms.services.settlement_channel import (
    STRIP_TAB_KEY,
    build_channel_dashboard,
    build_channel_strip,
)

# 권한 매트릭스·시드 SSOT 재사용(복제 금지).
from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_settlement_channel_api import (
    _ALLOWED_ACTORS,
    _DENIED_ACTORS,
    _case,
    _daily,
    _seed_basic,
)

API_URL = "/api/settlement/channel"

#: 계약 §2.2 의 ``data`` 최상위 키. 탭(full) 응답과 달리 kpi·daily·원장이 **없다**.
_STRIP_DATA_KEYS = {"channel", "basis", "basis_label", "range", "sync", "strip"}

#: ``strip`` 블록 키. 이 5개가 스트립 한 줄이 말하는 전부다.
_STRIP_KEYS = {"settled_amount", "expected_amount", "exception_count",
               "unmatched_count", "tab_key"}

#: 라우트가 아직 없으면 HTTP 절은 통째로 skip 한다(위 핸드셰이크 참조).
_ROUTE_PENDING = pytest.mark.skipif(
    not hasattr(api_module, "STRIP_VIEW"),
    reason="W2-A route pending — API 모듈에 STRIP_VIEW 가 아직 없다",
)


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _default_range(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """서버 기본 구간(오늘-30 ~ 오늘+14)과 같은 폭."""
    return today - datetime.timedelta(days=30), today + datetime.timedelta(days=14)


def _seed_exceptional(today: datetime.date) -> datetime.date:
    """예외 큐가 비지 않도록 보류·음수 정산·미매칭을 한 번에 심는다.

    Args:
        today: KST 오늘.

    Returns:
        시드한 정산 예정일.
    """
    day = _seed_basic(today)
    _daily(day, pay_holdback_amount=Decimal("50000"))
    _daily(day, settle_amount=Decimal("-250000"), pay_settle_amount=Decimal("-275000"),
           commission_settle_amount=Decimal("25000"),
           normal_settle_amount=Decimal("-250000"))
    _case(day, product_order_id="2026090100009", match_status="UNMATCHED")
    db_session.commit()
    return day


def _strip(today: datetime.date) -> dict:
    """기본 구간으로 스트립 한 벌."""
    date_from, date_to = _default_range(today)
    return build_channel_strip(db_session, date_from=date_from, date_to=date_to,
                               today=today)


def _full(today: datetime.date) -> dict:
    """같은 구간·같은 세션으로 채널 탭 한 벌(동일성 비교의 대조군)."""
    date_from, date_to = _default_range(today)
    return build_channel_dashboard(db_session, date_from=date_from, date_to=date_to,
                                   today=today)


def _count_queries(fn: Callable[[], Any]) -> tuple[Any, int]:
    """``fn()`` 이 도는 동안 실제로 나간 SQL 문 수를 센다.

    Args:
        fn: 인자 없는 호출 가능 객체.

    Returns:
        ``(반환값, 질의 수)``.
    """
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany) -> None:
        counter["n"] += 1

    db_session.expire_all()  # 식별 맵 적중으로 질의가 사라지지 않게 출발선을 맞춘다.
    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def _data(resp: Any) -> dict:
    """200 을 확인하고 ``data`` 를 꺼낸다."""
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    return body["data"]


# --------------------------------------------------------------------------
# 1. 커널 스키마
# --------------------------------------------------------------------------
def test_strip_keys_are_exactly_the_contract_set(app):
    """최상위·``strip`` 키 집합 정확 일치 + 축은 언제나 정산 예정일."""
    today = get_today_kst()
    _seed_basic(today)
    data = _strip(today)

    assert set(data) == _STRIP_DATA_KEYS
    assert set(data["strip"]) == _STRIP_KEYS
    assert set(data["range"]) == {"from", "to"}
    assert data["channel"] == "NAVER"
    assert data["basis"] == "expect"
    assert data["basis_label"]


def test_strip_carries_the_tab_key_from_the_server(app):
    """탭 키를 서버가 내려 준다(프론트가 ``"channel"`` 을 다시 적지 않게)."""
    today = get_today_kst()
    _seed_basic(today)

    assert _strip(today)["strip"]["tab_key"] == STRIP_TAB_KEY == "channel"


def test_strip_range_echoes_the_requested_window(app):
    """응답의 구간이 요청 구간 그대로다(서버가 조용히 넓히거나 좁히지 않는다)."""
    today = get_today_kst()
    date_from, date_to = _default_range(today)

    data = build_channel_strip(db_session, date_from=date_from, date_to=date_to,
                               today=today)

    assert data["range"] == {"from": date_from.isoformat(), "to": date_to.isoformat()}


def test_strip_amounts_are_numbers_not_strings(app):
    """금액·건수는 JSON 숫자다(문자열이면 프론트 축약 헬퍼가 조용히 깨진다)."""
    today = get_today_kst()
    _seed_exceptional(today)
    strip = _strip(today)["strip"]

    for key in ("settled_amount", "expected_amount"):
        assert isinstance(strip[key], (int, float)), (key, strip[key])
    for key in ("exception_count", "unmatched_count"):
        assert isinstance(strip[key], int), (key, strip[key])


# --------------------------------------------------------------------------
# 2. 동일성 계약 — 스트립과 탭이 갈라지면 red (§5.1-③)
# --------------------------------------------------------------------------
def test_strip_numbers_equal_the_tab_numbers(app):
    """같은 구간·같은 세션이면 스트립 스칼라가 탭과 **완전히 같다**."""
    today = get_today_kst()
    _seed_basic(today)

    strip = _strip(today)["strip"]
    full = _full(today)

    assert strip["settled_amount"] == full["kpi"]["settled_amount"]
    assert strip["expected_amount"] == full["kpi"]["expected_amount"]
    assert strip["unmatched_count"] == full["kpi"]["unmatched_count"]
    assert strip["exception_count"] == len(full["exceptions"])


def test_strip_numbers_equal_the_tab_numbers_with_exceptions(app):
    """보류·음수 정산·미매칭이 섞인 구간에서도 동일하다(예외가 0이면 무의미한 계약이다)."""
    today = get_today_kst()
    _seed_exceptional(today)

    strip = _strip(today)["strip"]
    full = _full(today)

    assert strip["exception_count"] == len(full["exceptions"]) > 0
    assert strip["unmatched_count"] == full["kpi"]["unmatched_count"] == 1
    assert strip["settled_amount"] == full["kpi"]["settled_amount"]
    assert strip["expected_amount"] == full["kpi"]["expected_amount"]


def test_strip_keeps_negative_settlement_signs(app):
    """음수 정산(취소·환급)을 절대값으로 바꾸지 않는다 — 탭과 같은 실제 합이다(계약 D-1)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _daily(day)
    _daily(day, settle_amount=Decimal("-250000"), pay_settle_amount=Decimal("-275000"),
           commission_settle_amount=Decimal("25000"),
           normal_settle_amount=Decimal("-250000"))
    db_session.commit()

    strip = _strip(today)["strip"]

    assert strip["expected_amount"] == 750000  # 절대값 합(1,250,000)이면 red
    assert strip["expected_amount"] == _full(today)["kpi"]["expected_amount"]


def test_strip_sync_block_is_the_tab_sync_block(app):
    """``sync`` 는 탭과 같은 dict 다 — 스트립이 "오래됨"을 다르게 판정하지 않는다."""
    today = get_today_kst()
    _seed_basic(today)

    assert _strip(today)["sync"] == _full(today)["sync"]


def test_strip_on_empty_data_says_zero_and_never_synced(app):
    """행이 하나도 없으면 0 을 내되 ``sync.never`` 로 "아직 안 맞춰 봤다"를 함께 말한다."""
    today = get_today_kst()
    data = _strip(today)

    assert data["strip"] == {"settled_amount": 0, "expected_amount": 0,
                             "exception_count": 0, "unmatched_count": 0,
                             "tab_key": STRIP_TAB_KEY}
    assert data["sync"]["never"] is True


# --------------------------------------------------------------------------
# 3. 비용 — 스트립은 탭보다 싸다 (§5.1-⑤)
# --------------------------------------------------------------------------
def test_strip_issues_fewer_queries_than_the_full_tab(app):
    """스트립은 전기 구간·원장·수수료·부가세를 조회하지 않으므로 질의가 더 적다."""
    today = get_today_kst()
    _seed_exceptional(today)

    _, strip_queries = _count_queries(lambda: _strip(today))
    _, full_queries = _count_queries(lambda: _full(today))

    assert strip_queries < full_queries, (strip_queries, full_queries)
    # 계약 §2.2 의 목표: 일별 1 + 건별 group-by 1 + 미매칭 1 + 최근 run 1 + 워터마크 1.
    assert strip_queries <= 5, strip_queries


# --------------------------------------------------------------------------
# 4. 파라미터 검증
# --------------------------------------------------------------------------
def test_strip_rejects_reversed_range(app):
    """시작일이 종료일보다 뒤면 ValueError(조용히 뒤집어 주지 않는다)."""
    today = get_today_kst()
    with pytest.raises(ValueError):
        build_channel_strip(db_session, date_from=today,
                            date_to=today - datetime.timedelta(days=1), today=today)


def test_strip_rejects_oversized_range(app):
    """구간 폭 상한(400일)은 탭과 같은 검사·같은 한글 사유를 쓴다."""
    today = get_today_kst()
    with pytest.raises(ValueError) as excinfo:
        build_channel_strip(db_session,
                            date_from=today - datetime.timedelta(days=500),
                            date_to=today, today=today)
    assert "400" in str(excinfo.value)


# --------------------------------------------------------------------------
# 5. HTTP 라우트 — W2-A 가 ``STRIP_VIEW`` 를 올리면 자동으로 켜진다
# --------------------------------------------------------------------------
@_ROUTE_PENDING
def test_view_strip_response_keys_exact(client, app):
    """``?view=strip`` 응답 ``data`` 가 커널 반환값 그대로 실린다."""
    today = get_today_kst()
    _seed_basic(today)
    _login(client, _make_user(role="ADMIN"))

    data = _data(client.get(API_URL + "?view=strip"))

    assert set(data) == _STRIP_DATA_KEYS
    assert set(data["strip"]) == _STRIP_KEYS
    assert data["strip"]["tab_key"] == STRIP_TAB_KEY


@_ROUTE_PENDING
def test_view_strip_matches_the_full_view_over_http(client, app):
    """같은 파라미터로 부른 ``view=strip`` 과 기본(full)이 같은 숫자를 말한다."""
    today = get_today_kst()
    _seed_exceptional(today)
    _login(client, _make_user(role="ADMIN"))

    strip = _data(client.get(API_URL + "?view=strip"))["strip"]
    full = _data(client.get(API_URL))

    assert strip["settled_amount"] == full["kpi"]["settled_amount"]
    assert strip["expected_amount"] == full["kpi"]["expected_amount"]
    assert strip["unmatched_count"] == full["kpi"]["unmatched_count"]
    assert strip["exception_count"] == len(full["exceptions"])


@_ROUTE_PENDING
def test_default_view_is_still_the_full_tab(client, app):
    """``view`` 를 안 주면 예전과 똑같은 탭 한 벌이다(기존 화면 무회귀)."""
    _login(client, _make_user(role="ADMIN"))
    data = _data(client.get(API_URL))

    assert "kpi" in data and "ledger" in data and "strip" not in data


@_ROUTE_PENDING
@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
def test_strip_allowed_actors_get_200(client, app, role, team):
    """ADMIN·회계팀 MANAGER/STAFF 는 스트립도 200(탭과 같은 게이트)."""
    _login(client, _make_user(role=role, team=team))
    assert client.get(API_URL + "?view=strip").status_code == 200, (role, team)


@_ROUTE_PENDING
@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_strip_denied_actors_get_403_json(client, app, role, team):
    """그 밖의 actor 는 403 JSON — **MANAGER+CS 포함**(엔진이라면 통과한다)."""
    _login(client, _make_user(role=role, team=team))
    resp = client.get(API_URL + "?view=strip")

    assert resp.status_code == 403, (role, team, resp.status_code)
    assert "Location" not in resp.headers, "API 거부는 302 가 아니라 403 JSON"
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None and body["error"]


@_ROUTE_PENDING
def test_strip_anonymous_is_not_served(client, app):
    """미인증은 로그인 리다이렉트(또는 401) — 절대 200 이 아니다."""
    assert client.get(API_URL + "?view=strip").status_code in (301, 302, 401)


@_ROUTE_PENDING
@pytest.mark.parametrize("view", ["bogus", "summary", "STRIPE"])
def test_unknown_view_is_400_with_a_korean_reason(client, app, view):
    """허용 집합 밖 ``view`` 는 400 + 사람이 읽는 사유(조용한 full 폴백 금지)."""
    _login(client, _make_user(role="ADMIN"))
    resp = client.get(API_URL + "?view=" + view)

    assert resp.status_code == 400, (view, resp.get_data(as_text=True))
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None
    assert "view" in body["error"]
