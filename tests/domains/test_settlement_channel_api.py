"""SETTLE-CHANNEL-01 §5: 채널(네이버) 정산 API 권한 매트릭스 + 응답 계약 테스트.

이 파일이 red 로 잡아야 하는 것:

1. **권한 매트릭스 이탈** — 허용은 ADMIN 과 **회계팀(ACCOUNTING) MANAGER/STAFF 뿐**이다.
   정책 엔진은 ``role == "MANAGER"`` 를 team 검사보다 먼저 통과시키므로(§1), CS 팀
   MANAGER 가 200 을 받으면 게이트가 엔진으로 새어 나간 것이다 — 운영 실측상 회계 업무
   담당 예정자 2명이 바로 그 조합이라 이 한 칸이 이 기능의 인가 경계 전부다.
2. **응답 스키마 드리프트** — ``static/js/settlement/channel.js`` 가 키 이름 하나에
   화면 블록 하나씩을 걸고 있다. 최상위·``sync``·``kpi``·``ledger.pagination`` 키 집합과
   워터폴 7단계 **순서**를 정확 일치로 못 박는다.
3. **부호 뒤집기** — 취소·환급 행(``NORMAL_SETTLE_AFTER_CANCEL``)의 음수를 절대값으로
   바꾸거나 합계에서 빼면 red(계약 D-1). 합계는 음수를 **포함한** 실제 합이다.
4. **계좌번호 노출** — 원본 계좌번호가 응답 어디에도 나오면 안 된다(뒤 4자리 마스킹만).
5. **충전금 섞임** — ``CHARGE_AMT``(통장 미기록 상계)와 ``ACCOUNT``(계좌 이체)가 한
   숫자로 합쳐지면 은행 대사가 통째로 틀린다(계약 D-7).
6. **결측을 0 으로 그리기** — 한 번도 동기화하지 않았으면 ``sync.never`` 가 True 여야
   한다. 이게 False 면 화면이 "정산 0원"이라는 없는 사실을 말한다(계약 D-10).
7. **감사 누락** — 동기화 요청은 ``NAVER_SETTLE_SYNC_REQUEST`` 행위로 기록된다.

테스트 데이터 규율: 존재하지 않는 FK id 를 쓰지 않는다(SQLite 는 FK 를 강제하지 않아
로컬만 통과하고 PG 레인에서 터진다). 여기서 만드는 정산 행은 FK 가 없는 소프트 참조라
``foms_order_id`` 를 비워 둔다.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from db import db_session
from foms.services.audit_message_display import ACTION_LABELS
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.settlement_channel import mask_account_no
from models import (
    ExternalOrderLink,
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverVatCase,
    NaverVatDaily,
    SecurityLog,
    SystemSetting,
)

# 권한 매트릭스 SSOT 재사용(복제 금지 — 두 파일이 각자 하드코딩하면 한쪽만 갱신된다).
from tests.domains.test_auth_finance import _login, _make_user  # noqa: E402

API_URL = "/api/settlement/channel"
SYNC_URL = "/api/settlement/channel/sync"

#: 통과해야 하는 actor. ADMIN + 회계팀 MANAGER/STAFF 만이다.
_ALLOWED_ACTORS = [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")]

#: 거부되어야 하는 actor. **MANAGER+CS 가 핵심**이다(엔진이라면 통과해 버린다).
_DENIED_ACTORS = [("MANAGER", "CS"), ("STAFF", "CS"), ("STAFF", "SALES"),
                  ("VIEWER", "ACCOUNTING"), ("VIEWER", None)]

#: 계약 §5 의 ``data`` 최상위 키. 화면 블록과 1:1 이라 하나만 빠져도 그 블록이 사라진다.
_DATA_KEYS = {
    "channel", "basis", "basis_label", "range", "granularity", "sync", "kpi",
    "daily", "daily_prev", "waterfall", "deposit_channels", "reconcile",
    "commission", "vat", "exceptions", "ledger", "holdback",
}

_SYNC_KEYS = {
    "last_run_at", "last_ok_at", "status", "coverage_from", "coverage_to",
    "rolling_days", "final_before", "vat_available_to", "rev", "stale", "never",
}

_KPI_SCALARS = {
    "settled_amount", "expected_amount", "expected_account_amount",
    "expected_charge_amount", "commission_total", "commission_rate",
    "holdback_amount", "match_rate", "unmatched_count", "case_count",
    "unmatched_pending_count", "unmatched_unlinked_count",
}

#: 워터폴은 **순서가 계약**이다(부동 막대가 누적되는 순서 그 자체).
_WATERFALL_ORDER = ["pay_settle", "commission", "benefit", "deduction_restore",
                    "holdback", "minus_charge", "settle_amount"]

_ACCOUNT_NO = "352-1234-567890"


# --------------------------------------------------------------------------
# 시드 헬퍼
# --------------------------------------------------------------------------
def _daily(expect: datetime.date, **kwargs) -> NaverSettleDaily:
    """일별 정산 1행. 금액은 전부 명시(기본값이 조용히 0 이 되지 않게)."""
    values = {
        "settle_amount": Decimal("1000000"), "pay_settle_amount": Decimal("1100000"),
        "commission_settle_amount": Decimal("-100000"),  # 네이버는 수수료를 음수로 준다(실측 2026-09-02)
        "benefit_settle_amount": Decimal("0"),
        "deduction_restore_settle_amount": Decimal("0"),
        "pay_holdback_amount": Decimal("0"), "minus_charge_amount": Decimal("0"),
        "normal_settle_amount": Decimal("1000000"), "quick_settle_amount": Decimal("0"),
        "settlement_limit_amount": Decimal("0"),
        "settle_method_type": "ACCOUNT", "bank_type": "KB",
        "depositor_name": "라홈", "account_no": _ACCOUNT_NO,
    }
    values.update(kwargs)
    row = NaverSettleDaily(channel="NAVER", settle_expect_date=expect,
                           raw_snapshot={"settleExpectDate": expect.isoformat()},
                           synced_at=datetime.datetime(2026, 9, 1, 0, 0), **values)
    db_session.add(row)
    return row


def _case(expect: datetime.date, **kwargs) -> NaverSettleCase:
    """건별 정산 1행."""
    values = {
        "product_order_id": "2026090100001", "order_id": "2026090100000",
        "product_order_type": "PROD_ORDER", "settle_type": "NORMAL_SETTLE_ORIGINAL",
        "product_name": "루나 3000", "pay_settle_amount": Decimal("1100000"),
        "total_pay_commission_amount": Decimal("-100000"),
        "selling_interlock_commission_amount": Decimal("0"),
        "settle_expect_amount": Decimal("1000000"), "match_status": "MATCHED",
    }
    values.update(kwargs)
    row = NaverSettleCase(
        channel="NAVER", search_date=expect, settle_expect_date=expect,
        period_type="SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
        raw_snapshot={"productOrderId": values["product_order_id"]},
        synced_at=datetime.datetime(2026, 9, 1, 0, 0), **values)
    db_session.add(row)
    return row


def _seed_basic(today: datetime.date) -> datetime.date:
    """기본 시드: 계좌 정산 1건 + 충전금 정산 1건 + 대응하는 건별 2행.

    Returns:
        시드한 정산 예정일.
    """
    day = today - datetime.timedelta(days=1)
    _daily(day)
    _daily(day, settle_method_type="CHARGE_AMT", bank_type=None, account_no=None,
           depositor_name=None, settle_amount=Decimal("300000"),
           pay_settle_amount=Decimal("330000"),
           commission_settle_amount=Decimal("-30000"),
           normal_settle_amount=Decimal("300000"))
    _case(day)
    _case(day, product_order_id="2026090100002", pay_settle_amount=Decimal("330000"),
          settle_expect_amount=Decimal("300000"),
          total_pay_commission_amount=Decimal("-30000"))
    db_session.commit()
    return day


def _get(client, **params):
    """조회 호출 헬퍼(기본 파라미터 없음 = 서버 기본 구간)."""
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return client.get(f"{API_URL}?{query}" if query else API_URL)


def _data(resp) -> dict:
    """200 을 확인하고 ``data`` 를 꺼낸다."""
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    return body["data"]


# --------------------------------------------------------------------------
# 1. 권한 매트릭스
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
def test_allowed_actors_get_200(client, app, role, team):
    """ADMIN·회계팀 MANAGER/STAFF 는 조회 200."""
    _login(client, _make_user(role=role, team=team))
    assert _get(client).status_code == 200, (role, team)


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_denied_actors_get_403_json(client, app, role, team):
    """그 밖의 actor 는 403 JSON — **MANAGER+CS 포함**(엔진이라면 통과한다)."""
    _login(client, _make_user(role=role, team=team))
    resp = _get(client)
    assert resp.status_code == 403, (role, team, resp.status_code)
    assert "Location" not in resp.headers, "API 거부는 302 가 아니라 403 JSON"
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None and body["error"]


def test_anonymous_is_not_served(client, app):
    """미인증은 로그인 리다이렉트(또는 401) — 절대 200 이 아니다."""
    resp = _get(client)
    assert resp.status_code in (301, 302, 401), resp.status_code


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_denied_actors_sync_403(client, app, role, team):
    """동기화 요청도 같은 게이트다(읽기만 막고 쓰기를 열어 두는 구멍 금지)."""
    _login(client, _make_user(role=role, team=team))
    resp = client.post(SYNC_URL, json={})
    assert resp.status_code == 403, (role, team, resp.status_code)
    assert resp.get_json()["success"] is False


# --------------------------------------------------------------------------
# 2. 응답 스키마
# --------------------------------------------------------------------------
def test_data_schema_keys_exact(client, app):
    """최상위·sync·kpi·pagination 키 집합 정확 일치 + 워터폴 순서 고정.

    ``ledger.axis`` 에 ``shifted_out`` 이 늘어난 것은 **C2(2026-09-03) 의 의도된 계약 변경**이다 —
    축 전환으로 조회 창 밖으로 밀린 행 수를 화면이 말하게 됐다. 그전에는 표가 조용히 줄어들 때
    "날짜가 없어서"(``excluded``)인지 "다른 기간으로 옮겨 가서"인지 아무도 말하지 않았다.
    """
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert set(data) == _DATA_KEYS
    assert set(data["sync"]) == _SYNC_KEYS
    assert set(data["kpi"]) == _KPI_SCALARS | {"prev"}
    assert set(data["kpi"]["prev"]) == _KPI_SCALARS
    assert set(data["range"]) == {"from", "to"}
    assert [step["key"] for step in data["waterfall"]] == _WATERFALL_ORDER
    assert all(set(step) == {"key", "label", "amount"} for step in data["waterfall"])
    assert set(data["ledger"]) == {"kind", "groups", "rows", "pagination", "axis"}
    assert set(data["ledger"]["axis"]) == {"basis", "label", "supported", "excluded",
                                           "shifted_out"}
    assert set(data["ledger"]["pagination"]) == {"page", "per_page", "total", "pages"}
    assert set(data["reconcile"]) == {"daily_total", "case_total", "diff"}
    assert set(data["commission"]) == {"by_type", "total", "max_interlock"}
    assert set(data["vat"]) == {"available_to", "rows", "total", "final"}


def test_ledger_rows_carry_labels_match_and_raw(client, app):
    """원장 행은 원본 필드 + enum 한글 라벨 + 매칭 상태 + 원본 스냅샷을 함께 낸다."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    rows = _data(_get(client))["ledger"]["rows"]

    assert rows, "건별 원장이 비었다"
    row = rows[0]
    assert row["settle_type_label"] == "일반 정산"
    assert row["product_order_type_label"] == "상품 주문"
    assert row["match_status"] == "MATCHED"
    assert "foms_order_id" in row
    assert row["raw"] == {"productOrderId": row["product_order_id"]}


