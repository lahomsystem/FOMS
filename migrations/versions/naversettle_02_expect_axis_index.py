"""CFO 감사 H-01: 정산 창 술어 COALESCE 식 인덱스 2종 (case·commission)

Revision ID: naversettle_02
Revises: naversettle_01
Create Date: 2026-09-06

왜 필요한가
-----------
채널 대시보드·요약 스트립의 구간 술어(``foms.services.settlement_channel._case_scope`` ·
``_commission_scope``)는 ``COALESCE(settle_expect_date, search_date)`` 축으로 창을 자른다
(예정일이 아직 안 잡힌 미확정 행이 조용히 빠지지 않게 조회일로 되돌린다). 그런데
``naversettle_00`` 이 만든 인덱스는 전부 ``search_date`` 단일 컬럼 축이라 이 식을 받지 못한다.
감사 H-01 실측(스테이징 PG 17.11): case 창 질의 4종(30일·1년 창) 전부 Seq Scan 1.8~5.9ms
(6,303행 8.7MB), commission 4.98ms. 음성 대조군 — 같은 창을 ``search_date BETWEEN`` 으로
주면 ``ix_nsc_unmatched`` Index Scan 0.49ms → COALESCE 가 원인이다. 체감은 ms 단위지만
프로젝트 규칙 "hot path Seq Scan 없음" 위반이고 행 수에 선형이다(정산 행은 관측
1,284행/월로 계속 늘어난다).

왜 이 모양인가
--------------
* **식 인덱스 ``(channel, COALESCE(settle_expect_date, search_date))``**: 조회가 항상 채널을
  함께 고정하고, 둘째 열은 커널 술어의 식과 **문자 그대로(인자 순서까지) 같다** — PG 플래너는
  표현식 트리가 정확히 일치할 때만 식 인덱스를 고른다. 술어를 ``search_date`` 로 바꾸는
  우회는 의미가 달라져(미확정 행 누락) 비권고다.
* 두 표(case·commission) 각 1개 — 요약 스트립 6문장 중 case 3문장이 이 술어다.
* 부분 인덱스가 아니다: 창 술어는 match_status 와 무관하게 전 행을 훑는다.

같은 인덱스가 ``models.py`` 의 두 ``__table_args__`` 에도 선언돼 있다(create_all 베이스라인이
models 라 PG 레인 왕복·신규 부트스트랩이 같은 스키마를 만들게). 인자 순서 회귀는
``tests/domains/test_naversettle_expect_axis_index.py`` 가 잡는다.

상수 동결: ``models`` 를 import 하지 않는다 — 표·인덱스 이름·식을 리터럴로 적는다.
(모델이 나중에 바뀌어도 이 마이그레이션의 결과는 그대로여야 한다.)

``downgrade()`` 는 인덱스만 지운다. 데이터 손실이 없는 완전 가역 변경이다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'naversettle_02'
down_revision: Union[str, None] = 'naversettle_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T_SETTLE_CASE = 'naver_settle_case'
T_SETTLE_COMMISSION = 'naver_settle_commission'
IX_CASE_AXIS = 'ix_nsc_channel_expect_axis'
IX_COMMISSION_AXIS = 'ix_nscm_channel_expect_axis'
#: 커널 술어(``_case_scope``·``_commission_scope``)의 식과 인자 순서까지 같아야 플래너가 탄다.
AXIS_EXPR = 'COALESCE(settle_expect_date, search_date)'


def upgrade() -> None:
    """창 술어 식 인덱스 2종을 만든다(스키마 확장만, 데이터 변경 0)."""
    op.create_index(IX_CASE_AXIS, T_SETTLE_CASE, ['channel', sa.text(AXIS_EXPR)])
    op.create_index(IX_COMMISSION_AXIS, T_SETTLE_COMMISSION, ['channel', sa.text(AXIS_EXPR)])


def downgrade() -> None:
    """인덱스 2개를 걷어낸다. 행은 건드리지 않으므로 손실 없이 되돌아간다."""
    op.drop_index(IX_COMMISSION_AXIS, table_name=T_SETTLE_COMMISSION)
    op.drop_index(IX_CASE_AXIS, table_name=T_SETTLE_CASE)
