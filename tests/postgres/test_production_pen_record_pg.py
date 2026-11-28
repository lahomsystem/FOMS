"""PostgreSQL — 생산 도면 펜 기록의 표 ``production_drawing_notes`` · 계정 칸 둘(설계서 2026-11-28 §3-1 · §4-1, 마이그레이션
``prodpen_01_pen_record``).

* 운영과 같은 PG 에서: 한 주문 · 한 도면 key 에 한 줄(유일 제약), 기록 원본은 JSONB, 주문을 지우면 같이 지워지고 첨부를 지우면
  ``attachment_id`` 만 비워진다. 대조군: 같은 주문의 다른 도면 key 는 들어간다.
* 마이그레이션 한 칸 왕복(새 부트스트랩 DB = create_all + stamp head): 내리면 표 · 칸 둘이 사라지고 다른 칸은 그대로, 다시 올리면
  create_all 과 같은 칸 지문(꼴 · NULL · 기본값)으로 돌아온다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다(conftest). SQLite 쪽은 ``tests/domains/test_production_pen_record_base.py``.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import IntegrityError

from models import Order, OrderAttachment, ProductionDrawingNote
from tests.postgres.test_migration_chain import _alembic_config, _column_fingerprint, migration_chain_url  # noqa: F401 — fixture

TABLE, UNIQUE = "production_drawing_notes", "uq_production_drawing_notes_order_key"
USER_COLUMNS = ("production_pen_write", "production_pen_first")


def _order(session) -> int:
    order = Order(received_date="2026-11-28", customer_name="정하늘", phone="010-0000-0000", address="가짜시", product="가짜장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                  structured_data={"workflow": {"stage": "PRODUCTION"}})
    session.add(order)
    session.flush()
    return int(order.id)


def _note(order_id: int, key: str = "orders/1/drawing/a.png", **fields) -> ProductionDrawingNote:
    values = dict(order_id=order_id, drawing_key=key, base_w=1478, base_h=1040, updated_by_name="김재단",
                  objects=[{"type": "text", "x": 10, "y": 20, "text": "깊이 620", "fill": "#000000", "fontSize": 24}])
    values.update(fields)
    return ProductionDrawingNote(**values)


def test_one_note_per_order_and_drawing_key(pg_session):
    oid = _order(pg_session)
    pg_session.add(_note(oid))
    pg_session.add(_note(oid, key="orders/1/drawing/b.png"))  # 대조군: 다른 장은 된다
    pg_session.flush()
    pg_session.add(_note(oid))
    with pytest.raises(IntegrityError, match=UNIQUE):
        pg_session.flush()


def test_objects_are_jsonb_and_version_defaults_to_one(pg_session):
    oid = _order(pg_session)
    pg_session.add(_note(oid))
    pg_session.flush()
    row = pg_session.execute(text(
        f"SELECT jsonb_typeof(objects), objects->0->>'text', version FROM {TABLE} WHERE order_id = :o"), {"o": oid}).one()
    assert tuple(row) == ("array", "깊이 620", 1)


def test_order_delete_cascades_and_attachment_delete_only_unlinks(pg_session):
    oid = _order(pg_session)
    att = OrderAttachment(order_id=oid, filename="도면1_생산기록.png", file_type="image", category="production",
                          storage_key=f"orders/{oid}/production/x.png")
    pg_session.add(att)
    pg_session.flush()
    pg_session.add(_note(oid, attachment_id=att.id))
    pg_session.flush()
    pg_session.execute(text("DELETE FROM order_attachments WHERE id = :a"), {"a": att.id})
    assert pg_session.execute(text(f"SELECT attachment_id FROM {TABLE} WHERE order_id = :o"), {"o": oid}).scalar_one() is None
    pg_session.execute(text("DELETE FROM orders WHERE id = :o"), {"o": oid})
    assert pg_session.execute(text(f"SELECT COUNT(*) FROM {TABLE} WHERE order_id = :o"), {"o": oid}).scalar_one() == 0


def test_prodpen_01_round_trip(migration_chain_url: URL, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    import app  # noqa: F401  (모든 모델 모듈을 Base.metadata 에 등록)
    from db import Base

    engine = create_engine(migration_chain_url, connect_args={"client_encoding": "utf8"})

    def tables(conn) -> set[str]:
        return {r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}

    def uniques(conn) -> set[str]:
        return {r[0] for r in conn.execute(text(f"SELECT conname FROM pg_constraint WHERE conname = '{UNIQUE}'"))}

    try:
        Base.metadata.create_all(bind=engine)
        monkeypatch.setenv("DATABASE_URL", migration_chain_url.render_as_string(hide_password=False))
        config = _alembic_config()
        command.stamp(config, "head")
        before = _column_fingerprint(engine)
        with engine.connect() as conn:
            assert TABLE in tables(conn) and uniques(conn) == {UNIQUE}

        command.downgrade(config, "prodpart_03_basic_parts")
        during = _column_fingerprint(engine)
        with engine.connect() as conn:
            assert TABLE not in tables(conn) and uniques(conn) == set()
        gone = set(before) - set(during)
        assert gone == {k for k in before if k[0] == TABLE} | {("users", c) for c in USER_COLUMNS}  # 다른 칸은 그대로

        command.upgrade(config, "head")
        assert _column_fingerprint(engine) == before  # create_all 과 같은 꼴 · NULL · 기본값
        with engine.connect() as conn:
            assert uniques(conn) == {UNIQUE}
            assert conn.execute(text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = :t AND column_name = 'objects'"),
                {"t": TABLE}).scalar_one() == "jsonb"
    finally:
        engine.dispose()
