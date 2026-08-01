"""BLUEPRINT-01: 주문 도면(blueprint) 현재 이미지 typed projection + legacy safe backfill.

legacy blueprint route(P0-11)는 도면 이미지를 ``orders.blueprint_image_url`` scalar 에 **직접
쓰고**(version/event 없음) 삭제도 동기였다. 이 모듈은 그 scalar 를 대체하는 **typed current
projection** 을 소유한다.

* **저장 위치**: ``structured_data['blueprint']['current']`` sub-key(dict). 최상위
  ``structured_data['blueprint']`` 는 고객 컨펌 상태(``customer_confirmed`` 등)가 이미 쓰는
  server-owned 키이며 DATA-01 preserve list 에 있으므로, 이미지 projection 은 그 dict 를
  **보존한 채 ``current`` sub-key 만** 다룬다(다른 blueprint 키 무손실).
* **scalar 병행(projection, direct write 아님)**: read 소비처(템플릿·검색·storage cleanup)가
  아직 ``order.blueprint_image_url`` 을 읽으므로 무회귀를 위해 scalar 를 **파생값으로 병행**
  갱신한다 — 단, 반드시 version bump·event 를 동반하는 mutation tx 안에서만 갱신한다(bare
  ``order.blueprint_image_url = X`` + commit 금지).
* **event**: 저장/교체/삭제마다 :class:`~models.OrderEvent`(``BLUEPRINT_SET`` /
  ``BLUEPRINT_REPLACED`` / ``BLUEPRINT_DELETED``) 를 남긴다.
* **typed replace / delete outbox**: 교체·삭제 시 이전 R2 object 는 **동기 삭제하지 않고**
  ``STORAGE_DELETE`` outbox(source_domain=``ORDER_EVENT``) 로 예약한다(SIDEFX worker 소비).

**legacy safe backfill(100%)**: 기존 scalar URL 을 projection 으로 무손실 이전한다.
``/api/files/view/<key>`` 형태이고 그 key 가 대상 order 기준 canonical(:func:`validate_upload_key`
통과)일 때만 ``object_key`` 를 **유도(exact)** 하고, 그 밖의 외부/비정규 URL 은 **object_key 를
자동 추정하지 않고**(ambiguous auto-map 금지) 원문 URL 을 ``view_url`` 로 보존한다. 어느 쪽이든
원문 URL 은 손실되지 않는다(coverage 100% = exact + ambiguous-preserved).

경계: R2 객체 실삭제·프론트 업로드 배선은 이 모듈이 하지 않는다(worker·후속 롤아웃 몫).
호출자가 ``session.commit()`` 을 소유한다(이 모듈은 ``flush`` 만).
"""
from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.files.upload_authz import validate_upload_key
from foms.services.sidefx_outbox import enqueue_side_effect
from models import Order, OrderAttachment, OrderEvent

BLUEPRINT_KEY = "blueprint"          # structured_data 최상위(고객 컨펌 상태와 공유·preserve list)
CURRENT_SUBKEY = "current"           # blueprint 이미지 현재 projection sub-key
VIEW_URL_PREFIX = "/api/files/view/"

EVENT_SET = "BLUEPRINT_SET"
EVENT_REPLACED = "BLUEPRINT_REPLACED"
EVENT_DELETED = "BLUEPRINT_DELETED"

PROVENANCE_TICKET = "ticket"
PROVENANCE_BACKFILL = "migration_backfill"

STORAGE_DELETE = "STORAGE_DELETE"

__all__ = [
    "BlueprintBackfillResult",
    "BlueprintCoverageReport",
    "apply_blueprint_backfill",
    "classify_blueprint_scalar",
    "clear_current_blueprint",
    "derive_object_key",
    "get_current_blueprint",
    "remove_backfill_projection",
    "set_current_blueprint",
    "verify_blueprint_coverage",
]


# --------------------------------------------------------------------------- #
# read helpers
# --------------------------------------------------------------------------- #
def get_current_blueprint(order: Order) -> Optional[dict]:
    """``structured_data['blueprint']['current']`` projection 을 반환(없으면 None).

    Args:
        order: 대상 :class:`~models.Order`.

    Returns:
        현재 blueprint projection dict, 또는 미설정 시 ``None``.
    """
    sd = order.structured_data or {}
    bp = sd.get(BLUEPRINT_KEY)
    if not isinstance(bp, dict):
        return None
    cur = bp.get(CURRENT_SUBKEY)
    return cur if isinstance(cur, dict) else None


