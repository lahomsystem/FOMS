"""지식 이름 정렬은 PostgreSQL 에서 ``COLLATE "C"`` — 운영 · 스테이징 기본 정렬 규칙(en_US.utf8)이 한글에 무게가 없어
'이름 순'이 가나다가 아니었다(스테이징 실측 2026-11-08). SQLite 는 그대로."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from foms.persistence.brain.models import BrainObject
from foms.services.brain.browse import name_order, pref_name


def _order_sql(dialect) -> str:
    query = select(BrainObject.item_key).order_by(name_order(pref_name()), BrainObject.item_key)
    return str(query.compile(dialect=dialect)).split("ORDER BY", 1)[1]


def test_postgres_name_order_uses_c_collation():
    assert 'COLLATE "C"' in _order_sql(postgresql.dialect())


def test_sqlite_name_order_has_no_collation():
    assert "COLLATE" not in _order_sql(sqlite.dialect())


def test_c_collation_sorts_hangul_in_ganada_order():
    names = ["첫인사", "상담 마무리", "주문 방법", "도면 사진", "실측 예약", "전화 상담"]
    assert sorted(names) == ["도면 사진", "상담 마무리", "실측 예약", "전화 상담", "주문 방법", "첫인사"]
