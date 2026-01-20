import os
import sys

# 스크립트 위치와 무관하게 프로젝트 루트 import 보장
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app

client = app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = 1

res = client.get("/erp/dashboard")
print("status:", res.status_code)
print(res.data[:200])

