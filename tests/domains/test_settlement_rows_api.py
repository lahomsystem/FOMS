"""SETTLE-TABS: 정산 실무 탭 **주문 행** 표면의 권한·노출 계약 테스트.

집계 API(`/api/settlement/aggregates`)는 주문 행을 절대 싣지 않고, 이 행 API
(`/api/settlement/rows`)는 고객 성명과 주문번호까지 낸다. **두 계약은 서로 다르고,
한쪽을 다른 쪽 근거로 완화하면 안 된다**(스펙 개정 A §13.1).

이 파일이 red 로 잡아야 하는 것:

1. **권한 매트릭스 이탈** — 행 표면은 집계와 **같은** 허용/거부 집합이어야 한다.
   행이 실린다는 이유로 게이트가 느슨해지거나(더 많은 actor 허용) 조여지면(정산
   담당이 막힘) red. actor 목록은 복제하지 않고 AUTH-FINANCE-01 SSOT 를 import 한다.
2. **PII 과다 노출** — 고객 성명·주문번호까지가 상한이다. 연락처·주소·현금영수증
   요청 자유텍스트 **원문**이 응답에 섞이면 red. 현금영수증은 파생 상태 코드만 낸다.
3. **캡의 조용한 발동** — 모집단을 자르고 그 다음 좁히면 특정 구간이 통째로 빈다
   (대시보드 캡 함정). 행 API 는 **필터를 먼저 적용하고 그 결과의 전량 개수**를
   보고해야 한다 — 페이지 크기는 표시 단위일 뿐 모집단 상한이 아니다.
4. **파생 파리티 이탈** — 잔금·과입금이 완료 대시보드/집계 커널과 다른 식을 쓰는 것.
5. **과입금 소실** — 잔금 클램프가 삼킨 금액을 안 내면 "돌려줄 돈이 있다"는 사실이
   화면에서 사라진다(CEO L-1). 목업에 칸이 없어도 응답에는 반드시 있어야 한다.

테스트 데이터 규율은 `test_settlement_dashboard_api` 와 같다 — 실제 Order 를 만들어 쓴다.
"""

from __future__ import annotations

import json

import pytest

from db import db_session
from foms.services.settlement_rows import PER_PAGE, list_settlement_rows

# --- 권한 매트릭스 SSOT 재사용(복제 금지) ---------------------------------------
from tests.domains.test_auth_finance import (  # noqa: E402
    _ALLOWED_ACTORS,
    _DENIED_ACTORS,
    _login,
    _make_user,
)
from tests.domains.test_settlement_aggregation import _money, _seed_order  # noqa: E402
from tests.domains.test_settlement_dashboard_api import (  # noqa: E402
    _CONSTRUCTION_PAGE_REDIRECT_ACTOR,
)

ROWS_URL = "/api/settlement/rows"

#: 행 응답이 반드시 가져야 하는 키 집합. **정확 일치** — 키가 늘면 노출면이 늘어난 것이라
#: 사람이 한 번 보고 넘겨야 한다(추가·누락 모두 red 가 의도다).
_ROW_KEYS = {
    "order_id",
    "customer_name",
    "status",
    "channel",
    "channel_label",
    "completion_date",
    "shipping_price",
    "deposit",
    "deposit_confirmed",
    "balance",
    "overpaid",
    "paid",
    "receivable",
    "elapsed_days",
    "aging",
    "aging_label",
    "cash_receipt_state",
    "settlement_issued",
}

#: 행에 절대 실리면 안 되는 필드 이름들.
_FORBIDDEN_ROW_KEYS = {
    "phone",
    "erp_phone_digits",
    "address",
    "site_address",
    "cash_receipt",          # 요청 자유텍스트 원문 — 파생 상태 코드만 낸다
    "raw_order_text",
    "structured_data",
    "notes",
}


