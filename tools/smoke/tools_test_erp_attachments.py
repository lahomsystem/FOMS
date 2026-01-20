from io import BytesIO

import os
import sys

# 스크립트 위치와 무관하게 프로젝트 루트 import 보장
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db import init_db, engine
from sqlalchemy import text

from app import app


def main():
    with app.app_context():
        init_db()

        with engine.begin() as conn:
            user = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).fetchone()
            order = conn.execute(text("SELECT id FROM orders ORDER BY id DESC LIMIT 1")).fetchone()

        if not user or not order:
            raise RuntimeError("테스트를 위한 users/orders 데이터가 없습니다.")

        user_id = int(user.id)
        order_id = int(order.id)
        print("user_id:", user_id, "order_id:", order_id)

        # 업로드할 샘플 파일(프로젝트에 있는 도면 png 재사용)
        sample_path = os.path.join("static", "uploads", "orders", "1806", "blueprint", "20260116_164646_2.png")
        if not os.path.exists(sample_path):
            raise RuntimeError(f"샘플 파일이 없습니다: {sample_path}")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        with open(sample_path, "rb") as f:
            data = {
                "file": (BytesIO(f.read()), "sample.png"),
            }
        res = client.post(f"/api/orders/{order_id}/attachments", data=data, content_type="multipart/form-data")
        print("upload status:", res.status_code)
        payload = res.get_json()
        print("upload json success:", payload.get("success"))
        if not payload.get("success"):
            raise RuntimeError(payload)

        att = payload["attachment"]
        assert att["view_url"].startswith("/api/files/view/"), att["view_url"]
        assert att["download_url"].startswith("/api/files/download/"), att["download_url"]

        # 리스트 조회
        res2 = client.get(f"/api/orders/{order_id}/attachments")
        print("list status:", res2.status_code)
        payload2 = res2.get_json()
        assert payload2.get("success") is True
        assert isinstance(payload2.get("attachments"), list)

        # view 엔드포인트 실제 동작(로컬은 200, R2면 302 redirect)
        view_url = att["view_url"]
        res3 = client.get(view_url, follow_redirects=False)
        print("view status:", res3.status_code)
        assert res3.status_code in (200, 302)

        print("[OK] ERP attachments upload/list/view smoke test passed")


if __name__ == "__main__":
    main()

