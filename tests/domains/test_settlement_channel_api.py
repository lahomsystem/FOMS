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
from typing import Any, Callable

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.services.audit_message_display import ACTION_LABELS
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services import settlement_channel as kernel
from foms.services.settlement_channel import mask_account_no
from models import (
    ExternalOrderLink,
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverSettleSyncRun,
    NaverVatCase,
    NaverVatDaily,
    SecurityLog,
    SystemSetting,
)

# 권한 매트릭스 SSOT 재사용(복제 금지 — 두 파일이 각자 하드코딩하면 한쪽만 갱신된다).
from tests.domains.test_auth_finance import _login, _make_user  # noqa: E402
# D-03 매칭 주문 시드 — 실제 Order 행을 만든다(없는 FK id 금지 규율, rows API 테스트와 같은 헬퍼).
from tests.domains.test_settlement_aggregation import _money, _seed_order  # noqa: E402

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
    # CFO 후속(2026-09-05) D-02: 상한 전 모집단(kind 별 + total)과 갈래별 상한.
    "exception_totals", "exception_cap",
}

_SYNC_KEYS = {
    "last_run_at", "last_ok_at", "status", "coverage_from", "coverage_to",
    "rolling_days", "final_before", "vat_available_to", "rev", "stale", "never",
    # CFO 후속 2차(2026-09-06) F-01·F-08: 임계값을 서버가 내리고, 실패를 stale 과 다른 사실로 낸다.
    "stale_after_hours", "last_error", "failed",
}

_KPI_SCALARS = {
    "settled_amount", "expected_amount", "expected_account_amount",
    "expected_charge_amount", "commission_total", "commission_rate",
    "holdback_amount", "match_rate", "unmatched_count", "case_count",
    "unmatched_pending_count", "unmatched_unlinked_count",
    # CFO 후속(2026-09-05) D-01·A-03: 미매칭 금액·완료분·경과 5구간(dict)·입금 방식 미정 몫.
    # 이 집합은 "kpi 키 집합"이라 dict 인 unmatched_aging 도 여기 등재한다.
    "unmatched_amount", "unmatched_settled_amount", "unmatched_aging",
    "expected_unassigned_amount",
}

#: ``exception_totals`` 의 고정 9종(커널 ``_EXCEPTION_KINDS`` 와 같은 값 — 갈리면 화면이 kind 를 놓친다).
#: ``SYNC_FAILED`` 는 CFO 후속 2차(2026-09-06) F-04 — 최신 동기화 실행이 FAILED 면 1행.
#: ``AMOUNT_DIFF`` 는 CFO 후속 3차(2026-09-06) D-03 — 매칭 주문의 Σpay_settle_amount ≠ 출고가면 주문당 1행
#: (대시보드만 — 스트립은 세지 않는다). ``_case`` 시드는 ``foms_order_id`` 가 None 이라 이 kind 를 만들지 않는다.
_EXCEPTION_KINDS = ("UNMATCHED", "UNLINKED", "HOLDBACK", "LIMIT", "NEGATIVE", "RETRO",
                    "COUNT_MISMATCH", "SYNC_FAILED", "AMOUNT_DIFF")

#: ``holdback`` 블록 키(CFO 후속 2차 B-02: 창 안 부호별 합 ``window`` + 적재 전 기간 누적 잔액 ``balance``).
_HOLDBACK_KEYS = {"rows", "count", "total", "window", "balance"}
#: 보류 금액 3키 모양 — ``total``·``window.*``·``balance.*`` 가 전부 같은 모양이다.
_HOLDBACK_SIDE_KEYS = {"pay_holdback", "settlement_limit", "amount"}

#: ``kpi.unmatched_aging`` 의 고정 5구간.
_AGING_KEYS = {"lt30", "d30_59", "d60_89", "d90_plus", "future"}

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


def _sync_run(status: str, *, started_at: datetime.datetime | None = None,
              error: str | None = None, stats: dict | None = None,
              trigger: str = "SCHEDULE") -> int:
    """동기화 실행 이력 1행을 심고 id 를 돌려준다(요청 뒤엔 인스턴스가 detach 되므로 id 만).

    ``scope`` 는 NOT NULL JSON 이라 dict 를 넣는다(PG 레인에서 None 은 거절된다).
    """
    started = started_at or now_utc_naive()
    run = NaverSettleSyncRun(
        channel="NAVER", started_at=started, finished_at=started, status=status,
        trigger=trigger, actor_user_id=None,
        scope={"from": "2026-08-01", "to": "2026-09-15", "backfill_from": None,
               "trigger": trigger, "channel": "NAVER"},
        stats=stats if stats is not None else {"retro_changes": []},
        error=error, dry_run=False)
    db_session.add(run)
    db_session.commit()
    return int(run.id)


def _sync_state(**value) -> None:
    """워터마크(``SystemSetting`` 한 행)를 심는다."""
    db_session.add(SystemSetting(setting_key="naver_settle_sync_state", setting_value=value))
    db_session.commit()


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
    assert set(data["range"]) == {"from", "to", "prev"}
    assert set(data["range"]["prev"]) == {"from", "to"}
    assert [step["key"] for step in data["waterfall"]] == _WATERFALL_ORDER
    assert all(set(step) == {"key", "label", "amount"} for step in data["waterfall"])
    assert set(data["ledger"]) == {"kind", "groups", "rows", "pagination", "axis", "totals"}
    assert set(data["ledger"]["totals"]) == {"count", "amount", "amount_column", "amount_label"}
    assert set(data["exception_totals"]) == set(_EXCEPTION_KINDS) | {"total"}
    assert isinstance(data["exception_cap"], int)
    # CFO 후속 2차 B-02·N-02: 보류 블록 5키(창 안 부호별 합·누적 잔액)와 버킷의 완료/예정 몫.
    assert set(data["holdback"]) == _HOLDBACK_KEYS
    assert set(data["holdback"]["total"]) == _HOLDBACK_SIDE_KEYS
    assert set(data["holdback"]["window"]) == {"held", "released", "net"}
    assert set(data["holdback"]["balance"]) == {"held", "released", "net", "since", "until"}
    for side in ("held", "released", "net"):
        assert set(data["holdback"]["window"][side]) == _HOLDBACK_SIDE_KEYS, side
        assert set(data["holdback"]["balance"][side]) == _HOLDBACK_SIDE_KEYS, side
    assert data["daily"], "기본 시드가 기본 구간 안이라 일별 버킷이 비면 안 된다"
    assert {"date", "completed", "settle_amount", "settled_amount",
            "expected_amount"} <= set(data["daily"][0])
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
    """28시간 넘게 성공하지 못했으면 ``stale`` 이 True 이고 ``never`` 는 False 다."""
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
#: 동기화 감사 행 detail 의 고정 7키(CFO 후속 2차 E-02 6키 + 3차 F-02 ``reason``).
_SYNC_DETAIL_KEYS = {"queued", "reason", "backfill_from", "channel", "job_id", "from", "to"}

#: F-02 503 본문 — API 상수·큐 docstring·JS 헤더 문구와 같은 뜻의 고정 리터럴.
_SYNC_UNAVAILABLE_MESSAGE = "지금은 동기화할 수 없습니다. 잠시 뒤 다시 시도하세요."