def _get(client, **params):
    """행 API 를 호출하고 JSON body 를 돌려준다."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{ROWS_URL}?{query}" if query else ROWS_URL
    return client.get(url)


def _json_text(body) -> str:
    """파싱 후 재직렬화한 문자열 — Flask 의 ASCII 이스케이프를 통과해 한글을 찾는다."""
    return json.dumps(body, ensure_ascii=False)


# ==========================================================================
# 1. 권한 매트릭스 — 집계 API 와 같은 집합
# ==========================================================================
@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
def test_rows_api_allows_finance_actors(client, app, role, team):
    """정산 열람이 허용된 actor 는 행 API 도 200 이다."""
    _login(client, _make_user(role=role, team=team))

    response = _get(client)

    assert response.status_code == 200, f"{role}+{team} 이 행 API 에서 막혔다"
    assert response.get_json()["success"] is True


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_rows_api_denies_non_finance_actors(client, app, role, team):
    """정산 열람이 거부된 actor 는 행 API 도 403 이다.

    행이 실린다고 게이트가 느슨해지면 안 된다 — 집계와 **같은** policy_id 로 판정한다.
    CONSTRUCTION 팀도 API 표면에서는 403 이다(플랫폼 가드는 `/api/` 를 제외한다).
    """
    _login(client, _make_user(role=role, team=team))

    response = _get(client)

    assert response.status_code == 403, f"{role}+{team} 이 행 API 를 열었다"
    body = response.get_json()
    assert body["success"] is False and body["data"] is None


def test_rows_api_denies_construction_team_on_api_surface(client, app):
    """플랫폼 가드 예외 actor 도 API 에서는 302 가 아니라 403 이다."""
    role, team = _CONSTRUCTION_PAGE_REDIRECT_ACTOR
    _login(client, _make_user(role=role, team=team))

    response = _get(client)

    assert response.status_code == 403


# ==========================================================================
# 2. 노출 계약 — 성명·주문번호까지, 연락처·주소·원문은 금지
# ==========================================================================
def test_row_shape_is_exactly_the_agreed_field_set(client, app):
    """행 키 집합이 계약과 정확히 일치한다(추가·누락 모두 red)."""
    _seed_order(completion="2026-08-10", sd=_money(items_total=3_000_000, deposit=500_000))
    _login(client, _make_user(role="ADMIN"))

    rows = _get(client).get_json()["data"]["rows"]

    assert rows, "시드한 주문이 행 목록에 없다"
    assert set(rows[0]) == _ROW_KEYS, (
        f"행 키가 계약과 다르다: 추가={set(rows[0]) - _ROW_KEYS} 누락={_ROW_KEYS - set(rows[0])}"
    )


def test_rows_carry_customer_name_by_design(client, app):
    """고객 성명은 **의도적으로** 실린다 — 실무 탭의 존재 이유다(스펙 개정 A §13)."""
    marker = "정산실무고객"
    _seed_order(
        completion="2026-08-10",
        sd=_money(items_total=3_000_000, deposit=500_000),
        customer_name=marker,
    )
    _login(client, _make_user(role="ADMIN"))

    text = _json_text(_get(client).get_json())

    assert marker in text, "실무 탭 행에 고객명이 없다 — 화면이 성립하지 않는다"


def test_rows_never_carry_contact_or_address(client, app):
    """연락처·주소는 행 API 에 실리지 않는다 — 노출면 상한이다.

    시드 헬퍼가 넣는 전화("010-0000-0000")·주소("서울시 강남구")가 응답 어디에도
    나타나면 안 된다. 필드명 검사만 하면 값이 다른 키에 얹혀 새는 것을 놓친다.
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=3_000_000, deposit=500_000))
    _login(client, _make_user(role="ADMIN"))

    body = _get(client).get_json()
    text = _json_text(body)

    assert "010-0000-0000" not in text, "연락처가 행 응답에 실렸다"
    assert "서울시 강남구" not in text, "주소가 행 응답에 실렸다"
    leaked = _FORBIDDEN_ROW_KEYS & set(body["data"]["rows"][0])
    assert not leaked, f"금지 필드가 행에 있다: {sorted(leaked)}"


