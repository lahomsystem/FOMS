"""정산 실무 탭 — 주문 **행 단위** 목록 (SETTLE-TABS S6).

집계 커널(`settlement_aggregation`)이 버킷만 내는 것과 달리, 이 모듈은 경리·수금 담당이
한 건씩 회수 작업을 하는 화면에 **주문 한 줄**을 낸다. 스펙 개정 A(§13)로 허용된 표면이다.

**노출 필드 계약(§13.3-1)**: 고객 **성명 + 주문번호**까지만 낸다.
연락처·주소·현금영수증 요청 자유텍스트 **원문은 절대 내지 않는다** — 현금영수증은 파생된
상태 코드(`issued`/`requested`/`none`)만 낸다. 원문에는 실무상 전화·사업자번호가 들어간다.

**파생 SSOT 재사용(§13.3-5)**: 출고가·예약금·잔금·과입금·현금영수증·정산 판정을 여기서
새로 만들지 않는다. 완료 대시보드와 집계 커널이 쓰는 **같은 헬퍼**를 그대로 부른다.
같은 주문의 잔금이 화면마다 갈리는 것을 막는 유일한 방법이다.

**네이버 정산 상태(v1.1 T13)**: ``include_naver_settlement=True`` 로 부를 때만 행에
``naver_settlement`` **키가 생긴다**. 이 표면은 정산 대시보드 권한(CS·영업 포함)으로
열려 있으므로, 회계 전용 정보를 내려보내고 화면에서 감추면 개발자 도구로 그대로 보인다
— 그래서 **서버가 키 자체를 만들지 않는다**. 상태는 코드(``SETTLED``/``PENDING``/
``UNMATCHED``)로만 내고 화면 문구는 프론트가 정한다.

**캡 없음(§13.3-2)**: 모집단 전량(운영 ERP 1,978건)을 읽고 파이썬에서 좁힌다. 완료
대시보드처럼 캡으로 먼저 자른 뒤 좁히면 특정 구간이 통째로 빈다. 규모가 커지면 캡이
아니라 모집단 술어를 SQL 로 내려야 한다.

순서 주의: `foms.services.orders.*` 를 `erp_display` 보다 먼저 둔다(집계 커널과 같은
순환 회피 — 그 파일 상단 주석 참조).
"""

from __future__ import annotations

import datetime
import math
from typing import Any, Sequence

from sqlalchemy import func

from foms.services.orders.erp_policy_constants import (
    ORDER_SETTLEMENT_ALERT_TARGET_STATUSES,
)
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_display import (
    _ensure_dict,
    erp_deposit_amount_from_structured,
    erp_shipping_price_from_structured,
)
from foms.services.estimate_service import (
    _balance_after_payments,
    _overpaid_after_payments,
)
from foms.services.settlement_aggregation import (
    AGING_BUCKETS,
    aging_bucket,
    completion_day_key,
)
from foms.web.cs.completion_dashboard import (
    _cash_receipt_issued,
    _cash_receipt_state,
)
from models import ExternalOrderLink, NaverSettleCase, Order

__all__ = [
    "CHANNEL_LABELS",
    "NAVER_SETTLE_PENDING",
    "NAVER_SETTLE_SETTLED",
    "NAVER_SETTLE_UNMATCHED",
    "PERIOD_FILTERS",
    "PER_PAGE",
    "SETTLEMENT_FILTERS",
    "list_settlement_rows",
]

PER_PAGE = 60           # 완료 대시보드 태블릿 그리드 `_paginate` 와 같은 크기.
_DEFAULT_CHANNEL = "일반"

#: 네이버 채널 코드. `ExternalOrderLink.channel` 과 `NaverSettleCase.channel` 이 같은 값을 쓴다.
_NAVER_CHANNEL = "NAVER"

#: 네이버 정산 칸의 상태 코드. **코드만 낸다** — 화면 문구는 프론트가 정한다(§4.2 어휘 제약).
NAVER_SETTLE_SETTLED = "SETTLED"
NAVER_SETTLE_PENDING = "PENDING"
NAVER_SETTLE_UNMATCHED = "UNMATCHED"