def _latest_sync_log() -> SecurityLog:
    """가장 최근 동기화 요청 감사 행(메시지·detail 을 함께 본다)."""
    return (db_session.query(SecurityLog)
            .filter(SecurityLog.action == "NAVER_SETTLE_SYNC_REQUEST")
            .order_by(SecurityLog.id.desc()).first())


def test_api_state_literals_equal_the_queue_constants():
    """API 가 다시 적은 3상태 리터럴은 큐 상수 ``SETTLE_ENQUEUE_*`` 와 **같은 값**이다(F-02).

    API 모듈은 rq/redis 를 조회 화면에 끌어오지 않으려고 문자열을 한 번 더 적는다. 아래 ``test_sync_*``
    는 ``enqueue_naver_settle_sync`` 를 monkeypatch 로 리터럴을 돌려주게 하므로 실제 큐 상수를 통과하지
    않는다 — 값이 갈리면 ``_SYNC_AUDIT_SUFFIX[state]`` KeyError(500·감사 행 유실)인데 그 이유를 말하는
    테스트가 이것이다(테스트 안 지역 import 라 API 모듈에 큐 의존이 생기지 않는다).
    """
    import foms.api.cs.settlement_channel as api_module
    from foms.services.jobs import queue as queue_module

    assert api_module._STATE_QUEUED == queue_module.SETTLE_ENQUEUE_QUEUED
    assert api_module._STATE_DUPLICATE == queue_module.SETTLE_ENQUEUE_DUPLICATE
    assert api_module._STATE_UNAVAILABLE == queue_module.SETTLE_ENQUEUE_UNAVAILABLE
    assert set(api_module._SYNC_AUDIT_SUFFIX) == {
        queue_module.SETTLE_ENQUEUE_QUEUED, queue_module.SETTLE_ENQUEUE_DUPLICATE,
        queue_module.SETTLE_ENQUEUE_UNAVAILABLE}


def test_sync_enqueues_and_writes_audit(client, app, monkeypatch):
    """허용 actor 의 동기화 요청은 큐에 들어가고 감사 1행을 남긴다.

    감사 detail 은 7키다(CFO 후속 2차 E-02 + 3차 F-02 ``reason``): 큐가 실제로 쓴 job id 와 요청
    시점에 계산된 실행 창 ``from``·``to`` 가 있어야 그 행이 rq 큐·실행 이력(scope) 양쪽과 대조되고,
    ``reason`` 이 있어야 큐 부재와 중복이 감사에서 구분된다.
    """
    from foms.services.jobs import queue as queue_module

    seen: dict = {}

    def _fake(actor_user_id=None, *, backfill_from=None, dry_run=False):
        seen.update({"actor": actor_user_id, "backfill_from": backfill_from})
        return "queued"

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
    assert body["success"] is True
    assert body["data"] == {"queued": True, "reason": "queued", "job_id": "naver_settle_sync"}
    assert seen == {"actor": user_id, "backfill_from": "2026-06-01"}

    logs = db_session.query(SecurityLog).filter(
        SecurityLog.action == "NAVER_SETTLE_SYNC_REQUEST").all()
    assert len(logs) == before + 1
    assert logs[-1].user_id == user_id
    detail = logs[-1].detail
    assert set(detail) == _SYNC_DETAIL_KEYS
    assert detail["queued"] is True and detail["reason"] == "queued"
    assert detail["channel"] == "NAVER"
    assert detail["backfill_from"] == "2026-06-01" == detail["from"]
    assert detail["job_id"] == "naver_settle_sync" == queue_module._SETTLE_SYNC_JOB_ID
    assert detail["to"] == (get_today_kst() + datetime.timedelta(days=14)).isoformat()


def test_sync_audit_window_defaults_to_rolling_thirty_days(client, app, monkeypatch):
    """백필 없는 요청의 감사 창은 워커 기본(오늘-30 ~ 오늘+14)이고, 큐에 안 들어갔으면 ``job_id`` 는 None.

    큐에 들어가지 않은 요청에 job id 를 적으면 "그 job 을 보라"는 거짓 단서가 된다.
    """
    from foms.services.jobs import queue as queue_module

    today = get_today_kst()
    _login(client, _make_user(role="ADMIN"))

    monkeypatch.setattr(queue_module, "enqueue_naver_settle_sync",
                        lambda actor_user_id=None, **_kwargs: "queued")
    assert client.post(SYNC_URL, json={}).get_json()["data"] == {
        "queued": True, "reason": "queued", "job_id": "naver_settle_sync"}
    detail = _latest_sync_log().detail
    assert detail["backfill_from"] is None
    assert detail["from"] == (today - datetime.timedelta(days=30)).isoformat()
    assert detail["to"] == (today + datetime.timedelta(days=14)).isoformat()
    assert detail["job_id"] == "naver_settle_sync"

    # 음성: 이미 대기 중(duplicate)이면 job_id 는 None — 창은 그래도 적는다.
    monkeypatch.setattr(queue_module, "enqueue_naver_settle_sync",
                        lambda actor_user_id=None, **_kwargs: "duplicate")
    assert client.post(SYNC_URL, json={}).get_json()["data"] == {
        "queued": False, "reason": "duplicate", "job_id": None}
    detail = _latest_sync_log().detail
    assert detail["queued"] is False and detail["reason"] == "duplicate"
    assert detail["job_id"] is None
    assert detail["from"] == (today - datetime.timedelta(days=30)).isoformat()


def test_sync_reports_already_queued_without_lying(client, app, monkeypatch):
    """이미 대기 중이면 200 ``queued: False``·``reason: duplicate`` 다 — 성공한 척도, 실패한 척도 하지 않는다.

    감사 메시지 꼬리 "(이미 대기 중)"은 **이 상태에만** 붙는다(F-02 — 옛 코드는 큐 부재에도 붙였다).
    """
    from foms.services.jobs import queue as queue_module

    monkeypatch.setattr(queue_module, "enqueue_naver_settle_sync",
                        lambda actor_user_id=None, **_kwargs: "duplicate")
    _login(client, _make_user(role="ADMIN"))
    resp = client.post(SYNC_URL, json={})
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["success"] is True
    assert body["data"] == {"queued": False, "reason": "duplicate", "job_id": None}
    log = _latest_sync_log()
    assert log.detail["reason"] == "duplicate" and log.detail["queued"] is False
    assert str(log.message).endswith("(이미 대기 중)")


def test_sync_unavailable_is_503_with_the_fixed_message_and_audited(client, app, monkeypatch):
    """큐 부재·Redis 장애·enqueue 실패(``unavailable``)는 **503** + 고정 문구이고, 감사 행은 그래도 남는다.

    F-02 의 요지: 옛 코드는 이 경로를 200 ``queued: False`` 로 내려 화면이 "이미 대기 중인 동기화가
    있습니다"라고 말했고 감사 행에도 "(이미 대기 중)"이 붙어, 장애 뒤 감사로 복원할 수 없었다.
    음성 대조: 메시지에 "(이미 대기 중)" 이 없어야 한다.
    """
    from foms.services.jobs import queue as queue_module

    monkeypatch.setattr(queue_module, "enqueue_naver_settle_sync",
                        lambda actor_user_id=None, **_kwargs: "unavailable")
    _login(client, _make_user(role="ADMIN"))
    before = db_session.query(SecurityLog).filter(
        SecurityLog.action == "NAVER_SETTLE_SYNC_REQUEST").count()

    resp = client.post(SYNC_URL, json={})

    assert resp.status_code == 503, resp.get_data(as_text=True)
    assert resp.get_json() == {"success": False, "data": None,
                               "error": _SYNC_UNAVAILABLE_MESSAGE}
    after = db_session.query(SecurityLog).filter(
        SecurityLog.action == "NAVER_SETTLE_SYNC_REQUEST").count()
    assert after == before + 1, "503 인데 감사 행이 남지 않았다"
    log = _latest_sync_log()
    assert set(log.detail) == _SYNC_DETAIL_KEYS
    assert log.detail["reason"] == "unavailable"
    assert log.detail["queued"] is False and log.detail["job_id"] is None
    assert str(log.message).endswith("(큐 연결 불가)")
    assert "(이미 대기 중)" not in str(log.message)


