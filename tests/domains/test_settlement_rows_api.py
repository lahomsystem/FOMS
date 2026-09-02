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
6. **채널 정산 누출**(v1.1 T13) — 이 표면의 게이트는 CS·영업까지 열려 있는데 네이버
   정산 상태는 회계 전용이다. `naver_settlement` 는 **키 자체가 권한**이라, 값이
   None 으로라도 실려 오면 red. 판정·부호·날짜 매트릭스 전량은
   `test_settlement_ops_channel_column.py` 가 맡고 여기서는 표면 계약만 본다.

테스트 데이터 규율은 `test_settlement_dashboard_api` 와 같다 — 실제 Order 를 만들어 쓴다.
"""

from __future__ import annotations

import datetime
import json

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.settlement_aggregation import AGING_BUCKETS
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
# 네이버 정산 칸 시드·쿼리 계수기는 전용 파일이 SSOT 다(복제하면 한쪽만 갱신된다).
from tests.domains.test_settlement_ops_channel_column import (  # noqa: E402
    _cell_by_order as _naver_cell,
    _count_queries,
    _seed_case,
    _seed_naver_order,
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

#: 채널 정산 열람 권한자(ADMIN·회계팀)에게만 **키가 하나 더 생긴다**(v1.1 T13 §6).
#: 두 갈래를 따로 못 박는 이유: 값 검사만 하면 "권한이 없는데 값이 None 으로 실려 온다"를
#: 통과시킨다. 키 부재와 값 None 은 노출면에서 전혀 다른 사실이다.
_NAVER_SETTLE_KEY = "naver_settlement"
_ROW_KEYS_WITH_CHANNEL = _ROW_KEYS | {_NAVER_SETTLE_KEY}

#: 채널 정산 게이트를 통과하는 actor(`can_view_channel_settlement` SSOT 와 같은 집합).
_CHANNEL_ALLOWED_ACTOR = ("ADMIN", None)
#: 행 API 는 열리지만 채널 정산은 못 보는 actor. **STAFF+CS 가 핵심**이다 —
#: `_ALLOWED_ACTORS` 에 들어 있어 200 을 받는데 회계 정보는 보면 안 된다.
_CHANNEL_DENIED_ACTOR = ("STAFF", "CS")

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
def test_row_shape_for_channel_settlement_actor_adds_exactly_one_key(client, app):
    """회계 권한자의 행 키 집합 = 기본 계약 ∪ {naver_settlement}(정확 일치).

    키가 **하나만** 늘어야 한다 — 네이버 정산을 붙이면서 금액·연락처가 슬쩍 함께 딸려
    오는 것을 여기서 잡는다.
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=3_000_000, deposit=500_000))
    role, team = _CHANNEL_ALLOWED_ACTOR
    _login(client, _make_user(role=role, team=team))

    rows = _get(client).get_json()["data"]["rows"]

    assert rows, "시드한 주문이 행 목록에 없다"
    assert set(rows[0]) == _ROW_KEYS_WITH_CHANNEL, (
        f"행 키가 계약과 다르다: 추가={set(rows[0]) - _ROW_KEYS_WITH_CHANNEL} "
        f"누락={_ROW_KEYS_WITH_CHANNEL - set(rows[0])}"
    )


