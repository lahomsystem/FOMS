"""초안 차례의 손님 사진 읽기 — 읽기(미리 읽은 결과 · 그 자리 읽기) · 차례 잇기 · 두뇌 사진 칸 · 직원 참고 줄 · 쓰임(설계서 17.11.1).

사장님 D172(11-05 '사진도 같이 보게'). 초안 차례(:mod:`.drafting` — 15분 바퀴 · 빠른 길 공통)가 견적 계산 넣기 뒤 · 두뇌 전에
부른다(사진만 온 글은 판정 때 먼저). 묶음 읽기는 차례마다 한 번이다(:func:`turn_read`) — 견적 도면 길(:func:`.image_step.turn_hook`)이
먼저 읽었으면 그 결과를 쓰고, 쓰임(토큰 · 돈)은 처음 읽은 쪽만 센다. 견적이 사람에게 넘긴 차례는 사진을 읽지 않는다(초안이 없다).
패널 '사진 · 그림 읽기'(:mod:`.image_settings`):

- **끔** — 아무것도 하지 않는다(설정 한 번 읽기뿐 · 모델 0번 · 표 쓰기 0 · 글자까지 예전 그대로).
- **직원 참고만** — 읽고(미리 읽은 결과가 있으면 그것) 직원 참고 줄 한 줄(:func:`note_line`)만 더한다. 두뇌 사진 칸 · 지시문
  13번은 없다. 사진만 온 글은 예전처럼 건너뛴다(두뇌가 사진을 모르니 쓸 초안이 없다 — 읽지도 않는다).
- **초안에 씀** — 두뇌 사진 칸(:mod:`.brain_photos`)을 상담 글 앞에 싣고, 사진만 온 글도 읽은 사진이 하나라도 있으면 초안을 쓴다.

고르기: 마지막 공개 직원 글 뒤 손님 파일 — 읽는 것은 새 것부터 차례당 상한(17.11 상한 그대로), 넘는 사진은 '상한'으로 칸에
남긴다. 시간 상한은 그 자리 읽기 상한(넘으면 사진 없이 — 늦은 초안보다 낫다). 읽은 그림 줄에는 그 차례 번호(``turn_id``)를
적는다 — 사례 학습(:mod:`.image_summaries`)이 차례 번호로 잇는다. 로그 · 요약엔 숫자 · 코드만.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional, Sequence

from sqlalchemy import select

from foms.services.cs_agent.brain_photos import PhotoEntry
from foms.services.cs_agent.drafting_read import MEMO_IMAGE_HEAD, conversation
from foms.services.cs_agent.image_fetch import pending_files
from foms.services.cs_agent.image_prep import SKIP_CAP, SKIP_FACE, SKIP_FORMAT, SKIP_PDF, SKIP_SIZE
from foms.services.cs_agent.image_read import BatchOutcome, current, read_batch
from foms.services.cs_agent.image_settings import MODE_DRAFT, MODE_OFF, image_mode
from foms.services.cs_agent.image_store import DISCARDED, DONE, SKIP_NOT_PREREAD, SKIP_SWITCH, ensure_rows
from foms.services.cs_agent.image_summaries import row_note
from foms.services.cs_agent.settings import read_settings
from models import CsAgentImageRead

__all__ = ["MAX_FILES", "NOTE_LABELS", "PhotoRead", "note_line", "read_photos", "stored_photos", "turn_read",
           "unread_code", "with_usage"]

#: 칸에 남기는 손님 파일 수 상한(읽는 수는 패널 '차례당 장수').
MAX_FILES = 20
#: 못 읽은 까닭 코드 → 직원 참고 줄의 짧은 말(숫자 · 정한 말만).
NOTE_LABELS = {"face": "얼굴", "file": "열 수 없음", "cap": "상한", "error": "오류"}
_FILE_CODES = frozenset({SKIP_FORMAT, SKIP_SIZE, SKIP_PDF, "fetch_failed"})
_CAP_CODES = frozenset({SKIP_CAP, SKIP_NOT_PREREAD, SKIP_SWITCH, "no_time", "daily_cap_reached", "time_cap"})
_USAGE = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_usd", "latency_ms")


@dataclass(frozen=True)
class PhotoRead:
    """차례 하나의 사진 읽기 — 모드 · 사진마다 칸(시간 순) · 읽은 수 · 묶음 결과(견적 도면 길이 다시 씀) · 이번에 부른 쓰임."""

    mode: str
    entries: tuple[PhotoEntry, ...]
    outcome: Optional[BatchOutcome] = None
    usage: Any = None

    @property
    def read(self) -> int:
        """읽은 사진 수(설명이 비었어도 종류를 알면 읽음)."""
        return sum(1 for entry in self.entries if not entry.unread)

    def apply(self, request: Any) -> Any:
        """초안 재료에 사진 칸을 넣는다 — '초안에 씀'일 때만(아니면 그대로)."""
        return dataclasses.replace(request, photos=self.entries) if self.mode == MODE_DRAFT and self.entries else request


def unread_code(state: str, skip_code: Optional[str]) -> str:
    """못 읽은 그림 줄 → 까닭 코드(:data:`.brain_photos.UNREAD_LABELS` 의 열쇠)."""
    code = skip_code or ""
    if state == DISCARDED or code in (SKIP_FACE, "discarded_face"):
        return "face"
    if code in _FILE_CODES or code.startswith(("signed_url_", "download_")):
        return "file"
    return "cap" if code in _CAP_CODES else "error"


def note_line(photo: Optional[PhotoRead]) -> str:
    """직원 참고 줄 ``[그림 읽기] 사진: N장 읽음 · M장 못 읽음(까닭)``(숫자 · 정한 말만 — 설명 글은 메모에 싣지 않는다)."""
    if photo is None or not photo.entries:
        return ""
    unread = [entry.unread for entry in photo.entries if entry.unread]
    tail = (f" · {len(unread)}장 못 읽음({'·'.join(NOTE_LABELS[c] for c in dict.fromkeys(unread))})" if unread else "")
    return f"{MEMO_IMAGE_HEAD}] 사진: {photo.read}장 읽음{tail}"


def with_usage(base: Any, photo: Optional[PhotoRead]) -> Any:
    """두뇌 · 뽑기 쓰임에 이번 차례 사진 읽기의 토큰 · 돈 · 시간을 더한 사본(차례 줄의 돈이 그 차례 전부가 되게)."""
    usage = photo.usage if photo is not None else None
    if usage is None or base is None:
        return base
    values = {name: (getattr(base, name, 0) or 0) + getattr(usage, name) for name in _USAGE}
    if dataclasses.is_dataclass(base):
        return dataclasses.replace(base, **values)
    return SimpleNamespace(**{**vars(base), **values})


def _chronological(lines: Sequence[Any], refs: Sequence[Any]) -> list[Any]:
    """파일들을 글 시간 순 · 글 안 차례로."""
    order = {(ref.message_id, ref.file_index): index
             for index, ref in enumerate(ref for line in lines for ref in getattr(line, "files", ()))}
    return sorted(refs, key=lambda ref: order.get((ref.message_id, ref.file_index), 0))


def _entry(number: int, row: Any) -> PhotoEntry:
    """그림 줄 하나 → 칸 하나(읽음이면 그 사진의 종류 · 확신 · 가린 설명, 아니면 까닭)."""
    result = row.result if isinstance(row.result, dict) else {}
    if row.state != DONE or not current(row.state, result):
        return PhotoEntry(number, unread=unread_code(row.state, row.skip_code))
    note = row_note(row)
    if note is None:
        return PhotoEntry(number, unread="error")
    text = " — ".join(part for part in (note.summary, note.about) if part)
    return PhotoEntry(number, kind=note.kind, confidence=note.confidence or str(result.get("confidence") or ""),
                      text=text)


def _usage(outcome: Optional[BatchOutcome]) -> Any:
    """이번에 모델을 불렀으면 그 쓰임(캐시 칸은 0 — 그림 읽기는 캐시 표시가 없다)."""
    used = outcome.usage if outcome is not None else None
    if used is None:
        return None
    return SimpleNamespace(input_tokens=used.input_tokens, output_tokens=used.output_tokens, cache_read_tokens=0,
                           cache_write_tokens=0, cost_usd=used.cost_usd or Decimal(0), latency_ms=used.latency_ms)


def turn_read(ctx: Any, row: Any, lines: Sequence[Any], cfg: Any) -> Optional[BatchOutcome]:
    """이 차례 손님 그림 묶음 읽기(:func:`.image_read.read_batch` — 그 자리 시간 상한) — 차례마다 한 번. 두 번째부터는 쓰임을
    비운 같은 결과다(토큰 · 돈을 두 번 세지 않게). 결과는 ``ctx.image_outcomes``(차례 줄 id → 결과)에 둔다."""
    seen = ctx.image_outcomes
    if row.id in seen:
        prior = seen[row.id]
        return dataclasses.replace(prior, usage=None) if prior is not None else None
    refs = pending_files(lines, limit=int(cfg.get("image_per_turn")))

    def still_on() -> bool:
        return not ctx.switched_off() and image_mode(read_settings(ctx.session, log=False)) != MODE_OFF

    outcome = BatchOutcome(codes=("no_file",)) if not refs else read_batch(
        ctx.session, reader=ctx.reader, brand=row.brand, chat_id=row.chat_id, refs=refs, turns=conversation(lines),
        cfg=cfg, now=ctx.now, owner=ctx.owner, deadline_s=float(cfg.get("image_inline_timeout_s")), still_on=still_on,
        clock=ctx.clock, sleep=ctx.image_sleep or time.sleep, client=ctx.image_client, transport=ctx.image_transport,
        turn_id=row.id, stop=ctx.stop)
    seen[row.id] = outcome
    return outcome


def read_photos(ctx: Any, row: Any, lines: Sequence[Any]) -> Optional[PhotoRead]:
    """사진 읽기 한 번(모듈 설명). 끔이거나 손님 파일이 없으면 ``None``.

    Raises:
        PassStopped: 두뇌 전 TERM 깃발. SQLAlchemyError: DB 오류(초안 차례가 다룬다).
    """
    cfg = read_settings(ctx.session, log=False)
    mode = image_mode(cfg)
    if mode == MODE_OFF:
        return None
    every = pending_files(lines, limit=MAX_FILES)
    if not every:
        return None
    refs = every[:int(cfg.get("image_per_turn"))]
    outcome = turn_read(ctx, row, lines, cfg)
    rows = {(r.message_id, r.file_index): r for r in ensure_rows(ctx.session, row.brand, row.chat_id, refs, ctx.now)}
    for image_row in rows.values():
        image_row.turn_id = row.id  # 이 결과를 쓴 차례(다시 쓴 미리 읽기 결과도 — 사례 학습이 잇는다)
    ctx.session.commit()
    entries = []
    for number, ref in enumerate(_chronological(lines, every), start=1):
        found = rows.get((ref.message_id, ref.file_index))
        entries.append(_entry(number, found) if found is not None else PhotoEntry(number, unread="cap"))
    photo = PhotoRead(mode=mode, entries=tuple(entries), outcome=outcome, usage=_usage(outcome))
    ctx.summary.brain_calls += int(photo.usage is not None)
    return photo


def stored_photos(session: Any, turn_id: int, cfg: Any) -> tuple[PhotoEntry, ...]:
    """[수정하기] 다시 쓰기(:mod:`.rewrite`)의 사진 칸 — 그 차례가 읽은 그림 줄(``turn_id``)로 다시 만든다('초안에 씀'일 때만,
    읽기 · 모델 0번). 차례당 상한을 넘어 줄이 없던 사진은 빠진다."""
    if image_mode(cfg) != MODE_DRAFT:
        return ()
    stmt = (select(CsAgentImageRead).where(CsAgentImageRead.turn_id == turn_id)
            .order_by(CsAgentImageRead.id).limit(MAX_FILES))
    return tuple(_entry(number, row) for number, row in enumerate(session.scalars(stmt), start=1))