def test_sync_queue_module_import_error_is_the_same_503(client, app, monkeypatch):
    """큐 모듈 부재(ImportError 경로)도 같은 503·같은 문구다 — 같은 사실은 같은 말로 한다.

    옛 "동기화 큐가 아직 준비되지 않았습니다" 는 소스에서 사라져야 한다(문구 분기 재발 방지).
    """
    import inspect

    import foms.api.cs.settlement_channel as api_module

    monkeypatch.setattr(api_module, "_enqueue", lambda *_a, **_k: ("unavailable", None))
    _login(client, _make_user(role="ADMIN"))
    resp = client.post(SYNC_URL, json={})

    assert resp.status_code == 503
    assert resp.get_json()["error"] == _SYNC_UNAVAILABLE_MESSAGE
    assert api_module.SYNC_UNAVAILABLE_MESSAGE == _SYNC_UNAVAILABLE_MESSAGE
    assert "아직 준비되지 않았습니다" not in inspect.getsource(api_module)
    assert _latest_sync_log().detail["reason"] == "unavailable"


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
    assert set(block) == _HOLDBACK_KEYS
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
    """보류·한도가 전부 0 이면 빈 목록 + 합계 0(0 행을 채워 "보류가 있었다"로 읽히게 하지 않는다).

    창 안 부호별 합(``window``)·누적 잔액(``balance``)도 전부 0 이되 **키는 있다**(None 금지). 잔액의
    ``since``/``until`` 은 보류 행이 아니라 채널 전체 일별 행의 최소·최대 예정일이라 시드일이다.
    """
    day = _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    zero = {"pay_holdback": 0, "settlement_limit": 0, "amount": 0}
    assert data["holdback"] == {
        "rows": [], "count": 0, "total": zero,
        "window": {"held": zero, "released": zero, "net": zero},
        "balance": {"held": zero, "released": zero, "net": zero,
                    "since": day.isoformat(), "until": day.isoformat()},
    }


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


def test_axis_gap_counts_answer_both_halves_in_one_call(client, app):
    """빠진 두 몫을 한 호출이 함께 답한다 — 같은 창·같은 술어라는 것이 이 계약이다(F10 T2).

    양성: 같은 시드에서 빈 몫(결제일 없음)과 밀린 몫(결제일이 창 밖)이 **동시에** 0 이 아니다.
    두 수가 따로 조회되면 한쪽만 창 정의가 바뀌어도 계약이 조용히 통과한다.
    """
    day = _seed_pay_axis(get_today_kst())

    counts = kernel._axis_gap_counts(db_session, NaverSettleCase,
                                     NaverSettleCase.pay_date, [], "NAVER", day, day)

    assert counts == (1, 1), "빈 몫(C) 1행 · 밀린 몫(B) 1행"


def test_axis_gap_counts_narrow_with_the_screen_predicate(client, app):
    """음성 대조군 — 화면 술어로 좁히면 두 수가 함께 0 이 된다(모집단 안의 표본).

    표본은 모집단 밖이 아니다: 같은 시드에서 빈 술어로 ``(1, 1)`` 을 먼저 확인하고, 창 안에
    있는 행(A)만 남기는 검색어를 주면 같은 호출이 ``(0, 0)`` 을 답한다. 술어를 무시하는
    구현이라면 좁힌 뒤에도 ``(1, 1)`` 이 나온다.
    """
    day = _seed_pay_axis(get_today_kst())
    axis = NaverSettleCase.pay_date

    wide = kernel._axis_gap_counts(db_session, NaverSettleCase, axis, [],
                                   "NAVER", day, day)
    scope = kernel._ledger_filters(NaverSettleCase, kernel._LEDGER_SPEC["case"],
                                   {"q": "2026090300001"})
    narrow = kernel._axis_gap_counts(db_session, NaverSettleCase, axis, scope,
                                     "NAVER", day, day)

    assert wide == (1, 1), "좁히기 전에는 두 몫이 실제로 있다"
    assert narrow == (0, 0), "창 안 행(A)만 남으면 빠진 몫이 없다"


def test_axis_gap_counts_replaced_the_two_count_helpers():
    """두 count 헬퍼가 조건부 집계 하나로 합쳐졌다 — 되살아나면 red(F10 T2).

    빈 몫과 밀린 몫을 따로 세던 옛 ``*_by_axis`` 두 함수가 남아 있으면 창 정의가 다시 두 곳으로
    갈라진다. 옛 이름을 리터럴로 적지 않고 접미사로 훑는 이유: 통합 게이트가 소스에서 그 두
    이름 **0건**을 세는데(설계 §3 ④) 이 테스트가 스스로 그 grep 에 잡히기 때문이다. 판정
    범위는 설계가 요구한 두 이름보다 넓다(그 접미사를 쓰는 축 계수 헬퍼 전부).
    """
    assert hasattr(kernel, "_axis_gap_counts")
    survivors = sorted(name for name in vars(kernel) if name.endswith("_by_axis"))
    assert survivors == [], f"옛 축 계수 헬퍼가 남아 있다: {survivors}"


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
    # ``_enqueue`` 는 ``(state, job_id)`` 를 돌려준다(CFO 후속 2차 E-02 · 3차 F-02 3상태).
    monkeypatch.setattr(api_mod, "_enqueue",
                        lambda actor_user_id, backfill_from:
                        calls.append(backfill_from) or ("queued", "naver_settle_sync"))
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


