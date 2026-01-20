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

    # 현재 structured 조회
    r1 = client.get(f"/api/orders/{order_id}/structured")
    assert r1.status_code == 200
    sd = (r1.get_json() or {}).get("structured_data") or {}

    # stage 변경 저장(이벤트 생성 기대)
    sd.setdefault("workflow", {})
    sd["workflow"]["stage"] = "DRAWING"
    sd.setdefault("flags", {})
    sd["flags"]["urgent"] = True
    sd["flags"]["urgent_reason"] = "테스트"

    r2 = client.put(
        f"/api/orders/{order_id}/structured",
        data=json.dumps({"structured_data": sd, "structured_schema_version": 1, "structured_confidence": None}),
        content_type="application/json",
    )
    print("PUT status:", r2.status_code, r2.get_json())
    assert r2.status_code == 200

    with app.app_context():
        db = get_db()
        rows = db.execute(
            text("SELECT event_type, payload FROM order_events WHERE order_id=:oid ORDER BY id DESC LIMIT 5"),
            {"oid": order_id},
        ).fetchall()
        print("events:", rows)
        assert any(r.event_type == "STAGE_CHANGED" for r in rows)
        assert any(r.event_type == "URGENT_CHANGED" for r in rows)

    print("[OK] structured save -> events smoke test passed")


if __name__ == "__main__":
    main()

