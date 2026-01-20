import os
import sys
import json

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
        oid = db.execute(text("SELECT id FROM orders ORDER BY id DESC LIMIT 1")).fetchone()
        if not oid:
            raise RuntimeError("orders 데이터가 없습니다.")
        order_id = int(oid.id)

    # create task
    r1 = client.post(
        f"/api/orders/{order_id}/tasks",
        data=json.dumps({"title": "테스트 Task", "owner_team": "DRAWING", "status": "OPEN"}),
        content_type="application/json",
    )
    assert r1.status_code == 200, r1.data
    j1 = r1.get_json()
    assert j1.get("success") is True
    task_id = j1.get("task_id")
    print("created task_id:", task_id)

    # list tasks
    r2 = client.get(f"/api/orders/{order_id}/tasks")
    assert r2.status_code == 200
    j2 = r2.get_json()
    assert j2.get("success") is True
    assert any(t["id"] == task_id for t in j2.get("tasks", []))

    # update status
    r3 = client.put(
        f"/api/orders/{order_id}/tasks/{task_id}",
        data=json.dumps({"status": "DONE"}),
        content_type="application/json",
    )
    assert r3.status_code == 200
    assert r3.get_json().get("success") is True

    # events list
    r4 = client.get(f"/api/orders/{order_id}/events?limit=5")
    assert r4.status_code == 200
    assert r4.get_json().get("success") is True

    # delete
    r5 = client.delete(f"/api/orders/{order_id}/tasks/{task_id}")
    assert r5.status_code == 200
    assert r5.get_json().get("success") is True

    print("[OK] tasks/events API smoke test passed")


if __name__ == "__main__":
    main()

