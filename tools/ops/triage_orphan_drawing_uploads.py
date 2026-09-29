"""전달에 실리지 못한 고아 도면 업로드(R1)를 세 무리로 나누고, 고른 행만 휴지통으로 — 1회성.

배경(설계서 2026-09-29 도면 결함 2차 §4.7 R1·Q4): 2026-07-27 뒤 작업실·ERP 전달 창에서 올린 도면은
``orders/<id>/attachments/`` 로 저장돼(M10) 전달 필터를 못 넘었다. 전달은 400 으로 막혔지만 업로드
행(``category='drawing'``)은 남아, 수령 확정이 파일을 지우지 않게 된 1차 뒤로 고객 링크·ZIP·생산/시공
도면 탭·발주 PUSH 에 보인다. 첨부 탭에서 multipart 로 일부러 올린 '도면'도 같은 경로라 코드로는
가를 신호가 없다 → **목록을 사람이 보고 하나씩 정한다.**

대상(측정 G1 과 같은 조건): 살아 있는 첨부 중 ``category='drawing'``, key 가 ``orders/%/attachments/%``,
``created_at >= --since``(기본 2026-07-27), 주문이 살아 있고, 어떤 TRANSFER 이력의 ``files`` 에도 그
key 가 없는 행.

세 무리:

* ``A_BEFORE_LAST_TRANSFER`` — 그 주문의 마지막 성공 전달 **이전**에 올렸고 현재 도면이 있다.
  숨김 후보. ``--apply --ids`` 로 고른 행만 휴지통으로 보낸다.
* ``B_AFTER_LAST_TRANSFER`` — 마지막 전달 **이후**에 올렸다(또는 전달 시각을 알 수 없다).
  도면팀이 보내려다 막힌 최신본일 수 있어 **숨기지 않는다** — 도면팀 확인 목록.
* ``C_NO_CURRENT`` — 현재 도면(``drawing_current_files``)이 없는 주문. 도면팀에 넘겨 다시 올리게
  한다(2c-1 뒤로는 ``drawing/`` 로 가서 바로 전달된다).

휴지통 규약(설계서 §4.3.6 — 2b 의 첨부 삭제·복구 보강과 같은 이름): 행에 ``deleted_at`` 만 세우고
**``STORAGE_DELETE`` 예약을 하지 않는다**(파일 보존). ``ATTACHMENT_DELETED`` 이벤트 payload 에
``file_retained: true, retained_reason: 'ORPHAN_UPLOAD'`` 를 싣는다. 2b 의 복구 API 는 예약 행이 없고
이 표시가 있으면 파일 존재를 확인한 뒤 되살린다 — 그래서 이 스크립트의 적용은 휴지통 복구로
되돌릴 수 있다. **2b 가 운영에 있기 전에는 적용하지 않는다**(그 전의 복구 API 는 예약 행이 없으면
409 로 거절한다) — 그래서 ``--apply`` 는 ``--confirm-restore-ready`` 를 함께 줘야 돈다(운영자가 2b 복구
보강 배포를 확인했다는 표시).

휴지통 행은 전역 tombstone 필터에 기대지 않고 쿼리가 직접 뺀다(``deleted_at IS NULL``). 그 필터는
``import app`` 의 run_auto_init 이 등록하는데, 앞 단계가 실패하면 예외를 삼켜 필터가 빠질 수 있다.
적용 직전에도 행이 아직 살아 있는지 다시 본다(``deleted_at`` 덮어쓰기·이벤트 중복 방지).

시각: TRANSFER ``transferred_at`` 은 ``now_utc_naive`` 문자열, 첨부 ``created_at`` 은 서버 현지 시각
(운영 Railway = UTC)이라 naive 끼리 비교한다. 로컬 dev DB 의 옛 행은 KST 가 섞여 있을 수 있다.

기본은 dry-run(무리별 목록 JSON 출력, 쓰기 0). 적용은 ``--apply --ids 1,2,3`` 을 명시하고, 고른 id 가
지금도 A 무리일 때만 휴지통으로 보낸다(B·C·대상 밖은 건너뛰고 이유를 적는다). 재실행하면 적용한
행은 대상에서 빠진다(멱등).

사용법::

    python tools/ops/triage_orphan_drawing_uploads.py                    # dry-run
    python tools/ops/triage_orphan_drawing_uploads.py --since 2026-07-27 --dry-run
    python tools/ops/triage_orphan_drawing_uploads.py --apply --ids 101,102 --actor-user-id 1 --confirm-restore-ready
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from models import Order, OrderAttachment, OrderEvent, User  # noqa: E402

BUCKET_A = "A_BEFORE_LAST_TRANSFER"
BUCKET_B = "B_AFTER_LAST_TRANSFER"
BUCKET_C = "C_NO_CURRENT"
BUCKETS = (BUCKET_A, BUCKET_B, BUCKET_C)
BUCKET_ACTIONS = {
    BUCKET_A: "숨김 후보(휴지통·파일 보존 — 고른 것만 적용)",
    BUCKET_B: "도면팀 확인(숨기지 않음 — 보내려던 최신본일 수 있음)",
    BUCKET_C: "도면팀에 다시 올림 요청(현재 도면 없음)",
}
#: 설계서 §4.3.6 휴지통 규약 — 2b 복구 API 가 읽는 이름. 바꾸지 않는다.
ATTACHMENT_DELETED = "ATTACHMENT_DELETED"
RETAINED_REASON = "ORPHAN_UPLOAD"
DEFAULT_SINCE = datetime.datetime(2026, 7, 27)
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _history(sd: Any) -> list[dict]:
    items = sd.get("drawing_transfer_history") if isinstance(sd, dict) else None
    return [h for h in (items or []) if isinstance(h, dict)]


def _transfers(sd: Any) -> list[dict]:
    return [h for h in _history(sd) if str(h.get("action") or "").upper() == "TRANSFER"]


def transferred_keys(sd: Any) -> set[str]:
    """어떤 TRANSFER 이력의 ``files`` 에든 오른 key."""
    return {
        str(f.get("key") or "").strip()
        for h in _transfers(sd) for f in (h.get("files") or [])
        if isinstance(f, dict) and f.get("key")
    }


def last_transfer_at(sd: Any) -> datetime.datetime | None:
    """마지막 성공 전달 시각(``transferred_at`` 을 읽을 수 있는 TRANSFER 중 가장 늦은 것)."""
    stamps = []
    for h in _transfers(sd):
        raw = h.get("transferred_at")
        if isinstance(raw, str) and raw.strip():
            try:
                stamps.append(datetime.datetime.strptime(raw.strip()[:19], _TS_FMT))
            except ValueError:
                continue
    return max(stamps) if stamps else None


def _has_current(sd: Any) -> bool:
    current = sd.get("drawing_current_files") if isinstance(sd, dict) else None
    return any(isinstance(f, dict) and f.get("key") for f in (current or []))


def classify(created_at: datetime.datetime | None, sd: Any) -> tuple[str, str]:
    """(무리, 이유) — 설계서 §4.7 세 무리. 전달 시각을 모르면 숨기지 않는 쪽(B)으로 둔다."""
    if not _has_current(sd):
        return BUCKET_C, "현재 도면 없음"
    last = last_transfer_at(sd)
    if last is None:
        return BUCKET_B, "마지막 전달 시각을 알 수 없음 — 숨기지 않음"
    if created_at is None or created_at > last:
        return BUCKET_B, "마지막 전달 이후 업로드"
    return BUCKET_A, "마지막 전달 이전 업로드 + 현재 도면 있음"


def find_orphan_uploads(session: Session, *, since: datetime.datetime = DEFAULT_SINCE) -> list[dict]:
    """고아 도면 업로드 목록(첨부 id 오름차순) — 무리·이유·업로더 팀 포함. 쓰기 없음."""
    rows = (
        session.query(OrderAttachment, Order)
        .join(Order, Order.id == OrderAttachment.order_id)
        .filter(
            func.lower(OrderAttachment.category) == "drawing",
            OrderAttachment.storage_key.like("orders/%/attachments/%"),
            OrderAttachment.created_at >= since,
            OrderAttachment.deleted_at.is_(None),
            Order.not_deleted_filter(),
        )
        .order_by(OrderAttachment.id)
        .all()
    )
    user_ids = {att.user_id for att, _order in rows if att.user_id}
    teams = dict(session.query(User.id, User.team).filter(User.id.in_(user_ids)).all()) if user_ids else {}
    out: list[dict] = []
    for att, order in rows:
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        if att.storage_key in transferred_keys(sd):
            continue
        bucket, reason = classify(att.created_at, sd)
        last = last_transfer_at(sd)
        out.append({
            "attachment_id": int(att.id),
            "order_id": int(order.id),
            "storage_key": att.storage_key,
            "filename": att.filename,
            "created_at": att.created_at.isoformat(sep=" ") if att.created_at else None,
            "last_transfer_at": last.isoformat(sep=" ") if last else None,
            "uploader_team": teams.get(att.user_id) or "?",
            "bucket": bucket,
            "reason": reason,
        })
    return out


def _tombstone_retained(session: Session, attachment: OrderAttachment, *, actor_user_id: int | None,
                        now: datetime.datetime) -> OrderEvent:
    """휴지통으로(파일 보존) — ``deleted_at`` + ``ATTACHMENT_DELETED``(file_retained) + 감사 1행."""
    from foms.web.auth import log_access  # 앱 import 뒤에만 순환 없이 풀린다(main 이 먼저 import app).

    attachment.deleted_at = now
    attachment.deleted_by_user_id = actor_user_id
    event = OrderEvent(
        order_id=attachment.order_id,
        event_type=ATTACHMENT_DELETED,
        payload={
            "attachment_id": attachment.id,
            "storage_key": attachment.storage_key,
            "thumbnail_key": attachment.thumbnail_key,
            "filename": attachment.filename,
            "category": attachment.category,
            "deleted_at": now.isoformat(),
            "file_retained": True,
            "retained_reason": RETAINED_REASON,
            "source": "tools/ops/triage_orphan_drawing_uploads.py",
        },
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    session.add(event)
    session.flush()
    log_access(
        f"고아 도면 업로드 휴지통(파일 보존): 주문 {attachment.order_id} · {attachment.filename}",
        actor_user_id, auto_commit=False, db=session,
        action="FILE_DELETED", target_type="order", target_id=int(attachment.order_id),
        detail={"attachment_id": attachment.id, "filename": attachment.filename, "category": attachment.category,
                "storage_key": attachment.storage_key, "file_retained": True,
                "retained_reason": RETAINED_REASON},
    )
    return event


def run(session: Session, *, since: datetime.datetime = DEFAULT_SINCE,
        apply_ids: list[int] | None = None, actor_user_id: int | None = None) -> dict:
    """무리별 목록을 만들고, ``apply_ids`` 가 있으면 그중 A 무리만 휴지통으로 보낸다.

    Returns:
        ``{"mode", "since", "counts", "rows", "applied", "skipped"}``. dry-run 이면 applied·skipped 는 빈 목록.
    """
    rows = find_orphan_uploads(session, since=since)
    summary: dict[str, Any] = {
        "mode": "apply" if apply_ids is not None else "dry-run",
        "since": since.isoformat(sep=" "),
        "counts": {b: {"rows": 0, "orders": 0, "action": BUCKET_ACTIONS[b]} for b in BUCKETS},
        "uploader_team_by_bucket": {b: {} for b in BUCKETS},
        "rows": rows,
        "applied": [],
        "skipped": [],
    }
    for bucket in BUCKETS:
        mine = [r for r in rows if r["bucket"] == bucket]
        summary["counts"][bucket]["rows"] = len(mine)
        summary["counts"][bucket]["orders"] = len({r["order_id"] for r in mine})
        summary["uploader_team_by_bucket"][bucket] = dict(Counter(r["uploader_team"] for r in mine))
    if apply_ids is None:
        return summary

    by_id = {r["attachment_id"]: r for r in rows}
    now = now_utc_naive()
    for att_id in apply_ids:
        row = by_id.get(att_id)
        if row is None:
            summary["skipped"].append({"attachment_id": att_id, "reason": "대상 밖(이미 휴지통·전달됨·조건 불일치)"})
            continue
        if row["bucket"] != BUCKET_A:
            summary["skipped"].append({"attachment_id": att_id, "reason": f"{row['bucket']} 는 숨기지 않는다"})
            continue
        att = session.get(OrderAttachment, att_id)
        if att is None or att.deleted_at is not None:
            summary["skipped"].append({"attachment_id": att_id, "reason": "이미 휴지통(적용 직전 재확인)"})
            continue
        event = _tombstone_retained(session, att, actor_user_id=actor_user_id, now=now)
        summary["applied"].append({**row, "event_id": int(event.id)})
    if summary["applied"]:
        session.commit()
        from foms.services.common.dashboard_cache import (
            ATTACHMENT_DASHBOARD_FAMILIES,
            invalidate_dashboard_families,
        )

        invalidate_dashboard_families(*ATTACHMENT_DASHBOARD_FAMILIES)
    return summary


def _parse_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.replace(" ", "").split(",") if part]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Triage orphan drawing uploads into 3 buckets (default: dry-run).")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default).")
    parser.add_argument("--apply", action="store_true",
                        help="Tombstone (file retained) the given --ids that are still bucket A.")
    parser.add_argument("--ids", default="", help="Comma separated attachment ids for --apply.")
    parser.add_argument("--since", default=DEFAULT_SINCE.date().isoformat(),
                        help="Only uploads created at/after this date (YYYY-MM-DD).")
    parser.add_argument("--actor-user-id", type=int, default=None,
                        help="User id recorded as deleted_by / event actor.")
    parser.add_argument("--confirm-restore-ready", action="store_true",
                        help="Required with --apply: confirms the 2b restore path (file_retained rows) "
                             "is deployed, so applied rows can be restored from the trash.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. 0 = ok, 1 = misuse."""
    args = _parse_args(argv)
    if args.dry_run and args.apply:
        print("[ERROR] --dry-run and --apply are mutually exclusive")
        return 1
    ids = _parse_ids(args.ids) if args.ids else []
    if args.apply and not ids:
        print("[ERROR] --apply needs --ids (pick rows from the dry-run list)")
        return 1
    if args.apply and not args.confirm_restore_ready:
        print("[ERROR] --apply needs --confirm-restore-ready (deploy the 2b restore path first)")
        return 1
    since = datetime.datetime.fromisoformat(args.since)

    import app  # noqa: F401,E402 — 앱 모듈을 먼저 올려 foms.web.auth 순환 import 를 푼다.
    from sqlalchemy.orm import sessionmaker

    from db import engine

    session = sessionmaker(bind=engine)()
    try:
        summary = run(session, since=since, apply_ids=ids if args.apply else None,
                      actor_user_id=args.actor_user_id)
    finally:
        session.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
