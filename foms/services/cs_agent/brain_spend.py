"""두뇌 돈 줄 · 오류 꼴 — 하루 상한(env) · 오늘 돈(예약 포함) · 예약 · 바로잡기와 두뇌가 올리는 오류(플랜 C3-2 · 설계서 11.1 의 6).

:mod:`.brain` 이 부르고 이름을 그대로 내보낸다(500줄 상한으로 옮겼다 — 부르는 쪽은 ``brain.`` 이름을 그대로 쓴다).
관리 화면 하루 상한(:mod:`.settings`)은 env 아래로만 자른다 — 둘 가운데 작은 값을 :mod:`.brain` 이 이 모듈에 넘긴다.

- **돈 줄**: SystemSetting :data:`SPEND_KEY` 한 줄. 값 ``{"date": "YYYY-MM-DD"(KST), "usd": 바로잡은 돈, "reserved": 부르는 중
  예약 합, "calls": 보낸 수}``. 죽어서 바로잡지 못한 예약은 그날 내내 남는다(막는 쪽).
- **막는 쪽으로 닫힘**: env 상한이 없거나 틀리면 · 돈 줄 꼴이 틀리면 :class:`BrainNotReady`. 상한 이상이면
  :class:`SpendCapReached`. 오류 글에는 코드 · 숫자만 싣는다.
- **WORKER 상한 알리기**: env 는 두뇌가 도는 WORKER(감시 루프) 것만 쓴다. 루프 러너가 바퀴마다 자기 env 상한을 하트비트
  metadata :data:`HEARTBEAT_CAP_KEY` 칸에 남기고(:func:`heartbeat_cap_value`), 관리 화면(web)은 env 를 읽지 않고 그 값을
  본다(:func:`worker_daily_cap`). 모르면 '확인 안 됨'이다 — 돈은 늘 WORKER 가 부를 때 자기 env 로 다시 자른다.
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.cs_agent.state import KST
from foms.services.datetime_kst import now_kst
from foms.services.sidefx_worker import WORKER_KIND_CS_LOOP
from models import SideEffectWorkerHeartbeat, SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "DAILY_CAP_ENV", "HEARTBEAT_CAP_KEY", "SPEND_KEY", "BrainError", "BrainNotReady", "BrainUnavailable",
    "SpendCapReached", "WorkerCap", "add_spend", "check_budget", "daily_cap_usd", "heartbeat_cap_value", "kst_now",
    "reserve_spend", "settle_spend", "spent_today", "today_spend", "worker_daily_cap",
]

DAILY_CAP_ENV = "FOMS_CS_BRAIN_DAILY_USD"  # 하루 상한(달러) = 콘솔 월 상한 ÷ 30(11.1 의 6 ②) — 관리 화면 값의 천장
#: 오늘 돈 줄 SystemSetting 키(두뇌만 쓴다).
SPEND_KEY = "cs_agent_brain_spend"
#: 감시 루프(CS_LOOP) 하트비트 metadata 에서 WORKER env 하루 상한(달러 글, 없거나 틀리면 ``None``)을 담는 칸.
HEARTBEAT_CAP_KEY = "daily_cap_usd"
CAP_KNOWN, CAP_ABSENT, CAP_UNKNOWN = "ok", "missing", "unknown"  # WORKER 상한: 앎 · WORKER 에 없음 · 확인 안 됨

# 오류 코드 — BrainNotReady(부르지 않음 · 키 거절) · SpendCapReached(돈 상한) · BrainUnavailable(불렀는데 못 씀)
BRAND_NOT_ENABLED, BRAND_MISMATCH, NO_KNOWLEDGE = "brand_not_enabled", "brand_mismatch", "no_knowledge"
NO_API_KEY, SDK_DEBUG_LOGGING, API_AUTH = "no_api_key", "sdk_debug_logging", "api_auth"
CAP_MISSING, CAP_INVALID, SPEND_RECORD_INVALID = "daily_cap_missing", "daily_cap_invalid", "spend_record_invalid"
DAILY_CAP_REACHED, API_SPEND_LIMIT = "daily_cap_reached", "api_spend_limit"
TIMEOUT, RATE_LIMITED, API_ERROR, BAD_RESPONSE = "timeout", "rate_limited", "api_error", "bad_response"
_MICRO = Decimal("0.000001")


# ── 오류 ─────────────────────────────────────────────────────────────────
class BrainError(RuntimeError):
    """두뇌를 부르지 않았거나 답을 쓸 수 없다 — 호출부는 :attr:`code` 로 가른다. 글(손님 글 · 오류 본문)은 싣지 않는다."""

    title = "두뇌 오류"

    def __init__(self, code: str, *, status: Optional[int] = None, request_id: Optional[str] = None) -> None:
        """코드 · HTTP 상태 · 요청 id(지원 문의용)만 싣는다."""
        self.code, self.status, self.request_id = code, status, request_id
        super().__init__(f"{self.title} — {code}" + (f" (HTTP {status})" if status else ""))


class BrainNotReady(BrainError):
    """설정 · 재료 · 브랜드가 준비되지 않았다 — 부르기 전에 알았거나 API 가 키 · 권한을 거절했다(401 · 403, 돈 0)."""

    title = "두뇌를 부르지 않는다"


class SpendCapReached(BrainError):
    """돈 상한 — 코드 하루 상한(``daily_cap_reached`` — 예약 포함)이나 콘솔 상한 응답(``api_spend_limit``). 다시 하지 않는다."""

    title = "돈 상한 — 더 부르지 않는다"


class BrainUnavailable(BrainError):
    """불렀는데 쓸 답이 없다 — ``timeout`` · ``rate_limited`` · ``api_error`` · ``bad_response``. 그 차례는 사람에게."""

    title = "두뇌 호출 실패"


# ── 하루 상한 · 오늘 돈 ──────────────────────────────────────────────────
def kst_now(now: Optional[datetime.datetime]) -> datetime.datetime:
    """지금(KST). 시간대 없는 시각은 거절한다(UTC · KST 가 섞이면 조용히 틀린다)."""
    value = now if now is not None else now_kst()
    if value.tzinfo is None:
        raise ValueError("시간대가 없는 시각은 받지 않는다")
    return value.astimezone(KST)


def daily_cap_usd(environ: Optional[Mapping[str, str]] = None) -> Decimal:
    """하루 상한(달러) — env :data:`DAILY_CAP_ENV`. 없거나 틀리면(숫자 아님 · 음수 · 무한) :class:`BrainNotReady`."""
    raw = (os.environ if environ is None else environ).get(DAILY_CAP_ENV)
    if raw is None or not raw.strip():
        raise BrainNotReady(CAP_MISSING)
    try:
        cap = Decimal(raw.strip())
    except InvalidOperation:
        raise BrainNotReady(CAP_INVALID) from None
    if not cap.is_finite() or cap < 0:
        raise BrainNotReady(CAP_INVALID)
    return cap


def heartbeat_cap_value(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """루프 러너가 하트비트에 남길 이 프로세스(WORKER)의 env 하루 상한 글 — 없거나 틀리면 ``None``."""
    try:
        return str(daily_cap_usd(environ))
    except BrainNotReady:
        return None


@dataclass(frozen=True)
class WorkerCap:
    """WORKER 가 마지막 하트비트에 남긴 env 하루 상한. ``state`` — 앎(``ok``) · WORKER 에 env 없음 · 틀림(``missing``) ·
    하트비트나 칸이 없어 모름(``unknown``). ``seen_at`` 은 그 하트비트 시각(UTC naive)."""

    cap: Optional[Decimal]
    state: str
    seen_at: Optional[datetime.datetime] = None


def worker_daily_cap(session: Any) -> WorkerCap:
    """감시 루프 하트비트에서 WORKER env 하루 상한을 읽는다(잠그지 않는다). 꼴이 틀린 값은 WORKER 에 없는 것으로 본다."""
    row = session.get(SideEffectWorkerHeartbeat, WORKER_KIND_CS_LOOP, populate_existing=True)
    meta = row.metadata_json if row is not None and isinstance(row.metadata_json, dict) else None
    if meta is None or HEARTBEAT_CAP_KEY not in meta:
        return WorkerCap(None, CAP_UNKNOWN)
    raw = meta.get(HEARTBEAT_CAP_KEY)
    try:
        cap = Decimal(str(raw)) if isinstance(raw, (str, int)) and not isinstance(raw, bool) else None
    except InvalidOperation:
        cap = None
    if cap is None or not cap.is_finite() or cap < 0:
        return WorkerCap(None, CAP_ABSENT, row.last_heartbeat_at)
    return WorkerCap(cap, CAP_KNOWN, row.last_heartbeat_at)


def _money(raw: Any) -> Decimal:
    """저장된 돈 값 하나(0 이상 · 유한). 틀리면 :class:`BrainNotReady` — 막는 쪽으로 닫힌다."""
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise BrainNotReady(SPEND_RECORD_INVALID) from None
    if not value.is_finite() or value < 0:
        raise BrainNotReady(SPEND_RECORD_INVALID)
    return value


def _stored(value: Any, day: str) -> tuple[Decimal, Decimal, int]:
    """저장 값 → 그날 (바로잡은 돈, 예약, 보낸 수)(다른 날이면 0). 꼴이 틀리면 :class:`BrainNotReady`."""
    if value is None or value == {}:
        return Decimal(0), Decimal(0), 0
    if not isinstance(value, dict) or not isinstance(value.get("date"), str):
        raise BrainNotReady(SPEND_RECORD_INVALID)
    if value["date"] != day:
        return Decimal(0), Decimal(0), 0
    calls = value.get("calls")
    return _money(value.get("usd")), _money(value.get("reserved", "0")), calls if isinstance(calls, int) else 0


def spent_today(session: Any, *, now: Optional[datetime.datetime] = None) -> Decimal:
    """오늘(KST) 상한에 드는 돈 = 바로잡은 돈 + 부르는 중 예약(잠그지 않고 읽는다)."""
    row = session.get(SystemSetting, SPEND_KEY, populate_existing=True)
    usd, reserved, _ = _stored(row.setting_value if row is not None else None, kst_now(now).date().isoformat())
    return usd + reserved


def today_spend(session: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """관리 화면 읽기판 — 오늘(KST) 바로잡은 돈 · 예약 · 보낸 수(잠그지 않고 읽는다). 꼴이 틀리면 ``problem`` 코드만(던지지 않는다)."""
    day = kst_now(now).date().isoformat()
    row = session.get(SystemSetting, SPEND_KEY, populate_existing=True)
    try:
        usd, reserved, calls = _stored(row.setting_value if row is not None else None, day)
    except BrainNotReady as exc:
        return {"date": day, "usd": None, "reserved": None, "calls": None, "problem": exc.code}
    return {"date": day, "usd": str(usd), "reserved": str(reserved), "calls": calls, "problem": None}


def check_budget(session: Any, *, cap: Optional[Decimal] = None, now: Optional[datetime.datetime] = None) -> Decimal:
    """부르기 전 돈 확인 — 오늘 돈(예약 포함)이 상한(없으면 env) 이상이면 :class:`SpendCapReached`. 오늘 돈을 돌려준다."""
    limit = daily_cap_usd() if cap is None else cap
    spent = spent_today(session, now=now)
    if spent >= limit:
        logger.warning("[CS 두뇌] 오늘 돈이 하루 상한에 닿아 부르지 않는다 key=%s spent=%s cap=%s", SPEND_KEY, spent, limit)
        raise SpendCapReached(DAILY_CAP_REACHED)
    return spent


# ── 예약 · 바로잡기 ──────────────────────────────────────────────────────
def _locked_row(session: Any) -> Any:
    """돈 줄을 잠가 읽는다(없으면 먼저 만들어 커밋 — 같은 때 다른 쪽이 만들었으면 그 줄)."""
    if session.get(SystemSetting, SPEND_KEY) is None:
        session.add(SystemSetting(setting_key=SPEND_KEY, setting_value={},
                                  description="AI 상담팀원 두뇌 — 오늘(KST) 돈 · 예약(플랜 C3-2, 하루 상한 확인)"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, SPEND_KEY, populate_existing=True, with_for_update=True)


def _put(row: Any, day: str, usd: Decimal, reserved: Decimal, calls: int) -> None:
    """돈 줄 새 값(버전 +1). 커밋은 부르는 쪽."""
    row.setting_value = {"date": day, "usd": str(usd), "reserved": str(reserved.quantize(_MICRO)), "calls": calls}
    flag_modified(row, "setting_value")
    row.version = int(row.version or 1) + 1


def _read_locked(session: Any, now: Optional[datetime.datetime]) -> tuple[Any, str, Decimal, Decimal, int]:
    """잠근 돈 줄과 오늘 값. 꼴이 틀리면 되돌려 잠금을 풀고 :class:`BrainNotReady`."""
    row, day = _locked_row(session), kst_now(now).date().isoformat()
    try:
        return (row, day, *_stored(row.setting_value, day))
    except BrainNotReady:
        session.rollback()
        raise


def reserve_spend(session: Any, amount: Decimal, *, cap: Decimal, now: Optional[datetime.datetime] = None) -> Decimal:
    """보내기 전 최악값을 예약하고 커밋한다(원장 R7-3). 예약 합을 돌려준다.

    줄 ``FOR UPDATE`` 안에서 '바로잡은 돈 + 예약 + 이번 값'이 상한을 넘으면 되돌리고 :class:`SpendCapReached` — 바퀴가
    겹쳐도(두 컨테이너) 둘째는 첫째 예약을 보고 멈춘다.
    """
    row, day, usd, reserved, calls = _read_locked(session, now)
    if usd + reserved + Decimal(amount) > cap:
        session.rollback()
        logger.warning("[CS 두뇌] 예약하면 하루 상한을 넘어 부르지 않는다 key=%s spent=%s reserved=%s need=%s cap=%s",
                       SPEND_KEY, usd, reserved, amount, cap)
        raise SpendCapReached(DAILY_CAP_REACHED)
    _put(row, day, usd, reserved + Decimal(amount), calls)
    session.commit()
    return reserved + Decimal(amount)


def settle_spend(session: Any, reserved_amount: Decimal, cost: Decimal, *,
                 now: Optional[datetime.datetime] = None) -> Decimal:
    """예약을 실제 돈으로 바로잡고 커밋한다 — 예약을 빼고(0 아래로 안 내림) ``cost`` 를 더하고 보낸 수 +1. 바로잡은 돈 합을 돌려준다.

    날이 바뀐 뒤면 옛 날 예약은 이미 0 으로 본다(다른 날 값은 세지 않는다) — 돈은 오늘 합에 더한다.
    """
    row, day, usd, reserved, calls = _read_locked(session, now)
    usd += Decimal(cost)
    _put(row, day, usd, max(Decimal(0), reserved - Decimal(reserved_amount)), calls + 1)
    session.commit()
    return usd


def add_spend(session: Any, cost_usd: Decimal, *, now: Optional[datetime.datetime] = None) -> Decimal:
    """쓴 돈을 오늘 합에 더해 커밋한다(예약 없이 — :func:`settle_spend` 의 예약 0). 새 합을 돌려준다."""
    return settle_spend(session, Decimal(0), cost_usd, now=now)
