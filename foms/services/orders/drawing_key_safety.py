"""공통 판정 "지워도 되는 키" — 파일을 지우는 모든 길이 이 한 곳을 거친다(원장 M5·M7, 2b).

1차 뒤 남은 파일 삭제 길은 셋이다: 전달 취소 회수(``cancel-transfer``) · 첨부 삭제 유예
purge(``DELETE /attachments/<id>``) · 공용 ``STORAGE_DELETE`` outbox 핸들러. 예전에는 각자
따로 판단해 복원된 현재 도면·이력이 가리키는 파일까지 지웠다. 이제 규칙은 하나다:

    **자기 주문 폴더이고, 지금 어떤 도면 기록·살아 있는 첨부 행도 쓰지 않는 key 만 지운다.**

주문 폴더 밖의 옛 모양 key 는 지우지 않는다(지우는 쪽보다 남기는 쪽이 안전 — 용량만 든다).
"""
from __future__ import annotations

import logging
import posixpath
from collections.abc import Iterable, Mapping
from typing import Any, Optional

from foms.services.files.upload_authz import ALLOWED_UPLOAD_SUBFOLDERS
from foms.services.orders.drawing_transfer import _is_drawing_key

logger = logging.getLogger(__name__)

__all__ = [
    "RETAIN_ATTACHMENT_IN_USE",
    "RETAIN_DRAWING_HISTORY",
    "RETAIN_FOREIGN_PATH",
    "RETAIN_OUTSIDE_DRAWING_SCOPE",
    "drawing_keys_in_use",
    "history_referenced_keys",
    "is_own_order_key",
    "referenced_keys",
    "split_deletable_keys",
]

#: 서버가 ``orders/<id>/`` 아래에 만드는 첫 하위 폴더 전부. 업로드 화이트리스트에는
#: ``drawing_wizard`` 가 없어(마법사 산출은 서버가 직접 올린다) 그대로 쓰면 마법사 파일이
#: 절대 "삭제 가능"이 되지 않는다.
_SERVER_SUBFOLDERS = frozenset(ALLOWED_UPLOAD_SUBFOLDERS | {"drawing_wizard"})

#: 보존 이유(로그·첨부 삭제 이벤트 ``retained_reason`` 에 싣는다).
RETAIN_FOREIGN_PATH = "FOREIGN_PATH"
RETAIN_OUTSIDE_DRAWING_SCOPE = "OUTSIDE_DRAWING_SCOPE"
RETAIN_DRAWING_HISTORY = "DRAWING_HISTORY"
RETAIN_ATTACHMENT_IN_USE = "ATTACHMENT_IN_USE"


def _file_keys(files: Any) -> set[str]:
    keys: set[str] = set()
    if not isinstance(files, (list, tuple)):
        return keys
    for f in files:
        if isinstance(f, Mapping):
            k = f.get("key")
            if isinstance(k, str) and k.strip():
                keys.add(k.strip())
    return keys


def history_referenced_keys(sd: Any) -> frozenset[str]:
    """도면 기록(현재본·마지막 전달·이력)이 가리키는 key 집합 — 마법사 제외.

    전달 취소의 **행** 보존 판정에 쓴다(§4.5): 복원 현재본이나 남은 이력이 가리키는 도면의
    첨부 행은 남긴다. 이력 중 TRANSFER ``files``·``previous_current_files``,
    CONFIRM_RECEIPT ``files``, REQUEST_REVISION ``files``, REVISION_CANCELLED
    ``request.files`` 를 모은다. 모르는 action 은 건너뛴다.

    Args:
        sd: 주문 ``structured_data``(dict 가 아니면 빈 집합).

    Returns:
        공백을 뺀 key 의 frozenset.
    """
    if not isinstance(sd, Mapping):
        return frozenset()
    keys = _file_keys(sd.get("drawing_current_files"))
    last = sd.get("last_drawing_transfer")
    if isinstance(last, Mapping):
        keys |= _file_keys(last.get("files"))
        keys |= _file_keys(last.get("previous_current_files"))
    for h in sd.get("drawing_transfer_history") or []:
        if not isinstance(h, Mapping):
            continue
        action = h.get("action")
        if action == "TRANSFER":
            keys |= _file_keys(h.get("files"))
            keys |= _file_keys(h.get("previous_current_files"))
        elif action in ("CONFIRM_RECEIPT", "REQUEST_REVISION"):
            keys |= _file_keys(h.get("files"))
        elif action == "REVISION_CANCELLED":
            req = h.get("request")
            if isinstance(req, Mapping):
                keys |= _file_keys(req.get("files"))
    return frozenset(keys)


def drawing_keys_in_use(sd: Any) -> frozenset[str]:
    """지금 어떤 도면 기록이든 쓰는 key 집합(파일 삭제 판정용).

    :func:`history_referenced_keys` 에 마법사 ``drawing_wizard.pending``(dict 값)의 ``key`` 와
    ``drawing_wizard.versions`` 항목의 ``key``, 도면 이미지 현재값 ``blueprint.current.object_key``
    를 더한다(마법사 화면·도면 이미지 화면이 아직 그 파일을 쓴다).

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        공백을 뺀 key 의 frozenset.
    """
    keys = set(history_referenced_keys(sd))
    if not isinstance(sd, Mapping):
        return frozenset(keys)
    wiz = sd.get("drawing_wizard")
    if isinstance(wiz, Mapping):
        pending = wiz.get("pending")
        if isinstance(pending, Mapping):
            keys |= _file_keys(list(pending.values()))
        keys |= _file_keys(wiz.get("versions"))
    bp = sd.get("blueprint")
    current = bp.get("current") if isinstance(bp, Mapping) else None
    if isinstance(current, Mapping):
        obj = current.get("object_key")
        if isinstance(obj, str) and obj.strip():
            keys.add(obj.strip())
    return frozenset(keys)


