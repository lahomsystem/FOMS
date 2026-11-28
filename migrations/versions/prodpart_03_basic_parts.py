"""PRODPART-03: 조립 '조립 없음' — production_part_marks 의 BASIC 제약을 재단만 → 재단 · 조립만

Revision ID: prodpart_03_basic_parts
Revises: prodpart_02_holders
Create Date: 2026-11-28

설계 정본: ``docs/specs/2026-11-28-production-flow-three_SPEC.md`` §3-4 · §5(사장님 2026-11-28 "조립 없음" · "조립만").

조립할 것이 없는 도면을 조립 파트가 한 번 눌러 넘기는 [조립 없음]은 재단 [기본]과 같은 상태 값 ``BASIC`` 을 쓴다(끝났는지 판정이
한 함수라 검수 열림 · 제작 완료 · "조립 2/3" · 공정 칸이 같이 맞는다). 지금 제약은 ``BASIC`` 을 재단 줄에만 받는다 — 조립 줄도 받게
넓힌다. 엣지 · 검수는 계속 못 넣는다(앱 상수 ``part_constants.BASIC_ALLOWED_PARTS`` 가 잘못 넓어져도 DB 가 막는다 — 엣지에도 필요해지는
날에는 마이그레이션을 하나 더 만든다).

upgrade: 제약 ``ck_production_part_marks_basic_cut``(``state <> 'BASIC' OR part = 'cut'``)을 지우고
``ck_production_part_marks_basic_part``(``state <> 'BASIC' OR part IN ('cut', 'assemble')``)를 건다. 칸 · 색인 · 채우기 없음.
넓히는 쪽이라 지금 줄은 모두 새 제약을 지난다(PG 는 표를 한 번 훑어 확인만 — 표시 줄은 적다, 잠금 짧음). 옛 코드는 조립 BASIC 을
쓰지 않으므로 **마이그레이션 먼저 → 코드** 차례로 올려도 같이 돈다.

downgrade(차례가 있다): ① 조립 BASIC 줄을 완료(``DONE``)로 바꾼다 — 옛 제약은 그 줄이 있으면 걸리지 않는다. '조립 없음'은 '조립
완료'와 같게 세던 줄이라 완료로 바꿔도 검수 열림 · 제작 완료 판정이 그대로다(끝낸 사람 · 때 칸은 이미 누른 사람으로 차 있다 — 사람
없는 완료 줄이 된다). "조립 없음" 글자만 "조립 완료"로 읽힌다. ② 새 제약을 지우고 옛 제약을 다시 건다.
코드만 되돌리고 이 제약은 그대로 둬도 된다(옛 코드는 조립 BASIC 을 쓰지 않는다) — downgrade 는 골라서 한다.

두 DB 같은 꼴: ``batch_alter_table`` 하나로 쓴다 — PostgreSQL 은 ``ALTER TABLE … DROP/ADD CONSTRAINT`` 두 문, SQLite 는 CHECK 를
ALTER 로 못 바꿔 표를 다시 만든다(이름 있는 제약 · 색인 · 줄은 그대로 옮겨진다).

마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다(표 · 제약 이름 · 글 리터럴). 새 제약 이름 · 글은 models.py
``ProductionPartMark`` 와 글자 단위로 같다(시험 ``tests/domains/test_production_part_marks_model.py`` ·
``tests/domains/test_production_assemble_none_1128.py`` · PG 왕복 ``tests/postgres/test_migration_chain.py``).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'prodpart_03_basic_parts'
down_revision: Union[str, None] = 'prodpart_02_holders'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'production_part_marks'
OLD_CHECK = 'ck_production_part_marks_basic_cut'
OLD_CHECK_SQL = "state <> 'BASIC' OR part = 'cut'"
NEW_CHECK = 'ck_production_part_marks_basic_part'
NEW_CHECK_SQL = "state <> 'BASIC' OR part IN ('cut', 'assemble')"
#: downgrade ① — 옛 제약에 걸리는 줄(재단이 아닌 BASIC = 조립 없음)을 완료로.
DOWNGRADE_FIX_SQL = f"UPDATE {TABLE} SET state = 'DONE' WHERE state = 'BASIC' AND part <> 'cut'"


def _swap(drop_name: str, add_name: str, add_sql: str) -> None:
    """제약 하나를 지우고 하나를 건다(PG = ALTER 두 문 · SQLite = 표 다시 만들기)."""
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(drop_name, type_='check')
        batch.create_check_constraint(add_name, sa.text(add_sql))


def upgrade() -> None:
    """BASIC 을 재단 · 조립 줄에 받는다(넓힘 — 지금 줄은 모두 지난다)."""
    _swap(OLD_CHECK, NEW_CHECK, NEW_CHECK_SQL)


def downgrade() -> None:
    """① 조립 BASIC 줄을 완료로 → ② 옛 제약(재단만)으로."""
    op.execute(sa.text(DOWNGRADE_FIX_SQL))
    _swap(NEW_CHECK, OLD_CHECK, OLD_CHECK_SQL)
