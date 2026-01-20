"""
환경변수에 설정된 DB URL을 '비번 마스킹'해서 출력.
레포에는 비밀번호/URL이 저장되지 않는 경우가 많아서,
운영 환경(Railway 등)에서 확인용으로 사용한다.
"""

import os
from urllib.parse import urlparse


def redact(url: str) -> str:
    if not url:
        return ""
    try:
        u = urlparse(url)
        if not u.scheme or not u.hostname:
            return "(unparseable)"
        user = u.username or ""
        host = u.hostname or ""
        port = f":{u.port}" if u.port else ""
        db = (u.path or "").lstrip("/")
        # password는 절대 출력하지 않음
        auth = f"{user}:***@" if user else ""
        return f"{u.scheme}://{auth}{host}{port}/{db}"
    except Exception:
        return "(unparseable)"


def main():
    keys = ["DATABASE_URL", "WD_CALCULATOR_DATABASE_URL", "WD_SRC_DATABASE_URL"]
    for k in keys:
        v = os.getenv(k) or ""
        print(f"{k} set:", bool(v))
        if v:
            print("  ", redact(v))


if __name__ == "__main__":
    main()

