"""SETTLE-CHANNEL v1.1 T14: 네이버 정산 CSV 내보내기 커널 계약.

이 파일이 red 로 잡아야 하는 것:

1. **"CSV 100%" 약속이 깨지는 것** — 리서치 카탈로그 47필드와 5개 모델의 컬럼 전량이
   5종 CSV 의 열 합집합에 다 들어 있어야 한다. 하나라도 빠지면 회계팀이 화면에서만 볼 수
   있는 값이 생긴다(스펙 §1 "적재 100% · CSV 100% · 화면 41").
2. **열 순서 드리프트** — 더존·이카운트 import 매핑은 열 순서를 기억한다. 순서가 바뀌면
   회계팀이 매핑을 다시 만들어야 하므로 헤더 목록을 통째로 못 박는다.
3. **BOM·CRLF 유실** — 없으면 표 계산 프로그램이 한글을 깨서 연다.
4. **부호 뒤집기·금액 서식화** — 취소·환급 행의 음수가 ``-389000`` 그대로 나와야 한다
   (``(389,000)``·``389000`` 아님). 천단위 콤마는 파서를 깨뜨린다.
5. **계좌번호 원문 유출** — 화면은 가리고 파일은 다 주는 구멍을 만들지 않는다.
6. **한글 라벨 하드코딩** — enum 라벨은 ``settle_enums`` 카탈로그에서만 온다. 이 모듈에
   코드→라벨 표를 손으로 다시 적으면 네이버가 표기를 바꿀 때 두 곳이 갈린다.
7. **표 계산 라이브러리 재등장** — 2026-09-01 에 떼어낸 ``pandas``·``openpyxl`` 을 되붙이는
   것이 이 기능의 가장 큰 유혹이다(계약 §1.3 C1·C2).
8. **구간 폭 상한 미적용** — 새 상한을 발명하지 않고 조회 커널의 ``MAX_RANGE_DAYS`` 를 쓴다.
9. **감사 라벨 미등재** — ``NAVER_SETTLE_EXPORT_CSV`` 가 ``ACTION_LABELS`` 에 없으면
   감사 화면에 영문 코드가 그대로 뜬다(pre_push_smoke 사각, CI 에서만 red 인 전례가 있다).

여기서 다루지 **않는** 것: HTTP 표면(권한 403 JSON·감사 1행 적재·400 응답). 라우트
``GET /api/settlement/channel/export.csv`` 는 W2-A 소유라 그 계약은 채널 API 테스트가 맡는다.

테스트 데이터 규율: 존재하지 않는 FK id 를 쓰지 않는다(SQLite 는 FK 를 강제하지 않아 로컬만
통과하고 PG 레인에서 터진다). 정산 행은 FK 가 없는 소프트 참조라 ``foms_order_id`` 를 비운다.
"""

from __future__ import annotations