def test_row_shape_for_non_channel_actor_is_exactly_the_base_field_set(client, app):
    """채널 정산을 못 보는 actor 의 행에는 `naver_settlement` **키가 아예 없다**.

    값을 None 으로 실어 보내고 화면에서 감추면 개발자 도구로 그대로 보인다(클라 숨김
    금지). 그래서 "값이 비었다"가 아니라 **키 부재**를 계약으로 못 박는다.
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=3_000_000, deposit=500_000))
    role, team = _CHANNEL_DENIED_ACTOR
    _login(client, _make_user(role=role, team=team))

    body = _get(client).get_json()
    rows = body["data"]["rows"]

    assert rows, "시드한 주문이 행 목록에 없다"
    assert set(rows[0]) == _ROW_KEYS, (
        f"행 키가 계약과 다르다: 추가={set(rows[0]) - _ROW_KEYS} 누락={_ROW_KEYS - set(rows[0])}"
    )
    assert body["data"]["channel_settlement_visible"] is False


def test_channel_settlement_visible_flag_matches_the_gate(client, app):
    """`channel_settlement_visible` 은 키 존재 여부와 **같은 신호**다.

    플래그와 실제 키가 갈리면 화면이 `<th>` 는 그렸는데 `<td>` 가 없는(또는 그 반대)
    표를 만든다 — 칸 수가 어긋난 표는 모든 열이 한 칸씩 밀린다.
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=0))

    for role, team in (_CHANNEL_ALLOWED_ACTOR, _CHANNEL_DENIED_ACTOR):
        _login(client, _make_user(role=role, team=team))
        data = _get(client).get_json()["data"]
        visible = data["channel_settlement_visible"]
        has_key = all(_NAVER_SETTLE_KEY in row for row in data["rows"])
        assert visible is has_key, f"{role}+{team}: 플래그={visible} 키존재={has_key}"


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
# 6. 정렬 — 미수 먼저, 그 안에서 경과일 오래된 순, 완료일 미상은 묶음 뒤
# ==========================================================================
def test_receivable_rows_come_before_settled_ones(client, app):
    """받을 돈이 있는 건이 위다 — 이 화면의 목적은 회수다.

    목업은 "경과일 오래된 순"만 말했다. 그대로 두면 잔금 0 인 옛 주문이 첫 페이지를
    통째로 차지한다(스테이징 실화면에서 1,263일 전 0원 주문부터 나왔다). 회수할 게
    없는 건이 회수 목록의 맨 위에 서는 것을 red 로 잡는다.
    """
    # 회수할 게 없는 아주 오래된 건(잔금 0) vs 최근이지만 미수인 건.
    _seed_order(completion="2023-01-05", sd=_money(items_total=1_000_000, deposit=1_000_000))
    _seed_order(completion="2026-08-20", sd=_money(items_total=1_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    rows = _get(client).get_json()["data"]["rows"]
    flags = [r["receivable"] for r in rows]

    assert rows[0]["receivable"] is True, (
        "회수할 돈이 없는 건이 목록 맨 위에 있다 — 경과일만 보고 정렬했다"
    )
    assert flags == sorted(flags, reverse=True), "미수 묶음이 뒤섞였다"


def test_rows_are_sorted_oldest_elapsed_first_within_each_group(client, app):
    """묶음 안에서는 목업 그대로 경과일 오래된 순이고, 완료일 미상은 묶음 뒤다."""
    _seed_order(completion="2026-08-30", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion="2026-02-01", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion=None, sd=_money(items_total=1_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    rows = [r for r in _get(client).get_json()["data"]["rows"] if r["receivable"]]
    known = [r["elapsed_days"] for r in rows if r["elapsed_days"] is not None]
    unknown_positions = [i for i, r in enumerate(rows) if r["elapsed_days"] is None]

    assert known == sorted(known, reverse=True), "경과일 내림차순이 아니다"
    if unknown_positions:
        assert min(unknown_positions) >= len(known), "완료일 미상이 묶음 뒤가 아니다"


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


# ==========================================================================
# 8. aging 구간 합계는 목록과 **한 응답**에 실린다 (P1 성능 개선의 계약)
#
# 화면은 예전에 구간마다 `aging=<code>` 로 5번 더 물었다. 한 요청이 모집단 전량 스캔이라
# 스코프를 한 번 바꿀 때마다 같은 스캔이 6번 돌았다(2026-08-31 운영 실측: 막대까지 2.9초,
# 그중 서버 1.26초). 이제 서버가 `aging_summary` 로 함께 낸다 — **값이 그대로여야** 한다.
# ==========================================================================
def _summary_by_code(data: dict) -> dict:
    """`aging_summary` 를 코드 → (건수, 금액) 으로 편다."""
    return {b["code"]: (b["count"], b["amount"]) for b in data["aging_summary"]}


def _seed_one_order_per_bucket() -> None:
    """버킷 5종에 골고루 걸리는 미수 주문 + 비교용 완납/미상 주문을 시드한다."""
    today = get_today_kst()
    for days in (3, 20, 45, 75, 200):
        _seed_order(
            completion=(today - datetime.timedelta(days=days)).isoformat(),
            sd=_money(items_total=1_000_000 + days, deposit=0),
        )
    paid_sd = _money(items_total=2_000_000, deposit=2_000_000)
    _seed_order(completion=(today - datetime.timedelta(days=10)).isoformat(), sd=paid_sd)
    _seed_order(completion=None, sd=_money(items_total=3_000_000, deposit=0))


def test_aging_summary_equals_asking_each_bucket_separately(client, app):
    """구간 합계가 **구간마다 따로 물어 얻던 값과 정확히 같다**.

    이 파일에서 가장 중요한 테스트다. 6회 → 1회로 줄인 대가로 숫자가 1원이라도 달라지면
    실무자가 보던 회수 금액이 조용히 바뀐다 — 그 순간을 red 로 잡는다.
    """
    _seed_one_order_per_bucket()
    _login(client, _make_user(role="ADMIN"))

    summary = _summary_by_code(_get(client).get_json()["data"])

    for code, (count, amount) in summary.items():
        slice_data = _get(client, aging=code).get_json()["data"]
        assert slice_data["total_count"] == count, f"{code} 건수가 갈렸다"
        assert slice_data["totals"]["balance"] == amount, f"{code} 금액이 갈렸다"


def test_aging_summary_is_unchanged_when_one_bucket_is_selected(client, app):
    """막대를 눌러 목록을 좁혀도 막대 값은 그대로다.

    고른 구간까지 반영하면 그 구간만 남고 나머지 막대가 0 으로 무너진다 — 예전 화면이
    `aging` 파라미터를 구간 코드로 덮어써서 지키던 성질을 이제 서버가 보장한다.
    """
    _seed_one_order_per_bucket()
    _login(client, _make_user(role="ADMIN"))

    everything = _summary_by_code(_get(client).get_json()["data"])
    narrowed = _get(client, aging="D91_PLUS").get_json()["data"]

    assert _summary_by_code(narrowed) == everything, "구간 선택이 막대 값을 바꿨다"
    assert {row["aging"] for row in narrowed["rows"]} == {"D91_PLUS"}, "목록은 좁혀져야 한다"


def test_aging_summary_follows_the_scope_filters(client, app):
    """구간 합계는 기간·정산상태·채널 스코프를 **따라간다**(집계 API 의 기간 무관 aging 과 다르다).

    요약 탭 aging 은 모집단 전체라 값이 다르다 — 그쪽을 실무 탭에 재사용하면 같은 화면에서
    숫자가 갈린다(그래서 재사용하지 않는다).
    """
    today = get_today_kst()
    issued_sd = _money(items_total=5_000_000, deposit=0)
    issued_sd["settlement"] = {"deductions": [{"department": "SALES", "amount": 1000}]}
    _seed_order(completion=(today - datetime.timedelta(days=200)).isoformat(), sd=issued_sd)
    _seed_order(
        completion=(today - datetime.timedelta(days=200)).isoformat(),
        sd=_money(items_total=1_000_000, deposit=0),
    )
    _login(client, _make_user(role="ADMIN"))

    pending = _summary_by_code(_get(client, settlement="pending").get_json()["data"])
    issued = _summary_by_code(_get(client, settlement="issued").get_json()["data"])

    assert pending["D91_PLUS"][1] == 1_000_000, "대기분 합계에 청구완료 건이 섞였다"
    assert issued["D91_PLUS"][1] == 5_000_000, "청구완료 합계가 스코프를 안 따라간다"


def test_aging_summary_lists_every_bucket_in_order_even_when_empty(client, app):
    """값이 0 인 구간도 생략하지 않는다 — 빠지면 화면이 '그 구간이 없다'로 읽는다."""
    _seed_order(completion=get_today_kst().isoformat(), sd=_money(items_total=1_000_000, deposit=0))
    _login(client, _make_user(role="ADMIN"))

    data = _get(client).get_json()["data"]

    codes = [bucket["code"] for bucket in data["aging_summary"]]
    assert codes == [code for code, _ in AGING_BUCKETS], "버킷 순서·구성이 서버 SSOT 와 다르다"
    assert all(bucket["label"] for bucket in data["aging_summary"]), "라벨이 비었다"
    assert any(bucket["count"] == 0 for bucket in data["aging_summary"]), "0 구간이 생략됐다"


def test_aging_summary_excludes_paid_and_unknown_completion_rows(client, app):
    """완납·완료일 미상은 어느 막대에도 들어가지 않는다(암묵 합산 금지).

    완료일 미상 미수는 KPI 타일이 따로 말한다 — 막대에 섞으면 경과일을 지어낸 셈이 된다.
    """
    _seed_one_order_per_bucket()
    _login(client, _make_user(role="ADMIN"))

    data = _get(client).get_json()["data"]

    bucket_total = sum(bucket["count"] for bucket in data["aging_summary"])
    receivable_with_date = sum(
        1 for row in _get(client).get_json()["data"]["rows"]
        if row["receivable"] and row["elapsed_days"] is not None
    )
    assert data["totals"]["unknown_completion_count"] >= 1, "미상 시드가 모집단에 없다"
    assert bucket_total == receivable_with_date, "막대 합과 미수(완료일 있음) 건수가 어긋난다"


# ==========================================================================
# 9. 네이버 정산 칸 (v1.1 T13) — 판정 우선순위와 쿼리 비용
#
# 판정·부호·날짜 매트릭스 전량은 `test_settlement_ops_channel_column.py` 가 맡는다.
# 여기서는 **행 API 표면**에서 그 값이 그대로 나오는지와, 컬럼을 붙인 대가가
# 쿼리 +1 을 넘지 않는지를 못 박는다(§8.1 T13 완료기준 ⑥).
# ==========================================================================
def test_naver_settlement_precedence_settled_beats_pending(client, app):
    """완료일이 있는 행이 하나라도 있으면 **정산완료**가 대기를 이긴다.

    한 주문에 상품주문 단위 정산 행이 여럿 붙는다. 마지막 행만 보거나 첫 행만 보면
    이미 돈이 들어온 건이 대기로 뜬다 — 실무자가 없는 미수를 쫓는다.
    """
    order_id = _seed_naver_order().id
    _seed_case(order_id, expect=datetime.date(2026, 9, 5))
    _seed_case(order_id, expect=datetime.date(2026, 9, 6),
               complete=datetime.date(2026, 9, 7))
    role, team = _CHANNEL_ALLOWED_ACTOR
    _login(client, _make_user(role=role, team=team))

    cell = _naver_cell(_get(client).get_json()["data"]["rows"], order_id)

    assert cell["status"] == "SETTLED"
    assert cell["settle_complete_date"] == "2026-09-07", "최근 완료일이 아니다"


def test_naver_settlement_precedence_pending_when_only_expect_dates(client, app):
    """완료일이 전부 없으면 대기이고, 날짜는 **가장 이른 예정일**이다."""
    order_id = _seed_naver_order().id
    _seed_case(order_id, expect=datetime.date(2026, 9, 20))
    _seed_case(order_id, expect=datetime.date(2026, 9, 4))
    role, team = _CHANNEL_ALLOWED_ACTOR
    _login(client, _make_user(role=role, team=team))

    cell = _naver_cell(_get(client).get_json()["data"]["rows"], order_id)

    assert cell["status"] == "PENDING"
    assert cell["settle_expect_date"] == "2026-09-04"


def test_naver_settlement_precedence_unmatched_and_not_applicable_differ(client, app):
    """네이버인데 정산 행 0건 = 미매칭 / 비네이버 = None. **둘을 섞지 않는다**.

    미매칭은 회계가 찾아야 하는 행이고, 비네이버는 애초에 대상이 아니다. 하나로 뭉개면
    "네이버 건인데 정산이 안 잡혔다"는 사실이 화면에서 사라진다.
    """
    naver_id = _seed_naver_order().id
    plain_id = _seed_order(completion="2026-08-10",
                           sd=_money(items_total=1_000_000, deposit=0)).id
    role, team = _CHANNEL_ALLOWED_ACTOR
    _login(client, _make_user(role=role, team=team))

    rows = _get(client).get_json()["data"]["rows"]

    assert _naver_cell(rows, naver_id)["status"] == "UNMATCHED"
    assert _naver_cell(rows, plain_id) is None


def test_rows_api_costs_at_most_one_extra_query_for_the_column(client, app):
    """컬럼이 붙어도 행 API 의 쿼리 수는 **+1 이하**로 늘어난다.

    실무 탭은 모집단 전량을 도는 hot path 다. 행마다 정산을 다시 묻는 구현이면 시드
    3건에서도 여기서 red 가 된다 — 운영 1,978건에서 처음 발견하면 이미 늦다.
    """
    for _ in range(3):
        _seed_case(_seed_naver_order().id, expect=datetime.date(2026, 9, 5))

    denied_role, denied_team = _CHANNEL_DENIED_ACTOR
    _login(client, _make_user(role=denied_role, team=denied_team))
    _, without = _count_queries(lambda: _get(client))

    allowed_role, allowed_team = _CHANNEL_ALLOWED_ACTOR
    _login(client, _make_user(role=allowed_role, team=allowed_team))
    _, with_column = _count_queries(lambda: _get(client))

    assert with_column - without <= 1, (
        f"컬럼 때문에 쿼리가 {with_column - without}회 늘었다"
        f" (없을 때 {without} → 있을 때 {with_column}) — N+1 이다"
    )


def test_service_defaults_to_omitting_the_naver_settlement_key(app):
    """서비스 기본값은 **키를 만들지 않는 것**이다.

    새 호출자가 인자를 안 넘겨도 회계 정보가 새지 않는다 — 안전한 쪽이 기본이어야 한다.
    """
    _seed_case(_seed_naver_order().id, complete=datetime.date(2026, 9, 3))

    rows = list_settlement_rows(db_session())["rows"]

    assert rows, "행이 없다"
    assert all("naver_settlement" not in row for row in rows)
