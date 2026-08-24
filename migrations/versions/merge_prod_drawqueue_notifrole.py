"""production 계보 병합: drawqueue_00 + notifrole_00

Revision ID: merge_prod_drawq
Revises: drawqueue_00, notifrole_00
Create Date: 2026-08-23

drawqueue_00(도면 작업실 모집단 부분 인덱스)은 deploy 에서 assort_00 을 부모로 삼았다.
production 계보의 head 는 notifrole_00 이고 assort_00 은 그 조상이라, 승격 시 head 가
둘로 갈린다. 같은 revision 을 계보마다 다른 부모로 바꿔치기하면 두 갈래가 생기므로
(부모 바꿔치기 금지) 병합 리비전으로 잇는다 — deploy 가 naverfail_00 과 병합한 것과
같은 방식이다.

DDL 없음(병합 노드).
"""
from typing import Sequence, Union

revision: str = "merge_prod_drawq"
down_revision: Union[str, Sequence[str], None] = ("drawqueue_00", "notifrole_00")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """병합 노드 — 스키마 변경 없음."""
    pass


def downgrade() -> None:
    """병합 노드 — 스키마 변경 없음."""
    pass