def test_cash_receipt_is_a_derived_state_not_the_raw_request_text(client, app):
    """현금영수증은 파생 상태 코드만 낸다 — 원문에는 전화·사업자번호가 들어간다."""
    secret = "010-9999-8888 사업자 123-45-67890"
    sd = _money(items_total=2_000_000, deposit=0)
    sd.setdefault("payment", {})["cash_receipt"] = secret
    _seed_order(completion="2026-08-12", sd=sd)
    _login(client, _make_user(role="ADMIN"))

    body = _get(client).get_json()

    assert secret not in _json_text(body), "현금영수증 요청 원문이 응답에 실렸다"
    states = {row["cash_receipt_state"] for row in body["data"]["rows"]}
    assert states <= {"issued", "requested", "none"}, states
    assert "requested" in states, "요청 텍스트가 있는데 파생 상태가 requested 가 아니다"


# ==========================================================================
# 3. 캡·페이지네이션 — 좁힌 뒤에 자른다
# ==========================================================================
def test_total_count_is_the_filtered_population_not_the_page(client, app):
    """`total_count` 는 필터 통과 전량이다 — 페이지 크기로 잘린 수가 아니다.

    캡으로 먼저 자르고 그 다음 좁히는 구조면 특정 구간이 통째로 빈다(대시보드 캡 함정).
    페이지 크기보다 많은 행을 넣고 전량 개수가 그대로 보고되는지 본다.
    """
    seeded = PER_PAGE + 7
    for index in range(seeded):
        _seed_order(
            completion="2026-08-10",
            sd=_money(items_total=1_000_000 + index, deposit=0),
            commit=False,
        )
    db_session().commit()
    _login(client, _make_user(role="ADMIN"))

    data = _get(client).get_json()["data"]

    assert data["total_count"] >= seeded, (
        f"필터 전량 개수가 시드보다 적다 — 캡이 조용히 발동했다: {data['total_count']} < {seeded}"
    )
    assert len(data["rows"]) == data["per_page"] == PER_PAGE
    assert data["total_pages"] >= 2


def test_page_two_returns_the_next_slice_without_overlap(client, app):
    """2페이지는 1페이지와 겹치지 않는 다음 구간이다."""
    for index in range(PER_PAGE + 5):
        _seed_order(
            completion="2026-08-10",
            sd=_money(items_total=1_000_000 + index, deposit=0),
            commit=False,
        )
    db_session().commit()
    _login(client, _make_user(role="ADMIN"))

    first = {row["order_id"] for row in _get(client, page=1).get_json()["data"]["rows"]}
    second = {row["order_id"] for row in _get(client, page=2).get_json()["data"]["rows"]}

    assert first and second
    assert not (first & second), "페이지가 겹친다"


def test_out_of_range_page_clamps_instead_of_erroring(client, app):
    """범위를 넘는 page 는 마지막 페이지로 접힌다(빈 화면 대신)."""
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    data = _get(client, page=9999).get_json()["data"]

    assert data["page"] == data["total_pages"]
    assert data["rows"], "마지막 페이지가 비었다"


# ==========================================================================
# 4. 필터
# ==========================================================================
def test_unknown_filter_value_is_a_400_not_a_silent_default(client, app):
    """허용 집합 밖 필터 값은 400 이다 — 조용히 '전체'로 떨어지면 잘못된 목록을 참으로 읽는다."""
    _login(client, _make_user(role="ADMIN"))

    response = _get(client, period="어제")

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False and body["error"]