# --------------------------------------------------------------------------
# 15. CFO 감사 후속(2026-09-05) — D-02 예외 모집단 · D-01 미매칭 금액/경과 · A-03 방식 미정 ·
#     C-02 원장 합계 · C-01 전기 구간
# --------------------------------------------------------------------------
def test_exception_totals_keep_every_kind_key_and_sum_to_total(client, app):
    """``exception_totals`` 는 7종 키가 항상 있고(0 포함) ``total`` 은 그 합이며, 상한 미만이면 kind 별
    목록 건수와 같다. ``exception_cap`` 은 갈래별 상한 50.

    보류·한도·음수·미연결(링크 없음)을 한 건씩 심는다. 음수 행의 결제 정산액이 건별 합과 어긋나므로
    COUNT_MISMATCH 도 1행 나온다(검출기가 실제로 발동하는 양성 대조군).
    """
    today = get_today_kst()
    day = _seed_basic(today)
    _daily(day, pay_holdback_amount=Decimal("50000"))
    _daily(day, settlement_limit_amount=Decimal("-70000"))
    _daily(day, settle_amount=Decimal("-250000"), pay_settle_amount=Decimal("-275000"),
           commission_settle_amount=Decimal("25000"), normal_settle_amount=Decimal("-250000"))
    _case(day, product_order_id="2026090100009", match_status="UNMATCHED")
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    totals = data["exception_totals"]
    assert set(totals) == set(_EXCEPTION_KINDS) | {"total"}
    assert all(isinstance(totals[key], int) for key in totals)
    assert totals["total"] == sum(totals[kind] for kind in _EXCEPTION_KINDS)
    assert data["exception_cap"] == 50
    listed = {kind: sum(1 for item in data["exceptions"] if item["kind"] == kind)
              for kind in _EXCEPTION_KINDS}
    assert {kind: totals[kind] for kind in _EXCEPTION_KINDS} == listed
    assert totals["UNLINKED"] == 1 and totals["UNMATCHED"] == 0
    assert totals["HOLDBACK"] == 1 and totals["LIMIT"] == 1 and totals["NEGATIVE"] == 1
    assert totals["COUNT_MISMATCH"] == 1 and totals["RETRO"] == 0
    assert totals["total"] == 5 == len(data["exceptions"])


def test_exception_totals_are_all_zero_on_empty_data(client, app):
    """음성 대조군 — 행이 없으면 7종 전부 0 이고 total 0, 목록도 빈다(키는 그대로 있다)."""
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert data["exception_totals"] == {kind: 0 for kind in _EXCEPTION_KINDS} | {"total": 0}
    assert data["exceptions"] == []


