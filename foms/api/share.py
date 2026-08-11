"""고객 공유 열람 — 비로그인 열람 라우트 + 직원 API (Phase A).

스펙: docs/specs/2026-08-11-customer-share-phase-a-design.md §3.2~§3.3
플랜: docs/plans/2026-08-11-customer-share-phase-a-plan.md

flat 모듈이다 — namespace 닫힌집합 게이트는 디렉토리만 검사하므로 비저촉(플랜 §0).
비로그인 열람 Blueprint(``share_view_bp``, T2)와 직원 API Blueprint(T3)를 이 파일에
함께 둔다. rate limit 은 앱 default limits(fail-open — Redis 장애 시 통과)가 보조
방어선이고, 실질 방어선은 256bit 토큰 원문이다(해시-온리 저장).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, Response, jsonify, render_template, request, session, url_for

from db import db_session
from foms.services import order_share as share_service
from foms.services.audit_message_display import describe_order_action
from foms.services.audit_writer import record_file_access
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_transfer import _is_drawing_key
from foms.services.storage import get_storage
from foms.web.auth import log_access, login_required, role_required
from models import Order, OrderAttachment, OrderShareToken

logger = logging.getLogger(__name__)

share_view_bp = Blueprint('share_view', __name__)

#: presigned URL 수명(초) — 열람 페이지 체류 5분 초과 시 이미지 fetch 는 실패하고
#: 템플릿의 onerror 안내("새로고침")가 표면화한다(플랜 T2, 수용된 엣지).
_PRESIGN_SECONDS = 300

_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.avif')

_MSG_NOT_FOUND = '링크를 찾을 수 없습니다. 담당자에게 새 링크를 요청해 주세요.'
_MSG_GONE = '만료되었거나 회수된 링크입니다. 담당자에게 새 링크를 요청해 주세요.'
_MSG_UNAVAILABLE = '일시적으로 열람할 수 없습니다. 잠시 후 다시 시도해 주세요.'


@share_view_bp.after_request
def _share_headers(response: Response) -> Response:
    """모든 응답(오류 포함)에 noindex·no-referrer 를 강제한다(스펙 §3.2).

    Args:
        response: Flask 응답.

    Returns:
        헤더 2종이 부착된 응답.
    """
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def _error_page(message: str, status: int) -> tuple[str, int]:
    """고객용 오류 페이지(wam_error 재사용) 렌더.

    Args:
        message: 고객에게 보여줄 안내 문구(내부 사유 노출 금지).
        status: HTTP 상태코드(404/410/503).

    Returns:
        (렌더된 본문, 상태코드) 튜플.
    """
    return render_template('channel/wam_error.html', message=message), status


def _is_image(filename: str) -> bool:
    """확장자 기준 이미지 여부(갤러리 카드 vs 다운로드 링크 분기).

    Args:
        filename: 파일명 또는 storage key.

    Returns:
        이미지 확장자면 True.
    """
    return filename.lower().endswith(_IMAGE_EXTS)


def _collect_drawing_files(order: Order) -> list[dict[str, str]]:
    """주문의 도면 파일 ``{key, filename}`` 목록(주문 격리 필수).

    ``OrderAttachment(category='drawing')`` (soft delete 는 전역 visibility 필터가
    제외) + structured_data ``drawing_current_files`` 를 합치되, sd 쪽 key 는
    ``_is_drawing_key`` **allow-list 만** 통과시킨다(타 주문·실측 첨부 유출 차단 —
    deny-list 단독 금지, 플랜 T2). key 기준 dedupe.

    Args:
        order: 대상 주문(활성 검증은 호출자 소관).

    Returns:
        도면 파일 목록(첨부 → sd 순서 유지).
    """
    files: list[dict[str, str]] = []
    seen: set[str] = set()
    attachments = (
        db_session.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order.id,
                OrderAttachment.category == 'drawing')
        .order_by(OrderAttachment.id.asc())
        .all()
    )
    for att in attachments:
        key = (att.storage_key or '').strip()
        if not key or key in seen:
            continue
        seen.add(key)
        files.append({'key': key,
                      'filename': att.filename or key.rsplit('/', 1)[-1]})
    sd = order.structured_data or {}
    for entry in (sd.get('drawing_current_files') or []):
        if not isinstance(entry, dict):
            continue
        key = (entry.get('key') or '').strip()
        if not key or key in seen or not _is_drawing_key(order.id, key):
            continue
        seen.add(key)
        files.append({'key': key,
                      'filename': entry.get('filename') or key.rsplit('/', 1)[-1]})
    return files


@share_view_bp.get('/s/<token>')
def view_shared_order(token: str):
    """비로그인 공유 열람 — 검증 체인(해시→회수→만료→주문 활성) 후 도면 렌더.

    Args:
        token: URL 경로의 토큰 원문.

    Returns:
        200 열람 페이지, 404/410 wam_error, 503 fail-closed 안내.
    """
    row, code = share_service.verify_token(db_session, token)
    if code == share_service.VERIFY_NOT_FOUND:
        return _error_page(_MSG_NOT_FOUND, 404)
    if code in (share_service.VERIFY_REVOKED, share_service.VERIFY_EXPIRED):
        return _error_page(_MSG_GONE, 410)

    order = (
        db_session.query(Order)
        .filter(Order.id == row.order_id, Order.active_filter())
        .one_or_none()
    )
    if order is None:
        return _error_page(_MSG_NOT_FOUND, 404)
    if row.kind != 'drawing':
        # estimate 열람 렌더는 T7 해금 — 그때까지 존재 자체를 숨긴다.
        return _error_page(_MSG_NOT_FOUND, 404)

    storage = get_storage()
    if storage.storage_type not in ('r2', 's3'):
        # fail-closed(스펙 §3.2): 로컬 경로 노출 금지 — 503 + 안내 + 로그 1건.
        logger.error('공유 열람 fail-closed: storage_type=%s (r2/s3 아님, share_id=%s)',
                     storage.storage_type, row.id)
        return _error_page(_MSG_UNAVAILABLE, 503)

    cards: list[dict[str, str]] = []
    extra_files: list[dict[str, str]] = []
    presign_failures = 0
    collected = _collect_drawing_files(order)
    for entry in collected:
        url = storage.get_download_url(entry['key'], expires_in=_PRESIGN_SECONDS)
        if not url:
            presign_failures += 1
            logger.warning('공유 열람 presign 실패: share_id=%s key=%s', row.id, entry['key'])
            continue
        item = {'url': url, 'label': entry['filename']}
        (cards if _is_image(entry['filename']) else extra_files).append(item)
    if collected and not cards and not extra_files:
        # 파일이 있는데 전부 presign 실패 — 조용한 빈 갤러리 금지, 명시 503.
        logger.error('공유 열람 presign 전멸: share_id=%s (%d건)', row.id, presign_failures)
        return _error_page(_MSG_UNAVAILABLE, 503)

    share_service.record_view(row)
    db_session.commit()
    # 열람 감사(비로그인 user_id=None, PII 무). storage_key 는 공유 식별자로 기록 —
    # order_id 는 정수만 격납(audit_writer 비정수 fail-open 함정).
    record_file_access(
        'FILE_VIEW',
        storage_key=f'share/{row.id}',
        user_id=None,
        ip=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        order_id=order.id,
    )
    return render_template(
        'orders/share_view.html',
        share_kind=row.kind,
        drawing_preview_cards=cards,
        share_extra_files=extra_files,
    )


# ---------------------------------------------------------------------------
# 직원 API (T3) — CSRF/Origin 은 공용 write guard before_request 가 담당하므로
# 라우트에 별도 데코레이터를 두지 않는다(manifest 등재가 그 계약, kakao 선례).
# ---------------------------------------------------------------------------

share_api_bp = Blueprint('share_api', __name__, url_prefix='/api/share')

#: 알림톡 수동 발송 선례와 동일 권한(스펙 §3.3). VIEWER 는 제외.
_SHARE_ROLES = ['ADMIN', 'MANAGER', 'STAFF']


def _envelope(data: Any, error: Optional[str], status: int = 200):
    """프로젝트 표준 응답 ``{success, data, error}`` 를 만든다.

    Args:
        data: 성공 payload.
        error: 오류 코드(성공이면 ``None``).
        status: HTTP 상태코드.

    Returns:
        (jsonify 응답, 상태코드) 튜플.
    """
    return jsonify({'success': error is None, 'data': data, 'error': error}), status


@share_api_bp.route('/create/<int:order_id>', methods=['POST'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_create(order_id: int):
    """공유 링크 발급 — 토큰 원문은 이 응답에서 **1회만** 노출된다(해시-온리 저장).

    body ``{'kind': 'drawing'}``. Stage-1 은 drawing 만 허용 — 'estimate' 는 T6
    해금까지 400. URL 은 서버가 조립한다(자사 도메인, 단축 금지).

    Args:
        order_id: 대상 주문 id (URL).

    Returns:
        ``data = {'share_id', 'kind', 'token', 'url', 'expires_at'}``.
    """
    kind = (request.get_json(silent=True) or {}).get('kind') or 'drawing'
    if kind == 'estimate':
        # T6(스냅샷 빌더) 전까지는 발급 자체를 막는다 — 스냅샷 없는 견적 링크 금지(D6).
        return _envelope(None, 'estimate_not_available', 400)
    if kind not in share_service.SHARE_KINDS:
        return _envelope(None, 'unknown_kind', 400)

    order = (
        db_session.query(Order)
        .filter(Order.id == order_id, Order.active_filter())
        .one_or_none()
    )
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    actor_user_id = session.get('user_id')
    row, token = share_service.create_share_token(
        db_session, order.id, kind, created_by_user_id=actor_user_id)
    db_session.commit()

    url = url_for('share_view.view_shared_order', token=token, _external=True)
    expires_iso = row.expires_at.isoformat()
    context = order_audit_context(order)
    # 감사에는 토큰 원문·URL 을 남기지 않는다(감사 원장에 bearer 자격 축적 금지).
    log_access(
        describe_order_action(order_id=order.id, action='SHARE_LINK_CREATED',
                              note=kind, **context),
        actor_user_id,
        action='SHARE_LINK_CREATED', target_type='order', target_id=int(order.id),
        detail={'share_id': row.id, 'kind': kind, 'expires_at': expires_iso, **context},
    )
    return _envelope({
        'share_id': row.id,
        'kind': kind,
        'token': token,
        'url': url,
        'expires_at': expires_iso,
    }, None)


@share_api_bp.route('/revoke/<int:share_id>', methods=['POST'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_revoke(share_id: int):
    """공유 링크 회수 — 즉시 열람 차단(410). 멱등(재호출도 200).

    주문이 삭제됐어도 회수는 허용한다(잔존 링크를 죽이는 안전 방향 조작).

    Args:
        share_id: 대상 공유 row id (URL).

    Returns:
        ``data = {'share_id', 'revoked_at'}``.
    """
    row = db_session.get(OrderShareToken, share_id)
    if row is None:
        return _envelope(None, 'share_not_found', 404)

    share_service.revoke_token(row)
    db_session.commit()

    actor_user_id = session.get('user_id')
    order = db_session.get(Order, row.order_id)
    context = order_audit_context(order) if order is not None else {}
    log_access(
        describe_order_action(order_id=row.order_id, action='SHARE_LINK_REVOKED',
                              note=row.kind, **context),
        actor_user_id,
        action='SHARE_LINK_REVOKED', target_type='order', target_id=int(row.order_id),
        detail={'share_id': row.id, 'kind': row.kind,
                'revoked_at': row.revoked_at.isoformat(), **context},
    )
    return _envelope({'share_id': row.id, 'revoked_at': row.revoked_at.isoformat()}, None)
