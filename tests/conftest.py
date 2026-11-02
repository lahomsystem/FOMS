"""Pytest fixtures for FOMS (NEXT-003)."""
import os
import pytest
import werkzeug.security as _werkzeug_security
from werkzeug.security import generate_password_hash

# --- CI-KDF-01: 테스트 레인 전용 PBKDF2 반복수 완화 -------------------------------
# werkzeug 2.3 기본값은 pbkdf2:sha256:600000 이고, 해시 1회에 약 250ms 가 든다.
# tests/ 는 User 행을 채우려고 generate_password_hash 를 404 곳에서 부르는데,
# 그렇게 만든 해시 1,695 개 중 실제 대조(check_password_hash)에 쓰이는 것은 254 개뿐이다.
# 나머지는 아무도 검증하지 않을 비밀번호를 60만 번 돌리는 순수 낭비이고, 이것이
# FOMS CI `Run tests` 839초의 약 73%(실측 676초)를 차지한다.
#
# 반복수만 낮춘다. 호출부 404 곳은 그대로 두고, 코드 경로도 그대로다 — 같은 경로가
# 싸질 뿐이라 검출력 손실이 없다(전체 4,469건 A/B 에서 실패/성공 집합 완전 동일).
# 반복수는 해시 문자열에 박히므로 check_password_hash 는 정상 동작한다.
#
# generate_password_hash 는 이 상수를 **호출 시점에** 읽는다. 그래서 위 4행처럼
# 이름을 미리 바인딩(early-bound)한 모듈이 있어도 이 패치가 먹는다. 반대로
# generate_password_hash 함수 자체를 교체하는 방식은 그런 모듈에 적용되지 않는다.
#
# werkzeug 3.0 부터 method 를 비우면 기본이 scrypt 다. 테스트 404 곳은 method 없이
# 부르므로 그대로 두면 scrypt 로 바뀌어 위 완화가 통째로 무효가 된다. 함수를 바꾸지
# 않고 **함수 객체의 기본 인자**만 pbkdf2 로 돌린다 — 미리 바인딩한 이름도 같은 함수
# 객체를 가리키므로 먹는다.
#
# 운영 해싱은 foms/services/security/password_policy.py 의 hash_password 한 곳이
# method 를 명시한다(pbkdf2:sha256, PASSWORD_PBKDF2_ITERATIONS 회). 그 반복수도 호출
# 시점에 모듈 전역에서 읽으므로 여기서 함께 낮춘다. 이 파일은 tests/ 전용이며, 완화가
# 조용히 무효화되거나 운영으로 새는 것은 tests/domains/test_password_kdf_contract.py 가 봉인한다.
import foms.services.security.password_policy as _password_policy

FOMS_TEST_PBKDF2_ITERATIONS = 10
PRODUCTION_PBKDF2_ITERATIONS = _password_policy.PASSWORD_PBKDF2_ITERATIONS
_password_policy.PASSWORD_PBKDF2_ITERATIONS = FOMS_TEST_PBKDF2_ITERATIONS
_werkzeug_security.DEFAULT_PBKDF2_ITERATIONS = FOMS_TEST_PBKDF2_ITERATIONS
_gph_defaults = _werkzeug_security.generate_password_hash.__defaults__ or ("pbkdf2", 16)
_werkzeug_security.generate_password_hash.__defaults__ = ("pbkdf2",) + tuple(_gph_defaults[1:])

from tests.postgres_guard import assert_not_postgresql, assert_safe_for_schema_reset

# 1. Set environment variable for test database BEFORE importing app/db
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_db_url = os.environ.get("DATABASE_URL", "").strip()
assert_not_postgresql(_db_url, context="pytest session (tests/conftest.py)")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DESIGNER_AI_FAKE"] = "1"

from sqlalchemy import text

from app import app as flask_app
from db import init_db, db_session, Base, engine
from models import (
    AUTH_RATE_KEY_STATE_SEED_SQL,
    CHANNEL_CREATE_FLAG_SEED_SQL,
    CHANNEL_INBOUND_KEY_STATE_SEED_SQL,
    FEATURE_CUTOVER_FENCE_SEED_SQL,
    SECURITY_SIGNING_STATE_SEED_SQL,
    User,
)

# Ensure designer models are registered in Base
import foms.persistence.designer.models  # noqa: F401


