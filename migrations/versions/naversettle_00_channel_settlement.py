"""SETTLE-CHANNEL-01 T-A1: 채널(네이버) 정산 적재 테이블 6종

Revision ID: naversettle_00
Revises: wizsend_00
Create Date: 2026-09-02

네이버 커머스API ``/v1/pay-settle/*`` 5개 엔드포인트의 응답을 담는 적재 테이블 5개와
동기화 실행 이력 1개를 만든다(``models.NaverSettleDaily`` 외 5클래스와 SSOT 공유 —
create_all 테스트 레인과 같은 스키마여야 한다).

설계 근거(왜 이 모양인가)
-------------------------
* **UNIQUE 멱등 키가 없다.** 다른 수집 테이블(``external_order_links``)과 다른 점이다.
  네이버 정산은 확정 전까지 **소급해서 바뀐다**(행이 사라지기도 한다). upsert 로 누적하면
  네이버 쪽에서 없어진 행이 우리 DB 에만 영원히 남아 합계가 어긋난다. 그래서 적재는
  "``channel`` + 축 날짜 파티션을 통째로 지우고 다시 넣는다"이고, 멱등성은 그 규칙이
  담보한다. 인덱스가 (channel, 축날짜)로 시작하는 것은 조회 경로이자 그 삭제 경로다.
* **금액은 ``NUMERIC(16, 2)``.** ``FLOAT`` 로 두면 합계가 원 단위에서 흔들려 네이버
  정산서와 대사가 불가능해진다. 취소·환급 행은 음수로 들어오며 부호를 그대로 보존한다.
* **날짜는 ``DATE``.** 네이버가 주는 KST 달력일 그대로다. ``TIMESTAMP`` 로 승격하면
  naive=UTC 저장 규약과 섞여 경계일이 하루씩 밀린다.
* **FK 가 없다.** ``naver_settle_case.foms_order_id``/``link_id``, 각 표의 ``sync_run_id``,
  ``naver_settle_sync_runs.actor_user_id`` 는 전부 소프트 참조다. 주문·링크·사용자·실행이력이
  지워져도 "네이버가 정산했다"는 사실은 남아야 하고, 반대로 정산 적재가 그 삭제를 막아서도
  안 된다.
* ``ix_nsc_unmatched`` 는 **미매칭 행만** 담는 부분 인덱스다. 매칭이 끝난 대다수 행이 인덱스에서
  빠지므로 이력이 쌓여도 예외 목록 조회가 함께 느려지지 않는다(``external_order_links`` 의
  ``ix_external_order_link_pending_review`` 와 같은 규율). SQLite 레인에서는 ``postgresql_where``
  가 무시돼 일반 인덱스가 되며, 그쪽은 성능이 아니라 동작만 보므로 문제되지 않는다.

상수 동결: ``models`` 를 import 하지 않는다 — 테이블·컬럼·인덱스 이름을 리터럴로 반복한다.
(모델이 나중에 바뀌면 과거 마이그레이션의 결과가 소급해서 달라지는 것을 막는다.)

``downgrade()`` 는 생성 역순(인덱스 → 테이블)으로 걷어낸다. 이 테이블들은 네이버에서 다시
받아올 수 있는 **파생 데이터**만 담으므로(원장 정본은 네이버 쪽) drop 해도 복구 가능하다 —
단 동기화 게이트를 끈 상태에서만 수행한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'naversettle_00'
down_revision: Union[str, None] = 'wizsend_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# models.JSONColumn 과 같은 형태를 리터럴로 재현한다(모델 import 금지 — 상수 동결).
_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')

T_SETTLE_DAILY = 'naver_settle_daily'
T_SETTLE_CASE = 'naver_settle_case'
T_SETTLE_COMMISSION = 'naver_settle_commission'
T_VAT_DAILY = 'naver_vat_daily'
T_VAT_CASE = 'naver_vat_case'
T_SYNC_RUNS = 'naver_settle_sync_runs'


def _money(name: str) -> sa.Column:
    """금액 컬럼 1개를 만든다(NUMERIC(16, 2), NULL 허용).

    Args:
        name: 컬럼 이름(네이버 응답 필드의 snake_case 형).

    Returns:
        ``sa.Column`` — 정밀도 16·소수 2자리. NULL 허용인 것은 네이버가 필드를 생략해서
        보내는 경우가 있고, 그때 0 으로 채우면 "값이 없음"과 "0원"이 구분되지 않기 때문이다.
    """
    return sa.Column(name, sa.Numeric(16, 2), nullable=True)


def _common_load_columns() -> list:
    """적재 5표의 공통 꼬리 컬럼(원본 스냅샷·동기화 시각·실행 참조).

    Returns:
        ``raw_snapshot``(NOT NULL, JSON/JSONB), ``synced_at``(NOT NULL), ``sync_run_id``(NULL,
        FK 없는 소프트 참조) 컬럼 리스트.
    """
    return [
        sa.Column('raw_snapshot', _JSON_TYPE, nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
    ]


def _channel_column() -> sa.Column:
    """판매채널 코드 컬럼(v1 은 'NAVER' 뿐이지만 컬럼으로 둬 채널 확장을 막지 않는다)."""
    return sa.Column('channel', sa.String(20), nullable=False, server_default='NAVER')


def _create_settle_daily() -> None:
    """naver_settle_daily(일자별 정산) 생성 — 파티션 축 ``settle_expect_date``."""
    op.create_table(
        T_SETTLE_DAILY,
        sa.Column('id', sa.Integer(), primary_key=True),
        _channel_column(),
        sa.Column('settle_basis_start_date', sa.Date(), nullable=True),
        sa.Column('settle_basis_end_date', sa.Date(), nullable=True),
        sa.Column('settle_expect_date', sa.Date(), nullable=False),
        sa.Column('settle_complete_date', sa.Date(), nullable=True),
        _money('settle_amount'),
        _money('pay_settle_amount'),
        _money('commission_settle_amount'),
        _money('benefit_settle_amount'),
        _money('deduction_restore_settle_amount'),
        _money('pay_holdback_amount'),
        _money('minus_charge_amount'),
        _money('difference_settle_amount'),
        _money('return_care_settle_amount'),
        _money('normal_settle_amount'),
        _money('quick_settle_amount'),
        _money('preferential_commission_amount'),
        _money('settlement_limit_amount'),
        sa.Column('settle_method_type', sa.String(20), nullable=True),
        sa.Column('bank_type', sa.String(40), nullable=True),
        sa.Column('depositor_name', sa.String(100), nullable=True),
        sa.Column('account_no', sa.String(60), nullable=True),
        sa.Column('merchant_id', sa.String(40), nullable=True),
        sa.Column('merchant_name', sa.String(100), nullable=True),
        *_common_load_columns(),
    )
    op.create_index('ix_nsd_channel_expect', T_SETTLE_DAILY,
                    ['channel', 'settle_expect_date'])


def _create_settle_case() -> None:
    """naver_settle_case(건별 정산) 생성 — 파티션 축 ``search_date`` + ``period_type``."""
    op.create_table(
        T_SETTLE_CASE,
        sa.Column('id', sa.Integer(), primary_key=True),
        _channel_column(),
        sa.Column('search_date', sa.Date(), nullable=False),
        sa.Column('period_type', sa.String(48), nullable=False),
        sa.Column('settle_basis_date', sa.Date(), nullable=True),
        sa.Column('settle_expect_date', sa.Date(), nullable=True),
        sa.Column('settle_complete_date', sa.Date(), nullable=True),
        sa.Column('pay_date', sa.Date(), nullable=True),
        sa.Column('order_id', sa.String(40), nullable=True),
        sa.Column('product_order_id', sa.String(40), nullable=True),
        sa.Column('product_order_type', sa.String(40), nullable=True),
        sa.Column('settle_type', sa.String(40), nullable=True),
        sa.Column('product_id', sa.String(40), nullable=True),
        sa.Column('product_name', sa.String(300), nullable=True),
        sa.Column('purchaser_name', sa.String(100), nullable=True),
        _money('pay_settle_amount'),
        _money('total_pay_commission_amount'),
        _money('free_installment_commission_amount'),
        _money('selling_interlock_commission_amount'),
        _money('benefit_settle_amount'),
        _money('settle_expect_amount'),
        sa.Column('merchant_id', sa.String(40), nullable=True),
        sa.Column('merchant_name', sa.String(100), nullable=True),
        sa.Column('contract_no', sa.String(60), nullable=True),
        # FOMS 매칭 축 — FK 없는 소프트 참조.
        sa.Column('foms_order_id', sa.Integer(), nullable=True),
        sa.Column('link_id', sa.Integer(), nullable=True),
        sa.Column('match_status', sa.String(20), nullable=False, server_default='NA'),
        *_common_load_columns(),
    )
    op.create_index('ix_nsc_channel_search', T_SETTLE_CASE, ['channel', 'search_date'])
    op.create_index('ix_nsc_product_order', T_SETTLE_CASE, ['product_order_id'])
    # 예외 목록(미매칭) 전용 부분 인덱스.
    op.create_index('ix_nsc_unmatched', T_SETTLE_CASE, ['channel', 'search_date'],
                    postgresql_where=sa.text("match_status = 'UNMATCHED'"))


def _create_settle_commission() -> None:
    """naver_settle_commission(건별 수수료 상세) 생성 — 행 단위는 상품주문 x 수수료 타입."""
    op.create_table(
        T_SETTLE_COMMISSION,
        sa.Column('id', sa.Integer(), primary_key=True),
        _channel_column(),
        sa.Column('search_date', sa.Date(), nullable=False),
        sa.Column('period_type', sa.String(48), nullable=False),
        # 네이버 원본이 orderNo 다(건별 정산의 orderId 와 이름이 다르다).
        sa.Column('order_no', sa.String(40), nullable=True),
        sa.Column('product_order_id', sa.String(40), nullable=True),
        sa.Column('product_order_type', sa.String(40), nullable=True),
        sa.Column('product_id', sa.String(40), nullable=True),
        sa.Column('product_name', sa.String(300), nullable=True),
        sa.Column('merchant_id', sa.String(40), nullable=True),
        sa.Column('merchant_name', sa.String(100), nullable=True),
        sa.Column('purchaser_name', sa.String(100), nullable=True),
        sa.Column('settle_type', sa.String(40), nullable=True),
        sa.Column('settle_basis_date', sa.Date(), nullable=True),
        sa.Column('settle_expect_date', sa.Date(), nullable=True),
        sa.Column('settle_complete_date', sa.Date(), nullable=True),
        sa.Column('tax_return_date', sa.Date(), nullable=True),
        _money('commission_basis_amount'),
        sa.Column('commission_type', sa.String(40), nullable=True),
        sa.Column('pay_means_type', sa.String(40), nullable=True),
        _money('commission_amount'),
        _money('maximum_selling_interlock_commission_amount'),
        *_common_load_columns(),
    )
    op.create_index('ix_nscm_channel_search', T_SETTLE_COMMISSION,
                    ['channel', 'search_date'])
    op.create_index('ix_nscm_product_order', T_SETTLE_COMMISSION, ['product_order_id'])


def _create_vat_daily() -> None:
    """naver_vat_daily(일자별 부가세) 생성 — 파티션 축 ``settle_basis_date``."""
    op.create_table(
        T_VAT_DAILY,
        sa.Column('id', sa.Integer(), primary_key=True),
        _channel_column(),
        sa.Column('settle_basis_date', sa.Date(), nullable=False),
        _money('total_sales_amount'),
        _money('taxation_sales_amount'),
        _money('tax_exemption_sales_amount'),
        _money('credit_card_amount'),
        # 원본 cashInComeDeductionAmount / cashOutGoingEvidenceAmount 의 snake_case 형.
        _money('cash_income_deduction_amount'),
        _money('cash_outgoing_evidence_amount'),
        _money('cash_exclusion_issuance_amount'),
        _money('other_amount'),
        sa.Column('merchant_id', sa.String(40), nullable=True),
        sa.Column('merchant_name', sa.String(100), nullable=True),
        sa.Column('is_final', sa.Boolean(), nullable=False, server_default='false'),
        *_common_load_columns(),
    )
    op.create_index('ix_nvd_channel_basis', T_VAT_DAILY,
                    ['channel', 'settle_basis_date'])


def _create_vat_case() -> None:
    """naver_vat_case(건별 부가세) 생성 — 금액 8종은 vat_daily 와 같은 이름."""
    op.create_table(
        T_VAT_CASE,
        sa.Column('id', sa.Integer(), primary_key=True),
        _channel_column(),
        sa.Column('settle_basis_date', sa.Date(), nullable=False),
        sa.Column('order_id', sa.String(40), nullable=True),
        sa.Column('product_order_id', sa.String(40), nullable=True),
        sa.Column('product_order_type', sa.String(40), nullable=True),
        sa.Column('detail_type', sa.String(50), nullable=True),
        sa.Column('status', sa.String(40), nullable=True),
        sa.Column('product_name', sa.String(300), nullable=True),
        _money('total_sales_amount'),
        _money('taxation_sales_amount'),
        _money('tax_exemption_sales_amount'),
        _money('credit_card_amount'),
        _money('cash_income_deduction_amount'),
        _money('cash_outgoing_evidence_amount'),
        _money('cash_exclusion_issuance_amount'),
        _money('other_amount'),
        sa.Column('merchant_id', sa.String(40), nullable=True),
        sa.Column('merchant_name', sa.String(100), nullable=True),
        *_common_load_columns(),
    )
    op.create_index('ix_nvc_channel_basis', T_VAT_CASE,
                    ['channel', 'settle_basis_date'])
    op.create_index('ix_nvc_product_order', T_VAT_CASE, ['product_order_id'])


def _create_sync_runs() -> None:
    """naver_settle_sync_runs(동기화 실행 이력) 생성 — 적재표의 공통 꼬리는 없다."""
    op.create_table(
        T_SYNC_RUNS,
        sa.Column('id', sa.Integer(), primary_key=True),
        _channel_column(),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        # RUNNING / OK / FAILED / ABORTED_QUOTA
        sa.Column('status', sa.String(20), nullable=False),
        # SCHEDULE / MANUAL / BACKFILL
        sa.Column('trigger', sa.String(20), nullable=False),
        # FK 없음 — 사용자가 지워져도 실행 이력은 남는다.
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('scope', _JSON_TYPE, nullable=False),
        sa.Column('stats', _JSON_TYPE, nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('dry_run', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_nssr_started', T_SYNC_RUNS, ['started_at'])


def upgrade() -> None:
    """정산 적재 5표 + 실행 이력 1표와 인덱스 9종을 만든다."""
    _create_settle_daily()
    _create_settle_case()
    _create_settle_commission()
    _create_vat_daily()
    _create_vat_case()
    _create_sync_runs()


def downgrade() -> None:
    """생성 역순으로 되돌린다(표마다 인덱스 → 테이블).

    담긴 데이터는 네이버에서 다시 받아올 수 있는 파생분이라 drop 해도 복구 가능하다.
    다만 동기화가 도는 중에 내리면 적재 트랜잭션이 깨지므로 게이트 off 상태에서만 수행한다.
    """
    op.drop_index('ix_nssr_started', table_name=T_SYNC_RUNS)
    op.drop_table(T_SYNC_RUNS)

    op.drop_index('ix_nvc_product_order', table_name=T_VAT_CASE)
    op.drop_index('ix_nvc_channel_basis', table_name=T_VAT_CASE)
    op.drop_table(T_VAT_CASE)

    op.drop_index('ix_nvd_channel_basis', table_name=T_VAT_DAILY)
    op.drop_table(T_VAT_DAILY)

    op.drop_index('ix_nscm_product_order', table_name=T_SETTLE_COMMISSION)
    op.drop_index('ix_nscm_channel_search', table_name=T_SETTLE_COMMISSION)
    op.drop_table(T_SETTLE_COMMISSION)

    op.drop_index('ix_nsc_unmatched', table_name=T_SETTLE_CASE)
    op.drop_index('ix_nsc_product_order', table_name=T_SETTLE_CASE)
    op.drop_index('ix_nsc_channel_search', table_name=T_SETTLE_CASE)
    op.drop_table(T_SETTLE_CASE)

    op.drop_index('ix_nsd_channel_expect', table_name=T_SETTLE_DAILY)
    op.drop_table(T_SETTLE_DAILY)
