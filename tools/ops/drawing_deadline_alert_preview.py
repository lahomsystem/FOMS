"""도면 마감 알림 미리 보기 — **읽기만** 한다(알림 줄 · 기록 줄 · 주문 어느 것도 쓰지 않는다).

설계서 ``docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md`` §9-8 · §11: 운영에서 스위치를 켜기 전에 영업일 사흘
돌려 받을 사람 · 건수를 사장님께 보인다. 스위치(``FOMS_DRAWING_DEADLINE_ALERT_ENABLED``)와 상관없이 돈다. 허용 목록
(``FOMS_DRAWING_DEADLINE_ALERT_ONLY_USERS``)은 이 명령을 돌리는 곳의 env 를 읽어 '건너뜀' 을 따로 보인다.

찍는 것: 그날 알림 칸(마감 날 아침 · 저녁, 마감 지난 뒤 아침) · 주문 번호 · 시공일 · 마감 · 막힌 까닭과 담당 이름 · 받을 사람 이름
(도면 · 영업 · 관리자) · 이미 보냈는지. 고객 이름 · 전화 · 주소 · 금액은 찍지 않는다.

사용법(Flask 앱을 띄우지 않는다 — PostgreSQL 은 트랜잭션 자체를 읽기 전용으로 연다)::

    DATABASE_URL=... python tools/ops/drawing_deadline_alert_preview.py --date 2026-11-23
    DATABASE_URL=... python tools/ops/drawing_deadline_alert_preview.py --date 2026-11-23 --json

종료 코드: ``0`` = 정상(대상 0건 포함), ``1`` = 실행 실패.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

# 저장소 루트를 import 경로에 넣는다 — 직접 실행하면 tools/ops 만 들어간다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

EXIT_OK = 0
EXIT_FAILED = 1
_KIND_LABELS = {"am": "마감 날 아침", "pm": "마감 날 저녁", "late": "마감 지남 · 아침"}


def _names(names: dict[int, str], ids: set[int]) -> list[str]:
    return sorted(names[uid] for uid in ids)


def build_preview(session: Any, day: datetime.date) -> dict[str, Any]:
    """그날 보낼 알림과 받을 사람(쓰기 없음).

    Args:
        session: SQLAlchemy 세션(운영은 읽기 전용 세션, 시험은 요청 세션).
        day: 미리 볼 날(KST).

    Returns:
        ``{'date', 'business_day', 'only_users', 'items': [{order_id, kind, construction_date, deadline, status,
        drawing, sales, admins, fallback, skipped, already_sent}], 'people'}``.
    """
    from foms.services.common.business_calendar import is_business_day
    from foms.services.notifications import drawing_deadline_alert as alert
    from foms.services.notifications import drawing_deadline_plan as plan

    allow = alert.only_user_ids()
    out: dict[str, Any] = {"date": day.isoformat(), "business_day": is_business_day(day),
                           "only_users": sorted(allow) if allow is not None else None, "items": [], "people": 0}
    if not out["business_day"]:
        return out
    dues = plan.due_alerts(session, day, plan.KIND_MORNING)[1] + plan.due_alerts(session, day, plan.KIND_EVENING)[1]
    sent = alert.read_sent(session) if dues else {}
    cache = plan.PeopleCache(session)
    picked = [(due, plan.recipients_for(session, due, cache)) for due in dues]
    names = plan.user_names(session, {uid for _d, rec in picked for uid in rec["all"]})
    everyone: set[int] = set()
    for due, rec in picked:
        allowed = rec["all"] if allow is None else rec["all"] & allow
        everyone |= allowed
        out["items"].append({
            "order_id": due.order_id, "kind": due.kind, "construction_date": due.day.isoformat(),
            "deadline": due.deadline.isoformat(), "status": plan.status_text(due),
            "drawing": _names(names, rec["drawing"]), "sales": _names(names, rec["sales"]),
            "admins": _names(names, rec["admins"]), "fallback": rec["fallback"],
            "skipped": _names(names, rec["all"] - allowed), "already_sent": due.key in sent,
        })
    out["people"] = len(everyone)
    return out


def render_report(preview: dict[str, Any]) -> str:
    """사람이 읽는 요약."""
    head = f"[DRAWING-DEADLINE-PREVIEW] {preview['date']}"
    if not preview["business_day"]:
        return f"{head} — 영업일이 아니라 알림이 없어요."
    lines = [f"{head} — 알림 {len(preview['items'])}건 · 받을 사람 {preview['people']}명"
             + (f" · 허용 목록 {preview['only_users']}" if preview["only_users"] is not None else "")]
    for item in preview["items"]:
        lines.append(f"  #{item['order_id']} {_KIND_LABELS.get(item['kind'], item['kind'])} · 시공 {item['construction_date']}"
                     f" · 마감 {item['deadline']}{' · 이미 보냄' if item['already_sent'] else ''}")
        lines.append(f"      지금: {item['status']}")
        lines.append(f"      받을 사람: 도면 {', '.join(item['drawing']) or '-'} / 영업 {', '.join(item['sales']) or '-'}"
                     + (f" / 관리자 {', '.join(item['admins'])}" if item["admins"] else "")
                     + (" (도면 담당 없음 → 도면팀 전원 + 관리자)" if item["fallback"] else ""))
        if item["skipped"]:
            lines.append(f"      건너뜀(허용 목록 밖): {', '.join(item['skipped'])}")
    return "\n".join(lines)


def _make_readonly_session(url: str):
    """DATABASE_URL 로 읽기 전용 세션을 연다(PostgreSQL 은 트랜잭션 자체를 읽기 전용으로)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from foms.services.db_url_resolver import sqlalchemy_url

    url = sqlalchemy_url(url)
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {
            "connect_timeout": 10,
            "options": "-c default_transaction_read_only=on",
        }
    engine = create_engine(url, **engine_kwargs)
    return sessionmaker(bind=engine)(), engine


def main(argv: list[str] | None = None) -> int:
    """한 번 보고 종료 코드를 낸다(0=정상, 1=실패)."""
    parser = argparse.ArgumentParser(description="도면 마감 알림 미리 보기(읽기 전용)")
    parser.add_argument("--date", required=True, help="미리 볼 날 YYYY-MM-DD(KST)")
    parser.add_argument("--json", action="store_true", help="결과를 JSON 한 줄로 출력")
    args = parser.parse_args(argv)
    try:
        day = datetime.date.fromisoformat(args.date)
    except ValueError:
        print("[DRAWING-DEADLINE-PREVIEW] 실패: --date 는 YYYY-MM-DD 꼴이어야 해요.", file=sys.stderr)
        return EXIT_FAILED
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("[DRAWING-DEADLINE-PREVIEW] 실패: DATABASE_URL 이 없습니다.", file=sys.stderr)
        return EXIT_FAILED
    try:
        session, engine = _make_readonly_session(url)
        try:
            preview = build_preview(session, day)
        finally:
            session.rollback()
            session.close()
            engine.dispose()
    except Exception as exc:  # 미리 보기 실패는 '0건' 과 구별돼야 한다
        print(f"[DRAWING-DEADLINE-PREVIEW] 실패: {exc.__class__.__name__}", file=sys.stderr)
        return EXIT_FAILED
    print(json.dumps(preview, ensure_ascii=False) if args.json else render_report(preview))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
