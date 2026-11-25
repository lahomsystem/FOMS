"""도면 판 카드의 '작업하는 사람' 칸 — 여러 명이 같이 작업(설계서 2026-11-25 multi-holder §5 · §8-1 · §8-2 · §10 M2).

순수 계산 · 쿼리 0. 이름 줄("이시영 · 김재단 외 1")은 :func:`foms.services.production.mark_crew.name_line` 하나만 쓴다 — 화면(JS)은
여기서 만든 글을 그대로 그린다(이름 줄을 따로 짓지 않는다). 보는 사람마다 다른 줄(나 빼고 · 나 더하고 · 한 사람을 나로 바꾸고 ·
한 사람 빼고)도 여기서 미리 만든다. 판(:mod:`~foms.services.production.part_board`)은 이미 읽은 표시 줄로, 쓰기 응답 · 30초 받아
오기는 응답 표시(``mark``)의 ``holders`` 로 같은 함수(:func:`crew_view`)를 부른다 — 화면 셋이 같은 글을 받는다.

칸 소속(Q12): 파트 계정은 내 몫이 작업 중이면 '작업 필요' 칸, 내 몫을 완료했으면(도면은 "재단 1/2 완료"여도) '완료' 칸. 관리자 ·
반장 · 보기만은 줄 상태 그대로(작업 필요 = 모두, 완료 = 모두).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.production import mark_crew as mc
from foms.services.production.part_mark_notes import actor_name
from foms.services.production.part_mark_rules import MarkSnapshot, holder_rows

NBSP = " "
#: 받침으로 읽는 숫자(영 · 일 · 삼 · 육 · 칠 · 팔) — "외 1과" · "외 2와".
_FINAL_DIGITS = "013678"


def _has_final(name: str) -> bool:
    """마지막 글자에 받침이 있는지(한글 · 숫자 — 그 밖은 받침 있음으로 본다)."""
    last = name[-1]
    if "가" <= last <= "힣":
        return (ord(last) - ord("가")) % 28 != 0
    return last in _FINAL_DIGITS if last.isdigit() else True


def with_particle(name: str) -> str:
    """이름 + 과/와 — "이시영과" · "이시영 · 김재단 외 2와"(빈 이름은 빈 글)."""
    name = (name or "").strip()
    return f"{name}{'과' if _has_final(name) else '와'}" if name else ""


def _line(people: Iterable[Any]) -> str:
    return mc.name_line(str(p or "").strip() for p in people)


def _names(rows: list[dict[str, Any]]) -> list[str]:
    return [str(h.get("name") or "").strip() for h in rows]


def _done_names(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for h in rows:
        name = str(h.get("done_name") or "").strip() if h.get("done") else ""
        if name and name not in out:
            out.append(name)
    return out


def _share(rows: list[dict[str, Any]], viewer_id: Any) -> str:
    me = next((h for h in rows if viewer_id is not None and h.get("user_id") == viewer_id), None)
    if me is None:
        return mc.SHARE_NONE
    return mc.SHARE_DONE if me.get("done") else mc.SHARE_HELD


def _person(rows: list[dict[str, Any]], item: dict[str, Any], viewer_id: Any, viewer_name: str) -> dict[str, Any]:
    """고르기 창 한 사람 — 이름 · 완료 · 시작한 때 + 그 사람을 나로 바꾼 줄(``swap``) · 그 사람을 뺀 줄(``drop``)."""
    uid = item.get("user_id")
    swapped = [viewer_name if h.get("user_id") == uid else h.get("name") for h in rows]
    return {"uid": uid, "name": item.get("name") or "", "done": bool(item.get("done")), "at": item.get("picked_at"),
            "day": item.get("picked_day"), "swap": _line(swapped) if uid != viewer_id else "",
            "drop": _line(h.get("name") for h in rows if h.get("user_id") != uid)}


def crew_view(holders: Optional[list[dict[str, Any]]], viewer_id: Any, viewer_name: Optional[str]) -> dict[str, Any]:
    """보는 사람 한 명이 카드 · 창에 그릴 글 전부(이름 줄은 모두 :func:`~mark_crew.name_line`).

    Args:
        holders: 응답 꼴 목록(:func:`~foms.services.production.part_mark_rules.holder_rows` — ``user_id`` · ``name`` · ``done`` ·
            ``picked_at`` · ``picked_day`` · ``done_name``).
        viewer_id · viewer_name: 보는 사람(같이 작업 창 "→ 이시영 · 김재단 작업 중" · 담당 바꾸기 줄에 들어갈 이름).

    Returns:
        ``{n, d, me, who, head, left, others_left, done, with, tag, join, at, day, sig, people}`` — ``me`` = 내 몫(none · held ·
        done), ``who`` = 모두, ``head`` = 칸 글("이시영 · 김재단 외 1 작업 중" — "외 n" · "작업 중"은 안 쪼개짐), ``left`` = 아직인
        사람, ``others_left`` = 나 빼고 아직인 사람, ``done`` = 완료한 사람(대신 완료면 반장), ``with`` = 나 빼고 모두, ``tag`` = 내 작업
        꼬리("이시영과 같이" · 남이 완료했으면 "이시영 완료"), ``join`` = 나를 더한 줄, ``at`` · ``day`` = 첫 사람이 시작한 때,
        ``sig`` = 받아 오기 견줌 표지("31:1,44:0"), ``people`` = 사람마다(:func:`_person`).
    """
    rows = [h for h in (holders or []) if isinstance(h, dict)]
    viewer_name = (viewer_name or "").strip()
    me = _share(rows, viewer_id)
    who = _line(_names(rows))
    others = [h for h in rows if h.get("user_id") != viewer_id] if me != mc.SHARE_NONE else rows
    others_done = _done_names(others)
    with_line = _line(h.get("name") for h in others) if me != mc.SHARE_NONE else ""
    first = rows[0] if rows else {}
    return {
        "n": len(rows), "d": sum(1 for h in rows if h.get("done")), "me": me, "who": who,
        "head": f"{who.replace(' 외 ', ' 외' + NBSP)} 작업{NBSP}중" if who else "",
        "left": _line(h.get("name") for h in rows if not h.get("done")),
        "others_left": _line(h.get("name") for h in others if not h.get("done")),
        "done": _line(_done_names(rows)), "with": with_line,
        "tag": (f"{_line(others_done)} 완료" if others_done else f"{with_particle(with_line)} 같이" if with_line else "")
        if me == mc.SHARE_HELD else "",
        "join": _line([*_names(rows), viewer_name]) if me == mc.SHARE_NONE and viewer_name else who,
        "at": first.get("picked_at"), "day": first.get("picked_day"),
        "sig": ",".join(f"{h.get('user_id')}:{1 if h.get('done') else 0}" for h in rows),
        "people": [_person(rows, h, viewer_id, viewer_name) for h in rows],
    }


def attach_crew(mark: Any, viewer: Any) -> Any:
    """응답 · 받아 오기 표시 한 장에 보는 사람 몫 칸 ``crew`` 를 붙인다(같은 dict 를 고쳐 돌려준다 — 표시가 아니면 그대로)."""
    if isinstance(mark, dict) and isinstance(mark.get("holders"), list):
        mark["crew"] = crew_view(mark["holders"], getattr(viewer, "id", None), actor_name(viewer))
    return mark


def card_crew(snap: MarkSnapshot, state: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """카드 한 장의 내 몫 · 칸 소속 · 배지(판 :func:`~foms.services.production.part_board.build_card` 가 부른다).

    Args:
        snap: 그 장 · 그 파트 표시 모습(목록 포함).
        state: 카드 상태(none · need · basic · done · hand — 손 체크 포함).
        ctx: 판 맥락(``user_id`` · ``viewer_name`` · ``mine`` — 파트 계정인지).

    Returns:
        ``{crew, picked_by_me, done_by_me, taken_by_other, badge, in_need, in_done}`` — ``crew`` = :func:`crew_view`(사람이
        없으면 None), ``picked_by_me`` = 내 몫이 작업 중, ``done_by_me`` = 내 몫 완료(사람 없는 완료 · 기본은 끝낸 사람이 나).
    """
    me, mine = ctx["user_id"], ctx["mine"]
    rows = holder_rows(snap.crew)
    view = crew_view(rows, me, ctx.get("viewer_name")) if rows else None
    share = view["me"] if view else mc.SHARE_NONE
    held = share == mc.SHARE_HELD
    done_by_me = share == mc.SHARE_DONE or (not rows and me is not None and snap.done_by_user_id == me)
    finished = state in ("done", "basic")
    badge = None
    if state == "need":
        badge = "taken" if mine and share == mc.SHARE_NONE else "need"
    elif finished:
        badge = state
    return {
        "crew": view, "picked_by_me": held, "done_by_me": done_by_me,
        "taken_by_other": state == "need" and share == mc.SHARE_NONE,
        "badge": badge,
        "in_need": state == "need" and (held or not mine),
        "in_done": (finished and (done_by_me or not mine)) or (state == "hand" and not mine)
        or (state == "need" and mine and share == mc.SHARE_DONE),
    }


__all__ = ["NBSP", "attach_crew", "card_crew", "crew_view", "with_particle"]