def test_aging_filter_narrows_to_that_bucket_only(client, app):
    """aging 필터는 해당 버킷 행만 남긴다(막대 클릭 → 그리드 좁히기의 배후)."""
    _seed_order(completion="2026-08-30", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion="2026-01-05", sd=_money(items_total=2_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    data = _get(client, aging="D91_PLUS").get_json()["data"]

    assert data["rows"], "91일 이상 버킷이 비었다"
    assert {row["aging"] for row in data["rows"]} == {"D91_PLUS"}


def test_settlement_filter_splits_pending_and_issued(client, app):
    """정산상태 필터가 청구완료/대기를 가른다."""
    issued_sd = _money(items_total=1_000_000, deposit=0)
    issued_sd["settlement"] = {"deductions": [{"department": "SALES", "amount": 1000}]}
    _seed_order(completion="2026-08-10", sd=issued_sd)
    _seed_order(completion="2026-08-11", sd=_money(items_total=1_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    issued = _get(client, settlement="issued").get_json()["data"]["rows"]
    pending = _get(client, settlement="pending").get_json()["data"]["rows"]

    assert issued and all(row["settlement_issued"] for row in issued)
    assert pending and not any(row["settlement_issued"] for row in pending)


# ==========================================================================
# 5. 파생 파리티 — 잔금 클램프와 과입금
# ==========================================================================
def test_balance_uses_the_shared_clamp_and_overpaid_is_reported(client, app):
    """예약금이 출고가를 넘으면 잔금은 0 이고, 넘친 금액은 `overpaid` 로 따로 나온다.

    잔금만 보면 "0원"이라 정산이 끝난 것처럼 읽힌다 — 돌려줄 돈이 있다는 사실이
    화면에서 사라지는 것을 막는 계약이다(CEO L-1).
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=1_300_000))
    _login(client, _make_user(role="ADMIN"))

    row = next(
        r for r in _get(client).get_json()["data"]["rows"] if r["deposit"] == 1_300_000
    )

    assert row["balance"] == 0, "잔금이 음수로 샜다 — 공유 클램프를 안 쓴다"
    assert row["overpaid"] == 300_000, "과입금이 응답에서 사라졌다"


def test_shipping_price_none_stays_none_instead_of_zero(client, app):
    """품목합을 못 내면 출고가는 `None` 이다 — 0 으로 뭉개면 '금액 미상'과 '0원'이 섞인다."""
    _seed_order(completion="2026-08-10", sd={})
    _login(client, _make_user(role="ADMIN"))

    rows = _get(client).get_json()["data"]["rows"]

    assert any(row["shipping_price"] is None for row in rows)


# ==========================================================================
# 6. 정렬 — 경과일 오래된 순, 완료일 미상은 맨 뒤
# ==========================================================================
def test_rows_are_sorted_oldest_elapsed_first_with_unknown_last(client, app):
    """회수 우선순위 그대로 정렬된다 — 오래 밀린 건이 위, 완료일 미상은 맨 뒤."""
    _seed_order(completion="2026-08-30", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion="2026-02-01", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion=None, sd=_money(items_total=1_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    rows = _get(client).get_json()["data"]["rows"]
    known = [r["elapsed_days"] for r in rows if r["elapsed_days"] is not None]
    unknown_positions = [i for i, r in enumerate(rows) if r["elapsed_days"] is None]

    assert known == sorted(known, reverse=True), "경과일 내림차순이 아니다"
    if unknown_positions:
        assert min(unknown_positions) >= len(known), "완료일 미상이 맨 뒤가 아니다"


# ==========================================================================
# 7. 서비스 계층 단독 계약
# ==========================================================================
def test_service_rejects_unknown_filter_values(app):
    """서비스가 허용 집합 밖 값을 ValueError 로 거절한다(라우트가 400 으로 옮긴다)."""
    for kwargs in ({"period": "어제"}, {"settlement": "미정"}, {"aging": "D999"}):
        with pytest.raises(ValueError):
            list_settlement_rows(db_session(), **kwargs)


def test_channel_code_carries_a_human_label(app):
    """채널 코드는 코드대로 두고 라벨을 따로 낸다 — 화면에 "NAVER" 가 그대로 뜨지 않게."""
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=0))

    data = list_settlement_rows(db_session())

    assert data["rows"], "행이 없다"
    for row in data["rows"]:
        assert row["channel_label"], "채널 라벨이 비었다"
