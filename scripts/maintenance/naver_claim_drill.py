"""수집 후 취소 추적(T14-F) 실전 리허설 — 네이버 호출 없이 클레임을 흉내 낸다.

**왜 필요한가**: 취소 추적은 "고객이 결제 후 네이버에서 취소" 라는 남의 사건에 의존해
켜진다. 진짜 취소가 날 때까지 기다리면 첫 실전이 곧 첫 시험이 된다. 이 스크립트는 이미
수집해 둔 링크의 **저장된 원본 스냅샷에 ``claimStatus`` 만 얹어** 상세 조회 응답인 척
:func:`claim_watch.refresh_claims` 에 먹인다. 네이버로 나가는 HTTP 는 0회다(스텁 클라이언트).

검증 대상: 스냅샷 교체 · ``triage_state['claim_sync']`` 기록 · 상태별 1회 알림 ·
알림 fan-out(수신자 per-user row) · 화면(도크/이력 취소 배지).

**되돌리기 필수**: ``--apply`` 는 백업 JSON 을 남긴다. 확인이 끝나면 반드시
``--revert <백업파일>`` 로 스냅샷·triage_state 를 원복하고 드릴이 만든 알림을 지운다.

사용 예 (PowerShell 5.x / bash 동일)::

    # 1) 미리보기 (DB 무변경)
    python scripts/maintenance/naver_claim_drill.py --link-id 53
    # 2) 실행 — 백업 파일 경로가 출력된다
    python scripts/maintenance/naver_claim_drill.py --link-id 53 --status CANCEL_REQUEST --apply
    # 3) 화면 확인 후 원복
    python scripts/maintenance/naver_claim_drill.py --revert <백업파일>

운영(production) DB 를 향해 실행하지 않는다. 연습 서버(FOMS-DEV) 전용이다.
"""
import argparse
import copy
import json
import os
import sys
from datetime import datetime
from typing import Any

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.integrations.naver_commerce.claim_watch import (  # noqa: E402
    NOTIFICATION_TYPE,
    STATE_KEY,
    refresh_claims,
)
from foms.services.integrations.naver_commerce.constants import CHANNEL  # noqa: E402
from foms.services.integrations.naver_commerce.mapping import (  # noqa: E402
    BLOCKING_CLAIM_STATUSES,
    extract_claim,
)
from models import (  # noqa: E402
    ExternalOrderLink,
    Notification,
    NotificationEvent,
    NotificationUserState,
)


class _StubClient:
    """상세 조회만 흉내 내는 클라이언트. 네이버로 나가는 요청은 없다."""

    def __init__(self, details: list[dict]) -> None:
        self._details = details
        self.calls: list[list[str]] = []

    def get_product_orders(self, ids: list[str]) -> list[dict]:
        """``refresh_claims`` 가 부르는 유일한 메서드."""
        self.calls.append(list(ids))
        wanted = {str(i) for i in ids}
        return [d for d in self._details if str(d.get("productOrderId") or "") in wanted]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rehearse post-ingest claim tracking.")
    parser.add_argument("--link-id", type=int, action="append", default=[],
                        help="드릴 대상 ExternalOrderLink id (여러 번 지정 가능).")
    parser.add_argument("--status", default="CANCEL_REQUEST",
                        help=f"흉내 낼 claimStatus (기본 CANCEL_REQUEST). "
                             f"차단 상태: {', '.join(sorted(BLOCKING_CLAIM_STATUSES))}")
    parser.add_argument("--reason", default="드릴(연습) — 실제 취소가 아니다",
                        help="cancelReason 문구.")
    parser.add_argument("--apply", action="store_true",
                        help="실제로 DB 에 반영한다(생략하면 미리보기).")
    parser.add_argument("--backup", default="",
                        help="백업 JSON 경로(생략 시 자동 생성).")
    parser.add_argument("--revert", default="",
                        help="백업 JSON 경로 — 스냅샷·triage_state 원복 + 드릴 알림 삭제.")
    return parser.parse_args()


def _fake_detail(link: ExternalOrderLink, status: str, reason: str) -> dict:
    """저장된 원본에 클레임 필드만 얹은 가짜 상세 응답을 만든다.

    Args:
        link: 대상 링크(원본 스냅샷 보유).
        status: 흉내 낼 ``claimStatus``.
        reason: 취소 사유 문구.

    Returns:
        ``refresh_claims`` 에 먹일 상세 dict.
    """
    detail = copy.deepcopy(link.raw_snapshot or {})
    detail.setdefault("productOrderId", str(link.external_id))
    product_order = detail.get("productOrder")
    if not isinstance(product_order, dict):
        product_order = {}
        detail["productOrder"] = product_order
    product_order["claimStatus"] = status
    product_order["claimType"] = "CANCEL" if status.startswith("CANCEL") else "RETURN"
    detail["cancel"] = {
        "claimStatus": status,
        "cancelReason": reason,
        "claimRequestDate": datetime.now().isoformat(timespec="seconds"),
    }
    return detail


def _load_links(db: Any, link_ids: list[int]) -> list[ExternalOrderLink]:
    """대상 링크를 읽는다. 없는 id 는 즉시 에러로 알린다."""
    links = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL, ExternalOrderLink.id.in_(link_ids))
        .all()
    )
    missing = sorted(set(link_ids) - {int(x.id) for x in links})
    if missing:
        raise SystemExit(f"[FAIL] 없는 링크 id: {missing}")
    return links


def _backup_path(explicit: str) -> str:
    """백업 파일 경로를 정한다(기본: 현재 디렉토리에 타임스탬프 파일)."""
    if explicit:
        return explicit
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.abspath(f"naver_claim_drill_backup_{stamp}.json")


