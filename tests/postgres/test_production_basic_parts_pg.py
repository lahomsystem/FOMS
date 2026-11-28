"""PostgreSQL — 조립 '조립 없음'의 제약 ``ck_production_part_marks_basic_part``(설계서 2026-11-28 흐름 셋 §3-4 · §3-7, 마이그레이션
``prodpart_03_basic_parts``).

* 운영과 같은 PG 에서: 조립 ``BASIC`` 줄이 들어가고, 엣지 · 검수 ``BASIC`` 줄은 제약이 막는다(사장님 "조립만" — 앱 상수가 잘못 넓어져도).
  대조군: 재단 ``BASIC`` 은 지금처럼 들어간다.
* 마이그레이션 한 칸 왕복(새 부트스트랩 DB = create_all + stamp head): 조립 없음 줄이 있어도 downgrade 가 된다 — 그 줄을 완료로 바꾼
  뒤 옛 제약(재단만)으로, upgrade 가 다시 새 제약으로. 제약 이름이 한 번에 하나만 걸려 있다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다(conftest). SQLite 쪽 왕복 · PG 가 받을 글은
``tests/domains/test_production_assemble_none_1128.py``. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from models import Order, ProductionPartMark
from tests.postgres.test_migration_chain import _alembic_config, migration_chain_url  # noqa: F401 — fixture

NEW_CHECK, OLD_CHECK = "ck_production_part_marks_basic_part", "ck_production_part_marks_basic_cut"


def _order(session) -> int:
    order = Order(received_date="2026-11-28", customer_name="가짜고객", phone="010-0000-0000", address="가짜시", product="가짜장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                  structured_data={"workflow": {"stage": "PRODUCTION"}})
    session.add(order)
    session.flush()
    return int(order.id)


@pytest.mark.parametrize("part", ["cut", "assemble"])
def test_check_accepts_basic_on_cut_and_assemble(pg_session, part):
    pg_session.add(ProductionPartMark(order_id=_order(pg_session), drawing_key="d0.png", part=part, state="BASIC", done_by_name="가짜"))
    pg_session.flush()


@pytest.mark.parametrize("part", ["edge", "inspect"])
def test_check_rejects_basic_on_edge_and_inspect(pg_session, part):
    pg_session.add(ProductionPartMark(order_id=_order(pg_session), drawing_key="d0.png", part=part, state="BASIC"))
    with pytest.raises(IntegrityError, match=NEW_CHECK):
        pg_session.flush()


def test_prodpart_03_round_trip_with_an_assemble_none_row(
    migration_chain_url: URL, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    import app  # noqa: F401  (모든 모델 모듈을 Base.metadata 에 등록)
    from db import Base

    engine = create_engine(migration_chain_url, connect_args={"client_encoding": "utf8"})

    def checks(conn) -> set[str]:
        return {r[0] for r in conn.execute(text("SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_production_part_marks_basic%'"))}

    try:
        Base.metadata.create_all(bind=engine)
        monkeypatch.setenv("DATABASE_URL", migration_chain_url.render_as_string(hide_password=False))
        config = _alembic_config()
        command.stamp(config, "head")
        with engine.connect() as conn:
            assert checks(conn) == {NEW_CHECK}
        session = sessionmaker(bind=engine)()
        try:
            oid = _order(session)
            session.add_all([ProductionPartMark(order_id=oid, drawing_key="d0.png", part="assemble", state="BASIC", done_by_name="최조립"),
                             ProductionPartMark(order_id=oid, drawing_key="d0.png", part="cut", state="BASIC", done_by_name="김재단"),
                             ProductionPartMark(order_id=oid, drawing_key="d1.png", part="assemble", state="NEED")])
            session.commit()
        finally:
            session.close()

        command.downgrade(config, "prodpart_02_holders")  # 조립 없음 줄이 있어도 내려간다
        with engine.connect() as conn:
            assert checks(conn) == {OLD_CHECK}
            rows = conn.execute(text("SELECT part, drawing_key, state, done_by_name FROM production_part_marks ORDER BY part, drawing_key")).all()
            assert rows == [("assemble", "d0.png", "DONE", "최조립"), ("assemble", "d1.png", "NEED", None), ("cut", "d0.png", "BASIC", "김재단")]
        with engine.connect() as conn, pytest.raises(IntegrityError, match=OLD_CHECK):  # 옛 제약 = 재단만
            conn.execute(text("UPDATE production_part_marks SET state = 'BASIC' WHERE part = 'assemble' AND drawing_key = 'd1.png'"))

        command.upgrade(config, "head")
        with engine.begin() as conn:
            assert checks(conn) == {NEW_CHECK}
            conn.execute(text("UPDATE production_part_marks SET state = 'BASIC' WHERE part = 'assemble' AND drawing_key = 'd1.png'"))
    finally:
        engine.dispose()