# --- CI-SHARD-01: CI 본 스위트를 파일 단위로 N 조각 나눠 동시에 돈다 -----------------
# FOMS CI `Run tests`(약 5분)가 deploy 푸시·운영 PR 마다 한 번씩, 한 건에 두 번 도는 가장
# 긴 구간이었다(2026-11-02 계측, 설계서 docs/specs/2026-11-02-push-guard-effective-repo_SPEC.md).
# `FOMS_TEST_SHARD=i/N` 이면 i 번 조각에 배정된 테스트 파일만 남긴다. 배정은 파일 단위라 모듈
# 스코프 fixture 가 조각 사이에서 갈리지 않는다(--dist loadfile 과 같은 이유). 수집한 파일 전체로
# 한 번에 정하므로 조각들의 합은 항상 전체와 같다(빠지거나 겹치는 파일이 없다).
# 변수가 없으면(로컬 smoke·개별 실행) 아무것도 하지 않는다.
#
# 처음엔 경로 crc32 로 나눴더니 무거운 파일이 한 조각에 몰려(기록 시간 174 · 232 · 174초) 그 조각이
# 전체를 늦췄다. 이제 tests/ci_shard_durations.json 의 파일별 시간으로 큰 파일부터 가장 덜 찬
# 조각에 넣는다. 기록에 없는 새 파일은 중간값으로 친다. 기록 갱신은
# tools/harness/refresh_ci_shard_durations.py.
_SHARD_DURATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_shard_durations.json")
#: 1번 조각은 lint·Redis·UI 구조 스텝(CI 약 25초)을 더 맡는다 — 그만큼 먼저 찬 것으로 친다.
_SHARD_ONE_HEAD_START_SECONDS = 15.0


def ci_shard_plan(test_paths, total: int) -> dict[str, int]:
    """테스트 파일 경로 → 조각 번호(1..total). 같은 입력이면 어느 프로세스에서도 같은 답이다."""
    import json
    import statistics

    try:
        with open(_SHARD_DURATIONS_PATH, encoding="utf-8") as handle:
            seconds = json.load(handle)["seconds"]
    except (OSError, ValueError, KeyError):
        seconds = {}
    paths = sorted({p.replace("\\", "/") for p in test_paths})
    known = [seconds[p] for p in paths if p in seconds]
    fallback = statistics.median(known) if known else 1.0
    loads = [0.0] * total
    loads[0] = _SHARD_ONE_HEAD_START_SECONDS if total > 1 else 0.0
    plan: dict[str, int] = {}
    for path in sorted(paths, key=lambda p: (-seconds.get(p, fallback), p)):
        target = min(range(total), key=lambda k: (loads[k], k))
        plan[path] = target + 1
        loads[target] += seconds.get(path, fallback)
    return plan


def pytest_collection_modifyitems(config, items):
    spec = os.environ.get("FOMS_TEST_SHARD", "").strip()
    if not spec:
        return
    index, total = (int(part) for part in spec.split("/", 1))
    if not 1 <= index <= total:
        raise pytest.UsageError(f"FOMS_TEST_SHARD={spec!r}: 1..N 범위가 아니다")
    plan = ci_shard_plan({item.nodeid.split("::", 1)[0] for item in items}, total)
    keep, drop = [], []
    for item in items:
        (keep if plan[item.nodeid.split("::", 1)[0].replace("\\", "/")] == index else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep


# --- CI-SCHEMA-01: 스키마는 세션에 한 번, 데이터만 테스트마다 비운다 ------------
# 예전에는 `app` fixture 가 테스트마다 83 개 테이블을 create_all 하고 drop_all 했다
# (1 사이클 65.9ms x 2,234 회 = 약 146 초, CI `Run tests` 의 17%).
#
# 스키마는 매 테스트 동일하다. 달라야 하는 것은 데이터뿐이므로 DDL 은 세션에 한 번만
# 하고, 테스트마다 전 테이블을 비운 뒤 create_all 이 심어주던 싱글턴 시드를 다시
# 넣는다. 그래야 "격리 단독 실행" 과 같은 출발선이 된다.
#
# 이 시드 재실행이 이 변경의 핵심이다. create_all 은 순수 DDL 이 아니라 models.py 의
# after_create 이벤트를 함께 태운다(훅 8 곳 중 3 곳은 execute_if(postgresql) 이라
# SQLite 에서는 5 곳이 산다). 시드를 다시 넣지 않으면 싱글턴 행(id=1)을 전제로 하는
# 테스트가 조용히 깨진다 — tests/postgres/conftest.py 가 같은 이유로 TRUNCATE 뒤
# 같은 5 종을 다시 넣는다.
_SINGLETON_SEED_SQL = (
    FEATURE_CUTOVER_FENCE_SEED_SQL,
    SECURITY_SIGNING_STATE_SEED_SQL,
    AUTH_RATE_KEY_STATE_SEED_SQL,
    CHANNEL_INBOUND_KEY_STATE_SEED_SQL,
    CHANNEL_CREATE_FLAG_SEED_SQL,
)


def _reset_database_to_fresh() -> None:
    """전 테이블을 비우고 싱글턴 시드를 재주입해 create_all 직후 상태를 복원한다.

    Raises:
        Exception: DELETE/시드 실패는 그대로 올린다. 반쯤 초기화된 DB 를 다음
            테스트에 넘기는 것보다 시끄럽게 죽는 편이 낫다.
    """
    db_session.remove()
    with engine.begin() as conn:
        # SQLite 는 FK 를 강제하지 않지만, 순서를 지켜 지우면 FK 를 켠 환경에서도
        # 그대로 동작한다.
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        # AUTOINCREMENT 를 쓰는 테이블이 있으면 카운터도 되돌린다. 그래야 id 를
        # 가정하는 테스트가 실행 순서에 따라 갈리지 않는다(PG 레인의 RESTART
        # IDENTITY 와 같은 목적).
        has_seq = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
        ).first()
        if has_seq:
            conn.execute(text("DELETE FROM sqlite_sequence"))
        for seed_sql in _SINGLETON_SEED_SQL:
            conn.execute(text(seed_sql))