def is_own_order_key(order_id: Any, key: Any) -> bool:
    """key 가 이 주문 폴더 안, 서버가 만드는 하위 폴더의 정규 경로인지.

    앞뒤 공백·``\\``·절대경로·``..``·비정규 경로는 거부한다. 썸네일(``thumb_*``)은 본체와
    같은 폴더라 함께 통과한다.
    """
    if not order_id or not isinstance(key, str) or not key or key != key.strip():
        return False
    if key.startswith("/") or "\\" in key or "\x00" in key:
        return False
    if posixpath.normpath(key) != key:
        return False
    parts = key.split("/")
    if len(parts) < 4 or ".." in parts:
        return False
    return parts[0] == "orders" and parts[1] == str(order_id) and parts[2] in _SERVER_SUBFOLDERS


def _attachment_keys_in_use(db: Any, order_id: int, candidates: set[str],
                            exclude_attachment_ids: Iterable[int]) -> set[str]:
    """제외 목록 밖의 살아 있는 첨부 행이 storage_key·thumbnail_key 로 쓰는 후보(쿼리 1회)."""
    if not candidates:
        return set()
    from sqlalchemy import or_

    from models import OrderAttachment

    q = db.query(OrderAttachment.storage_key, OrderAttachment.thumbnail_key).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.deleted_at.is_(None),
        or_(OrderAttachment.storage_key.in_(list(candidates)),
            OrderAttachment.thumbnail_key.in_(list(candidates))),
    )
    excluded = [int(i) for i in exclude_attachment_ids or () if i is not None]
    if excluded:
        q = q.filter(OrderAttachment.id.notin_(excluded))
    used: set[str] = set()
    for storage_key, thumbnail_key in q.all():
        for k in (storage_key, thumbnail_key):
            if k in candidates:
                used.add(k)
    return used


def referenced_keys(db: Any, order_id: int, sd: Any, candidates: Iterable[str], *,
                    exclude_attachment_ids: Iterable[int] = ()) -> dict[str, str]:
    """후보 중 지금 **쓰이는** key 와 그 이유(경로 모양은 보지 않는다).

    STORAGE_DELETE 핸들러 재확인(§4.5)이 쓴다: 예약 뒤 7일 사이에 그 key 가 다시 현재본이
    되었거나 다른 첨부 행이 쓰면 지우지 않는다.

    Returns:
        ``{key: RETAIN_DRAWING_HISTORY | RETAIN_ATTACHMENT_IN_USE}``.
    """
    cands = {k.strip() for k in candidates if isinstance(k, str) and k.strip()}
    in_use: dict[str, str] = {}
    drawing = drawing_keys_in_use(sd)
    for k in cands:
        if k in drawing:
            in_use[k] = RETAIN_DRAWING_HISTORY
    rest = cands - set(in_use)
    for k in _attachment_keys_in_use(db, order_id, rest, exclude_attachment_ids):
        in_use[k] = RETAIN_ATTACHMENT_IN_USE
    return in_use


def split_deletable_keys(
    db: Any,
    order_id: int,
    sd_after: Any,
    candidates: Iterable[str],
    *,
    scope: str = "any",
    exclude_attachment_ids: Iterable[int] = (),
    reasons_out: Optional[dict[str, str]] = None,
) -> tuple[set[str], set[str]]:
    """후보 key 를 (지워도 되는 것, 남길 것) 으로 나눈다.

    삭제 가능 = (1) :func:`is_own_order_key` 통과 (1') ``scope='drawing'`` 이면 도면 폴더
    (``drawing_wizard/``·``drawing/``·``drawing_gateway/``)도 통과 (2) ``sd_after`` 의
    :func:`drawing_keys_in_use` 에 없음 (3) 제외 목록 밖 살아 있는 첨부 행이 쓰지 않음.
    남기는 key 는 이유와 함께 ``logger.info`` 로 남긴다.

    Args:
        db: 세션(첨부 행 조회 1회).
        order_id: 대상 주문 id.
        sd_after: 이번 변경을 반영한 뒤의 ``structured_data``.
        candidates: 지우려는 key 들.
        scope: ``'any'``(첨부 삭제·핸들러) 또는 ``'drawing'``(전달 취소).
        exclude_attachment_ids: 이번에 함께 지우는 첨부 행 id(그 행은 "쓰는 행"으로 치지 않는다).
        reasons_out: 주면 남기는 key → 이유 상수를 채운다.

    Returns:
        ``(deletable, retained)`` 두 집합.
    """
    cands = {k.strip() for k in candidates if isinstance(k, str) and k.strip()}
    reasons: dict[str, str] = {}
    for k in cands:
        if not is_own_order_key(order_id, k):
            reasons[k] = RETAIN_FOREIGN_PATH
        elif scope == "drawing" and not _is_drawing_key(order_id, k):
            reasons[k] = RETAIN_OUTSIDE_DRAWING_SCOPE
    reasons.update(referenced_keys(
        db, order_id, sd_after, cands - set(reasons),
        exclude_attachment_ids=exclude_attachment_ids,
    ))
    retained = set(reasons)
    deletable = cands - retained
    for k in sorted(retained):
        logger.info("[drawing-key-safety] order=%s keep key=%s reason=%s", order_id, k, reasons[k])
    if reasons_out is not None:
        reasons_out.update(reasons)
    return deletable, retained