import ast
import csv
import datetime
import io
import pathlib
from decimal import Decimal

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.services.audit_message_display import ACTION_LABELS
from foms.services.integrations.naver_commerce import settle_enums
from foms.services import settlement_channel as kernel
from foms.services import settlement_channel_export as export
from models import (
    NaverSettleCase,
    NaverSettleCommission,
    NaverSettleDaily,
    NaverVatCase,
    NaverVatDaily,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 라우트가 남길 감사 행위 코드(계약 §1.3 C5). 라우트보다 라벨이 먼저 들어간다.
_AUDIT_ACTION = "NAVER_SETTLE_EXPORT_CSV"

#: 어느 모델에나 붙는 공통 메타. 업무 데이터가 아니라 CSV 에 넣지 않는다
#: (``raw_snapshot`` 은 셀 안 개행·콤마로 임포터를 깨뜨린다).
_COMMON_META = {"id", "channel", "raw_snapshot", "synced_at", "sync_run_id"}

_MODELS = {
    "settle_daily": NaverSettleDaily, "settle_case": NaverSettleCase,
    "commission": NaverSettleCommission, "vat_daily": NaverVatDaily,
    "vat_case": NaverVatCase,
}

#: 리서치 카탈로그 47필드 —
#: ``docs/research/2026-09-02-naver-settlement/01-naver-settle-api-spec.md`` §데이터 카탈로그.
#: (번호, 원본 필드명, 대응 모델 컬럼들). 컬럼이 비어 있는 항목은 **행 필드가 아니라는 뜻**이며
#: 사유를 함께 적는다 — 조용히 빼면 "47 중 46" 이 47 로 둔갑한다.
_CATALOGUE: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "settleBasisDate", ("settle_basis_date",)),
    (2, "settleExpectDate", ("settle_expect_date",)),
    (3, "settleCompleteDate", ("settle_complete_date",)),
    (4, "payDate", ("pay_date",)),
    (5, "orderId", ("order_id",)),
    (6, "productOrderId", ("product_order_id",)),
    (7, "productOrderType", ("product_order_type",)),
    (8, "settleType", ("settle_type",)),
    (9, "productId, productName", ("product_id", "product_name")),
    (10, "purchaserName", ("purchaser_name",)),
    (11, "paySettleAmount", ("pay_settle_amount",)),
    (12, "totalPayCommissionAmount", ("total_pay_commission_amount",)),
    (13, "freeInstallmentCommissionAmount", ("free_installment_commission_amount",)),
    (14, "sellingInterlockCommissionAmount", ("selling_interlock_commission_amount",)),
    (15, "benefitSettleAmount", ("benefit_settle_amount",)),
    (16, "settleExpectAmount", ("settle_expect_amount",)),
    (17, "merchantId, merchantName, contractNo",
     ("merchant_id", "merchant_name", "contract_no")),
    (18, "commissionBasisAmount", ("commission_basis_amount",)),
    (19, "commissionType", ("commission_type",)),
    (20, "payMeansType", ("pay_means_type",)),
    (21, "commissionAmount", ("commission_amount",)),
    (22, "maximumSellingInterlockCommissionAmount",
     ("maximum_selling_interlock_commission_amount",)),
    (23, "taxReturnDate", ("tax_return_date",)),
    (24, "settleBasisStartDate/EndDate",
     ("settle_basis_start_date", "settle_basis_end_date")),
    (25, "settleAmount", ("settle_amount",)),
    (26, "commissionSettleAmount", ("commission_settle_amount",)),
    (27, "deductionRestoreSettleAmount", ("deduction_restore_settle_amount",)),
    (28, "payHoldbackAmount", ("pay_holdback_amount",)),
    (29, "minusChargeAmount", ("minus_charge_amount",)),
    (30, "differenceSettleAmount", ("difference_settle_amount",)),
    (31, "returnCareSettleAmount", ("return_care_settle_amount",)),
    (32, "normalSettleAmount vs quickSettleAmount",
     ("normal_settle_amount", "quick_settle_amount")),
    (33, "preferentialCommissionAmount", ("preferential_commission_amount",)),
    (34, "settlementLimitAmount", ("settlement_limit_amount",)),
    (35, "settleMethodType", ("settle_method_type",)),
    (36, "bankType, depositorName, accountNo",
     ("bank_type", "depositor_name", "account_no")),
    (37, "detailType", ("detail_type",)),
    (38, "status", ("status",)),
    (39, "totalSalesAmount", ("total_sales_amount",)),
    (40, "taxationSalesAmount", ("taxation_sales_amount",)),
    (41, "taxExemptionSalesAmount", ("tax_exemption_sales_amount",)),
    (42, "creditCardAmount", ("credit_card_amount",)),
    (43, "cashInComeDeductionAmount", ("cash_income_deduction_amount",)),
    (44, "cashOutGoingEvidenceAmount", ("cash_outgoing_evidence_amount",)),
    (45, "cashExclusionIssuanceAmount", ("cash_exclusion_issuance_amount",)),
    (46, "otherAmount", ("other_amount",)),
    # 응답 봉투의 총 건수다. 행에 실리는 값이 아니라 적재 검증용 카운터라 컬럼이 없다.
    (47, "pagination.totalElements", ()),
)

#: 열 순서 고정 핀. 회계 프로그램의 import 매핑이 순서를 기억하므로 **순서까지** 계약이다.
_PINNED_HEADERS: dict[str, tuple[str, ...]] = {
    "settle_daily": (
        "정산 기준 시작일", "정산 기준 종료일", "정산 예정일", "정산 완료일", "정산 금액",
        "결제 정산 금액", "수수료 정산 합계", "혜택 정산 금액", "공제 환급 합계",
        "지급 보류 금액", "마이너스 충전금 상계", "차액 정산 금액", "반품안심케어 정산 금액",
        "일반정산 금액", "빠른정산 금액", "우대 수수료 환급", "한도 보류 금액",
        "정산 방식(settleMethodType)", "정산 방식명", "은행(bankType)", "은행명",
        "예금주명", "계좌번호(마스킹)", "가맹점 ID", "가맹점명",
    ),
    "settle_case": (
        "조회일", "조회 기준(periodType)", "조회 기준명", "정산 기준일", "정산 예정일",
        "정산 완료일", "결제일", "주문번호(orderId)", "상품주문번호(productOrderId)",
        "정산 대상 구분(productOrderType)", "정산 대상 구분명", "정산 구분(settleType)",
        "정산 구분명", "상품번호", "상품명", "구매자명", "결제 정산 금액",
        "네이버페이 수수료 합계", "무이자 할부 수수료", "매출 연동 수수료", "혜택 정산 금액",
        "정산 예정 금액", "가맹점 ID", "가맹점명", "계약번호", "FOMS 주문 ID",
        "FOMS 연동 링크 ID", "주문 매칭 상태",
    ),
    "commission": (
        "조회일", "조회 기준(periodType)", "조회 기준명", "주문번호(orderNo)",
        "상품주문번호(productOrderId)", "정산 대상 구분(productOrderType)",
        "정산 대상 구분명", "상품번호", "상품명", "가맹점 ID", "가맹점명", "구매자명",
        "정산 구분(settleType)", "정산 구분명", "정산 기준일", "정산 예정일", "정산 완료일",
        "세금 신고 기준일", "수수료 기준 금액", "수수료 유형(commissionType)",
        "수수료 유형명", "결제 수단(payMeansType)", "결제 수단명", "수수료 금액",
        "매출 연동 수수료 상한",
    ),
    "vat_daily": (
        "정산 기준일", "총 매출 금액", "과세 매출 금액", "면세 매출 금액",
        "신용카드 결제 금액", "현금영수증 소득공제 금액", "현금영수증 지출증빙 금액",
        "현금영수증 발행제외 금액", "기타 금액", "가맹점 ID", "가맹점명", "확정 여부",
    ),
    "vat_case": (
        "정산 기준일", "주문번호(orderId)", "상품주문번호(productOrderId)",
        "정산 대상 구분(productOrderType)", "정산 대상 구분명",
        "부가세 상세 유형(detailType)", "부가세 상세 유형명", "증빙 상태(status)",
        "증빙 상태명", "상품명", "총 매출 금액", "과세 매출 금액", "면세 매출 금액",
        "신용카드 결제 금액", "현금영수증 소득공제 금액", "현금영수증 지출증빙 금액",
        "현금영수증 발행제외 금액", "기타 금액", "가맹점 ID", "가맹점명",
    ),
}

