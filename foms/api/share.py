"""고객 공유 열람 — 비로그인 열람 라우트 + 직원 API (Phase A).

스펙: docs/specs/2026-08-11-customer-share-phase-a-design.md §3.2~§3.3
플랜: docs/plans/2026-08-11-customer-share-phase-a-plan.md

flat 모듈이다 — namespace 닫힌집합 게이트는 디렉토리만 검사하므로 비저촉(플랜 §0).
비로그인 열람 Blueprint(``share_view_bp``, T2)와 직원 API Blueprint(T3)를 이 파일에
함께 둔다. rate limit 은 앱 default limits(fail-open — Redis 장애 시 통과)가 보조
방어선이고, 실질 방어선은 256bit 토큰 원문이다(해시-온리 저장).
"""
from __future__ import annotations

import io
import logging
import re
import tempfile
import time
import urllib.parse
import zipfile
from typing import Any, Iterator, Optional

from flask import Blueprint, Response, jsonify, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as share_service
from foms.services import order_share_history as share_history
from foms.services.audit_message_display import describe_order_action
from foms.services.audit_writer import record_file_access
from foms.services.datetime_kst import (format_datetime_kst, get_today_kst,
                                        now_utc_naive)
from foms.services.erp_shipment_settings import load_erp_shipment_settings
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.drawing_transfer import _is_drawing_key
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage
from foms.web.auth import log_access, login_required, role_required
from models import (Order, OrderAttachment, OrderEvent, OrderShareSnapshot,
                    OrderShareToken, User)

# 합본 사진(drawings-sheet.png) 합성용. storage.py 와 같은 가드 방식 — Pillow 가 없는
# 런타임에서도 앱 import 는 살아 있어야 하고, 합본 라우트만 fail-closed(503) 로 죽는다.
try:
    from PIL import Image, UnidentifiedImageError

    _PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover - Pillow 는 requirements 고정
    Image = None  # type: ignore[assignment]
    UnidentifiedImageError = OSError  # type: ignore[misc,assignment]
    _PILLOW_AVAILABLE = False

logger = logging.getLogger(__name__)

share_view_bp = Blueprint('share_view', __name__)

#: presigned URL 수명(초) — 열람 페이지 체류 5분 초과 시 이미지 fetch 는 실패하고
#: 템플릿의 onerror 안내("새로고침")가 표면화한다(플랜 T2, 수용된 엣지).
_PRESIGN_SECONDS = 300

_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.avif')

#: 도면 일괄 저장(ZIP) 을 허용하는 공유 종류. estimate 는 도면이 없으므로 제외(404).
_ZIP_KINDS = ('drawing', 'bundle')

#: ZIP 에 담을 원본 총 바이트 상한. 넘으면 503 + 로그 1건(무한 메모리·무한 대기 금지).
#: 도면 1장이 보통 1~5MB 라 200MB 는 40~200장에 해당한다 — 실사용 상한을 크게 웃돈다.
_ZIP_MAX_TOTAL_BYTES = 200 * 1024 * 1024

#: 스풀이 메모리에 머무는 상한. 넘으면 SpooledTemporaryFile 이 디스크로 롤오버한다.
_ZIP_SPOOL_MAX_BYTES = 16 * 1024 * 1024

#: 응답 스트리밍 청크 크기.
_ZIP_CHUNK_BYTES = 64 * 1024

#: zip 항목명·다운로드 파일명에서 지우는 문자(경로 구분자·윈도 예약문자·제어문자).
_UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_MSG_NOT_FOUND = '링크를 찾을 수 없습니다. 담당자에게 새 링크를 요청해 주세요.'
_MSG_GONE = '만료되었거나 회수된 링크입니다. 담당자에게 새 링크를 요청해 주세요.'
_MSG_UNAVAILABLE = '일시적으로 열람할 수 없습니다. 잠시 후 다시 시도해 주세요.'
_MSG_ZIP_TOO_LARGE = ('도면 용량이 너무 커서 한 번에 저장할 수 없습니다. '
                      '아래 목록에서 하나씩 저장해 주세요.')
#: 일부만 담긴 zip 을 내보내지 않는다 — 고객이 전부 받았다고 오해한다.
_MSG_ZIP_PARTIAL = ('일부 도면을 불러오지 못해 한 번에 저장할 수 없습니다. '
                    '이전 화면에서 하나씩 저장해 주세요.')

#: 합본 사진(drawings-sheet.png) 폭 상한. 카톡 인앱에서 길게 눌러 저장하는 용도라
#: 폰 화면(≤430pt) 기준 2~3배면 충분하고, 그 위는 파일만 커진다.
_SHEET_MAX_WIDTH = 1400

#: 합본에서 장과 장 사이 흰 여백(px) — 도면 경계가 붙어 한 장으로 읽히지 않게.
_SHEET_GAP = 16

#: 합본 결과의 총 픽셀 상한. 넘으면 **거절하지 않고** 전체를 비율대로 줄여 맞춘다
#: (고객에게는 이 길 하나뿐이라 거절은 곧 저장 불가다). 줄여도 못 맞추면 503.
#:
#: 값은 iOS 웹뷰 기준이다. 이 사진은 폰에서 화면에 띄워 길게 눌러 저장하는 것이 본 경로라
#: 아이폰이 디코딩할 수 있어야 의미가 있다 — 40MP 는 RGB 로 펼치면 약 120MB 라 인앱
#: 웹뷰에서 통째로 실패할 수 있다. 저장소가 이미 쓰는 iOS 상한과 같은 값으로 맞춘다
#: (static/js/orders/share-contract.js 의 MAX_CANVAS_PIXELS).
_SHEET_MAX_PIXELS = 16_000_000

