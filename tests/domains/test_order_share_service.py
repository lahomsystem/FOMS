"""고객 공유 토큰 — 수명주기 테스트 (Phase A T1).

DB 픽스처는 tests/conftest.py 의 ``app``(in-memory sqlite) + ``db_session``
(test_kakao_alimtalk_send.py 선례). 열람 라우트·직원 API·감사는 T2~T3 범위 밖.
"""
import datetime

import pytest

from db import db_session
from foms.services import order_share as osvc
from foms.services.datetime_kst import now_utc_naive
from models import Order, OrderShareToken


def _mk_order() -> Order:
    """ERP 주문 1건을 커밋한다."""
    order = Order(
        received_date=datetime.date(2026, 8, 11),
        customer_name="임다슬",
        phone="010-2473-6730",
        address="Seoul",
        product="가구",
        status="ERPORDER",
        is_erp_order=True,
        structured_data={},
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def order(db):
    return _mk_order()


# --- create_share_token ---------------------------------------------------------


def test_create_returns_token_and_stores_hash_only(db, order):
    row, token = osvc.create_share_token(db, order.id, 'drawing')
    db.commit()

    assert len(token) >= 43  # token_urlsafe(32) = 43자
    assert row.token_hash == osvc.hash_token(token)
    assert row.token_hash != token
    assert len(row.token_hash) == 64
    # 원문은 DB 어디에도 없다 — 해시로만 조회 가능.
    assert db.query(OrderShareToken).filter_by(token_hash=token).one_or_none() is None
    assert row.kind == 'drawing'
    assert row.view_count == 0
    assert row.revoked_at is None
    assert row.snapshot is None


def test_create_expiry_defaults_to_30_days(db, order, monkeypatch):
    monkeypatch.delenv('FOMS_SHARE_TOKEN_DAYS', raising=False)
    row, _ = osvc.create_share_token(db, order.id, 'drawing')
    delta = row.expires_at - now_utc_naive()
    assert datetime.timedelta(days=29) < delta <= datetime.timedelta(days=30)


def test_create_expiry_env_override(db, order, monkeypatch):
    monkeypatch.setenv('FOMS_SHARE_TOKEN_DAYS', '7')
    row, _ = osvc.create_share_token(db, order.id, 'drawing')
    delta = row.expires_at - now_utc_naive()
    assert datetime.timedelta(days=6) < delta <= datetime.timedelta(days=7)


def test_create_expiry_env_garbage_falls_back(db, order, monkeypatch):
    for bad in ('abc', '0', '-3'):
        monkeypatch.setenv('FOMS_SHARE_TOKEN_DAYS', bad)
        row, _ = osvc.create_share_token(db, order.id, 'drawing')
        delta = row.expires_at - now_utc_naive()
        assert datetime.timedelta(days=29) < delta <= datetime.timedelta(days=30)


def test_create_rejects_unknown_kind(db, order):
    with pytest.raises(ValueError):
        osvc.create_share_token(db, order.id, 'contract')


def test_create_stores_estimate_snapshot(db, order):
    snap = {'items': [{'name': '무몰딩 여닫이', 'amount': 100000}]}
    row, _ = osvc.create_share_token(db, order.id, 'estimate', snapshot=snap)
    db.commit()
    db.expire_all()
    assert db.get(OrderShareToken, row.id).snapshot == snap


def test_create_tokens_are_unique(db, order):
    row1, t1 = osvc.create_share_token(db, order.id, 'drawing')
    row2, t2 = osvc.create_share_token(db, order.id, 'drawing')
    assert t1 != t2
    assert row1.token_hash != row2.token_hash


# --- verify_token ---------------------------------------------------------------


def test_verify_roundtrip_ok(db, order):
    row, token = osvc.create_share_token(db, order.id, 'drawing')
    db.commit()
    found, code = osvc.verify_token(db, token)
    assert code == osvc.VERIFY_OK
    assert found.id == row.id


def test_verify_unknown_token_not_found(db, order):
    found, code = osvc.verify_token(db, 'no-such-token')
    assert (found, code) == (None, osvc.VERIFY_NOT_FOUND)


def test_verify_expired_returns_row(db, order):
    row, token = osvc.create_share_token(db, order.id, 'drawing')
    row.expires_at = now_utc_naive() - datetime.timedelta(seconds=1)
    db.commit()
    found, code = osvc.verify_token(db, token)
    assert code == osvc.VERIFY_EXPIRED
    assert found.id == row.id


def test_verify_revoked_wins_over_expired(db, order):
    """회수가 만료보다 먼저 판정된다(회수 안내가 더 구체적)."""
    row, token = osvc.create_share_token(db, order.id, 'drawing')
    row.expires_at = now_utc_naive() - datetime.timedelta(seconds=1)
    osvc.revoke_token(row)
    db.commit()
    _, code = osvc.verify_token(db, token)
    assert code == osvc.VERIFY_REVOKED


# --- revoke_token / record_view -------------------------------------------------


def test_revoke_is_idempotent(db, order):
    row, _ = osvc.create_share_token(db, order.id, 'drawing')
    osvc.revoke_token(row)
    db.commit()
    first = row.revoked_at
    osvc.revoke_token(row)
    db.commit()
    assert row.revoked_at == first


def test_record_view_increments_and_stamps(db, order):
    row, _ = osvc.create_share_token(db, order.id, 'drawing')
    db.commit()
    osvc.record_view(row)
    osvc.record_view(row)
    db.commit()
    db.expire_all()
    fresh = db.get(OrderShareToken, row.id)
    assert fresh.view_count == 2
    assert fresh.last_viewed_at is not None