#: 되붙이면 안 되는 표 계산 라이브러리(계약 §1.3 C1). 이름 자체도 쓰지 않는다(C2).
_FORBIDDEN_LIBS = ("pandas", "openpyxl", "xlsxwriter", "xlrd", "xlwt")
_FORBIDDEN_WORDS = ("pandas", "openpyxl", "xlsxwriter", "excel", "xlsx")

_DAY = datetime.date(2026, 9, 1)
_ACCOUNT_NO = "352-1234-567890"


# ---------------------------------------------------------------------------
# 시드 헬퍼 — 금액은 전부 명시(기본값이 조용히 0 이 되지 않게)
# ---------------------------------------------------------------------------
def _seed_daily(**kwargs) -> NaverSettleDaily:
    """일별 정산 1행(계좌 이체 · 수수료는 네이버 원본대로 음수)."""
    values = {
        "settle_basis_start_date": _DAY, "settle_basis_end_date": _DAY,
        "settle_complete_date": _DAY,
        "settle_amount": Decimal("1000000"), "pay_settle_amount": Decimal("1100000"),
        "commission_settle_amount": Decimal("-100000"),
        "benefit_settle_amount": Decimal("0"),
        "deduction_restore_settle_amount": Decimal("0"),
        "pay_holdback_amount": Decimal("0"), "minus_charge_amount": Decimal("0"),
        "difference_settle_amount": Decimal("0"),
        "return_care_settle_amount": Decimal("0"),
        "normal_settle_amount": Decimal("1000000"), "quick_settle_amount": Decimal("0"),
        "preferential_commission_amount": Decimal("0"),
        "settlement_limit_amount": Decimal("0"),
        "settle_method_type": "ACCOUNT", "bank_type": "KB",
        "depositor_name": "라홈", "account_no": _ACCOUNT_NO,
        "merchant_id": "M1", "merchant_name": "라홈",
    }
    values.update({"channel": "NAVER", "settle_expect_date": _DAY,
                   "raw_snapshot": {"settleExpectDate": _DAY.isoformat()},
                   "synced_at": datetime.datetime(2026, 9, 1, 0, 0)})
    values.update(kwargs)
    row = NaverSettleDaily(**values)
    db_session.add(row)
    db_session.commit()
    return row


def _seed_case(**kwargs) -> NaverSettleCase:
    """건별 정산 1행. 취소 행의 음수를 그대로 두는지 보는 표본이다."""
    values = {
        "settle_basis_date": _DAY, "settle_expect_date": _DAY,
        "settle_complete_date": _DAY, "pay_date": _DAY,
        "order_id": "2026090100000", "product_order_id": "2026090100001",
        "product_order_type": "PROD_ORDER", "settle_type": "NORMAL_SETTLE_AFTER_CANCEL",
        "product_id": "P1", "product_name": "루나 3000", "purchaser_name": "홍길동",
        "pay_settle_amount": Decimal("-389000.00"),
        "total_pay_commission_amount": Decimal("-10000"),
        "free_installment_commission_amount": Decimal("0"),
        "selling_interlock_commission_amount": Decimal("0"),
        "benefit_settle_amount": Decimal("0"),
        "settle_expect_amount": Decimal("-379000"),
        "merchant_id": "M1", "merchant_name": "라홈", "contract_no": "C1",
        "match_status": "MATCHED",
    }
    values.update({"channel": "NAVER", "search_date": _DAY,
                   "period_type": "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
                   "synced_at": datetime.datetime(2026, 9, 1, 0, 0)})
    values.update(kwargs)
    values["raw_snapshot"] = {"productOrderId": values["product_order_id"]}
    row = NaverSettleCase(**values)
    db_session.add(row)
    db_session.commit()
    return row