def _view_url(object_key: str) -> str:
    """object key → canonical view URL(build_file_view_url 와 동일 규칙, lazy import)."""
    from foms.api.files import build_file_view_url  # api 의존 최소화(런타임 import)

    return build_file_view_url(object_key)


def derive_object_key(view_url: Any, order_id: int) -> Optional[str]:
    """canonical ``/api/files/view/<key>`` URL 에서만 object_key 를 유도한다(exact-only).

    URL prefix 가 canonical 이고 그 key 가 대상 order 기준 :func:`validate_upload_key` 를
    통과할 때만 key 를 돌려준다. 외부/비정규 URL 은 **자동 추정하지 않고**(ambiguous
    auto-map 금지) ``None`` 을 돌려준다.

    Args:
        view_url: scalar 에 저장된 URL 원문.
        order_id: 대상 주문 id(key order segment 대조).

    Returns:
        유도된 canonical object key, 또는 ambiguous 이면 ``None``.
    """
    if not isinstance(view_url, str) or not view_url.startswith(VIEW_URL_PREFIX):
        return None
    key = view_url[len(VIEW_URL_PREFIX):]
    ok, _category, _err = validate_upload_key(key, order_id)
    return key if ok else None


# --------------------------------------------------------------------------- #
# projection write helpers (deepcopy + flag_modified)
# --------------------------------------------------------------------------- #
def _write_current(order: Order, current: Optional[dict]) -> None:
    """``structured_data['blueprint']['current']`` 을 설정/삭제하고 flag_modified 한다.

    다른 ``blueprint`` sub-key(고객 컨펌 등)는 보존한다. ``current=None`` 이면 sub-key 제거.
    """
    sd = copy.deepcopy(order.structured_data or {})
    bp = sd.get(BLUEPRINT_KEY)
    if not isinstance(bp, dict):
        bp = {}
    if current is None:
        bp.pop(CURRENT_SUBKEY, None)
    else:
        bp[CURRENT_SUBKEY] = current
    sd[BLUEPRINT_KEY] = bp
    order.structured_data = sd
    flag_modified(order, "structured_data")


def _new_event(
    session: Session, order_id: int, event_type: str, payload: dict,
    actor_user_id: Optional[int], now: datetime.datetime,
) -> OrderEvent:
    """OrderEvent 를 추가·flush 해 id 를 확보한다(STORAGE_DELETE FK source)."""
    event = OrderEvent(
        order_id=order_id, event_type=event_type, payload=payload,
        created_by_user_id=actor_user_id, created_at=now,
    )
    session.add(event)
    session.flush()
    return event


def _enqueue_storage_delete(
    session: Session, order_id: int, event_id: int, object_key: str
) -> None:
    """이전 blueprint R2 object 삭제를 STORAGE_DELETE outbox 로 예약한다(동기 삭제 금지)."""
    enqueue_side_effect(
        session, source_domain="ORDER_EVENT", source_id=event_id,
        effect_type=STORAGE_DELETE,
        payload={"object_key": object_key, "order_id": order_id},
        dedupe_key=f"blueprint:{order_id}:{object_key}",
    )


def _remove_attachment(
    session: Session, order_id: int, attachment_id: Optional[int], object_key: Optional[str]
) -> None:
    """교체/삭제된 blueprint 의 OrderAttachment row 를 제거한다(R2 blob 은 outbox 소관)."""
    q = session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id)
    if attachment_id is not None:
        q = q.filter(OrderAttachment.id == attachment_id)
    elif object_key:
        q = q.filter(OrderAttachment.storage_key == object_key)
    else:
        return
    for att in q.all():  # ORM delete(session-sync) — stale identity-map row 방지.
        session.delete(att)


