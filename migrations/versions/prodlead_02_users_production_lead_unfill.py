"""PRODLEAD-02: 반장 자동 채우기 되돌림 — prodlead_01 이 채운 '파트 없는 생산팀' 반장 값을 비운다(한 번만 도는 되돌림)

Revision ID: prodlead_02
Revises: prodfactory_01
Create Date: 2026-11-25

사장님 2026-11-25 "자동 지정 없이 직접 지정" — 반장은 관리자가 ``/admin/users`` 에서 계정마다 지정한다. 운영에 올릴 때 아무 계정도
저절로 반장이 되지 않고, 지정하기 전까지 파트 없는 생산팀 계정은 보기만 한다.

왜 prodlead_01 을 고치지 않고 새 리비전인가(마이그레이션 상수 동결 원칙 — 작성 시점 동작을 소급해 바꾸지 않는다, 2026-07-28 사고):
prodlead_01 은 스테이징에 이미 돌았다. 그 파일의 채우기를 지우면 스테이징 DB(채워짐)와 체인 기록이 말없이 어긋나고(alembic 은 다시
돌리지 않는다) 새 DB · 운영과 결과가 갈린다. 되돌림을 체인 끝에 더하면 어느 DB 든 같은 끝(아무도 자동 반장 아님)에 닿는다 —
운영은 predeploy 한 번에 prodlead_01(채움) → prodlead_02(비움)가 이어 돈다(옛 코드는 이 칸을 읽지 않아 그 사이 영향 없음).

upgrade: prodlead_01 의 채우기 조건(:data:`FILL_WHERE`, 그 파일과 글자 그대로 같다 — 시험이 견준다)에 맞는 행의 ``production_lead`` 를
NULL 로(새 계정 기본값과 같다 — 앱은 NULL · 거짓을 반장 아님으로 읽는다). 칸 · CHECK · 색인은 그대로.
**주의(한 번만 도는 되돌림)**: 이 리비전이 돌 때 조건에 맞는 행은 사람이 손으로 지정한 반장이어도 함께 비운다. 2026-11-25 스테이징에서
손으로 지정한 반장은 시험 계정뿐이다(괜찮음 — 지휘 확인 2026-11-25). 돈 뒤에 관리자가 지정하는 반장은 다시 건드리지 않는다(alembic 은
한 번만 돈다). 조건 밖(파트가 있는 계정 · VIEWER · 다른 팀)의 반장 값은 건드리지 않는다.

downgrade: 같은 조건 행을 참으로 다시 채운다(= prodlead_01 이 끝난 뒤 모습). 커밋 되돌리기만 해도 되돌림은 그대로 남는다.

두 방언(PG · SQLite) 같은 글 · 값은 bind. 마이그레이션 상수 동결 원칙에 따라 ``models`` 를 import 하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'prodlead_02'
down_revision: Union[str, None] = 'prodfactory_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: prodlead_01 채우기 조건 그대로(그 리비전의 글을 이 파일에 동결 — 소급 오염 없음).
FILL_WHERE = ("upper(trim(team)) = 'PRODUCTION' AND upper(trim(role)) IN ('STAFF', 'MANAGER') "
              "AND production_part IS NULL")


def upgrade() -> None:
    """prodlead_01 이 채운 반장 값 비우기(조건에 맞는 행만)."""
    op.execute(sa.text(f"UPDATE users SET production_lead = NULL WHERE {FILL_WHERE}"))


def downgrade() -> None:
    """같은 조건 행을 반장으로 다시 채운다(prodlead_01 이 끝난 뒤 모습)."""
    op.execute(sa.text(f"UPDATE users SET production_lead = :lead WHERE {FILL_WHERE}").bindparams(lead=True))
