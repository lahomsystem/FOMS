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
import re
import time
import urllib.parse
from typing import Any, Optional

from flask import Blueprint, Response, jsonify, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as share_service
from foms.services.audit_message_display import describe_order_action
from foms.services.audit_writer import record_file_access
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_transfer import _is_drawing_key
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage
from foms.web.auth import log_access, login_required, role_required
from models import Order, OrderAttachment, OrderEvent, OrderShareToken, User

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


def _attachment_disposition(filename: str) -> str:
    """다운로드 강제용 Content-Disposition 값(한글 파일명 RFC 5987 인코딩).

    Args:
        filename: 원본 파일명.

    Returns:
        ``attachment; filename*=UTF-8''<인코딩>`` — R2/S3 presign 의
        ResponseContentDisposition 파라미터로 쓰면 브라우저가 열지 않고 저장한다.
    """
    quoted = urllib.parse.quote(filename, safe='')
    return f"attachment; filename*=UTF-8''{quoted}"


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

    if row.kind == 'estimate':
        # D6: 스냅샷만 렌더 — 라이브 재조회 없음(발급 이후 주문 수정은 반영되지 않는다).
        snap = row.snapshot
        if not isinstance(snap, dict) or not snap:
            # 스냅샷 없는 estimate 링크는 존재하면 안 되는 상태(생성 시 강제) — 명시 503.
            logger.error('estimate 공유 스냅샷 부재: share_id=%s', row.id)
            return _error_page(_MSG_UNAVAILABLE, 503)
        share_service.record_view(row)
        db_session.commit()
        record_file_access(
            'FILE_VIEW',
            storage_key=f'share/{row.id}',
            user_id=None,
            ip=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            order_id=order.id,
        )
        return render_template('orders/share_estimate_view.html', snap=snap)

    snapshot = None
    if row.kind == 'bundle':
        # 계약서 쪽은 estimate 와 같은 동결 규칙 — 스냅샷 없는 링크는 존재하면 안 된다.
        snapshot = row.snapshot
        if not isinstance(snapshot, dict) or not snapshot:
            logger.error('bundle 공유 스냅샷 부재: share_id=%s', row.id)
            return _error_page(_MSG_UNAVAILABLE, 503)

    storage = get_storage()
    if storage.storage_type not in ('r2', 's3'):
        # fail-closed(스펙 §3.2): 로컬 경로 노출 금지 — 503 + 안내 + 로그 1건.
        logger.error('공유 열람 fail-closed: storage_type=%s (r2/s3 아님, share_id=%s)',
                     storage.storage_type, row.id)
        return _error_page(_MSG_UNAVAILABLE, 503)

    cards: list[dict[str, str]] = []
    extra_files: list[dict[str, str]] = []
    download_files: list[dict[str, str]] = []
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
        # 고객 다운로드용 attachment presign — 열람 URL 과 별개(브라우저 저장 강제).
        dl_url = storage.get_download_url(
            entry['key'], expires_in=_PRESIGN_SECONDS,
            response_content_disposition=_attachment_disposition(entry['filename']))
        if dl_url:
            download_files.append({'url': dl_url, 'label': entry['filename']})
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
    # bundle 은 같은 도면 렌더 위에 동결 계약서를 얹는다(링크 하나로 둘 다 — 2026-08-25).
    template = ('orders/share_bundle_view.html' if row.kind == 'bundle'
                else 'orders/share_view.html')
    return render_template(
        template,
        share_kind=row.kind,
        snap=snapshot,
        drawing_preview_cards=cards,
        share_extra_files=extra_files,
        share_download_files=download_files,
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
    if kind not in share_service.SHARE_KINDS:
        return _envelope(None, 'unknown_kind', 400)

    order = (
        db_session.query(Order)
        .filter(Order.id == order_id, Order.active_filter())
        .one_or_none()
    )
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    snapshot = None
    if kind in share_service.SNAPSHOT_KINDS:
        # D6: 발송 시점 동결 — 스냅샷 없는 견적 링크는 존재하지 않는다.
        try:
            snapshot = share_service.build_estimate_snapshot(order)
        except share_service.SnapshotTooLargeError as exc:
            return _envelope(None, str(exc), 400)

    actor_user_id = session.get('user_id')
    row, token = share_service.create_share_token(
        db_session, order.id, kind, created_by_user_id=actor_user_id,
        snapshot=snapshot)
    db_session.commit()

    url = url_for('share_view.view_shared_order', token=token, _external=True)
    expires_iso = row.expires_at.isoformat()
    brand = ka.resolve_brand(order.structured_data or {})
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
        # 영업 본인 휴대폰 문자앱으로 바로 보내기(모바일)용 — 서버가 조립한 본문과
        # 정규화된 수신번호. 화면값 조립을 막아 알림톡 문구와 어긋나지 않게 한다.
        'to_phone': ka.extract_valid_phone(order.structured_data or {}) or '',
        'sms_text': share_link_message(order, kind=kind, url=url, brand=brand),
    }, None)