def _seed_commission(**kwargs) -> NaverSettleCommission:
    """건별 수수료 상세 1행."""
    values = {
        "order_no": "2026090100000", "product_order_id": "2026090100001",
        "product_order_type": "PROD_ORDER", "product_id": "P1",
        "product_name": "루나 3000", "merchant_id": "M1", "merchant_name": "라홈",
        "purchaser_name": "홍길동", "settle_type": "NORMAL_SETTLE_ORIGINAL",
        "settle_basis_date": _DAY, "settle_expect_date": _DAY,
        "settle_complete_date": _DAY, "tax_return_date": _DAY,
        "commission_basis_amount": Decimal("1100000"),
        "commission_type": "PAY_COMMISSION", "pay_means_type": "CREDIT_CARD",
        "commission_amount": Decimal("-33000"),
        "maximum_selling_interlock_commission_amount": Decimal("0"),
    }
    values.update({"channel": "NAVER", "search_date": _DAY,
                   "period_type": "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
                   "synced_at": datetime.datetime(2026, 9, 1, 0, 0)})
    values.update(kwargs)
    values["raw_snapshot"] = {"orderNo": values["order_no"]}
    row = NaverSettleCommission(**values)
    db_session.add(row)
    db_session.commit()
    return row


def _vat_amounts() -> dict:
    """부가세 8금액 표본(면세·기타는 0, 총매출은 양수)."""
    return {
        "total_sales_amount": Decimal("1100000"),
        "taxation_sales_amount": Decimal("1000000"),
        "tax_exemption_sales_amount": Decimal("0"),
        "credit_card_amount": Decimal("1100000"),
        "cash_income_deduction_amount": Decimal("0"),
        "cash_outgoing_evidence_amount": Decimal("0"),
        "cash_exclusion_issuance_amount": Decimal("0"),
        "other_amount": Decimal("0"),
    }


def _seed_vat_daily(**kwargs) -> NaverVatDaily:
    """일별 부가세 1행(잠정치 — ``is_final`` 기본 False)."""
    values = dict(_vat_amounts(), merchant_id="M1", merchant_name="라홈", is_final=False)
    values.update({"channel": "NAVER", "settle_basis_date": _DAY,
                   "raw_snapshot": {"settleBasisDate": _DAY.isoformat()},
                   "synced_at": datetime.datetime(2026, 9, 1, 0, 0)})
    values.update(kwargs)
    row = NaverVatDaily(**values)
    db_session.add(row)
    db_session.commit()
    return row


def _seed_vat_case(**kwargs) -> NaverVatCase:
    """건별 부가세 1행."""
    values = dict(_vat_amounts(), order_id="2026090100000",
                  product_order_id="2026090100001", product_order_type="PROD_ORDER",
                  detail_type="PAY_SETTLE", status="ORDER_SALE",
                  product_name="루나 3000", merchant_id="M1", merchant_name="라홈")
    values.update({"channel": "NAVER", "settle_basis_date": _DAY,
                   "synced_at": datetime.datetime(2026, 9, 1, 0, 0)})
    values.update(kwargs)
    values["raw_snapshot"] = {"orderId": values["order_id"]}
    row = NaverVatCase(**values)
    db_session.add(row)
    db_session.commit()
    return row


_SEEDERS = {
    "settle_daily": _seed_daily, "settle_case": _seed_case,
    "commission": _seed_commission, "vat_daily": _seed_vat_daily,
    "vat_case": _seed_vat_case,
}


# ---------------------------------------------------------------------------
# 조회 헬퍼
# ---------------------------------------------------------------------------
def _lines(kind: str, *, date_from: datetime.date = _DAY,
           date_to: datetime.date = _DAY, **kwargs) -> list[str]:
    """CSV 줄 목록(첫 줄은 BOM+헤더)."""
    return list(export.iter_csv_lines(db_session, kind=kind, date_from=date_from,
                                      date_to=date_to, **kwargs))


def _parsed(kind: str, **kwargs) -> list[list[str]]:
    """CSV 를 파싱한 행 목록(BOM 제거 후)."""
    lines = _lines(kind, **kwargs)
    text = "".join(lines).lstrip("﻿")
    return list(csv.reader(io.StringIO(text)))


def _row_map(kind: str, **kwargs) -> dict[str, str]:
    """첫 데이터 행을 ``{헤더: 셀}`` 로. 시드가 1행뿐인 테스트용."""
    rows = _parsed(kind, **kwargs)
    assert len(rows) == 2, f"데이터 행이 1행이 아니다: {len(rows) - 1}"
    return dict(zip(rows[0], rows[1]))


