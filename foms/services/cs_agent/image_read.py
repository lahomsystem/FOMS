"""그림 묶음 읽기 한 번 — 줄 · 받기 전 거르기 · (남이 읽는 중이면 기다림) · 선점 · 받기 · 준비 · 같은 그림 다시 쓰기 · 하루 상한 ·
두뇌 · 결과 쓰기(설계서 17.11 (a) · (b) · (e) · (f)). 미리 읽기 길(:mod:`.image_preread`)과 그 자리 읽기(:mod:`.image_step`)가 같이
쓴다.

- **묶음**: 마지막 공개 직원 글 뒤 손님 파일(새 것부터 차례당 상한까지)을 한 번에 읽는다 — 평면도 + 참고 사진처럼 같이 보내야
  모델이 고른다(시험 1건). 묶음의 모든 줄이 같은 결과(``result.batch`` = sha256 차례)를 가진다. 새 그림이 들어와 묶음이 바뀌면
  묶음 전체를 다시 읽는다.
- **저장 0(D89)**: 바이트는 이 함수의 지역 변수에만 있고 준비가 끝나면 놓는다. 표에는 sha256 · 숫자 · 코드만.
- **기다림 · 시간**: 다른 길이 같은 그림을 읽는 중이면 끝나기를 기다린다(시간 상한 안). 시간 상한(``deadline_s``)은 받기까지
  포함한 전체다 — 넘으면 그림 없이 간다(늦은 초안보다 사람이 낫다 — 11.1 의 5).
- **실패는 조용히 앞 단계로**: 받기 · 두뇌 오류 · 가림 · 돈 상한이면 줄을 실패로 적고 ``None`` 결과를 돌려준다(초안 차례는
  앞 단계 '되묻지 않기' 그대로). 로그엔 상담 id · 코드 · 숫자만.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent.image_brain import BrainRead, read_images
from foms.services.cs_agent.image_fetch import FetchError, fetch_bytes
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_prep import SKIP_CAP, SKIP_SIZE, Prepared, precheck, prepare
from foms.services.cs_agent.image_rules import WALL_SIDE_MM, ImageRead, read_result, result_json, space_range
from foms.services.cs_agent.image_store import (
    DISCARDED, DONE, FAILED, HARD_SKIPS, READING, SKIPPED, SKIP_SWITCH, claim, ensure_rows, finish, reuse_by_sha,
    sent_today, set_skip,
)
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.rule_settings import wall_side_mm
from foms.services.cs_agent.settings import PanelSettings
from foms.services.cs_agent.state import KST

logger = logging.getLogger(__name__)

__all__ = ["CLAIM_MARGIN_S", "MIN_CALL_S", "RULES_VERSION", "BatchOutcome", "read_batch"]

RULES_VERSION = 1  # 결과 판 번호(지시문 · 스키마 · 범위 규칙을 바꾸면 올린다)
CLAIM_MARGIN_S = 45  # 선점 만료 = 시간 상한 + 이 여유
MIN_CALL_S = 5  # 두뇌에 남은 시간이 이보다 짧으면 부르지 않는다
POLL_S = 1.0
UTC = datetime.timezone.utc


@dataclass(frozen=True)
class BatchOutcome:
    """묶음 읽기 결과 — 쓸 결과(없으면 ``None``) · 두뇌 쓰임(다시 쓴 결과면 ``None``) · 본 건너뜀 · 실패 코드 · 보낸 장수."""

    read: Optional[ImageRead] = None
    usage: Optional[BrainRead] = None
    codes: tuple[str, ...] = ()
    images: int = 0
    reused: bool = False
    discarded: bool = False
    ranges: tuple[dict[str, Any], ...] = field(default=())


def _ranges(read: ImageRead, wall_side: int = WALL_SIDE_MM) -> list[dict[str, Any]]:
    """공간마다 코드가 낸 범위(또는 못 쓴 까닭) — 표 ``result.ranges``. ``wall_side`` = 벽 쪽마다 빼는 값(설정 → 처음 값)."""
    out = []
    for space in read.spaces:
        found, code = space_range(space, wall_side)
        entry: dict[str, Any] = {"room": space.room, "target": space.target}
        if found is None:
            entry["code"] = code
        else:
            entry.update(low=found.low, high=found.high, walls=found.walls, deducted=list(found.deducted),
                         basis_unknown=found.basis_unknown)
        out.append(entry)
    return out


def _from_result(result: Any, *, codes: Sequence[str], images: int, reused: bool, discarded: bool,
                 usage: Optional[BrainRead] = None) -> BatchOutcome:
    """표 결과 → 묶음 결과(버린 결과는 쓰지 않는다)."""
    try:
        read = read_result(json.dumps(result)) if isinstance(result, dict) and not discarded else None
    except ValueError:
        read = None
    ranges = tuple(result.get("ranges") or ()) if isinstance(result, dict) else ()
    return BatchOutcome(read=read, usage=usage, codes=tuple(codes), images=images, reused=reused,
                        discarded=discarded, ranges=ranges)


def _same_batch(rows: Sequence[Any]) -> Optional[Any]:
    """묶음의 모든 줄이 같은 결과(같은 sha256 묶음)를 가지면 그 첫 줄."""
    if not rows or any(row.state not in (DONE, DISCARDED) or not isinstance(row.result, dict) for row in rows):
        return None
    batch = rows[0].result.get("batch")
    if not isinstance(batch, list) or len(batch) != len(rows):
        return None
    same = all(row.result.get("batch") == batch and row.sha256 in batch for row in rows)
    return rows[0] if same else None


@dataclass
class _Job:
    """한 번의 읽기 재료(부르는 쪽이 채운다)."""

    session: Any
    reader: Any
    brand: str
    chat_id: str
    turns: Sequence[tuple[str, str]]
    cfg: PanelSettings
    now: datetime.datetime
    owner: str
    deadline_s: float
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    still_on: Callable[[], bool]
    client: Any = None
    transport: Any = None
    turn_id: Optional[int] = None
    stop: Any = None
    started: float = 0.0
    codes: list[str] = field(default_factory=list)

    def left(self) -> float:
        return self.deadline_s - (self.clock() - self.started)

    def at(self) -> datetime.datetime:
        return self.now + datetime.timedelta(seconds=max(0.0, self.clock() - self.started))


def _wait_others(job: _Job, rows: Sequence[Any]) -> bool:
    """다른 길이 읽는 중(만료 전)인 줄이 끝날 때까지 기다린다 — 시간 상한을 넘으면 거짓."""
    while True:
        now = job.at().astimezone(UTC).replace(tzinfo=None)
        busy = [row for row in rows if row.state == READING and row.claim_expires_at is not None
                and row.claim_expires_at > now and row.claim_owner != job.owner]
        if not busy:
            return True
        if job.left() <= POLL_S:
            return False
        job.sleep(POLL_S)
        job.session.commit()
        for row in rows:
            job.session.refresh(row)


def _prepared(job: _Job, pairs: Sequence[tuple[FileRef, Any]]) -> list[tuple[Any, Prepared]]:
    """선점한 줄마다 받기 · 준비 — 건너뜀 · 실패는 그 줄에 적는다. 바이트는 여기서 놓는다."""
    out: list[tuple[Any, Prepared]] = []
    for ref, row in pairs:
        try:
            data = fetch_bytes(job.reader, job.brand, job.chat_id, ref, timeout=max(1.0, min(20.0, job.left())),
                               transport=job.transport)
        except FetchError as exc:
            code = SKIP_SIZE if exc.args == ("too_big",) else "fetch_failed"
            set_skip(row, code, job.at(), state=SKIPPED if code == SKIP_SIZE else FAILED)
            job.codes.append(code)
            continue
        item = prepare(ref, data, page_cap=int(job.cfg.get("image_pdf_pages")),
                       pdf_max_bytes=int(job.cfg.get("image_pdf_max_mb")) * 1024 * 1024)
        del data
        if isinstance(item, str):
            set_skip(row, item, job.at())
            job.codes.append(item)
            continue
        out.append((row, item))
    job.session.commit()
    return out


def _over_cap(job: _Job, count: int) -> bool:
    """오늘(KST) 보낸 장수 + 이번 장수가 상담 하나 · 전체 하루 상한을 넘나."""
    local = job.now.astimezone(KST)
    day = datetime.datetime(local.year, local.month, local.day, tzinfo=KST)
    chat = sent_today(job.session, day, chat_id=job.chat_id)
    total = sent_today(job.session, day)
    return (chat + count > int(job.cfg.get("image_per_chat_day"))
            or total + count > int(job.cfg.get("image_per_day")))


def _call(job: _Job, used: Sequence[tuple[Any, Prepared]]) -> BatchOutcome:
    """하루 상한 · 스위치 · 남은 시간을 보고 두뇌를 부르고 결과를 쓴다."""
    rows, shas = [row for row, _ in used], [item.sha256 for _, item in used]
    skip = SKIP_CAP if _over_cap(job, len(used)) else SKIP_SWITCH if not job.still_on() else None
    if skip is None and job.left() < MIN_CALL_S:
        skip = "no_time"
    if skip is not None:
        for row in rows:
            set_skip(row, skip, job.at(), state=FAILED if skip == "no_time" else SKIPPED, sha256=None)
        job.session.commit()
        return BatchOutcome(codes=(*job.codes, skip))
    if job.stop is not None:
        job.stop.check()  # 두뇌 전
    try:
        answer = read_images([item for _, item in used], job.turns, brand=job.brand, chat_id=job.chat_id,
                             session=job.session, cfg=job.cfg, now=job.now, timeout_s=job.left(), client=job.client)
    except (BrainError, MaskLeak) as exc:
        code = getattr(exc, "code", None) or "mask_leak"
        for row in rows:
            set_skip(row, str(code), job.at(), state=FAILED)
        job.session.commit()
        logger.warning("[CS 그림] 읽기 실패 — 그림 없이 간다 chat=%s code=%s", job.chat_id, code)
        return BatchOutcome(codes=(*job.codes, str(code)))
    if answer.read is None:
        for row in rows:
            set_skip(row, "refused", job.at(), state=FAILED)
        job.session.commit()
        return BatchOutcome(usage=answer, codes=(*job.codes, "refused"))
    read = answer.read
    result = {**result_json(read), "batch": shas, "ranges": _ranges(read, wall_side_mm(job.session)),
              "rules_version": RULES_VERSION}
    state = DISCARDED if read.face_seen else DONE
    finish(rows, result=result, state=state, confidence=read.confidence, personal=read.personal_seen,
           usage=answer.usage(), now=job.at(), shas=shas, turn_id=job.turn_id)
    job.session.commit()
    return _from_result(result, codes=job.codes, images=len(used), reused=False, discarded=state == DISCARDED,
                        usage=answer)


def _prechecked(job: _Job, refs: Sequence[FileRef]) -> list[tuple[FileRef, Any]]:
    """줄을 만들고 받기 전 거르기를 적는다 — 굳은 건너뜀이 아닌 (파일, 줄) 짝들(굳은 건너뜀 코드는 ``job.codes`` 에)."""
    rows = ensure_rows(job.session, job.brand, job.chat_id, refs, job.now)
    pdf_cap = int(job.cfg.get("image_pdf_max_mb")) * 1024 * 1024
    for ref, row in zip(refs, rows):
        hard = row.state == SKIPPED and row.skip_code in HARD_SKIPS
        code = None if hard else precheck(ref, pdf_max_bytes=pdf_cap)
        if code is not None and row.state != READING:
            set_skip(row, code, job.now)
    job.session.commit()
    job.codes.extend(row.skip_code for row in rows if row.state == SKIPPED and row.skip_code in HARD_SKIPS)
    return [(ref, row) for ref, row in zip(refs, rows) if not (row.state == SKIPPED and row.skip_code in HARD_SKIPS)]


def _reused(job: _Job, used: Sequence[tuple[Any, Prepared]]) -> Optional[BatchOutcome]:
    """같은 상담에서 같은 그림 묶음을 이미 읽었으면 그 결과를 줄에 옮겨 쓰고 돌려준다(두뇌 0번)."""
    shas = [item.sha256 for _, item in used]
    prior = reuse_by_sha(job.session, job.chat_id, shas)
    if prior is None:
        return None
    finish([row for row, _ in used], result=prior.result, state=prior.state, confidence=prior.confidence or "",
           personal=prior.personal_codes or [], usage=None, now=job.at(), shas=shas, turn_id=job.turn_id)
    job.session.commit()
    return _from_result(prior.result, codes=job.codes, images=len(used), reused=True,
                        discarded=prior.state == DISCARDED)


def read_batch(session: Any, *, reader: Any, brand: str, chat_id: str, refs: Sequence[FileRef],
               turns: Sequence[tuple[str, str]], cfg: PanelSettings, now: datetime.datetime, owner: str,
               deadline_s: float, still_on: Callable[[], bool], clock: Callable[[], float] = time.monotonic,
               sleep: Callable[[float], None] = time.sleep, client: Any = None, transport: Any = None,
               turn_id: Optional[int] = None, stop: Any = None) -> Optional[BatchOutcome]:
    """묶음 읽기 한 번(모듈 설명). 남이 읽는 중인데 시간 상한을 넘으면 ``None``(그림 없이).

    Raises:
        PassStopped: 두뇌 전 TERM 깃발(선점은 만료가 지나면 다른 길이 다시 집는다).
    """
    job = _Job(session, reader, brand, chat_id, turns, cfg, now, owner, deadline_s, clock, sleep, still_on, client,
               transport, turn_id, stop, started=clock())
    pairs = _prechecked(job, refs)
    if not pairs:
        return BatchOutcome(codes=tuple(job.codes))
    rows = [row for _, row in pairs]
    for _ in range(3):  # 남이 먼저 집으면 기다렸다가 다시 본다(시간 상한 안)
        done = _same_batch(rows)
        if done is None and not _wait_others(job, rows):
            return None
        done = done or _same_batch(rows)  # 기다린 사이 다른 길이 같은 묶음을 읽어 두었으면 그것을 쓴다
        if done is not None:
            return _from_result(done.result, codes=job.codes, images=len(pairs), reused=True,
                                discarded=done.state == DISCARDED)
        until = job.at() + datetime.timedelta(seconds=deadline_s + CLAIM_MARGIN_S)
        if claim(session, rows, owner=owner, until=until, now=job.at(), reread=True):
            break
        for row in rows:
            session.refresh(row)
    else:
        return None
    used = _prepared(job, pairs)
    if not used:
        return BatchOutcome(codes=tuple(job.codes))
    return _reused(job, used) or _call(job, used)