def test_ledger_group_dates_match_row_dates(client, app):
    """날짜 그룹 키가 행의 날짜와 같다(다르면 화면이 빈 그룹만 그린다)."""
    day = _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    ledger = _data(_get(client))["ledger"]

    assert [group["date"] for group in ledger["groups"]] == [day.isoformat()]
    assert ledger["groups"][0]["count"] == 2
    assert ledger["pagination"]["total"] == 2
    assert {row["settle_expect_date"] for row in ledger["rows"]} == {day.isoformat()}


def test_ledger_filters_narrow_rows(client, app):
    """``type``·``q`` 는 파라미터 바인딩으로 좁힌다(집계·페이저도 함께 줄어든다)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    typed = _data(_get(client, type="PROD_ORDER"))["ledger"]
    assert typed["pagination"]["total"] == 2
    searched = _data(_get(client, q="2026090100002"))["ledger"]
    assert searched["pagination"]["total"] == 1
    assert searched["rows"][0]["product_order_id"] == "2026090100002"
    empty = _data(_get(client, type="DELIVERY"))["ledger"]
    assert empty["pagination"]["total"] == 0 and empty["rows"] == []


# --------------------------------------------------------------------------
# 3. 파라미터 검증(400)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("params", [
    {"from": "2026-13-01"},
    {"to": "not-a-date"},
    {"basis": "settle"},
    {"granularity": "quarter"},
    {"ledger": "orders"},
    {"channel": "COUPANG"},
    {"from": "2024-01-01", "to": "2026-01-01"},
])
def test_bad_params_400(client, app, params):
    """형식·허용 집합·구간 폭(400일 초과) 위반은 400 + 사람이 읽는 사유."""
    _login(client, _make_user(role="ADMIN"))
    resp = _get(client, **params)
    assert resp.status_code == 400, (params, resp.get_data(as_text=True))
    body = resp.get_json()
    assert body["success"] is False and body["error"]


def test_reversed_range_400(client, app):
    """시작일이 종료일보다 뒤면 400(조용히 뒤집어 주지 않는다)."""
    _login(client, _make_user(role="ADMIN"))
    resp = _get(client, **{"from": "2026-09-10", "to": "2026-09-01"})
    assert resp.status_code == 400


# --------------------------------------------------------------------------
# 4. 마스킹 · 입금 채널 분리
# --------------------------------------------------------------------------
def test_mask_account_no_keeps_last_four_only():
    """마스킹 규칙 자체(구분자 제거 후 뒤 4자리)."""
    assert mask_account_no("352-1234-567890") == "****7890"
    assert mask_account_no("123") == "****"
    assert mask_account_no(None) == ""


def test_account_no_never_leaves_the_server(client, app):
    """응답 본문 어디에도 원본 계좌번호가 없다(마스킹만 나간다)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    resp = _get(client)
    text = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert _ACCOUNT_NO not in text and "3521234567890" not in text
    assert "****7890" in text