def _count_queries(fn):
    """실제 SQL 실행 횟수를 센다(``before_cursor_execute``)."""
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def _module_source() -> str:
    """내보내기 커널 소스."""
    return pathlib.Path(export.__file__).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. 종류·필드 소진 (CSV 100% 약속)
# ---------------------------------------------------------------------------
def test_export_kinds_are_the_five_agreed_kinds():
    """5종이다 — 4종이면 settle/daily 13필드가 어느 파일에도 안 들어간다."""
    assert export.EXPORT_KINDS == (
        "settle_daily", "settle_case", "commission", "vat_daily", "vat_case")
    assert export.CSV_KINDS == export.EXPORT_KINDS, "별칭 상수가 갈렸다"
    assert set(export.CSV_COLUMNS) == set(export.EXPORT_KINDS)


def test_catalogue_has_exactly_47_entries():
    """카탈로그 자체가 47줄이다(테스트가 조용히 줄어들지 않게)."""
    assert len(_CATALOGUE) == 47
    assert [number for number, _f, _c in _CATALOGUE] == list(range(1, 48))


def test_every_catalogue_field_is_exported():
    """**47필드 소진 계약** — 카탈로그의 모든 필드가 5종 CSV 열 합집합 안에 있다."""
    exported = {column for columns in export.CSV_COLUMNS.values()
                for _header, column, _tag in columns}
    missing = [(number, field, column)
               for number, field, columns in _CATALOGUE
               for column in columns if column not in exported]
    assert not missing, f"CSV 에 안 실린 카탈로그 필드: {missing}"


def test_catalogue_entry_without_column_is_not_a_row_field():
    """컬럼이 비어 있는 항목(#47 총 건수)은 실제로 어느 모델에도 없는 값이다."""
    all_columns = {name for model in _MODELS.values()
                   for name in model.__table__.columns.keys()}
    for number, field, columns in _CATALOGUE:
        if columns:
            continue
        assert number == 47 and "totalElements" in field
        assert "total_elements" not in all_columns, "행 필드가 됐다면 CSV 에 실어야 한다"


@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_every_model_column_is_exported(kind):
    """모델의 업무 컬럼 전량이 그 kind 의 CSV 에 있다(공통 메타만 뺀다)."""
    wanted = set(_MODELS[kind].__table__.columns.keys()) - _COMMON_META
    exported = {column for _header, column, _tag in export.CSV_COLUMNS[kind]}
    assert wanted - exported == set(), f"{kind} 에서 빠진 컬럼: {sorted(wanted - exported)}"
    assert exported - wanted == set(), f"{kind} 에 없는 컬럼: {sorted(exported - wanted)}"


@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_common_meta_is_never_exported(kind):
    """``raw_snapshot``·``synced_at`` 같은 메타는 CSV 에 넣지 않는다."""
    exported = {column for _header, column, _tag in export.CSV_COLUMNS[kind]}
    assert not (exported & _COMMON_META), sorted(exported & _COMMON_META)


# ---------------------------------------------------------------------------
# 2. 헤더 — 1줄, 순서 고정
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_headers_are_pinned_in_contract_order(app, kind):
    """헤더는 정확히 1줄이고 **순서까지** 계약이다(회계 프로그램 매핑이 순서를 기억한다)."""
    rows = _parsed(kind)
    assert rows[0] == list(_PINNED_HEADERS[kind]), f"{kind} 헤더 드리프트"
    assert len(rows) == 1, "시드가 없는데 데이터 행이 나왔다"


@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_header_row_matches_column_spec(app, kind):
    """실제로 내보낸 헤더가 :data:`CSV_COLUMNS` 와 같다(핀과 스펙이 함께 움직이는지)."""
    spec = [header for header, _column, _tag in export.CSV_COLUMNS[kind]]
    assert _parsed(kind)[0] == spec


@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_headers_are_unique_within_one_file(kind):
    """한 파일 안에서 헤더 이름이 겹치지 않는다(임포터가 열을 못 고른다)."""
    headers = [header for header, _column, _tag in export.CSV_COLUMNS[kind]]
    assert len(headers) == len(set(headers)), "중복 헤더"


# ---------------------------------------------------------------------------
# 3. 인코딩 — BOM · CRLF
# ---------------------------------------------------------------------------
def test_first_line_carries_utf8_bom(app):
    """첫 줄이 UTF-8 BOM 으로 시작한다 — 없으면 한글이 깨져서 열린다."""
    _seed_case()
    lines = _lines("settle_case")
    assert lines[0].startswith("﻿")
    assert "".join(lines).encode("utf-8").startswith(b"\xef\xbb\xbf")


def test_bom_appears_exactly_once(app):
    """BOM 은 파일 선두 1회뿐이다(줄마다 붙으면 첫 열이 통째로 깨진다)."""
    _seed_case()
    body = "".join(_lines("settle_case"))
    assert body.count("﻿") == 1


