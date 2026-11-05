"""사진마다 가린 짧은 글 두 칸 — 무엇이 보이나(``summary``) · 손님 질문과 이어지는 점(``about_question``)(설계서 17.11.1 의 2).

그림 읽기 결과(:mod:`.image_rules`)의 ``images[]`` 칸에 붙는다. 그림 읽기는 처음엔 숫자 · 코드만 냈다(17.11 (c)) — 사장님 D172
(11-05)로 사진마다 이 두 글 칸과 사진 하나의 확신만 더한다. 글 칸은 직원 사진 설명(:mod:`.photo_desc`)과 같은 규칙을 지난다:
모델 글에 개인정보 꼴이 하나라도 있으면 **그 칸만** 비우고(모델이 사람 정보를 보았다는 뜻 — 가려서 남기지 않는다), 아니면 가림
→ 가림 검사 0 → 한 줄로 → 상한(:data:`SUMMARY_LIMIT` · :data:`ABOUT_LIMIT` 자, 합 200자). 줄 나눔은 빈칸으로 바꿔 한 줄로 둔다
— 두뇌 재료에서 머리표를 흉내 내지 못하게(:mod:`.brain_photos`). 글은 로그 · 예외에 싣지 않는다.

표에 남긴 결과를 다시 읽을 때도 같은 함수를 지난다(가린 글을 다시 가려도 바뀌지 않는다). 옛 결과(판 1 — 글 칸 없음)는 빈 글이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from foms.services.cs_agent.masking import MaskLeak, leak_counts, mask, require_masked

__all__ = ["ABOUT_LIMIT", "SUMMARY_LIMIT", "ImageNote", "clean_text", "note_json", "parse_notes"]

SUMMARY_LIMIT, ABOUT_LIMIT = 120, 80
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ImageNote:
    """사진 하나 — 보낸 차례(0부터) · 종류 · 확신(옛 결과는 빈 글) · 가린 설명 · 가린 질문과 이어지는 점."""

    index: int
    kind: str
    confidence: str = ""
    summary: str = field(default="", repr=False)
    about: str = field(default="", repr=False)

    @property
    def has_text(self) -> bool:
        """남은 글이 있나(두 칸 모두 비면 종류만 안다)."""
        return bool(self.summary or self.about)


def clean_text(value: Any, limit: int) -> str:
    """글 칸 하나 — 개인정보 꼴이 있으면 빈 글, 아니면 가림 → 가림 검사 0 → 한 줄 → ``limit`` 자. 글이 아니면 빈 글."""
    if not isinstance(value, str) or not value.strip() or any(leak_counts(value).values()):
        return ""
    try:
        masked = require_masked(mask(value))
    except MaskLeak:
        return ""
    return _SPACE.sub(" ", masked).strip()[:limit].strip()


def parse_notes(images: Sequence[Any], *, kinds: Sequence[str], confidences: Sequence[str],
                max_images: int) -> tuple[ImageNote, ...]:
    """``images[]`` 칸 → 사진마다 :class:`ImageNote`(차례가 틀리거나 겹치거나 종류가 고른 값 밖이면 그 사진만 뺀다)."""
    out: list[ImageNote] = []
    seen: set[int] = set()
    for item in images[:max_images]:
        if not isinstance(item, Mapping) or item.get("kind") not in kinds:
            continue
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < max_images or index in seen:
            continue
        seen.add(index)
        confidence = item.get("confidence") if item.get("confidence") in confidences else ""
        out.append(ImageNote(index=index, kind=item["kind"], confidence=confidence,
                             summary=clean_text(item.get("summary"), SUMMARY_LIMIT),
                             about=clean_text(item.get("about_question"), ABOUT_LIMIT)))
    return tuple(out)


def note_json(note: ImageNote) -> dict[str, Any]:
    """표 ``result.images[]`` 칸 하나(빈 글 칸은 싣지 않는다)."""
    out: dict[str, Any] = {"index": note.index, "kind": note.kind}
    if note.confidence:
        out["confidence"] = note.confidence
    if note.summary:
        out["summary"] = note.summary
    if note.about:
        out["about_question"] = note.about
    return out