def test_charge_amt_and_account_are_split(client, app):
    """충전금 상계와 계좌 이체가 KPI·입금 채널 양쪽에서 갈라져 나온다."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    kpi = data["kpi"]
    assert kpi["expected_account_amount"] == 1000000
    assert kpi["expected_charge_amount"] == 300000
    assert kpi["expected_amount"] == 1300000
    assert kpi["settled_amount"] == 0

    methods = {row["method"]: row for row in data["deposit_channels"]}
    assert set(methods) == {"ACCOUNT", "CHARGE_AMT"}
    assert methods["ACCOUNT"]["account_no_masked"] == "****7890"
    assert methods["ACCOUNT"]["method_label"] == "계좌 이체"
    assert methods["CHARGE_AMT"]["method_label"] == "충전금"
    assert methods["CHARGE_AMT"]["account_no_masked"] == ""


def test_deposit_channels_skip_zero_days_and_label_undecided_method(client, app):
    """정산액 0 인 날은 입금 채널에 안 세고, 방식이 비어 오는 예정 행은 '미정(정산 예정)' 이다.

    스테이징 실측(2026-09-02): 은행 정보가 빈 0원 행 16개가 "계좌 이체 · *" 로, 예정일이 안 온
    행이 "방식 미상" 으로 보였다. 둘 다 입금 사실이 아니라 데이터 모양이다.
    """
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _daily(day)
    _daily(day, settle_amount=Decimal("0"), pay_settle_amount=Decimal("0"),
           commission_settle_amount=Decimal("0"), normal_settle_amount=Decimal("0"),
           bank_type=None, account_no=None, depositor_name=None)
    _daily(today + datetime.timedelta(days=3), settle_method_type=None, bank_type=None,
           account_no=None, depositor_name=None, settle_complete_date=None,
           settle_amount=Decimal("500000"), pay_settle_amount=Decimal("550000"),
           commission_settle_amount=Decimal("-50000"), normal_settle_amount=Decimal("500000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    rows = _data(_get(client))["deposit_channels"]

    labels = {row["method_label"]: row for row in rows}
    assert "미정(정산 예정)" in labels and labels["미정(정산 예정)"]["amount"] == 500000
    account = [row for row in rows if row["method"] == "ACCOUNT"]
    assert len(account) == 1 and account[0]["count"] == 1  # 0원 행은 세지 않는다


def test_completed_rows_land_in_settled_not_expected(client, app):
    """정산 완료일이 찍힌 행은 '완료액'이고 '예정액'에 섞이지 않는다(계약 D-6)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=2)
    _daily(day, settle_complete_date=day)
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert data["kpi"]["settled_amount"] == 1000000
    assert data["kpi"]["expected_amount"] == 0
    assert data["daily"], "일별 버킷이 비었다"
    assert any(bucket["completed"] for bucket in data["daily"])


