"""그림 미리 읽기 길 — 손님 사진 · 그림이 온 순간 따로 읽어 두는 2초 차례(설계서 17.11 (b) · 17.11.1 의 1 · D172).

WORKER 감독자 자식 ``cs_image_read``(``scripts/maintenance/run_cs_image_read.py`` — env ``FOMS_CS_IMAGE_READ_ENABLED=1``
일 때만 뜬다)가 :data:`TICK_SECONDS` 마다 :func:`run_preread_tick` 을 부른다. 빠른 길 차례 안에서는 읽지 않는다 — 한 번에
20 ~ 30초가 걸려 다른 상담 초안을 막는다(R10-1 과 같은 까닭). 빠른 길 · 15분 바퀴와 다른 잠금 키 · 다른 하트비트 종류다.

차례 하나:

0. **켜짐** — 패널 '사진 · 그림 읽기'가 끔이 아님 · 비상 정지 아님 · 초안 스위치 끔이 아님. 아니면 일 0. 견적 계산 넣기와는
   상관없다(17.11.1 의 1 — 처음엔 견적 계산 넣기가 켜져야 돌았다).
1. **볼 상담** — 라홈 · 마지막 손님 글이 24시간 안 · 그 뒤 공개 직원 글 없음(색인 ``ix_cs_agent_chats_brand_last_user_at``)
   가운데, 아직 그림 줄이 없는 손님 파일 글이 있고 마지막 손님 글 뒤 :data:`SETTLE` 가 지난 상담(같이 보낸 그림이 다 오게)을
   새 것부터 :data:`MAX_CHATS` 개.
2. **읽기** — 파일이 온 상담이면 모두(견적 말 · 첫 글 묶음 조건은 17.11.1 에서 뗐다 — 하자 · 배송 사진도 질문과 같이 본다)
   :func:`.image_read.read_batch`(미리 읽기 시간 상한 · 같은 선점 · 같은 하루 상한 · 부르기 전 스위치 다시 읽기). 조용 기다림
   (15초) 안에 끝나면 초안 차례는 읽은 결과를 그대로 쓴다.

글 · 파일 key 는 메모리에만 — 로그 · 요약엔 숫자 · 코드만.
"""

from __future__ import annotations

import datetime
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import and_, or_, select

from foms.services.cs_agent.channel_read import ChannelRateLimited, ChannelReadError, OpenApiReader, naive_utc
from foms.services.cs_agent.drafting_read import conversation, read_lines
from foms.services.cs_agent.image_fetch import pending_files
from foms.services.cs_agent.image_read import read_batch
from foms.services.cs_agent.image_settings import MODE_OFF, image_mode
from foms.services.cs_agent.loop import PassStopped, StopFlag, leader_lock
from foms.services.cs_agent.settings import PanelSettings, read_settings
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.turns import DRAFT_OFF, claim_owner, draft_mode, read_switch
from foms.services.datetime_kst import now_kst
from models import CsAgentChat, CsAgentImageRead, CsAgentMessage

logger = logging.getLogger(__name__)

__all__ = ["BRAND", "MAX_CHATS", "PREREAD_LOCK_KEY", "SETTLE", "TICK_SECONDS", "PrereadMemory", "PrereadResult",
           "run_preread_tick"]

BRAND = "LAHOM"
PREREAD_LOCK_KEY = "foms:cs_agent_image_read"
TICK_SECONDS = 2.0
SETTLE = datetime.timedelta(seconds=5)
WINDOW = datetime.timedelta(hours=24)
MAX_CHATS = 3
MEMORY_LIMIT = 2000
OUTCOME_OK, OUTCOME_IDLE, OUTCOME_NOT_LEADER, OUTCOME_STOPPED = "ok", "idle", "not_leader", "stopped"


@dataclass
class PrereadMemory:
    """파일 정보를 못 얻은 상담(마지막 손님 글 시각과 함께) — 같은 상담을 2초마다 다시 읽지 않게(크기 상한)."""

    seen: "OrderedDict[str, datetime.datetime]" = field(default_factory=OrderedDict)

    def skip(self, chat_id: str, last_user_at: datetime.datetime) -> bool:
        return self.seen.get(chat_id) == last_user_at

    def remember(self, chat_id: str, last_user_at: datetime.datetime) -> None:
        self.seen[chat_id] = last_user_at
        self.seen.move_to_end(chat_id)
        while len(self.seen) > MEMORY_LIMIT:
            self.seen.popitem(last=False)


@dataclass
class PrereadResult:
    """한 차례 결과 — 숫자 · 코드만(상담 id · 글 없음)."""

    outcome: str
    chats: int = 0
    read: int = 0  # 두뇌를 부른 묶음
    reused: int = 0
    not_preread: int = 0  # 예전 칸(17.11.1 부터 늘 0 — 요약 꼴을 그대로 둔다)
    failed: int = 0

    def summary(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in ("outcome", "chats", "read", "reused", "not_preread", "failed")}


