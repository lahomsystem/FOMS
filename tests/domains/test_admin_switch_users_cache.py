"""W3-5: ADMIN 전환 드롭다운 유저 목록 마이크로 캐시 계약 가드.

_get_admin_switch_users는 활성 유저 전체(자기 제외 없음)를 60s 프로세스 캐시에 담고,
자기 제외(id != current_user_id)는 캐시 반환 후 파이썬 필터로 적용한다. 캐시 히트 시
DB 쿼리가 발생하지 않아야 하고, 반환 객체는 세션 밖에서도 id/name/username 접근이
가능한 detached-safe 경량 객체여야 한다(ORM User lazy-load DetachedInstanceError 회피).
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
import foms.services.context_processors as cp
from models import User


@pytest.fixture(autouse=True)
def _reset_admin_cache():
    """테스트 간 모듈 캐시 오염 방지: 매 테스트 전후 캐시 리셋."""
    cp._ADMIN_SWITCH_USERS_CACHE["ts"] = 0.0
    cp._ADMIN_SWITCH_USERS_CACHE["users"] = []
    yield
    cp._ADMIN_SWITCH_USERS_CACHE["ts"] = 0.0
    cp._ADMIN_SWITCH_USERS_CACHE["users"] = []


def _make_user(username: str, name: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


class _CountingQuery:
    """db.query 호출 횟수만 계수하는 얇은 프록시."""

    def __init__(self, db, counter):
        self._db = db
        self._counter = counter

    def query(self, *args, **kwargs):
        self._counter["n"] += 1
        return self._db.query(*args, **kwargs)


def test_cache_hit_avoids_second_query(app):
    with app.app_context():
        viewer = _make_user("admin_viewer", "가viewer")
        _make_user("other_a", "나other")
        counter = {"n": 0}
        db = _CountingQuery(db_session, counter)

        first = cp._get_admin_switch_users(db, viewer.id)
        assert counter["n"] == 1, "첫 호출은 1회 쿼리"
        assert first, "다른 활성 유저가 있어야 한다"

        second = cp._get_admin_switch_users(db, viewer.id)
        assert counter["n"] == 1, "TTL 내 2회차는 캐시 히트(쿼리 증가 0)"
        assert {u.id for u in first} == {u.id for u in second}


def test_ttl_expiry_requeries(app):
    with app.app_context():
        viewer = _make_user("admin_ttl", "가ttl")
        _make_user("other_b", "나ttl")
        counter = {"n": 0}
        db = _CountingQuery(db_session, counter)

        cp._get_admin_switch_users(db, viewer.id)
        assert counter["n"] == 1

        # 캐시 ts를 과거로 강제해 TTL 만료 유도
        cp._ADMIN_SWITCH_USERS_CACHE["ts"] = 0.0
        cp._get_admin_switch_users(db, viewer.id)
        assert counter["n"] == 2, "TTL 만료 후 재쿼리"


def test_return_shape_is_detached_safe(app):
    with app.app_context():
        viewer = _make_user("admin_shape", "가shape")
        _make_user("other_c", "나shape")

        result = cp._get_admin_switch_users(db_session, viewer.id)
        # 세션 만료 후에도 필드 접근 가능해야 한다(detached lazy-load 아님)
        db_session.remove()
        u = result[0]
        assert isinstance(u.id, int)
        assert isinstance(u.name, str)
        assert isinstance(u.username, str)


def test_self_excluded_from_result(app):
    with app.app_context():
        viewer = _make_user("admin_self", "가self")
        other = _make_user("other_d", "나self")

        result = cp._get_admin_switch_users(db_session, viewer.id)
        result_ids = {u.id for u in result}
        assert viewer.id not in result_ids, "본인은 결과에서 제외"
        assert other.id in result_ids, "타 활성 유저는 포함"
