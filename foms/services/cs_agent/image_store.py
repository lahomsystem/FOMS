"""그림 읽기 표 — 줄 만들기 · 선점 · 하루 장수 · 결과 · 건너뜀 쓰기 · 기록 탭 숫자(설계서 17.11 (e) · (f)).

표(``cs_agent_image_reads``)에는 숫자 · 코드만 둔다 — 그림 바이트 · 파일 key · 주소 · 파일 이름 · 모델 글은 칸이 없다.
선점은 조건부 쓰기 하나(기다림 · 실패 · 다시 볼 건너뜀 · 결과 · 만료가 지난 읽는 중만)라 미리 읽기 길과 초안 차례가 같은
그림을 두 번 읽지 않는다. 건너뜀은 둘이다 — **굳은 건너뜀**(꼴 · 크기 · 얼굴 · 거르기 고장 · PDF 훑기 실패)은 다시 보내지
않고, **무른 건너뜀**(하루 상한 · 미리 읽기 밖 · 스위치)은 다음 차례가 다시 집을 수 있다.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import and_, func, or_, select, update

from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_prep import (
    SKIP_CAP, SKIP_FACE, SKIP_FACE_CHECK, SKIP_FORMAT, SKIP_PDF, SKIP_SIZE,
)
from foms.services.cs_agent.state_store import _insert_ignore
from models import CsAgentImageRead

__all__ = [
    "DISCARDED", "DONE", "FAILED", "HARD_SKIPS", "PENDING", "READING", "SKIPPED", "SKIP_NOT_PREREAD", "SKIP_SWITCH",
    "SOFT_SKIPS", "STATES", "claim", "ensure_rows", "finish", "image_view", "reuse_by_sha", "sent_today", "set_skip",
]

PENDING, READING, DONE, SKIPPED, FAILED, DISCARDED = "pending", "reading", "done", "skipped", "failed", "discarded"
STATES: tuple[str, ...] = (PENDING, READING, DONE, SKIPPED, FAILED, DISCARDED)
SKIP_NOT_PREREAD, SKIP_SWITCH = "not_preread", "skipped_switch"
DISCARDED_FACE = "discarded_face"
HARD_SKIPS = frozenset({SKIP_FORMAT, SKIP_SIZE, SKIP_FACE, SKIP_FACE_CHECK, SKIP_PDF})
SOFT_SKIPS = frozenset({SKIP_CAP, SKIP_NOT_PREREAD, SKIP_SWITCH})
_T = CsAgentImageRead
UTC = datetime.timezone.utc


def _naive(when: datetime.datetime) -> datetime.datetime:
    """표에 둘 UTC naive(시간대 없는 값은 이미 UTC naive 로 본다 — 관리 화면 하루 시작)."""
    return when if when.tzinfo is None else when.astimezone(UTC).replace(tzinfo=None)


def ensure_rows(session: Any, brand: str, chat_id: str, refs: Sequence[FileRef],
                now: datetime.datetime) -> list[CsAgentImageRead]:
    """파일마다 줄(없으면 ``pending`` 으로 넣는다 — 있으면 그대로)을 ``refs`` 차례로 돌려준다. 커밋은 부르는 쪽."""
    if not refs:
        return []
    rows = [{"brand": brand, "chat_id": chat_id, "message_id": ref.message_id, "file_index": ref.file_index,
             "state": PENDING, "attempts": 0, "created_at": _naive(now)} for ref in refs]
    _insert_ignore(session, _T.__table__, rows, ("chat_id", "message_id", "file_index"))
    keys = {(ref.message_id, ref.file_index) for ref in refs}
    stmt = (select(_T).where(_T.chat_id == chat_id, _T.message_id.in_({k[0] for k in keys}))
            .execution_options(populate_existing=True))
    found = {(row.message_id, row.file_index): row for row in session.scalars(stmt)}
    return [found[(ref.message_id, ref.file_index)] for ref in refs]


def _claimable(now: datetime.datetime, *, reread: bool) -> Any:
    """선점할 수 있는 줄 조건 — ``reread`` 면 결과 있는 줄도(새 그림이 묶음에 들어와 다시 읽는다)."""
    states = [PENDING, FAILED, *((DONE, DISCARDED) if reread else ())]
    return or_(_T.state.in_(states), and_(_T.state == SKIPPED, _T.skip_code.in_(SOFT_SKIPS)),
               and_(_T.state == READING, _T.claim_expires_at < _naive(now)))


def claim(session: Any, rows: Sequence[CsAgentImageRead], *, owner: str, until: datetime.datetime,
          now: datetime.datetime, reread: bool = False) -> bool:
    """줄들을 한 번에 선점하고 커밋한다 — 모두 잡았으면 참, 하나라도 남이 쥐고 있으면 아무것도 잡지 않는다(되돌림)."""
    ids = [row.id for row in rows]
    stmt = (update(_T).where(_T.id.in_(ids), _claimable(now, reread=reread))
            .values(state=READING, claim_owner=owner[:64], claim_expires_at=_naive(until), attempts=_T.attempts + 1)
            .execution_options(synchronize_session=False))
    if session.execute(stmt).rowcount != len(ids):
        session.rollback()
        return False
    session.commit()
    for row in rows:
        session.refresh(row)
    return True


def set_skip(row: CsAgentImageRead, code: str, now: datetime.datetime, *, state: str = SKIPPED,
             sha256: Optional[str] = None) -> None:
    """건너뜀 · 실패 · 버림 하나 — 선점을 놓는다(커밋은 부르는 쪽)."""
    row.state, row.skip_code = state, code[:32]
    row.claim_owner = row.claim_expires_at = None
    if sha256:
        row.sha256 = sha256
    if state != FAILED:
        row.read_at = _naive(now)


def finish(rows: Sequence[CsAgentImageRead], *, result: dict[str, Any], state: str, confidence: str,
           personal: Sequence[str], usage: Optional[dict[str, Any]], now: datetime.datetime,
           shas: Sequence[str], turn_id: Optional[int] = None) -> None:
    """묶음 결과를 줄마다 쓴다(같은 결과 · 선점 놓기). 토큰 · 돈은 첫 줄에만(합이 한 번만 세이게). 커밋은 부르는 쪽."""
    for number, (row, sha) in enumerate(zip(rows, shas)):
        row.state, row.skip_code = state, DISCARDED_FACE if state == DISCARDED else None
        row.result, row.confidence, row.personal_codes = dict(result), confidence, list(personal)
        row.sha256, row.read_at, row.turn_id = sha, _naive(now), turn_id
        row.claim_owner = row.claim_expires_at = None
        lead = usage if number == 0 and usage else {}
        row.model, row.effort = (usage or {}).get("model"), (usage or {}).get("effort")
        row.input_tokens, row.output_tokens = lead.get("input_tokens"), lead.get("output_tokens")
        row.cost_usd, row.latency_ms = lead.get("cost_usd"), lead.get("latency_ms")


def sent_today(session: Any, day_start: datetime.datetime, *, chat_id: Optional[str] = None) -> int:
    """오늘(KST 0시 뒤) 모델에 보낸 장수 — 모델 칸이 찬 줄(묶음의 모든 줄)."""
    stmt = select(func.count()).select_from(_T).where(_T.read_at >= _naive(day_start), _T.model.isnot(None))
    if chat_id is not None:
        stmt = stmt.where(_T.chat_id == chat_id)
    return int(session.scalar(stmt) or 0)


def reuse_by_sha(session: Any, chat_id: str, shas: Sequence[str],
                 usable: Callable[[str, Any], bool] = lambda _state, _result: True) -> Optional[CsAgentImageRead]:
    """같은 상담에서 같은 그림 묶음(sha256 차례가 같음)을 이미 읽은 줄 — 같은 그림 재전송은 앞 결과를 쓴다(사진 교훈 1-12).
    ``usable(상태, 결과)`` 가 거짓인 줄(옛 판 결과 — :func:`.image_read.current`)은 건너뛴다."""
    stmt = (select(_T).where(_T.chat_id == chat_id, _T.state.in_((DONE, DISCARDED)), _T.sha256.in_(set(shas)))
            .order_by(_T.read_at.desc()))
    for row in session.scalars(stmt):
        if (isinstance(row.result, dict) and list(row.result.get("batch") or ()) == list(shas)
                and usable(row.state, row.result)):
            return row
    return None


def _counts(rows: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, count in rows:
        out[str(key)] = out.get(str(key), 0) + int(count)
    return out


def image_view(session: Any, since: datetime.datetime) -> dict[str, Any]:
    """기록 탭 숫자(오늘 — 손님 정보 없음): 상태별 · 건너뜀 까닭별 · 보낸 장수 · 돈 · 평균 시간 · 보인 개인정보 종류 수."""
    start = _naive(since)
    base = (_T.created_at >= start)
    states = _counts(session.execute(select(_T.state, func.count()).where(base).group_by(_T.state)))
    skips = _counts(session.execute(select(_T.skip_code, func.count()).where(base, _T.skip_code.isnot(None))
                                    .group_by(_T.skip_code)))
    sent = sent_today(session, since)
    money = session.execute(select(func.sum(_T.cost_usd), func.avg(_T.latency_ms))
                            .where(_T.read_at >= start, _T.input_tokens.isnot(None))).one()
    personal: dict[str, int] = {}
    for codes in session.scalars(select(_T.personal_codes).where(_T.read_at >= start, _T.personal_codes.isnot(None))):
        for code in codes if isinstance(codes, list) else ():
            personal[str(code)] = personal.get(str(code), 0) + 1
    return {"by_state": states, "by_skip": skips, "sent": sent,
            "cost_usd": str(Decimal(money[0] or 0).quantize(Decimal("0.0001"))),
            "avg_latency_ms": int(money[1] or 0), "personal": personal}