#: Pillow 가 던지는 좁은 예외 묶음. broad ``except Exception`` 은 failopen 인벤토리
#: 게이트가 잡으므로 쓰지 않는다(UnidentifiedImageError 는 OSError 하위지만 명시한다).
_SHEET_IMAGE_ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError,
                                                        UnidentifiedImageError)
if _PILLOW_AVAILABLE:  # DecompressionBombError 는 Exception 직계라 따로 넣어야 한다
    _SHEET_IMAGE_ERRORS = _SHEET_IMAGE_ERRORS + (Image.DecompressionBombError,)

#: ZIP 과 같은 규칙(일부만 담긴 결과물 금지)을 '사진' 표현으로.
_MSG_SHEET_PARTIAL = ('일부 도면을 불러오지 못해 사진 한 장으로 만들 수 없습니다. '
                      '이전 화면에서 하나씩 저장해 주세요.')
_MSG_SHEET_TOO_LARGE = ('도면이 너무 커서 사진 한 장으로 만들 수 없습니다. '
                        '이전 화면에서 하나씩 저장해 주세요.')


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


def _resolve_share_target(
    token: str,
) -> tuple[Optional[OrderShareToken], Optional[Order], Optional[tuple[str, int]]]:
    """공유 토큰 검증 체인 **단일 정본** — 해시 → 회수 → 만료 → 주문 활성.

    열람 페이지(:func:`view_shared_order`)와 ZIP 일괄 저장
    (:func:`download_shared_drawings_zip`)이 같은 체인을 쓰게 하려고 뽑아냈다.
    체인이 두 벌이면 한쪽만 고쳐 회수된 링크가 파일을 계속 내주는 구멍이 난다.

    Args:
        token: URL 경로의 토큰 원문.

    Returns:
        성공이면 ``(row, order, None)``. 실패면 ``(None, None, (본문, 상태코드))`` —
        호출자는 그 튜플을 그대로 반환하면 된다(404 없음/410 회수·만료).
    """
    row, code = share_service.verify_token(db_session, token)
    if code == share_service.VERIFY_NOT_FOUND:
        return None, None, _error_page(_MSG_NOT_FOUND, 404)
    if code in (share_service.VERIFY_REVOKED, share_service.VERIFY_EXPIRED):
        return None, None, _error_page(_MSG_GONE, 410)

    order = (
        db_session.query(Order)
        .filter(Order.id == row.order_id, Order.active_filter())
        .one_or_none()
    )
    if order is None:
        return None, None, _error_page(_MSG_NOT_FOUND, 404)
    return row, order, None


def _safe_name_part(value: Any, fallback: str, *, limit: int = 40) -> str:
    """다운로드 파일명에 넣을 조각을 살균한다(고객명 등 사용자 입력 유래).

    경로 구분자·윈도 예약문자·제어문자를 지우고 길이를 자른다. 남는 게 없으면
    ``fallback`` 을 쓴다 — 빈 조각이 ``도면__4114.zip`` 같은 모양을 만들지 않게.

    Args:
        value: 원본 값(고객명 등).
        fallback: 살균 후 비었을 때 쓸 대체 문자열.
        limit: 최대 길이.

    Returns:
        파일명에 넣어도 안전한 문자열.
    """
    cleaned = _UNSAFE_NAME_CHARS.sub('', str(value or '')).strip().strip('.')
    return cleaned[:limit] or fallback


def _zip_entry_name(filename: Any, index: int, used: set[str]) -> str:
    """zip 내부 항목명 — 살균 + 중복 시 ``이름 (2).png`` 번호 부여.

    항목명에 경로가 남으면 압축 해제 시 디렉토리가 생기거나(zip slip 계열) 뷰어가
    깨진다. basename 만 남기고 예약문자를 지운다.

    Args:
        filename: 원본 파일명(또는 storage key 꼬리).
        index: 살균 후 이름이 통째로 비었을 때 쓸 순번.
        used: 이미 담은 항목명 집합(호출자가 유지, 이 함수가 갱신한다).

    Returns:
        이 zip 안에서 유일한 항목명.
    """
    base = str(filename or '').rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    base = _UNSAFE_NAME_CHARS.sub('', base).strip().strip('.')
    if not base:
        base = f'도면-{index}'
    stem, dot, ext = base.rpartition('.')
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f'{stem} ({counter}).{ext}' if dot else f'{base} ({counter})'
        counter += 1
    used.add(candidate)
    return candidate


def _is_kakao_inapp(user_agent: Optional[str]) -> bool:
    """카카오톡 인앱 브라우저인지 — 저장 실패 시 "다른 브라우저" 안내를 켜는 기준.

    판정은 서버에서 한다(클라 분기는 스크립트가 죽으면 통째로 사라진다).

    Args:
        user_agent: 요청 User-Agent 원문(없을 수 있다).

    Returns:
        UA 에 ``KAKAOTALK`` 이 있으면 True.
    """
    return 'KAKAOTALK' in (user_agent or '').upper()


