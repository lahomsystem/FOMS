"""PostgreSQL — 반장 칸 ``users.production_lead``(설계서 2026-11-23 '승인 때 고친 것' 5, 마이그레이션 ``prodlead_01``).

마이그레이션 한 칸 왕복(새 부트스트랩 DB = create_all + stamp head): downgrade 가 반장 칸만 지우고(다른 칸 그대로) → upgrade 가 지금
'파트 없는 생산팀'(STAFF · MANAGER, 활성 여부 무관, 옛 칸 NULL · 새 칸 NULL 또는 빈 목록)만 참으로 채운다. jsonb '빈 목록' 견주기와
Boolean 칸 꼴은 SQLite 레인이 못 본다. 채우기 조건 글은 운영에 올리기 전 셀 읽기 전용 집계와 같다(같은 글을 여기서 돌려 센다).

``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다(conftest). 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL

from tests.postgres.test_migration_chain import _alembic_config, migration_chain_url  # noqa: F401 — fixture

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "prodlead_01_users_production_lead.py"
_COLS = ("username, password, name, role, team, is_active, approval_status, password_policy_version, session_version, "
         "production_part, production_parts")


def _fill_where() -> str:
    spec = importlib.util.spec_from_file_location("prodlead_01_pg", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FILL_WHERE["postgresql"]


def test_prodlead_01_round_trip_fills_only_partless_production_writers(
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
        command.downgrade(config, "prodparts_01")
        with engine.connect() as conn:
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))}
            assert "production_lead" not in cols and {"production_parts", "production_part"} <= cols
        with engine.begin() as conn:  # 옛 코드(반장 칸을 모름)가 만든 행들
            conn.execute(text(
                f"INSERT INTO users ({_COLS}) VALUES "
                "('plg_boss', 'x', '박반장', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, NULL, NULL),"
                "('plg_mgr', 'x', '정반장', 'MANAGER', ' production ', false, 'ACTIVE', 0, 0, NULL, '[]'),"
                "('plg_view', 'x', '조보기', 'VIEWER', 'PRODUCTION', true, 'ACTIVE', 0, 0, NULL, NULL),"
                "('plg_cs', 'x', '상담', 'STAFF', 'CS', true, 'ACTIVE', 0, 0, NULL, NULL),"
                "('plg_cut', 'x', '김재단', 'STAFF', 'PRODUCTION', true, 'ACTIVE', 0, 0, 'cut', '[\"cut\"]'),"
                "('plg_admin', 'x', '가짜관리', 'ADMIN', 'PRODUCTION', true, 'ACTIVE', 0, 0, NULL, NULL)"))
            expected_count = conn.execute(text(f"SELECT count(*) FROM users WHERE {_fill_where()}")).scalar()
        assert expected_count == 2  # 운영 전 집계와 같은 글 — 박반장 · 정반장(꺼진 계정 · 빈 목록 · 빈칸 섞인 팀 글)

        command.upgrade(config, "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT username, production_lead FROM users WHERE username LIKE 'plg_%'")).all())
            assert got == {"plg_boss": True, "plg_mgr": True, "plg_view": None, "plg_cs": None, "plg_cut": None,
                           "plg_admin": None}
            data_type, nullable, default = conn.execute(text(
                "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'production_lead'")).one()
            assert (data_type, nullable, default) == ("boolean", "YES", None)
            parts = dict(conn.execute(text("SELECT username, production_part FROM users WHERE username LIKE 'plg_%'")).all())
            assert parts["plg_cut"] == "cut"  # 다른 칸은 그대로
    finally:
        engine.dispose()