def switched_on(session: Any, cfg: Optional[PanelSettings] = None) -> bool:
    """미리 읽어도 되나 — 사진 · 그림 읽기 켬 · 비상 정지 아님 · 초안 끔 아님(DB 에서 새로 읽는다). 견적 계산 넣기와 상관없다."""
    cfg = cfg or read_settings(session, log=False)
    return image_mode(cfg) != MODE_OFF and read_switch(session) and draft_mode(session) != DRAFT_OFF


def _waiting_chats(session: Any, now: datetime.datetime) -> list[tuple[str, datetime.datetime]]:
    """그림 줄이 아직 없는 손님 파일 글이 있는 미답 상담(마지막 손님 글 시각과 함께) — 새 것부터."""
    at = naive_utc(now)
    msg, img = CsAgentMessage, CsAgentImageRead
    stmt = (select(CsAgentChat.chat_id, CsAgentChat.last_user_at)
            .join(msg, and_(msg.chat_id == CsAgentChat.chat_id, msg.person_type == "user", msg.has_file.is_(True),
                            msg.is_private.is_(False), msg.is_log.is_(False), msg.created_at >= at - WINDOW))
            .outerjoin(img, and_(img.chat_id == msg.chat_id, img.message_id == msg.message_id))
            .where(CsAgentChat.brand == BRAND, CsAgentChat.last_user_at >= at - WINDOW,
                   CsAgentChat.last_user_at <= at - SETTLE, img.id.is_(None),
                   or_(CsAgentChat.last_answer_at.is_(None), CsAgentChat.last_answer_at < msg.created_at))
            .group_by(CsAgentChat.chat_id, CsAgentChat.last_user_at)
            .order_by(CsAgentChat.last_user_at.desc()).limit(MAX_CHATS * 4))
    return [(row.chat_id, row.last_user_at) for row in session.execute(stmt)]


def _one_chat(session: Any, chat_id: str, *, reader: Any, cfg: PanelSettings, now: datetime.datetime,
              result: PrereadResult, stop: StopFlag, deps: dict[str, Any]) -> bool:
    """상담 하나 — 읽었으면(또는 건너뜀을 적었으면) 참, 파일 정보가 없으면 거짓."""
    lines = read_lines(reader, BRAND, chat_id)
    refs = pending_files(lines, limit=int(cfg.get("image_per_turn")))
    if not refs:
        return False
    outcome = read_batch(session, reader=reader, brand=BRAND, chat_id=chat_id, refs=refs, turns=conversation(lines),
                         cfg=cfg, now=now, owner=claim_owner("image"),
                         deadline_s=float(cfg.get("image_preread_timeout_s")),
                         still_on=lambda: switched_on(session), stop=stop, **deps)
    if outcome is None or (outcome.read is None and outcome.usage is None and not outcome.reused):
        result.failed += 1
    elif outcome.reused:
        result.reused += 1
    else:
        result.read += 1
    return True


def run_preread_tick(session: Any, *, memory: PrereadMemory, stop: Optional[StopFlag] = None,
                     reader: Optional[Any] = None, now: Optional[datetime.datetime] = None,
                     clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                     client: Any = None, transport: Any = None, lock_key: str = PREREAD_LOCK_KEY) -> PrereadResult:
    """미리 읽기 한 차례(모듈 설명의 순서). 꺼진 차례 · 대표가 아닌 차례 · 멈춘 차례는 일 0.

    Raises:
        SQLAlchemyError: DB 오류 — 러너가 기록하고 다음 차례로 간다.
    """
    stop = stop or StopFlag()
    now = (now or now_kst()).astimezone(KST)
    if stop.is_set():
        return PrereadResult(OUTCOME_STOPPED)
    cfg = read_settings(session, log=False)
    on = switched_on(session, cfg)
    session.commit()
    if not on:
        return PrereadResult(OUTCOME_IDLE)
    with leader_lock(session.get_bind(), lock_key) as leader:
        if not leader:
            return PrereadResult(OUTCOME_NOT_LEADER)
        result = PrereadResult(OUTCOME_OK)
        chats = [(c, at) for c, at in _waiting_chats(session, now) if not memory.skip(c, at)][:MAX_CHATS]
        session.commit()
        reader = reader or OpenApiReader(sleep=stop.reader_sleep)
        deps = {"clock": clock, "sleep": sleep, "client": client, "transport": transport}
        for chat_id, last_user_at in chats:
            if stop.is_set():
                result.outcome = OUTCOME_STOPPED
                break
            result.chats += 1
            try:
                if not _one_chat(session, chat_id, reader=reader, cfg=cfg, now=now, result=result, stop=stop,
                                 deps=deps):
                    memory.remember(chat_id, last_user_at)
            except PassStopped:
                session.rollback()
                result.outcome = OUTCOME_STOPPED
                break
            except ChannelRateLimited:
                logger.warning("[CS 그림] 채널톡 읽기 한도 — 이번 차례 그만 chat=%s", chat_id)
                break
            except ChannelReadError as exc:
                logger.warning("[CS 그림] 상담 글 읽기 실패 chat=%s status=%s", chat_id, exc.status)
                result.failed += 1
        return result
