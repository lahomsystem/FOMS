"""
ERP Automation (DB 반영) 모듈

- 정책(erp_policy)에서 계산한 AutoTaskSpec을 DB에 upsert하는 역할
- Flask app import 없이 step runner에서도 재사용 가능
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from models import OrderTask
from services.erp_policy import build_auto_tasks


def ensure_auto_task(
    db,
    order_id: int,
    auto_key: str,
    title: str,
    owner_team: Optional[str],
    due_date: Optional[str],
    meta: Optional[Dict[str, Any]],
):
    row = db.execute(text("""
        SELECT id FROM order_tasks
        WHERE order_id=:oid
          AND status IN ('OPEN','IN_PROGRESS')
          AND (meta->>'auto_key') = :k
        LIMIT 1
    """), {"oid": order_id, "k": auto_key}).fetchone()

    meta_obj = meta if isinstance(meta, dict) else {"auto_key": auto_key}
    meta_obj.setdefault("auto_key", auto_key)
    meta_json = json.dumps(meta_obj, ensure_ascii=False)

    if row:
        db.execute(text("""
            UPDATE order_tasks
            SET owner_team = COALESCE(:owner_team, owner_team),
                due_date = COALESCE(:due_date, due_date),
                updated_at = NOW(),
                meta = COALESCE(CAST(:meta AS JSONB), meta)
            WHERE id = :id
        """), {
            "id": int(row.id),
            "owner_team": owner_team,
            "due_date": due_date,
            "meta": meta_json,
        })
        return int(row.id)

    t = OrderTask(
        order_id=order_id,
        title=title,
        status="OPEN",
        owner_team=owner_team,
        owner_user_id=None,
        due_date=due_date,
        meta=meta_obj,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
    )
    db.add(t)
    return None


def apply_auto_tasks(db, order_id: int, structured_data: Dict[str, Any], now: Optional[datetime.datetime] = None):
    specs = build_auto_tasks(structured_data or {}, now=now)
    for s in specs:
        ensure_auto_task(
            db=db,
            order_id=order_id,
            auto_key=s.auto_key,
            title=s.title,
            owner_team=s.owner_team,
            due_date=s.due_date,
            meta=s.meta,
        )