def _db_identity(db: Any) -> str:
    """지금 붙어 있는 DB 를 사람이 확인할 수 있게 한 줄로 만든다.

    연습 서버 전용 도구라 **어느 DB 인지 눈으로 대조하는 것이 첫 안전장치**다.
    """
    from sqlalchemy import text

    row = db.execute(
        text("select current_database(), coalesce(inet_server_addr()::text, 'local')")
    ).first()
    return f"{row[0]} @ {row[1]}" if row else "unknown"


def _run_drill(db: Any, args: argparse.Namespace) -> int:
    """드릴 본체 — 미리보기(기본) 또는 실행(``--apply``)."""
    if not args.link_id:
        raise SystemExit("[FAIL] --link-id 를 하나 이상 지정한다.")
    links = _load_links(db, args.link_id)
    details = [_fake_detail(link, args.status, args.reason) for link in links]

    print(f"[DB] {_db_identity(db)}")
    for link, detail in zip(links, details):
        claim = extract_claim(detail)
        print(f"[대상] link={link.id} external_id={link.external_id} order_id={link.order_id} "
              f"sync_status={link.sync_status} → claim={claim['status']}({claim['label']}) "
              f"blocking={claim['blocking']}")
    if not args.apply:
        print("[미리보기] --apply 없이는 DB 를 바꾸지 않는다.")
        return 0
    return _apply_drill(db, args, links, details)


def _snapshot_backup(args: argparse.Namespace,
                     links: list[ExternalOrderLink]) -> dict[str, Any]:
    """원복에 필요한 원본 값을 dict 로 뜬다(파일 기록은 호출자)."""
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": args.status,
        "links": [
            {
                "id": int(link.id),
                "raw_snapshot": copy.deepcopy(link.raw_snapshot),
                "triage_state": copy.deepcopy(link.triage_state),
            }
            for link in links
        ],
    }


def _apply_drill(db: Any, args: argparse.Namespace,
                 links: list[ExternalOrderLink], details: list[dict]) -> int:
    """실제 반영 — 백업 기록 → ``refresh_claims`` → 결과 출력."""
    changed = [{"productOrderId": str(link.external_id)} for link in links]
    before = db.query(Notification.id).order_by(Notification.id.desc()).first()
    before_max_id = int(before[0]) if before else 0
    backup = _snapshot_backup(args, links)

    client = _StubClient(details)
    result = refresh_claims(db, client=client, changed=changed)
    db.flush()
    backup["notification_ids"] = [
        int(row[0])
        for row in db.query(Notification.id)
        .filter(Notification.id > before_max_id,
                Notification.notification_type == NOTIFICATION_TYPE)
        .all()
    ]
    path = _backup_path(args.backup)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(backup, fh, ensure_ascii=False, indent=2, default=str)
    db.commit()

    print(f"[결과] {result} · 네이버 호출 0회(스텁 상세조회 {len(client.calls)}회)")
    print(f"[알림] 새로 만든 {NOTIFICATION_TYPE} id={backup['notification_ids']}")
    for link in links:
        db.refresh(link)
        print(f"[상태] link={link.id} claim_sync={(link.triage_state or {}).get(STATE_KEY)}")
    print(f"[백업] {path}")
    print("[다음] 화면 확인이 끝나면 --revert 로 반드시 원복한다.")
    return 0


def _delete_notifications(db: Any, ids: list[int]) -> int:
    """드릴이 만든 알림을 자식 row 부터 순서대로 지운다.

    ``notification_events.user_state_id`` 는 ondelete 가 없어 DB CASCADE 만 믿으면
    삭제 순서에 따라 FK 위반이 날 수 있다. event → user_state → notification 순으로 지운다.

    Args:
        db: 세션.
        ids: 삭제할 notification id 목록.

    Returns:
        삭제한 notification 건수.
    """
    if not ids:
        return 0
    db.query(NotificationEvent).filter(
        NotificationEvent.notification_id.in_(ids)
    ).delete(synchronize_session=False)
    db.query(NotificationUserState).filter(
        NotificationUserState.notification_id.in_(ids)
    ).delete(synchronize_session=False)
    return (
        db.query(Notification)
        .filter(Notification.id.in_(ids),
                Notification.notification_type == NOTIFICATION_TYPE)
        .delete(synchronize_session=False)
    )


def _revert(db: Any, path: str) -> int:
    """백업 JSON 으로 스냅샷·triage_state 를 되돌리고 드릴 알림을 지운다."""
    from sqlalchemy.orm.attributes import flag_modified

    with open(path, "r", encoding="utf-8") as fh:
        backup = json.load(fh)
    restored = 0
    for row in backup.get("links") or []:
        link = db.get(ExternalOrderLink, int(row["id"]))
        if link is None:
            print(f"[SKIP] 링크 {row['id']} 가 없다")
            continue
        link.raw_snapshot = row.get("raw_snapshot")
        link.triage_state = row.get("triage_state")
        flag_modified(link, "raw_snapshot")
        flag_modified(link, "triage_state")
        restored += 1
    deleted = _delete_notifications(db, [int(i) for i in (backup.get("notification_ids") or [])])
    db.commit()
    print(f"[원복] 링크 {restored}건 · 알림 {deleted}건 삭제 (백업 {path})")
    return 0


def main() -> int:
    """엔트리포인트."""
    args = _parse_args()
    with app.app_context():
        db = get_db()
        try:
            if args.revert:
                return _revert(db, args.revert)
            return _run_drill(db, args)
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
