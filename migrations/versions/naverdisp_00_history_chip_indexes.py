"""external_order_links: 이력 탭 칩 숫자용 부분 인덱스 2벌.

왜: 이력 탭은 렌더마다 칩 숫자를 센다 — ``_dispatch_pending_group_count(db)`` 와
``_relation_group_count(db)`` 가 매 요청 ``external_order_links`` 를 훑는다. 앞의 것은
술어가 JSONB 두 경로(``triage_state -> 'fulfillment' ->> 'dispatched_at'``,
``raw_snapshot -> 'delivery' ->> 'sendDate'``)를 타서, 인덱스가 없으면 전수 Seq Scan 이
확정이다 — 이 저장소의 hot path JSONB 스캔 금지 규칙에 정면으로 걸린다. 바로 옆
``_place_pending_clause()`` 가 같은 이유로 일부러 컬럼만 보게 만들어져 있다.

두 인덱스 모두 ``(channel, group_key)`` 를 담는다 — 세는 쿼리가
``WHERE channel = 'NAVER' AND <술어> GROUP BY <묶음키>`` 모양이라, 채널로 좁히고 묶음키로
모으는 그 순서 그대로다(기존 ``ix_external_order_link_group`` 과 같은 자리).

**조건식은 손으로 적은 것이 아니다.** ``_dispatch_pending_clause()`` 를 PostgreSQL 방언으로
``literal_binds`` 렌더한 문자열에서 테이블 수식어만 뗀 것이다::

    str(_dispatch_pending_clause().compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

``models.JSONColumn`` 의 베이스 타입이 ``JSON`` 이라(``JSON().with_variant(JSONB, …)``)
``.as_string()`` 이 ``CAST(… AS VARCHAR)`` 를 붙인다. 인덱스 조건식이 그 모양이 아니면
PostgreSQL 이 부분 인덱스를 증명하지 못해 통째로 무시하고, 그때 나오는 Seq Scan 은
"선택도가 낮아서"로 오독된다(2026-08-30 CEO 지적 1). 술어를 고치면 이 파일이 아니라 새
마이그레이션으로 인덱스를 다시 만들어야 한다.

테이블 수식어(``external_order_links.``)만 뗀 이유: ``CREATE INDEX`` 의 ``WHERE`` 는 그
테이블 컬럼만 가리키므로 수식어를 붙이지 않는 것이 정상 표기이고, PostgreSQL 이 저장하는
파스 트리도 어차피 수식어가 없다(같은 식으로 남는다).

**``models`` 를 import 하지 않는다** — 마이그레이션 상수 동결 원칙. live import 하면 나중에
술어가 바뀔 때 이 과거 마이그레이션이 소급 오염된다. 조건식은 위 렌더 결과를 문자열로 박는다.

**``models.py`` 의 ``__table_args__`` 에는 넣지 않는다.** 선례가 있다 —
``ix_external_order_link_fulfillment_error`` 도 마이그레이션에만 있다. 같은 자리를 따른다.

PostgreSQL 전용이다. SQLite 레인은 JSONB 연산자도 부분 인덱스 조건식도 없어 그대로
건너뛴다(테스트 레인은 데이터가 작아 인덱스가 없어도 동작이 같다).

Revision ID: naverdisp_00
Revises: merge_drawq_naverfail
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = 'naverdisp_00'
down_revision = 'merge_drawq_naverfail'
branch_labels = None
depends_on = None

DISPATCH_INDEX = 'ix_external_order_link_dispatch_pending'
RELATION_INDEX = 'ix_external_order_link_relation_pair'

# _dispatch_pending_clause() 렌더 결과 그대로(테이블 수식어만 제거).
DISPATCH_SQL = f"""
CREATE INDEX IF NOT EXISTS {DISPATCH_INDEX}
    ON external_order_links (channel, group_key)
    WHERE coalesce(CAST(((triage_state -> 'fulfillment') ->> 'dispatched_at') AS VARCHAR), '') = ''
      AND coalesce(CAST(((raw_snapshot -> 'delivery') ->> 'sendDate') AS VARCHAR), '') = ''
"""

# _relation_clause() 렌더 결과 그대로(테이블 수식어만 제거).
RELATION_SQL = f"""
CREATE INDEX IF NOT EXISTS {RELATION_INDEX}
    ON external_order_links (channel, group_key)
    WHERE relation IN ('ADDON', 'REPAY')
"""


def upgrade() -> None:
    """이력 탭 칩 2종의 모집단만 담는 부분 인덱스를 만든다(PostgreSQL 전용).

    Returns:
        None. PostgreSQL 이 아니면 아무것도 하지 않고 돌아간다.
    """
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute(sa.text(DISPATCH_SQL))
    op.execute(sa.text(RELATION_SQL))


def downgrade() -> None:
    """두 인덱스를 되돌린다(파생 구조라 잃어도 데이터는 그대로다).

    Returns:
        None. PostgreSQL 이 아니면 아무것도 하지 않고 돌아간다.
    """
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute(sa.text(f'DROP INDEX IF EXISTS {RELATION_INDEX}'))
    op.execute(sa.text(f'DROP INDEX IF EXISTS {DISPATCH_INDEX}'))
