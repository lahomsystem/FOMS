"""네이버 정산 동기화 — 파티션 통째 교체로 소급 변경까지 따라간다 (SETTLE-CHANNEL-01 §4).

주문 수집(:mod:`~foms.services.integrations.naver_commerce.ingest`)과 **적재 규율이 반대**다.
주문은 ``UNIQUE (channel, external_id)`` 로 "한 번 들어온 것은 두 번 안 들어온다"를 지키지만,
정산은 네이버가 **이미 준 값을 소급해서 바꾼다**(취소·반품·보류 해제·수수료 정정). upsert 로
행을 누적하면 사라진 행이 영원히 남고, 합계가 조용히 부풀어 회계 대사가 안 맞는다.

그래서 이 모듈의 적재 단위는 **파티션(채널 + 축 날짜) 통째 교체**다: 같은 트랜잭션에서
그 날짜의 행을 지우고 방금 받은 응답을 그대로 넣는다. 멱등성은 UNIQUE 가 아니라 이 규칙이
담보한다 — 같은 날짜를 열 번 돌려도 행 수가 같다.

교체 **직전에** 그 파티션의 (행수, 금액 합)을 재어 두고 새 값과 다르면
``stats["retro_changes"]`` 에 남긴다. 이것이 "지난주 정산이 오늘 바뀌었다"를 사람이 알게
되는 유일한 경로다(화면 예외 목록의 RETRO 항목). **처음 적재(옛 행 0건)는 소급 변경이
아니다** — 그것까지 세면 첫 백필 90일이 통째로 "변경"으로 뜬다.

기타 규율:

* **금액은 재계산하지 않는다.** 네이버 숫자를 ``Decimal(str(v))`` 로 그대로 넣는다. 음수도
  부호 그대로다(정산 후 취소·빠른정산 회수는 원래 음수로 온다).
* **확정 구간은 다시 안 읽는다.** ``settle_expect_date + 30일 < 오늘`` 인 날짜는 네이버가
  더 이상 바꾸지 않는다 — 매일 다시 읽으면 호출만 태운다. 백필은 예외(그때는 다 읽는다).
* **쿼터 헤더가 오면 그 자리에서 멈춘다.** ``client.last_quota_limit_header`` 가 채워지면
  실행을 ``ABORTED_QUOTA`` 로 끝내고 **성공 구간을 전진시키지 않는다**. 실패가 아니라
  "내일 이어서 하면 되는 중단"이라 FAILED 와 갈라 둔다.
* **WORKER 프로세스 전용**이다 — 네이버 HTTP 는 등록된 IP 가 WORKER 것뿐이다. web 은
  enqueue 만 한다(:func:`foms.services.jobs.queue.enqueue_naver_settle_sync`).

규격 근거: ``docs/research/2026-09-02-naver-settlement/`` (raw/ 는 공식 문서 원문 발췌).
``settle/case``·``settle/commission-details`` 는 **기간 조회가 없다**(하루씩), ``vat/*`` 는
**전월 말일까지만** 조회된다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.backfill import CALL_INTERVAL_SECONDS
from foms.services.integrations.naver_commerce.client import DEFAULT_SETTLE_PERIOD_TYPE
from models import (
    NAVER_SETTLE_CHANNEL_DEFAULT,
    NAVER_SETTLE_RUN_TRIGGERS,
    ExternalOrderLink,
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverSettleSyncRun,
    NaverVatCase,
    NaverVatDaily,
    SystemSetting,
)

logger = logging.getLogger(__name__)

#: 정산 동기화 상태(워터마크)를 담는 ``SystemSetting`` 키. 주문 수집 워터마크
#: (``naver_sync_watermark``)·백필 상태(``naver_backfill_state``)와 **다른 행**이다.
SETTING_KEY = "naver_settle_sync_state"

#: 기본 구간: 오늘에서 이만큼 뒤로.
DEFAULT_ROLLING_DAYS = 30

#: 기본 구간: 오늘에서 이만큼 앞으로(정산 예정일은 미래 날짜로 잡힌다).
DEFAULT_FUTURE_DAYS = 14

#: 정산 예정일이 이 일수보다 과거면 네이버가 더 이상 바꾸지 않는다(확정 구간).
FINALIZED_AFTER_DAYS = 30

#: 백필을 쪼개는 창 길이(일). 한 job 안에서 순차로 돈다.
BACKFILL_WINDOW_DAYS = 30
#: ``settle/daily`` 한 번의 ``startDate``~``endDate`` 폭 상한. 네이버는 **1개월 이내**만 받는다
#: (실측 2026-09-02: 44일 창 → 400 ``LocalDatePeriod`` "시작일과 종료일은 1 달 이내여야 합니다",
#: 문서 미기재). 28일이면 2월 포함 어느 달에도 안전하다.
DAILY_RANGE_MAX_DAYS = 28

#: 부가세 확정본을 당길 수 있는 날(익월 이 날 이후). 네이버는 확정 여부를 알려주지
#: 않으므로 우리가 규칙을 정한다(설계 결정, 문서 근거 없음).
VAT_FINAL_DAY = 10

#: 페이지 순회 상한. ``totalPages`` 가 깨져 와도 무한 루프에 빠지지 않게 하는 안전판이다.
MAX_PAGES = 500

#: 매칭 조회를 나누는 크기. SQLite 의 바인딩 변수 상한(999)에 걸리지 않게 한다.
_MATCH_CHUNK = 400

#: ERP 주문에 붙일 수 있는 정산 행의 유형. 배송비·기타비용 행은 붙을 주문이 없다.
MATCHABLE_PRODUCT_ORDER_TYPE = "PROD_ORDER"

_DATE = "date"
_AMOUNT = "amount"
_TEXT = "text"


class SettleSyncQuotaAborted(RuntimeError):
    """쿼터 헤더를 만나 순회를 중단했다(실패가 아니라 정상 중단)."""


# --------------------------------------------------------------------------- #
# 필드 지도 — 네이버 원문 키(camelCase) → 컬럼(snake_case)
# 원문: docs/research/2026-09-02-naver-settlement/raw/*.md
# --------------------------------------------------------------------------- #

DAILY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("settleBasisStartDate", "settle_basis_start_date", _DATE),
    ("settleBasisEndDate", "settle_basis_end_date", _DATE),
    ("settleExpectDate", "settle_expect_date", _DATE),
    ("settleCompleteDate", "settle_complete_date", _DATE),
    ("settleAmount", "settle_amount", _AMOUNT),
    ("paySettleAmount", "pay_settle_amount", _AMOUNT),
    ("commissionSettleAmount", "commission_settle_amount", _AMOUNT),
    ("benefitSettleAmount", "benefit_settle_amount", _AMOUNT),
    ("deductionRestoreSettleAmount", "deduction_restore_settle_amount", _AMOUNT),
    ("payHoldbackAmount", "pay_holdback_amount", _AMOUNT),
    ("minusChargeAmount", "minus_charge_amount", _AMOUNT),
    ("differenceSettleAmount", "difference_settle_amount", _AMOUNT),
    ("returnCareSettleAmount", "return_care_settle_amount", _AMOUNT),
    ("normalSettleAmount", "normal_settle_amount", _AMOUNT),
    ("quickSettleAmount", "quick_settle_amount", _AMOUNT),
    ("preferentialCommissionAmount", "preferential_commission_amount", _AMOUNT),
    ("settlementLimitAmount", "settlement_limit_amount", _AMOUNT),
    ("settleMethodType", "settle_method_type", _TEXT),
    ("bankType", "bank_type", _TEXT),
    ("depositorName", "depositor_name", _TEXT),
    ("accountNo", "account_no", _TEXT),
    ("merchantId", "merchant_id", _TEXT),
    ("merchantName", "merchant_name", _TEXT),
)

CASE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("settleBasisDate", "settle_basis_date", _DATE),
    ("settleExpectDate", "settle_expect_date", _DATE),
    ("settleCompleteDate", "settle_complete_date", _DATE),
    ("payDate", "pay_date", _DATE),
    ("orderId", "order_id", _TEXT),
    ("productOrderId", "product_order_id", _TEXT),
    ("productOrderType", "product_order_type", _TEXT),
    ("settleType", "settle_type", _TEXT),
    ("productId", "product_id", _TEXT),
    ("productName", "product_name", _TEXT),
    ("purchaserName", "purchaser_name", _TEXT),
    ("paySettleAmount", "pay_settle_amount", _AMOUNT),
    ("totalPayCommissionAmount", "total_pay_commission_amount", _AMOUNT),
    ("freeInstallmentCommissionAmount", "free_installment_commission_amount", _AMOUNT),
    ("sellingInterlockCommissionAmount", "selling_interlock_commission_amount", _AMOUNT),
    ("benefitSettleAmount", "benefit_settle_amount", _AMOUNT),
    ("settleExpectAmount", "settle_expect_amount", _AMOUNT),
    ("merchantId", "merchant_id", _TEXT),
    ("merchantName", "merchant_name", _TEXT),
    ("contractNo", "contract_no", _TEXT),
)

COMMISSION_FIELDS: tuple[tuple[str, str, str], ...] = (
    # 수수료 상세만 주문번호 키가 ``orderNo`` 다(건별 정산은 ``orderId``). 원문 그대로다.
    ("orderNo", "order_no", _TEXT),
    ("productOrderId", "product_order_id", _TEXT),
    ("productOrderType", "product_order_type", _TEXT),
    ("productId", "product_id", _TEXT),
    ("productName", "product_name", _TEXT),
    ("merchantId", "merchant_id", _TEXT),
    ("merchantName", "merchant_name", _TEXT),
    ("purchaserName", "purchaser_name", _TEXT),
    ("settleType", "settle_type", _TEXT),
    ("settleBasisDate", "settle_basis_date", _DATE),
    ("settleExpectDate", "settle_expect_date", _DATE),
    ("settleCompleteDate", "settle_complete_date", _DATE),
    ("taxReturnDate", "tax_return_date", _DATE),
    ("commissionBasisAmount", "commission_basis_amount", _AMOUNT),
    ("commissionType", "commission_type", _TEXT),
    ("payMeansType", "pay_means_type", _TEXT),
    ("commissionAmount", "commission_amount", _AMOUNT),
    ("maximumSellingInterlockCommissionAmount",
     "maximum_selling_interlock_commission_amount", _AMOUNT),
)

#: 부가세 금액 8종. 원문 대소문자가 우리 규약과 어긋나는 두 개(``cashInComeDeductionAmount``·
#: ``cashOutGoingEvidenceAmount``)는 **여기서만** 편다 — 컬럼명은 snake_case 정본이다.
_VAT_AMOUNT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("totalSalesAmount", "total_sales_amount", _AMOUNT),
    ("taxationSalesAmount", "taxation_sales_amount", _AMOUNT),
    ("taxExemptionSalesAmount", "tax_exemption_sales_amount", _AMOUNT),
    ("creditCardAmount", "credit_card_amount", _AMOUNT),
    ("cashInComeDeductionAmount", "cash_income_deduction_amount", _AMOUNT),
    ("cashOutGoingEvidenceAmount", "cash_outgoing_evidence_amount", _AMOUNT),
    ("cashExclusionIssuanceAmount", "cash_exclusion_issuance_amount", _AMOUNT),
    ("otherAmount", "other_amount", _AMOUNT),
)

VAT_DAILY_FIELDS: tuple[tuple[str, str, str], ...] = (
    (("settleBasisDate", "settle_basis_date", _DATE),)
    + _VAT_AMOUNT_FIELDS
    + (("merchantId", "merchant_id", _TEXT), ("merchantName", "merchant_name", _TEXT))
)

VAT_CASE_FIELDS: tuple[tuple[str, str, str], ...] = (
    (
        ("settleBasisDate", "settle_basis_date", _DATE),
        ("orderId", "order_id", _TEXT),
        ("productOrderId", "product_order_id", _TEXT),
        ("productOrderType", "product_order_type", _TEXT),
        ("detailType", "detail_type", _TEXT),
        ("status", "status", _TEXT),
        ("productName", "product_name", _TEXT),
    )
    + _VAT_AMOUNT_FIELDS
    + (("merchantId", "merchant_id", _TEXT), ("merchantName", "merchant_name", _TEXT))
)

#: 소급 변경 판정에 쓰는 대표 금액 컬럼(테이블마다 하나). 행수만으로는 "금액만 바뀐"
#: 정정을 못 잡고, 전 컬럼을 비교하면 판정이 무거워지기만 한다.
PARTITION_TOTAL_ATTR: dict[str, str] = {
    "naver_settle_daily": "settle_amount",
    "naver_settle_case": "pay_settle_amount",
    "naver_settle_commission": "commission_amount",
    "naver_vat_daily": "total_sales_amount",
    "naver_vat_case": "total_sales_amount",
}

_CENT = Decimal("0.01")


# --------------------------------------------------------------------------- #
# 상태(워터마크)
# --------------------------------------------------------------------------- #

def read_settle_state(session: Session) -> dict[str, Any]:
    """저장된 정산 동기화 상태를 준다(없으면 빈 dict).

    Args:
        session: DB 세션.

    Returns:
        상태 dict(``coverage_from``·``coverage_to``·``vat_final_month`` 등).
    """
    row = session.get(SystemSetting, SETTING_KEY)
    value = row.setting_value if row is not None else None
    return dict(value) if isinstance(value, dict) else {}


def write_settle_state(session: Session, state: dict[str, Any]) -> None:
    """상태 행을 만들거나 갱신한다(커밋은 호출자).

    Args:
        session: DB 세션.
        state: 통째로 저장할 상태 dict.
    """
    row = session.get(SystemSetting, SETTING_KEY)
    if row is None:
        session.add(SystemSetting(
            setting_key=SETTING_KEY, setting_value=dict(state),
            description="네이버 채널 정산 동기화 상태 (SETTLE-CHANNEL-01)",
        ))
    else:
        row.setting_value = dict(state)
        row.version = int(row.version or 1) + 1
    session.flush()


# --------------------------------------------------------------------------- #
# 값 변환 — 재계산 금지, 형만 맞춘다
# --------------------------------------------------------------------------- #

def parse_settle_date(value: Any) -> Optional[date]:
    """``"YYYY-MM-DD"`` 문자열을 :class:`datetime.date` 로(빈 값·형식 오류는 None).

    날짜에 시각을 붙이지 않는다 — 정산 날짜는 KST 달력 날짜이고, ``DateTime`` 으로 올리면
    naive=UTC 저장 규약과 섞여 하루씩 밀린다.

    Args:
        value: 네이버 원문 값(문자열 또는 ``date``).

    Returns:
        파싱된 날짜 또는 None.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        logger.warning("[NAVER][정산] 날짜 파싱 실패(무시): %r", value)
        return None


