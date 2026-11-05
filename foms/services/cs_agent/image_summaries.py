"""차례가 읽은 손님 사진 설명 — 그림 읽기 표(``cs_agent_image_reads``)에서 차례 번호로 읽는다(설계서 17.11.1 의 6 · 7).

사례 재료(:mod:`.case_material` — '고침' · '직접 답' 사례에 사진 설명 줄) · 주간 고침 안 재료(:mod:`.weekly_fix`) · 사진 학습
(:mod:`.photo_learning`)이 같이 쓴다. 새 칸은 없다 — 초안 차례가 읽은 그림 줄에 차례 번호(``turn_id``)를 적어 두고
(:mod:`.photo_step`), 여기서는 그 줄의 결과(가린 설명 — :mod:`.image_notes`)만 읽는다.

- 지금 판 결과(:func:`.image_read.current` — 판 2 이상)의 ``done`` 줄만. 얼굴로 버린 줄 · 옛 판 · 글이 빈 사진은 뺀다.
- 사진마다 한 줄 ``종류: 설명 — 질문과 이어지는 점``(가림 검사 0 · :data:`LINE_LIMIT` 자 — 직원 사진 설명 칸과 같은 상한).
- 차례 묶음을 :data:`CHUNK` 개씩 한 번에 읽는다(N+1 없음). DB 를 읽기만 한다 — 글은 로그에 싣지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from sqlalchemy import select

from foms.services.cs_agent.brain_photos import KIND_LABELS
from foms.services.cs_agent.image_notes import ImageNote, parse_notes
from foms.services.cs_agent.image_read import current
from foms.services.cs_agent.image_rules import CONFIDENCES, MAX_IMAGES
from foms.services.cs_agent.image_store import DONE
from foms.services.cs_agent.masking import leak_counts
from models import CsAgentImageRead

__all__ = ["CHUNK", "LINE_LIMIT", "PER_TURN", "PhotoSummary", "row_note", "summaries_by_turn"]

LINE_LIMIT, PER_TURN, CHUNK = 120, 4, 500


@dataclass(frozen=True)
class PhotoSummary:
    """차례가 읽은 사진 하나 — 종류 코드 · 가린 한 줄(``종류: 설명 — 이어지는 점``)."""

    kind: str
    text: str = field(repr=False)


def row_note(row: Any) -> Optional[ImageNote]:
    """지금 판 ``done`` 그림 줄 → 그 사진의 칸(묶음 결과에서 그 줄 sha256 의 차례). 아니면 ``None``."""
    result = row.result if isinstance(row.result, dict) else None
    if row.state != DONE or result is None or not current(row.state, result):
        return None
    batch = list(result.get("batch") or ())
    index = batch.index(row.sha256) if row.sha256 in batch else -1
    notes = parse_notes(result.get("images") or [], kinds=tuple(KIND_LABELS), confidences=CONFIDENCES,
                        max_images=MAX_IMAGES)
    return next((n for n in notes if n.index == index), None)


def _summary(row: Any, limit: int) -> Optional[PhotoSummary]:
    """그림 줄 하나 → 그 사진의 한 줄(지금 판 · 글이 있는 사진만 — 아니면 ``None``)."""
    note = row_note(row)
    if note is None or not note.has_text:
        return None
    body = " — ".join(part for part in (note.summary, note.about) if part)
    text = f"{KIND_LABELS[note.kind]}: {body}"[:limit].strip()
    return PhotoSummary(note.kind, text) if not any(leak_counts(text).values()) else None


def summaries_by_turn(session: Any, turn_ids: Sequence[int], *, per_turn: int = PER_TURN,
                      limit: int = LINE_LIMIT) -> dict[int, list[PhotoSummary]]:
    """차례 번호 → 그 차례가 읽은 사진 한 줄들(그림 줄 순서, 차례마다 ``per_turn`` 장까지). 없는 차례는 빠진다."""
    ids = sorted({int(i) for i in turn_ids if i is not None})
    out: dict[int, list[PhotoSummary]] = {}
    for start in range(0, len(ids), CHUNK):
        stmt = (select(CsAgentImageRead.turn_id, CsAgentImageRead.state, CsAgentImageRead.sha256,
                       CsAgentImageRead.result)
                .where(CsAgentImageRead.turn_id.in_(ids[start:start + CHUNK]), CsAgentImageRead.state == DONE,
                       CsAgentImageRead.result.isnot(None))
                .order_by(CsAgentImageRead.turn_id, CsAgentImageRead.id))
        for row in session.execute(stmt):
            found = out.setdefault(row.turn_id, [])
            line = _summary(row, limit) if len(found) < per_turn else None
            if line is not None:
                found.append(line)
    return {turn: lines for turn, lines in out.items() if lines}