# --------------------------------------------------------------------------
# 5. 부호 보존
# --------------------------------------------------------------------------
def test_negative_cancel_row_keeps_its_sign(client, app):
    """정산 후 취소(음수)를 절대값으로 바꾸지 않고 합계에 **그대로** 넣는다(계약 D-1)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _daily(day)
    _daily(day, settle_amount=Decimal("-250000"),
           pay_settle_amount=Decimal("-275000"),
           commission_settle_amount=Decimal("25000"),  # 취소 행은 수수료가 되돌아와 +
           normal_settle_amount=Decimal("-250000"))
    _case(day)
    _case(day, product_order_id="2026090100003",
          settle_type="NORMAL_SETTLE_AFTER_CANCEL",
          pay_settle_amount=Decimal("-275000"),
          total_pay_commission_amount=Decimal("25000"),
          settle_expect_amount=Decimal("-250000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    # 1,000,000 + (-250,000) — 절대값 합(1,250,000)이면 red.
    assert data["kpi"]["expected_amount"] == 750000
    # -100,000 + 25,000 — 부호를 지우면(125,000) red.
    assert data["kpi"]["commission_total"] == -75000
    assert data["reconcile"]["case_total"] == 825000
    negatives = [row for row in data["ledger"]["rows"]
                 if row["settle_type"] == "NORMAL_SETTLE_AFTER_CANCEL"]
    assert negatives and negatives[0]["settle_expect_amount"] == -250000
    assert negatives[0]["settle_type_label"] == "정산 후 취소"
    assert any(item["kind"] == "NEGATIVE" for item in data["exceptions"])


def test_waterfall_deduction_steps_point_down(client, app):
    """차감 단계는 네이버 원본 부호(음수) 그대로 아래로 향한다 — 방향을 곱하지 않는다."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    steps = {step["key"]: step["amount"] for step in _data(_get(client))["waterfall"]}

    assert steps["pay_settle"] == 1430000
    assert steps["commission"] == -130000        # 저장값 -100,000 + -30,000 그대로
    assert steps["settle_amount"] == 1300000


# --------------------------------------------------------------------------
# 6. 동기화 상태 · 부가세
# --------------------------------------------------------------------------
def test_sync_never_true_without_state(client, app):
    """워터마크 행이 없으면 ``never`` — 화면이 0 을 사실로 말하지 않게 한다(계약 D-10)."""
    _login(client, _make_user(role="ADMIN"))
    sync = _data(_get(client))["sync"]

    assert sync["never"] is True and sync["stale"] is False
    assert sync["last_run_at"] is None and sync["rev"] is None
    assert sync["final_before"] == (get_today_kst() - datetime.timedelta(days=30)).isoformat()


def test_sync_stale_when_last_success_is_old(client, app):
    """36시간 넘게 성공하지 못했으면 ``stale`` 이 True 이고 ``never`` 는 False 다."""
    old = (now_utc_naive() - datetime.timedelta(hours=40)).isoformat()
    db_session.add(SystemSetting(
        setting_key="naver_settle_sync_state",
        setting_value={"rev": 7, "last_run_at": old, "last_ok_at": old,
                       "last_status": "OK", "coverage_from": "2026-08-01",
                       "coverage_to": "2026-09-15", "rolling_days": 30}))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    sync = _data(_get(client))["sync"]

    assert sync["never"] is False and sync["stale"] is True
    assert sync["rev"] == 7 and sync["status"] == "OK"
    assert sync["coverage_to"] == "2026-09-15" and sync["rolling_days"] == 30


def test_vat_available_to_is_previous_month_end(client, app):
    """부가세는 **전월 말일까지만** 제공된다 — 당월 구간은 빈 표가 아니라 이 한계일을 말한다."""
    today = get_today_kst()
    available_to = today.replace(day=1) - datetime.timedelta(days=1)
    db_session.add(NaverVatDaily(
        channel="NAVER", settle_basis_date=available_to,
        total_sales_amount=Decimal("5000000"),
        taxation_sales_amount=Decimal("4545455"),
        tax_exemption_sales_amount=Decimal("0"),
        credit_card_amount=Decimal("3000000"),
        cash_income_deduction_amount=Decimal("1000000"),
        cash_outgoing_evidence_amount=Decimal("500000"),
        cash_exclusion_issuance_amount=Decimal("0"),
        other_amount=Decimal("500000"), is_final=True,
        raw_snapshot={"settleBasisDate": available_to.isoformat()},
        synced_at=datetime.datetime(2026, 9, 1, 0, 0)))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    vat = _data(_get(client, **{"from": available_to.isoformat(),
                                "to": today.isoformat(), "ledger": "vat_case"}))["vat"]

    assert vat["available_to"] == available_to.isoformat()
    assert [row["date"] for row in vat["rows"]] == [available_to.isoformat()]
    assert set(vat["total"]) == {key for key in vat["rows"][0] if key != "date"}
    assert vat["total"]["cash_income_deduction"] == 1000000
    assert vat["total"]["cash_outgoing_evidence"] == 500000
    assert vat["final"] is True