def _live_estimate_snapshot(row, order) -> tuple[Optional[dict], str]:
    """계약서 렌더 데이터를 **열람 시점에 다시 만든다**(라이브 반영).

    발급 시점 동결(D6)에서 바뀐 지점이다. 금액·품목을 고친 뒤 새 링크를 다시 보내야
    했던 것이 사용자 결정으로 뒤집혔다 — 같은 링크가 늘 최신 계약 내용을 보여준다.

    **유출 차단은 그대로다.** 라이브 값을 직접 템플릿에 넘기지 않고
    :func:`order_share.build_estimate_snapshot` 화이트리스트를 매번 다시 태운다 —
    타 브랜드 계좌·내부 플래그는 여전히 키 자체가 만들어지지 않는다.

    재구성이 실패하면(항목 과다 등) 발급 시점 스냅샷으로 내려간다. 고객에게 빈 화면을
    주는 것보다 조금 낡은 계약서가 낫다.

    Args:
        row: 공유 토큰 행(발급 시점 스냅샷 보유).
        order: 대상 주문(활성 검증 완료).

    Returns:
        ``(렌더용 dict, 출처)`` 튜플. 출처는 ``live``/``stored`` — 열람 이력 원장
        (SHARE-HIST-00)이 "왜 옛 금액이 떴나"를 답하려면 이 구별이 필요하다.
        라이브 재구성도 저장본도 없으면 dict 자리가 ``None``(호출자가 503).
    """
    stored = row.snapshot if isinstance(row.snapshot, dict) and row.snapshot else None
    try:
        live = share_service.build_estimate_snapshot(order)
    except share_service.SnapshotTooLargeError:
        logger.warning('공유 계약서 라이브 재구성 실패(항목 과다) — 발급본 사용: share_id=%s',
                       row.id)
        return stored, share_history.SOURCE_STORED
    if not isinstance(live, dict) or not live:
        return stored, share_history.SOURCE_STORED
    # 날짜 두 개를 가른다.
    #  * issued_date — 이 내용이 **언제 기준인지**. 주문이 마지막으로 바뀐 날을 쓴다.
    #    오늘 날짜를 박으면 아무것도 안 바뀐 계약서의 날짜가 매일 굴러간다.
    #  * contract_no_date — **계약번호**의 재료. 발급 시점에 고정한다. 여기까지 라이브로
    #    두면 고객이 들고 있는 계약번호가 날마다 달라진다.
    changed = format_datetime_kst(getattr(order, 'structured_updated_at', None),
                                  '%Y-%m-%d')
    live['issued_date'] = changed or get_today_kst().strftime('%Y-%m-%d')
    live['contract_no_date'] = ((stored or {}).get('issued_date')
                                or live['issued_date'])
    return live, share_history.SOURCE_LIVE


def _record_view_history(row, snapshot: dict, source: str) -> None:
    """고객이 지금 본 계약서를 열람 원장에 남긴다 (SHARE-HIST-00).

    라이브 반영으로 바뀐 뒤 "고객이 어제 본 금액"이 어디에도 없다는 공백을 메운다.
    내용이 바뀐 순간에만 새 행이 쌓인다(같은 내용 재열람은 횟수만 증가).

    **적재 실패가 고객 화면을 죽이면 안 된다** — 계약서를 못 보는 것이 이력이 한 건
    비는 것보다 나쁘다. 다만 조용히 넘기지 않고 ``logger.error`` 로 남긴다. 호출 순서도
    중요하다: 이 함수가 먼저 실행돼야 실패 시 rollback 이 ``record_view`` 증가분까지
    되돌리지 않는다(호출자가 이 뒤에 ``record_view`` → ``commit`` 한다).

    Args:
        row: 공유 토큰 행.
        snapshot: 화면에 렌더된 계약서 dict.
        source: ``live`` 또는 ``stored``.
    """
    try:
        share_history.record_snapshot_view(db_session, row, snapshot, source=source)
    except Exception:  # noqa: BLE001 - 증거 적재 실패로 고객 열람을 막지 않는다
        db_session.rollback()
        logger.error('공유 계약서 열람 이력 적재 실패: share_id=%s', row.id, exc_info=True)


@share_view_bp.get('/s/<token>')
def view_shared_order(token: str):
    """비로그인 공유 열람 — 검증 체인(해시→회수→만료→주문 활성) 후 도면 렌더.

    Args:
        token: URL 경로의 토큰 원문.

    Returns:
        200 열람 페이지, 404/410 wam_error, 503 fail-closed 안내.
    """
    row, order, failure = _resolve_share_target(token)
    if failure is not None:
        return failure

    if row.kind == 'estimate':
        # 라이브 반영 — 열람할 때마다 화이트리스트를 다시 태운다(사용자 결정 2026-09-01).
        snap, snap_source = _live_estimate_snapshot(row, order)
        if not isinstance(snap, dict) or not snap:
            # 라이브도 저장본도 없다 — 빈 계약서를 보여주지 않는다.
            logger.error('estimate 공유 렌더 데이터 부재: share_id=%s', row.id)
            return _error_page(_MSG_UNAVAILABLE, 503)
        _record_view_history(row, snap, snap_source)
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
        # 계약서 쪽은 estimate 와 같은 규칙 — 라이브 재구성.
        snapshot, snapshot_source = _live_estimate_snapshot(row, order)
        if not isinstance(snapshot, dict) or not snapshot:
            logger.error('bundle 공유 렌더 데이터 부재: share_id=%s', row.id)
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
        # 고객 다운로드용 attachment presign — 열람 URL 과 별개(브라우저 저장 강제).
        dl_url = storage.get_download_url(
            entry['key'], expires_in=_PRESIGN_SECONDS,
            response_content_disposition=_attachment_disposition(entry['filename']))
        # 카드 저장 아이콘은 이 값을 그대로 쓴다 — 인덱스 짝짓기 대신 카드에 실어
        # 내려야 presign 실패로 목록 길이가 어긋나도 엉뚱한 파일을 가리키지 않는다.
        item = {'url': url, 'label': entry['filename'], 'download_url': dl_url or ''}
        (cards if _is_image(entry['filename']) else extra_files).append(item)
        if dl_url:
            download_files.append({'url': dl_url, 'label': entry['filename']})
    if collected and not cards and not extra_files:
        # 파일이 있는데 전부 presign 실패 — 조용한 빈 갤러리 금지, 명시 503.
        logger.error('공유 열람 presign 전멸: share_id=%s (%d건)', row.id, presign_failures)
        return _error_page(_MSG_UNAVAILABLE, 503)

    if row.kind == 'bundle' and isinstance(snapshot, dict):
        _record_view_history(row, snapshot, snapshot_source)
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
        # 일괄 저장 버튼은 presign 성공 여부와 무관하다 — ZIP 라우트가 바이트를 직접 읽는다.
        share_drawing_count=len(collected),
        # 합본 사진은 이미지만 합친다(PDF 는 범위 밖) — 라벨·노출 판정은 이 수로 한다.
        share_image_count=sum(1 for e in collected if _is_image(e['filename'])),
        share_zip_url=url_for('share_view.download_shared_drawings_zip', token=token),
        share_sheet_url=url_for('share_view.download_shared_drawings_sheet', token=token),
        share_is_kakao_inapp=_is_kakao_inapp(request.headers.get('User-Agent')),
    )