@share_api_bp.route('/list/<int:order_id>', methods=['GET'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_list(order_id: int):
    """주문의 발급 이력(메타만) — URL·토큰·해시는 절대 포함하지 않는다.

    해시-온리 저장이라 과거 링크의 URL 재표시는 원천 불가하다(플랜 §1) — UI 는
    "회수 후 재발급" 을 유도한다. 최신순 20건.

    Args:
        order_id: 대상 주문 id (URL).

    Returns:
        ``data = {'items': [{share_id, kind, status, created_at, expires_at,
        view_count, last_viewed_at}]}``. status = active|expired|revoked.
    """
    rows = (
        db_session.query(OrderShareToken)
        .filter(OrderShareToken.order_id == order_id)
        .order_by(OrderShareToken.id.desc())
        .limit(20)
        .all()
    )
    now = share_service.now_utc_naive()
    items = []
    for row in rows:
        if row.revoked_at is not None:
            status = 'revoked'
        elif row.expires_at <= now:
            status = 'expired'
        else:
            status = 'active'
        items.append({
            'share_id': row.id,
            'kind': row.kind,
            'status': status,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'expires_at': row.expires_at.isoformat() if row.expires_at else None,
            'view_count': row.view_count or 0,
            'last_viewed_at': row.last_viewed_at.isoformat() if row.last_viewed_at else None,
        })
    return _envelope({'items': items}, None)


#: send-sms 멱등 시간버킷(초) — 같은 버킷 내 재요청은 outbox UNIQUE 가 DB 로 차단(플랜 §1).
_SMS_BUCKET_SECONDS = 5

_SMS_KIND_LABEL = {'drawing': '도면', 'estimate': '견적서', 'bundle': '도면·계약서'}
#: 문자 본문 첫 줄의 발주사 표기(알림톡 승인 템플릿 문구와 같은 표기).
_BRAND_LABEL = {'LAHOM': '라홈', 'HAUD': '하우드'}


def _manager_sender_phone(order: Order) -> Optional[str]:
    """주문 담당자(``manager_name``)와 이름이 일치하는 활성 사용자의 sender_phone.

    동명이인은 id 오름차순 첫 등록자. 담당자 없음·미등록이면 ``None``.

    Args:
        order: 대상 주문.

    Returns:
        등록 발신번호 또는 ``None``.
    """
    manager = (order.manager_name or '').strip()
    if not manager:
        return None
    matched = (
        db_session.query(User)
        .filter(User.name == manager, User.is_active.is_(True),
                User.sender_phone.isnot(None))
        .order_by(User.id.asc())
        .first()
    )
    phone = ((matched.sender_phone if matched else None) or '').strip()
    return phone or None


def _resolve_sender(order: Order, brand: str) -> tuple[Optional[str], Optional[str]]:
    """발신번호 3단 우선순위 결정(T8.1 — 원장 '문자 발신번호 확정' 섹션이 정본).

    지방 주문이면 그 앞에 본사 CS 번호가 온다(안내 연락처와 같은 번호 — 2026-08-25).
    ① 주문 담당자(``manager_name``)와 이름이 일치하는 활성 사용자의 ``sender_phone``
    (발송 버튼 누른 직원 기준 아님 — 동명이인은 id 오름차순 첫 등록자) ② 브랜드
    대표번호 ``SOLAPI_SENDER_PHONE_{brand}`` ③ 구 ``SOLAPI_SENDER_PHONE`` 최후 폴백.
    ② 벤더 실패 시 백업 재시도는 :func:`_send_sms_with_fallback` 가 담당한다.

    Args:
        order: 대상 주문(담당자명 조회).
        brand: :func:`ka.resolve_brand` 결과(``LAHOM``/``HAUD``).

    Returns:
        ``(발신번호, 출처)`` — 출처는 ``regional_cs``/``manager``/``brand``/``legacy``.
        결정 불가면 ``(None, None)`` (호출자가 503 처리).
    """
    if _is_regional_order(order):
        # 지방 주문은 안내 연락처가 본사 CS 다. 카톡이 실패해 문자로 대체발송될 때
        # 발신번호가 담당자 번호면 고객 화면에는 두 번호가 따로 뜬다 — 같은 번호로 맞춘다
        # (사용자 결정 2026-08-25). 벤더에는 숫자만 넘긴다.
        digits = re.sub(r'\D', '', _regional_contact_phone(brand))
        if digits:
            return digits, 'regional_cs'
    phone = _manager_sender_phone(order)
    if phone:
        return phone, 'manager'
    phone = ka._env(f'SOLAPI_SENDER_PHONE_{brand}')
    if phone:
        return phone, 'brand'
    phone = ka._env('SOLAPI_SENDER_PHONE')
    if phone:
        return phone, 'legacy'
    return None, None


def _send_sms_with_fallback(
    share_id: int,
    *,
    to_phone: str,
    text: str,
    from_phone: str,
    sender_source: str,
    brand: str,
) -> tuple[Optional[str], list[dict[str, Any]]]:
    """벤더 발송 실행 — ② 브랜드 대표번호 실패 시에만 백업번호로 1회 재시도(T8.1).

    재시도는 같은 요청 내 동기 수행이며 멱등 앵커(선점 insert)는 호출자의 1개를
    공유한다 — 시도 이력은 attempts 로 반환해 이벤트 payload 에 기록한다.
    ``manager``/``legacy`` 출처 실패는 재시도하지 않는다(백업번호는 브랜드 전용).

    Args:
        share_id: 로그용 공유 row id.
        to_phone: 수신 휴대폰(숫자만).
        text: 발송 본문.
        from_phone: 1차 발신번호(:func:`_resolve_sender` 결과).
        sender_source: 1차 발신 출처(``regional_cs``/``manager``/``brand``/``legacy``).
            백업 재시도는 ``brand`` 일 때만 — 본사 CS·담당자 번호는 대체 후보가 없다.
        brand: 브랜드 판정(백업 env 키 ``SOLAPI_SENDER_FALLBACK_{brand}`` 결정).

    Returns:
        ``(최종 error, attempts)`` — attempts 는 시도별(최대 2건)
        ``{'from': 마스킹 번호, 'source': ..., 'error': ...}``.
    """
    attempts: list[dict[str, Any]] = []

    def _attempt(phone: str, source: str) -> Optional[str]:
        try:
            ka._solapi_send_text(to=to_phone, from_=phone, text=text)
            code: Optional[str] = None
        except Exception as exc:  # 벤더/네트워크 실패 분류 — 조용한 실패 금지
            code = ka._classify_error(exc)
            logger.warning('공유 문자 발송 실패: share_id=%s source=%s error=%s (%s)',
                           share_id, source, code, exc)
        attempts.append({'from': ka._mask_phone(phone), 'source': source, 'error': code})
        return code

    error = _attempt(from_phone, sender_source)
    if error is not None and sender_source == 'brand':
        backup = ka._env(f'SOLAPI_SENDER_FALLBACK_{brand}')
        if backup:
            error = _attempt(backup, 'brand_fallback')
    return error, attempts


@share_api_bp.route('/send-sms/<int:share_id>', methods=['POST'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_send_sms(share_id: int):
    """공유 링크 문자 발송(LMS) — 발급 직후 화면에서만 가능(D2·플랜 §1).

    body ``{'token': <원문>}``. 서버는 재해시가 저장 해시와 일치할 때만 URL 을
    조립한다(클라 본문·URL 불신). 멱등 = **발송 전 앵커 선점 insert**: OrderEvent+
    outbox 행을 벤더 호출 전에 commit, ``(effect_type, dedupe_key)`` UNIQUE 로 5초
    버킷 중복을 DB 가 차단(IntegrityError→409). 발신 = 3단 우선순위
    (:func:`_resolve_sender` — 담당자 개인번호 → 브랜드 대표번호 → 구
    ``SOLAPI_SENDER_PHONE``), 브랜드 대표번호 벤더 실패 시 백업번호 1회 재시도
    (:func:`_send_sms_with_fallback`).

    Args:
        share_id: 대상 공유 row id (URL).

    Returns:
        성공/벤더 실패 모두 200 + ``data={'sent', 'error'}``. 중복 409,
        토큰 불일치 400, 죽은 링크 410, 미설정 503.
    """
    row = db_session.get(OrderShareToken, share_id)
    if row is None:
        return _envelope(None, 'share_not_found', 404)

    token = str((request.get_json(silent=True) or {}).get('token') or '')
    if not token or share_service.hash_token(token) != row.token_hash:
        # 해시-온리 저장 — 원문 없이는 URL 재구성 불가. 목록의 과거 항목은 재발급 유도.
        return _envelope(None, 'token_mismatch', 400)

    _, code = share_service.verify_token(db_session, token)
    if code != share_service.VERIFY_OK:
        # 만료·회수 링크의 문자 발송 금지(죽은 링크 문자 차단 — 플랜 T8 계약).
        return _envelope(None, f'share_{code}', 410)

    order = (
        db_session.query(Order)
        .filter(Order.id == row.order_id, Order.active_filter())
        .one_or_none()
    )
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    to_phone = ka.extract_valid_phone(order.structured_data or {})
    if not to_phone:
        return _envelope(None, 'no_valid_phone', 400)

    actor_user_id = session.get('user_id')
    brand = ka.resolve_brand(order.structured_data or {})
    from_phone, sender_source = _resolve_sender(order, brand)
    if not from_phone:
        return _envelope(None, 'not_configured', 503)

    kind_label = _SMS_KIND_LABEL.get(row.kind, '문서')
    url = url_for('share_view.view_shared_order', token=token, _external=True)
    text = (
        f'안녕하세요. 요청하신 {kind_label} 열람 링크를 보내드립니다.\n'
        f'{url}\n'
        f'링크는 {share_service.token_days()}일간 유효합니다.'
    )

    # --- 선점 insert (벤더 호출 전 commit — check-then-act 레이스 봉쇄) ---
    bucket = int(time.time()) // _SMS_BUCKET_SECONDS
    event = OrderEvent(
        order_id=order.id,
        event_type='SHARE_SMS',
        payload={'share_id': row.id, 'kind': row.kind, 'status': 'in_flight',
                 'sent_by': actor_user_id},
        created_by_user_id=actor_user_id,
    )
    try:
        db_session.add(event)
        db_session.flush()
        outbox_row = enqueue_side_effect(
            db_session,
            source_domain='ORDER_EVENT',
            source_id=event.id,
            effect_type='SHARE_SMS',
            # 계약: 토큰 원문은 payload 에 절대 격납하지 않는다(bearer). URL 재구성이
            # 불가하므로 이 효과는 동기 전용이다 — 향후 워커는 이 행을 재발송하지 말고,
            # 소비 시 반드시 토큰 유효성(만료·회수)을 재검증해야 한다.
            payload={'share_id': row.id, 'order_id': order.id, 'sync_only': True},
            dedupe_key=f'share_sms:{row.id}:{bucket}',
        )
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
        return _envelope(None, 'duplicate_send', 409)

    # --- 동기 발송 (WORKER_OFF — 알림톡 T0.decision 계승) ---
    error, attempts = _send_sms_with_fallback(
        row.id, to_phone=to_phone, text=text,
        from_phone=from_phone, sender_source=sender_source, brand=brand)

    # 앵커 결과 기록 + outbox 종결(동기 전용 — 워커 재소비 방지, 성공·실패 무관 DONE).
    event.payload = {**(event.payload or {}), 'status': 'sent' if error is None else 'failed',
                     'error': error, 'attempts': attempts}
    flag_modified(event, 'payload')
    outbox_row.status = 'DONE'
    outbox_row.completed_at = now_utc_naive()
    db_session.commit()

    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action='SHARE_SMS_SENT',
                              note=None if error is None else f'실패: {error}', **context),
        actor_user_id,
        action='SHARE_SMS_SENT', target_type='order', target_id=int(order.id),
        detail={'share_id': row.id, 'kind': row.kind, 'sent': error is None,
                'error': error, 'to': ka._mask_phone(to_phone),
                'sender_source': attempts[-1]['source'] if attempts else None, **context},
    )
    return _envelope({'sent': error is None, 'error': error}, error)


def share_link_message(order: Order, *, kind: str, url: str, brand: str) -> str:
    """공유 링크 안내 문자 본문 — 승인 알림톡 템플릿과 같은 문구(버튼 대신 링크 인라인).

    알림톡은 WL 버튼이 링크를 들고 있지만 문자에는 버튼이 없어 본문에 URL 을 넣는다.
    담당자/연락처 폴백은 :func:`_share_alimtalk_variables` 와 같은 규칙이다.

    Args:
        order: 대상 주문.
        kind: 공유 종류(drawing/estimate).
        url: 열람 링크 절대 URL.
        brand: :func:`ka.resolve_brand` 결과(``LAHOM``/``HAUD``).

    Returns:
        문자앱에 채울 본문 문자열.
    """
    variables = _share_alimtalk_variables(order, kind=kind, token='', brand=brand)
    customer = variables['#{고객명}']
    kind_label = variables['#{문서종류}']
    days = variables['#{유효기간}']
    manager = variables['#{담당자}']
    manager_phone = variables['#{담당자연락처}']
    brand_label = _BRAND_LABEL.get(brand, '라홈')
    lines = [
        '안녕하세요 ' + customer + ' 고객님, ' + brand_label + '입니다.',
        '요청하신 ' + kind_label + ' 열람 링크를 보내드립니다.',
        '',
        '아래 링크를 누르시면 로그인 없이 도면·계약서 등 문서를 확인하고 다운로드하실 수 있습니다.',
        url,
        '',
        '유효기간 : ' + days + '일',
        '담당자 : ' + manager,
        '담당자 연락처 : ' + manager_phone,
    ]
    return '\n'.join(lines)

#: 지방(협력사 시공) 주문의 안내 연락처 — 브랜드별 본사 CS 대표번호(사용자 결정 2026-08-25).
#: 발주사에 '라홈'이 들어가면 라홈, 그 외 전부 하우드다(:func:`ka.resolve_brand` 규칙).
_REGIONAL_CONTACT_PHONE_DEFAULTS = {
    'LAHOM': '1566-0792',
    'HAUD': '1566-0703',
}

#: 대표번호가 바뀌면 코드 재배포 없이 갈아끼우는 env 접두(뒤에 브랜드가 붙는다).
_REGIONAL_CONTACT_PHONE_ENV_PREFIX = 'FOMS_REGIONAL_CONTACT_PHONE_'


def _is_regional_order(order: Order) -> bool:
    """지방(협력사 시공) 주문인지 — 안내 문구·발신번호를 본사 CS 로 돌리는 기준."""
    return bool(getattr(order, 'is_regional', False))


def _regional_contact_phone(brand: str) -> str:
    """지방 주문 안내에 쓸 본사 CS 대표번호(표시 형식 그대로).

    Args:
        brand: :func:`ka.resolve_brand` 결과(``LAHOM``/``HAUD``).

    Returns:
        브랜드 대표번호. 모르는 브랜드는 하우드 쪽으로 떨어뜨린다(라홈 외 전부 하우드).
    """
    fallback = _REGIONAL_CONTACT_PHONE_DEFAULTS.get(
        brand, _REGIONAL_CONTACT_PHONE_DEFAULTS['HAUD'])
    return ka._env(_REGIONAL_CONTACT_PHONE_ENV_PREFIX + brand) or fallback


def _share_contact_name(order: Order) -> str:
    """고객에게 보여줄 담당자 표기.

    지방 주문은 번호가 본사 CS 인데 이름만 현장 담당자면 고객이 누구에게 연락하는지
    헷갈린다 — 이름도 '고객센터' 로 맞춘다(사용자 결정 2026-08-25).
    """
    if _is_regional_order(order):
        return '고객센터'
    return (order.manager_name or '').strip() or '고객센터'


def _share_contact_phone(order: Order, brand: str) -> str:
    """고객에게 **보여줄** 문의 연락처.

    지방 주문은 협력사가 시공하지만 도면 컨펌은 본사 CS 가 받는다. 현장 담당자 번호를
    안내하면 컨펌 문의가 CS 를 건너뛰므로, 지방 주문에는 본사 대표번호를 넣는다
    (사용자 결정 2026-08-25). 그 외에는 담당자 등록번호 → 브랜드 대표 → 구 폴백 순.

    Args:
        order: 대상 주문.
        brand: :func:`ka.resolve_brand` 결과(``LAHOM``/``HAUD``).

    Returns:
        표시용 연락처 문자열(빈값 금지 — 알림톡 변수는 비울 수 없다).
    """
    if _is_regional_order(order):
        return _regional_contact_phone(brand)
    return (
        _manager_sender_phone(order)
        or ka._env(f'SOLAPI_SENDER_PHONE_{brand}')
        or ka._env('SOLAPI_SENDER_PHONE')
        or '고객센터'
    )


def _share_alimtalk_variables(order: Order, *, kind: str, token: str,
                              brand: str) -> dict[str, str]:
    """공유 알림톡 템플릿 변수(심사 승인 템플릿과 1:1 — 빈값 금지 폴백 포함).

    담당자/연락처 폴백 = "고객센터"/브랜드 대표번호(원장 결정 2026-08-13). 토큰은
    버튼 WL ``https://<운영 도메인>/s/#{토큰}`` 의 경로 변수다.

    Args:
        order: 대상 주문.
        kind: 공유 종류(drawing/estimate).
        token: 토큰 원문(재해시 검증 완료 전제).
        brand: :func:`ka.resolve_brand` 결과.

    Returns:
        ``{'#{고객명}': ..., ...}`` 치환 dict.
    """
    sd = order.structured_data or {}
    customer = str(ka._node(sd, 'parties', 'customer').get('name') or '').strip() or '고객'
    manager = _share_contact_name(order)
    manager_phone = _share_contact_phone(order, brand)
    return {
        '#{고객명}': customer,
        '#{문서종류}': _SMS_KIND_LABEL.get(kind, '문서'),
        '#{유효기간}': str(share_service.token_days()),
        '#{담당자}': manager,
        '#{담당자연락처}': manager_phone,
        '#{토큰}': token,
    }


@share_api_bp.route('/send-alimtalk/<int:share_id>', methods=['POST'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_send_alimtalk(share_id: int):
    """공유 링크 알림톡 발송 — 발급 직후 화면에서만 가능(send-sms 와 대칭).

    body ``{'token': <원문>}`` 재해시 검증 후 심사 승인 템플릿
    (``SOLAPI_TEMPLATE_SHARE_ID_{brand}``)으로 발송한다. 발신번호는 T8.1 3단
    우선순위(:func:`_resolve_sender`) — Solapi 가 알림톡 실패 시 이 번호로 SMS
    대체발송(failover)한다(담당자 번호 발신 요구). 멱등 = 선점 insert +
    ``share_alimtalk:{share_id}:{bucket}`` UNIQUE(409).

    Args:
        share_id: 대상 공유 row id (URL).

    Returns:
        성공/벤더 실패 모두 200 + ``data={'sent', 'error'}``. 중복 409,
        토큰 불일치 400, 죽은 링크 410, 미설정 503.
    """
    row = db_session.get(OrderShareToken, share_id)
    if row is None:
        return _envelope(None, 'share_not_found', 404)

    token = str((request.get_json(silent=True) or {}).get('token') or '')
    if not token or share_service.hash_token(token) != row.token_hash:
        return _envelope(None, 'token_mismatch', 400)

    _, code = share_service.verify_token(db_session, token)
    if code != share_service.VERIFY_OK:
        return _envelope(None, f'share_{code}', 410)

    order = (
        db_session.query(Order)
        .filter(Order.id == row.order_id, Order.active_filter())
        .one_or_none()
    )
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    to_phone = ka.extract_valid_phone(order.structured_data or {})
    if not to_phone:
        return _envelope(None, 'no_valid_phone', 400)

    actor_user_id = session.get('user_id')
    brand = ka.resolve_brand(order.structured_data or {})
    pf_id = ka._env(f'SOLAPI_PF_ID_{brand}')
    template_id = ka._env(f'SOLAPI_TEMPLATE_SHARE_ID_{brand}')
    from_phone, sender_source = _resolve_sender(order, brand)
    if not (pf_id and template_id and from_phone):
        return _envelope(None, 'not_configured', 503)

    variables = _share_alimtalk_variables(order, kind=row.kind, token=token, brand=brand)

    # --- 선점 insert (send-sms 와 동일 계약 — 벤더 호출 전 commit) ---
    bucket = int(time.time()) // _SMS_BUCKET_SECONDS
    event = OrderEvent(
        order_id=order.id,
        event_type='SHARE_ALIMTALK',
        payload={'share_id': row.id, 'kind': row.kind, 'status': 'in_flight',
                 'sent_by': actor_user_id},
        created_by_user_id=actor_user_id,
    )
    try:
        db_session.add(event)
        db_session.flush()
        outbox_row = enqueue_side_effect(
            db_session,
            source_domain='ORDER_EVENT',
            source_id=event.id,
            effect_type='SHARE_ALIMTALK',
            # 토큰 원문 미격납(bearer) — 동기 전용, 워커 재발송 금지(send-sms 계약 동일).
            payload={'share_id': row.id, 'order_id': order.id, 'sync_only': True},
            dedupe_key=f'share_alimtalk:{row.id}:{bucket}',
        )
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
        return _envelope(None, 'duplicate_send', 409)

    # --- 동기 발송 — 알림톡 실패 시 Solapi failover 가 from_ 번호로 SMS 대체발송 ---
    error: Optional[str] = None
    try:
        ka._solapi_send(to=to_phone, from_=from_phone, pf_id=pf_id,
                        template_id=template_id, variables=variables)
    except Exception as exc:  # 벤더/네트워크 실패 분류 — 조용한 실패 금지
        error = ka._classify_error(exc)
        logger.warning('공유 알림톡 발송 실패: share_id=%s source=%s error=%s (%s)',
                       row.id, sender_source, error, exc)

    event.payload = {**(event.payload or {}), 'status': 'sent' if error is None else 'failed',
                     'error': error, 'sender_source': sender_source}
    flag_modified(event, 'payload')
    outbox_row.status = 'DONE'
    outbox_row.completed_at = now_utc_naive()
    db_session.commit()

    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action='SHARE_ALIMTALK_SENT',
                              note=None if error is None else f'실패: {error}', **context),
        actor_user_id,
        action='SHARE_ALIMTALK_SENT', target_type='order', target_id=int(order.id),
        detail={'share_id': row.id, 'kind': row.kind, 'sent': error is None,
                'error': error, 'to': ka._mask_phone(to_phone),
                'sender_source': sender_source, **context},
    )
    return _envelope({'sent': error is None, 'error': error}, error)


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