def test_unmatched_amount_and_aging_split_settled_rows_and_keep_cancel_sign(client, app):
    """미매칭 정산액 = ``settle_expect_amount`` **원값 부호합**, 완료분 따로, 경과 구간은 예정일 기준 오늘 대비.

    A: 100일 전 예정·완료(1,000,000) → ``d90_plus`` / B: 10일 전 예정·미완료·취소(−50,000) →
    ``lt30``. 절대값으로 합치면 1,050,000 이라 red. MATCHED 2행은 어느 합에도 안 들어간다.
    """
    today = get_today_kst()
    _seed_basic(today)                                     # MATCHED 2행 — 대조군
    old = today - datetime.timedelta(days=100)
    _case(old, product_order_id="2026090100051", match_status="UNMATCHED",
          settle_complete_date=old, settle_expect_amount=Decimal("1000000"))
    recent = today - datetime.timedelta(days=10)
    _case(recent, product_order_id="2026090100052", match_status="UNMATCHED",
          settle_type="NORMAL_SETTLE_AFTER_CANCEL", settle_expect_amount=Decimal("-50000"),
          pay_settle_amount=Decimal("-55000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    window = {"from": (today - datetime.timedelta(days=120)).isoformat()}
    kpi = _data(_get(client, **window))["kpi"]

    assert kpi["unmatched_count"] == 2
    assert kpi["unmatched_amount"] == 950000                # 절대값 합(1,050,000)이면 red
    assert kpi["unmatched_settled_amount"] == 1000000
    aging = kpi["unmatched_aging"]
    assert set(aging) == _AGING_KEYS
    assert aging["d90_plus"] == {"count": 1, "amount": 1000000}
    assert aging["lt30"] == {"count": 1, "amount": -50000}
    for key in ("d30_59", "d60_89", "future"):
        assert aging[key] == {"count": 0, "amount": 0}, key
    prev = kpi["prev"]
    assert prev["unmatched_amount"] == 0 and prev["unmatched_settled_amount"] == 0
    assert prev["unmatched_aging"] == {key: {"count": 0, "amount": 0} for key in _AGING_KEYS}


def test_unmatched_aging_buckets_follow_the_case_order_at_the_edges(client, app):
    """구간 경계: 경과 0일=lt30, 29일=lt30, 30일=d30_59, 59=d30_59, 60=d60_89, 89=d60_89, 90=d90_plus,
    미래(−1일)=future. SQL CASE 의 ``>`` 경계가 파이썬 뺄셈 정의(0≤age<30 …)와 같아야 한다."""
    today = get_today_kst()
    expected = {0: "lt30", 29: "lt30", 30: "d30_59", 59: "d30_59", 60: "d60_89",
                89: "d60_89", 90: "d90_plus", -1: "future"}
    for index, age in enumerate(expected):
        _case(today - datetime.timedelta(days=age), product_order_id=f"20260901006{index:02d}",
              match_status="UNMATCHED", settle_expect_amount=Decimal(str(1000 * (index + 1))))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    window = {"from": (today - datetime.timedelta(days=100)).isoformat()}
    aging = _data(_get(client, **window))["kpi"]["unmatched_aging"]

    counts = {key: aging[key]["count"] for key in _AGING_KEYS}
    assert counts == {"lt30": 2, "d30_59": 2, "d60_89": 2, "d90_plus": 1, "future": 1}
    assert sum(aging[key]["amount"] for key in _AGING_KEYS) == sum(1000 * (i + 1) for i in range(8))


def test_expected_unassigned_amount_sums_unsettled_rows_without_a_method(client, app):
    """입금 방식이 빈 **미완료** 일별 행의 ``settle_amount`` 합. ACCOUNT 행은 제외.

    음성: 방식이 비어도 완료 행이면 0 — 그 행은 완료액이지 예정액이 아니다(창을 그 날로 좁혀 본다).
    """
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _daily(day)                                                        # ACCOUNT 미완료 — 제외
    _daily(day, settle_method_type=None, bank_type=None, account_no=None, depositor_name=None,
           settle_amount=Decimal("500000"), pay_settle_amount=Decimal("550000"),
           commission_settle_amount=Decimal("-50000"), normal_settle_amount=Decimal("500000"))
    done_day = day - datetime.timedelta(days=5)
    _daily(done_day, settle_method_type=None, settle_complete_date=done_day,
           settle_amount=Decimal("700000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))

    kpi = _data(_get(client))["kpi"]
    assert kpi["expected_unassigned_amount"] == 500000
    assert kpi["expected_account_amount"] == 1000000
    assert kpi["expected_amount"] == 1500000
    assert kpi["settled_amount"] == 700000
    assert kpi["prev"]["expected_unassigned_amount"] == 0

    narrow = _data(_get(client, **{"from": done_day.isoformat(), "to": done_day.isoformat()}))["kpi"]
    assert narrow["expected_unassigned_amount"] == 0
    assert narrow["settled_amount"] == 700000 and narrow["expected_amount"] == 0


def test_ledger_totals_follow_the_same_filter_as_the_groups(client, app):
    """``ledger.totals`` = 같은 유형·검색 술어의 건수·금액 합(그룹 합의 파이썬 덧셈), 종류별 금액 컬럼·라벨."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    ledger = _data(_get(client))["ledger"]
    assert ledger["totals"] == {"count": 2, "amount": 1300000,
                                "amount_column": "settle_expect_amount",
                                "amount_label": "정산 예정 금액"}
    assert ledger["totals"]["count"] == ledger["pagination"]["total"]
    assert ledger["totals"]["amount"] == sum(group["amount"] for group in ledger["groups"])
    typed = _data(_get(client, type="PROD_ORDER"))["ledger"]["totals"]
    assert typed["count"] == 2 and typed["amount"] == 1300000
    searched = _data(_get(client, q="2026090100002"))["ledger"]["totals"]
    assert searched["count"] == 1 and searched["amount"] == 300000
    empty = _data(_get(client, type="DELIVERY"))["ledger"]["totals"]
    assert empty == {"count": 0, "amount": 0, "amount_column": "settle_expect_amount",
                     "amount_label": "정산 예정 금액"}
    commission = _data(_get(client, ledger="commission"))["ledger"]["totals"]
    assert commission["amount_column"] == "commission_amount"
    assert commission["amount_label"] == "수수료 금액"
    vat = _data(_get(client, ledger="vat_case"))["ledger"]["totals"]
    assert vat["amount_column"] == "total_sales_amount" and vat["amount_label"] == "총매출 금액"


@pytest.mark.parametrize("granularity,date_from,date_to,expected", [
    ("month", "2026-02-01", "2026-02-28", ("2026-01-01", "2026-01-31")),
    ("month", "2026-03-01", "2026-03-31", ("2026-02-01", "2026-02-28")),
    ("month", "2026-07-01", "2026-08-31", ("2026-05-01", "2026-06-30")),
    ("month", "2026-01-01", "2026-01-31", ("2025-12-01", "2025-12-31")),   # 해 넘김
    ("month", "2026-08-06", "2026-09-19", ("2026-06-22", "2026-08-05")),   # 부분 월 — 같은 일수 규칙
    ("day", "2026-02-01", "2026-02-28", ("2026-01-04", "2026-01-31")),     # 불변
    ("week", "2026-02-01", "2026-02-28", ("2026-01-04", "2026-01-31")),    # 불변
])
def test_previous_range_uses_calendar_months_only_for_full_month_queries(
        granularity, date_from, date_to, expected):
    """전기 = ``month`` + 꽉 찬 달력 월이면 직전 같은 개월수의 달력 월, 그 밖은 같은 일수 직전 구간(감사 C-01)."""
    prev = kernel._previous_range(datetime.date.fromisoformat(date_from),
                                  datetime.date.fromisoformat(date_to), granularity)
    assert tuple(day.isoformat() for day in prev) == expected


def test_range_prev_is_echoed_and_matches_the_daily_prev_window(client, app):
    """``range.prev`` 가 응답에 실리고 ``kpi.prev``·``daily_prev`` 가 정확히 그 구간을 본다.

    1월 2일 행은 달력 전월(01-01~)에는 들어가고 같은 일수 전기(01-04~)에는 빠진다 — 두 규칙이
    다른 숫자를 내야 이 계약이 무의미하지 않다.
    """
    _daily(datetime.date(2026, 1, 2), settle_amount=Decimal("700000"))
    _daily(datetime.date(2026, 1, 20), settle_amount=Decimal("300000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    window = {"from": "2026-02-01", "to": "2026-02-28"}

    month = _data(_get(client, granularity="month", **window))
    assert month["range"] == {"from": "2026-02-01", "to": "2026-02-28",
                              "prev": {"from": "2026-01-01", "to": "2026-01-31"}}
    assert [bucket["date"] for bucket in month["daily_prev"]] == ["2026-01-01"]
    assert month["daily_prev"][0]["settle_amount"] == 1000000
    assert month["kpi"]["prev"]["expected_amount"] == 1000000

    day = _data(_get(client, granularity="day", **window))
    assert day["range"]["prev"] == {"from": "2026-01-04", "to": "2026-01-31"}
    assert day["daily_prev"][0]["date"] == "2026-01-04"
    assert day["daily_prev"][-1]["date"] == "2026-01-31"
    assert sum(bucket["settle_amount"] for bucket in day["daily_prev"]) == 300000
    assert day["kpi"]["prev"]["expected_amount"] == 300000

def test_ledger_amount_labels_cover_every_ledger_kind():
    """원장 종류마다 합계 라벨이 있다 — 종류를 하나 더 붙이고 라벨을 빠뜨리면 원장 조회가 KeyError 500 이 된다.

    `_build_ledger` 가 `_LEDGER_AMOUNT_LABELS[kind]` 를 그대로 읽으므로 두 표의 키 집합이 같아야 한다.
    """
    from foms.services.settlement_channel import _LEDGER_AMOUNT_LABELS, _LEDGER_SPEC

    assert set(_LEDGER_AMOUNT_LABELS) == set(_LEDGER_SPEC)


# --------------------------------------------------------------------------
# 16. CFO 감사 후속 2차(2026-09-06) — B-02 보류 부호별 합·누적 잔액 · CRIT-A-01 RETRO/COUNT_MISMATCH
#     검출기 계약 · F-04 SYNC_FAILED · F-01 stale 28h · F-08 failed 모드 · N-02 버킷 부분 완료 ·
#     F-06 no-store
# --------------------------------------------------------------------------
def test_holdback_window_splits_signs_and_balance_spans_all_loaded_rows(client, app):
    """``window`` 는 조회 창 안 보류(음수)·해제(양수)를 **컬럼별 부호**로 갈라 더한 합, ``balance`` 는
    적재된 전 기간의 같은 합이다(조회 창 무관).

    창 안 보류 2행(−10,000,000·−5,000,000)·해제 1행(+2,000,000), 창 밖(오늘−100일) 해제 1행
    (+3,000,000). 창 밖 해제는 ``balance`` 에만 들어간다 — 음성: ``window.released.amount`` 는
    2,000,000 그대로다. 항등식 ``window.net == total == kpi.holdback_amount``.
    """
    today = get_today_kst()
    day = _seed_basic(today)                       # 보류 0 인 두 행 — 어느 부호 합에도 안 들어간다
    far = today - datetime.timedelta(days=100)     # 기본 창(오늘-30 ~ 오늘+14) 밖
    _daily(day, pay_holdback_amount=Decimal("-10000000"))
    _daily(day - datetime.timedelta(days=1), pay_holdback_amount=Decimal("-5000000"))
    _daily(day, pay_holdback_amount=Decimal("2000000"))
    _daily(far, pay_holdback_amount=Decimal("3000000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    block = data["holdback"]
    window, balance = block["window"], block["balance"]
    assert block["count"] == 3, "창 밖 해제 행은 상세 목록에 없다"
    assert window["held"]["pay_holdback"] == -15000000
    assert window["released"]["pay_holdback"] == 2000000
    assert window["released"]["amount"] == 2000000          # 음성: 창 밖 +3,000,000 은 여기 없다
    assert window["held"]["settlement_limit"] == 0 == window["released"]["settlement_limit"]
    assert (window["net"]["amount"] == -13000000 == block["total"]["amount"]
            == data["kpi"]["holdback_amount"])
    assert window["net"]["pay_holdback"] == (window["held"]["pay_holdback"]
                                            + window["released"]["pay_holdback"])
    assert balance["held"]["pay_holdback"] == -15000000
    assert balance["released"]["pay_holdback"] == 5000000
    assert balance["net"]["amount"] == -10000000
    assert balance["since"] == far.isoformat()
    assert balance["until"] == day.isoformat()
    # 전기 KPI 블록은 불변 — window/balance 가 kpi.prev 로 새지 않는다.
    assert "window" not in data["kpi"]["prev"] and "balance" not in data["kpi"]["prev"]


@pytest.mark.parametrize("daily_pay,case_pay,diff", [
    ("1100000", "1000000", 100000),      # 일별 > 건별 → 양수
    ("1000000", "1100000", -100000),     # 건별 > 일별 → 음수(부호를 뒤집지 않는다)
])
def test_count_mismatch_exception_carries_the_signed_diff(client, app, daily_pay, case_pay, diff):
    """일별↔건별 결제 정산액이 어긋나면 COUNT_MISMATCH **정확히 1행** — 금액은 ``daily - case`` 부호
    그대로이고 ``ref`` 가 두 합을 든다(CRIT-A-01: 이 검출기에 계약이 0건이었다)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=1)
    _daily(day, pay_settle_amount=Decimal(daily_pay))
    _case(day, pay_settle_amount=Decimal(case_pay))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    rows = [item for item in data["exceptions"] if item["kind"] == "COUNT_MISMATCH"]
    assert len(rows) == 1, data["exceptions"]
    row = rows[0]
    assert row["amount"] == diff == data["reconcile"]["diff"]
    assert row["ref"] == {"daily_total": int(daily_pay), "case_total": int(case_pay)}
    assert row["label"] == "일별↔건별 합계 불일치"
    assert row["date"] is None and row["age_days"] is None   # 구간 합의 차라 날짜가 없다
    assert data["exception_totals"]["COUNT_MISMATCH"] == 1


def _retro_change(day: datetime.date, old_total: str, new_total: str) -> dict:
    """``run.stats.retro_changes`` 항목 1개 — ``settle_sync.replace_partition`` 이 남기는 모양 그대로."""
    return {"table": "naver_settle_daily", "date": day.isoformat(), "old_total": old_total,
            "new_total": new_total, "old_count": 1, "new_count": 1}


def test_retro_exceptions_come_from_the_latest_run_and_are_capped_at_fifty(client, app):
    """RETRO 는 **최신** run 의 ``stats.retro_changes`` 에서만 나오고, 목록은 50건 상한·모집단은 전부(CRIT-A-01).

    1) 1건짜리 run → RETRO 1행, 금액은 ``new_total - old_total``(부호 포함).
    2) 그 뒤 51건짜리 run → 목록 50행·``exception_totals.RETRO == 51``, 옛 run 의 1건은 사라진다.
    """
    today = get_today_kst()
    _seed_basic(today)
    _login(client, _make_user(role="ADMIN"))
    older = _retro_change(today - datetime.timedelta(days=9), "1000000.00", "900000.00")
    _sync_run("OK", started_at=now_utc_naive() - datetime.timedelta(days=1),
              stats={"retro_changes": [older]})

    data = _data(_get(client))
    retro = [item for item in data["exceptions"] if item["kind"] == "RETRO"]
    assert len(retro) == 1 and data["exception_totals"]["RETRO"] == 1
    assert retro[0]["amount"] == -100000                       # 900,000 − 1,000,000
    assert retro[0]["label"] == "소급 변경(확정 후 값 변동)"
    assert retro[0]["date"] == older["date"] and retro[0]["age_days"] == 9
    assert retro[0]["ref"] == older

    changes = [_retro_change(today - datetime.timedelta(days=index + 1), "1000000.00",
                             f"{1000000 + 1000 * (index + 1)}.00") for index in range(51)]
    _sync_run("OK", stats={"retro_changes": changes})
    data = _data(_get(client))
    retro = [item for item in data["exceptions"] if item["kind"] == "RETRO"]
    assert len(retro) == 50 == data["exception_cap"]
    assert data["exception_totals"]["RETRO"] == 51
    assert retro[0]["amount"] == 1000 and retro[0]["ref"] == changes[0]
    assert older not in [item["ref"] for item in retro], "옛 run 의 변경이 섞여 나왔다"


def test_retro_and_mismatch_are_absent_when_data_agrees(client, app):
    """음성 대조군 — 일별·건별이 일치하고 최신 run 의 ``retro_changes`` 가 비면 두 kind 는 0행·0건."""
    today = get_today_kst()
    _seed_basic(today)                       # 일별 pay 1,430,000 == 건별 pay 1,430,000
    _sync_run("OK", stats={"retro_changes": []})
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert data["reconcile"]["diff"] == 0
    assert not [item for item in data["exceptions"]
                if item["kind"] in ("RETRO", "COUNT_MISMATCH")]
    assert data["exception_totals"]["RETRO"] == 0 == data["exception_totals"]["COUNT_MISMATCH"]


def test_sync_failed_exception_when_the_latest_run_failed(client, app):
    """최신 run 이 FAILED 면 SYNC_FAILED **정확히 1행**이 목록 맨 앞에 — 화면 전체가 옛 값이라는 신호(F-04).

    금액은 없다(``amount`` None — 돈이 아니라 적재 상태). 라벨은 오류를 공백 정리해 80자로 자른 요약.
    """
    today = get_today_kst()
    day = _seed_basic(today)
    _daily(day, pay_holdback_amount=Decimal("-50000"))     # 다른 예외(HOLDBACK)보다 앞에 서야 한다
    db_session.commit()
    started = now_utc_naive() - datetime.timedelta(hours=2)
    error = "네이버 500   Internal\nServer Error " + "x" * 120
    run_id = _sync_run("FAILED", started_at=started, error=error, trigger="MANUAL")
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    failed = [item for item in data["exceptions"] if item["kind"] == "SYNC_FAILED"]
    assert len(failed) == 1 and data["exceptions"][0] == failed[0]
    row = failed[0]
    assert row["label"].startswith("동기화 실패: ") and "네이버 500" in row["label"]
    assert "\n" not in row["label"] and "   " not in row["label"]
    assert len(row["label"]) == len("동기화 실패: ") + 80
    assert row["amount"] is None and row["action_url"] is None
    assert row["date"] == started.date().isoformat()
    assert row["ref"]["run_id"] == run_id and row["ref"]["status"] == "FAILED"
    assert row["ref"]["trigger"] == "MANUAL" and row["ref"]["started_at"] == started.isoformat()
    assert row["ref"]["error"] == error
    assert data["exception_totals"]["SYNC_FAILED"] == 1
    assert data["exception_totals"]["HOLDBACK"] == 1 and data["exceptions"][1]["kind"] == "HOLDBACK"


@pytest.mark.parametrize("status", ["OK", "ABORTED_QUOTA"])
def test_ok_run_leaves_no_sync_failed_exception(client, app, status):
    """음성 — 최신 run 이 OK·ABORTED_QUOTA 면 SYNC_FAILED 0행(쿼터 중단은 실패가 아니라 정상 중단이다).

    옛 FAILED run 이 뒤에 있어도 **최신** run 만 본다.
    """
    _seed_basic(get_today_kst())
    _sync_run("FAILED", started_at=now_utc_naive() - datetime.timedelta(days=1), error="옛 실패")
    _sync_run(status, error="쿼터 제한" if status != "OK" else None)
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert not [item for item in data["exceptions"] if item["kind"] == "SYNC_FAILED"]
    assert data["exception_totals"]["SYNC_FAILED"] == 0


def test_retro_and_sync_failed_coexist_for_a_failed_run_with_committed_changes(client, app):
    """최신 run 이 FAILED 여도 ``stats.retro_changes`` 에 남은(앞 창에서 **커밋된**) 소급 변경은 RETRO 로 나온다.

    SYNC_FAILED 1행(맨 앞) + RETRO 1행 공존 — 되돌림은 미커밋 꼬리만 빼기 때문이다(F-04·리뷰 A-1/Q-01).
    음성: 되돌린 몫(``retro_changes_rolled_back``)은 RETRO 재료가 아니다.
    """
    today = get_today_kst()
    _seed_basic(today)
    committed = _retro_change(today - datetime.timedelta(days=12), "1000000.00", "1200000.00")
    rolled = _retro_change(today - datetime.timedelta(days=1), "500000.00", "700000.00")
    run_id = _sync_run("FAILED", error="창 2 에서 네이버 500",
                       stats={"retro_changes": [committed], "retro_changes_rolled_back": [rolled]})
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    kinds = [item["kind"] for item in data["exceptions"]]
    assert kinds[0] == "SYNC_FAILED" and kinds.count("SYNC_FAILED") == 1
    assert data["exceptions"][0]["ref"]["run_id"] == run_id
    retro = [item for item in data["exceptions"] if item["kind"] == "RETRO"]
    assert len(retro) == 1 and retro[0]["ref"] == committed
    assert retro[0]["amount"] == 200000                        # 1,200,000 − 1,000,000
    assert rolled not in [item["ref"] for item in retro], "되돌린 변경이 RETRO 로 나왔다"
    assert data["exception_totals"]["RETRO"] == 1 and data["exception_totals"]["SYNC_FAILED"] == 1


@pytest.mark.parametrize("hours,stale", [(27.9, False), (28.1, True)])
def test_stale_threshold_is_28_hours_at_the_boundary(client, app, hours, stale):
    """stale 임계값은 28시간(일 1회 05:30 스케줄 + 여유 4h)이고 서버가 ``stale_after_hours`` 로 내린다(F-01)."""
    stamp = (now_utc_naive() - datetime.timedelta(hours=hours)).isoformat()
    _sync_state(rev=1, last_run_at=stamp, last_ok_at=stamp, last_status="OK")
    _login(client, _make_user(role="ADMIN"))
    sync = _data(_get(client))["sync"]

    assert sync["stale"] is stale, (hours, sync)
    assert sync["stale_after_hours"] == 28 == kernel.STALE_AFTER_HOURS
    assert sync["failed"] is False and sync["last_error"] is None and sync["never"] is False


@pytest.mark.parametrize("last_ok_hours,stale", [(None, False), (40, True)])
def test_failed_without_any_ok_is_failed_not_stale(client, app, last_ok_hours, stale):
    """성공이 한 번도 없는 FAILED 는 ``failed=True``·``stale=False`` — stale 문구가 방금 난 실패를 덮지
    않는다(F-08). 대조: 성공이 있었고 그게 40시간 전이면 ``failed``·``stale`` 둘 다 True(둘 다 사실)."""
    now = now_utc_naive()
    state = {"last_run_at": (now - datetime.timedelta(hours=2)).isoformat(),
             "last_status": "FAILED", "last_error": "token expired", "rev": 3}
    if last_ok_hours is not None:
        state["last_ok_at"] = (now - datetime.timedelta(hours=last_ok_hours)).isoformat()
    _sync_state(**state)
    _login(client, _make_user(role="ADMIN"))
    sync = _data(_get(client))["sync"]

    assert sync["status"] == "FAILED" and sync["failed"] is True
    assert sync["stale"] is stale and sync["never"] is False
    assert sync["last_error"] == "token expired"


def test_daily_buckets_split_settled_and_expected_amounts(client, app):
    """월 버킷에 완료·미완료 행이 섞이면 ``completed`` 는 False 인 채로 ``settled_amount``·``expected_amount``
    가 각각의 몫을 말한다(N-02). 항등식 ``settled + expected == settle_amount``. 일 세밀도도 같은 키·규칙."""
    _daily(datetime.date(2026, 2, 3), settle_amount=Decimal("700000"),
           settle_complete_date=datetime.date(2026, 2, 3))
    _daily(datetime.date(2026, 2, 20), settle_amount=Decimal("300000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    window = {"from": "2026-02-01", "to": "2026-02-28"}

    month = _data(_get(client, granularity="month", **window))["daily"]
    assert [bucket["date"] for bucket in month] == ["2026-02-01"]
    assert month[0]["completed"] is False
    assert month[0]["settled_amount"] == 700000 and month[0]["expected_amount"] == 300000
    assert month[0]["settle_amount"] == 1000000 == (month[0]["settled_amount"]
                                                    + month[0]["expected_amount"])

    days = {bucket["date"]: bucket
            for bucket in _data(_get(client, granularity="day", **window))["daily"]}
    assert days["2026-02-03"]["completed"] is True
    assert days["2026-02-03"]["settled_amount"] == 700000
    assert days["2026-02-03"]["expected_amount"] == 0
    assert days["2026-02-20"]["completed"] is False
    assert days["2026-02-20"]["settled_amount"] == 0
    assert days["2026-02-20"]["expected_amount"] == 300000
    empty = days["2026-02-10"]                        # 빈 날: 둘 다 0, completed False(불변)
    assert empty["completed"] is False and empty["settled_amount"] == 0 == empty["expected_amount"]
    assert all(bucket["settled_amount"] + bucket["expected_amount"] == bucket["settle_amount"]
               for bucket in days.values())


def test_json_api_is_no_store(client, app):
    """탭 한 벌(full)·스트립 응답 둘 다 ``Cache-Control: no-store`` — 구매자명이 실리는 응답을 SW PII
    게이트가 이 헤더로 판정한다(F-06)."""
    _login(client, _make_user(role="ADMIN"))

    full = _get(client)
    strip = _get(client, view="strip")

    assert full.status_code == 200 and full.headers["Cache-Control"] == "no-store"
    assert strip.status_code == 200 and strip.headers["Cache-Control"] == "no-store"


# --------------------------------------------------------------------------
# 17. CFO 후속 3차(2026-09-06) D-03 — 매칭 주문의 Σ결제 정산 금액 ≠ 출고가 (AMOUNT_DIFF)
#
# 두 **원값**을 나란히 두고 "같지 않음"만 판정한다(재계산 금지 D-4 — 차액을 만들지 않는다).
# 시드는 실제 Order 행(``_seed_order``)에 ``foms_order_id`` 로 붙인다.
# --------------------------------------------------------------------------
_AMOUNT_DIFF_REF_KEYS = {"order_id", "pay_settle_total", "shipping_price", "case_count",
                         "has_cancel_row"}


def _count_queries(fn: Callable[[], Any]) -> tuple[Any, int]:
    """``fn()`` 이 도는 동안 실제로 나간 SQL 문 수를 센다.

    커널의 질의 예산 계약(대시보드·스트립)이 둘 다 이 함수 하나를 쓴다 —
    ``tests/domains/test_settlement_channel_strip.py`` 가 여기서 import 한다.
    세는 방식이 파일마다 갈리면 "예산 6" 같은 숫자가 서로 다른 뜻이 된다.

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


def _matched_order(day: datetime.date, items_total: int | None, pay: str,
                   product_order_id: str) -> int:
    """출고가 ``items_total``(None 이면 품목 미입력) 주문 1건 + 그 주문에 붙은 MATCHED 정산 1행."""
    sd = _money(items_total=items_total, deposit=0) if items_total is not None else {}
    order = _seed_order(completion="2026-08-10", sd=sd)
    _case(day, product_order_id=product_order_id, foms_order_id=order.id,
          pay_settle_amount=Decimal(pay), settle_expect_amount=Decimal(pay) - 100000)
    return int(order.id)


def _amount_diff_rows(data: dict) -> list[dict]:
    """응답 예외 목록에서 AMOUNT_DIFF 만."""
    return [item for item in data["exceptions"] if item["kind"] == "AMOUNT_DIFF"]


def test_amount_diff_flags_mismatch_and_missing_shipping_but_not_equal(client, app):
    """일치 주문은 예외가 아니고, 불일치 주문과 출고가 None(품목 미입력) 주문만 ``AMOUNT_DIFF`` 1행씩.

    라벨 ``정산액≠출고가``, ``amount`` 는 Σpay 원값(차액이 아니다), ref 는 5키 정확 일치, 출고가 None 은
    ``ref.shipping_price`` null 로 그대로 말한다(0 으로 그리지 않는다).
    """
    today = get_today_kst()
    day = today - datetime.timedelta(days=2)
    equal_id = _matched_order(day, 1_100_000, "1100000", "2026090100031")
    diff_id = _matched_order(day, 900_000, "1100000", "2026090100032")
    none_id = _matched_order(day, None, "1100000", "2026090100033")
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    rows = _amount_diff_rows(data)
    assert data["exception_totals"]["AMOUNT_DIFF"] == 2 == len(rows)
    by_order = {row["ref"]["order_id"]: row for row in rows}
    assert set(by_order) == {diff_id, none_id}, "일치 주문이 예외로 나왔거나 불일치 주문이 빠졌다"
    for row in rows:
        assert row["label"] == "정산액≠출고가"
        assert row["action_url"] == f"/erp/orders/{row['ref']['order_id']}", (
            "조치 링크가 그 주문의 편집 화면을 가리키지 않는다(행이 어느 주문인지 말해야 한다)")
        assert set(row["ref"]) == _AMOUNT_DIFF_REF_KEYS
        assert row["amount"] == 1100000 == row["ref"]["pay_settle_total"], "차액을 만들었다(D-4 위반)"
        assert row["ref"]["case_count"] == 1 and row["ref"]["has_cancel_row"] is False
        assert row["date"] == day.isoformat() and row["age_days"] == 2
    assert by_order[diff_id]["ref"]["shipping_price"] == 900_000
    assert by_order[none_id]["ref"]["shipping_price"] is None
    assert equal_id not in by_order


def test_amount_diff_is_zero_when_every_matched_order_equals_its_shipping_price(client, app):
    """음성 대조군 — 매칭 주문 전부 Σpay == 출고가면 AMOUNT_DIFF 0행·0건(키는 그대로 있다)."""
    today = get_today_kst()
    day = today - datetime.timedelta(days=2)
    _matched_order(day, 1_100_000, "1100000", "2026090100041")
    _matched_order(day, 330_000, "330000", "2026090100042")
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    assert data["exception_totals"]["AMOUNT_DIFF"] == 0
    assert _amount_diff_rows(data) == []
    assert "AMOUNT_DIFF" in data["exception_totals"]


def test_amount_diff_sums_every_row_of_the_order_not_only_the_window(client, app):
    """Σ의 범위는 **그 주문에 붙은 행 전부**(창 무관) — 창 밖 취소 행도 합에 들어간다.

    창 안 부분합(1,100,000)만 보면 출고가 1,100,000 과 같아 예외가 아니지만, 창 밖(40일 전) 취소 행
    −100,000 을 더한 실제 Σ 1,000,000 은 다르다 → 예외 1행, ``case_count`` 2, ``has_cancel_row`` True.
    실무 탭 ``_naver_settle_map`` 과 같은 정의다.
    """
    today = get_today_kst()
    day = today - datetime.timedelta(days=2)
    order_id = _matched_order(day, 1_100_000, "1100000", "2026090100051")
    _case(today - datetime.timedelta(days=40), product_order_id="2026090100052",
          foms_order_id=order_id, settle_type="NORMAL_SETTLE_AFTER_CANCEL",
          pay_settle_amount=Decimal("-100000"), settle_expect_amount=Decimal("-90000"))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    rows = _amount_diff_rows(data)
    assert len(rows) == 1 and data["exception_totals"]["AMOUNT_DIFF"] == 1
    row = rows[0]
    assert row["ref"]["order_id"] == order_id
    assert row["amount"] == 1_000_000 == row["ref"]["pay_settle_total"], "창 안 부분합만 더했다"
    assert row["ref"]["case_count"] == 2 and row["ref"]["has_cancel_row"] is True
    assert row["date"] == day.isoformat(), "주문 행의 최대 축일이 아니다"


def test_amount_diff_rows_come_last_and_respect_the_cap(client, app):
    """AMOUNT_DIFF 는 목록 **맨 뒤** 갈래이고 상한 50 이 걸린다 — 모집단은 ``exception_totals`` 가 말한다.

    51주문 불일치 + HOLDBACK 1행: 목록은 HOLDBACK 뒤 AMOUNT_DIFF 50행, totals 는 51.
    갈래 안 정렬은 (date desc, order_id desc) 로 결정적이다.
    """
    today = get_today_kst()
    day = _seed_basic(today)
    _daily(day, pay_holdback_amount=Decimal("50000"))
    order_ids = [_matched_order(day, 900_000, "1100000", f"20260901{index:05d}")
                 for index in range(200, 251)]
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))
    data = _data(_get(client))

    kinds = [item["kind"] for item in data["exceptions"]]
    assert kinds[-1] == "AMOUNT_DIFF" and kinds.count("AMOUNT_DIFF") == 50
    first_amount = kinds.index("AMOUNT_DIFF")
    assert set(kinds[first_amount:]) == {"AMOUNT_DIFF"}, "AMOUNT_DIFF 뒤에 다른 kind 가 있다"
    assert "HOLDBACK" in kinds[:first_amount]
    assert data["exception_totals"]["AMOUNT_DIFF"] == 51
    listed_ids = [item["ref"]["order_id"] for item in _amount_diff_rows(data)]
    assert listed_ids == sorted(order_ids, reverse=True)[:50]


def test_dashboard_adds_at_most_two_queries_for_amount_diff(client, app):
    """AMOUNT_DIFF 의 대가는 질의 **+2 이하**(그룹 1 + 주문 ``in_`` 배치 1) — 매칭 주문이 없으면 +1."""
    today = get_today_kst()
    day = _seed_basic(today)
    date_from, date_to = today - datetime.timedelta(days=30), today + datetime.timedelta(days=14)

    def _full() -> dict:
        return kernel.build_channel_dashboard(db_session, date_from=date_from, date_to=date_to,
                                              today=today)

    _, without = _count_queries(_full)
    _matched_order(day, 900_000, "1100000", "2026090100061")
    _matched_order(day, 1_100_000, "1100000", "2026090100062")
    db_session.commit()
    data, with_orders = _count_queries(_full)

    assert data["exception_totals"]["AMOUNT_DIFF"] == 1
    assert 0 <= with_orders - without <= 2, (without, with_orders)