# --------------------------------------------------------------------------- #
# mutations (호출자가 version bump·commit 소유)
# --------------------------------------------------------------------------- #
def set_current_blueprint(
    session: Session, order: Order, *, attachment: OrderAttachment,
    actor_user_id: Optional[int], now: Optional[datetime.datetime] = None,
) -> dict:
    """완료된 ticket 첨부를 현재 blueprint projection 으로 설정한다(교체 시 이전 정리).

    projection(structured_data)·파생 scalar 를 갱신하고 SET/REPLACED event 를 남긴다. 교체면
    이전 object 를 STORAGE_DELETE outbox 로 예약하고 이전 첨부 row 를 제거한다(동기 R2 삭제
    금지). **version bump 는 호출자(complete_ticket REV-00)가 소유** 하므로 여기서 bump 하지
    않는다 — scalar 갱신은 그 version tx 안에서 일어나는 파생 projection 이다.

    Args:
        session: business tx 세션(호출자 소유·commit 미수행).
        order: 대상 주문(호출자가 FOR UPDATE 로 잠갔다고 가정).
        attachment: complete_ticket 이 만든 :class:`~models.OrderAttachment`.
        actor_user_id: 저장 actor(event provenance).
        now: 기준 시각(테스트 주입).

    Returns:
        새 current projection dict.
    """
    now = now or now_utc_naive()
    prev = get_current_blueprint(order)
    prev_key = (prev or {}).get("object_key")
    replacing = bool(prev_key and prev_key != attachment.storage_key)

    view = _view_url(attachment.storage_key)
    current = {
        "attachment_id": attachment.id,
        "object_key": attachment.storage_key,
        "filename": attachment.filename,
        "view_url": view,
        "uploaded_at": now.isoformat(),
        "uploaded_by": actor_user_id,
        "provenance": PROVENANCE_TICKET,
    }
    _write_current(order, current)
    order.blueprint_image_url = view  # 파생 projection(version tx 내부·direct write 아님)

    event = _new_event(
        session, order.id, EVENT_REPLACED if replacing else EVENT_SET,
        {"object_key": attachment.storage_key, "attachment_id": attachment.id,
         "previous_object_key": prev_key}, actor_user_id, now,
    )
    if replacing:
        _enqueue_storage_delete(session, order.id, event.id, prev_key)
        _remove_attachment(session, order.id, (prev or {}).get("attachment_id"), prev_key)
    session.flush()
    return current


def clear_current_blueprint(
    session: Session, order: Order, *,
    actor_user_id: Optional[int], now: Optional[datetime.datetime] = None,
) -> Optional[dict]:
    """현재 blueprint projection 을 삭제하고 이전 object 를 STORAGE_DELETE outbox 로 예약한다.

    projection·scalar 를 비우고 DELETED event 를 남긴다. 이전 object 의 R2 blob 은 동기
    삭제하지 않고 outbox 로 예약한다. version bump 는 호출자(REV-00 mutation)가 소유한다.

    Args:
        session: business tx 세션(호출자 소유·commit 미수행).
        order: 대상 주문(호출자가 FOR UPDATE 로 잠갔다고 가정).
        actor_user_id: 삭제 actor(event provenance).
        now: 기준 시각(테스트 주입).

    Returns:
        제거된 이전 projection dict, 또는 처음부터 없었으면 ``None``.
    """
    now = now or now_utc_naive()
    prev = get_current_blueprint(order)
    if prev is None:
        return None
    _write_current(order, None)
    order.blueprint_image_url = None  # 파생 projection(version tx 내부·direct write 아님)

    obj = prev.get("object_key")
    event = _new_event(
        session, order.id, EVENT_DELETED,
        {"object_key": obj, "attachment_id": prev.get("attachment_id")},
        actor_user_id, now,
    )
    if obj:
        _enqueue_storage_delete(session, order.id, event.id, obj)
    _remove_attachment(session, order.id, prev.get("attachment_id"), obj)
    session.flush()
    return prev


# --------------------------------------------------------------------------- #
# legacy safe backfill (scalar → typed projection, 100% coverage)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BlueprintBackfillResult:
    """scalar → projection safe backfill 결과.

    Attributes:
        total: blueprint_image_url 이 비어있지 않은 order 수.
        exact: object_key 를 canonical 로 유도한(또는 유도될) order 수.
        ambiguous: object_key 를 자동 추정하지 않고 URL 만 보존한 order 수.
        projected: 이번 run 에서 새로 current projection 을 쓴(또는 쓸) order 수.
        already_present: 이미 current projection 이 있어 건드리지 않은 order 수.
        applied: True=실제 쓰기, False=dry-run(무쓰기).
    """

    total: int
    exact: int
    ambiguous: int
    projected: int
    already_present: int
    applied: bool


