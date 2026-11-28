"""생산 현장 알람 — 알림 종류 이름과 화면 글(설계서 2026-11-28 생산 현장 알람 §2-3 · §4-2 · §6-2 약속 5, '사장님 답 2차').

순수 함수만(쿼리 0). 알림 표에는 사건을 적을 칸이 없어 **종류 이름**이 등급 · 사건을 싣는다 — 화면은 앞머리 셋
(``PRODUCTION_FLOOR_NEW`` · ``_STOP`` · ``_NOTICE``)만 보고 색 · 소리를 고른다. 긴급 둘(NEW · STOP)은 ``is_urgent`` 참, 띠(NOTICE)는 거짓.

글 규칙: 해요체, 누가 했는지를 맨 앞에. 긴급 본문은 두 줄(줄바꿈 ``\\n`` — 첫 줄 = 어느 주문 · 도면, 둘째 줄 = 무엇을 하면 되는지),
띠 본문은 한 줄. 담당 변경 둘은 사장님 답 2차 글 그대로다(원래 담당 본문은 한 줄 "… · 하던 작업은 멈춰 주세요.").
이/가 · 으로/로는 지금 있는 판정(:func:`~foms.services.production.part_mark_rules.subject_particle` · ``toward_particle``)을 쓴다.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from foms.services.production.factory_constants import factory_label
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, PRODUCTION_PART_LABELS
from foms.services.production.part_mark_rules import subject_particle, toward_particle

PREFIX = "PRODUCTION_FLOOR_"
#: SQL ``LIKE`` 꼴(밑줄은 한 글자 와일드카드라 풀어 쓴다) — ``Notification.notification_type.like(LIKE_PATTERN, escape=LIKE_ESCAPE)``.
#: 바인드 값 하나로 끝나게 글 이어 붙이기(``startswith``)를 쓰지 않는다(운영 드라이버가 이어 붙인 바인드에 형을 덧붙인다).
LIKE_ESCAPE = chr(92)
LIKE_PATTERN = PREFIX.replace("_", LIKE_ESCAPE + "_") + "%"
NEW_GIVEN = PREFIX + "NEW_GIVEN"
STOP_TAKEN = PREFIX + "STOP_TAKEN"
STOP_DRAWING = PREFIX + "STOP_DRAWING"
STOP_REVISING = PREFIX + "STOP_REVISING"
STOP_HOLD = PREFIX + "STOP_HOLD"
STOP_CANCELLED = PREFIX + "STOP_CANCELLED"
STOP_FACTORY = PREFIX + "STOP_FACTORY"
NOTICE_START_CANCELLED = PREFIX + "NOTICE_START_CANCELLED"
NOTICE_DONE_CANCELLED = PREFIX + "NOTICE_DONE_CANCELLED"
NOTICE_DRAWING = PREFIX + "NOTICE_DRAWING"
NOTICE_HOLD_RELEASED = PREFIX + "NOTICE_HOLD_RELEASED"
NOTICE_DATE = PREFIX + "NOTICE_DATE"
NOTICE_DEFECT = PREFIX + "NOTICE_DEFECT"
NOTICE_REWORK = PREFIX + "NOTICE_REWORK"
NOTICE_FIX_REJECTED = PREFIX + "NOTICE_FIX_REJECTED"
NOTICE_FIX_APPLIED = PREFIX + "NOTICE_FIX_APPLIED"
NOTICE_UNBLOCKED = PREFIX + "NOTICE_UNBLOCKED"
NOTICE_DUE_TODAY = PREFIX + "NOTICE_DUE_TODAY"

URGENT_TYPES: tuple[str, ...] = (NEW_GIVEN, STOP_TAKEN, STOP_DRAWING, STOP_REVISING, STOP_HOLD, STOP_CANCELLED, STOP_FACTORY)
NOTICE_TYPES: tuple[str, ...] = (
    NOTICE_START_CANCELLED, NOTICE_DONE_CANCELLED, NOTICE_DRAWING, NOTICE_HOLD_RELEASED, NOTICE_DATE, NOTICE_DEFECT,
    NOTICE_REWORK, NOTICE_FIX_REJECTED, NOTICE_FIX_APPLIED, NOTICE_UNBLOCKED, NOTICE_DUE_TODAY)
ALL_TYPES: tuple[str, ...] = URGENT_TYPES + NOTICE_TYPES

TITLE_MAX = 200
#: 여러 장을 합친 제목 꼬리("… — 도면 3장") 앞 글 — 60초 합치기가 이 앞머리로 같은 알람을 찾는다.
_MERGE_TAIL = " — 도면 "
_NUMBER_RE = re.compile(r"(\d+)번")
_MD_RE = re.compile(r"(\d{1,2})/(\d{1,2})")
_NOBODY = "담당자"


def is_urgent_type(ntype: Any) -> bool:
    """전체 화면 등급(새 일 · 멈춤)인지 — 띠 · 다른 종류는 False."""
    return str(ntype or "") in URGENT_TYPES


@dataclass(frozen=True)
class Scene:
    """글 재료 — 어느 주문(``when`` = "11/30 시공" · ``customer``) · 어느 도면(``numbers``) · 누가(``actor``) · 어느 파트(``part`` key)."""

    customer: str = ""
    when: str = ""
    numbers: tuple[int, ...] = ()
    actor: str = ""
    part: str = ""


def _cut(text: str, limit: int = TITLE_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _who(name: str) -> str:
    """이름 + 이/가("박반장이" · "한검수가") — 빈 이름은 "담당자가"."""
    return subject_particle((name or "").strip() or _NOBODY)


def numbers_text(numbers: Iterable[int]) -> str:
    """도면 번호 글 — "도면 2번" · "도면 1번 · 2번 · 4번"(없으면 빈 글)."""
    found = sorted({int(n) for n in numbers})
    return "도면 " + " · ".join(f"{n}번" for n in found) if found else ""


def numbers_in(message: Any) -> tuple[int, ...]:
    """알람 본문 첫 줄에 적힌 도면 번호(합칠 때 앞 알람의 번호를 읽는다 — 알림 표에 칸이 없다)."""
    first = str(message or "").split("\n", 1)[0]
    return tuple(sorted({int(n) for n in _NUMBER_RE.findall(first)}))


def merge_head(title: Any) -> str:
    """합치기 열쇠 — 제목에서 "— 도면 n장" 꼬리를 뗀 앞머리."""
    return str(title or "").split(_MERGE_TAIL, 1)[0]


def pulled_forward(detail: Any, today: datetime.date) -> Optional[bool]:
    """"12/2 → 11/30" 글에서 당겨졌는지(앞 날 > 뒤 날) — 해는 오늘과 가까운 쪽. 글을 못 풀면 None(§4-9 의 2)."""
    found = _MD_RE.findall(str(detail or ""))
    if len(found) != 2 or "→" not in str(detail):
        return None
    days = []
    for month, day in found:
        near = []
        for year in (today.year - 1, today.year, today.year + 1):
            try:
                near.append(datetime.date(year, int(month), int(day)))
            except ValueError:
                continue
        if not near:
            return None
        days.append(min(near, key=lambda d: abs((d - today).days)))
    return days[1] < days[0]


def _where(scene: Scene, *, when: bool = True, numbers: bool = True) -> str:
    """"11/30 시공 · 정하늘 · 도면 2번"(도면 칸과 같은 말 · 같은 순서 — 없는 조각은 뺀다)."""
    parts = [scene.when if when else "", scene.customer, numbers_text(scene.numbers) if numbers else ""]
    return " · ".join(p for p in parts if p)


def _band(scene: Scene, *tail: str, numbers: bool = True) -> str:
    """띠 본문 한 줄 — "정하늘 · 도면 2번"(+ 꼬리)."""
    return " · ".join(p for p in (_where(scene, when=False, numbers=numbers), *tail) if p)


def _sheets_tail(title: str, scene: Scene) -> str:
    return _cut(f"{title}{_MERGE_TAIL}{len(set(scene.numbers))}장" if len(set(scene.numbers)) > 1 else title)


def _part(scene: Scene) -> str:
    return PRODUCTION_PART_LABELS.get(scene.part, scene.part)


def given(scene: Scene) -> tuple[str, str]:
    """#1 받은 사람 — "박반장이 재단 담당을 당신으로 변경했어요"(여러 장이면 "— 도면 3장")."""
    title = _sheets_tail(f"{_who(scene.actor)} {_part(scene)} 담당을 당신으로 변경했어요", scene)
    body = _where(scene)
    return title, body if len(set(scene.numbers)) > 1 else f"{body}\n[확인]을 누르면 그 주문 도면 칸으로 가요."


