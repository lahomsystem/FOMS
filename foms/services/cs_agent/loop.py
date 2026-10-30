"""감시 루프 한 바퀴 — 바로 끄기 · 멈춤 깃발 · 대표 잠금 → 수신 기록 → 채널톡 보정 → 상태 → 경보 · 아침 보고.

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C1-3 · 설계서 3.2 · 6절 · 15.2 의 8 · 15.5. WORKER 감독자 자식
``cs_loop``(``scripts/maintenance/run_cs_loop.py``)가 15분마다 :func:`run_pass` 를 부른다. 실시간 길(C6-1)도 이 루프가
맡을 자리라 바퀴를 단계 함수로 나눠 두었다. 경보 · 아침 보고를 언제 · 한 번만 내는지는 :mod:`.report`.

- **채널톡 쓰기 0 · AI 0 · RQ 0**: 채널톡은 GET 만(두 브랜드 다 읽기만), 알림은 FOMS 앱 안 알림만. 초안 스위치
  (:func:`.turns.draft_mode`)가 ``store`` · ``memo`` 일 때만 바퀴 끝에 :mod:`.drafting` 이 라홈 초안을 쓴다(두뇌 · 내부 메모).
  스위치가 없거나 꺼져 있으면(기본) 바퀴는 그대로다. 관리 화면의 빠른 길 스위치가 켜져 있으면 초안은 빠른 길
  (:mod:`.realtime` — 따로 도는 실행 단위 · 따로 잠금)의 몫이라 이 바퀴는 보정 · 아침 보고만 한다(설계서 17.3). 직원이 데스크에서
  직접 보낸 답을 끝난 차례에 사례로 붙이는 일(:mod:`.case_memory` — 상담 글 GET 만)도 초안을 쓰는 쪽 하나만 한다.
- **바로 끄기(설계서 6절)**: SystemSetting :data:`SWITCH_KEY` 를 매 바퀴 읽는다(``{"loop": "off"}`` 면 그 바퀴 일 0).
  env(``FOMS_CS_LOOP_ENABLED``)는 켜기용이다 — Railway env 는 재배포 전엔 안 바뀐다(원장 R2-15). 쓰기(:func:`set_switch`)는
  줄을 잠그고 새로 읽은 값에 ``loop`` 칸만 얹은 뒤 읽은 판(version)일 때만 쓴다 — 초안 스위치 쓰기와 겹쳐도 서로 덮지 않는다
  (원장 R10-31).
- **멈춤 깃발(R4-4)**: TERM 을 받으면 일을 집기 전 · 쓰기 전마다 :meth:`StopFlag.check` 가 바퀴를 멈춘다. 이미 읽은
  채널톡 글은 버린다 — 깃발 뒤에는 쓰기를 시작하지 않는다.
- **대표 하나(R4-10)**: 바퀴마다 따로 연 연결로 ``pg_try_advisory_lock`` 을 잡고, 못 잡으면 그 바퀴를 건너뛴다.
- **시간 상한 · 맨 뒤(R4-13 · R4-17)**: 채널톡 보정은 브랜드마다 시간 상한 안에서 바뀐 상담을 오래된 것부터 맞추고,
  남은 상담은 다음 바퀴가 잇는다. 창 시작은 상태 표에 반영한 마지막 ``updatedAt`` 이다(커서를 따로 두지 않는다 — R4-16).
  키가 없으면(:class:`OpenApiNotConfigured`) 그 브랜드 보정만 건너뛰고 바퀴는 끝까지 돈다.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional, Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from foms.services.common.business_calendar import is_business_day as calendar_is_business_day
from foms.services.cs_agent import report
from foms.services.cs_agent.channel_read import (
    ChannelRateLimited,
    ChannelReadError,
    ChatSnapshot,
    DerivedMessage,
    OpenApiNotConfigured,
    OpenApiReader,
    aware_utc,
    naive_utc,
)
from foms.services.cs_agent.state import KST, BusinessDayFn
from foms.services.cs_agent.state_store import (
    apply_api_messages,
    apply_chat_snapshots,
    compute_open_states,
    ingest_inbound,
)
from foms.services.common.table_version_counter import mark_tables_dirty
from foms.services.cs_agent.case_memory import PASS_LIMITS, attach_staff_replies
from foms.services.cs_agent.drafting import DraftSummary, run_drafting
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import DRAFT_OFF, SWITCH_OFF, SWITCH_ON, draft_mode, read_switch
from foms.services.datetime_kst import now_kst
from models import CsAgentChat, SystemSetting

logger = logging.getLogger(__name__)

UTC = datetime.timezone.utc

#: 바로 끄기 SystemSetting 키(관리자가 쓴다 — ``run_cs_loop.py --switch off``). 값 ``{"loop": "on" | "off"}``.
#: 뒤 단계의 스위치(메모 · 브랜드 · 의도)도 이 한 줄에 칸으로 더한다(설계서 6절 '키 하나').
SWITCH_KEY = "cs_agent_switch"
LEADER_LOCK_KEY = "foms:cs_agent_loop"

BRANDS: tuple[str, ...] = ("LAHOM", "HAUD")
DEFAULT_INTERVAL_SECONDS = 900
#: 바퀴마다 채널톡 보정에 쓰는 시간 합(초, 브랜드끼리 나눈다). 15분 간격 · 정지 유예와 견주어 짧게 둔다.
RECONCILE_BUDGET_SECONDS = 120.0
#: 15분 바퀴의 수신 기록 뒤돌아 읽기 줄 수(실시간 몇 초 바퀴의 500 보다 넓게 — 15분 사이 쌓인 줄을 다 덮는다).
PASS_INGEST_LOOKBACK = 2000
RECONCILE_OVERLAP = datetime.timedelta(minutes=10)  # 창 시작을 이만큼 앞당겨 시계 차 · 늦은 반영을 덮는다
INITIAL_RECONCILE_LOOKBACK = datetime.timedelta(days=30)  # 처음 · 오래 멈춘 뒤의 창(Open API 목록 상한)
MIN_RECONCILE_WINDOW = datetime.timedelta(minutes=1)
MAX_CHAT_ERRORS = 5  # 한 브랜드에서 상담 글 읽기가 이만큼 실패하면 그 바퀴 보정을 멈춘다

OUTCOME_OK, OUTCOME_KILLED, OUTCOME_NOT_LEADER, OUTCOME_STOPPED = "ok", "killed", "not_leader", "stopped"
CHECK_OK, CHECK_PARTIAL, CHECK_NOT_CONFIGURED = "ok", "partial", "not_configured"
CHECK_RATE_LIMITED, CHECK_ERROR = "rate_limited", "error"


# ── 바로 끄기 ────────────────────────────────────────────────────────────
# 읽기(:func:`read_switch` — 줄이 없거나 ``{"loop": "on"}`` 이면 돈다, 꼴이 틀리면 끈 것)는 :mod:`.turns` 에 있다 — 초안 바퀴도
# 두뇌를 부르기 전마다 같은 함수로 다시 읽는다(초안 바퀴가 이 모듈을 import 하지 않게).
#: 판이 그사이 바뀌어 다시 읽는 횟수 — 비상 정지는 버전 충돌로 실패하면 안 되니 몇 번 다시 한다.
SWITCH_WRITE_TRIES = 3


class SwitchConflict(RuntimeError):
    """바로 끄기 쓰기가 몇 번 다시 읽어도 판(version)이 계속 바뀌었다(값은 쓰지 않았다)."""


def set_switch(session: Any, *, on: bool, now: Optional[datetime.datetime] = None) -> dict:
    """바로 끄기 값을 쓰고 커밋한다(관리자 스크립트 · 관리 화면). ``loop`` · ``changed_at`` 칸만 바꾸고 다른 칸은 그대로 둔다.

    줄을 ``FOR UPDATE`` 로 잠그고 **새로 읽은** 값에 칸을 얹은 뒤, 읽은 판(version)과 같을 때만 쓴다(조건부 UPDATE —
    판 +1). 판이 그사이 바뀌었으면(잠금이 없는 DB · 다른 쓰기) 다시 읽어 :data:`SWITCH_WRITE_TRIES` 번까지 한다 — 초안
    스위치(:func:`.turns.set_draft_mode`)를 옛 값으로 되돌리지 않는다(원장 R10-31). 관리 화면이 미리 넣은 수정 기록 ·
    감사 줄도 같은 커밋에 들어간다.

    Returns:
        새로 쓴 값.

    Raises:
        SwitchConflict: 다시 읽어도 판이 계속 바뀌었다.
    """
    stamp = naive_utc(now or datetime.datetime.now(UTC)).isoformat(timespec="seconds")
    for _ in range(SWITCH_WRITE_TRIES):
        row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True, with_for_update=True)
        old = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
        value = {**old, "loop": SWITCH_ON if on else SWITCH_OFF, "changed_at": stamp}
        if row is None:
            session.add(SystemSetting(setting_key=SWITCH_KEY, setting_value=value,
                                      description="AI 상담팀원 감시 루프 바로 끄기(매 바퀴 읽음, 플랜 C1-3)"))
            session.commit()
            return value
        read_version = int(row.version or 1)
        written = session.execute(
            update(SystemSetting)
            .where(SystemSetting.setting_key == SWITCH_KEY, SystemSetting.version == read_version)
            .values(setting_value=value, version=read_version + 1)
            .execution_options(synchronize_session="fetch")).rowcount
        if written == 1:
            mark_tables_dirty(session, SystemSetting.__tablename__)  # ORM 을 거치지 않은 쓰기 — 화면 304 카운터
            session.commit()
            return value
        logger.warning("[CS 감시] 바로 끄기 쓰기 중 판이 바뀌었다 — 다시 읽는다 key=%s", SWITCH_KEY)
    session.rollback()
    raise SwitchConflict("바로 끄기 줄의 판이 계속 바뀌었다 — 쓰지 않았다")


# ── 멈춤 깃발 · 대표 잠금 ────────────────────────────────────────────────
class PassStopped(Exception):
    """TERM 깃발이 선 뒤 — 바퀴를 그 자리에서 멈춘다(쓰기를 시작하지 않는다)."""


class StopFlag:
    """TERM 멈춤 깃발(원장 R4-4). 신호 처리기는 값 하나만 세운다 — 잠금을 잡지 않으니 처리기가 막히지 않는다.

    ``threading.Event.set`` 은 안쪽 잠금을 잡아, 같은 스레드가 그 잠금을 쥔 순간에 신호가 오면 처리기가 멈출 수 있다.
    """

    def __init__(self) -> None:
        """깃발은 내린 채 시작한다."""
        self._stopped = False

    def set(self, *_args: Any) -> None:
        """깃발을 세운다(``signal.signal`` 처리기 꼴 — 인자는 버린다)."""
        self._stopped = True

    def is_set(self) -> bool:
        """깃발이 섰는가."""
        return self._stopped

    def check(self) -> None:
        """깃발이 섰으면 :class:`PassStopped` — 일을 집기 전 · 쓰기 전에 부른다."""
        if self._stopped:
            raise PassStopped()

    def sleep(self, seconds: float, *, tick: float = 1.0) -> bool:
        """``seconds`` 동안 자되 깃발이 서면 ``tick`` 안에 깬다. 깃발이 섰으면 True."""
        deadline = time.monotonic() + max(0.0, float(seconds))
        while not self._stopped:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(tick, left))
        return self._stopped

    def reader_sleep(self, seconds: float) -> None:
        """채널톡 읽기 도우미의 기다림 — 깃발이 서면 :class:`PassStopped` (다시 시도를 이어 가 정지 유예를 넘기지 않게,
        원장 R5-7)."""
        if self.sleep(seconds):
            raise PassStopped()


_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


@contextmanager
def leader_lock(bind: Engine, key: str = LEADER_LOCK_KEY) -> Iterator[bool]:
    """대표 잠금 — 잡았으면 True 를 내고 나갈 때 푼다(원장 R4-10).

    PostgreSQL 은 따로 연 연결 하나로 세션 advisory lock 을 잡아 바퀴 내내 쥔다(일 세션이 커밋해도 안 풀린다). 연결이
    닫히면(프로세스가 죽어도) 서버가 잠금을 푼다. PostgreSQL 이 아니면(시험 · 로컬 SQLite) 프로세스 안 잠금이다.
    """
    if bind.dialect.name != "postgresql":
        with _LOCAL_LOCKS_GUARD:
            lock = _LOCAL_LOCKS.setdefault(key, threading.Lock())
        got = lock.acquire(blocking=False)
        try:
            yield got
        finally:
            if got:
                lock.release()
        return
    with bind.connect() as conn:
        # 옛 컨테이너가 연결을 정상 종료 없이 잃어도 서버가 약 2분 안에 그 연결을 끊어 잠금을 풀게 한다(기본은 약 2시간,
        # 원장 R5-5). 이 연결의 서버 쪽 TCP keepalive 만 바꾼다.
        conn.execute(text("SELECT set_config('tcp_keepalives_idle', '60', false), "
                          "set_config('tcp_keepalives_interval', '10', false), "
                          "set_config('tcp_keepalives_count', '6', false)"))
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": key}).scalar())
        conn.commit()  # 세션 잠금은 트랜잭션을 닫아도 남는다 — 'idle in transaction' 으로 두지 않는다
        try:
            yield got
        finally:
            if got:
                _unlock(conn, key)


def _unlock(conn: Any, key: str) -> None:
    """대표 잠금을 푼다. 풀지 못하면 그 연결을 버린다 — 잠금을 쥔 연결이 풀로 돌아가면 다음 바퀴가 대표를 못 잡는다."""
    try:
        released = bool(conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": key}).scalar())
        conn.commit()
    except SQLAlchemyError:
        logger.warning("[CS 감시] 대표 잠금 풀기 실패 — 연결을 버린다", exc_info=True)
        conn.invalidate()
        return
    if not released:
        logger.warning("[CS 감시] 대표 잠금이 이미 풀려 있었다 — 연결을 버린다")
        conn.invalidate()


# ── 설정 · 결과 ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class LoopConfig:
    """바퀴 설정 — 러너가 실행 환경에서 정한다(새 env 없음)."""

    watch_missing_inbound: bool = False  # 이 환경으로 웹훅이 오는가(운영만) — 아니면 수신 누락 경보를 끈다
    brands: tuple[str, ...] = BRANDS
    reconcile_budget_seconds: float = RECONCILE_BUDGET_SECONDS
    report_hour: int = report.REPORT_HOUR
    ingest_lookback: int = PASS_INGEST_LOOKBACK


def watch_missing_inbound_for(environment: str) -> bool:
    """수신 누락 경보를 켤 환경인가 — 채널톡 웹훅이 오는 운영만(스테이징 · 로컬엔 웹훅이 없어 모든 글이 '누락'이다)."""
    return environment == "production"


@dataclass
class BrandCheck:
    """한 브랜드 채널톡 보정 결과."""

    status: str = CHECK_OK
    listed: int = 0
    todo: int = 0
    done: int = 0
    errors: int = 0
    missing: list[report.MissingInbound] = field(default_factory=list)


@dataclass
class PassResult:
    """한 바퀴 결과 — 하트비트 · 로그 재료(상담 id · 손님 정보 없음)."""

    outcome: str
    ingested: int = 0
    checks: dict[str, BrandCheck] = field(default_factory=dict)
    needs_reply: dict[str, int] = field(default_factory=dict)
    alerts: dict[str, int] = field(default_factory=dict)
    report_sent: bool = False
    drafting: Optional[DraftSummary] = None  # 초안 스위치가 켜진 바퀴만(숫자만)
    realtime_drafting: bool = False  # 초안은 켜졌지만 빠른 길 몫이라 이 바퀴는 쓰지 않았다
    cases: Optional[dict[str, Any]] = None  # 직원 직접 답 붙이기(초안을 쓰는 바퀴만 — 숫자 · 코드만)

    def summary(self) -> dict[str, Any]:
        """JSON 한 줄 요약 — 초안을 돈 바퀴만 ``drafting`` 칸, 사례를 붙인 바퀴만 ``cases`` 칸(숫자만)이 붙는다."""
        out = {"outcome": self.outcome, "ingested": self.ingested,
               "reconciled": sum(c.done for c in self.checks.values()),
               "checks": {b: c.status for b, c in self.checks.items()},
               "needs_reply": sum(self.needs_reply.values()), "alerts": sum(self.alerts.values()),
               "report_sent": self.report_sent}
        if self.drafting is not None:
            out["drafting"] = self.drafting.counts()
        if self.realtime_drafting:
            out["drafting"] = "realtime"
        if self.cases is not None:
            out["cases"] = self.cases
        return out


# ── 한 바퀴 ──────────────────────────────────────────────────────────────
def run_pass(session: Any, *, config: LoopConfig = LoopConfig(), stop: Optional[StopFlag] = None,
             reader: Optional[OpenApiReader] = None, now: Optional[datetime.datetime] = None,
             clock: Callable[[], float] = time.monotonic,
             is_business_day: Optional[BusinessDayFn] = None) -> PassResult:
    """감시 한 바퀴. 끈 바퀴 · 대표가 아닌 바퀴 · 멈춘 바퀴는 일을 하지 않고 결과만 돌려준다.

    Args:
        session: DB 세션(바퀴 안에서 커밋한다).
        config: 바퀴 설정.
        stop: TERM 깃발(없으면 내린 깃발).
        reader: 채널톡 읽기(없으면 기본 — 기다림이 깃발을 본다).
        now: 지금(시간대 있는 값, 시험 주입).
        clock: 시간 상한 시계(단조, 시험 주입).
        is_business_day: 운영일 판정(시험 주입).

    Returns:
        :class:`PassResult`.

    Raises:
        SQLAlchemyError: DB 오류 — 러너가 기록하고 다음 바퀴로 간다.
    """
    stop = stop or StopFlag()
    now = (now or now_kst()).astimezone(KST)
    if stop.is_set():
        return PassResult(OUTCOME_STOPPED)
    running = read_switch(session)
    session.commit()  # 읽기 트랜잭션을 닫는다
    if not running:
        return PassResult(OUTCOME_KILLED)
    with leader_lock(session.get_bind()) as leader:
        if not leader:
            return PassResult(OUTCOME_NOT_LEADER)
        result = PassResult(OUTCOME_OK)
        try:
            _work(session, result, config=config, stop=stop, reader=reader or OpenApiReader(sleep=stop.reader_sleep),
                  now=now, clock=clock, cal=is_business_day or calendar_is_business_day)
        except PassStopped:
            session.rollback()
            result.outcome = OUTCOME_STOPPED
        return result


def _work(session: Any, result: PassResult, *, config: LoopConfig, stop: StopFlag, reader: OpenApiReader,
          now: datetime.datetime, clock: Callable[[], float], cal: BusinessDayFn) -> None:
    """대표가 된 바퀴의 일 — 수신 기록 → 채널톡 보정(시간 상한) → 열린 상담 상태 → 경보 · 아침 보고 → (스위치가 켜졌고 빠른 길이
    안 돌면) 직원 직접 답을 사례로 붙이기(:mod:`.case_memory`) → 초안."""
    stop.check()
    result.ingested = ingest_inbound(session, lookback=config.ingest_lookback, now=naive_utc(now)).inserted
    budget = config.reconcile_budget_seconds / max(1, len(config.brands))
    for brand in config.brands:
        result.checks[brand] = _reconcile_brand(session, reader, brand, now=now, deadline=clock() + budget,
                                                clock=clock, stop=stop, detect_missing=config.watch_missing_inbound)
    states = compute_open_states(session, now=now, brands=config.brands, is_business_day=cal)
    session.commit()
    result.needs_reply = {b: sum(1 for s in states if s.brand == b and s.needs_reply) for b in config.brands}
    stop.check()  # 알림 · 기록 쓰기 전(publish 안에서도 쓰기 바로 앞마다 다시 본다)
    published = report.publish(
        session, states=states, missing=[m for check in result.checks.values() for m in check.missing],
        checks={brand: check.status for brand, check in result.checks.items()},
        watch_missing_inbound=config.watch_missing_inbound, now=now, is_business_day=cal,
        report_hour=config.report_hour, stop_check=stop.check)
    result.alerts, result.report_sent = published.alerts, published.report_sent
    mode = draft_mode(session)  # 초안 스위치(매 바퀴 DB 에서 새로) — 없거나 꺼졌으면 바퀴는 여기까지(예전 그대로)
    realtime_on = bool(read_settings(session, log=False).get("realtime_enabled"))
    session.commit()
    if mode == DRAFT_OFF or realtime_on:  # 빠른 길이 켜져 있으면 초안은 빠른 길 몫(보정 · 아침 보고만 — 설계서 17.3)
        result.realtime_drafting = realtime_on and mode != DRAFT_OFF
        return
    # 사례 기억(L0 — C10-4): 초안을 쓰는 쪽이 직원 직접 답도 붙인다(빠른 길이 돌면 빠른 길 몫). 새 사례가 이번 초안 재료가 된다.
    result.cases = attach_staff_replies(session, now=now, stop=stop, reader=reader, limits=PASS_LIMITS,
                                        clock=clock).counts()
    result.drafting = DraftSummary()  # 멈춰도 센 수가 요약에 남게 미리 단다
    run_drafting(session, states=states, reader=reader, now=now, stop=stop, mode=mode, is_business_day=cal,
                 clock=clock, summary=result.drafting)


# ── 채널톡 보정(시간 상한 · 오래된 것부터) ───────────────────────────────
def _window_start(session: Any, brand: str, now: datetime.datetime) -> datetime.datetime:
    """바뀐 상담 목록 창의 시작 — 상태 표에 반영한 마지막 ``updatedAt`` 에서 겹침만큼 앞(없으면 30일 전)."""
    latest = session.scalar(select(func.max(CsAgentChat.state_at)).where(CsAgentChat.brand == brand))
    floor = aware_utc(now) - INITIAL_RECONCILE_LOOKBACK
    start = floor if latest is None else max(floor, latest.replace(tzinfo=UTC) - RECONCILE_OVERLAP)
    return min(start, aware_utc(now) - MIN_RECONCILE_WINDOW)


def _needs_reconcile(snap: ChatSnapshot, row: Any) -> bool:
    """이 상담을 다시 맞춰야 하나 — 처음 보거나 반영한 ``updatedAt`` 보다 새로 바뀌었을 때만."""
    if row is None:
        return True
    if snap.updated_at is None:  # 바뀐 시각을 모르면 처음 한 번만(칸 이름이 다르면 매 바퀴 다시 읽지 않게)
        return row.chat_state is None
    return row.state_at is None or naive_utc(snap.updated_at) > row.state_at


def _changed_chats(session: Any, snaps: Sequence[ChatSnapshot]) -> list[ChatSnapshot]:
    """목록에서 다시 맞출 상담만, 오래 바뀐 것부터(시간 상한에 걸려도 창 시작이 남은 상담을 덮는다)."""
    latest: dict[str, ChatSnapshot] = {}
    far = datetime.datetime.max.replace(tzinfo=UTC)
    for snap in snaps:
        seen = latest.get(snap.chat_id)
        if seen is None or (snap.updated_at or far) > (seen.updated_at or far):
            latest[snap.chat_id] = snap
    ids = sorted(latest)
    stored: dict[str, Any] = {}
    for start in range(0, len(ids), 500):
        stmt = select(CsAgentChat.chat_id, CsAgentChat.chat_state, CsAgentChat.state_at).where(
            CsAgentChat.chat_id.in_(ids[start:start + 500]))
        stored.update({row.chat_id: row for row in session.execute(stmt)})
    todo = [snap for snap in latest.values() if _needs_reconcile(snap, stored.get(snap.chat_id))]
    return sorted(todo, key=lambda snap: (snap.updated_at or far, snap.chat_id))


def _reconcile_brand(session: Any, reader: OpenApiReader, brand: str, *, now: datetime.datetime,
                     deadline: float, clock: Callable[[], float], stop: StopFlag,
                     detect_missing: bool = True) -> BrandCheck:
    """한 브랜드 보정 — 바뀐 상담 목록을 읽고 시간 상한 안에서 오래된 것부터 맞춘다(R4-13). 키가 없으면 건너뛴다.

    ``detect_missing`` 이 거짓이면(웹훅이 오지 않는 환경) 수신 누락을 찾지 않는다 — 모든 글이 '누락'이다(원장 R5-10).
    """
    stop.check()
    start = _window_start(session, brand, now)
    session.commit()  # 채널톡을 읽는 동안 트랜잭션을 열어 두지 않는다('idle in transaction' 방지)
    try:
        snaps = list(reader.iter_user_chats(brand, changed_from=start, changed_to=aware_utc(now)))
    except OpenApiNotConfigured:
        return BrandCheck(status=CHECK_NOT_CONFIGURED)
    except ChannelRateLimited:
        return BrandCheck(status=CHECK_RATE_LIMITED)
    except ChannelReadError as exc:
        logger.warning("[CS 감시] 상담 목록 읽기 실패 brand=%s status=%s", brand, exc.status)
        return BrandCheck(status=CHECK_ERROR)
    if any(snap.updated_at is None for snap in snaps):
        logger.warning("[CS 감시] updatedAt 없는 상담이 목록에 있다 brand=%s — 칸 이름을 확인한다", brand)
    todo = _changed_chats(session, snaps)
    session.commit()  # 읽기 트랜잭션을 닫는다
    check = BrandCheck(listed=len(snaps), todo=len(todo))
    for snap in todo:
        if clock() >= deadline:
            check.status = CHECK_PARTIAL
            break
        stop.check()  # 일을 집기 전
        if not _reconcile_one(session, reader, brand, snap, now=now, stop=stop, check=check,
                              detect_missing=detect_missing):
            break
    return check


def _reconcile_one(session: Any, reader: OpenApiReader, brand: str, snap: ChatSnapshot, *,
                   now: datetime.datetime, stop: StopFlag, check: BrandCheck, detect_missing: bool = True) -> bool:
    """한 상담 보정 — 글을 읽고 상태 표에 넣은 뒤 상담 상태를 반영한다. 계속해도 되면 True.

    읽기가 잠깐 실패하면 그 브랜드 보정을 이 바퀴에서 멈춘다 — 더 새 상담을 맞추면 창 시작(반영한 마지막
    ``updatedAt``)이 이 상담을 넘어가 다시 목록에 오르지 않는다(원장 R5-1). 404(지워진 상담)는 다시 읽어도 같아
    상태만 반영하고 넘어간다.
    """
    messages: Sequence[DerivedMessage] = ()
    if snap.state != "closed":  # 닫힌 상담은 상태만 — 손님이 다시 쓰면 웹훅 · 다음 목록이 연다
        try:
            messages = reader.read_messages(brand, snap.chat_id)
        except ChannelRateLimited:
            check.status = CHECK_RATE_LIMITED
            return False
        except ChannelReadError as exc:
            check.errors += 1
            logger.warning("[CS 감시] 상담 글 읽기 실패 brand=%s chat=%s status=%s", brand, snap.chat_id, exc.status)
            if exc.status != 404 or check.errors >= MAX_CHAT_ERRORS:
                check.status = CHECK_ERROR
                return False
    stop.check()  # 쓰기 전 — TERM 뒤엔 읽은 글을 버린다(R4-4)
    if messages:
        missing = apply_api_messages(session, snap.chat_id, messages, now=now,
                                     detect_missing=detect_missing).missing_inbound
        check.missing.extend(_missing_of(brand, messages, missing, now))
        stop.check()  # 다음 쓰기 전 — 상태를 안 쓰면 다음 바퀴가 이 상담을 다시 맞춘다(R5-3)
    apply_chat_snapshots(session, [snap], now=naive_utc(now))  # 맨 끝 — 반영한 updatedAt 이 '여기까지 맞췄다' 표시다
    check.done += 1
    return True


def _missing_of(brand: str, messages: Sequence[DerivedMessage], missing_ids: Sequence[str],
                now: datetime.datetime) -> list[report.MissingInbound]:
    """빠진 글 id → 경보 재료. 경보 나이 상한보다 옛 글은 뺀다(처음 바퀴의 30일 채우기가 옛 누락을 쏟지 않게)."""
    floor = aware_utc(now) - report.WATCH_LOOKBACK
    by_id = {m.message_id: m for m in messages}
    return [report.MissingInbound(brand, by_id[mid].chat_id, mid, by_id[mid].created_at)
            for mid in missing_ids if mid in by_id and by_id[mid].created_at >= floor]
