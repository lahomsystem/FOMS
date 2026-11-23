"""PRODPART-01: 생산 파트 표시 줄 담당 바꾸기 기록 — production_part_marks.handed_from_name · handed_at

Revision ID: prodpart_01_handover
Revises: aistaff_00
Create Date: 2026-11-23

설계 정본: ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §3 · §6-4(사장님 승인 2026-11-23).

[담당 바꾸기]로 지금 담당이 누구에게서 · 언제 넘겨받았는지를 표시 줄에 남긴다(마지막 한 번 — 전체 목록은
``order_events``). 카드 · 날짜 줄 · 작업 시트 · PC 가 쿼리를 더하지 않고 "박엣지에서 바뀜 14:20" 을 그린다(이미 읽는 줄).

upgrade: 칸 둘을 더한다 — ``handed_from_name`` String(120) NULL · ``handed_at`` DateTime NULL. 기본값 · 채우기 · 색인 ·
제약이 없는 NULL 칸이라 PG 는 표를 다시 쓰지 않는다(메타만 바뀜, 잠금 짧음). 기존 줄은 모두 NULL(= 바뀐 적 없음)이다.

downgrade: 두 칸을 지운다 — 그 사이 쌓인 담당 바꾸기 요약이 사라진다(전체 기록은 이벤트에 남는다). 옛 코드는 두 칸을
읽지 않으므로 칸이 남아 있어도 무시한다(커밋 되돌리기만 하고 downgrade 는 골라서 해도 된다).

server_default 없음 — migration_chain 지문(models.py ↔ 마이그레이션 재생) 정합. 칸 정의는 models.py
``ProductionPartMark`` 와 같다(시험 ``tests/domains/test_production_part_marks_model.py`` 가 견준다).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'prodpart_01_handover'
down_revision: Union[str, None] = 'aistaff_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'production_part_marks'
#: (칸 이름, 꼴) — 순서 = upgrade 순서(downgrade 는 거꾸로).
COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ('handed_from_name', sa.String(length=120)),
    ('handed_at', sa.DateTime()),
)


def upgrade() -> None:
    """표시 줄에 담당 바꾸기 기록 칸 둘(NULL 허용, 채우기 없음)."""
    for name, type_ in COLUMNS:
        op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    """두 칸을 거꾸로 지운다."""
    for name, _type in reversed(COLUMNS):
        op.drop_column(TABLE, name)