# 채널 코드 → 화면 라벨. `ExternalOrderLink.channel` 은 대문자 코드("NAVER")를 담는다 —
# 코드를 그대로 화면에 내면 "NAVER" 로 뜬다(v1 요약 탭의 기존 결함과 같은 원인).
CHANNEL_LABELS: dict[str, str] = {"NAVER": "네이버"}

# 기간 칩 = **완료 후 경과일** 기준이다(완료 대시보드의 `period=완료월` 과 다른 축).
PERIOD_FILTERS: tuple[str, ...] = ("all", "7", "30", "31")
SETTLEMENT_FILTERS: tuple[str, ...] = ("all", "pending", "issued")
_AGING_CODES: tuple[str, ...] = tuple(code for code, _ in AGING_BUCKETS)
_AGING_LABELS: dict[str, str] = dict(AGING_BUCKETS)


def _population_filters() -> tuple:
    """모집단 3조건 — 집계 커널·완료 대시보드와 **정확히 동일**해야 한다.

    Returns:
        SQLAlchemy 필터 튜플.
    """
    return (
        Order.active_filter(),
        Order.is_erp_order.is_(True),
        Order.status.in_(ORDER_SETTLEMENT_ALERT_TARGET_STATUSES),
    )


def _channel_map(db: Any) -> dict[int, str]:
    """주문별 외부 판매채널 코드(배치 1회, N+1 없음).

    주 쿼리에 조인하지 않는다 — 한 주문에 링크가 여럿(ADDON/REPAY) 붙으면 조인이 행을
    복제해 같은 주문이 목록에 두 번 뜬다. 링크가 여럿이면 가장 먼저 만들어진 것을 쓴다.

    Args:
        db: SQLAlchemy Session.

    Returns:
        {order_id: 채널코드}. 링크 없는 주문은 키가 없다.
    """
    rows = (
        db.query(ExternalOrderLink.order_id, ExternalOrderLink.channel)
        .join(Order, ExternalOrderLink.order_id == Order.id)
        .filter(*_population_filters())
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    mapping: dict[int, str] = {}
    for order_id, channel in rows:
        if order_id is None:
            continue
        mapping.setdefault(int(order_id), str(channel or "").strip() or _DEFAULT_CHANNEL)
    return mapping


def _iso_or_none(value: Any) -> str | None:
    """`Date` 컬럼 값을 ISO 문자열로. 값이 없으면 None.

    Args:
        value: `datetime.date` 또는 None(드라이버에 따라 문자열이 올 수도 있다).

    Returns:
        "YYYY-MM-DD" 또는 None.
    """
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _naver_settle_map(db: Any, order_ids: Sequence[int]) -> dict[int, dict]:
    """주문별 네이버 정산 상태(**쿼리 1회** group by, N+1 없음).

    **판정 우선순위(SSOT)** — 한 주문에 정산 행이 여럿 붙는다(상품주문 단위 + 취소·환급
    행). 그래서 행 하나가 아니라 묶음으로 판정한다:

    1. 완료일(``settle_complete_date``)이 있는 행이 **하나라도** 있으면 ``SETTLED``.
       표시 날짜는 그 중 **가장 최근 완료일**(``max``) — 분할 정산에서 마지막으로 돈이
       들어온 날이 실무자가 찾는 값이다.
    2. 완료일이 전부 없으면 ``PENDING``. 표시 날짜는 **가장 이른 예정일**(``min``) —
       다음에 들어올 돈이 언제인지가 회수 판단의 기준이다. 예정일도 전부 없으면 None
       (상태는 그대로 ``PENDING``: "행은 붙었는데 날짜를 아직 못 받았다"가 사실이다).
    3. 이 map 에 **키가 없다** = 붙은 정산 행 0건. 미매칭/해당없음 판정은 채널을 아는
       :func:`_naver_settlement_cell` 이 한다(이 함수는 채널을 모른다).

    ``amount`` 는 ``settle_expect_amount`` 의 **원값 합**이다. 부호를 그대로 더할 뿐
    재계산하지 않는다(v1 워터폴 부호 사고 재발 금지) — 취소·환급 행이 음수로 들어와
    상계된 결과가 곧 그 주문의 정산 총액이다. 컬럼은 ``NUMERIC(16,2)`` 지만 원 단위에
    소수가 없어 ``int`` 로 낸다(다른 금액 필드와 같은 직렬화 규약).

    Args:
        db: SQLAlchemy Session.
        order_ids: 모집단 주문 id. 빈 시퀀스면 **쿼리를 아예 걸지 않는다**.

    Returns:
        {order_id: {"status", "settle_expect_date", "settle_complete_date", "amount"}}.
        정산 행이 없는 주문은 키 자체가 없다.
    """
    ids = [int(order_id) for order_id in order_ids]
    if not ids:
        return {}

    rows = (
        db.query(
            NaverSettleCase.foms_order_id,
            func.max(NaverSettleCase.settle_complete_date),
            func.min(NaverSettleCase.settle_expect_date),
            func.sum(NaverSettleCase.settle_expect_amount),
        )
        .filter(
            NaverSettleCase.channel == _NAVER_CHANNEL,
            NaverSettleCase.foms_order_id.in_(ids),
        )
        .group_by(NaverSettleCase.foms_order_id)
        .all()
    )

    mapping: dict[int, dict] = {}
    for order_id, complete_date, expect_date, amount in rows:
        if order_id is None:
            continue
        settled = complete_date is not None
        mapping[int(order_id)] = {
            "status": NAVER_SETTLE_SETTLED if settled else NAVER_SETTLE_PENDING,
            "settle_expect_date": _iso_or_none(expect_date),
            "settle_complete_date": _iso_or_none(complete_date),
            "amount": None if amount is None else int(amount),
        }
    return mapping


def _naver_settlement_cell(channel: str, entry: dict | None) -> dict | None:
    """행의 "네이버 정산" 칸 값(신규 쿼리 없음).

    Args:
        channel: 행의 채널 코드.
        entry: :func:`_naver_settle_map` 에서 이 주문에 걸린 값(없으면 None).

    Returns:
        네이버 주문이 아니면 **None**(화면은 '—'). 네이버인데 붙은 정산 행이 0건이면
        ``UNMATCHED``. 그 밖에는 map 이 판정한 dict 그대로.
    """
    if channel != _NAVER_CHANNEL:
        return None
    if entry is None:
        return {
            "status": NAVER_SETTLE_UNMATCHED,
            "settle_expect_date": None,
            "settle_complete_date": None,
            "amount": None,
        }
    return entry


def _customer_name(sd: dict, order: Any) -> str:
    """표시용 고객명 — 완료 대시보드 `_completion_row` 와 같은 우선순위.

    ERP 주문은 sd 가 정본이고 flat 컬럼은 그 투영이라 sd 를 먼저 본다.

    Args:
        sd: `_ensure_dict` 를 통과한 structured_data.
        order: id/customer_name 이 실린 결과 행.

    Returns:
        고객명. 어느 쪽에도 없으면 "-".
    """
    parties = sd.get("parties")
    if isinstance(parties, dict):
        customer = parties.get("customer")
        if isinstance(customer, dict):
            name = str(customer.get("name") or "").strip()
            if name:
                return name
    return str(getattr(order, "customer_name", "") or "").strip() or "-"


def _elapsed_days(day_key: str, today: datetime.date) -> int | None:
    """완료일로부터 경과한 일수. 완료일 미상이면 None.

    Args:
        day_key: "YYYY-MM-DD" 완료 일 키(빈 문자열이면 미상).
        today: 기준일(KST).

    Returns:
        경과일 또는 None.
    """
    if not day_key:
        return None
    try:
        completed = datetime.date.fromisoformat(day_key)
    except ValueError:
        return None
    return (today - completed).days


def _settlement_row(
    order: Any,
    channel: str,
    today: datetime.date,
    *,
    include_naver_settlement: bool = False,
    naver_settle: dict | None = None,
) -> dict:
    """모집단 1행 → 화면 행 dict(신규 쿼리 없음).

    Args:
        order: id/status/customer_name/structured_data 가 실린 결과 행.
        channel: 채널 코드 또는 "일반".
        today: 기준일(KST).
        include_naver_settlement: True 일 때만 ``naver_settlement`` **키를 만든다**.
            False 면 키 자체가 없다 — 회계 권한이 없는 actor 에게는 값을 내려보내고
            감추는 것이 아니라 아예 만들지 않는다(클라 숨김 금지 원칙).
        naver_settle: :func:`_naver_settle_map` 에서 이 주문에 걸린 값(없으면 None).

    Returns:
        노출 계약을 지킨 행 dict. 연락처·주소·현금영수증 원문은 키 자체가 없다.
    """
    sd = _ensure_dict(order.structured_data)
    schedule = sd.get("schedule") or {}
    construction = schedule.get("construction") if isinstance(schedule, dict) else None
    completion_raw = construction.get("date") if isinstance(construction, dict) else None
    day_key = completion_day_key(completion_raw)

    payment = sd.get("payment")
    payment = payment if isinstance(payment, dict) else {}
    settlement = sd.get("settlement")
    issued = _cash_receipt_issued(settlement)
    cash_receipt_text = str(payment.get("cash_receipt") or "").strip()

    shipping_price = erp_shipping_price_from_structured(sd)
    deposit = erp_deposit_amount_from_structured(sd)
    balance = (
        None if shipping_price is None
        else _balance_after_payments(shipping_price, deposit or 0)
    )
    # 잔금은 0 에서 잘린다 — 넘친 금액을 따로 내지 않으면 "돌려줄 돈이 있다"는 사실이
    # 화면에서 사라진다(CEO L-1). 목업에 칸이 없어도 이 값은 반드시 낸다.
    overpaid = (
        0 if shipping_price is None
        else _overpaid_after_payments(shipping_price, deposit or 0)
    )
    paid = bool(payment.get("balance_confirmed"))
    elapsed = _elapsed_days(day_key, today)
    receivable = (not paid) and isinstance(balance, int) and balance > 0
    aging_code = aging_bucket(elapsed) if (receivable and elapsed is not None) else ""

    row = {
        "order_id": int(order.id),
        "customer_name": _customer_name(sd, order),
        "status": order.status,
        "channel": channel,
        "channel_label": CHANNEL_LABELS.get(channel, channel),
        "completion_date": day_key,
        "shipping_price": shipping_price,
        "deposit": deposit,
        "deposit_confirmed": bool(payment.get("deposit_confirmed")),
        "balance": balance,
        "overpaid": overpaid,
        "paid": paid,
        "receivable": receivable,
        "elapsed_days": elapsed,
        "aging": aging_code,
        "aging_label": _AGING_LABELS.get(aging_code, ""),
        # 요청 자유텍스트 원문은 내지 않는다 — 파생 상태 코드만.
        "cash_receipt_state": _cash_receipt_state(cash_receipt_text, issued),
        "settlement_issued": bool(
            isinstance(settlement, dict) and settlement.get("deductions")
        ),
    }
    if include_naver_settlement:
        row["naver_settlement"] = _naver_settlement_cell(channel, naver_settle)
    return row


def _load_rows(
    db: Any,
    today: datetime.date,
    *,
    include_naver_settlement: bool = False,
) -> list[dict]:
    """모집단 전량을 화면 행으로 읽는다(날짜 술어 없음, 캡 없음).

    쿼리 수는 **2회**(채널 링크 + 주문)이고, ``include_naver_settlement`` 가 True 일 때만
    정산 역조회 **1회**가 더해진다(총 3회). 루프 안에서는 어떤 조회도 하지 않는다.

    Args:
        db: SQLAlchemy Session.
        today: 기준일(KST).
        include_naver_settlement: True 면 행마다 ``naver_settlement`` 키를 만든다.

    Returns:
        행 dict 리스트.
    """
    channels = _channel_map(db)
    orders = (
        db.query(Order.id, Order.status, Order.customer_name, Order.structured_data)
        .filter(*_population_filters())
        .all()
    )
    settle_map: dict[int, dict] = {}
    if include_naver_settlement:
        settle_map = _naver_settle_map(db, [int(order.id) for order in orders])
    return [
        _settlement_row(
            order,
            channels.get(int(order.id), _DEFAULT_CHANNEL),
            today,
            include_naver_settlement=include_naver_settlement,
            naver_settle=settle_map.get(int(order.id)),
        )
        for order in orders
    ]


def _matches_period(row: dict, period: str) -> bool:
    """기간 칩(경과일 기준) 판정. 완료일 미상은 '전체'에서만 보인다."""
    if period == "all":
        return True
    elapsed = row["elapsed_days"]
    if elapsed is None:
        return False
    if period == "7":
        return elapsed <= 7
    if period == "30":
        return elapsed <= 30
    return elapsed >= 31


def _matches_filters(row: dict, period: str, settlement: str, channel: str,
                     aging: str) -> bool:
    """행이 현재 필터 조합을 통과하는지 판정한다.

    Args:
        row: `_settlement_row` 결과.
        period: PERIOD_FILTERS 중 하나.
        settlement: SETTLEMENT_FILTERS 중 하나.
        channel: 채널 코드 또는 "all".
        aging: aging 버킷 코드 또는 "".

    Returns:
        통과하면 True.
    """
    if not _matches_period(row, period):
        return False
    if settlement == "pending" and row["settlement_issued"]:
        return False
    if settlement == "issued" and not row["settlement_issued"]:
        return False
    if channel != "all" and row["channel"] != channel:
        return False
    if aging and row["aging"] != aging:
        return False
    return True


def _sort_key(row: dict) -> tuple:
    """**미수 먼저**, 그 안에서 경과일 오래된 순. 완료일 미상은 각 묶음의 맨 뒤.

    목업은 "경과일 오래된 순"만 말했지만, 그대로 두면 잔금이 0 인 옛 주문(회수할 돈이
    없는 건)이 목록 첫 페이지를 통째로 차지한다 — 스테이징 실화면에서 1,263일 전 0원
    주문부터 나왔다. 이 화면의 목적은 회수라서 **받을 돈이 있는 건**이 위에 와야 한다.
    묶음 안의 정렬은 목업 그대로다.

    Args:
        row: ``_settlement_row`` 결과.

    Returns:
        정렬 키 튜플(오름차순 정렬에 그대로 쓴다).
    """
    elapsed = row["elapsed_days"]
    return (
        0 if row["receivable"] else 1,          # 미수 먼저
        0 if elapsed is not None else 1,        # 완료일 미상은 묶음 뒤로
        -(elapsed or 0),                        # 오래 밀린 순
        -row["order_id"],                       # 안정화
    )


def _aging_summary(scoped_rows: list[dict]) -> list[dict]:
    """스코프 안의 aging 버킷별 미수 건수·잔금합.

    **입력은 aging 필터를 걸기 전 행**이다(기간·정산상태·채널만 통과한 행). 막대를 눌러
    목록을 좁혀도 막대 값은 그대로여야 하기 때문이다 — 고른 구간까지 반영하면 그 구간만
    남고 나머지 막대가 0 으로 무너진다.

    화면이 예전에 구간마다 ``aging=<code>`` 로 한 번씩 물어 얻던 값과 **정의상 같다**:
    그 호출의 ``total_count`` 는 같은 스코프에서 해당 코드 행의 수이고 ``totals.balance``
    는 그 행들의 잔금합이다. 여기서는 이미 읽은 모집단을 한 번 훑어 같은 값을 만든다
    (요청 6회 → 1회. 2026-08-31 운영 실측: 전량 스캔 1회당 서버 약 210ms).

    Args:
        scoped_rows: ``_matches_filters`` 를 aging="" 로 통과한 행들.

    Returns:
        ``AGING_BUCKETS`` 순서대로 ``{code,label,count,amount}`` 5개. 값이 0 인 구간도
        생략하지 않는다(화면이 "구간이 비었다"를 직접 말해야 한다).
    """
    counts = {code: 0 for code in _AGING_CODES}
    amounts = {code: 0 for code in _AGING_CODES}
    for row in scoped_rows:
        code = row["aging"]
        if code not in counts:
            continue                       # 미수가 아니거나 완료일 미상 — 어느 버킷도 아니다
        counts[code] += 1
        balance = row["balance"]
        if isinstance(balance, int):
            amounts[code] += balance
    return [
        {
            "code": code,
            "label": _AGING_LABELS[code],
            "count": counts[code],
            "amount": amounts[code],
        }
        for code in _AGING_CODES
    ]


def _totals(rows: list[dict]) -> dict:
    """필터 적용 후 행들의 금액 합. `None`(금액 미상)은 합산에서 뺀다."""
    def _sum(field: str) -> int:
        return sum(r[field] for r in rows if isinstance(r[field], int))

    return {
        "shipping_price": _sum("shipping_price"),
        "deposit": _sum("deposit"),
        "balance": _sum("balance"),
        "overpaid": _sum("overpaid"),
        "receivable_count": sum(1 for r in rows if r["receivable"]),
        "unknown_completion_count": sum(1 for r in rows if not r["completion_date"]),
    }


def list_settlement_rows(
    db: Any,
    *,
    period: str = "all",
    settlement: str = "all",
    channel: str = "all",
    aging: str = "",
    page: int = 1,
    per_page: int = PER_PAGE,
    include_naver_settlement: bool = False,
) -> dict:
    """정산 실무 탭의 주문 행 목록(필터·정렬·페이지네이션 적용).

    Args:
        db: SQLAlchemy Session.
        period: "all" | "7" | "30" | "31" — **완료 후 경과일** 기준.
        settlement: "all" | "pending" | "issued".
        channel: "all" 또는 채널 코드("NAVER" 등) 또는 "일반".
        aging: aging 버킷 코드("D91_PLUS" 등) 또는 "".
        page: 1부터.
        per_page: 페이지 크기(상한 PER_PAGE).
        include_naver_settlement: 채널 정산 열람 권한자에게만 True 로 준다. True 일 때만
            행에 ``naver_settlement`` 키가 **생긴다**(기본 False = 키 부재). 판정은 이
            모듈이 하지 않는다 — 라우트가
            :func:`foms.services.settlement_channel_access.can_view_channel_settlement`
            으로 판정해 넘긴다.

    Returns:
        rows/page/per_page/total_count/total_pages/totals/filters/aging_options/
        **aging_summary**/as_of 를 가진 dict. ``aging_summary`` 는 aging 선택과 무관한
        스코프 기준 구간 합계라, 화면이 구간마다 따로 묻지 않는다.

    Raises:
        ValueError: 필터 값이 허용 집합 밖일 때.
    """
    if period not in PERIOD_FILTERS:
        raise ValueError(f"period 는 {'|'.join(PERIOD_FILTERS)} 중 하나여야 합니다: {period!r}")
    if settlement not in SETTLEMENT_FILTERS:
        raise ValueError(
            f"settlement 는 {'|'.join(SETTLEMENT_FILTERS)} 중 하나여야 합니다: {settlement!r}"
        )
    if aging and aging not in _AGING_CODES:
        raise ValueError(f"aging 은 {'|'.join(_AGING_CODES)} 중 하나여야 합니다: {aging!r}")

    today = get_today_kst()
    all_rows = _load_rows(db, today, include_naver_settlement=include_naver_settlement)
    # 2단으로 좁힌다: 스코프(기간·정산상태·채널)까지가 aging 막대의 모집단이고, 거기서
    # 고른 구간을 더 좁힌 것이 목록이다. 한 번 읽은 모집단으로 둘 다 낸다.
    scoped = [
        row for row in all_rows
        if _matches_filters(row, period, settlement, channel, "")
    ]
    matched = [row for row in scoped if not aging or row["aging"] == aging]
    matched.sort(key=_sort_key)

    per_page = max(1, min(int(per_page or PER_PAGE), PER_PAGE))
    total_count = len(matched)
    total_pages = max(1, math.ceil(total_count / per_page))
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * per_page

    return {
        "rows": matched[start:start + per_page],
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "totals": _totals(matched),
        "filters": {
            "period": period,
            "settlement": settlement,
            "channel": channel,
            "aging": aging,
        },
        "aging_options": [
            {"code": code, "label": label} for code, label in AGING_BUCKETS
        ],
        "aging_summary": _aging_summary(scoped),
        "as_of": today.isoformat(),
    }
