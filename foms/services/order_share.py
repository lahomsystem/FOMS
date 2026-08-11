"""고객 공유 열람 토큰 서비스 — 발급·검증·회수·열람 기록 (Phase A T1).

스펙: docs/specs/2026-08-11-customer-share-phase-a-design.md §3.1
플랜: docs/plans/2026-08-11-customer-share-phase-a-plan.md

토큰 원문은 발급 순간 1회만 반환하고 저장은 sha256 해시만 한다(해시-온리).
이 모듈은 토큰 레벨 DB 계층만 담당한다 — 주문 레벨 검증(``Order.active_filter()``·
draft 제외)과 라우트·감사는 T2~T3, estimate 스냅샷 빌더는 T6 소관.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import secrets
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import OrderShareToken

SHARE_KINDS = ('drawing', 'estimate')
_DEFAULT_TOKEN_DAYS = 30

# verify_token 상태코드 — 열람 라우트(T2)가 410/404 매핑에 사용한다.
VERIFY_OK = 'ok'
VERIFY_NOT_FOUND = 'not_found'
VERIFY_EXPIRED = 'expired'
VERIFY_REVOKED = 'revoked'


def token_days() -> int:
    """공유 토큰 유효기간(일).

    Returns:
        env ``FOMS_SHARE_TOKEN_DAYS`` 의 양의 정수 값, 아니면 기본 30(사용자 결정 D3).
    """
    try:
        days = int(os.environ.get('FOMS_SHARE_TOKEN_DAYS', ''))
    except ValueError:
        return _DEFAULT_TOKEN_DAYS
    return days if days > 0 else _DEFAULT_TOKEN_DAYS


def hash_token(token: str) -> str:
    """토큰 원문의 sha256 hex 해시(저장·조회 키).

    Args:
        token: ``secrets.token_urlsafe`` 원문.

    Returns:
        64자 hex 문자열.
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_share_token(
    session: Session,
    order_id: int,
    kind: str,
    created_by_user_id: Optional[int] = None,
    snapshot: Optional[dict[str, Any]] = None,
) -> tuple[OrderShareToken, str]:
    """공유 토큰 발급 — 토큰 원문은 이 반환값에서 1회만 노출된다.

    Args:
        session: DB 세션(commit 은 호출자 소관).
        order_id: 대상 주문 id.
        kind: ``SHARE_KINDS`` 중 하나('drawing'|'estimate').
        created_by_user_id: 발급 직원 id(감사 표시용, 선택).
        snapshot: estimate 전용 동결 렌더 데이터(T6 빌더 산출물, 선택).

    Returns:
        (저장된 row, 토큰 원문) 튜플. row 는 flush 되어 id 가 있다.

    Raises:
        ValueError: kind 가 ``SHARE_KINDS`` 밖일 때.
    """
    if kind not in SHARE_KINDS:
        raise ValueError(f"unknown share kind: {kind!r}")
    token = secrets.token_urlsafe(32)
    row = OrderShareToken(
        order_id=order_id,
        kind=kind,
        token_hash=hash_token(token),
        created_by_user_id=created_by_user_id,
        expires_at=now_utc_naive() + datetime.timedelta(days=token_days()),
        snapshot=snapshot,
    )
    session.add(row)
    session.flush()
    return row, token


def verify_token(
    session: Session, token: str
) -> tuple[Optional[OrderShareToken], str]:
    """토큰 원문을 검증한다(해시 조회 → 회수 → 만료 순).

    Args:
        session: DB 세션.
        token: URL 경로로 받은 토큰 원문.

    Returns:
        (row 또는 None, 상태코드). 회수·만료 판정에도 row 를 함께 반환한다
        (안내 페이지가 kind·주문 맥락을 알 수 있게). 상태코드는
        ``VERIFY_OK``/``VERIFY_NOT_FOUND``/``VERIFY_REVOKED``/``VERIFY_EXPIRED``.
    """
    row = (
        session.query(OrderShareToken)
        .filter(OrderShareToken.token_hash == hash_token(token))
        .one_or_none()
    )
    if row is None:
        return None, VERIFY_NOT_FOUND
    if row.revoked_at is not None:
        return row, VERIFY_REVOKED
    if row.expires_at <= now_utc_naive():
        return row, VERIFY_EXPIRED
    return row, VERIFY_OK


def revoke_token(row: OrderShareToken) -> None:
    """토큰 회수 — ``revoked_at`` 을 찍는다(멱등: 최초 회수 시각 보존).

    Args:
        row: 대상 토큰 row(commit 은 호출자 소관).
    """
    if row.revoked_at is None:
        row.revoked_at = now_utc_naive()


def record_view(row: OrderShareToken) -> None:
    """열람 1회 기록 — ``view_count`` 증가 + ``last_viewed_at`` 갱신.

    Args:
        row: 대상 토큰 row(commit 은 호출자 소관).
    """
    row.view_count = (row.view_count or 0) + 1
    row.last_viewed_at = now_utc_naive()