@dataclass(frozen=True)
class BlueprintCoverageReport:
    """coverage 검증 결과(exact + ambiguous-preserved = 100%).

    Attributes:
        total: scalar 를 가진 order 수.
        projected: current projection 을 가진 order 수.
        missing: scalar 는 있으나 projection 이 없는 order 수(0 이어야 완료).
        coverage_complete: ``missing == 0`` 이면 True.
    """

    total: int
    projected: int
    missing: int
    coverage_complete: bool


def classify_blueprint_scalar(order_id: int, url: str, now_iso: str) -> Tuple[str, dict]:
    """legacy scalar URL 을 exact/ambiguous 로 분류하고 projection dict 를 만든다.

    Args:
        order_id: 대상 주문 id.
        url: scalar 원문 URL(무손실로 ``view_url`` 에 보존).
        now_iso: backfill 시각 ISO 문자열.

    Returns:
        ``("exact"|"ambiguous", projection_dict)``. ambiguous 는 ``object_key=None`` +
        ``ambiguous=True`` 로 자동 매핑을 하지 않는다.
    """
    key = derive_object_key(url, order_id)
    current = {
        "attachment_id": None,
        "object_key": key,
        "filename": None,
        "view_url": url,
        "uploaded_at": now_iso,
        "uploaded_by": None,
        "provenance": PROVENANCE_BACKFILL,
    }
    if key is not None:
        return "exact", current
    current["ambiguous"] = True
    return "ambiguous", current


def _legacy_orders(session: Session) -> list[Order]:
    """blueprint_image_url 이 비어있지 않은 order 를 조회한다(backfill 대상)."""
    return (
        session.query(Order)
        .filter(Order.blueprint_image_url.isnot(None), Order.blueprint_image_url != "")
        .all()
    )


def apply_blueprint_backfill(
    session: Session, *, apply: bool = False, now: Optional[datetime.datetime] = None
) -> BlueprintBackfillResult:
    """legacy scalar 를 typed current projection 으로 무손실 backfill 한다(dry-run 기본·멱등).

    이미 ``current`` projection 이 있는 order 는 건드리지 않는다(멱등·resume). scalar 는
    수정하지 않는다(read 소비처 무회귀 — projection 병행). ambiguous URL 은 object_key 를
    자동 추정하지 않는다. 커밋은 호출자 몫.

    Args:
        session: DB 세션.
        apply: False(기본)=dry-run(무쓰기·계획만), True=실제 projection 쓰기.
        now: 기준 시각(테스트 주입).

    Returns:
        :class:`BlueprintBackfillResult`.
    """
    now = now or now_utc_naive()
    now_iso = now.isoformat()
    total = exact = ambiguous = projected = already = 0
    for order in _legacy_orders(session):
        total += 1
        if get_current_blueprint(order) is not None:
            already += 1
            continue
        kind, current = classify_blueprint_scalar(order.id, order.blueprint_image_url, now_iso)
        exact += kind == "exact"
        ambiguous += kind == "ambiguous"
        projected += 1
        if apply:
            _write_current(order, current)
    if apply:
        session.flush()
    return BlueprintBackfillResult(
        total=total, exact=exact, ambiguous=ambiguous,
        projected=projected, already_present=already, applied=apply,
    )


def verify_blueprint_coverage(session: Session) -> BlueprintCoverageReport:
    """scalar 를 가진 모든 order 가 current projection 을 갖는지(coverage 100%) 검증한다.

    Args:
        session: DB 세션.

    Returns:
        :class:`BlueprintCoverageReport` (``missing==0`` 이면 완료).
    """
    total = projected = 0
    for order in _legacy_orders(session):
        total += 1
        if get_current_blueprint(order) is not None:
            projected += 1
    missing = total - projected
    return BlueprintCoverageReport(
        total=total, projected=projected, missing=missing, coverage_complete=(missing == 0)
    )


def remove_backfill_projection(session: Session) -> int:
    """migration downgrade 용: provenance=migration_backfill 인 current projection 만 제거한다.

    ticket 으로 저장된 projection(provenance=ticket)이나 다른 blueprint sub-key 는 보존한다.
    scalar 는 backfill 이 건드리지 않았으므로 그대로 둔다.

    Args:
        session: DB 세션.

    Returns:
        제거한 projection 수.
    """
    removed = 0
    for order in _legacy_orders(session):
        cur = get_current_blueprint(order)
        if cur is not None and cur.get("provenance") == PROVENANCE_BACKFILL:
            _write_current(order, None)
            removed += 1
    session.flush()
    return removed
