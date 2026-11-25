"""한 도면 · 한 파트를 여러 명이 같이 작업 — 작업하는 사람 목록(표시 줄 칸 ``holders``) 순수 함수(설계서 2026-11-25 multi-holder §4 · §5).

쿼리 0 · DB 0. 표시 줄(``ProductionPartMark`` 또는 같은 모양)의 목록을 읽고(:func:`crew_of`), 사람 하나를 넣고 · 빼고 · 완료하고 ·
되돌린 **새 목록**을 돌려준다(받은 목록은 건드리지 않는다 — 고칠 때마다 깊은 사본). 줄의 상태 칸 · 한 명짜리 칸은 목록의
요약이다(:func:`summarize` — 모두 완료 = DONE, 한 명이라도 아직 = NEED, 첫 사람 = ``picked_by_*``, 가장 늦게 완료한 사람 = ``done_by_*``).

목록 한 칸(시작한 차례)::

    {"uid": 31, "name": "이시영", "at": "2026-11-24T23:10:00+00:00",
     "done_at": "2026-11-25T02:30:00+00:00", "done_uid": 31, "done_name": "이시영"}

* ``at`` = 그 사람이 시작한 때(밤 넘김 · 아침 칩 — Q21), ``done_*`` = 그 사람 몫의 완료(대신 완료면 반장 이름 — Q15).
* **읽기 정규화**(§4-3 · Q18 ②): 칸이 NULL(옛 줄 · 옛 코드가 쓴 줄)이면 요약 칸에서 푼다. 목록의 요약(상태 · 첫 사람 · 완료한 사람)이
  줄의 요약 칸과 다르면 옛 코드가 마지막으로 쓴 줄이라 요약 칸이 이긴다. 모든 읽기가 :func:`crew_of` 하나만 쓴다.
* 사람 없는 줄(안 봄 · 재단 기본 · 풀어 쓴 완료 · 옛 줄의 담당 없는 완료)은 빈 목록이다 — 그 상태는 부르는 쪽이 지금 규칙대로 정한다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import parse_datetime_utc, to_utc_naive
from foms.services.production.part_constants import MARK_STATE_DONE, MARK_STATE_NEED, MARK_STATE_NONE

#: 이름 줄에 이름으로 쓰는 사람 수(Q10 · Q20 — "둘까지 이름, 나머지는 '외 n'").
NAME_LINE_LIMIT = 2
#: 내 몫(화면이 보내는 ``seen_me`` 와 같은 낱말).
SHARE_NONE, SHARE_HELD, SHARE_DONE = "none", "held", "done"
SHARE_VALUES: tuple[str, ...] = (SHARE_NONE, SHARE_HELD, SHARE_DONE)

Member = dict[str, Any]


def to_iso(value: Optional[datetime.datetime]) -> Optional[str]:
    """DB UTC naive 시각 → 시간대가 붙은 UTC ISO 글(없으면 None)."""
    aware = parse_datetime_utc(value) if value is not None else None
    return aware.isoformat() if aware is not None else None


def from_iso(text: Any) -> Optional[datetime.datetime]:
    """목록의 ISO 글 → DB 와 같은 UTC naive 시각(없거나 틀리면 None)."""
    return to_utc_naive(text) if text else None


def member(uid: Optional[int], name: Optional[str], at: Optional[str], *, done_at: Optional[str] = None,
           done_uid: Optional[int] = None, done_name: Optional[str] = None) -> Member:
    """목록 한 칸을 만든다.

    Args:
        uid: 작업하는 사람 id(사용자가 지워졌으면 None).
        name: 이름 스냅샷.
        at: 시작한 때(UTC ISO).
        done_at · done_uid · done_name: 그 사람 몫 완료(아직이면 모두 None).

    Returns:
        :data:`Member` dict.
    """
    return {"uid": uid, "name": name, "at": at, "done_at": done_at, "done_uid": done_uid, "done_name": done_name}


def is_done(item: Member) -> bool:
    """그 사람 몫이 완료인지 — 완료 칸 셋 중 하나라도 차 있으면 완료."""
    return any(item.get(key) is not None for key in ("done_at", "done_uid", "done_name"))


def _clean(raw: Any) -> Optional[Member]:
    """저장된 한 칸 → 모양을 맞춘 칸(사람이 없는 칸 · 모르는 꼴은 None — 버린다)."""
    if not isinstance(raw, dict):
        return None
    uid = raw.get("uid")
    uid = uid if isinstance(uid, int) and not isinstance(uid, bool) else None
    name = str(raw.get("name") or "").strip() or None
    if uid is None and name is None:
        return None
    done_uid = raw.get("done_uid")
    done_uid = done_uid if isinstance(done_uid, int) and not isinstance(done_uid, bool) else None
    done_name = raw.get("done_name")
    return member(uid, name, raw.get("at") or None, done_at=raw.get("done_at") or None, done_uid=done_uid,
                  done_name=str(done_name) if done_name is not None else None)


def _stored(row: Any) -> list[Member]:
    """줄에 저장된 목록(모양을 맞춘 칸만 — 칸이 NULL · 목록이 아니면 빈 목록)."""
    raw = getattr(row, "holders", None)
    if not isinstance(raw, list):
        return []
    return [m for m in (_clean(item) for item in raw) if m is not None]


def _from_summary(row: Any) -> list[Member]:
    """요약 칸(한 명짜리 칸)에서 목록을 푼다 — NEED · DONE 이고 담당이 있으면 그 한 사람, 그 밖 빈 목록."""
    state = str(getattr(row, "state", None) or MARK_STATE_NONE)
    uid, name = getattr(row, "picked_by_user_id", None), str(getattr(row, "picked_by_name", None) or "").strip() or None
    if state not in (MARK_STATE_NEED, MARK_STATE_DONE) or (uid is None and name is None):
        return []
    item = member(uid, name, to_iso(getattr(row, "picked_at", None)))
    if state == MARK_STATE_DONE:
        done_name = getattr(row, "done_by_name", None)
        item.update(done_at=to_iso(getattr(row, "done_at", None) or getattr(row, "updated_at", None)),
                    done_uid=getattr(row, "done_by_user_id", None), done_name=done_name if done_name is not None else "")
    return [item]


def summarize(crew: Iterable[Member]) -> Optional[dict[str, Any]]:
    """목록 → 줄의 요약 칸. 빈 목록이면 None(사람 없는 줄 — 상태는 부르는 쪽이 정한다).

    Returns:
        ``{state, picked_by_user_id, picked_by_name, picked_at, done_by_user_id, done_by_name, done_at}`` — 한 명이라도
        아직이면 NEED(완료 칸 비움), 모두 완료면 DONE(완료 칸 = 가장 늦게 완료한 사람 — 같은 때면 목록 뒤쪽).
    """
    crew = list(crew)
    if not crew:
        return None
    first = crew[0]
    out = {"picked_by_user_id": first.get("uid"), "picked_by_name": first.get("name"), "picked_at": from_iso(first.get("at")),
           "state": MARK_STATE_NEED, "done_by_user_id": None, "done_by_name": None, "done_at": None}
    if all(is_done(m) for m in crew):
        floor = datetime.datetime.min
        last = max(enumerate(crew), key=lambda pair: (from_iso(pair[1].get("done_at")) or floor, pair[0]))[1]
        out.update(state=MARK_STATE_DONE, done_by_user_id=last.get("done_uid"), done_by_name=last.get("done_name") or None,
                   done_at=from_iso(last.get("done_at")))
    return out


def _agrees(crew: list[Member], row: Any) -> bool:
    """목록의 요약(상태 · 첫 사람 · 완료한 사람)이 줄의 요약 칸과 같은지(§4-3)."""
    summary = summarize(crew)
    if summary is None:
        return False
    return (summary["state"], summary["picked_by_user_id"], summary["done_by_user_id"]) == (
        str(getattr(row, "state", None) or ""), getattr(row, "picked_by_user_id", None), getattr(row, "done_by_user_id", None))


def crew_of(row: Any) -> list[Member]:
    """표시 줄의 작업하는 사람 목록(읽기 정규화 — §4-3). 줄이 없으면 빈 목록.

    Args:
        row: ``ProductionPartMark`` 줄 · 같은 모양(SimpleNamespace) · None.

    Returns:
        새 목록(시작한 차례). 저장된 목록이 요약 칸과 맞으면 그 목록, 아니면 요약 칸에서 푼 목록.
    """
    if row is None:
        return []
    stored = _stored(row)
    if stored and _agrees(stored, row):
        return stored
    return _from_summary(row)


def find(crew: Iterable[Member], uid: Any) -> Optional[Member]:
    """목록에서 그 사람 칸(없거나 uid 가 None 이면 None)."""
    if uid is None:
        return None
    return next((m for m in crew if m.get("uid") == uid), None)


def share_of(crew: Iterable[Member], uid: Any) -> str:
    """그 사람 몫 — none(목록에 없음) · held(작업 중) · done(내 몫 완료)."""
    item = find(crew, uid)
    if item is None:
        return SHARE_NONE
    return SHARE_DONE if is_done(item) else SHARE_HELD


def join(crew: Iterable[Member], uid: int, name: Optional[str], now: datetime.datetime) -> list[Member]:
    """목록 끝에 한 사람을 더한 새 목록(이미 있으면 그대로)."""
    out = copy.deepcopy(list(crew))
    if find(out, uid) is None:
        out.append(member(uid, name, to_iso(now)))
    return out


def leave(crew: Iterable[Member], uid: Any) -> list[Member]:
    """그 사람을 뺀 새 목록."""
    return [copy.deepcopy(m) for m in crew if m.get("uid") != uid]


def _done_fields(by_uid: Optional[int], by_name: Optional[str], now: datetime.datetime) -> dict[str, Any]:
    """완료 칸 셋(이름이 없으면 빈 글 — 완료 표지는 남긴다)."""
    return {"done_at": to_iso(now), "done_uid": by_uid, "done_name": by_name if by_name is not None else ""}


def finish(crew: Iterable[Member], uid: Any, *, by_uid: Optional[int], by_name: Optional[str],
           now: datetime.datetime) -> list[Member]:
    """그 사람 몫을 완료한 새 목록(누른 사람 = ``by_*``)."""
    out = copy.deepcopy(list(crew))
    for item in out:
        if item.get("uid") == uid and not is_done(item):
            item.update(_done_fields(by_uid, by_name, now))
    return out


def finish_rest(crew: Iterable[Member], *, by_uid: Optional[int], by_name: Optional[str],
                now: datetime.datetime) -> list[Member]:
    """남은 사람 몫을 한 번에 완료한 새 목록(대신 완료 — Q15, 누른 사람은 목록에 들어가지 않는다)."""
    out = copy.deepcopy(list(crew))
    for item in out:
        if not is_done(item):
            item.update(_done_fields(by_uid, by_name, now))
    return out


def unfinish(crew: Iterable[Member], uids: Optional[Iterable[Any]] = None) -> list[Member]:
    """그 사람들 몫 완료를 끈 새 목록(``uids`` 가 None 이면 모두)."""
    pick = None if uids is None else set(uids)
    out = copy.deepcopy(list(crew))
    for item in out:
        if pick is None or item.get("uid") in pick:
            item.update(done_at=None, done_uid=None, done_name=None)
    return out


def swap(crew: Iterable[Member], old_uid: Any, uid: int, name: Optional[str], now: datetime.datetime) -> list[Member]:
    """고른 한 사람 자리를 나로 바꾼 새 목록(담당 바꾸기 — 자리 · 나머지 그대로, 시작한 때 = 지금)."""
    out = copy.deepcopy(list(crew))
    for index, item in enumerate(out):
        if item.get("uid") == old_uid:
            out[index] = member(uid, name, to_iso(now))
    return out


def names(crew: Iterable[Member]) -> list[str]:
    """작업하는 사람 이름(시작한 차례 · 겹침 · 빈 이름 뺌)."""
    out: list[str] = []
    for item in crew:
        name = str(item.get("name") or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def done_names(crew: Iterable[Member]) -> list[str]:
    """완료한 사람 이름(완료 칸 — 대신 완료면 반장 이름, 겹침 · 빈 이름 뺌)."""
    out: list[str] = []
    for item in crew:
        name = str(item.get("done_name") or "").strip() if is_done(item) else ""
        if name and name not in out:
            out.append(name)
    return out


def name_line(people: Iterable[str], limit: int = NAME_LINE_LIMIT) -> str:
    """이름 줄 — 둘까지 이름, 나머지는 "외 n"("이시영 · 김재단 외 1"). 비면 빈 글."""
    people = [str(p).strip() for p in people if str(p or "").strip()]
    head = " · ".join(people[:limit])
    rest = len(people) - limit
    return f"{head} 외 {rest}" if rest > 0 else head


def late_join(action: str, seen: str, state: str, crew: list[Member], uid: Any) -> tuple[str, str, bool]:
    """넘김 판정(§7-3 ① · ②) — 화면이 본 상태와 서버 줄이 다를 때 누른 사람의 뜻대로 바꾼 (누름, 본 상태, 늦게 들어옴).

    * [작업 시작](``take`` · ``none``)인데 서버 줄이 작업 중이고 내가 목록에 없음 → ``join`` · ``need`` · True(Q16).
    * [같이 작업](``join``)인데 서버 줄이 비었음(그사이 모두 시작 취소) → ``take`` · ``none`` · False(판결 1, 글 없음).
    * 그 밖은 그대로.
    """
    if action == "take" and seen == "none" and state == MARK_STATE_NEED and crew and find(crew, uid) is None:
        return "join", "need", True
    if action == "join" and state == MARK_STATE_NONE:
        return "take", "none", False
    return action, seen, False


__all__ = [
    "NAME_LINE_LIMIT", "SHARE_DONE", "SHARE_HELD", "SHARE_NONE", "SHARE_VALUES", "crew_of", "done_names", "find", "finish",
    "finish_rest", "from_iso", "is_done", "join", "late_join", "leave", "member", "name_line", "names", "share_of", "summarize",
    "swap", "to_iso", "unfinish",
]
