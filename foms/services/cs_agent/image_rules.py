"""그림 읽기 규칙 — 구조화 출력 스키마 · 읽기 · 벽 범위(D90 · D96) · 벽 고르기 · 공간 짝 · 직원 참고 줄(순수 함수).

설계서 17.11 (c) · (d). 모델은 숫자 · 고른 값만 낸다 — 글 칸은 사진마다 가린 짧은 설명 두 칸(``summary`` ·
``about_question`` — 17.11.1 의 2 · D172, 가림 검사 0 이 아니면 그 칸만 비운다 — :mod:`.image_notes`)뿐이다. 단지명 · 동호수 ·
이름은 옮기지 않게 지시하고, 옮겼으면 그 칸이 비워진다. 범위 셈은 코드가 한다 — 모델은 '어느 기준 치수인가'(``basis``)와 '벽 끝이 벽에 닿았나'(``ends``)만
고른다:

- ``center_line``(벽 포함 · 중심선 — 실제 안쪽보다 넓게 적힘): 벽 쪽마다 :data:`WALL_SIDE_MM` 를 뺀다(양쪽 벽 = 300mm).
  한쪽이 트인 벽(``one_wall``)은 벽 쪽만 150, 양쪽 모두 트임(``no_wall``)은 빼지 않는다(D96 의 1 — 추천대로).
- ``inner``(내경 · 안목): 그대로.
- ``unknown``: 범위 아래 끝은 뺀 값, 위 끝은 그대로(두 기준을 다 덮음) + 까닭 ``basis_unknown``.
- 그다음 아래 끝은 10mm 내림 · 위 끝은 10mm 올림(30cm 제품 mm 올림 D78 은 계산기가 한다).

벽 고르기: 손님 표시(``target=marked``)가 있으면 표시한 벽만, 없으면 그 방의 쓸 수 있는 벽을 모두 합친 범위. 합친 범위의
위 끝 ÷ 아래 끝이 :data:`RATIO_LIMIT` 를 넘으면 쓰지 않는다(``wall_unclear``). 꼴 검사: 고른 값 밖 · 정수 아닌 mm · 100m
넘는 값 · 아래 끝 > 위 끝인 칸은 버리고, 큰 꼴이 틀리면 ``ValueError``(칸 이름만 — 모델 글은 싣지 않는다).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Optional, Sequence

from foms.services.cs_agent.image_notes import ImageNote, note_json, parse_notes
from foms.services.cs_agent.quote_brain import DOORS, HANDLES, SPACES

__all__ = [
    "BASES", "BLOCKERS", "CONFIDENCES", "ENDS", "FACE_CODES", "HUMAN_REASONS", "KINDS", "MARKS", "MOLDINGS",
    "PERSONAL", "RATIO_LIMIT", "REASONS", "ROOM_BASIS", "SIDES", "SOURCES", "TARGETS", "WALL_SIDE_MM", "ImageRead",
    "ReadSpace", "SpaceRange", "Wall", "image_schema", "read_result", "result_json", "space_range", "wall_range",
]

KINDS: tuple[str, ...] = ("floor_plan", "hand_sketch", "site_photo", "example_photo", "product_screen", "quote_screen",
                          "appliance_spec", "other")
ROOM_BASIS: tuple[str, ...] = ("label_on_plan", "customer_text", "customer_mark", "ensuite_bath", "dress_room_attached",
                               "largest_bedroom", "position_guess")
TARGETS: tuple[str, ...] = ("marked", "named", "inferred", "none")
MARKS: tuple[str, ...] = ("circle", "x_mark", "color_line", "arrow", "handwriting", "floor_tape")
SIDES: tuple[str, ...] = ("top", "bottom", "left", "right", "unknown")
BLOCKERS: tuple[str, ...] = ("window", "door", "closet_entrance", "pillar", "none")
SOURCES: tuple[str, ...] = ("written", "scaled", "handwritten")
BASES: tuple[str, ...] = ("center_line", "inner", "unknown")
#: 그 벽 길이의 두 끝이 벽에 닿았나 — 벽 쪽마다 150 을 뺀다(D96).
ENDS: dict[str, int] = {"both_walls": 2, "one_wall": 1, "no_wall": 0}
MOLDINGS: tuple[str, ...] = ("molding", "no_molding", "unknown")
CONFIDENCES: tuple[str, ...] = ("low", "medium", "high")  # 낮은 것부터(견주기 차례)
REASONS: tuple[str, ...] = ("no_dimensions", "wall_unclear", "room_unclear", "several_rooms", "scale_estimated",
                            "basis_unknown", "marks_conflict", "low_resolution", "cut_off", "not_furniture")
PERSONAL: tuple[str, ...] = ("none", "face", "person", "name", "phone", "address", "complex_name", "unit_number",
                             "car_plate", "document")
#: 모델이 보았다고 하면 결과를 버리는 종류(D57 — 거르기가 놓친 얼굴).
FACE_CODES = frozenset({"face", "person"})
#: 이 까닭이 있으면 금액에 쓰지 않는다(사람에게 — 17.11 (d)).
HUMAN_REASONS = frozenset({"wall_unclear", "room_unclear", "marks_conflict"})
WALL_SIDE_MM = 150  # D90 · D96 — 벽 포함 치수면 벽 쪽마다(처음 값 — 설정 drawing_dimension_rules 가 있으면 그 값, D116)
RATIO_LIMIT = Fraction(3, 2)
MAX_SPACES, MAX_WALLS, MAX_IMAGES, MAX_MM = 4, 3, 6, 100_000
_ROUND = 10


@dataclass(frozen=True)
class Wall:
    """후보 벽 하나 — 그림에서 읽은 그대로(줄이기 전)의 mm 범위와 치수 기준."""

    side: str
    usable: bool
    marked: bool
    blocked_by: tuple[str, ...]
    read_min_mm: int
    read_max_mm: int
    source: str
    basis: str
    ends: str


@dataclass(frozen=True)
class ReadSpace:
    """설치 자리 하나(방 이름 · 찾은 까닭 · 표시 · 벽 · 예시에서 본 문 방식 등)."""

    room: str
    room_basis: tuple[str, ...]
    target: str
    mark_kinds: tuple[str, ...]
    walls: tuple[Wall, ...]
    door: str = "unknown"
    handle: str = "unknown"
    molding: str = "unknown"
    height_mm: int = 0


@dataclass(frozen=True)
class ImageRead:
    """읽기 한 번의 결과(숫자 · 고른 값만)."""

    kinds: tuple[str, ...]
    is_drawing: bool
    spaces: tuple[ReadSpace, ...]
    confidence: str
    reasons: tuple[str, ...]
    personal_seen: tuple[str, ...]
    other_question: bool
    notes: tuple[ImageNote, ...] = ()  # 사진마다 종류 · 확신 · 가린 설명(17.11.1 — 옛 결과는 빈 튜플)

    @property
    def face_seen(self) -> bool:
        """모델이 얼굴 · 사람을 보았다고 했나(그러면 결과를 버린다)."""
        return bool(FACE_CODES.intersection(self.personal_seen))


@dataclass(frozen=True)
class SpaceRange:
    """공간 하나의 코드가 낸 가로 범위(mm). ``high == low`` 면 한 값(D96 의 4 — '약 ○mm')."""

    low: int
    high: int
    walls: int
    deducted: tuple[int, ...] = field(default=())  # 벽마다 뺀 mm(0 = 그대로)
    basis_unknown: bool = False


# ── 스키마 ───────────────────────────────────────────────────────────────
def _enum(values: Sequence[str]) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def _list(values: Sequence[str]) -> dict[str, Any]:
    return {"type": "array", "items": _enum(values)}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def image_schema() -> dict[str, Any]:
    """``output_config.format`` JSON 스키마 — 숫자 · 참거짓 · 고른 값, 글 칸은 사진마다 짧은 설명 두 칸뿐(17.11.1)."""
    wall = _object({"side": _enum(SIDES), "usable": {"type": "boolean"}, "marked": {"type": "boolean"},
                    "blocked_by": _list(BLOCKERS), "read_min_mm": {"type": "integer"},
                    "read_max_mm": {"type": "integer"}, "source": _enum(SOURCES), "basis": _enum(BASES),
                    "ends": _enum(tuple(ENDS))})
    space = _object({"room": _enum(SPACES), "room_basis": _list(ROOM_BASIS), "target": _enum(TARGETS),
                     "mark_kinds": _list(MARKS), "walls": {"type": "array", "items": wall},
                     "door": _enum(tuple(DOORS)), "handle": _enum(tuple(HANDLES)), "molding": _enum(MOLDINGS),
                     "height_mm": {"type": "integer"}})
    image = _object({"index": {"type": "integer"}, "kind": _enum(KINDS), "confidence": _enum(CONFIDENCES),
                     "summary": {"type": "string"}, "about_question": {"type": "string"}})  # 글자 상한은 코드가 자른다
    return _object({"images": {"type": "array", "items": image}, "is_drawing": {"type": "boolean"},
                    "spaces": {"type": "array", "items": space}, "confidence": _enum(CONFIDENCES),
                    "reasons": _list(REASONS), "personal_seen": _list(PERSONAL), "other_question": {"type": "boolean"}})


# ── 읽기 ─────────────────────────────────────────────────────────────────
def _mm(value: Any) -> Optional[int]:
    """mm 칸 — 0 이상 100m 이하 정수만(0 = 모름). 아니면 ``None``(그 칸을 버린다)."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_MM:
        return None
    return value


