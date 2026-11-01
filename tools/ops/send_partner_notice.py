"""협력사 공지 보내기 — 켜진 협력사의 켜진 직원마다 공지 1건(협력사 화면에 "확인"을 눌러야 닫히는 창으로 뜬다).

공지 글은 아래 ``NOTICES`` 에 이름을 붙여 둔다(운영 컨테이너에 글 파일을 따로 올리지 않아도 되게). 같은 제목을 이미 받은
직원은 건너뛴다(다시 돌려도 안전). 기본은 dry-run, ``--apply`` 때만 쓴다. 공지 · 확인 판정은
:mod:`foms.services.partners.notices`.

사용(운영은 배포 뒤 ``railway ssh -s web`` 안에서):
    python tools/ops/send_partner_notice.py --notice 2026-11-measure-pending --actor-user-id <관리자 id>
    python tools/ops/send_partner_notice.py --notice 2026-11-measure-pending --actor-user-id <관리자 id> --apply
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from foms.services.db_url_resolver import sqlalchemy_url  # noqa: E402
from foms.services.partners.notices import create_partner_notice  # noqa: E402

NOTICES = {
    # 실측 예정 · 도면 요청(docs/specs/2026-11-01-partner-measure-pending_SPEC.md, 사용자 2026-11-02).
    "2026-11-measure-pending": {
        "title": "실측 전 주문은 '실측 예정'으로 들어갑니다",
        "message": (
            "주문 등록 방법이 조금 바뀌었습니다.\n"
            "\n"
            "1. 새 주문을 저장할 때 '실측을 마쳤나요?'를 꼭 골라 주세요.\n"
            "   실측 전이면 '아직이에요'를 고르고, 실측일에 실측 예정일을 넣어 주세요.\n"
            "\n"
            "2. 실측을 마치면 주문 화면에서 제품마다 가로 치수를 넣고 '실측 끝 · 도면 요청'을 눌러 주세요.\n"
            "   그때 저희 도면팀이 도면 작업을 시작합니다.\n"
            "\n"
            "3. 이미 올려 주신 실측 전 주문도 '실측 예정'으로 옮겨 두었습니다.\n"
            "   실측을 마치면 같은 방법으로 도면을 요청해 주세요.\n"
            "\n"
            "희망 시공일은 지금처럼 넣어 주시면 저희 출고 담당자가 확인합니다."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), help="PostgreSQL 접속 문자열")
    parser.add_argument("--notice", required=True, choices=sorted(NOTICES), help="보낼 공지 이름")
    parser.add_argument("--actor-user-id", type=int, required=True, help="보낸 사람으로 남길 본사 관리자 id")
    parser.add_argument("--actor-name", default="라홈 본사", help="보낸 사람 이름(공지에 남는다)")
    parser.add_argument("--apply", action="store_true", help="실제로 보낸다(기본 dry-run)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # PS-ENC-01: Windows cp949 콘솔에서도 한글 출력
    if not args.dsn:
        print("--dsn 또는 DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    notice = NOTICES[args.notice]
    engine = create_engine(sqlalchemy_url(args.dsn), future=True)
    with Session(engine) as session:
        rows = create_partner_notice(session, title=notice["title"], message=notice["message"],
                                     actor_user_id=args.actor_user_id, actor_name=args.actor_name, apply=args.apply)
        if args.apply:
            session.commit()
    for row in rows:
        print(f"user {row['user_id']} {row['name']} (협력사 {row['org_id']}): {row['verdict']}")
    print(("APPLY" if args.apply else "DRY-RUN"), notice["title"], f"{len(rows)}명")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
