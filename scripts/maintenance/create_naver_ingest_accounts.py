"""네이버 수집용 시스템 계정 2개 생성/점검 CLI (NAVER-INGEST-01 T0).

정책·보정 로직은 :mod:`foms.services.integrations.naver_commerce.accounts` 가 갖는다
(앱 부팅 없이도 쓸 수 있어야 해서 서비스 쪽에 뒀다). 이 파일은 인자 파싱과 출력만 한다.

만드는 계정:

* ``naver_ingest_bot`` (MANAGER) — 이벤트 author·``assigned_by``.
* ``naver_unassigned`` (STAFF/SALES/active) — 미배정 보류함 owner.

둘 다 아무도 모르는 난수 비밀번호로 잠근다(``is_active=False`` 로는 잠글 수 없다 —
owner 계약이 활성 SALES 를 요구한다).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/create_naver_ingest_accounts.py --dry-run
    python scripts/maintenance/create_naver_ingest_accounts.py --json
"""
import argparse
import json
import os
import sys

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.integrations.naver_commerce.accounts import (  # noqa: E402
    ensure_ingest_accounts,
)


def run() -> int:
    parser = argparse.ArgumentParser(description="Create/repair Naver ingest system accounts.")
    parser.add_argument("--dry-run", action="store_true", help="변경을 커밋하지 않고 계획만 출력.")
    parser.add_argument("--reset-password", action="store_true",
                        help="기존 계정의 비밀번호도 난수로 재잠금.")
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력.")
    args = parser.parse_args()

    with app.app_context():
        db = get_db()
        try:
            results = ensure_ingest_accounts(db, reset_password=args.reset_password)
            db.rollback() if args.dry_run else db.commit()
        except Exception:
            db.rollback()
            raise

    payload = {"dry_run": bool(args.dry_run), "accounts": results}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    else:
        for row in results:
            extra = f" ({', '.join(row['fixed'])})" if row.get("fixed") else ""
            print(f"[{row['action']}] {row['username']} id={row['id']}{extra}", flush=True)
        if args.dry_run:
            print("(dry-run — 커밋하지 않았다)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