@share_view_bp.get('/s/<token>/drawings.zip')
def download_shared_drawings_zip(token: str):
    """도면 전체를 zip 한 파일로 내려준다(비로그인 — 열람과 같은 검증 체인).

    카카오톡으로 받은 링크에서 도면을 한 장씩 길게 눌러 저장하던 것을 버튼 하나로
    바꾼다. 파일 수집은 :func:`_collect_drawing_files` 재사용이라 주문 격리
    allow-list 를 그대로 물려받는다.

    압축 방식은 ``ZIP_STORED``(무압축) 다 — 도면은 PNG/JPG 로 **이미 압축된**
    바이트라 DEFLATE 를 돌려도 크기는 거의 안 줄고 CPU 만 쓴다.

    바이트는 ``SpooledTemporaryFile`` 에 쌓아 :data:`_ZIP_SPOOL_MAX_BYTES` 를 넘으면
    디스크로 흘리고, 총합이 :data:`_ZIP_MAX_TOTAL_BYTES` 를 넘으면 만들다 말고 503 이다
    (메모리 무한 적재 금지). 완성된 스풀은 청크 단위로 스트리밍한다.

    Args:
        token: URL 경로의 토큰 원문.

    Returns:
        200 ``application/zip`` 스트림, 404(없는 토큰·estimate·도면 0건),
        410(회수·만료), 503(fail-closed·용량 초과·한 장이라도 읽기 실패).
    """
    row, order, failure = _resolve_share_target(token)
    if failure is not None:
        return failure

    if row.kind not in _ZIP_KINDS:
        # estimate 링크에는 도면이 없다 — 존재 자체를 숨긴다(404, 405 아님).
        return _error_page(_MSG_NOT_FOUND, 404)

    storage = get_storage()
    if storage.storage_type not in ('r2', 's3'):
        # fail-closed(스펙 §3.2): 로컬 경로 노출 금지 — 열람 라우트와 같은 규약.
        logger.error('공유 ZIP fail-closed: storage_type=%s (r2/s3 아님, share_id=%s)',
                     storage.storage_type, row.id)
        return _error_page(_MSG_UNAVAILABLE, 503)

    collected = _collect_drawing_files(order)
    if not collected:
        return _error_page(_MSG_NOT_FOUND, 404)

    spool = tempfile.SpooledTemporaryFile(max_size=_ZIP_SPOOL_MAX_BYTES)
    used_names: set[str] = set()
    total_bytes = 0
    packed = 0
    too_large = False
    # 상한 초과에도 여기서 곧장 return 하지 않는다 — ZipFile.__exit__ 가 중앙 디렉토리를
    # 쓰려고 스풀에 seek 하므로, 블록 안에서 스풀을 닫으면 ValueError 로 500 이 난다.
    with zipfile.ZipFile(spool, 'w', zipfile.ZIP_STORED) as archive:
        for index, entry in enumerate(collected, start=1):
            blob = storage.read_file_bytes(entry['key'])
            if blob is None:
                # 한 장이라도 실패하면 아래에서 503 — 불완전한 zip 을 내보내지 않는다.
                logger.warning('공유 ZIP 원본 읽기 실패: share_id=%s key=%s',
                               row.id, entry['key'])
                continue
            total_bytes += len(blob)
            if total_bytes > _ZIP_MAX_TOTAL_BYTES:
                logger.error('공유 ZIP 용량 초과: share_id=%s bytes=%s limit=%s files=%s',
                             row.id, total_bytes, _ZIP_MAX_TOTAL_BYTES, len(collected))
                too_large = True
                break
            archive.writestr(_zip_entry_name(entry['filename'], index, used_names), blob)
            packed += 1
    if too_large:
        spool.close()
        return _error_page(_MSG_ZIP_TOO_LARGE, 503)
    if packed < len(collected):
        # 일부만 담긴 zip 을 200 으로 내보내면 고객은 전부 받았다고 믿는다 — 버튼 라벨이
        # "전체 저장 (N개)" 이라 더 그렇다. 하나라도 빠지면 내보내지 않고 개별 저장으로
        # 안내한다(조용한 실패 금지).
        logger.error('공유 ZIP 일부 누락: share_id=%s packed=%d/%d',
                     row.id, packed, len(collected))
        spool.close()
        return _error_page(_MSG_ZIP_PARTIAL if packed else _MSG_UNAVAILABLE, 503)

    zip_size = spool.tell()  # ZipFile.close 가 중앙 디렉토리까지 쓴 뒤의 위치 = 총 크기
    spool.seek(0)

    # 열람과 같은 규약의 감사 1건. 액션은 이미 라벨 맵에 있는 FILE_DOWNLOAD 재사용
    # (새 액션 문자열은 audit_message_display 등재가 없으면 CI red).
    record_file_access(
        'FILE_DOWNLOAD',
        storage_key=f'share/{row.id}',
        user_id=None,
        ip=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        order_id=order.id,
    )

    filename = f'도면_{_safe_name_part(order.customer_name, "고객")}_{order.id}.zip'

    def _stream() -> Iterator[bytes]:
        """스풀을 청크로 흘리고 끝나면 반드시 닫는다(임시파일 누수 금지)."""
        try:
            while True:
                chunk = spool.read(_ZIP_CHUNK_BYTES)
                if not chunk:
                    break
                yield chunk
        finally:
            spool.close()

    response = Response(_stream(), mimetype='application/zip')
    response.headers['Content-Disposition'] = _attachment_disposition(filename)
    response.headers['Content-Length'] = str(zip_size)
    response.headers['Cache-Control'] = 'no-store'
    return response


