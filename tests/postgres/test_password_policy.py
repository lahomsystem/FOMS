"""PASSWORD-POLICY-01 비밀번호 강도 정책 PostgreSQL 계약 테스트 (PGTEST-00 lane).

실 PostgreSQL 세션으로 컬럼 SSOT·server_default backfill·count/ENFORCED 전이를 검증한다:

* ``users.password_policy_version`` 컬럼이 존재하고, 값을 생략한 INSERT 는 마이그레이션
  server_default(``0``=LEGACY)로 backfill 된다(기존 행을 hash 추정 없이 legacy 로 표시).
* :func:`set_strong_password` 가 실 PG 에 STRONG 버전을 지속(persist)한다.
* active legacy count·role별 count·ENFORCED 전이가 실 PG 집계로 정확하다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest). 커밋 파일에는
비밀번호·DSN 을 넣지 않는다(dev DSN 은 env 로만 주입).
"""
from __future__ import annotations

from sqlalchemy import text
from werkzeug.security import generate_password_hash

from models import User
from foms.services.security.password_policy import (
    POLICY_VERSION_LEGACY,
    POLICY_VERSION_STRONG,
    active_legacy_count,
    is_policy_enforced,
    legacy_counts_by_role,
    set_strong_password,
)

# 8자+영문+숫자(강도 통과). 실제 계정 비밀번호가 아니라 테스트용 리터럴이다.
_STRONG_PW = "Abcdef12"


def _add(pg_session, username, *, role="STAFF", is_active=True, version=POLICY_VERSION_LEGACY):
    user = User(
        username=username,
        password=generate_password_hash("seed-pw"),
        role=role,
        name=f"{username}-name",
        is_active=is_active,
        password_policy_version=version,
    )
    pg_session.add(user)
    pg_session.commit()
    return user


def test_column_exists_and_server_default_backfills_legacy(pg_session):
    """version 컬럼을 생략한 raw INSERT 는 server_default(0=LEGACY)로 backfill 된다."""
    pg_session.execute(text(
        "INSERT INTO users (username, password, name, role, is_active) "
        "VALUES (:u, :p, :n, :r, true)"
    ), {"u": "legacy-existing", "p": generate_password_hash("x"), "n": "N", "r": "STAFF"})
    pg_session.commit()

    version = pg_session.execute(text(
        "SELECT password_policy_version FROM users WHERE username = :u"
    ), {"u": "legacy-existing"}).scalar_one()
    assert version == POLICY_VERSION_LEGACY  # 기존 행 = LEGACY(추정 없이 명시 backfill)


def test_set_strong_password_persists_strong_on_pg(pg_session):
    user = _add(pg_session, "pg-setter", version=POLICY_VERSION_LEGACY)
    set_strong_password(user, _STRONG_PW)
    pg_session.commit()

    persisted = pg_session.execute(text(
        "SELECT password_policy_version FROM users WHERE username = :u"
    ), {"u": "pg-setter"}).scalar_one()
    assert persisted == POLICY_VERSION_STRONG


def test_active_legacy_count_and_enforced_on_pg(pg_session):
    a = _add(pg_session, "pg-leg-a", role="STAFF", version=POLICY_VERSION_LEGACY)
    b = _add(pg_session, "pg-leg-b", role="MANAGER", version=POLICY_VERSION_LEGACY)
    _add(pg_session, "pg-strong", version=POLICY_VERSION_STRONG)
    _add(pg_session, "pg-inactive-leg", is_active=False, version=POLICY_VERSION_LEGACY)

    assert active_legacy_count(pg_session) == 2       # active legacy 만
    assert is_policy_enforced(pg_session) is False
    counts = legacy_counts_by_role(pg_session, active_only=True)
    assert counts.get("STAFF") == 1 and counts.get("MANAGER") == 1

    set_strong_password(a, _STRONG_PW); pg_session.commit()
    set_strong_password(b, _STRONG_PW); pg_session.commit()
    assert active_legacy_count(pg_session) == 0       # reset 마다 감소 → 0
    assert is_policy_enforced(pg_session) is True      # active count 0 → ENFORCED
