"""PostgreSQL — 계정 공장 ``users.production_factory``(설계서 2026-11-23 §6-2, 마이그레이션 ``prodfactory_01``).

* CHECK ``ck_users_production_factory`` — NULL · 1 · 2 는 받고 그 밖은 막는다(create_all 꼴 = 모델).
* 마이그레이션 한 칸 왕복(새 부트스트랩 DB = create_all + stamp head): downgrade 가 CHECK · 칸만 지우고(다른 칸 그대로) → upgrade 가
  칸 · CHECK 를 다시 단다(채우기 없음 — 옛 행은 NULL = 1공장). 옛 코드가 넣는 행(칸을 모름)도 지난다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다(conftest). 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import IntegrityError

from models import User
from tests.postgres.test_migration_chain import _alembic_config, migration_chain_url  # noqa: F401 — fixture

_COLS = ("username, password, name, role, team, is_active, approval_status, password_policy_version, session_version, "
         "production_part, production_lead")


@pytest.mark.parametrize("factory", [None, 1, 2])
def test_check_accepts_null_one_and_two(pg_session, factory):
    pg_session.add(User(username=f"pfg_ok{factory}", password="x", name="공장", role="STAFF", team="PRODUCTION",
                        production_factory=factory))
    pg_session.flush()


@pytest.mark.parametrize("factory", [0, 3, -1])
def test_check_rejects_other_numbers(pg_session, factory):
    pg_session.add(User(username="pfg_bad", password="x", name="공장", role="STAFF", team="PRODUCTION",
                        production_factory=factory))
    with pytest.raises(IntegrityError, match="ck_users_production_factory"):
        pg_session.flush()


def test_prodfactory_01_round_trip_keeps_other_columns(
    migration_chain_url: URL, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    import app  # noqa: F401  (모든 모델 모듈을 Base.metadata 에 등록)
    from db import Base

    engine = create_engine(migration_chain_url, connect_args={"client_encoding": "utf8"})
    try:
        Base.metadata.create_all(bind=engine)
        monkeypatch.setenv("DATABASE_URL", migration_chain_url.render_as_string(hide_password=False))
        config = _alembic_config()
        command.stamp(config, "head")
        with engine.begin() as conn:
            conn.execute(text(
                f"INSERT INTO users ({_COLS}, production_factory) VALUES "
                "('pfg_two', 'x', '강검수', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, 'inspect', true, 2)"))

        command.downgrade(config, "prodlead_01")
        with engine.connect() as conn:
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))}
            assert "production_factory" not in cols and {"production_lead", "production_part"} <= cols
            kept = conn.execute(text("SELECT production_part, production_lead FROM users WHERE username = 'pfg_two'")).one()
            assert tuple(kept) == ("inspect", True)  # 다른 칸은 그대로
        with engine.begin() as conn:  # 옛 코드(칸을 모름)가 그사이 만든 행
            conn.execute(text(f"INSERT INTO users ({_COLS}) VALUES "
                              "('pfg_old', 'x', '윤검수', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, NULL, NULL)"))

        command.upgrade(config, "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT username, production_factory FROM users WHERE username LIKE 'pfg_%'")).all())
            assert got == {"pfg_two": None, "pfg_old": None}  # 채우기 없음(되돌린 동안 2공장 값은 사라진다 — §15)
            kinds = dict(conn.execute(text(
                "SELECT conname, contype FROM pg_constraint WHERE conname = 'ck_users_production_factory'")).all())
            assert kinds == {"ck_users_production_factory": "c"}
            data_type = conn.execute(text(
                "SELECT data_type FROM information_schema.columns WHERE table_name = 'users' "
                "AND column_name = 'production_factory'")).scalar()
            assert data_type == "smallint"
            with pytest.raises(IntegrityError):
                conn.execute(text("UPDATE users SET production_factory = 3 WHERE username = 'pfg_old'"))
    finally:
        engine.dispose()
