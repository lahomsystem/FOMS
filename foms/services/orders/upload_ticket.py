"""UPLOAD-02: per-file 업로드 ticket 서비스 (issue / complete).

파일이 R2 에 도착하기 전에 per-file **ticket** 을 발급(:func:`issue_ticket`)하고, 파일이
확정되면 그 ticket 을 소비(:func:`complete_ticket`)해 :class:`~models.OrderAttachment` 로
반영한다. 두 단계 모두 **auth·resource·item-active 를 재검사**하며, complete 는 추가로
tamper(server-derived key 불일치)·expiry·type·size 를 검증한다. issue 의 object key 는
서버가 유도하므로(FILE-01/UPLOAD-01 canonical path) 클라이언트가 대상 경로를 바꿀 수 없다.

* **900s expiry**: ``expires_at = created_at + 900s``. complete 는 만료 ticket 을 거부하고,
  만료·item 은퇴로 orphan 이 된 ticket 은 :mod:`foms.services.upload_cleanup` 의 bounded
  scan provider 가 EXPIRED 로 claim 한다(별도 scheduler 없음 — SIDEFX worker 300s scan).
* **item-retire race**: complete 는 ticket·item identity 를 ``FOR UPDATE`` 로 잠가 동시
  retire 와 직렬화한다 — retire 가 먼저 커밋되면 complete 는 거부하고, complete 가 먼저면
  첨부 후 retire 가 tombstone 한다(no-reuse).
* **retry idempotent**: 이미 COMPLETED 인 ticket 재확정은 no-op(중복 첨부·Order version bump
  0) 이며 최초 확정으로 만든 첨부를 그대로 돌려준다.

경계(UPLOAD-02): 만료 정리 scheduler·R2 객체 삭제 실행은 이 모듈이 하지 않는다(cleanup
provider + worker 몫). 모든 함수는 ``flush`` 만 하고 ``commit`` 은 호출자가 소유한다.
"""
from __future__ import annotations

import datetime
import re
import uuid
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.files.upload_authz import (
    ALLOWED_UPLOAD_SUBFOLDERS,
    category_upload_allowed,
    validate_upload_key,
)
from foms.services.orders.item_identity import resolve_active_item_id
from models import (
    UPLOAD_TICKET_TTL_SECONDS,
    Order,
    OrderAttachment,
    OrderItemIdentity,
    UploadTicket,
)

__all__ = [
    "UploadTicketError",
    "UploadTicketForbidden",
    "complete_ticket",
    "issue_ticket",
]

_TTL = datetime.timedelta(seconds=UPLOAD_TICKET_TTL_SECONDS)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "gif", "webp"})
_VIDEO_EXTS = frozenset({"mp4", "mov", "avi", "mkv", "webm"})


class UploadTicketError(ValueError):
    """UPLOAD-02 ticket 계약 위반(부재 order/ticket, tamper, 만료, type/size, 잘못된 전이)."""


class UploadTicketForbidden(UploadTicketError):
    """auth 재검사 실패(VIEWER/무권한 팀 등) — route 는 403 으로 매핑한다."""


def _file_type(filename: str) -> str:
    """확장자로 image/video/file 을 판정한다(storage.get_file_type 와 동일 규칙, 순수 함수)."""
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    return "file"


def _normalize_category(category: Optional[str]) -> str:
    """첨부 category 정규화(measurement/drawing/construction/as, 그 외는 measurement)."""
    from foms.api.files.common import normalize_attachment_category  # 런타임 import(layering)

    return normalize_attachment_category(category) or "measurement"


def _derive_object_key(order_id: int, category: str, filename: str) -> str:
    """server-derived R2 object key 를 만든다(클라이언트 입력 아님).

    ``orders/{order_id}/{subfolder}/{uuid}_{safe_filename}`` 형태로, subfolder 는 category
    화이트리스트(없으면 ``attachments``)다. UPLOAD-01 :func:`validate_upload_key` 가 통과하는
    canonical 경로만 만든다(tamper 검사 시 exact-match 기준).
    """
    subfolder = category if category in ALLOWED_UPLOAD_SUBFOLDERS else "attachments"
    safe = _UNSAFE.sub("_", filename).strip("_") or "file"
    return f"orders/{order_id}/{subfolder}/{uuid.uuid4().hex}_{safe}"