def taken(scene: Scene, *, to_name: str, self_take: bool) -> tuple[str, str]:
    """#2 원래 담당 — 남에게 줌 "…담당을 오재단으로 변경했어요" · 스스로 가져감 "…담당을 가져갔어요"(사장님 답 2차 1 · 2)."""
    if self_take or not (to_name or "").strip():
        head = f"{_who(scene.actor)} {_part(scene)} 담당을 가져갔어요"
    else:
        head = f"{_who(scene.actor)} {_part(scene)} 담당을 {toward_particle(to_name.strip())} 변경했어요"
    return _sheets_tail(head, scene), " · ".join(p for p in (_where(scene), "하던 작업은 멈춰 주세요.") if p)


def stop_drawing(scene: Scene, *, drawing_team: bool = True) -> tuple[str, str]:
    """#5 작업 중인 도면이 새 도면으로 바뀜."""
    who = _who(f"도면팀 {scene.actor}".strip() if drawing_team else scene.actor)
    return "멈추세요 — 도면이 바뀌었어요", f"{_where(scene)}\n{who} 새 도면을 보냈어요. 새 도면을 보고 다시 시작해 주세요."


def stop_revising(scene: Scene, *, drawing_team: bool = True) -> tuple[str, str]:
    """#7 도면 수정 중 — 도면팀이 고치는 중이면 "고치고 있어요", 그 밖(공장 · 영업 수정 요청)은 "도면 수정을 요청했어요"."""
    if drawing_team:
        why = f"{_who(f'도면팀 {scene.actor}'.strip())} 고치고 있어요."
    else:
        why = f"{_who(scene.actor)} 도면 수정을 요청했어요."
    return "멈추세요 — 도면을 고치는 중이에요", f"{_where(scene)}\n{why} 새 도면이 오면 알려 드려요."


