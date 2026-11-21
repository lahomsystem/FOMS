"""생산 첫 화면 탭 "바뀐 것" 보기 모델 — '누가 · 언제' · 머리 숫자 · 확인한 것 · 더 보기(설계서 §12.3, 사용자 11-21).

목업(``tablet-production-ui-alternatives.html`` 안 4 받은함)대로 채운다:

- 줄마다 '누가 · 언제' — "영업 서하나 · 2시간 전 · <메모>". 누가 = 바꾼 사람의 팀(짧게) + 이름. 시공일 변경은
  ``CONSTRUCTION_DATE_CHANGED`` 의 ``created_by_user_id``, 도면 바뀜 · 수정요청은 도면 이력의 ``by_user_id`` ·
  ``by_user_name``(:mod:`production_change_alerts` 가 항목에 싣는다). 기록에 사람이 없으면 '언제'만 쓴다(지어내지 않는다).
- 언제 = 서버 KST 기준 상대 시간(:func:`change_when_label`) — 방금 · N분 전 · N시간 전(오늘) · 어제 HH:MM · M/D.
  시각은 모두 naive UTC 로 저장돼 있어(``now_utc_naive``) +9시간으로 KST 날짜를 가른다(CI 는 UTC — 날짜를 서버 시계로 안 고른다).
- 확인한 것 = 미확인 변경이 없고 **본인**이 [확인했어요]로 덮은 변경 이력이 있는 생산 단계 주문(D20) — 흐린 장 +
  "<내 이름> 확인 M/D HH:MM"(본인 마지막 ``PRODUCTION_CHANGE_ACK``). 기간 = 상설 이력과 같다(생산 진입 뒤 · D22 바닥선).
  확인 시각 늦은 순. 받은함과 합쳐 :data:`DONE_FILL` 장이 되도록 보이고(적어도 :data:`DONE_MIN`), 나머지는
  "확인한 것 n건 더 보기" 링크(``?tab=changes&done=all`` — 탭 링크와 같은 조각 다시 받기, 스크립트 없음)로 다 보인다.
- 머리 = "바뀐 것 n"(받은함 장 수 = 탭 숫자, 묘비 포함).

쿼리: 사람 이름 · 팀 읽기 1회(``User.id IN (...)``, 바뀐 것 · 찾기 탭만, 읽을 id 가 없으면 0회). 금액은 싣지 않는다(D7).
"""

from __future__ import annotations

import datetime
from typing import Any

from models import User
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.team_labels import team_label
from foms.services.production_home_read_model import _change_line, production_home_inbox

__all__ = [
    "DONE_ALL_VALUE",
    "DONE_FILL",
    "DONE_MIN",
    "ack_when_label",
    "change_when_label",
    "production_home_attach_change_by",
    "production_home_changes_view",
]

#: 받은함 + 확인한 것을 합쳐 이만큼 보이게 채운다(1280×800 가로 2열 = 4줄). 목업은 오른쪽 500px 한 줄이라 1장이었다.
DONE_FILL = 8
#: 받은함이 길어도 확인한 것은 이만큼은 보인다(이력이 있다는 것을 알게).
DONE_MIN = 2
#: ``?done=`` 이 값이면 확인한 것을 모두 그린다(더 보기).
DONE_ALL_VALUE = "all"
#: 목업 "영업 이서연" · "CS 김민지" — 이 두 팀은 '팀' 없이 짧게, 나머지는 팀 이름 정본(도면팀 · 생산팀 …).
_SHORT_TEAM = {"SALES": "영업", "CS": "CS"}
_KST_OFFSET = datetime.timedelta(hours=9)


def _kst(at: datetime.datetime) -> datetime.datetime:
    return at + _KST_OFFSET


def change_when_label(at: datetime.datetime | None, now: datetime.datetime | None = None) -> str:
    """바뀐 시각(naive UTC) → 방금 · N분 전 · N시간 전(KST 오늘) · 어제 HH:MM · M/D. 시각이 없으면 ''."""
    if not isinstance(at, datetime.datetime):
        return ""
    now = now or now_utc_naive()
    seconds = (now - at).total_seconds()
    if seconds < 60:  # 시계가 조금 앞선 기록(음수)도 방금
        return "방금"
    if seconds < 3600:
        return f"{int(seconds // 60)}분 전"
    at_k, today_k = _kst(at), _kst(now).date()
    if at_k.date() == today_k:
        return f"{int(seconds // 3600)}시간 전"
    if at_k.date() == today_k - datetime.timedelta(days=1):
        return f"어제 {at_k:%H:%M}"
    return f"{at_k.month}/{at_k.day}"


def ack_when_label(at: datetime.datetime | None) -> str:
    """확인 시각(naive UTC) → KST 'M/D HH:MM'(목업 "11/3 14:10")."""
    if not isinstance(at, datetime.datetime):
        return ""
    at_k = _kst(at)
    return f"{at_k.month}/{at_k.day} {at_k:%H:%M}"