def _picked(values: Any, choices: Sequence[str]) -> Optional[tuple[str, ...]]:
    """고른 값 목록(겹침 없이). 목록이 아니거나 고른 값 밖이 섞이면 ``None``."""
    if not isinstance(values, list) or not all(isinstance(v, str) and v in choices for v in values):
        return None
    return tuple(dict.fromkeys(values))


def _wall(raw: Any) -> Optional[Wall]:
    """벽 하나 — 꼴이 틀리면 ``None``(그 벽만 버린다)."""
    if not isinstance(raw, Mapping):
        return None
    low, high = _mm(raw.get("read_min_mm")), _mm(raw.get("read_max_mm"))
    blocked = _picked(raw.get("blocked_by"), BLOCKERS)
    if (low is None or high is None or not low or blocked is None or high and low > high
            or raw.get("side") not in SIDES or raw.get("source") not in SOURCES or raw.get("basis") not in BASES
            or raw.get("ends") not in ENDS or not isinstance(raw.get("usable"), bool)
            or not isinstance(raw.get("marked"), bool)):
        return None
    return Wall(side=raw["side"], usable=raw["usable"], marked=raw["marked"], blocked_by=blocked,
                read_min_mm=low, read_max_mm=high or low, source=raw["source"], basis=raw["basis"], ends=raw["ends"])