def stop_hold(scene: Scene, *, reason: str = "") -> tuple[str, str]:
    """#8 보류."""
    why = f"{_who(scene.actor)} 보류했어요." + (f" 사유: {reason.strip()}" if (reason or "").strip() else "")
    return "멈추세요 — 보류됐어요", f"{_where(scene, numbers=False)}\n{why}"


def stop_cancelled(scene: Scene, *, item: bool = False) -> tuple[str, str]:
    """#10 주문 취소 · 품목 취소(품목 취소도 주문 단위 — 설계서 §4-9 의 3)."""
    where = _where(scene, numbers=False)
    if item:
        return "멈추세요 — 품목이 취소됐어요", f"{where}\n어느 품목인지 반장에게 확인해 주세요."
    return "멈추세요 — 주문이 취소됐어요", f"{where}\n더 만들지 말고 반장에게 알려 주세요."


def stop_factory(scene: Scene, *, factory: Any) -> tuple[str, str]:
    """#11 다른 공장으로 옮겨짐."""
    label = factory_label(factory)
    return f"멈추세요 — {toward_particle(label)} 옮겨졌어요", f"{_where(scene)}\n{label}에서 작업하는 도면이에요."


def start_cancelled(scene: Scene) -> tuple[str, str]:
    """#3 반장이 내 시작을 취소함."""
    return _cut(f"{_who(scene.actor)} {_part(scene)} 시작을 취소했어요"), _band(scene)


