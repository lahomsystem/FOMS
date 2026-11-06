"""주문 ↔ 프리랜서 계정 연결(``order_freelancer_links``) — 계산 · 맞추기 · 일괄 다시 맞추기(FCOMM-01 §4.4 · §5 · §6.1).

연결은 **투영**이다. 정본은 주문 ``structured_data`` 의 이름 칸과 프리랜서 설정의 맞출 이름(J8)이다.

- ``MANAGER_PRIMARY`` — 대표 담당(담당 명단 맨 앞)이 프리랜서의 맞출 이름.
- ``MANAGER`` — 대표가 아닌 다른 담당(``parties.manager.names``)이 맞출 이름.
- ``ORDERER`` — 발주사(``parties.orderer.name``)가 맞출 이름(개인영업).
- ``CREATOR`` — 켜진 프리랜서가 직접 등록한 주문. 이름과 무관하고, 한 번 생기면 지우지 않는다(자동 저장이
  서버가 채운 담당을 지워도 본인 주문이 사라지지 않게 — 검수 원장 A8).

이름은 :func:`~foms.services.sales_commission.names.normalize_name`(NFC + 앞뒤 공백) 뒤 **완전 일치**만 본다.
``User.name`` 은 쓰지 않는다(J8 — 프리랜서가 내 정보에서 이름을 바꿔 남의 주문을 가져가는 길을 막는다).

주문 저장 때 맞추는 일은 전역 훅(:mod:`foms.services.sales_commission.link_hook`)이 한다. 여기 있는
:func:`sync_links_for_orders` 는 되채우기 · 설정 저장 뒤 다시 맞추기용이다 — 알림을 내지 않는다(기본).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_order_flags import is_erp_draft_structured_data
from foms.services.orders.manager_names import order_manager_names
from foms.services.sales_commission.names import normalize_name
from foms.services.sales_commission.settings import active_freelancers
from foms.services.settlement_source import fetch_settlement_rows
from models import Order, OrderEvent, OrderFreelancerLink

REL_MANAGER_PRIMARY = "MANAGER_PRIMARY"
REL_MANAGER = "MANAGER"
REL_ORDERER = "ORDERER"
REL_CREATOR = "CREATOR"
RELATIONS: tuple[str, ...] = (REL_MANAGER_PRIMARY, REL_MANAGER, REL_ORDERER, REL_CREATOR)
#: 배정 알림(``SALES_ORDER_ASSIGNED``)을 내는 관계 — 담당으로 들어간 것.
MANAGER_RELATIONS = frozenset({REL_MANAGER_PRIMARY, REL_MANAGER})
#: 되채우기가 "만든 사람"으로 읽는 이벤트(설계서 §5).
CREATOR_EVENT_TYPES: tuple[str, ...] = ("ORDER_CREATED", "ORDER_DRAFT_CREATED")
#: 일괄 맞추기가 한 번에 읽는 주문 수.
DEFAULT_CHUNK_SIZE = 500
#: 이름 칸만 읽는 얇은 문서(PostgreSQL 16+ 은 SQL 이 줄여서 보낸다 — :mod:`foms.services.settlement_source`).
LINK_SD_SPEC: dict[str, Any] = {
    "parties": {"manager": {"name": None, "names": None}, "orderer": {"name": None}},
    "meta": {"draft": None},
}

LinkKey = tuple[int, str]

#: 켜진 프리랜서 표 캐시 — 요청 밖은 ``session.info``(트랜잭션마다 비운다), 요청 안은 flask ``g``(요청 한 번에 한 번).
SNAPSHOT_INFO_KEY = "foms_fcomm_link_snapshot"
_G_SNAPSHOT_ATTR = "_fcomm_link_snapshot"
#: 배정 알림 후보(저장 훅 · 일괄 맞추기 → 커밋 때 :mod:`~foms.services.sales_commission.link_hook` 이 만든다).
PENDING_INFO_KEY = "foms_fcomm_assign_pending"


@dataclass(frozen=True)
class LinkSnapshot:
    """켜진 프리랜서 — ``match_map`` = ``{정리한 맞출 이름: user_id}``, ``start_months`` = ``{user_id: 'YYYY-MM'}``."""

    match_map: Mapping[str, int]
    start_months: Mapping[int, str]

    @property
    def active_ids(self) -> frozenset[int]:
        return frozenset(self.start_months)


def load_link_snapshot(db) -> LinkSnapshot:
    """설정 한 줄을 읽어 켜진 프리랜서 표를 만든다(쿼리 1번)."""
    configs = active_freelancers(db)
    match_map = {c.match_name: uid for uid, c in configs.items() if c.match_name}
    return LinkSnapshot(match_map=match_map, start_months={uid: c.start_month for uid, c in configs.items()})


def request_g() -> Any:
    """요청 안이면 flask ``g``, 밖이면 None."""
    try:
        from flask import g, has_request_context
    except ImportError:  # pragma: no cover — flask 는 늘 있다
        return None
    return g if has_request_context() else None


def cached_snapshot(session: Any) -> LinkSnapshot:
    """켜진 프리랜서 표 — 요청이면 ``g``, 아니면 트랜잭션의 ``session.info`` 에 한 번만 읽어 둔다."""
    g = request_g()
    cached = getattr(g, _G_SNAPSHOT_ATTR, None) if g is not None else session.info.get(SNAPSHOT_INFO_KEY)
    if cached is None:
        with session.no_autoflush:
            cached = load_link_snapshot(session)
        if g is not None:
            setattr(g, _G_SNAPSHOT_ATTR, cached)
        else:
            session.info[SNAPSHOT_INFO_KEY] = cached
    return cached


def clear_snapshot_cache(session: Any = None) -> None:
    """캐시를 비운다(설정을 바꾼 바로 그 요청 · 트랜잭션이 옛 표를 쓰지 않게)."""
    if session is not None:
        session.info.pop(SNAPSHOT_INFO_KEY, None)
    g = request_g()
    if g is not None and hasattr(g, _G_SNAPSHOT_ATTR):
        delattr(g, _G_SNAPSHOT_ATTR)


def queue_assignment(session: Any, order: Any, user_ids: Iterable[int], actor_user_id: Optional[int] = None) -> None:
    """배정 알림 후보를 모은다(커밋 때 만든다). ``order`` 는 ``Order`` 객체(id 없어도 됨) 또는 주문 id.

    저장한 본인(``actor_user_id``)에게는 알리지 않는다.
    """
    bucket = session.info.setdefault(PENDING_INFO_KEY, [])
    for uid in user_ids:
        if actor_user_id is not None and int(uid) == int(actor_user_id):
            continue
        bucket.append({"order": order, "user_id": int(uid), "actor": actor_user_id})


# --------------------------------------------------------------------------
# 계산(순수 함수)
# --------------------------------------------------------------------------
def _normalized_map(match_map: Mapping[str, Any] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw_name, raw_uid in (match_map or {}).items():
        name = normalize_name(raw_name)
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            continue
        if name:
            out[name] = uid
    return out


def _orderer_name(sd: Any) -> str:
    parties = sd.get("parties") if isinstance(sd, dict) else None
    orderer = parties.get("orderer") if isinstance(parties, dict) else None
    return normalize_name(orderer.get("name")) if isinstance(orderer, dict) else ""


def desired_links(sd: Any, match_map: Mapping[str, Any] | None, creator_user_id: Any = None) -> set[LinkKey]:
    """주문 하나가 가져야 할 연결 ``{(user_id, relation)}``.

    Args:
        sd: 주문 ``structured_data``(None · 비 dict 허용). 담당 명단은 :func:`order_manager_names` 규칙으로 읽는다
            (대표가 맨 앞, 옛 한 칸 여러 이름 꼴도 나눈다).
        match_map: 켜진 프리랜서의 ``{맞출 이름: user_id}``. 열쇠는 여기서 다시 정리한다.
        creator_user_id: 이 주문을 등록한 사람. 켜진 프리랜서(= ``match_map`` 값)일 때만 ``CREATOR``.

    Returns:
        연결 집합. 같은 사람이 대표이면서 명단에 또 있으면 ``MANAGER_PRIMARY`` 하나만.
    """
    names = _normalized_map(match_map)
    out: set[LinkKey] = set()
    if not names:
        return out
    managed: set[int] = set()
    for idx, raw in enumerate(order_manager_names(sd)):
        uid = names.get(normalize_name(raw))
        if uid is None or uid in managed:
            continue
        managed.add(uid)
        out.add((uid, REL_MANAGER_PRIMARY if idx == 0 else REL_MANAGER))
    orderer = _orderer_name(sd)
    if orderer and orderer in names:
        out.add((names[orderer], REL_ORDERER))
    try:
        creator = int(creator_user_id) if creator_user_id is not None else None
    except (TypeError, ValueError):
        creator = None
    if creator is not None and creator in set(names.values()):
        out.add((creator, REL_CREATOR))
    return out


def manager_user_ids(keys: Iterable[LinkKey]) -> set[int]:
    """연결 중 담당 관계(대표 · 다른 담당)인 사람 id."""
    return {uid for uid, rel in keys if rel in MANAGER_RELATIONS}


# --------------------------------------------------------------------------
# 맞추기(세션에 더하고 지우기 — 커밋은 부르는 쪽)
# --------------------------------------------------------------------------
def existing_links_by_order(db, order_ids: Iterable[int], user_ids: Optional[Iterable[int]] = None
                            ) -> dict[int, list[OrderFreelancerLink]]:
    """주문들의 지금 연결 줄(쿼리 1번). ``user_ids`` 를 주면 그 사람 줄만."""
    ids = sorted({int(i) for i in order_ids if i is not None})
    if not ids:
        return {}
    query = db.query(OrderFreelancerLink).filter(OrderFreelancerLink.order_id.in_(ids))
    if user_ids is not None:
        query = query.filter(OrderFreelancerLink.user_id.in_(sorted({int(u) for u in user_ids})))
    out: dict[int, list[OrderFreelancerLink]] = {}
    for row in query.all():
        out.setdefault(int(row.order_id), []).append(row)
    return out


def apply_link_diff(db, order: Any, desired: set[LinkKey], current: Iterable[OrderFreelancerLink],
                    *, dry_run: bool = False) -> tuple[set[LinkKey], set[LinkKey]]:
    """지금 줄을 ``desired`` 로 맞춘다 → ``(더한 것, 지운 것)``. ``CREATOR`` 줄은 지우지 않는다.

    Args:
        db: 세션.
        order: ``Order`` 객체(새 주문이면 id 가 아직 없다 — 관계로 붙여 flush 가 채운다) 또는 주문 id.
        desired: 가져야 할 연결.
        current: 지금 DB 에 있는 이 주문의 연결 줄.
        dry_run: True 면 세지만 바꾸지 않는다.
    """
    rows = list(current)
    current_keys = {(int(r.user_id), str(r.relation)) for r in rows}
    removed: set[LinkKey] = set()
    for row in rows:
        key = (int(row.user_id), str(row.relation))
        if key[1] != REL_CREATOR and key not in desired:
            removed.add(key)
            if not dry_run:
                db.delete(row)
    added = set(desired) - current_keys
    if not dry_run:
        for uid, rel in sorted(added):
            if isinstance(order, int):
                db.add(OrderFreelancerLink(order_id=order, user_id=uid, relation=rel))
            else:
                db.add(OrderFreelancerLink(order=order, user_id=uid, relation=rel))
    return added, removed


# --------------------------------------------------------------------------
# 일괄 다시 맞추기(되채우기 · 설정 저장 뒤)
# --------------------------------------------------------------------------
def _in_start_month(created_at: Any, start_month: str) -> bool:
    month = format_datetime_kst(created_at, "%Y-%m") if created_at is not None else None
    return bool(month) and bool(start_month) and month >= start_month


def creator_links(db, order_ids: list[int], snapshot: LinkSnapshot) -> dict[int, set[LinkKey]]:
    """되채우기용 ``CREATOR`` — 주문 생성 이벤트(:data:`CREATOR_EVENT_TYPES`) 작성자가 켜진 프리랜서이고, 그 일이
    그 사람의 시작 달 이후일 때만(회사 직원일 때 등록한 옛 주문은 넣지 않는다). 쿼리 1번.

    마법사 초안 표(``order_drafts``)는 근거로 쓰지 않는다(T18 R9) — 그 표의 ``order_id`` 는 클라이언트가 초안 저장
    본문으로 넣는 값이라, 근거로 삼으면 남의 주문 번호를 적어 넣는 것만으로 되채우기가 그 주문을 내 것으로 묶는다.
    마법사 등록은 ``create_order`` 가 ``ORDER_CREATED`` 를 남기므로 이벤트만으로 빠지는 주문이 없다."""
    starts = snapshot.start_months
    if not order_ids or not starts:
        return {}
    out: dict[int, set[LinkKey]] = {}
    events = (db.query(OrderEvent.order_id, OrderEvent.created_by_user_id, OrderEvent.created_at)
              .filter(OrderEvent.order_id.in_(order_ids), OrderEvent.event_type.in_(CREATOR_EVENT_TYPES),
                      OrderEvent.created_by_user_id.in_(sorted(starts))).all())
    for order_id, uid, created_at in events:
        if order_id is None or uid is None or not _in_start_month(created_at, starts.get(int(uid), "")):
            continue
        out.setdefault(int(order_id), set()).add((int(uid), REL_CREATOR))
    return out


def _target_order_ids(db, order_ids: Optional[Iterable[int]], user_ids: Optional[set[int]]) -> list[int]:
    if order_ids is not None:
        return sorted({int(i) for i in order_ids})
    ids = {int(i) for (i,) in db.query(Order.id).filter(Order.is_erp_order.is_(True)).all()}
    linked = db.query(OrderFreelancerLink.order_id).distinct()
    if user_ids is not None:
        linked = linked.filter(OrderFreelancerLink.user_id.in_(sorted(user_ids)))
    ids.update(int(i) for (i,) in linked.all())  # ERP 가 아니게 된 주문의 낡은 줄도 지운다
    return sorted(ids)


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), max(1, size)):
        yield values[start:start + max(1, size)]


def sync_links_for_orders(db, order_ids: Optional[Iterable[int]] = None, *, notify: bool = False,
                          user_ids: Optional[Iterable[int]] = None, dry_run: bool = False,
                          commit: bool = False, chunk_size: int = DEFAULT_CHUNK_SIZE) -> dict[str, int]:
    """주문들의 연결을 지금 설정 기준으로 다시 맞춘다 → ``{"orders", "added", "removed", "freelancers"}``(숫자만).

    Args:
        db: 세션. 주문마다 쿼리를 내지 않는다 — 덩어리(``chunk_size``)마다 이름 칸 · 지금 줄 · 만든 사람을 한 번씩 읽는다.
        order_ids: 대상 주문. None 이면 ERP 주문 전부 + 연결 줄이 있는 주문.
        notify: True 면 새로 담당이 된 사람에게 배정 알림을 커밋 때 만든다(초안 제외). 되채우기 · 설정 저장은 False.
        user_ids: 주면 그 사람의 줄만 맞춘다(설정 저장 뒤 — 다른 프리랜서 줄은 건드리지 않는다).
        dry_run: True 면 세기만 한다(쓰기 0).
        commit: True 면 덩어리마다 커밋(되채우기 스크립트). False 면 flush 만 — 커밋은 부르는 쪽.
        chunk_size: 덩어리 크기.
    """
    snapshot = load_link_snapshot(db)
    clear_snapshot_cache(db)
    scope = {int(u) for u in user_ids} if user_ids is not None else None
    stats = {"orders": 0, "added": 0, "removed": 0, "freelancers": len(snapshot.active_ids)}
    targets = _target_order_ids(db, order_ids, scope)
    for chunk in _chunks(targets, chunk_size):
        rows = fetch_settlement_rows(db, (Order.id, Order.is_erp_order, Order.status, Order.deleted_at),
                                     (Order.id.in_(chunk),), LINK_SD_SPEC)
        existing = existing_links_by_order(db, chunk, scope)
        creators = creator_links(db, chunk, snapshot)
        for row in rows:
            oid = int(row.id)
            desired = desired_links(row.structured_data, snapshot.match_map) if row.is_erp_order else set()
            desired |= creators.get(oid, set())
            if scope is not None:
                desired = {key for key in desired if key[0] in scope}
            current = existing.get(oid, [])
            added, removed = apply_link_diff(db, oid, desired, current, dry_run=dry_run)
            stats["orders"] += 1
            stats["added"] += len(added)
            stats["removed"] += len(removed)
            if notify and not dry_run and _notifiable_row(row):
                newly = manager_user_ids(added) - manager_user_ids((int(r.user_id), r.relation) for r in current)
                queue_assignment(db, oid, newly)
        if dry_run:
            continue
        if commit:
            db.commit()
        else:
            db.flush()
    return stats


def _notifiable_row(row: Any) -> bool:
    if not row.is_erp_order or row.deleted_at or str(row.status or "").upper() in ("DRAFT", "DELETED"):
        return False
    return not is_erp_draft_structured_data(row.structured_data)


def resync_freelancer_links(db, user_id: int) -> dict[str, int]:
    """프리랜서 설정 저장(추가 · 켜기 · 끄기 · 맞출 이름 바꿈) 뒤 그 사람의 연결만 다시 맞춘다. 알림 없음 · 커밋은 부르는 쪽."""
    return sync_links_for_orders(db, user_ids=[int(user_id)], notify=False)


__all__ = [
    "CREATOR_EVENT_TYPES",
    "LINK_SD_SPEC",
    "MANAGER_RELATIONS",
    "RELATIONS",
    "REL_CREATOR",
    "REL_MANAGER",
    "REL_MANAGER_PRIMARY",
    "REL_ORDERER",
    "LinkSnapshot",
    "apply_link_diff",
    "cached_snapshot",
    "clear_snapshot_cache",
    "creator_links",
    "desired_links",
    "existing_links_by_order",
    "load_link_snapshot",
    "manager_user_ids",
    "queue_assignment",
    "request_g",
    "resync_freelancer_links",
    "sync_links_for_orders",
]