@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_every_line_ends_with_crlf(app, kind):
    """모든 줄이 ``\\r\\n`` 으로 끝난다."""
    _SEEDERS[kind]()
    lines = _lines(kind)
    assert len(lines) == 2
    assert all(line.endswith("\r\n") for line in lines), "CRLF 아님"
    assert not any(line[:-2].endswith("\r") for line in lines), "빈 줄이 끼었다"


# ---------------------------------------------------------------------------
# 4. 값 서식 — 부호 보존 · 마스킹 · 라벨
# ---------------------------------------------------------------------------
def test_negative_amount_keeps_its_sign(app):
    """취소 행의 음수가 ``-389000`` 그대로 나온다(절대값·괄호·콤마 금지)."""
    _seed_case()
    cells = _row_map("settle_case")
    assert cells["결제 정산 금액"] == "-389000"
    assert "," not in cells["결제 정산 금액"]
    assert "(" not in cells["결제 정산 금액"]


def test_decimal_fraction_is_not_dropped(app):
    """소수부가 있으면 버리지 않는다(버림은 회계에서 조용한 손실이다)."""
    _seed_case(pay_settle_amount=Decimal("1234.56"))
    assert _row_map("settle_case")["결제 정산 금액"] == "1234.56"


def test_empty_amount_is_a_blank_cell(app):
    """빈 금액은 빈 칸이다 — ``0`` 으로 그리면 없는 사실을 말하는 것이다."""
    _seed_case(settle_expect_amount=None)
    assert _row_map("settle_case")["정산 예정 금액"] == ""


def test_dates_are_iso_and_missing_dates_are_blank(app):
    """날짜는 ``YYYY-MM-DD``, 빈 값은 빈 칸(``-`` 금지)."""
    _seed_case(settle_complete_date=None)
    cells = _row_map("settle_case")
    assert cells["정산 예정일"] == "2026-09-01"
    assert cells["정산 완료일"] == ""


def test_account_no_is_masked_in_csv(app):
    """계좌번호는 CSV 에서도 뒤 4자리만 — 화면만 가리는 구멍을 만들지 않는다."""
    _seed_daily()
    cells = _row_map("settle_daily")
    assert cells["계좌번호(마스킹)"] == kernel.mask_account_no(_ACCOUNT_NO) == "****7890"
    assert _ACCOUNT_NO not in "".join(_lines("settle_daily"))


def test_missing_account_no_is_blank(app):
    """충전금 상계 행(계좌 없음)은 빈 칸이다."""
    _seed_daily(settle_method_type="CHARGE_AMT", bank_type=None, account_no=None,
                depositor_name=None)
    assert _row_map("settle_daily")["계좌번호(마스킹)"] == ""


def test_enum_columns_carry_code_and_label(app):
    """enum 은 코드 열 + 한글 라벨 열 2개다. 라벨은 카탈로그 값과 정확히 같다."""
    _seed_case()
    cells = _row_map("settle_case")
    assert cells["정산 구분(settleType)"] == "NORMAL_SETTLE_AFTER_CANCEL"
    assert cells["정산 구분명"] == settle_enums.SETTLE_TYPES["NORMAL_SETTLE_AFTER_CANCEL"]
    assert cells["정산 대상 구분(productOrderType)"] == "PROD_ORDER"
    assert cells["정산 대상 구분명"] == settle_enums.PRODUCT_ORDER_TYPES["PROD_ORDER"]


def test_unknown_enum_code_falls_back_to_the_code(app):
    """카탈로그에 없는 코드는 코드 그대로 — 빈칸으로 감추지 않는다."""
    _seed_case(settle_type="SOME_FUTURE_TYPE")
    cells = _row_map("settle_case")
    assert cells["정산 구분(settleType)"] == "SOME_FUTURE_TYPE"
    assert cells["정산 구분명"] == "SOME_FUTURE_TYPE"


def test_boolean_column_is_y_or_n(app):
    """확정 여부는 ``Y``/``N``(잠정치를 확정처럼 보여주지 않는다)."""
    _seed_vat_daily(is_final=True)
    assert _row_map("vat_daily")["확정 여부"] == "Y"


def test_every_enum_label_column_has_a_catalogue(app):
    """라벨 열마다 카탈로그가 있다(없으면 렌더 시점에 KeyError)."""
    for kind, columns in export.CSV_COLUMNS.items():
        for header, column, tag in columns:
            if tag == "enum_label":
                assert column in export._ENUM_MAPS, (kind, header, column)


# ---------------------------------------------------------------------------
# 5. 파일명 — ASCII
# ---------------------------------------------------------------------------
def test_filename_is_ascii_and_dated():
    """파일명은 ASCII 만 쓴다(한글 파일명은 RFC 5987 인코딩 함정에 걸린다)."""
    name = export.export_filename("settle_case", datetime.date(2026, 8, 3),
                                  datetime.date(2026, 9, 2))
    assert name == "naver_settle_case_20260803_20260902.csv"
    assert name.isascii()