def parse_settle_amount(value: Any) -> Optional[Decimal]:
    """네이버 금액을 :class:`~decimal.Decimal` 로 **그대로** 옮긴다(부호 보존·재계산 금지).

    ``float`` 로 받지 않는 이유는 회계 대사다 — 이진 부동소수는 합계가 1원씩 어긋난다.

    Args:
        value: 네이버 원문 값(숫자 또는 숫자 문자열).

    Returns:
        Decimal 또는 None(빈 값·숫자가 아닌 값).
    """
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning("[NAVER][정산] 금액 파싱 실패(무시): %r", value)
        return None


def build_row(element: dict, fields: Sequence[tuple[str, str, str]]) -> dict[str, Any]:
    """응답 element 하나를 컬럼 dict 으로 옮긴다(원본은 ``raw_snapshot`` 에 통째로).

    Args:
        element: 네이버 응답 ``elements`` 의 한 항목.
        fields: ``(원문 키, 컬럼명, 종류)`` 지도.

    Returns:
        모델 생성자에 그대로 넘길 수 있는 dict.
    """
    row: dict[str, Any] = {"raw_snapshot": dict(element)}
    for source_key, column, kind in fields:
        value = element.get(source_key)
        if kind == _DATE:
            row[column] = parse_settle_date(value)
        elif kind == _AMOUNT:
            row[column] = parse_settle_amount(value)
        else:
            text = str(value).strip() if value is not None else ""
            row[column] = text or None
    return row


