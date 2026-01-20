import os
import sys
import json
import datetime

# 스크립트 위치와 무관하게 프로젝트 루트 import 보장
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app
from db import get_db
from sqlalchemy import text


def main():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "ADMIN"

    with app.app_context():
        db = get_db()
        row = db.execute(text("SELECT id FROM orders ORDER BY id DESC LIMIT 1")).fetchone()
        if not row:
            raise RuntimeError("orders 데이터가 없습니다.")
        order_id = int(row.id)

    # structured get
    r1 = client.get(f"/api/orders/{order_id}/structured")
    assert r1.status_code == 200
    sd = (r1.get_json() or {}).get("structured_data") or {}

    # trigger: urgent + drawing stage + dates
    today = datetime.date.today()
    meas_date = (today + datetime.timedelta(days=7)).isoformat()
    cons_date = (today + datetime.timedelta(days=10)).isoformat()

    sd.setdefault("flags", {})
    sd["flags"]["urgent"] = True
    sd["flags"]["urgent_reason"] = "스모크 테스트"

    sd.setdefault("workflow", {})
    sd["workflow"]["stage"] = "DRAWING"
    sd["workflow"]["stage_updated_at"] = datetime.datetime.now().isoformat()

    sd.setdefault("assignments", {})
    sd["assignments"]["owner_team"] = "DRAWING"

    sd.setdefault("schedule", {})
    sd["schedule"].setdefault("measurement", {})
    sd["schedule"]["measurement"]["date"] = meas_date
    sd["schedule"].setdefault("construction", {})
    sd["schedule"]["construction"]["date"] = cons_date

    r2 = client.put(
        f"/api/orders/{order_id}/structured",
        data=json.dumps({"structured_data": sd, "structured_schema_version": 1}),
        content_type="application/json",
    )
    assert r2.status_code == 200, r2.data
    assert r2.get_json().get("success") is True

    with app.app_context():
        db = get_db()
        rows = db.execute(
            text("""
                SELECT meta->>'auto_key' AS k, title, owner_team, due_date
                FROM order_tasks
                WHERE order_id=:oid
                  AND status IN ('OPEN','IN_PROGRESS')
                  AND meta ? 'auto_key'
                ORDER BY id DESC
            """),
            {"oid": order_id},
        ).fetchall()
        keys = set([r.k for r in rows if r.k])
        print("auto keys:", keys)
        assert "AUTO_URGENT" in keys
        assert "AUTO_BLUEPRINT_48H" in keys

    print("[OK] auto tasks smoke test passed")


if __name__ == "__main__":
    main()

