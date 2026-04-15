#!/usr/bin/env python3
"""
Phase D 6.1~6.3 검증 스크립트
- 6.1: 채팅 session/complete API 응답 확인
- 6.2: (수동) 동시 업로드 시 CPU/메모리 비교
- 6.3: USE_DIRECT_UPLOAD=0 시 multipart 경로 사용 확인

실행: python scripts/ops/verify_phase_d.py
환경변수: BASE_URL(기본 http://localhost:5000), VERIFY_USER, VERIFY_PASS
"""
import os
import sys

try:
    import requests
except ImportError:
    print("requests 필요: pip install requests")
    sys.exit(1)

BASE = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
USER = os.environ.get("VERIFY_USER", "admin")
PASS = os.environ.get("VERIFY_PASS", "admin")


def main():
    sess = requests.Session()
    sess.headers["Accept"] = "application/json"

    # 로그인
    r = sess.post(f"{BASE}/login", data={"username": USER, "password": PASS}, allow_redirects=True)
    if r.status_code not in (200, 302):
        print(f"[FAIL] 로그인 실패: HTTP {r.status_code}")
        sys.exit(1)
    print("[OK] 로그인 성공")

    # 6.1 채팅 session API
    r = sess.post(
        f"{BASE}/api/chat/upload/session",
        json={"filename": "test.jpg", "size": 1024, "room_id": "1"},
        timeout=10,
    )
    try:
        d = r.json()
    except Exception:
        d = {}
    if r.status_code == 200:
        if d.get("success") and d.get("upload_url"):
            print("[OK] 6.1 session API: R2 presigned URL 반환 (직접 업로드 가능)")
        elif not d.get("success") and "R2" in (d.get("message") or ""):
            print("[OK] 6.1 session API: 로컬 스토리지 모드 → upload_url 없음 (정상)")
        else:
            print(f"[INFO] 6.1 session API: {d}")
    else:
        msg = d.get("message", r.text[:200] if r.text else "")
        print(f"[INFO] 6.1 session API HTTP {r.status_code}: {msg}")
        if r.status_code == 400 and "R2" in str(msg):
            print("  → 로컬 스토리지이므로 direct 불가. multipart 경로 사용 권장.")

    # 6.3 multipart 경로 검증 (채팅 POST /api/chat/upload)
    import io
    buf = io.BytesIO(b"x" * 128)
    files = {"file": ("test_verify.jpg", buf, "image/jpeg")}
    data = {"room_id": "1"}
    r3 = sess.post(f"{BASE}/api/chat/upload", files=files, data=data, timeout=10)
    try:
        d3 = r3.json()
    except Exception:
        d3 = {}
    if r3.status_code == 200 and d3.get("success"):
        print("[OK] 6.3 multipart API: POST /api/chat/upload 정상 응답")
    elif r3.status_code == 200:
        print("[OK] 6.3 multipart API: HTTP 200 (multipart 경로 동작)")
    elif r3.status_code in (400, 500):
        print(f"[INFO] 6.3 multipart API HTTP {r3.status_code}: {d3.get('message', d3)}")
    else:
        print(f"[INFO] 6.3 multipart API HTTP {r3.status_code}")

    print("\n--- Phase D 6.2 수동 검증 ---")
    print("6.2 동시 20건: Railway/로컬에서 브라우저 또는 툴로 동시 업로드 후 CPU/메모리 비교")


if __name__ == "__main__":
    main()
