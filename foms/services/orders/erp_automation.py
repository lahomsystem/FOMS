"""ERP Automation (DB 반영) 모듈 (TASK-01).

정책(erp_policy)에서 계산한 :class:`AutoTaskSpec` 을 :class:`~models.OrderTask` 로
**typed ORM upsert** 한다(raw SQL 0). 자동 task 는 **caller 트랜잭션**에서만 쓰고
내부 commit 하지 않으며(:func:`apply_auto_tasks` 는 주문 저장 tx 안에서 호출된다),
활성(OPEN/IN_PROGRESS) ``(order_id, auto_key)`` 조합의 **중복을 만들지 않는다**(TASK-BACKFILL
auto_key 불변식). 기존 활성 task 가 있으면 owner_team/due_date/meta 를 갱신하고, 없으면
새 identity(task_uuid·version=1·provenance='AUTO')로 삽입한다.

Flask app import 없이 step runner 에서도 재사용 가능하다.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from models import OrderTask
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_policy import build_auto_tasks

#: 자동 upsert dedup 대상 status(auto_key 불변식은 활성 task 만 본다 — audit 과 동일).
_ACTIVE_STATUSES = ("OPEN", "IN_PROGRESS")


def _meta_auto_key(meta: Any) -> Optional[str]:
    """``meta['auto_key']`` 를 비어있지 않은 문자열로 반환(없으면 None)."""
    if not isinstance(meta, dict):
        return None
    raw = meta.get("auto_key")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _active_auto_tasks_by_key(db, order_id: int) -> Dict[str, OrderTask]:
    """주문의 활성 auto task 를 ``auto_key -> OrderTask`` 로 색인한다(typed ORM, 배치 1쿼리).

    같은 key 가 여럿이면(backfill 이 quarantine 한 legacy collision) id 가 가장 작은
    것만 대표로 잡아 upsert 대상을 결정적으로 만든다(auto_key 중복 0 유지).
    """
    rows = (
        db.query(OrderTask)
        .filter(OrderTask.order_id == order_id, OrderTask.status.in_(_ACTIVE_STATUSES))
        .order_by(OrderTask.id.asc())
        .all()
    )
    by_key: Dict[str, OrderTask] = {}
    for task in rows:
        key = _meta_auto_key(task.meta)
        if key and key not in by_key:
            by_key[key] = task
    return by_key


def ensure_auto_task(
    db,
    order_id: int,
    auto_key: str,
    title: str,
    owner_team: Optional[str],
    due_date: Optional[str],
    meta: Optional[Dict[str, Any]],
):
    """활성 (order_id, auto_key) task 를 typed ORM 으로 upsert 한다(caller tx·중복 0).

    Args:
        db: SQLAlchemy 세션(호출자 소유 — 내부 commit 하지 않는다).
        order_id: 부모 주문 id.
        auto_key: 자동 task 식별 key(``meta['auto_key']`` 로 저장).
        title: 신규 삽입 시 제목.
        owner_team/due_date/meta: upsert 값(기존 갱신은 non-null 만 반영).

    Returns:
        갱신된 기존 task id, 또는 신규 삽입이면 None.
    """
    existing = _active_auto_tasks_by_key(db, order_id).get(auto_key)

    meta_obj = dict(meta) if isinstance(meta, dict) else {}
    meta_obj.setdefault("auto_key", auto_key)

    if existing is not None:
        if owner_team is not None:
            existing.owner_team = owner_team
        if due_date is not None:
            existing.due_date = due_date
        existing.meta = meta_obj
        flag_modified(existing, "meta")
        existing.updated_at = now_utc_naive()
        return existing.id

    now = now_utc_naive()
    task = OrderTask(
        order_id=order_id,
        title=title,
        status="OPEN",
        owner_team=owner_team,
        owner_user_id=None,
        due_date=due_date,
        meta=meta_obj,
        task_uuid=str(uuid.uuid4()),
        version=1,
        provenance="AUTO",
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    return None


def apply_auto_tasks(db, order_id: int, structured_data: Dict[str, Any], now: Optional[datetime.datetime] = None):
    """structured_data 기반 자동 task spec 을 부모 주문에 typed upsert 한다(caller tx)."""
    specs: List[Any] = build_auto_tasks(structured_data or {}, now=now)
    for spec in specs:
        ensure_auto_task(
            db=db,
            order_id=order_id,
            auto_key=spec.auto_key,
            title=spec.title,
            owner_team=spec.owner_team,
            due_date=spec.due_date,
            meta=spec.meta,
        )


__all__ = ["apply_auto_tasks", "build_auto_tasks", "ensure_auto_task"]