def _load_people(db: Any, items: list[dict[str, Any]]) -> dict[int, tuple[str, str]]:
    """항목들의 ``by_id`` → (이름, 팀 코드). 한 번의 ``IN`` 쿼리, 읽을 id 가 없으면 쿼리 0."""
    ids = sorted({a["by_id"] for a in items if isinstance(a.get("by_id"), int)})
    if not ids:
        return {}
    rows = db.query(User.id, User.name, User.team).filter(User.id.in_(ids)).all()  # perf-ok: 바꾼 사람 id IN 묶음(줄 수 ≤ 사람 수)
    return {uid: (str(name or "").strip(), str(team or "").strip()) for uid, name, team in rows}


def _who(item: dict[str, Any], people: dict[int, tuple[str, str]]) -> str:
    """'영업 서하나' · '도면팀 도윤재' · 이름만 · ''(기록에 사람이 없으면)."""
    name, team = people.get(item.get("by_id"), ("", ""))
    name = name or str(item.get("by_name") or "").strip()
    if not name:
        return ""
    prefix = _SHORT_TEAM.get(team) or (team_label(team) if team else "")
    return f"{prefix} {name}".strip()


def _by_text(item: dict[str, Any], people: dict[int, tuple[str, str]], now: datetime.datetime) -> str:
    return " · ".join(part for part in (_who(item, people), change_when_label(item.get("at"), now)) if part)


def _lines(alerts: list[dict[str, Any]], people: dict[int, tuple[str, str]], now: datetime.datetime) -> list[dict[str, Any]]:
    """화면 줄 — 원래 항목은 그대로 두고 복사본에 ``m``('누가 · 언제 · 메모')을 더한다.

    시공일은 'from → to' 가 이미 큰 글에 있어 메모가 없다. 도면 · 취소는 ``detail``(전달 메모 · 안내)을 메모로 옮긴다(목업 m 줄).
    """
    out = []
    for a in alerts:
        memo = "" if a.get("kind") == "construction_date" else str(a.get("detail") or "").strip()
        m = " · ".join(part for part in (_by_text(a, people, now), memo) if part)
        out.append({**a, "m": m})
    return out


def _done_items(rows: list[dict[str, Any]], me: str) -> list[dict[str, Any]]:
    items = []
    for row in rows:
        if not row.get("home_done") or row.get("home_acked_at") is None:
            continue
        items.append({
            "kind": "done", "id": row["id"], "customer_name": row.get("customer_name") or "-",
            "product_label": row.get("v3_product_label") or "", "stage": row.get("home_stage") or "",
            "day_label": row.get("day_label") or "", "alerts": row["home_done"], "acked_at": row["home_acked_at"],
            "ack_by": me, "ack_when": ack_when_label(row["home_acked_at"]),
        })
    items.sort(key=lambda it: it["acked_at"], reverse=True)
    return items


def production_home_changes_view(
    db: Any, user: Any, rows: list[dict[str, Any]], tombstones: list[dict[str, Any]], *,
    show_all_done: bool = False, now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """탭 "바뀐 것" 화면 값 — ``{'count', 'inbox', 'done', 'done_more'}``.

    ``inbox`` = :func:`production_home_inbox`(미확인 + 묘비, 시공일 순) · ``count`` = 그 장 수(머리 · 탭 숫자와 같다) ·
    ``done`` = 보이는 확인한 것 · ``done_more`` = 더 보기 뒤에 남은 수(다 보이면 0).
    """
    now = now or now_utc_naive()
    inbox = production_home_inbox(rows, tombstones)
    me = str(getattr(user, "name", None) or getattr(user, "username", "") or "").strip()
    done_all = _done_items(rows, me)
    keep = len(done_all) if show_all_done else max(DONE_MIN, DONE_FILL - len(inbox))
    done = done_all[:keep]
    people = _load_people(db, [a for it in inbox + done for a in it["alerts"]])
    for it in inbox + done:
        it["alerts"] = _lines(it["alerts"], people, now)
    return {"count": len(inbox), "inbox": inbox, "done": done, "done_more": len(done_all) - len(done)}


def production_home_attach_change_by(db: Any, rows: list[dict[str, Any]], now: datetime.datetime | None = None) -> None:
    """찾기 탭 바뀐 줄에 '누가 · 언제'를 넣는다("시공일 변경 11/10 → 11/12 · 영업 서하나 · 2시간 전 · 그 외 1건").

    맨 앞(가장 최근) 변경 한 건의 사람만 읽는다 — 쿼리 1회(바뀐 주문이 없거나 사람 기록이 없으면 0).
    """
    now = now or now_utc_naive()
    changed = [row for row in rows if row.get("home_alerts")]
    people = _load_people(db, [row["home_alerts"][0] for row in changed])
    for row in changed:
        row["change_line"] = _change_line(row["home_alerts"], by=_by_text(row["home_alerts"][0], people, now))
