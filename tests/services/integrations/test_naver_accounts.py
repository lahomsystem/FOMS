"""NAVER-INGEST-01 T0: 수집용 시스템 계정 정책 테스트.

이 계정들이 정책에서 벗어나면 수집이 통째로 멈추거나(비활성 owner), 주문이 엉뚱한 사람에게
배정된다. 그래서 "만들었다"가 아니라 "목표 상태로 수렴한다"를 고정한다.
"""

from __future__ import annotations

from werkzeug.security import check_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.accounts import (
    SPECS,
    ensure_ingest_accounts,
    locked_password_hash,
)
from foms.services.integrations.naver_commerce.ingest import (
    ACTOR_USERNAME,
    OWNER_USERNAME,
    resolve_ingest_accounts,
)
from models import User


def _get(username: str) -> User:
    return db_session.query(User).filter(User.username == username).one()


def test_creates_both_accounts_with_policy_shape(app):
    """봇=MANAGER, 보류함=활성 SALES STAFF."""
    results = ensure_ingest_accounts(db_session)
    db_session.commit()
    assert [r["action"] for r in results] == ["created", "created"]

    bot = _get(ACTOR_USERNAME)
    owner = _get(OWNER_USERNAME)
    assert (bot.role, bot.is_active) == ("MANAGER", True)
    assert (owner.role, owner.team, owner.is_active) == ("STAFF", "SALES", True)
    assert owner.approval_status == "ACTIVE"


def test_created_accounts_satisfy_create_order_owner_contract(app):
    """수집 파이프라인이 곧바로 이 계정으로 돌 수 있어야 한다."""
    ensure_ingest_accounts(db_session)
    db_session.commit()
    actor_id, owner_id = resolve_ingest_accounts(db_session)
    assert actor_id == _get(ACTOR_USERNAME).id
    assert owner_id == _get(OWNER_USERNAME).id


def test_rerun_is_idempotent(app):
    """반복 실행이 계정을 늘리거나 바꾸지 않는다."""
    ensure_ingest_accounts(db_session)
    db_session.commit()
    results = ensure_ingest_accounts(db_session)
    db_session.commit()
    assert [r["action"] for r in results] == ["ok", "ok"]
    assert db_session.query(User).count() == 2


def test_password_is_never_a_known_value(app):
    """로그인 잠금: 예측 가능한 비밀번호가 들어가면 안 된다."""
    ensure_ingest_accounts(db_session)
    db_session.commit()
    stored = _get(OWNER_USERNAME).password
    for guess in ("", "password", "naver_unassigned", "1234", "admin"):
        assert not check_password_hash(stored, guess)
    # 매 호출마다 다른 난수여야 한다(같은 값이면 한 번 새면 전부 뚫린다).
    assert locked_password_hash() != locked_password_hash()


def test_repairs_drifted_owner_instead_of_failing(app):
    """누가 보류함 계정을 비활성/타팀으로 바꿔놨어도 되돌린다 — 수집 중단의 흔한 원인."""
    ensure_ingest_accounts(db_session)
    db_session.commit()
    owner = _get(OWNER_USERNAME)
    owner.is_active = False
    owner.team = "CS"
    db_session.commit()

    results = ensure_ingest_accounts(db_session)
    db_session.commit()
    repaired = next(r for r in results if r["username"] == OWNER_USERNAME)
    assert repaired["action"] == "repaired"
    assert set(repaired["fixed"]) == {"team", "is_active"}
    owner = _get(OWNER_USERNAME)
    assert (owner.team, owner.is_active) == ("SALES", True)


def test_existing_password_is_not_touched_by_default(app):
    """운영자가 일부러 바꿔 쓰는 경우를 말없이 덮지 않는다."""
    ensure_ingest_accounts(db_session)
    db_session.commit()
    before = _get(ACTOR_USERNAME).password
    ensure_ingest_accounts(db_session)
    db_session.commit()
    assert _get(ACTOR_USERNAME).password == before

    ensure_ingest_accounts(db_session, reset_password=True)
    db_session.commit()
    assert _get(ACTOR_USERNAME).password != before


def test_specs_cover_exactly_the_two_usernames_the_pipeline_reads(app):
    """정책 표와 파이프라인 상수가 어긋나면 계정을 만들어도 수집이 못 찾는다."""
    assert {spec["username"] for spec in SPECS} == {ACTOR_USERNAME, OWNER_USERNAME}