def _flatten_image(blob: bytes):
    """원본 바이트를 흰 배경 위 RGB 이미지로 편다(합본 캔버스에 붙일 수 있는 형태).

    투명 PNG 를 그냥 ``convert('RGB')`` 하면 투명한 부분이 **검게** 나온다 — 도면은
    배경이 투명한 경우가 흔해서 그대로 두면 새까만 장이 섞인다.

    Args:
        blob: 이미지 원본 바이트.

    Returns:
        RGB 모드 :class:`PIL.Image.Image` (호출자가 close 책임).
    """
    with Image.open(io.BytesIO(blob)) as im:
        im.load()
        if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
            rgba = im.convert('RGBA')
            flat = Image.new('RGB', rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[-1])
            rgba.close()
            return flat
        return im.convert('RGB')


def _sheet_layout(sources: list, width: int, gaps: int) -> tuple[list[int], int]:
    """주어진 통일 폭에서 각 장의 높이와 합본 전체 높이를 계산한다.

    Args:
        sources: 원본 이미지 목록.
        width: 통일할 폭(px).
        gaps: 장 사이 여백의 총합(px).

    Returns:
        ``(장별 높이 목록, 합본 전체 높이)``.
    """
    heights = [max(1, round(im.height * width / im.width)) for im in sources]
    return heights, sum(heights) + gaps


def _compose_drawing_sheet(blobs: list[bytes], *,
                           share_id: int) -> tuple[Optional[bytes], Optional[str]]:
    """도면 이미지들을 세로로 이어 붙인 합본 PNG 를 만든다.

    카카오톡 인앱 웹뷰는 ``<a download>`` 를 무시하고 ``window.print()`` 도 없다.
    남는 길은 **이미지를 길게 눌러 사진첩에 저장**뿐이라, 여러 장을 한 장으로 합쳐
    한 번의 롱프레스로 전부 가져가게 한다(ZIP 은 폰에서 풀 수단이 없다).

    폭은 가장 넓은 장 기준으로 통일하되 :data:`_SHEET_MAX_WIDTH` 를 상한으로 둔다.
    총 픽셀이 :data:`_SHEET_MAX_PIXELS` 를 넘으면 **거절하지 않고** 비율대로 줄여
    맞춘다 — 여기서 거절하면 고객이 도면을 받을 길이 아예 없어진다.

    Args:
        blobs: 이미지 원본 바이트 목록(순서 = 화면 카드 순서).
        share_id: 로그 식별자(토큰 원문은 남기지 않는다).

    Returns:
        성공이면 ``(png 바이트, None)``. 실패면 ``(None, 고객 안내 문구)``.
    """
    if not _PILLOW_AVAILABLE:
        logger.error('공유 합본 사진 fail-closed: Pillow 미설치 (share_id=%s)', share_id)
        return None, _MSG_UNAVAILABLE

    sources: list = []
    try:
        for blob in blobs:
            sources.append(_flatten_image(blob))

        width = min(max(im.width for im in sources), _SHEET_MAX_WIDTH)
        gaps = _SHEET_GAP * (len(sources) - 1)
        heights, total = _sheet_layout(sources, width, gaps)
        # 반올림·여백 때문에 한 번에 딱 안 맞을 수 있어 몇 번 더 조인다.
        for _ in range(4):
            if width * total <= _SHEET_MAX_PIXELS or width <= 1:
                break
            shrink = (_SHEET_MAX_PIXELS / (width * total)) ** 0.5
            width = max(1, int(width * shrink))
            heights, total = _sheet_layout(sources, width, gaps)
        if width * total > _SHEET_MAX_PIXELS:
            logger.error('공유 합본 사진 축소 실패: share_id=%s px=%s limit=%s files=%s',
                         share_id, width * total, _SHEET_MAX_PIXELS, len(sources))
            return None, _MSG_SHEET_TOO_LARGE

        sheet = Image.new('RGB', (width, total), (255, 255, 255))
        offset = 0
        for source, height in zip(sources, heights):
            resized = source.resize((width, height), Image.Resampling.LANCZOS)
            sheet.paste(resized, (0, offset))
            resized.close()
            offset += height + _SHEET_GAP
        buffer = io.BytesIO()
        sheet.save(buffer, format='PNG')
        sheet.close()
        return buffer.getvalue(), None
    except _SHEET_IMAGE_ERRORS:
        # broad catch 금지(failopen 인벤토리) — Pillow 가 실제로 던지는 타입만 잡는다.
        logger.error('공유 합본 사진 합성 실패: share_id=%s files=%d',
                     share_id, len(blobs), exc_info=True)
        return None, _MSG_SHEET_PARTIAL
    finally:
        for source in sources:
            source.close()