def _check_type_size(filename: str, category: str, file_size: int) -> None:
    """확장자 정책(type)과 타입별 최대 크기(size)를 검증한다(FILE-01/UPLOAD-01 정책 재사용)."""
    from foms.api.files.common import (  # 런타임 import(layering)
        allowed_erp_attachment_file,
        get_erp_media_max_size,
    )

    if not allowed_erp_attachment_file(filename, category):
        raise UploadTicketError(f"허용되지 않은 파일 형식입니다: {filename!r}")
    max_size = get_erp_media_max_size(filename)
    if file_size is None or file_size < 0 or file_size > max_size:
        raise UploadTicketError(
            f"파일 크기가 유효하지 않습니다(0..{max_size}): {file_size!r}")


def _require_auth(user: Any, category: str) -> None:
    """category 업로드 권한을 재검사한다(VIEWER/무권한 팀 hard-deny). user None 도 거부."""
    if not category_upload_allowed(user, category):
        raise UploadTicketForbidden("이 업로드를 수행할 권한이 없습니다.")


def issue_ticket(
    session: Session,
    *,
    order_id: int,
    filename: str,
    file_size: int,
    user: Any,
    category: Optional[str] = None,
    item_index: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> UploadTicket:
    """per-file 업로드 ticket 을 발급한다(ISSUED, 900s expiry, server-derived key).

    auth(category 권한)·resource(order 존재)·item-active(슬롯 identity 활성)를 재검사하고
    type/size 를 검증한 뒤, 서버가 유도한 object key 로 ISSUED ticket 을 만든다.

    Args:
        session: business transaction 세션(호출자 소유·commit 미수행).
        order_id: 대상 주문 id.
        filename: 업로드 파일명(확장자 정책·file_type 판정에 사용).
        file_size: 선언 파일 크기(byte). 타입별 최대 크기 이내여야 한다.
        user: 발급 actor(``role``/``team`` 로 category 권한 재검사; None/VIEWER 는 거부).
        category: 첨부 용도(measurement/drawing/construction/as). None 이면 measurement.
        item_index: per-item 업로드면 아이템 슬롯 좌표. None 이면 order 공통 첨부.
        now: 기준 시각(테스트 주입용). 기본 :func:`now_utc_naive`.

    Returns:
        발급된 ISSUED :class:`~models.UploadTicket`.

    Raises:
        UploadTicketForbidden: category 업로드 권한 없음(VIEWER/무권한).
        UploadTicketError: order 부재, 활성 identity 없는 item_index, type/size 위반.
    """
    now = now or now_utc_naive()
    cat = _normalize_category(category)
    _require_auth(user, cat)

    order = session.get(Order, order_id)
    if order is None:
        raise UploadTicketError(f"주문 {order_id} 을(를) 찾을 수 없습니다.")

    item_id: Optional[str] = None
    if item_index is not None:
        item_id = resolve_active_item_id(session, order_id, item_index)
        if item_id is None:
            raise UploadTicketError(
                f"주문 {order_id} 의 item_index {item_index} 에 활성 아이템이 없습니다.")

    _check_type_size(filename, cat, file_size)

    object_key = _derive_object_key(order_id, cat, filename)
    ok_key, _key_category, key_err = validate_upload_key(object_key, order_id)
    if not ok_key:  # server-derived 라 정상 도달 불가(방어) — 유도 규칙과 정책 drift 감지.
        raise UploadTicketError(f"server-derived key 검증 실패: {key_err}")

    ticket = UploadTicket(
        order_id=order_id,
        category=cat,
        item_id=item_id,
        item_index=item_index,
        object_key=object_key,
        filename=filename,
        file_type=_file_type(filename),
        file_size=int(file_size),
        state="ISSUED",
        issued_by=getattr(user, "id", None),
        row_version=1,
        created_at=now,
        expires_at=now + _TTL,
    )
    session.add(ticket)
    session.flush()
    return ticket


def complete_ticket(
    session: Session,
    *,
    ticket_id: int,
    object_key: str,
    user: Any,
    file_size: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> Tuple[UploadTicket, OrderAttachment]:
    """ISSUED ticket 을 확정해 :class:`~models.OrderAttachment` 로 소비한다(REV-00 1회 bump).

    ticket 을 ``FOR UPDATE`` 로 잠근 뒤 auth·resource·item-active 를 재검사하고 tamper(key
    불일치)·expiry·type·size 를 검증한다. 최초 확정은 첨부 생성 + Order ``mutation_version``
    1회 bump + ticket→COMPLETED 이며, 이미 COMPLETED 인 ticket 재확정은 no-op(중복 첨부/bump
    0) 로 최초 첨부를 돌려준다(retry idempotent).

    Args:
        session: business transaction 세션(호출자 소유·commit 미수행).
        ticket_id: 확정할 ticket id.
        object_key: 클라이언트가 확정 요청한 key. ticket 의 server-derived key 와 **정확히**
            일치해야 한다(tamper 검사).
        user: 확정 actor(category 권한 재검사). None/VIEWER 거부.
        file_size: 확정 시 실측 크기(byte). None 이면 발급 시점 크기로 재검증.
        now: 기준 시각(테스트 주입용).

    Returns:
        ``(COMPLETED ticket, 소비된 OrderAttachment)``.

    Raises:
        UploadTicketForbidden: category 업로드 권한 없음.
        UploadTicketError: ticket 부재, key tamper, 만료, type/size 위반, EXPIRED/CANCELLED
            ticket 확정 시도, order 부재, item 은퇴(item-retire race).
    """
    now = now or now_utc_naive()
    ticket = (
        session.query(UploadTicket)
        .filter(UploadTicket.id == ticket_id)
        .with_for_update()
        .one_or_none()
    )
    if ticket is None:
        raise UploadTicketError(f"upload ticket {ticket_id} 을(를) 찾을 수 없습니다.")

    if ticket.state == "COMPLETED":
        # retry idempotent — 최초 확정으로 만든 첨부를 재조회해 그대로 반환(중복 부작용 0).
        attachment = (
            session.query(OrderAttachment)
            .filter(OrderAttachment.storage_key == ticket.object_key)
            .order_by(OrderAttachment.id)
            .first()
        )
        if attachment is None:
            raise UploadTicketError(
                f"COMPLETED ticket {ticket_id} 의 첨부를 찾을 수 없습니다(무결성 손상).")
        return ticket, attachment
    if ticket.state in ("EXPIRED", "CANCELLED"):
        raise UploadTicketError(
            f"ticket {ticket_id} 은(는) {ticket.state} 상태라 확정할 수 없습니다.")
    if now >= ticket.expires_at:
        raise UploadTicketError(f"ticket {ticket_id} 이(가) 만료되었습니다.")

    _require_auth(user, ticket.category)

    if object_key != ticket.object_key:  # tamper: server-derived key 와 exact-match.
        raise UploadTicketError("확정 key 가 발급된 key 와 일치하지 않습니다.")

    effective_size = ticket.file_size if file_size is None else int(file_size)
    _check_type_size(ticket.filename, ticket.category, effective_size)

    order = (
        session.query(Order)
        .filter(Order.id == ticket.order_id)
        .with_for_update()
        .one_or_none()
    )
    if order is None:
        raise UploadTicketError(f"주문 {ticket.order_id} 을(를) 찾을 수 없습니다.")

    if ticket.item_id is not None:
        # item-retire race: identity 를 잠가 동시 retire 와 직렬화한다. retire 가 먼저
        # 커밋되면 여기서 is_active=False 를 보고 거부(첨부가 은퇴 아이템에 묶이지 않음).
        identity = (
            session.query(OrderItemIdentity)
            .filter(OrderItemIdentity.id == ticket.item_id)
            .with_for_update()
            .one_or_none()
        )
        if identity is None or not identity.is_active:
            raise UploadTicketError(
                f"ticket {ticket_id} 의 아이템이 은퇴되어 확정할 수 없습니다.")

    attachment = OrderAttachment(
        order_id=ticket.order_id,
        filename=ticket.filename,
        file_type=ticket.file_type,
        category=ticket.category,
        item_index=ticket.item_index,
        item_id=ticket.item_id,
        file_size=effective_size,
        storage_key=ticket.object_key,
        thumbnail_key=None,
        user_id=ticket.issued_by,
    )
    session.add(attachment)

    order.mutation_version = (order.mutation_version or 0) + 1  # REV-00: 확정만 1회 bump.
    ticket.state = "COMPLETED"
    ticket.completed_at = now
    ticket.row_version = (ticket.row_version or 0) + 1
    session.flush()
    return ticket, attachment