def test_commission_by_type_shares_and_labels(client, app):
    """수수료 유형별 구성은 한글 라벨과 비중을 함께 낸다(화면이 enum 을 몰라도 되게)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    for code, amount in (("PLATFORM_COMMISSION", "80000"), ("PAY_COMMISSION", "20000")):
        db_session.add(NaverSettleCommission(
            channel="NAVER", search_date=day, settle_expect_date=day,
            period_type="SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
            order_no="2026090100000", product_order_id="2026090100001",
            commission_type=code, pay_means_type="PAYMEANS_TYPE_CCARD",
            commission_amount=Decimal(amount),
            commission_basis_amount=Decimal("1100000"),
            raw_snapshot={"commissionType": code},
            synced_at=datetime.datetime(2026, 9, 1, 0, 0)))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    commission = _data(_get(client))["commission"]

    assert commission["total"] == 100000
    assert [item["type"] for item in commission["by_type"]] == [
        "PLATFORM_COMMISSION", "PAY_COMMISSION"]
    assert commission["by_type"][0]["label"] == "판매 수수료"
    assert commission["by_type"][0]["share"] == pytest.approx(0.8)
    assert set(commission["max_interlock"]) == {"amount", "cap"}


# --------------------------------------------------------------------------
# 7. 동기화 요청(POST)
# --------------------------------------------------------------------------
def test_sync_enqueues_and_writes_audit(client, app, monkeypatch):
    """허용 actor 의 동기화 요청은 큐에 들어가고 감사 1행을 남긴다."""
    from foms.services.jobs import queue as queue_module

    seen: dict = {}

    def _fake(actor_user_id=None, *, backfill_from=None, dry_run=False):
        seen.update({"actor": actor_user_id, "backfill_from": backfill_from})
        return True

    monkeypatch.setattr(queue_module, "enqueue_naver_settle_sync", _fake)
    user = _make_user(role="STAFF", team="ACCOUNTING")
    # 요청 뒤에는 세션이 정리돼 ORM 인스턴스가 detach 된다 — id 를 먼저 뽑아 둔다.
    user_id = user.id
    _login(client, user)
    before = db_session.query(SecurityLog).filter(
        SecurityLog.action == "NAVER_SETTLE_SYNC_REQUEST").count()

    resp = client.post(SYNC_URL, json={"backfill_from": "2026-06-01"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["data"] == {"queued": True}
    assert seen == {"actor": user_id, "backfill_from": "2026-06-01"}

    logs = db_session.query(SecurityLog).filter(
        SecurityLog.action == "NAVER_SETTLE_SYNC_REQUEST").all()
    assert len(logs) == before + 1
    assert logs[-1].user_id == user_id
    assert logs[-1].detail["backfill_from"] == "2026-06-01"


def test_sync_reports_already_queued_without_lying(client, app, monkeypatch):
    """이미 대기 중이면 ``queued: False`` 다 — 성공한 척도, 실패한 척도 하지 않는다."""
    from foms.services.jobs import queue as queue_module

    monkeypatch.setattr(queue_module, "enqueue_naver_settle_sync",
                        lambda actor_user_id=None, **_kwargs: False)
    _login(client, _make_user(role="ADMIN"))
    body = client.post(SYNC_URL, json={}).get_json()

    assert body["success"] is True and body["data"] == {"queued": False}


def test_sync_rejects_bad_backfill_date(client, app):
    """``backfill_from`` 형식 오류는 큐에 넣기 **전에** 400 으로 돌려세운다."""
    _login(client, _make_user(role="ADMIN"))
    resp = client.post(SYNC_URL, json={"backfill_from": "2026-6-1x"})

    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_sync_audit_action_has_business_label():
    """행위 코드는 표시 SSOT 에 등재돼 있다(미등재면 감사 화면에 영문 코드가 뜬다)."""
    assert ACTION_LABELS["NAVER_SETTLE_SYNC_REQUEST"] == "네이버 정산 동기화 요청"


# --------------------------------------------------------------------------
# 8. 원장 3종 · 세밀도 · 페이저
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind,granularity", [
    ("case", "day"), ("commission", "week"), ("vat_case", "month"),
])
def test_every_ledger_kind_and_granularity_renders(client, app, kind, granularity):
    """원장 3종·세밀도 3종이 모두 응답한다(``basis=pay`` 는 ``pay_date`` 가 없는 표도 있다)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client, ledger=kind, granularity=granularity, basis="pay"))

    assert data["ledger"]["kind"] == kind
    assert data["granularity"] == granularity
    assert data["basis"] == "pay" and data["basis_label"] == "결제일 기준"


def test_pagination_clamps_out_of_range_page(client, app):
    """범위 밖 page 는 서버가 접는다(화면이 빈 표를 그리지 않게 — 값의 권위는 서버다)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    pagination = _data(_get(client, page=99, per_page=1))["ledger"]["pagination"]

    assert pagination == {"page": 2, "per_page": 1, "total": 2, "pages": 2}


def test_per_page_is_capped(client, app):
    """``per_page`` 상한 200 — 한 번에 원장 전량을 끌어오는 요청을 막는다."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    assert _data(_get(client, per_page=5000))["ledger"]["pagination"]["per_page"] == 200


# --------------------------------------------------------------------------
# 11. v1.2 — F1 미연결 2갈래 · F2 보류·한도 일자별 상세
# --------------------------------------------------------------------------
def _link(external_id: str) -> int:
    """주문이 아직 안 만들어진(``order_id`` NULL) 네이버 링크 1행 — 워크벤치 대기 상태.

    id 만 돌려준다 — 요청이 끝나면 세션이 닫혀 인스턴스가 detach 되고, 그 뒤 ``link.id`` 는
    DetachedInstanceError 다.
    """
    link = ExternalOrderLink(channel="NAVER", external_id=external_id, order_id=None,
                             sync_status="COLLECTED", raw_snapshot={})
    db_session.add(link)
    db_session.flush()
    return int(link.id)


