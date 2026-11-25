"""PRODPART-02: 한 도면 · 한 파트를 여러 명이 같이 작업 — production_part_marks.holders(작업하는 사람 목록)

Revision ID: prodpart_02_holders
Revises: prodlead_02
Create Date: 2026-11-25

설계 정본: ``docs/specs/2026-11-25-production-multi-holder_SPEC.md`` §4(안 ⓒ — 표시 줄 안 JSON 목록) · Q18 ②.

표시 줄(도면 한 장 × 파트 하나에 한 줄)은 그대로 두고, 그 줄 안에 작업하는 사람 목록
``[{uid, name, at, done_at, done_uid, done_name}]`` 을 더한다. 상태 칸 · 한 명짜리 칸은 목록의 요약으로 계속 쓴다(모두 완료 = DONE) —
완료 판정 · 공정 칸 동기화 · 공장 완료는 한 줄도 안 바뀐다. 같은 줄에 실려 오므로 생산 화면 쿼리 수가 늘지 않는다.

upgrade: 칸 하나를 더한다 — ``holders`` JSON(PG = JSONB) NULL. **채우지 않는다**(지휘 결정 Q18 ② — 운영 표시 줄은 몇 줄뿐): NULL
이면 앱이 읽을 때 요약 칸에서 푼다(``foms.services.production.mark_crew.crew_of``), 옛 줄에 처음 쓰는 순간 목록이 찬다. 기본값 ·
채우기 · 색인 · 제약이 없는 NULL 칸이라 PG 는 표를 다시 쓰지 않는다(메타만 바뀜, 잠금 짧음).

downgrade: 칸을 지운다 — 같이 작업하던 둘째 이후 사람이 사라진다(요약 칸은 늘 맞게 쓰여 있어 옛 코드는 첫 사람을 담당으로 본다 —
설계서 §10 '되돌리기'). 옛 코드는 이 칸을 읽지 않으므로 칸이 남아 있어도 무시한다(커밋 되돌리기만 하고 downgrade 는 골라서 해도
된다). 되돌리기 전에 목록이 둘 이상인 줄 수를 세어 반장에게 알린다(운영 절차).

server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합. 칸 꼴은 models.py ``ProductionPartMark.holders``
와 같다(시험 ``tests/domains/test_production_mark_crew.py`` · PG 왕복 ``tests/postgres/test_migration_chain.py``). 마이그레이션
상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'prodpart_02_holders'
down_revision: Union[str, None] = 'prodlead_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'production_part_marks'
COLUMN = 'holders'
# models.JSONColumn 과 같은 꼴을 리터럴로(모델 import 금지 — 상수 동결, prodparts_01 과 같다).
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    """표시 줄에 작업하는 사람 목록 칸(NULL 허용, 채우기 없음)."""
    op.add_column(TABLE, sa.Column(COLUMN, JSON_TYPE, nullable=True))


def downgrade() -> None:
    """목록 칸을 지운다."""
    op.drop_column(TABLE, COLUMN)
