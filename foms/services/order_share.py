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

#: estimate 스냅샷 직렬화 상한 — drawing_wizard 64KB 캡 선례(플랜 §1).
SNAPSHOT_MAX_BYTES = 65_536

SNAPSHOT_TOO_LARGE_MSG = '견적 항목이 너무 많아 공유 스냅샷을 만들 수 없습니다'

#: 스냅샷 품목 행에 허용되는 키 — 그 외는 구성 단계에서 소거된다(D5 화이트리스트).
_SNAPSHOT_ITEM_KEYS = (
    'product_name', 'spec', 'color', 'option_detail',
    'quantity', 'unit_price', 'amount',
)


class SnapshotTooLargeError(ValueError):
    """estimate 스냅샷이 64KB 캡을 넘었다 — 절단 없이 발급을 거절한다(금액 문서)."""

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


def build_estimate_snapshot(order: 'Order') -> dict[str, Any]:
    """견적 공유용 **동결 스냅샷**을 화이트리스트로 구성한다(D5·D6).

    렌더 SSOT(:func:`extract_estimate_data_from_order`)에서 허용 필드만 **새 dict 로
    복사**한다 — 차단 대상(타 브랜드 계좌·factory2/is_lahom 내부 플래그·variants)은
    키 자체가 존재하지 않는다. 계좌·공급자 정보는 발주사 판정(factory2)에 따른
    **해당 브랜드 1벌만** 담는다.

    Args:
        order: 대상 주문(활성 검증은 호출자 소관).

    Returns:
        스냅샷 dict(snapshot_version=1). 열람(T7)은 이 dict 만 렌더한다.

    Raises:
        SnapshotTooLargeError: 직렬화가 ``SNAPSHOT_MAX_BYTES`` 를 넘을 때.
    """
    import json

    from foms.services.datetime_kst import get_today_kst
    from foms.services.estimate_service import extract_estimate_data_from_order
    from foms.services.orders.estimate_defaults import (
        resolve_estimate_company_info,
        resolve_estimate_payment_info,
    )

    data = extract_estimate_data_from_order(order)
    factory2 = bool(data.get('factory2'))
    company = resolve_estimate_company_info(factory2)
    payment = resolve_estimate_payment_info(factory2)

    items = []
    for item in data.get('items') or []:
        if not isinstance(item, dict):
            continue
        items.append({key: item.get(key) for key in _SNAPSHOT_ITEM_KEYS})

    snapshot: dict[str, Any] = {
        'snapshot_version': 1,
        'issued_date': get_today_kst().strftime('%Y-%m-%d'),
        'customer_name': data.get('customer_name') or '',
        'customer_phone': data.get('customer_phone') or '',
        'site_address': data.get('site_address') or '',
        'construction_date': data.get('construction_date'),
        'manager_name': data.get('manager_name') or '',
        'manager_phone': data.get('manager_phone') or '',
        'items': items,
        'items_subtotal': int(data.get('items_subtotal') or 0),
        'free_input_lines': [
            {'label': str(row.get('label') or ''), 'amount': int(row.get('amount') or 0)}
            for row in (data.get('free_input_lines') or [])
            if isinstance(row, dict)
        ],
        'free_input_amount': int(data.get('free_input_amount') or 0),
        'shipping_price': int(data.get('shipping_price') or 0),
        'discount_amount': int(data.get('discount_amount') or 0),
        'deposit_amount': int(data.get('deposit_amount') or 0),
        'balance_amount': int(data.get('balance_amount') or 0),
        'company_info': {
            'name': company.get('name') or '',
            'ceo': company.get('ceo') or '',
            'business_number': company.get('business_number') or '',
            'address': company.get('address') or '',
            'industry': company.get('industry') or '',
            'phone': company.get('phone') or '',
            'customer_center': company.get('customer_center') or '',
            'website': company.get('website') or '',
        },
        'payment_info': {
            'notice': payment.get('notice') or '',
            'accounts': [
                {'bank': acc.get('bank') or '', 'account': acc.get('account') or '',
                 'holder': acc.get('holder') or ''}
                for acc in (payment.get('accounts') or [])
                if isinstance(acc, dict)
            ],
        },
    }
    size = len(json.dumps(snapshot, ensure_ascii=False).encode('utf-8'))
    if size > SNAPSHOT_MAX_BYTES:
        raise SnapshotTooLargeError(SNAPSHOT_TOO_LARGE_MSG)
    return snapshot


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