@pytest.mark.parametrize("kind", export.EXPORT_KINDS)
def test_filename_is_ascii_for_every_kind(kind):
    """5종 전부 ASCII 파일명이고 ``.csv`` 로 끝난다."""
    name = export.export_filename(kind, _DAY, _DAY)
    assert name.isascii() and name.endswith(".csv"), name
    assert name.startswith("naver_settle_")


def test_filename_alias_is_the_same_function():
    """계약서 초안 이름(``csv_filename``)이 같은 함수다."""
    assert export.csv_filename is export.export_filename
    assert export.iter_settlement_csv is export.iter_csv_lines


def test_filename_rejects_unknown_kind():
    """허용 밖 종류는 파일명 단계에서 막힌다."""
    with pytest.raises(ValueError):
        export.export_filename("bogus", _DAY, _DAY)


# ---------------------------------------------------------------------------
# 6. 파라미터 검증 — 구간 상한은 커널과 같은 상수
# ---------------------------------------------------------------------------
def test_span_over_max_range_raises_korean_value_error(app):
    """구간 폭이 상한을 넘으면 한글 사유의 :class:`ValueError`."""
    start = datetime.date(2026, 1, 1)
    too_wide = start + datetime.timedelta(days=kernel.MAX_RANGE_DAYS)
    with pytest.raises(ValueError) as excinfo:
        export.iter_csv_lines(db_session, kind="settle_case",
                              date_from=start, date_to=too_wide)
    message = str(excinfo.value)
    assert str(kernel.MAX_RANGE_DAYS) in message
    assert any("가" <= ch <= "힣" for ch in message), f"한글 사유가 아니다: {message}"


def test_max_range_boundary_is_allowed(app):
    """상한 **정확히** 400일은 통과한다(경계에서 한 칸 어긋나지 않게)."""
    start = datetime.date(2026, 1, 1)
    edge = start + datetime.timedelta(days=kernel.MAX_RANGE_DAYS - 1)
    assert export.iter_csv_lines(db_session, kind="settle_case",
                                 date_from=start, date_to=edge) is not None


def test_max_range_days_is_the_kernel_constant():
    """새 상한을 발명하지 않고 조회 커널의 상수를 그대로 쓴다."""
    assert kernel.MAX_RANGE_DAYS == 400
    assert "MAX_RANGE_DAYS" in _module_source()


def test_reversed_range_raises(app):
    """시작일이 종료일보다 뒤면 거절한다."""
    with pytest.raises(ValueError):
        export.iter_csv_lines(db_session, kind="settle_case",
                              date_from=_DAY, date_to=_DAY - datetime.timedelta(days=1))


@pytest.mark.parametrize("kind", ["", None, "bogus", "vat", "settle"])
def test_unknown_kind_raises_at_call_time(app, kind):
    """허용 밖 종류는 **호출 시점에** 터진다(스트림이 시작된 뒤면 반쪽 파일이 내려간다)."""
    with pytest.raises(ValueError):
        export.iter_csv_lines(db_session, kind=kind, date_from=_DAY, date_to=_DAY)


def test_short_kind_aliases_resolve(app):
    """계약서 초안의 짧은 이름(``case``·``daily``)도 같은 파일을 낸다."""
    assert export.normalize_kind("case") == "settle_case"
    assert export.normalize_kind("daily") == "settle_daily"
    assert export.export_filename("case", _DAY, _DAY) == \
        export.export_filename("settle_case", _DAY, _DAY)


def test_filter_is_refused_where_it_has_no_meaning(app):
    """일자 단위 표는 유형·검색 조건을 받지 않는다 — 조용히 버리면 화면과 다른 파일이 나간다."""
    with pytest.raises(ValueError):
        export.iter_csv_lines(db_session, kind="vat_daily", date_from=_DAY,
                              date_to=_DAY, filters={"q": "2026"})
    assert export.FILTER_FIELDS["vat_daily"] == ((), ())


def test_filter_narrows_the_rows(app):
    """건별 정산은 검색어를 받는다(원장 화면과 같은 필드)."""
    _seed_case()
    _seed_case(order_id="9999", product_order_id="9998")
    assert len(_parsed("settle_case", filters={"q": "9998"})) == 2


# ---------------------------------------------------------------------------
# 7. 스트리밍 · 축
# ---------------------------------------------------------------------------
def test_header_line_does_not_run_the_query(app):
    """첫 줄(헤더)만 받아도 조회가 일어나지 않는다 — 전량 적재 금지의 실측."""
    _seed_case()
    stream = export.iter_csv_lines(db_session, kind="settle_case",
                                   date_from=_DAY, date_to=_DAY)
    (first, count) = _count_queries(lambda: next(iter(stream)))
    assert first.startswith("﻿")
    assert count == 0, f"헤더를 내는 데 SQL 이 {count}회 돌았다"


def test_rows_are_scoped_to_the_range(app):
    """구간 밖 행은 나오지 않는다(축은 조회 커널과 같은 되돌림 순서)."""
    _seed_case()
    _seed_case(order_id="2026080100000", product_order_id="2026080100001",
               settle_expect_date=datetime.date(2026, 8, 1),
               search_date=datetime.date(2026, 8, 1))
    assert len(_parsed("settle_case")) == 2