def test_unmatched_exceptions_split_by_link_presence(client, app):
    """미연결이 두 갈래로 나온다: 링크 있음·주문 없음 = UNMATCHED(워크벤치), 링크 없음 = UNLINKED(수집 전).

    조치 링크가 갈래마다 다르다 — 워크벤치 대기는 **그 집**(`link_id`)으로, 수집 전 주문은
    수집 운영 화면으로. KPI 도 두 갈래 건수를 따로 말하고 합은 기존 ``unmatched_count`` 와 같다.
    MATCHED·NA 행은 어느 갈래에도 안 나온다(음성 대조군).
    """
    today = get_today_kst()
    day = _seed_basic(today)  # MATCHED 2행
    link_id = _link("2026090100031")
    _case(day, product_order_id="2026090100031", match_status="UNMATCHED", link_id=link_id)
    _case(day, product_order_id="2026090100032", match_status="UNMATCHED")
    _case(day, product_order_id="2026090100033", product_order_type="DELIVERY",
          match_status="NA", settle_expect_amount=Decimal("3000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    by_po = {item["ref"]["product_order_id"]: item for item in data["exceptions"]
             if item["kind"] in ("UNMATCHED", "UNLINKED")}
    assert set(by_po) == {"2026090100031", "2026090100032"}
    pending, unlinked = by_po["2026090100031"], by_po["2026090100032"]
    assert pending["kind"] == "UNMATCHED"
    assert pending["label"] == "워크벤치 대기(주문 미생성)"
    assert pending["action_url"] == f"/admin/naver-ingest/triage?link_id={link_id}"
    assert pending["ref"]["link_id"] == link_id
    assert unlinked["kind"] == "UNLINKED"
    assert unlinked["label"] == "수집 전 주문(링크 없음)"
    assert unlinked["action_url"] == "/admin/naver-ingest"
    assert unlinked["ref"]["link_id"] is None
    # 갈래 순서: 조치 가능한 워크벤치 대기가 앞.
    kinds = [item["kind"] for item in data["exceptions"] if item["kind"] in ("UNMATCHED", "UNLINKED")]
    assert kinds == ["UNMATCHED", "UNLINKED"]

    kpi = data["kpi"]
    assert kpi["unmatched_count"] == 2
    assert kpi["unmatched_pending_count"] == 1
    assert kpi["unmatched_unlinked_count"] == 1
    assert kpi["match_rate"] == 0.5          # MATCHED 2 / PROD_ORDER 4 (NA 는 분모 밖)
    assert kpi["case_count"] == 5
    assert kpi["prev"]["unmatched_pending_count"] == 0
    assert kpi["prev"]["unmatched_unlinked_count"] == 0


def test_unmatched_kinds_are_absent_when_every_row_is_matched(client, app):
    """전부 MATCHED 면 두 갈래 다 0 이고 예외에도 없다(갈래 분리가 유령 행을 만들지 않는다)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert not [item for item in data["exceptions"] if item["kind"] in ("UNMATCHED", "UNLINKED")]
    assert data["kpi"]["unmatched_pending_count"] == 0
    assert data["kpi"]["unmatched_unlinked_count"] == 0
    assert data["kpi"]["match_rate"] == 1.0


def test_holdback_block_lists_only_days_with_hold_or_limit_and_keeps_sign(client, app):
    """``holdback`` 블록: 두 컬럼 중 하나라도 0 이 아닌 일별 행만, 예정일 내림차순, 부호 원본, 합계는 KPI 와 같다.

    운영 실측(2026-09-03)의 모양을 그대로 시드한다 — 보류가 음수로 잡혔다가 뒤에 같은
    금액이 양수로 온다(해제). 절대값으로 바꾸거나 상계해 버리면 -1.2억 의 원인을 못 쫓는다.
    """
    today = get_today_kst()
    day = _seed_basic(today)                       # 보류 0 인 두 행 → 표에 없어야 한다
    d_hold = day - datetime.timedelta(days=1)
    d_both = day - datetime.timedelta(days=2)
    _daily(d_hold, pay_holdback_amount=Decimal("-10053445"), settle_complete_date=d_hold)
    _daily(d_both, settlement_limit_amount=Decimal("-500000"))
    _daily(d_both, pay_holdback_amount=Decimal("2410000"), settle_method_type="CHARGE_AMT",
           bank_type=None, account_no=None, depositor_name=None)
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    block = data["holdback"]
    assert set(block) == {"rows", "count", "total"}
    assert block["count"] == 3 == len(block["rows"])
    assert [row["date"] for row in block["rows"]] == [d_hold.isoformat(), d_both.isoformat(),
                                                      d_both.isoformat()]
    assert set(block["rows"][0]) == {"date", "settle_method_type", "settle_method_label",
                                     "pay_holdback", "settlement_limit", "amount", "completed"}
    first = block["rows"][0]
    assert first["pay_holdback"] == -10053445 and first["settlement_limit"] == 0
    assert first["amount"] == -10053445 and first["completed"] is True
    assert first["settle_method_type"] == "ACCOUNT"
    limit_row = next(row for row in block["rows"] if row["settlement_limit"] != 0)
    assert limit_row["settlement_limit"] == -500000 and limit_row["completed"] is False
    release = next(row for row in block["rows"] if row["pay_holdback"] == 2410000)
    assert release["settle_method_type"] == "CHARGE_AMT"
    # 합계는 더하기뿐(-10,053,445 + 2,410,000 / -500,000). 절대값 합(12,963,445)이면 red.
    assert block["total"] == {"pay_holdback": -7643445, "settlement_limit": -500000,
                              "amount": -8143445}
    assert data["kpi"]["holdback_amount"] == block["total"]["amount"]
    # 계좌번호는 이 블록에도 실리지 않는다.
    assert _ACCOUNT_NO not in str(block)


def test_holdback_block_is_empty_without_any_hold(client, app):
    """보류·한도가 전부 0 이면 빈 목록 + 합계 0(0 행을 채워 "보류가 있었다"로 읽히게 하지 않는다)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert data["holdback"] == {"rows": [], "count": 0,
                                "total": {"pay_holdback": 0, "settlement_limit": 0, "amount": 0}}


# --------------------------------------------------------------------------
# 12. 기준일 셀렉트 — 완료일 축은 되돌리지 않고, 없는 축은 되돌림을 말한다 (2026-09-03)
# --------------------------------------------------------------------------
def test_complete_axis_lists_only_completed_rows_and_counts_the_rest(client, app):
    """완료일 축: 완료일 있는 행만 완료일로 묶고, 완료일 없는 행은 ``axis.excluded`` 로 센다.

    되돌림(coalesce) 을 두면 미완료 행이 예정일에 얹혀 "완료일 기준" 표가 예정일 표와 같아진다 —
    스테이징 실측(2026-09-03)에서 셀렉트가 죽은 것처럼 보이던 원인이다.
    """
    today = get_today_kst()
    day = _seed_basic(today)                       # 완료일 없는 2행
    done_day = day - datetime.timedelta(days=2)
    _case(day, product_order_id="2026090100041", settle_complete_date=done_day)
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))

    ledger = _data(_get(client, basis="complete"))["ledger"]
    # ``shifted_out`` 은 C2(2026-09-03)로 늘어난 키다. 여기 완료일은 창 **안**이라 0 이다
    # (밀려난 행을 세는 축은 아래 전용 테스트가 따로 못 박는다).
    assert ledger["axis"] == {"basis": "complete", "label": "정산 완료일 기준",
                              "supported": True, "excluded": 2, "shifted_out": 0}
    assert [group["date"] for group in ledger["groups"]] == [done_day.isoformat()]
    assert ledger["pagination"]["total"] == 1
    assert ledger["rows"][0]["settle_complete_date"] == done_day.isoformat()
    # 음성 대조군: 예정일 축은 셋 다 싣고 제외가 0 이다.
    base = _data(_get(client))["ledger"]
    assert base["pagination"]["total"] == 3
    assert base["axis"] == {"basis": "expect", "label": "정산 예정일 기준",
                            "supported": True, "excluded": 0, "shifted_out": 0}