@share_view_bp.get('/s/<token>/drawings-sheet.png')
def download_shared_drawings_sheet(token: str):
    """도면 이미지 전체를 **세로로 이어 붙인 사진 1장**으로 내려준다(비로그인).

    ZIP 은 폰에서 풀 수단이 없어 카톡으로 링크를 받은 고객에게는 죽은 버튼이다.
    이 라우트는 같은 도면을 PNG 한 장으로 합쳐 **inline** 으로 내보낸다 — 화면에
    떠 있어야 길게 눌러 사진첩에 저장할 수 있다. ``?download=1`` 이면 attachment.

    검증 체인·주문 격리·fail-closed 규약은 :func:`download_shared_drawings_zip` 와
    같다. 파일 수집도 :func:`_collect_drawing_files` 재사용이라 allow-list 를
    그대로 물려받는다. PDF 등 비이미지는 합치지 않고 무시한다(개별 저장 목록 몫).

    Args:
        token: URL 경로의 토큰 원문.

    Returns:
        200 ``image/png``, 404(없는 토큰·estimate·이미지 도면 0장),
        410(회수·만료), 503(fail-closed·한 장이라도 읽기/디코드 실패·축소 불가).
    """
    row, order, failure = _resolve_share_target(token)
    if failure is not None:
        return failure

    if row.kind not in _ZIP_KINDS:
        # estimate 링크에는 도면이 없다 — 존재 자체를 숨긴다(404, 405 아님).
        return _error_page(_MSG_NOT_FOUND, 404)

    storage = get_storage()
    if storage.storage_type not in ('r2', 's3'):
        # fail-closed(스펙 §3.2): 로컬 경로 노출 금지 — 열람·ZIP 과 같은 규약.
        logger.error('공유 합본 사진 fail-closed: storage_type=%s (r2/s3 아님, share_id=%s)',
                     storage.storage_type, row.id)
        return _error_page(_MSG_UNAVAILABLE, 503)

    images = [entry for entry in _collect_drawing_files(order)
              if _is_image(entry['filename'])]
    if not images:
        return _error_page(_MSG_NOT_FOUND, 404)

    blobs: list[bytes] = []
    for entry in images:
        blob = storage.read_file_bytes(entry['key'])
        if blob is None:
            # ZIP 과 같은 규칙 — 일부만 담긴 결과물을 내보내지 않는다. 고객은 버튼
            # 라벨("전체 저장 N장")을 믿고 다 받았다고 생각한다.
            logger.error('공유 합본 사진 원본 읽기 실패: share_id=%s key=%s',
                         row.id, entry['key'])
            return _error_page(_MSG_SHEET_PARTIAL, 503)
        blobs.append(blob)

    png, message = _compose_drawing_sheet(blobs, share_id=row.id)
    if png is None:
        return _error_page(message or _MSG_UNAVAILABLE, 503)

    # ZIP 라우트와 같은 감사 1건(액션은 라벨 맵에 이미 있는 FILE_DOWNLOAD 재사용).
    # record_view 는 부르지 않는다 — 저장은 열람이 아니다(view_count 부풀림 방지).
    record_file_access(
        'FILE_DOWNLOAD',
        storage_key=f'share/{row.id}',
        user_id=None,
        ip=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        order_id=order.id,
    )

    filename = f'도면_{_safe_name_part(order.customer_name, "고객")}_{order.id}.png'
    response = Response(png, mimetype='image/png')
    if request.args.get('download') == '1':
        response.headers['Content-Disposition'] = _attachment_disposition(filename)
    else:
        # 기본은 inline — 길게 눌러 저장하려면 화면에 떠 있어야 한다.
        quoted = urllib.parse.quote(filename, safe='')
        response.headers['Content-Disposition'] = f"inline; filename*=UTF-8''{quoted}"
    response.headers['Content-Length'] = str(len(png))
    response.headers['Cache-Control'] = 'no-store'
    return response


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


