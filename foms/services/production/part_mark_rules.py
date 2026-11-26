"""생산 파트 표시의 상태 전이 표 — 순수 계산(설계서 §15.4 '바뀌는 길' · '경합 409' · 2026-11-25 multi-holder §5 · §7-3).

DB · commit · 요청 없이 표시 줄 하나의 지금 모습(:class:`MarkSnapshot` — 작업하는 사람 목록 포함)과 누름(action · seen)만 보고
'바꾼다 / 이미 그렇다(멱등) / 경합 / 거절 / 잘못된 요청' 을 정한다. 쓰기 API 가 한 장 쓰기와 일괄 기본에서 같이 쓴다.

한 도면 · 한 파트를 여러 명이 같이 작업한다(사장님 2026-11-25). 줄 안의 목록(:mod:`~foms.services.production.mark_crew`)에서 한
사람만 넣고 빼고, 줄의 상태 칸은 목록의 요약이다 — 모두 [완료]를 눌러야 DONE, 한 명이라도 아직이면 NEED("재단 1/2 완료").

========  ==========================  ==============================================
action    지금 → 새                     조건
========  ==========================  ==============================================
take      NONE → NEED[나]              [작업 시작]. 서버 줄이 NEED[남…]이면 join 으로 넘김(Q16)
join      NEED[남…] → NEED[남…, 나]   [같이 작업]. 모두 완료면 409 ``JOIN_DONE``, 그사이 비었으면 take 로(판결 1)
basic     NONE → BASIC                 재단만(API 가 400 으로 막는다) — 지금 그대로
done      내 몫 완료                   모두 완료면 DONE. 반장 · 관리자가 남의 줄 = 남은 사람 몫을 한 번에(Q15)
undo      내 몫 완료 끔 / BASIC → NONE  남의 몫은 반장 · 관리자만(파트 계정 403 ``UNDO_NOT_MINE`` — Q3)
release   나 빼기                      [시작 취소]. 완료 누른 뒤 409 ``RELEASE_AFTER_DONE``(Q7), 남은 사람 모두 완료면 DONE(Q6)
remove    고른 사람 빼기                [{이름} 시작 취소] — 반장 · 관리자만(Q5)
takeover  고른 한 사람 → 나            [담당 바꾸기] — 완료 누른 사람은 못 고름(``TARGET_DONE``)
check     NONE → DONE[나] / 대신 완료  PC [완료 처리] 한 요청(판결 2) — 반장 · 관리자만(API 가 403)
========  ==========================  ==============================================

같은 사람이 같은 결과를 다시 보내면(연결이 얼어 두 번 누름) 성공으로 친다. ``seen_by``(옛 화면이 본 담당 id)는 한 명일 때만 담당까지
견주고, ``seen_me``(새 화면이 본 내 몫)를 보내면 내 몫까지 견준다. 담당이 바뀐 기록 칸 ``handed_from_name`` · ``handed_at`` 은 담당
바꾸기가 쓰고, 시작 취소 · NONE 이 지운다(§6-4). 누름 판정 차례는 :mod:`~foms.services.production.part_mark_decide`(500줄 래칫).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional

from foms.services.datetime_kst import format_datetime_kst, parse_datetime_utc
from foms.services.production import mark_crew as mc
from foms.services.production.part_constants import (
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    MARK_STATE_NONE,
)

ACTION_TAKE = "take"
ACTION_BASIC = "basic"
ACTION_DONE = "done"
ACTION_UNDO = "undo"
ACTION_RELEASE = "release"
ACTION_TAKEOVER = "takeover"
ACTION_JOIN = "join"
ACTION_REMOVE = "remove"
ACTION_CHECK = "check"
MARK_ACTIONS: tuple[str, ...] = (ACTION_TAKE, ACTION_BASIC, ACTION_DONE, ACTION_UNDO, ACTION_RELEASE, ACTION_TAKEOVER,
                                 ACTION_JOIN, ACTION_REMOVE, ACTION_CHECK)
#: 3판 뒤 생긴 누름 — 경합 글은 새 글을 쓴다.
NEW_ACTIONS: tuple[str, ...] = (ACTION_RELEASE, ACTION_TAKEOVER, ACTION_REMOVE)

#: 화면이 본 상태(``seen``) — 표 상태의 작은 글자 꼴. 줄이 없으면 ``none``.
SEEN_VALUES: tuple[str, ...] = ("none", "need", "basic", "done")

#: 결정 종류.
DECISION_APPLY = "apply"
DECISION_SAME = "same"
DECISION_CONFLICT = "conflict"
DECISION_INVALID = "invalid"
#: 권한 거절 403(남의 시작 취소 · 남의 몫 되돌리기 · 남의 장 시작 취소) — 코드는 :attr:`MarkDecision.code`.
DECISION_FORBIDDEN = "forbidden"
#: 그 밖 거절(409 ``JOIN_DONE`` · ``RELEASE_AFTER_DONE`` · ``TARGET_DONE`` · ``TARGET_GONE``, 400 ``TARGET_REQUIRED``).
DECISION_REFUSE = "refuse"

STALE_MESSAGE = "그사이 다른 사람이 바꿨어요. [다시 받기]를 눌러 주세요."
#: 새 누름(시작 취소 · 담당 바꾸기)의 경합 글(§9 '경합').
NEW_STALE_MESSAGE = "그사이 담당이 바뀌었어요. [다시 받기]를 눌러 주세요."
RELEASED_MESSAGE = "그사이 시작이 취소됐어요. 지금은 담당 미정이에요."
RELEASE_NOT_HOLDER_MESSAGE = "내가 시작한 도면만 시작을 취소할 수 있어요. 직접 하려면 [담당 바꾸기]를 눌러 주세요."
JOIN_DONE_MESSAGE = "이미 완료된 도면이에요. 다시 해야 하면 완료한 사람이 [{label} 완료 취소]를 먼저 눌러 주세요."
RELEASE_AFTER_DONE_MESSAGE = "[{label} 완료]를 누른 도면은 시작을 취소할 수 없어요. 먼저 [{label} 완료 취소]를 눌러 주세요."
REMOVE_FORBIDDEN_MESSAGE = "다른 사람의 시작을 취소하는 것은 반장이나 관리자만 할 수 있어요."
TARGET_REQUIRED_SWAP = "누구와 바꿀지 골라 주세요."
TARGET_REQUIRED_REMOVE = "누구의 시작을 취소할지 골라 주세요."
TARGET_DONE_MESSAGE = "완료를 누른 사람은 바꿀 수 없어요."
#: 거절 코드(§7-4).
JOIN_DONE, RELEASE_AFTER_DONE, UNDO_NOT_MINE = "JOIN_DONE", "RELEASE_AFTER_DONE", "UNDO_NOT_MINE"
REMOVE_FORBIDDEN, RELEASE_NOT_HOLDER = "REMOVE_FORBIDDEN", "RELEASE_NOT_HOLDER"
TARGET_REQUIRED, TARGET_DONE, TARGET_GONE = "TARGET_REQUIRED", "TARGET_DONE", "TARGET_GONE"

#: 표 ``production_part_marks`` 의 쓰는 칸(``id`` 제외) — 쓰기 API 가 표마다 한 번에 INSERT/UPDATE 할 때 쓴다.
MARK_COLUMNS: tuple[str, ...] = (
    "order_id", "drawing_key", "sheet_id", "part", "state",
    "picked_by_user_id", "picked_by_name", "picked_at",
    "done_by_user_id", "done_by_name", "done_at",
    "updated_by_user_id", "updated_at",
    "handed_from_name", "handed_at",
    "holders",
)

#: ``seen_by`` 를 안 보낸 요청(지금 화면) — 담당은 견주지 않는다(상태만, 2026-11-13 판 그대로).
SEEN_BY_UNSET: Any = object()


@dataclass(frozen=True)
class MarkSnapshot:
    """표시 줄 하나의 지금 모습(줄이 없으면 :meth:`from_row` 가 NONE 빈 모습을 만든다). 한 명짜리 칸은 목록의 요약이다."""

    state: str = MARK_STATE_NONE
    picked_by_user_id: Optional[int] = None
    picked_by_name: Optional[str] = None
    done_by_user_id: Optional[int] = None
    done_by_name: Optional[str] = None
    updated_by_user_id: Optional[int] = None
    picked_at: Optional[datetime.datetime] = None
    handed_from_name: Optional[str] = None
    handed_at: Optional[datetime.datetime] = None
    #: 작업하는 사람 목록(:func:`~foms.services.production.mark_crew.crew_of` — 읽기 정규화 뒤).
    crew: tuple[dict[str, Any], ...] = field(default=(), compare=False, hash=False)

    @classmethod
    def from_row(cls, row: Any) -> "MarkSnapshot":
        """``ProductionPartMark`` 줄(또는 같은 모양 · None · 이미 만든 모습) → 모습. 3판 칸 · 목록 칸은 없어도 된다."""
        if row is None:
            return cls()
        if isinstance(row, MarkSnapshot):
            return row
        return cls(
            state=str(row.state or MARK_STATE_NONE), picked_by_user_id=row.picked_by_user_id,
            picked_by_name=row.picked_by_name, done_by_user_id=row.done_by_user_id,
            done_by_name=row.done_by_name, updated_by_user_id=row.updated_by_user_id,
            picked_at=getattr(row, "picked_at", None), handed_from_name=getattr(row, "handed_from_name", None),
            handed_at=getattr(row, "handed_at", None), crew=tuple(mc.crew_of(row)),
        )

    @property
    def seen_key(self) -> str:
        """화면 글자 꼴(none · need · basic · done)."""
        return self.state.lower() if self.state in (MARK_STATE_NEED, MARK_STATE_BASIC, MARK_STATE_DONE) else "none"


@dataclass(frozen=True)
class MarkDecision:
    """누름 하나의 결정. ``target`` 은 apply · same 일 때 새 상태, ``override`` 는 반장 · 관리자가 남의 몫을 바꿀 때.

    ``action`` = 넘김 뒤 실제로 쓰는 누름, ``crew`` = 쓸 새 목록(apply), ``joined_late`` · ``notice`` = Q16 넘김,
    ``proxied`` = PC [완료 처리]가 대신 완료로 감, ``target_uid`` · ``target_name`` = 바꾸기 · 시작 취소 대상,
    ``code`` · ``status`` = 거절 코드 · 상태.
    """

    kind: str
    target: Optional[str] = None
    override: bool = False
    message: str = ""
    action: str = ""
    crew: Optional[tuple[dict[str, Any], ...]] = field(default=None, compare=False, hash=False)
    code: str = ""
    status: int = 0
    joined_late: bool = False
    notice: str = ""
    proxied: bool = False
    target_uid: Optional[int] = None
    target_name: str = ""


def action_target(action: str, seen: str) -> Optional[str]:
    """누름 + 화면이 본 상태 → 화면이 기대하는 새 상태. 표에 없는 짝이면 None(잘못된 요청).

    여러 명이면 실제 새 상태는 목록이 정한다(:func:`decide_mark`) — 여기 값은 짝이 맞는지와 멱등 판정용이다.

    Args:
        action: :data:`MARK_ACTIONS` 중 하나.
        seen: 화면이 본 상태(none · need · basic · done).

    Returns:
        새 표 상태(NEED · BASIC · DONE · NONE) 또는 None.
    """
    table = {
        (ACTION_TAKE, "none"): MARK_STATE_NEED,
        (ACTION_BASIC, "none"): MARK_STATE_BASIC,
        (ACTION_DONE, "need"): MARK_STATE_DONE,
        (ACTION_UNDO, "done"): MARK_STATE_NEED,
        (ACTION_UNDO, "need"): MARK_STATE_NEED,
        (ACTION_UNDO, "basic"): MARK_STATE_NONE,
        (ACTION_RELEASE, "need"): MARK_STATE_NONE,
        (ACTION_TAKEOVER, "need"): MARK_STATE_NEED,
        (ACTION_JOIN, "need"): MARK_STATE_NEED,
        (ACTION_REMOVE, "need"): MARK_STATE_NEED,
        (ACTION_CHECK, "none"): MARK_STATE_DONE,
        (ACTION_CHECK, "need"): MARK_STATE_DONE,
    }
    return table.get((action, seen))


def _subject(name: str) -> str:
    """이름 뒤 토씨 — 마지막 글자에 받침이 있으면 '이', 없으면 '가'(한글이 아니면 '이')."""
    last = name[-1]
    if "가" <= last <= "힣":
        return "이" if (ord(last) - ord("가")) % 28 else "가"
    return "이"


def subject_particle(name: str) -> str:
    """이름 + 이/가 — 다른 모듈(막힘 글)도 같은 토씨 규칙을 쓴다. 빈 이름은 빈 글."""
    name = (name or "").strip()
    return f"{name}{_subject(name)}" if name else ""


def toward_particle(name: str) -> str:
    """이름 + 으로/로 — 받침이 없거나 ㄹ 받침이면 '로', 그 밖 받침은 '으로'(한글이 아니면 '으로')."""
    last = name[-1]
    if "가" <= last <= "힣":
        final = (ord(last) - ord("가")) % 28
        return f"{name}로" if final in (0, 8) else f"{name}으로"
    return f"{name}으로"


def crew_line(snapshot: MarkSnapshot) -> str:
    """문장 속 작업하는 사람 이름("이시영 · 김재단 외 1명") — 목록이 비면 한 명짜리 칸. 경합 · 넘김 글이 쓴다."""
    return mc.name_sentence(mc.names(snapshot.crew) or [snapshot.picked_by_name or ""])


def done_line(snapshot: MarkSnapshot) -> str:
    """문장 속 완료한 사람 이름 — 목록이 비면(사람 없는 완료) 한 명짜리 칸."""
    return mc.name_sentence(mc.done_names(snapshot.crew) or [snapshot.done_by_name or ""])


def took_first_message(line: str) -> str:
    """"이시영이 먼저 시작했어요." — Q16 넘김 글 · 경합 글 · 일괄 기본 건너뜀 글(사장님 답 원문)."""
    return f"{subject_particle(line)} 먼저 시작했어요." if line else "다른 사람이 먼저 시작했어요."


def conflict_message(snapshot: MarkSnapshot, action: str = "") -> str:
    """경합 409 글 — 지금 작업하는 사람 · 완료한 사람 이름을 넣은 해요체 한 문장(이름 줄은 둘까지 + "외 n").

    [되돌리기]의 경합(둘 다 완료한 줄을 한 명이 먼저 되돌린 뒤 낡은 화면이 누름 · 1/2 완료 화면인데 그사이 모두 완료)은 이름 글이 누른
    본인을 넣거나 '시작'이 아니라 틀리므로 지금 글 :data:`STALE_MESSAGE`(11-25 검토 4).

    Args:
        snapshot: 서버의 지금 모습.
        action: 누름(넘김 뒤 — 되돌리기면 이름 글 대신 지금 글).

    Returns:
        "박재단이 먼저 시작했어요." 같은 글. 이름을 모르면 두루 쓰는 글.
    """
    if action == ACTION_UNDO and snapshot.state in (MARK_STATE_NEED, MARK_STATE_DONE):
        return STALE_MESSAGE
    if snapshot.state == MARK_STATE_NEED:
        return took_first_message(crew_line(snapshot))
    if snapshot.state == MARK_STATE_DONE:
        name, verb = done_line(snapshot), "먼저 완료했어요"
    elif snapshot.state == MARK_STATE_BASIC:
        name, verb = (snapshot.done_by_name or "").strip(), "먼저 기본으로 했어요"
    else:
        return STALE_MESSAGE
    return f"{subject_particle(name)} {verb}" if name else f"다른 사람이 {verb}"


def new_action_conflict_message(snapshot: MarkSnapshot) -> str:
    """시작 취소 · 담당 바꾸기의 경합 글 — 서버 지금 모습으로(§9 '경합')."""
    if snapshot.state == MARK_STATE_NONE:
        return RELEASED_MESSAGE
    if snapshot.state == MARK_STATE_DONE and done_line(snapshot):
        return f"그사이 {subject_particle(done_line(snapshot))} 완료했어요. 더 할 일은 없어요."
    name = (snapshot.done_by_name or "").strip()
    if snapshot.state == MARK_STATE_BASIC and name:
        return f"그사이 {subject_particle(name)} 기본으로 했어요. 더 할 일은 없어요."
    return NEW_STALE_MESSAGE


def holder_changed_message(snapshot: MarkSnapshot) -> str:
    """화면이 본 담당과 지금 담당이 다를 때(담당 바꾸기 뒤의 늦은 화면)."""
    name = (snapshot.picked_by_name or "").strip()
    if not name:
        return NEW_STALE_MESSAGE
    return f"그사이 {toward_particle(name)} 담당이 바뀌었어요. 이 장은 이제 {subject_particle(name)} 해요."


def undo_not_mine_message(line: str) -> str:
    """파트 계정이 남의 완료를 되돌릴 때(403 ``UNDO_NOT_MINE`` — Q3)."""
    if not line:
        return "내가 완료한 것만 되돌릴 수 있어요."
    return f"내가 완료한 것만 되돌릴 수 있어요. {subject_particle(line)} 완료한 것은 {line}에게 말해 주세요."


def target_gone_message(name: str) -> str:
    """고른 사람이 그사이 빠졌을 때(409 ``TARGET_GONE``)."""
    who = (name or "").strip() or "그 사람"
    return f"그사이 {who}의 시작이 취소됐어요. [다시 받기]를 눌러 주세요."


def default_crew(row: Any, action: str, target: str, *, actor_id: Optional[int], actor_name: Optional[str],
                 now: datetime.datetime) -> list[dict[str, Any]]:
    """결정 없이 쓰는 곳(풀어 쓰기 · 일괄 기본)의 새 목록 — 완료는 남은 사람 몫을 한 번에, 기본은 빈 목록, 그 밖 그대로."""
    crew = mc.crew_of(row)
    if target == MARK_STATE_DONE and action in (ACTION_DONE, ACTION_CHECK):
        return mc.finish_rest(crew, by_uid=actor_id, by_name=actor_name, now=now)
    if target in (MARK_STATE_BASIC, MARK_STATE_NONE):
        return []
    return crew


def _write_summary(view: Any, crew: list[dict[str, Any]], target: str, actor_id: int, actor_name: Optional[str],
                   now: datetime.datetime) -> None:
    """요약 칸을 목록에서 다시 계산한다. 빈 목록(사람 없는 줄)은 지금 규칙 — NONE 은 비움, BASIC · DONE 은 끝낸 사람 = 나."""
    summary = mc.summarize(crew)
    if summary is not None:
        for name, value in summary.items():
            setattr(view, name, value)
        return
    if target == MARK_STATE_NONE:
        view.picked_by_user_id, view.picked_by_name, view.picked_at = None, None, None
    if target in (MARK_STATE_BASIC, MARK_STATE_DONE):
        view.done_by_user_id, view.done_by_name, view.done_at = actor_id, actor_name, now
    else:
        view.done_by_user_id, view.done_by_name, view.done_at = None, None, None
    view.state = target


def next_mark_values(row: Any, *, order_id: int, drawing_key: str, part: str, sheet_id: Optional[str], target: str,
                     actor_id: int, actor_name: Optional[str], now: datetime.datetime, action: str = "",
                     decision: Optional[MarkDecision] = None) -> dict[str, Any]:
    """표시 줄 하나의 새 칸 값 전부(줄은 건드리지 않는다 — 쓰기는 부르는 쪽이 표마다 한 번에 한다).

    목록 = 결정의 새 목록(없으면 :func:`default_crew`), 요약 칸 = 목록의 요약(:func:`_write_summary`). 이름은 스냅샷이다.
    바뀐 기록 칸: 담당 바꾸기 = 넘겨준 사람 · 지금, [작업 시작] · 시작 취소 · NONE = 비움, 그 밖(같이 작업 · 완료 · 되돌리기) 그대로.

    Args:
        row: 지금 줄(없으면 None — 새 줄).
        order_id · drawing_key · part: 자리.
        sheet_id: 지금 확정 도면 항목의 시트 신원(표시할 때의 스냅샷 — 바뀐 도면 짝짓기).
        target: 새 표 상태.
        actor_id · actor_name: 누른 사람.
        now: 쓰는 시각(UTC naive).
        action: 실제로 쓰는 누름(넘김 뒤).
        decision: :func:`decide_mark` 결정(목록 · 바꾸기 대상).

    Returns:
        :data:`MARK_COLUMNS` 칸 이름 → 값.
    """
    view = SimpleNamespace(**{column: getattr(row, column, None) if row is not None else None for column in MARK_COLUMNS})
    view.order_id, view.drawing_key, view.part, view.sheet_id = order_id, drawing_key, part, sheet_id
    if decision is not None and decision.crew is not None:
        crew = [dict(m) for m in decision.crew]
    else:
        crew = default_crew(row, action, target, actor_id=actor_id, actor_name=actor_name, now=now)
    _write_summary(view, crew, target, actor_id, actor_name, now)
    if action == ACTION_TAKEOVER:
        handed = decision.target_name if decision is not None and decision.target_name else getattr(row, "picked_by_name", None)
        view.handed_from_name, view.handed_at = handed, now
    elif action in (ACTION_TAKE, ACTION_RELEASE, ACTION_REMOVE) or view.state == MARK_STATE_NONE:
        view.handed_from_name, view.handed_at = None, None
    view.holders = crew
    view.updated_by_user_id = actor_id
    view.updated_at = now
    return {column: getattr(view, column) for column in MARK_COLUMNS}


def _utc_iso(value: Optional[datetime.datetime]) -> Optional[str]:
    """DB UTC naive 시각 → 시간대가 붙은 ISO 글(화면이 KST 로 바꾼다)."""
    aware = parse_datetime_utc(value) if value is not None else None
    return aware.isoformat() if aware is not None else None


def holder_rows(crew: Any) -> list[dict[str, Any]]:
    """응답에 싣는 목록 ``[{user_id, name, done, picked_at, picked_day, done_at, done_name}]``(시작한 차례)."""
    out = []
    for item in crew:
        at = item.get("at")
        out.append({"user_id": item.get("uid"), "name": item.get("name"), "done": mc.is_done(item), "picked_at": at,
                    "picked_day": format_datetime_kst(at, "%Y-%m-%d") if at else None, "done_at": item.get("done_at"),
                    "done_name": item.get("done_name") or None})
    return out


def mark_payload(row: Any) -> dict[str, Any]:
    """응답 · 경합 자료에 싣는 표시 한 장(화면이 그 카드만 서버 상태로 고친다).

    Args:
        row: ``ProductionPartMark`` 줄 · 같은 모양 · :class:`MarkSnapshot` 또는 None(안 봄 · 안 고름).

    Returns:
        ``{state, picked_by_name, done_by_name, picked_by_user_id, done_by_user_id, picked_at, picked_day,
        handed_from_name, handed_at, holders, holder_n, done_n}`` — state 는 작은 글자 꼴. 한 명짜리 칸은 목록의 요약 그대로
        (지금 화면 호환 — 첫 사람 · 가장 늦게 완료한 사람). ``holders`` = :func:`holder_rows`, ``holder_n`` · ``done_n`` = 사람 수 ·
        완료한 사람 수(2026-11-25 multi-holder §7-1).
    """
    snap = MarkSnapshot.from_row(row)
    holders = holder_rows(snap.crew)
    return {
        "state": snap.seen_key,
        "picked_by_name": snap.picked_by_name,
        "done_by_name": snap.done_by_name,
        "picked_by_user_id": snap.picked_by_user_id,
        "done_by_user_id": snap.done_by_user_id,
        "picked_at": _utc_iso(snap.picked_at),
        "picked_day": format_datetime_kst(snap.picked_at, "%Y-%m-%d") if snap.picked_at is not None else None,
        "handed_from_name": snap.handed_from_name,
        "handed_at": _utc_iso(snap.handed_at),
        "holders": holders,
        "holder_n": len(holders),
        "done_n": sum(1 for h in holders if h["done"]),
    }