def test_rows_are_scoped_to_the_channel(app):
    """다른 채널 행은 섞이지 않는다."""
    _seed_case()
    _seed_case(channel="OTHER", order_id="X", product_order_id="Y")
    assert len(_parsed("settle_case")) == 2


def test_basis_column_map_matches_the_kernel():
    """기준일 축 표가 조회 커널과 한 글자도 다르지 않다 — 갈리면 화면에서 본 행이 파일에 없다."""
    assert export._BASIS_COLUMN == kernel._BASIS_COLUMN


def test_build_export_rows_yields_cells_in_column_order(app):
    """:func:`build_export_rows` 는 헤더 없이 셀 목록만 낸다(라우트가 헤더를 두 번 쓰지 않게)."""
    _seed_vat_daily()
    rows = list(export.build_export_rows(db_session, kind="vat_daily",
                                         date_from=_DAY, date_to=_DAY))
    assert len(rows) == 1
    assert len(rows[0]) == len(export.CSV_COLUMNS["vat_daily"])
    assert rows[0][0] == "2026-09-01"


# ---------------------------------------------------------------------------
# 8. 금지 계약 — 표 계산 라이브러리 · 한글 라벨 하드코딩 · 감사 라벨
# ---------------------------------------------------------------------------
def _code_identifiers(tree: ast.AST) -> set[str]:
    """소스의 식별자 전부(이름·속성·인자·import 별칭). 주석·docstring 은 코드가 아니다."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name)
    return names


def test_export_module_uses_only_stdlib_csv_serialization():
    """직렬화는 표준 라이브러리 ``csv``·``io`` 뿐이다 — 새 의존성 0(계약 §1.3 C1)."""
    tree = ast.parse(_module_source())
    imported = {alias.name.split(".")[0]
                for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {(node.module or "").split(".")[0]
                 for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert {"csv", "io"} <= imported, sorted(imported)
    assert not (imported & set(_FORBIDDEN_LIBS)), sorted(imported & set(_FORBIDDEN_LIBS))


def test_export_module_names_no_spreadsheet_library():
    """식별자·문자열 상수 어디에도 금지 낱말이 없다(설명하는 docstring·주석은 예외).

    이름을 쓰지 않는 것 자체가 계약이다(§1.3 C2 잔존 grep 0) — 다만 "왜 안 쓰는가"를
    적어 둔 문서 줄까지 지우면 다음 사람이 같은 유혹에 다시 빠진다.
    """
    tree = ast.parse(_module_source())
    docstrings = {node.body[0].value.value for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant)
                  and isinstance(node.body[0].value.value, str)}
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    haystack = _code_identifiers(tree) | (literals - docstrings)
    found = sorted(text for text in haystack
                   if any(word in str(text).lower() for word in _FORBIDDEN_WORDS))
    assert not found, f"금지 낱말 재등장: {found}"


def test_no_module_under_foms_imports_a_spreadsheet_library():
    """``foms/`` 어디에서도 ``pandas``·``openpyxl`` 을 import 하지 않는다(계약 §1.3 C1)."""
    offenders: list[str] = []
    for path in (_REPO_ROOT / "foms").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0].lower() in _FORBIDDEN_LIBS:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}: {name}")
    assert not offenders, offenders


def test_requirements_has_no_spreadsheet_library():
    """``requirements.txt`` 에도 되붙지 않았다 — 2026-09-01 에 뗀 2줄이다."""
    lines = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    packages = {line.split("==")[0].split(">=")[0].split("[")[0].strip().lower()
                for line in lines if line.strip() and not line.lstrip().startswith("#")}
    assert not (packages & set(_FORBIDDEN_LIBS)), sorted(packages & set(_FORBIDDEN_LIBS))


def test_no_file_under_foms_is_named_after_a_spreadsheet():
    """파일 이름에도 그 낱말을 쓰지 않는다(잔존 grep 0 계약, §1.3 C2)."""
    named = [str(path.relative_to(_REPO_ROOT))
             for path in (_REPO_ROOT / "foms").rglob("*.py")
             if any(word in path.name.lower() for word in _FORBIDDEN_WORDS)]
    assert not named, named


def test_module_hardcodes_no_enum_code():
    """enum 코드 리터럴이 0건이다 — 코드를 적었다면 라벨 표를 손으로 다시 만든 것이다."""
    codes = {code for name in settle_enums.__all__
             if isinstance(getattr(settle_enums, name), dict)
             for code in getattr(settle_enums, name)}
    tree = ast.parse(_module_source())
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not (literals & codes), sorted(literals & codes)


def test_audit_action_label_is_registered():
    """다운로드 감사 코드에 업무 라벨이 있다(없으면 감사 화면에 영문 코드가 뜬다)."""
    assert ACTION_LABELS[_AUDIT_ACTION] == "네이버 정산 CSV 내보내기"