@share_api_bp.route('/history/<int:share_id>', methods=['GET'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_history(share_id: int):
    """공유 계약서 링크의 **고객 열람 이력** 목록 (SHARE-HIST-00).

    계약서가 라이브 반영이라 같은 링크가 시점마다 다른 금액을 보여준다. 이 목록이
    "고객이 언제 얼마짜리 계약서를 봤나"를 답한다. 내용이 바뀐 순간마다 1행이며,
    같은 내용 재열람은 ``view_count`` 로 접힌다.

    **스냅샷 원문은 싣지 않는다** — 목록 응답이 행마다 64KB 까지 부풀 수 있다.
    원문은 ``/history/<snapshot_id>/page`` 가 그 시점 화면 그대로 렌더한다.

    Args:
        share_id: 공유 토큰 id (URL).

    Returns:
        ``data = {'items': [{snapshot_id, content_hash, source, first_viewed_at,
        last_viewed_at, view_count, summary}]}`` 최신순 50건.
    """
    rows = share_history.list_rows(db_session, share_id)
    items = [{
        'snapshot_id': int(row.id),
        'content_hash': row.content_hash,
        'source': row.source,
        'first_viewed_at': row.first_viewed_at.isoformat() if row.first_viewed_at else None,
        'last_viewed_at': row.last_viewed_at.isoformat() if row.last_viewed_at else None,
        'view_count': row.view_count or 0,
        'summary': share_history.summarize(row.snapshot),
    } for row in rows]
    return _envelope({'items': items}, None)


@share_api_bp.route('/history/<int:snapshot_id>/page', methods=['GET'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_history_page(snapshot_id: int):
    """저장된 시점의 계약서를 **고객이 본 그 화면 그대로** 렌더한다 (SHARE-HIST-00).

    증거로 쓰려면 같은 파셜·같은 CSS 여야 하므로 사본을 만들지 않고 고객 템플릿
    (``share_estimate_view.html``)을 재사용한다. ERP 는 이 주소를 **새 탭**으로 연다 —
    ERP 셸에 공유 전용 CSS 를 끌어들이지 않아 스타일 오염이 0 이다.

    ``/api`` 접두어 아래 HTML 페이지가 되는 어색함은 감수한 것이다: 새 블루프린트·새
    디렉토리는 네임스페이스 닫힌집합 게이트를 건드리는데, 이 페이지는 공유 열람 기능의
    부속이라 그만한 값이 없다(스펙 §6).

    Args:
        snapshot_id: 열람 원장 행 id (URL).

    Returns:
        200 계약서 페이지, 404 없음.
    """
    row = (
        db_session.query(OrderShareSnapshot)
        .filter(OrderShareSnapshot.id == snapshot_id)
        .one_or_none()
    )
    if row is None or not isinstance(row.snapshot, dict) or not row.snapshot:
        return _error_page('요청하신 기록을 찾을 수 없습니다.', 404)

    viewed_at = format_datetime_kst(row.first_viewed_at, '%Y-%m-%d %H:%M') or ''
    log_access(
        f'고객 열람 계약서 기록 조회 (주문 {row.order_id}, {viewed_at})',
        session.get('user_id'),
        action='SHARE_HISTORY_VIEWED', target_type='order', target_id=int(row.order_id),
        detail={'snapshot_id': int(row.id), 'share_id': int(row.share_token_id),
                'kind': row.kind, 'source': row.source, 'viewed_at': viewed_at},
    )
    return render_template(
        'orders/share_estimate_view.html',
        snap=row.snapshot,
        # 고객 경로는 이 변수를 넘기지 않는다 — 템플릿이 정의 여부로 분기한다.
        history_meta={
            'viewed_at': viewed_at,
            'last_viewed_at': format_datetime_kst(row.last_viewed_at, '%Y-%m-%d %H:%M') or '',
            'view_count': row.view_count or 0,
            'source': row.source,
            'order_id': int(row.order_id),
        },
    )


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
        .filter(func.trim(User.name) == manager, User.is_active.is_(True),
                User.sender_phone.isnot(None))
        .order_by(User.id.asc())
        .first()
    )
    phone = ((matched.sender_phone if matched else None) or '').strip()
    return phone or None


def _settings_manager_phone(order: Order) -> Optional[str]:
    """출고설정 실측담당자 목록(``measurement_manager``)에서 담당자 전화번호를 찾는다.

    ``users.sender_phone`` 은 솔라피에 등록된 **발신** 번호라 등록 절차를 거친 사람만
    갖는다. 반면 이 목록은 실무가 이미 이름·전화로 관리하고 있어 표시용 연락처의
    현실적인 정본이다 — 그래서 **표시 전용**이고 발신번호로는 쓰지 않는다
    (미등록 번호를 from 으로 쓰면 발송 자체가 실패한다).

    이름 비교는 양쪽 모두 공백을 걷어낸 뒤 한다 — 설정 입력과 주문 입력이 서로 다른
    화면이라 공백 하나로 조용히 어긋나는 걸 막는다.

    Args:
        order: 대상 주문.

    Returns:
        등록된 전화번호(표시 형식 그대로) 또는 ``None``.
    """
    manager = (order.manager_name or '').strip()
    if not manager:
        return None
    try:
        settings = load_erp_shipment_settings() or {}
    except Exception:  # pragma: no cover - 설정 조회 실패가 발송을 막지는 않는다
        logger.warning('출고설정 담당자 연락처 조회 실패', exc_info=True)
        return None
    for entry in settings.get('measurement_manager') or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get('name') or '').strip() != manager:
            continue
        phone = str(entry.get('phone') or '').strip()
        if phone:
            return phone
    return None


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
    # 발송 흔적(화면 칩) — 알림톡 경로와 같은 레코드를 채널만 달리해 남긴다.
    last_share = ka.record_share_history(
        db_session, order, kind=row.kind, channel='sms',
        share_id=row.id, error=error, sent_by=actor_user_id)
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
    return _envelope({'sent': error is None, 'error': error, 'last_share': last_share}, error)


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
    (사용자 결정 2026-08-25). 그 외에는 담당자 등록번호(``users.sender_phone``) →
    출고설정 실측담당자 목록의 전화번호 → 브랜드 대표 → 구 폴백 순이다.
    **발신번호와 달리** 표시용은 솔라피 등록 여부와 무관하므로 설정 목록을 함께 본다.

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
        or _settings_manager_phone(order)
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


#: 버튼 2개짜리 통합 템플릿 env 접두(뒤에 브랜드가 붙는다). 심사 승인 뒤 이 env 를 넣으면
#: bundle 발송이 '링크 1개' 에서 '도면·계약서 버튼 2개' 로 갈아탄다 — 코드 변경 없이 env 스위치.
_BOTH_TEMPLATE_ENV_PREFIX = 'SOLAPI_TEMPLATE_SHARE_BOTH_ID_'


def _both_template_id(brand: str) -> str:
    """브랜드별 통합(버튼 2개) 템플릿 id. 미설정이면 빈 문자열(= 구 경로 유지)."""
    return ka._env(_BOTH_TEMPLATE_ENV_PREFIX + brand)


def _share_both_variables(order: Order, *, drawing_token: str, estimate_token: str,
                          brand: str) -> dict[str, str]:
    """버튼 2개 템플릿 변수(승인 템플릿과 1:1).

    문서종류는 본문에 고정 문구로 들어가므로 변수가 없고, 토큰이 둘이다.

    Args:
        order: 대상 주문.
        drawing_token: 도면 링크 토큰 원문.
        estimate_token: 계약서 링크 토큰 원문.
        brand: :func:`ka.resolve_brand` 결과.

    Returns:
        치환 dict — 빈값 금지 폴백은 :func:`_share_alimtalk_variables` 와 같은 규칙.
    """
    sd = order.structured_data or {}
    customer = str(ka._node(sd, 'parties', 'customer').get('name') or '').strip() or '고객'
    return {
        '#{고객명}': customer,
        '#{유효기간}': str(share_service.token_days()),
        '#{담당자}': _share_contact_name(order),
        '#{담당자연락처}': _share_contact_phone(order, brand),
        '#{도면토큰}': drawing_token,
        '#{계약서토큰}': estimate_token,
    }


def _issue_pair_tokens(order: Order) -> tuple[Any, str, Any, str]:
    """버튼 2개 발송용 도면·계약서 링크를 새로 발급한다(커밋은 호출자 몫).

    계약서 링크는 발급 시점 동결 스냅샷을 동반한다 — 단독 발급과 같은 규칙(D6).

    Args:
        order: 대상 주문.

    Returns:
        ``(도면 row, 도면 토큰, 계약서 row, 계약서 토큰)``.

    Raises:
        share_service.SnapshotTooLargeError: 견적 항목이 스냅샷 상한을 넘을 때.
    """
    drawing_row, drawing_token = share_service.create_share_token(
        db_session, order.id, 'drawing')
    snapshot = share_service.build_estimate_snapshot(order)
    estimate_row, estimate_token = share_service.create_share_token(
        db_session, order.id, 'estimate', snapshot=snapshot)
    return drawing_row, drawing_token, estimate_row, estimate_token


@share_api_bp.route('/send-alimtalk/<int:share_id>', methods=['POST'])
@login_required
@role_required(_SHARE_ROLES)
def api_share_send_alimtalk(share_id: int):
    """공유 링크 알림톡 발송 — 발급 직후 화면에서만 가능(send-sms 와 대칭).

    body ``{'token': <원문>}`` 재해시 검증 후 심사 승인 템플릿
    (``SOLAPI_TEMPLATE_SHARE_ID_{brand}``)으로 발송한다. ``kind='bundle'`` 이고 통합
    템플릿(``SOLAPI_TEMPLATE_SHARE_BOTH_ID_{brand}``)이 등록돼 있으면 도면·계약서 링크를
    그 자리에서 발급해 **버튼 2개** 템플릿으로 내보낸다(승인 전후 전환이 env 하나). 발신번호는 T8.1 3단
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
    # bundle 은 통합 템플릿(버튼 2개)이 승인·등록돼 있으면 그쪽으로 나간다. env 가 없으면
    # 지금처럼 링크 1개(통합 열람 페이지)로 나간다 — 승인 전후 전환이 env 하나다.
    use_both = row.kind == 'bundle' and bool(_both_template_id(brand))
    template_id = (_both_template_id(brand) if use_both
                   else ka._env(f'SOLAPI_TEMPLATE_SHARE_ID_{brand}'))
    from_phone, sender_source = _resolve_sender(order, brand)
    if not (pf_id and template_id and from_phone):
        return _envelope(None, 'not_configured', 503)

    pair_ids: dict[str, int] = {}
    if use_both:
        try:
            drawing_row, drawing_token, estimate_row, estimate_token = _issue_pair_tokens(order)
        except share_service.SnapshotTooLargeError:
            db_session.rollback()
            return _envelope(None, 'snapshot_too_large', 400)
        variables = _share_both_variables(order, drawing_token=drawing_token,
                                          estimate_token=estimate_token, brand=brand)
        pair_ids = {'drawing_share_id': drawing_row.id, 'estimate_share_id': estimate_row.id}
    else:
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
    # 발송 흔적(화면 칩) — sd 쓰기는 정본 소유 모듈이 한다(REV-99 writer 분류는 파일 단위).
    last_share = ka.record_share_history(
        db_session, order, kind=row.kind, channel='alimtalk',
        share_id=row.id, error=error, sent_by=actor_user_id)
    db_session.commit()

    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action='SHARE_ALIMTALK_SENT',
                              note=None if error is None else f'실패: {error}', **context),
        actor_user_id,
        action='SHARE_ALIMTALK_SENT', target_type='order', target_id=int(order.id),
        detail={'share_id': row.id, 'kind': row.kind, 'sent': error is None,
                'error': error, 'to': ka._mask_phone(to_phone),
                'template': 'share_both' if use_both else 'share',
                'sender_source': sender_source, **pair_ids, **context},
    )
    return _envelope({'sent': error is None, 'error': error, 'last_share': last_share}, error)


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