def test_unsupported_axis_falls_back_to_the_table_default_and_says_so(client, app):
    """수수료 표엔 결제일이, 부가세 표엔 정산 기준일밖에 없다 — 되돌리되 ``supported=False``.

    라벨만 바뀌고 표는 그대로인 조용한 되돌림이 결함이었다. 최상위 ``basis``/``basis_label`` 은
    사용자가 고른 값 그대로 남는다(셀렉트 상태의 권위).
    """
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    data = _data(_get(client, ledger="commission", basis="pay"))
    assert data["basis"] == "pay" and data["basis_label"] == "결제일 기준"
    assert data["ledger"]["axis"] == {"basis": "expect", "label": "정산 예정일 기준",
                                      "supported": False, "excluded": 0,
                                      "shifted_out": 0}

    vat = _data(_get(client, ledger="vat_case", basis="complete"))["ledger"]
    assert vat["axis"] == {"basis": "basis", "label": "정산 기준일 기준",
                           "supported": False, "excluded": 0, "shifted_out": 0}
    # 부가세 표에서 정산 기준일을 고르면 그게 곧 이 표의 축이다.
    vat_ok = _data(_get(client, ledger="vat_case", basis="basis"))["ledger"]
    assert vat_ok["axis"]["supported"] is True and vat_ok["axis"]["basis"] == "basis"


# --------------------------------------------------------------------------
# 13. C2 — 축 전환으로 조회 창 **밖으로 밀려난** 행 수 (2026-09-03)
# --------------------------------------------------------------------------
def _seed_pay_axis(today: datetime.date) -> datetime.date:
    """건별 3행 — 결제일이 창 안(A) / 창 밖(B) / 비어 있음(C). 예정일은 셋 다 창 안이다.

    이 시드가 **모집단 그 자체**다: 예정일 창(오늘-30~오늘+14) 안에 3행이 있고, 결제일 축으로
    바꾸면 A 만 남는다. 밀린 몫(B)과 빈 몫(C)이 실제로 존재해야 음성 대조군이 반증이 된다.

    Args:
        today: KST 오늘.

    Returns:
        시드한 정산 예정일.
    """
    day = today - datetime.timedelta(days=1)
    _case(day, product_order_id="2026090300001", pay_date=day)
    _case(day, product_order_id="2026090300002",
          pay_date=day - datetime.timedelta(days=90))
    _case(day, product_order_id="2026090300003", pay_date=None)
    db_session.commit()
    return day