@pytest.fixture(scope="session")
def _schema():
    """세션에 한 번만 스키마를 만든다(after_create 시드 포함)."""
    # 엔진 기준 가드가 **먼저** 온다. env 문자열만 보면, conftest 보다 먼저 db 를 import 한
    # 파일 하나가 엔진을 로컬 Postgres 에 묶어 놓아도 "sqlite 니까 안전"으로 통과한다
    # (2026-08-23 그렇게 로컬 dev DB 테이블 86개가 드롭됐다).
    assert_safe_for_schema_reset(
        os.environ.get("DATABASE_URL", ""),
        context="tests/conftest.py session schema setup",
        engine=engine,
    )
    Base.metadata.create_all(bind=engine)

    yield

    db_session.remove()
    assert_safe_for_schema_reset(
        os.environ.get("DATABASE_URL", ""),
        context="tests/conftest.py session schema teardown",
        engine=engine,
    )
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def app(_schema):
    """Flask app with TESTING config and in-memory DB."""
    flask_app.config["TESTING"] = True

    # 이전 테스트가 남긴 행을 지우고 시드를 되돌린다. 테스트 **시작** 시점에
    # 비우므로, app fixture 를 쓰지 않는 테스트가 중간에 무엇을 남겨도 출발선이
    # 같다.
    _reset_database_to_fresh()
    # DB 를 비웠으면 DB 에서 센 값을 들고 있는 프로세스 캐시도 비운다. 네이버 처리 대기 수
    # (30초 캐시)는 처리 탭 렌더가 채우고 이력 탭·nav 배지가 읽는다 — 안 비우면 앞 테스트의
    # 수가 다음 테스트 화면에 실려 실행 순서에 따라 결과가 갈린다.
    from foms.services.integrations.naver_commerce.triage_count import (
        reset_triage_count_cache_for_tests,
    )

    reset_triage_count_cache_for_tests()

    yield flask_app

    db_session.remove()

@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()

@pytest.fixture
def login(client):
    """Login helper. Creates admin user and logs in."""
    # Create admin user
    user = User(
        username="admin", 
        password=generate_password_hash("admin"), 
        role="admin",
        name="Admin User"
    )
    db_session.add(user)
    db_session.commit()

    # Login
    client.post("/login", data={
        "username": "admin",
        "password": "admin"
    }, follow_redirects=True)
    
    return client


@pytest.fixture
def auth_client(app):
    """Test client with an authenticated admin session."""
    # Ensure table exists
    Base.metadata.create_all(bind=engine)

    # Create admin user if not exists
    existing = db_session.query(User).filter_by(username="testadmin").first()
    if not existing:
        user = User(
            username="testadmin",
            password=generate_password_hash("testpass"),
            role="ADMIN",
            name="Test Admin",
        )
        db_session.add(user)
        db_session.commit()

    client = app.test_client()
    client.post("/login", data={"username": "testadmin", "password": "testpass"}, follow_redirects=True)
    return client