def _space(raw: Any) -> Optional[ReadSpace]:
    """공간 하나 — 방 · 표시 · 문 꼴이 틀리면 ``None``(그 공간만 버린다). 틀린 벽 · 높이는 그 칸만 버린다."""
    if not isinstance(raw, Mapping) or raw.get("room") not in SPACES or raw.get("target") not in TARGETS:
        return None
    basis, marks = _picked(raw.get("room_basis"), ROOM_BASIS), _picked(raw.get("mark_kinds"), MARKS)
    if basis is None or marks is None or not isinstance(raw.get("walls"), list):
        return None
    walls = tuple(w for w in (_wall(item) for item in raw["walls"]) if w is not None)[:MAX_WALLS]
    door = raw.get("door") if raw.get("door") in DOORS else "unknown"
    handle = raw.get("handle") if raw.get("handle") in HANDLES else "unknown"
    molding = raw.get("molding") if raw.get("molding") in MOLDINGS else "unknown"
    return ReadSpace(room=raw["room"], room_basis=basis, target=raw["target"], mark_kinds=marks, walls=walls,
                     door=door, handle=handle, molding=molding, height_mm=_mm(raw.get("height_mm")) or 0)


def read_result(text: str) -> ImageRead:
    """구조화 출력 글 → :class:`ImageRead`. 큰 꼴이 틀리면 ``ValueError``(칸 이름만)."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("JSON 이 아니다") from None
    if not isinstance(data, dict):
        raise ValueError("객체가 아니다")
    for name in ("is_drawing", "other_question"):
        if not isinstance(data.get(name), bool):
            raise ValueError(name)
    if data.get("confidence") not in CONFIDENCES:
        raise ValueError("confidence")
    reasons, personal = _picked(data.get("reasons"), REASONS), _picked(data.get("personal_seen"), PERSONAL)
    if reasons is None or personal is None:
        raise ValueError("reasons · personal_seen")
    images, spaces = data.get("images"), data.get("spaces")
    if not isinstance(images, list) or not isinstance(spaces, list):
        raise ValueError("images · spaces")
    kinds = tuple(item["kind"] for item in images[:MAX_IMAGES]
                  if isinstance(item, Mapping) and item.get("kind") in KINDS)
    read_spaces = tuple(s for s in (_space(item) for item in spaces) if s is not None)[:MAX_SPACES]
    notes = parse_notes(images, kinds=KINDS, confidences=CONFIDENCES, max_images=MAX_IMAGES)
    return ImageRead(kinds=kinds, is_drawing=data["is_drawing"], spaces=read_spaces, confidence=data["confidence"],
                     reasons=reasons, personal_seen=tuple(p for p in personal if p != "none"),
                     other_question=data["other_question"], notes=notes)


def result_json(read: ImageRead) -> dict[str, Any]:
    """표 ``result`` 칸에 남길 JSON(숫자 · 고른 값 + 사진마다 가린 설명 두 칸 — 빈 칸은 싣지 않는다)."""
    def wall(w: Wall) -> dict[str, Any]:
        return {"side": w.side, "usable": w.usable, "marked": w.marked, "blocked_by": list(w.blocked_by),
                "read_min_mm": w.read_min_mm, "read_max_mm": w.read_max_mm, "source": w.source, "basis": w.basis,
                "ends": w.ends}

    spaces = [{"room": s.room, "room_basis": list(s.room_basis), "target": s.target, "mark_kinds": list(s.mark_kinds),
               "walls": [wall(w) for w in s.walls], "door": s.door, "handle": s.handle, "molding": s.molding,
               "height_mm": s.height_mm} for s in read.spaces]
    images = ([note_json(note) for note in read.notes] if read.notes
              else [{"index": i, "kind": k} for i, k in enumerate(read.kinds)])
    return {"images": images, "is_drawing": read.is_drawing,
            "spaces": spaces, "confidence": read.confidence, "reasons": list(read.reasons),
            "personal_seen": list(read.personal_seen) or ["none"], "other_question": read.other_question}


# ── 범위(코드가 한다 — D90 · D96) ────────────────────────────────────────
def wall_range(wall: Wall, wall_side_mm: int = WALL_SIDE_MM) -> Optional[tuple[int, int, int]]:
    """벽 하나 → (아래 끝, 위 끝, 뺀 mm). 뺀 뒤 0 이하면 ``None``.

    ``center_line`` 은 두 끝에서, ``unknown`` 은 아래 끝에서만 벽 쪽마다 ``wall_side_mm``(처음 값 150 — 설정
    ``drawing_dimension_rules`` 의 ``wall_side_mm``, :func:`.rule_settings.wall_side_mm`)를 뺀다. 아래는 10mm 내림 · 위는 10mm 올림.
    """
    cut = wall_side_mm * ENDS[wall.ends] if wall.basis != "inner" else 0
    low = wall.read_min_mm - cut
    high = wall.read_max_mm - cut if wall.basis == "center_line" else wall.read_max_mm
    low, high = (low // _ROUND) * _ROUND, math.ceil(high / _ROUND) * _ROUND
    if low <= 0 or high < low:
        return None
    return low, high, cut


def _chosen(space: ReadSpace) -> tuple[Wall, ...]:
    """고를 벽 — 손님 표시가 있으면 표시한 벽만, 없으면 쓸 수 있는 벽 모두."""
    marked = tuple(w for w in space.walls if w.marked)
    if space.target == "marked" and marked:
        return marked
    return tuple(w for w in space.walls if w.usable)


def space_range(space: ReadSpace, wall_side_mm: int = WALL_SIDE_MM) -> tuple[Optional[SpaceRange], Optional[str]]:
    """공간 하나 → (범위, 못 쓴 까닭 코드). 벽이 없으면 ``no_dimensions``, 합친 범위가 1.5배를 넘으면 ``wall_unclear``.
    ``wall_side_mm`` 은 벽 쪽마다 빼는 값(:func:`wall_range`)."""
    ranges = [r for r in (wall_range(w, wall_side_mm) for w in _chosen(space)) if r is not None]
    if not ranges:
        return None, "no_dimensions"
    low, high = min(r[0] for r in ranges), max(r[1] for r in ranges)
    if Fraction(high, low) > RATIO_LIMIT:
        return None, "wall_unclear"
    unknown = any(w.basis == "unknown" and ENDS[w.ends] for w in _chosen(space))
    return SpaceRange(low=low, high=high, walls=len(ranges), deducted=tuple(r[2] for r in ranges),
                      basis_unknown=unknown), None