def test_pay_axis_counts_rows_that_moved_out_of_the_window(client, app):
    """결제일 축: 표에서 사라진 3행 중 1행은 "날짜가 없어서", 1행은 "기간 밖으로 옮겨 가서"다.

    축을 바꾸면 표가 조용히 줄어드는 것이 C2 결함이었다. ``excluded``(축 날짜 NULL)와
    ``shifted_out``(축 날짜가 창 밖)은 **서로소**이므로 두 수와 표에 남은 수를 더하면 모집단이
    정확히 복원된다 — 겹쳐 세면 이 등식이 깨진다.
    """
    _seed_pay_axis(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    ledger = _data(_get(client, basis="pay"))["ledger"]

    assert ledger["axis"]["basis"] == "pay" and ledger["axis"]["supported"] is True
    assert ledger["axis"]["shifted_out"] == 1        # B: 결제일이 90일 전
    assert ledger["axis"]["excluded"] == 1           # C: 결제일 없음
    assert ledger["pagination"]["total"] == 1        # A 만 남는다
    # 서로소 증명: 남은 수 + 빈 몫 + 밀린 몫 = 예정일 창 안의 모집단 3행.
    assert (ledger["pagination"]["total"] + ledger["axis"]["excluded"]
            + ledger["axis"]["shifted_out"]) == 3


def test_expect_and_vat_axes_never_report_shifted_out(client, app):
    """음성 대조군 — **밀릴 행이 실제로 있는** 같은 시드에서 예정일·부가세 축은 0 이다.

    예정일 축은 창 정의식과 축 식이 같은 식이라 구조적으로 0 이고(밀릴 자리가 없다),
    부가세 건별은 애초에 예정일 창이라는 것이 없는 표다. 모집단 밖 표본으로 0 을 확인하면
    그건 반증이 아니라 빈 그릇을 센 것이다 — 그래서 B(밀린 행)가 있는 시드를 그대로 쓴다.
    """
    _seed_pay_axis(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    # 부가세 건별에도 행을 둔다(빈 표에서 0 을 보면 반증이 아니다).
    day = get_today_kst() - datetime.timedelta(days=1)
    for offset, order_id in ((0, "2026090300011"), (90, "2026090300012")):
        db_session.add(NaverVatCase(
            channel="NAVER", order_id=order_id, product_order_id=order_id,
            settle_basis_date=day - datetime.timedelta(days=offset),
            raw_snapshot={"orderId": order_id},
            synced_at=datetime.datetime(2026, 9, 1, 0, 0)))
    db_session.commit()

    # 밀린 행 B 가 결제일 축에서는 실제로 세어진다(대조군이 모집단 안이라는 증거).
    assert _data(_get(client, basis="pay"))["ledger"]["axis"]["shifted_out"] == 1

    expect = _data(_get(client, basis="expect"))["ledger"]
    assert expect["axis"]["shifted_out"] == 0
    assert expect["pagination"]["total"] == 3, "예정일 축은 셋 다 싣는다"

    vat = _data(_get(client, ledger="vat_case", basis="basis"))["ledger"]
    assert vat["axis"]["shifted_out"] == 0
    assert vat["pagination"]["total"] >= 1, "빈 표에서 잰 0 은 반증이 아니다"


def test_shifted_out_respects_the_type_and_search_filters(client, app):
    """밀린 행도 **화면과 같은 술어 안에서만** 센다 — 좁혀 놓고 전체 기준 수를 말하지 않는다.

    두 수가 다른 모집단을 세면 "3건이 빠졌다"는 안내가 화면에 보이는 표와 무관한 숫자가 된다.
    """
    _seed_pay_axis(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    # 검색으로 밀린 행(B) 하나만 남기면 밀린 수는 1, 표는 비고 빈 몫은 0 이다.
    only_b = _data(_get(client, basis="pay", q="2026090300002"))["ledger"]
    assert only_b["axis"]["shifted_out"] == 1
    assert only_b["axis"]["excluded"] == 0
    assert only_b["pagination"]["total"] == 0

    # 음성 대조군: 창 안 행(A)만 남기면 밀린 수가 0 이다(술어를 무시하면 1 이 나온다).
    only_a = _data(_get(client, basis="pay", q="2026090300001"))["ledger"]
    assert only_a["axis"]["shifted_out"] == 0
    assert only_a["pagination"]["total"] == 1

    # 유형 필터가 아무도 안 남기면 세 수가 모두 0 이다.
    none_left = _data(_get(client, basis="pay", type="NOTHING"))["ledger"]
    assert none_left["axis"]["shifted_out"] == 0
    assert none_left["axis"]["excluded"] == 0
    assert none_left["pagination"]["total"] == 0


# --------------------------------------------------------------------------
# 14. 건별 검색이 구매자명도 본다 (R5a, 2026-09-03)
# --------------------------------------------------------------------------
def test_case_search_matches_purchaser_name(client, app):
    """``q`` 가 주문번호·상품주문번호에 더해 **구매자명**도 본다(회계팀이 이름으로 찾는다)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _case(day, product_order_id="2026090300021", purchaser_name="김라홈")
    _case(day, product_order_id="2026090300022", purchaser_name="이가구")
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))

    found = _data(_get(client, q="김라홈"))["ledger"]
    assert found["pagination"]["total"] == 1
    assert found["rows"][0]["purchaser_name"] == "김라홈"
    # 부분 일치도 같은 규칙이다(ilike '%..%').
    assert _data(_get(client, q="라홈"))["ledger"]["pagination"]["total"] == 1


def test_case_search_by_purchaser_name_has_a_negative_control(client, app):
    """음성 대조군 — 없는 이름은 0건이고, 기존 주문번호 검색은 그대로 동작한다.

    검색 필드를 늘리다 술어를 ``or_`` 로 헐겁게 만들면 아무 이름이나 전량을 돌려준다.
    """
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _case(day, product_order_id="2026090300031", purchaser_name="김라홈")
    _case(day, product_order_id="2026090300032", purchaser_name="이가구")
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))

    assert _data(_get(client, q="박없음"))["ledger"]["pagination"]["total"] == 0
    by_order = _data(_get(client, q="2026090300032"))["ledger"]
    assert by_order["pagination"]["total"] == 1
    assert by_order["rows"][0]["purchaser_name"] == "이가구"


def test_export_complete_axis_matches_the_screen_row_set(client, app):
    """CSV 도 화면 표와 같은 축 규칙: 완료일 축 파일엔 완료일 있는 행만 실린다(예정일 축은 전부)."""
    today = get_today_kst()
    day = _seed_basic(today)
    done_day = day - datetime.timedelta(days=2)
    _case(day, product_order_id="2026090100042", settle_complete_date=done_day)
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    window = f"from={(day - datetime.timedelta(days=5)).isoformat()}&to={today.isoformat()}"

    def lines(basis: str) -> int:
        resp = client.get(f"/api/settlement/channel/export.csv?kind=settle_case&{window}&basis={basis}")
        assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
        text = resp.get_data(as_text=True).lstrip("﻿")
        return len([row for row in text.splitlines() if row.strip()]) - 1   # 머리줄 제외

    assert lines("expect") == 3
    assert lines("complete") == 1


def test_sync_rejects_backfill_older_than_the_floor_and_future(client, app, monkeypatch):
    """백필 시작일은 오늘-400일 ~ 오늘 사이여야 한다 — 그 밖은 400 으로 막고 큐에 넣지 않는다."""
    calls: list = []
    import foms.api.cs.settlement_channel as api_mod
    monkeypatch.setattr(api_mod, "_enqueue", lambda actor_user_id, backfill_from: calls.append(backfill_from) or True)
    _login(client, _make_user(role="ADMIN"))
    today = get_today_kst()
    too_old = (today - datetime.timedelta(days=401)).isoformat()
    edge = (today - datetime.timedelta(days=400)).isoformat()
    future = (today + datetime.timedelta(days=1)).isoformat()

    resp = client.post(API_URL + "/sync", json={"backfill_from": too_old})
    assert resp.status_code == 400 and "400일" in (resp.get_json()["error"] or "")
    resp = client.post(API_URL + "/sync", json={"backfill_from": future})
    assert resp.status_code == 400
    resp = client.post(API_URL + "/sync", json={"backfill_from": edge})
    assert resp.status_code == 200 and resp.get_json()["data"]["queued"] is True
    assert calls == [edge]