def done_cancelled(scene: Scene) -> tuple[str, str]:
    """#4 내가 완료한 것을 반장 · 관리자가 완료 취소함."""
    return _cut(f"{_who(scene.actor)} {_part(scene)} 완료를 취소했어요 — 다시 봐 주세요"), _band(scene)


def notice_drawing(scene: Scene) -> tuple[str, str]:
    """#6 완료한 도면이 바뀜."""
    return "도면이 바뀌었어요 — 완료한 도면을 다시 봐 주세요", _band(scene)


def hold_released(scene: Scene) -> tuple[str, str]:
    """#9 보류 풀림."""
    return "보류가 풀렸어요 — 다시 작업하세요", _band(scene, numbers=False)


def date_changed(scene: Scene, *, detail: str, left_parts: Iterable[str] = ()) -> tuple[str, str]:
    """#12 시공일 임박 — "시공일이 당겨졌어요 — 12/2 → 11/30" · "정하늘 · 남은 공정: 조립 · 검수"."""
    labels = [PRODUCTION_PART_LABELS[key] for key in PRODUCTION_PART_KEYS if key in set(left_parts)]
    tail = "남은 공정: " + " · ".join(labels) if labels else ""
    title = "시공일이 당겨졌어요" + (f" — {detail.strip()}" if (detail or "").strip() else "")
    return _cut(title), _band(scene, tail, numbers=False)


def defect(scene: Scene, *, label: str = "") -> tuple[str, str]:
    """#13 불량 알림 — "박엣지가 불량을 알렸어요 — 파손" · "정하늘 · 11/30 시공"."""
    title = f"{_who(scene.actor)} 불량을 알렸어요" + (f" — {label.strip()}" if (label or "").strip() else "")
    return _cut(title), _band(scene, scene.when, numbers=False)


def rework(scene: Scene, *, sheets: int = 0, steps: Iterable[str] = ()) -> tuple[str, str]:
    """#14 수정 제작 — 도면이 있으면 "— 도면 2장", 도면 없는 주문이면 다시 할 칸 "— 조립 · 검수"."""
    labels = [PRODUCTION_PART_LABELS[key] for key in PRODUCTION_PART_KEYS if key in set(steps)]
    tail = f"도면 {sheets}장" if sheets else " · ".join(labels)
    title = f"{_who(scene.actor)} 수정 제작으로 되돌렸어요" + (f" — {tail}" if tail else "")
    return _cut(title), _band(scene, scene.when, numbers=False)


def fix_rejected(scene: Scene, *, reason: str = "") -> tuple[str, str]:
    """#15 도면 수정 요청 반려."""
    tail = f"사유: {reason.strip()}" if (reason or "").strip() else ""
    return "도면 수정 요청이 반려됐어요 — 그대로 작업하세요", _band(scene, tail)


def fix_applied(scene: Scene) -> tuple[str, str]:
    """#16 수정 요청 반영(고친 도면이 옴) — 이미 멈춰 있던 일이라 멈춤이 아니다."""
    return "새 도면이 왔어요 — 다시 시작할 수 있어요", _band(scene)


def unblocked(scene: Scene) -> tuple[str, str]:
    """#20 막힘만 풀림(안 누른 멈춤 알람이 닫힐 때만)."""
    return "도면 수정이 취소됐어요 — 다시 작업하세요", _band(scene)


def due_today(customers: Iterable[str]) -> tuple[str, str]:
    """#21 오늘 나갈 주문 — "오늘 나가는 주문 2건이 아직 안 끝났어요" · "정하늘 · 윤봄"."""
    names = [str(name or "").strip() or "-" for name in customers]
    return f"오늘 나가는 주문 {len(names)}건이 아직 안 끝났어요", " · ".join(names)