def _q(value: Optional[Decimal]) -> Decimal:
    """금액을 원 단위 소수 2자리로 맞춘다(SQLite 합계의 부동소수 잡음 제거용)."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(_CENT)


# --------------------------------------------------------------------------- #
# 파티션 교체
# --------------------------------------------------------------------------- #

def replace_partition(session: Session, model: Any, *, channel: str, axis_column: Any,
                      axis_value: date, rows: list[dict], run_id: Optional[int] = None,
                      now: Optional[datetime] = None) -> Optional[dict]:
    """``(channel, axis_value)`` 파티션을 지우고 ``rows`` 를 넣는다(같은 트랜잭션).

    교체 **직전** 합계를 재어 새 합계와 다르면 소급 변경으로 판정한다. 옛 행이 0건이면
    첫 적재이므로 변경으로 세지 않는다.

    Args:
        session: DB 세션(커밋은 호출자).
        model: 대상 모델 클래스.
        channel: 채널 코드.
        axis_column: 파티션 축 컬럼(InstrumentedAttribute).
        axis_value: 파티션 축 값(날짜).
        rows: :func:`build_row` 결과 목록.
        run_id: 실행 이력 id(소프트 참조).
        now: 적재 시각(미지정이면 지금).

    Returns:
        소급 변경 dict 또는 None.
    """
    total_attr = PARTITION_TOTAL_ATTR[model.__tablename__]
    scope = (model.channel == channel, axis_column == axis_value)
    old_count, old_total = _partition_totals(session, model, total_attr, scope)
    session.query(model).filter(*scope).delete(synchronize_session=False)
    stamp = now or now_utc_naive()
    for row in rows:
        session.add(model(channel=channel, sync_run_id=run_id, synced_at=stamp, **row))
    new_total = sum((_q(row.get(total_attr)) for row in rows), Decimal("0.00"))
    if old_count and (old_count != len(rows) or _q(old_total) != new_total):
        return {"table": model.__tablename__, "date": axis_value.isoformat(),
                "old_total": str(_q(old_total)), "new_total": str(new_total),
                "old_count": int(old_count), "new_count": len(rows)}
    return None


def _partition_totals(session: Session, model: Any, total_attr: str,
                      scope: tuple) -> tuple[int, Decimal]:
    """교체 전 파티션의 ``(행수, 금액 합)`` 을 잰다."""
    column = getattr(model, total_attr)
    row = (session.query(func.count(model.id), func.sum(column))
           .filter(*scope).one())
    return int(row[0] or 0), _q(row[1])


# --------------------------------------------------------------------------- #
# 실행 컨텍스트
# --------------------------------------------------------------------------- #

@dataclass
class _SyncContext:
    """한 번의 실행이 들고 다니는 것들(세션·클라이언트·집계)."""

    session: Session
    client: Any
    today: date
    channel: str
    trigger: str
    backfill: bool
    dry_run: bool
    sleep: Callable[[float], Any]
    now: datetime
    run_id: Optional[int] = None
    calls: int = 0
    stats: dict[str, Any] = field(default_factory=lambda: {
        "calls": {}, "rows": {}, "retro_changes": [], "partitions": 0,
        "skipped_no_axis": 0, "last_dates": {},
    })

    def note_call(self, endpoint: str) -> None:
        """호출 1회를 집계한다."""
        self.calls += 1
        counters = self.stats["calls"]
        counters[endpoint] = int(counters.get(endpoint, 0)) + 1

    def note_coverage(self, endpoint: str, through: date) -> None:
        """엔드포인트가 어느 날짜까지 성공적으로 훑었는지 기록한다(뒤로 가지 않는다)."""
        covered = self.stats["last_dates"]
        current = str(covered.get(endpoint) or "")
        covered[endpoint] = max(current, through.isoformat())

    def note_rows(self, table: str, count: int) -> None:
        """적재 행수를 집계한다."""
        counters = self.stats["rows"]
        counters[table] = int(counters.get(table, 0)) + int(count)

    def note_retro(self, change: Optional[dict]) -> None:
        """소급 변경 1건을 남긴다(None 이면 아무 일도 없다)."""
        if change:
            self.stats["retro_changes"].append(change)
            logger.warning("[NAVER][정산] 소급 변경 감지 %s", change)

    def skip_day(self, day: date) -> bool:
        """확정 구간(예정일+30일 경과)이면 건너뛴다 — 백필은 건너뛰지 않는다."""
        return (not self.backfill) and is_finalized(day, self.today)

    def check_quota(self) -> None:
        """쿼터 헤더가 왔으면 순회를 중단시킨다.

        Raises:
            SettleSyncQuotaAborted: ``client.last_quota_limit_header`` 가 채워졌을 때.
        """
        header = getattr(self.client, "last_quota_limit_header", None)
        if header:
            raise SettleSyncQuotaAborted(f"네이버 호출 쿼터 제한(gncp-gw-quota-limit={header})")


def _fetch_pages(ctx: _SyncContext, endpoint: str,
                 call: Callable[[int], dict]) -> list[dict]:
    """페이지를 끝까지 훑어 ``elements`` 를 모은다(호출 간격 준수 + 쿼터 감시).

    Args:
        ctx: 실행 컨텍스트.
        endpoint: 집계용 엔드포인트 이름.
        call: 페이지 번호를 받아 응답 dict 을 주는 호출.

    Returns:
        모든 페이지의 element 목록.

    Raises:
        SettleSyncQuotaAborted: 쿼터 헤더를 만났을 때.
    """
    elements: list[dict] = []
    page = 1
    while True:
        if ctx.calls:
            # 자사 스토어 앱은 2 RPS 고정이고 초과분은 처리되지 않고 실패한다.
            ctx.sleep(CALL_INTERVAL_SECONDS)
        payload = call(page) or {}
        ctx.note_call(endpoint)
        ctx.check_quota()
        elements.extend(list(payload.get("elements") or []))
        total_pages = int((payload.get("pagination") or {}).get("totalPages") or 0)
        if page >= total_pages or page >= MAX_PAGES:
            return elements
        page += 1


# --------------------------------------------------------------------------- #
# 매칭 — PROD_ORDER 행만 ERP 주문에 붙인다
# --------------------------------------------------------------------------- #

def apply_matching(session: Session, rows: list[dict], *, channel: str) -> None:
    """건별 정산 행에 ``foms_order_id``·``link_id``·``match_status`` 를 채운다(제자리 수정).

    ``PROD_ORDER`` 가 아닌 행(배송비·기타비용·리뷰 적립 등)은 붙을 주문이 애초에 없으므로
    ``NA`` 다 — 미매칭으로 세면 매칭률이 영원히 100% 에 못 닿는다.

    Args:
        session: DB 세션.
        rows: :func:`build_row` 결과 목록(``product_order_id``·``product_order_type`` 보유).
        channel: 채널 코드(링크도 같은 채널만 본다).
    """
    wanted = {
        str(row.get("product_order_id"))
        for row in rows
        if row.get("product_order_type") == MATCHABLE_PRODUCT_ORDER_TYPE
        and row.get("product_order_id")
    }
    links = _fetch_links(session, sorted(wanted), channel=channel)
    for row in rows:
        if row.get("product_order_type") != MATCHABLE_PRODUCT_ORDER_TYPE:
            row.update({"foms_order_id": None, "link_id": None, "match_status": "NA"})
            continue
        link_id, order_id = links.get(str(row.get("product_order_id") or ""), (None, None))
        row.update({
            "foms_order_id": order_id,
            "link_id": link_id,
            "match_status": "MATCHED" if order_id else "UNMATCHED",
        })


def _fetch_links(session: Session, product_order_ids: Sequence[str], *,
                 channel: str) -> dict[str, tuple[Optional[int], Optional[int]]]:
    """상품주문번호 → ``(link_id, order_id)`` 지도를 배치 조회로 만든다(N+1 금지)."""
    found: dict[str, tuple[Optional[int], Optional[int]]] = {}
    for start in range(0, len(product_order_ids), _MATCH_CHUNK):
        chunk = list(product_order_ids[start:start + _MATCH_CHUNK])
        if not chunk:
            continue
        rows = (session.query(ExternalOrderLink.external_id, ExternalOrderLink.id,
                              ExternalOrderLink.order_id)
                .filter(ExternalOrderLink.channel == channel,
                        ExternalOrderLink.external_id.in_(chunk))
                .all())
        for external_id, link_id, order_id in rows:
            found[str(external_id)] = (int(link_id), int(order_id) if order_id else None)
    return found


# --------------------------------------------------------------------------- #
# 구간·달력 계산
# --------------------------------------------------------------------------- #

def is_finalized(day: date, today: date) -> bool:
    """정산 예정일이 확정 구간(더 이상 안 바뀜)에 들어갔는지.

    Args:
        day: 판정할 날짜.
        today: 오늘.

    Returns:
        ``day + 30일 < today`` 면 True.
    """
    return day + timedelta(days=FINALIZED_AFTER_DAYS) < today


def iter_days(start: date, end: date) -> list[date]:
    """``[start, end]`` 의 날짜를 하루씩(끝 포함)."""
    if end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def split_windows(start: date, end: date, size_days: int = BACKFILL_WINDOW_DAYS
                  ) -> list[tuple[date, date]]:
    """긴 구간을 ``size_days`` 짜리 창으로 쪼갠다(끝 포함, 한 job 안에서 순차 처리).

    Args:
        start: 구간 시작.
        end: 구간 끝.
        size_days: 창 길이(일).

    Returns:
        ``(창 시작, 창 끝)`` 목록.
    """
    if end < start:
        return []
    windows: list[tuple[date, date]] = []
    cursor = start
    step = max(1, int(size_days))
    while cursor <= end:
        finish = min(cursor + timedelta(days=step - 1), end)
        windows.append((cursor, finish))
        cursor = finish + timedelta(days=1)
    return windows


def last_month_bounds(today: date) -> tuple[date, date]:
    """전월 1일과 말일을 준다(부가세는 전월 말일까지만 조회된다)."""
    first_of_this_month = today.replace(day=1)
    last_day = first_of_this_month - timedelta(days=1)
    return (last_day.replace(day=1), last_day)


def resolve_vat_months(state: dict[str, Any], today: date, *,
                       backfill_from: Optional[date]) -> list[tuple[date, date]]:
    """이번 실행에서 적재할 부가세 달 목록을 정한다.

    규칙: 매달 10일 이후에 전월 확정본을 **한 번만** 당긴다(``vat_final_month`` 로 기억).
    백필이면 ``backfill_from`` 의 달부터 전월까지 월 단위로 전부 다시 받는다.

    Args:
        state: 현재 상태 dict.
        today: 오늘.
        backfill_from: 백필 시작일(아니면 None).

    Returns:
        ``(달 첫날, 달 말일)`` 목록(할 일이 없으면 빈 목록).
    """
    month_start, month_end = last_month_bounds(today)
    if backfill_from is not None:
        months: list[tuple[date, date]] = []
        cursor = backfill_from.replace(day=1)
        while cursor <= month_start:
            _, cursor_end = last_month_bounds(cursor + timedelta(days=32))
            months.append((cursor, min(cursor_end, month_end)))
            cursor = cursor_end + timedelta(days=1)
        return months
    if today.day < VAT_FINAL_DAY:
        return []
    if str(state.get("vat_final_month") or "") == month_start.strftime("%Y-%m"):
        return []
    return [(month_start, month_end)]


# --------------------------------------------------------------------------- #
# 엔드포인트별 적재
# --------------------------------------------------------------------------- #

def _sync_settle_daily(ctx: _SyncContext, start: date, end: date) -> None:
    """일별 정산을 구간으로 받아 ``settle_expect_date`` 별 파티션으로 교체한다.

    응답에 없는 날짜도 **비운다** — 행이 통째로 사라진 소급 변경을 놓치지 않기 위해서다.
    """
    elements: list[dict] = []
    for win_start, win_end in split_windows(start, end, DAILY_RANGE_MAX_DAYS):
        elements.extend(_fetch_pages(
            ctx, "settle/daily",
            lambda page, a=win_start, b=win_end: ctx.client.get_settle_daily(a, b, page=page)))
    grouped: dict[date, list[dict]] = {}
    for element in elements:
        row = build_row(element, DAILY_FIELDS)
        axis = row.get("settle_expect_date")
        if axis is None:
            ctx.stats["skipped_no_axis"] += 1
            continue
        grouped.setdefault(axis, []).append(row)
    ctx.note_rows("naver_settle_daily", sum(len(v) for v in grouped.values()))
    ctx.note_coverage("settle/daily", end)
    if ctx.dry_run:
        return
    for day in sorted(set(iter_days(start, end)) | set(grouped)):
        if ctx.skip_day(day):
            continue
        ctx.note_retro(replace_partition(
            ctx.session, NaverSettleDaily, channel=ctx.channel,
            axis_column=NaverSettleDaily.settle_expect_date, axis_value=day,
            rows=grouped.get(day, []), run_id=ctx.run_id, now=ctx.now))
        ctx.stats["partitions"] += 1


def _sync_settle_case(ctx: _SyncContext, day: date) -> None:
    """건별 정산 하루치를 받아 ``search_date`` 파티션으로 교체한다(매칭 포함)."""
    elements = _fetch_pages(
        ctx, "settle/case",
        lambda page: ctx.client.get_settle_cases(day, page=page))
    rows = [build_row(element, CASE_FIELDS) for element in elements]
    for row in rows:
        row["search_date"] = day
        row["period_type"] = DEFAULT_SETTLE_PERIOD_TYPE
    ctx.note_rows("naver_settle_case", len(rows))
    ctx.note_coverage("settle/case", day)
    if ctx.dry_run:
        return
    apply_matching(ctx.session, rows, channel=ctx.channel)
    ctx.note_retro(replace_partition(
        ctx.session, NaverSettleCase, channel=ctx.channel,
        axis_column=NaverSettleCase.search_date, axis_value=day,
        rows=rows, run_id=ctx.run_id, now=ctx.now))
    ctx.stats["partitions"] += 1


def _sync_settle_commission(ctx: _SyncContext, day: date) -> None:
    """수수료 상세 하루치를 받아 ``search_date`` 파티션으로 교체한다."""
    elements = _fetch_pages(
        ctx, "settle/commission-details",
        lambda page: ctx.client.get_settle_commission_details(day, page=page))
    rows = [build_row(element, COMMISSION_FIELDS) for element in elements]
    for row in rows:
        row["search_date"] = day
        row["period_type"] = DEFAULT_SETTLE_PERIOD_TYPE
    ctx.note_rows("naver_settle_commission", len(rows))
    ctx.note_coverage("settle/commission-details", day)
    if ctx.dry_run:
        return
    ctx.note_retro(replace_partition(
        ctx.session, NaverSettleCommission, channel=ctx.channel,
        axis_column=NaverSettleCommission.search_date, axis_value=day,
        rows=rows, run_id=ctx.run_id, now=ctx.now))
    ctx.stats["partitions"] += 1


def _sync_vat_month(ctx: _SyncContext, month_start: date, month_end: date) -> None:
    """부가세 한 달치(일별 + 건별)를 받아 ``settle_basis_date`` 파티션으로 교체한다.

    전월 말일까지만 조회되는 구간이므로 여기 들어온 값은 전부 **확정본**이다
    (``is_final=True``).
    """
    for endpoint, fetch, model, fields in (
        ("vat/daily", ctx.client.get_vat_daily, NaverVatDaily, VAT_DAILY_FIELDS),
        ("vat/case", ctx.client.get_vat_cases, NaverVatCase, VAT_CASE_FIELDS),
    ):
        elements = _fetch_pages(
            ctx, endpoint,
            lambda page, _fetch=fetch: _fetch(month_start, month_end, page=page))
        grouped: dict[date, list[dict]] = {}
        for element in elements:
            row = build_row(element, fields)
            axis = row.get("settle_basis_date")
            if axis is None:
                ctx.stats["skipped_no_axis"] += 1
                continue
            if model is NaverVatDaily:
                row["is_final"] = True
            grouped.setdefault(axis, []).append(row)
        ctx.note_rows(model.__tablename__, sum(len(v) for v in grouped.values()))
        ctx.note_coverage(endpoint, month_end)
        if ctx.dry_run:
            continue
        for day in sorted(set(iter_days(month_start, month_end)) | set(grouped)):
            ctx.note_retro(replace_partition(
                ctx.session, model, channel=ctx.channel,
                axis_column=model.settle_basis_date, axis_value=day,
                rows=grouped.get(day, []), run_id=ctx.run_id, now=ctx.now))
            ctx.stats["partitions"] += 1


# --------------------------------------------------------------------------- #
# 진입점
# --------------------------------------------------------------------------- #

def run_settle_sync(session: Session, client: Any, *, today: date, trigger: str,
                    actor_user_id: Optional[int] = None,
                    backfill_from: Optional[date] = None, dry_run: bool = False,
                    sleep: Callable[[float], Any] = time.sleep,
                    channel: str = NAVER_SETTLE_CHANNEL_DEFAULT) -> dict[str, Any]:
    """정산 동기화 1회 실행(커밋은 이 함수가 소유한다).

    구간은 기본 ``today-30 .. today+14``, ``backfill_from`` 이 있으면
    ``backfill_from .. today+14`` 를 30일 창으로 쪼개 순차로 돈다.

    Args:
        session: DB 세션.
        client: :class:`NaverCommerceClient` 또는 같은 계약의 객체.
        today: 오늘(KST 날짜).
        trigger: ``SCHEDULE``/``MANUAL``/``BACKFILL``.
        actor_user_id: 화면에서 누른 사람(기록용).
        backfill_from: 소급 적재 시작일(없으면 기본 구간).
        dry_run: True 면 **조회만** 하고 DB 에 아무것도 쓰지 않는다(이력 행도 없다).
        sleep: 호출 간격 대기 함수(테스트 주입용).
        channel: 채널 코드.

    Returns:
        ``{ok, status, run_id, dry_run, scope, stats, error}``.

    Raises:
        ValueError: ``trigger`` 가 허용 집합 밖일 때(호출 0회로 거절).
    """
    if trigger not in NAVER_SETTLE_RUN_TRIGGERS:
        raise ValueError(f"알 수 없는 실행 유형입니다: {trigger!r}")
    start = backfill_from or (today - timedelta(days=DEFAULT_ROLLING_DAYS))
    end = today + timedelta(days=DEFAULT_FUTURE_DAYS)
    scope = {"from": start.isoformat(), "to": end.isoformat(),
             "backfill_from": backfill_from.isoformat() if backfill_from else None,
             "trigger": trigger, "channel": channel}
    ctx = _SyncContext(session=session, client=client, today=today, channel=channel,
                       trigger=trigger, backfill=backfill_from is not None,
                       dry_run=bool(dry_run), sleep=sleep, now=now_utc_naive())
    if hasattr(client, "last_quota_limit_header"):
        # 지난 호출의 관측값이 남아 있으면 첫 호출부터 중단으로 오판한다.
        client.last_quota_limit_header = None
    _open_run(ctx, scope=scope, actor_user_id=actor_user_id)
    return _drive(ctx, start=start, end=end, scope=scope, backfill_from=backfill_from)


def _drive(ctx: _SyncContext, *, start: date, end: date, scope: dict,
           backfill_from: Optional[date]) -> dict[str, Any]:
    """구간을 실제로 훑고 결과를 확정한다(예외를 삼켜 상태로 바꾼다)."""
    try:
        for window_start, window_end in split_windows(start, end):
            _sync_window(ctx, window_start, window_end)
        for month_start, month_end in resolve_vat_months(
                read_settle_state(ctx.session), ctx.today,
                backfill_from=backfill_from):
            _sync_vat_month(ctx, month_start, month_end)
            ctx.stats["vat_month"] = month_start.strftime("%Y-%m")
    except SettleSyncQuotaAborted as exc:
        return _finish(ctx, status="ABORTED_QUOTA", scope=scope, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 실패를 이력·상태로 남기고 반환한다
        logger.error("[NAVER][정산] 동기화 실패: %s", exc, exc_info=True)
        return _finish(ctx, status="FAILED", scope=scope, error=str(exc))
    return _finish(ctx, status="OK", scope=scope, error=None)


def _sync_window(ctx: _SyncContext, window_start: date, window_end: date) -> None:
    """창 하나를 훑는다: 일별 정산 1회 + 건별/수수료는 하루씩."""
    _sync_settle_daily(ctx, window_start, window_end)
    for day in iter_days(window_start, window_end):
        if ctx.skip_day(day):
            continue
        _sync_settle_case(ctx, day)
        _sync_settle_commission(ctx, day)
    if not ctx.dry_run:
        # 창마다 커밋한다 — 중간에 멈춰도 여기까지 받은 것은 남는다.
        ctx.session.commit()


def _open_run(ctx: _SyncContext, *, scope: dict, actor_user_id: Optional[int]) -> None:
    """실행 이력 행을 ``RUNNING`` 으로 연다(dry_run 은 아무것도 쓰지 않는다)."""
    if ctx.dry_run:
        return
    run = NaverSettleSyncRun(
        channel=ctx.channel, started_at=ctx.now, status="RUNNING", trigger=ctx.trigger,
        actor_user_id=actor_user_id, scope=dict(scope), stats=None, dry_run=False)
    ctx.session.add(run)
    ctx.session.commit()
    ctx.run_id = int(run.id)


def _finish(ctx: _SyncContext, *, status: str, scope: dict,
            error: Optional[str]) -> dict[str, Any]:
    """이력 행과 워터마크를 마무리하고 반환 dict 을 만든다.

    ``OK`` 일 때만 성공 구간(coverage)과 ``last_ok_at`` 이 전진한다 — 쿼터 중단·실패는
    다음 실행이 같은 구간을 다시 훑도록 제자리에 둔다.
    """
    payload = {"ok": status == "OK", "status": status, "run_id": ctx.run_id,
               "dry_run": ctx.dry_run, "scope": dict(scope), "stats": dict(ctx.stats),
               "error": error}
    if ctx.dry_run:
        return payload
    try:
        _close_run(ctx, status=status, error=error)
        _write_watermark(ctx, status=status, scope=scope, error=error)
        ctx.session.commit()
    except Exception as exc:  # noqa: BLE001 - 기록 실패가 이미 받은 적재를 되돌리지 않게
        ctx.session.rollback()
        logger.error("[NAVER][정산] 실행 기록 실패(적재는 유지): %s", exc, exc_info=True)
    return payload


def _close_run(ctx: _SyncContext, *, status: str, error: Optional[str]) -> None:
    """실행 이력 행을 종료 상태로 덮는다."""
    if ctx.run_id is None:
        return
    run = ctx.session.get(NaverSettleSyncRun, ctx.run_id)
    if run is None:
        return
    run.status = status
    run.finished_at = now_utc_naive()
    run.stats = dict(ctx.stats)
    run.error = (str(error)[:2000] if error else None)


def _write_watermark(ctx: _SyncContext, *, status: str, scope: dict,
                     error: Optional[str]) -> None:
    """상태 행을 갱신한다(성공했을 때만 구간을 전진시킨다)."""
    state = read_settle_state(ctx.session)
    state["rev"] = int(state.get("rev") or 0) + 1
    state["last_run_at"] = ctx.now.isoformat()
    state["last_status"] = status
    state["last_error"] = (str(error)[:2000] if error else None)
    state.setdefault("rolling_days", DEFAULT_ROLLING_DAYS)
    state.setdefault("future_days", DEFAULT_FUTURE_DAYS)
    state.setdefault("vat_final_month", None)
    if status == "OK":
        state["last_ok_at"] = ctx.now.isoformat()
        state["coverage_from"] = scope["from"]
        state["coverage_to"] = scope["to"]
        covered = ctx.stats.get("last_dates") or {}
        state["per_endpoint"] = {
            name: {"last_ok_date": covered.get(name) or scope["to"], "calls": int(count)}
            for name, count in (ctx.stats.get("calls") or {}).items()
        }
        if ctx.stats.get("vat_month"):
            state["vat_final_month"] = ctx.stats["vat_month"]
    write_settle_state(ctx.session, state)


__all__ = [
    "BACKFILL_WINDOW_DAYS",
    "DAILY_RANGE_MAX_DAYS",
    "CALL_INTERVAL_SECONDS",
    "DEFAULT_FUTURE_DAYS",
    "DEFAULT_ROLLING_DAYS",
    "FINALIZED_AFTER_DAYS",
    "MATCHABLE_PRODUCT_ORDER_TYPE",
    "PARTITION_TOTAL_ATTR",
    "SETTING_KEY",
    "VAT_FINAL_DAY",
    "SettleSyncQuotaAborted",
    "apply_matching",
    "build_row",
    "is_finalized",
    "iter_days",
    "last_month_bounds",
    "parse_settle_amount",
    "parse_settle_date",
    "read_settle_state",
    "replace_partition",
    "resolve_vat_months",
    "run_settle_sync",
    "split_windows",
    "write_settle_state",
]
