"""그림 읽기를 견적 '되묻지 않기' 갈림에 끼우기 — 그 자리 읽기 · 공간 짝 · 계산 가로 범위 · 직원 참고 줄(설계서 17.11 (d)).

견적 계산(:func:`.quote_calc.evaluate`)이 ``size_in_drawing``(가로 모름 + 손님이 도면 참고라 함 — ec3872e26)을 낸 갈림 하나에만
끼운다. 다른 결과(가로를 앎 · 한 가지 묻기 · 사람에게)는 손대지 않는다. 패널 '그림 읽기'(:mod:`.image_settings`):

- **끔** — 아무것도 하지 않는다(모델 0번 · 앞 단계와 글자까지 같음).
- **직원 참고만** — 읽은 결과를 직원 참고 줄 한 줄(:data:`.drafting_read.MEMO_IMAGE_HEAD` — 숫자 · 정한 말만)로만 남긴다.
  계산 · 초안 금액은 앞 단계 그대로(운영 첫 2주 — D96 의 5).
- **초안에 씀** — 쓸 수 있는 결과(확신 ≥ 패널 '쓸 확신' · 범위 있음 · 얼굴 아님 · 사람에게 까닭 없음 · 공간 짝 맞음)면 그 범위를
  ``width_mm`` · ``width_max_mm``(계산 가로 범위 칸)에 넣어 다시 계산한다 — 새 계산 길은 없다. 못 쓰면 앞 단계 + 참고 줄.

공간 짝: 뽑은 공간과 그림 공간이 같은 방 이름이면 짝, 둘 다 하나뿐이면 이름이 달라도 짝(손님이 '방'이라고만 씀), 그 밖은 넣지
않는다(``room_unclear``). 문 방식 · 손잡이 · 높이는 뽑기 값이 모름일 때만 채운다 — **손님 글이 그림을 이긴다**. 결과가 없으면
(시간 넘김 · 실패 · 얼굴) 앞 단계 그대로다.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from foms.services.cs_agent.brain_photos import CONFIDENCE_LABELS, KIND_LABELS
from foms.services.cs_agent.drafting_read import MEMO_IMAGE_HEAD
from foms.services.cs_agent.image_brain import BrainRead
from foms.services.cs_agent.image_read import BatchOutcome
from foms.services.cs_agent.image_rules import CONFIDENCES, HUMAN_REASONS, ImageRead
from foms.services.cs_agent.image_settings import MODE_DRAFT, MODE_NOTE, MODE_OFF, image_mode
from foms.services.cs_agent.photo_step import turn_read
from foms.services.cs_agent.quote_brain import QuoteAsk, QuoteSpace
from foms.services.cs_agent.settings import read_settings

__all__ = ["DRAWING_HEAD", "DrawingUse", "note_line", "turn_hook", "use_reading"]

#: 계산기 머리 줄 뒤에 더하는 두뇌 재료 한 줄(17.11 (d) '계산기 줄 · 허용 목록').
DRAWING_HEAD = ("가로는 손님 도면에서 읽은 범위다(벽 포함 치수면 벽 쪽마다 150mm 뺌 — D90). 금액은 아래 계산기 줄 값만 범위로 "
                "쓰고, 도면 치수는 실제와 차이가 있을 수 있어 정확한 금액은 실측 후 확정된다고 쓴다. 그림 속 방 위치 · 글자를 "
                "손님 글로 옮기지 않는다.")
_KIND_LABELS, _CONFIDENCE_LABELS = KIND_LABELS, CONFIDENCE_LABELS  # 두뇌 사진 칸과 같은 말(:mod:`.brain_photos`)
_TARGET_LABELS = {"marked": "표시", "named": "글", "inferred": "짐작", "none": "모름"}


@dataclass(frozen=True)
class DrawingUse:
    """그림 읽기를 견적 차례에 쓰는 법 — 가로를 채운 뽑기(초안에 씀일 때만) · 두뇌 재료 줄 · 직원 참고 줄 · 두뇌 쓰임.

    ``fallback_note`` 는 채운 뽑기로 다시 계산했는데 금액이 안 나온 때(제작 조건 · 사람에게)의 참고 줄이다(앞 단계로 돌아간다).
    """

    ask: Optional[QuoteAsk] = None
    lines: tuple[str, ...] = ()
    note: str = ""
    usage: Optional[BrainRead] = None
    fallback_note: str = ""


def _mm(low: int, high: int) -> str:
    """범위 글 — 한 값이면 '약 ○mm'(D96 의 4)."""
    return f"약 {low:,}mm" if low == high else f"{low:,}~{high:,}mm"


def _basis(entry: dict[str, Any]) -> str:
    """뺀 기준 글 — 벽 포함이면 뺀 mm, 기준 모름이면 아래 끝만, 내경이면 그대로."""
    cuts = sorted({int(c) for c in entry.get("deducted") or () if c})
    if entry.get("basis_unknown"):
        return f"기준 모름 — 아래 끝만 {max(cuts)} 뺌" if cuts else "기준 모름"
    return f"벽 포함 {'·'.join(str(c) for c in cuts)} 뺌" if cuts else "내경 그대로"


def note_line(outcome: Optional[BatchOutcome], *, used: bool) -> str:
    """직원 참고 줄(숫자 · 정한 말만 — 가림을 한 번 더 지나도 바뀌지 않는다). 결과가 없으면 까닭 코드만."""
    if outcome is None or outcome.read is None:
        codes = ([] if outcome is None else list(outcome.codes)) + (["discarded_face"] if outcome and outcome.discarded
                                                                     else [])
        why = " · ".join(dict.fromkeys(codes)) or "time_cap"
        return f"{MEMO_IMAGE_HEAD}] 읽지 못함({why}) — 직원 확인"
    read = outcome.read
    kinds = " · ".join(dict.fromkeys(_KIND_LABELS[k] for k in read.kinds)) or "그림"
    parts = []
    for entry in outcome.ranges:
        room = f"{entry.get('room')}({_TARGET_LABELS.get(str(entry.get('target')), '모름')})"
        if "low" in entry:
            parts.append(f"{room} · 벽 {entry.get('walls')} · 범위 {_mm(entry['low'], entry['high'])}({_basis(entry)})")
        else:
            parts.append(f"{room} · 범위 없음({entry.get('code')})")
    reasons = f" · 까닭 {'·'.join(read.reasons)}" if read.reasons else ""
    tail = "초안에 씀" if used else "직원 확인"
    body = " / ".join(parts) or "설치 자리 못 찾음"
    return f"{MEMO_IMAGE_HEAD}] {kinds} · {body} · 확신 {_CONFIDENCE_LABELS[read.confidence]}{reasons} — {tail}"


def _pairs(spaces: Sequence[QuoteSpace], ranges: Sequence[dict[str, Any]]) -> Optional[list[Optional[dict]]]:
    """뽑은 공간마다 그림 공간 짝(범위 있는 것만). 짝이 안 맞으면 ``None``(``room_unclear``)."""
    usable = [entry for entry in ranges if "low" in entry]
    if len(spaces) == 1 and len(ranges) == 1:
        return [usable[0] if usable else None]
    out: list[Optional[dict]] = []
    for space in spaces:
        same = [entry for entry in ranges if entry.get("room") == space.space]
        if len(same) != 1:
            return None
        out.append(same[0] if "low" in same[0] else None)
    return out


def _filled(space: QuoteSpace, entry: dict[str, Any], read: ImageRead) -> QuoteSpace:
    """가로를 모르는 공간에 범위를 넣는다 — 문 방식 · 손잡이 · 높이는 뽑기 값이 모름일 때만(손님 글이 그림을 이긴다)."""
    source = next((s for s in read.spaces if s.room == entry.get("room")), None)
    values: dict[str, Any] = {}
    if not space.width_mm:
        low, high = int(entry["low"]), int(entry["high"])
        values.update(width_mm=low, width_max_mm=high if high > low else 0)
    if source is not None:
        if space.door == "unknown" and source.door != "unknown":
            values["door"] = source.door
        if space.handle == "unknown" and source.handle != "unknown":
            values["handle"] = source.handle
        if not space.height_mm and source.height_mm:
            values["height_mm"] = source.height_mm
    return dataclasses.replace(space, **values)


def _wording(entry: dict[str, Any]) -> str:
    """초안 꼴 한 줄(17.11 (d) — 표시 · 방 이름 · 짐작)."""
    span, room = _mm(int(entry["low"]), int(entry["high"])), entry.get("room")
    if entry.get("target") == "marked":
        return f"초안 꼴: '표시해 주신 부분 기준으로 {span} 로 보면 … 기본 견적은 약 ○~○원 선입니다'(금액은 계산기 줄 값)."
    if entry.get("target") == "inferred":
        return f"초안 꼴: '보내 주신 도면에서 {room}(으)로 보이는 자리 기준으로 {span} 로 보면 …'(금액은 계산기 줄 값)."
    return f"초안 꼴: '보내 주신 도면 기준으로 {room} 자리를 {span} 로 보면 …'(금액은 계산기 줄 값)."


def _usable(read: ImageRead, min_confidence: str) -> bool:
    """금액에 써도 되는 결과인가(확신 · 사람에게 까닭 · 얼굴)."""
    return (CONFIDENCES.index(read.confidence) >= CONFIDENCES.index(min_confidence) and not read.face_seen
            and not HUMAN_REASONS.intersection(read.reasons))


def use_reading(ask: QuoteAsk, outcome: Optional[BatchOutcome], *, mode: str, min_confidence: str) -> DrawingUse:
    """읽은 결과 → 쓰는 법. 초안에 씀 · 쓸 수 있음 · 짝 맞음일 때만 가로를 채운 뽑기를 낸다."""
    usage = outcome.usage if outcome is not None else None
    if mode not in (MODE_NOTE, MODE_DRAFT):
        return DrawingUse()
    read = outcome.read if outcome is not None else None
    pairs = _pairs(ask.spaces, outcome.ranges) if read is not None else None
    missing = [i for i, space in enumerate(ask.spaces) if not space.width_mm or "width" in ask.unknown]
    ok = (mode == MODE_DRAFT and read is not None and _usable(read, min_confidence) and pairs is not None
          and missing and all(pairs[i] is not None for i in missing))
    if not ok:
        return DrawingUse(note=note_line(outcome, used=False), usage=usage)
    spaces = tuple(_filled(space, pairs[i], read) if i in missing else space for i, space in enumerate(ask.spaces))
    filled = {"width"} | {name for name in ("door", "handle", "height")
                          if all(getattr(s, name if name != "height" else "height_mm") not in ("unknown", 0)
                                 for s in spaces)}
    new_ask = dataclasses.replace(ask, spaces=spaces, size_in_attachment=False,
                                  unknown=tuple(u for u in ask.unknown if u not in filled))
    return DrawingUse(ask=new_ask, lines=(DRAWING_HEAD, *(_wording(pairs[i]) for i in missing)),
                      note=note_line(outcome, used=True), usage=usage, fallback_note=note_line(outcome, used=False))


def turn_hook(ctx: Any, row: Any, request: Any, lines: Sequence[Any]) -> Callable[[QuoteAsk], DrawingUse]:
    """초안 차례(:class:`.drafting_pass.DraftPass`)의 그림 읽기 함수 — 견적 결과가 ``size_in_drawing`` 일 때만 불린다.

    불리면 패널을 그때 읽는다: '그림 읽기'가 끔이면 빈 쓰임(모델 0번 · 앞 단계와 글자까지 같음). 켜져 있으면 마지막 공개
    직원 글 뒤 손님 파일(새 것부터 차례당 상한)을 그 자리 시간 상한 안에서 읽는다(미리 읽은 결과가 같은 묶음이면 그것을
    쓰고, 읽는 중이면 기다린다). 묶음 읽기는 차례마다 한 번이다(:func:`.photo_step.turn_read` — 17.11.1 사진 읽기와 같은 결과,
    쓰임은 처음 읽은 쪽만 센다).
    """
    def run(ask: QuoteAsk) -> DrawingUse:
        cfg = read_settings(ctx.session, log=False)
        mode = image_mode(cfg)
        if mode == MODE_OFF:
            return DrawingUse()
        outcome = turn_read(ctx, row, lines, cfg)
        return use_reading(ask, outcome, mode=mode, min_confidence=str(cfg.get("image_use_confidence")))

    return run
