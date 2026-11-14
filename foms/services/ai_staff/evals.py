"""상담 AI 평가 묶음 — 설정 · 묶음 만들기 · 결과 저장 · 줄 일 넣기(설계서 2026-11-14-foms-graft 3.15 · D209, 판 ⑪ 'AI 시험').

화면 값은 :mod:`.evals_view`, 한 번 돌리기는 :mod:`.evals_run`(500줄 상한으로 셋으로 나눴다).

- **설정**(SystemSetting :data:`SETTINGS_KEY`): ``{"cap_usd": "<달러 글>", "past_size": n, "risk_size": n, "past_target_pct": n}``.
  처음 값은 모두 0 이다 — ADMIN 이 ⑪ 에서 넣기 전에는 돌지 않는다(:attr:`EvalSettings.ready`). 금액 숫자는 저장소에 적지 않는다.
  꼴이 틀린 저장 값은 모두 0(막는 쪽)으로 본다.
- **묶음**(:func:`build_eval_set`): 돌릴 때 DB 에서 만든다. 읽는 칸은 번호 · 브랜드 · 상담 id · 검사 코드와 가린 칸
  (``masked_question`` · ``masked_context`` · ``staff_reply_masked``)뿐이다 — 줄 전체를 읽지 않는다.
  - '지난 상담': 시험용으로 떼어 둔 차례(``held_out``) 가운데 직원 답이 있는 것, 최근 것부터 설정 수까지. 없으면 0 이다 — 배우기에
    쓴 차례로 채우지 않는다(답을 이미 본 문제다).
  - '위험 문장': 보내기 전 검사에 걸린 적 있는 차례(``check_codes`` 에 막는 코드가 있음 — 말투 알림만 있는 줄은 뺀다), 최근 것부터.
    JSON 칸을 글자로 바꿔 찾지 않고, 최근 :data:`RISK_POOL` 줄의 코드 칸만 읽어 파이썬으로 거른다.
- **결과**(SystemSetting :data:`RESULTS_KEY`): ``{"runs": [...]}`` 최근 :data:`KEEP_RUNS` 번 — 시작 · 마지막 소식 · 끝 · 누른 사람
  번호 · 묶음마다 수 · 통과 수 · 모델 · 쓴 돈 · 상태 · 틀린 차례(번호 · 까닭 코드). **글은 없다.**
- **한 번에 하나만**: 마지막 줄이 '줄 섬' · '도는 중'이고 마지막 소식이 :data:`STALE_AFTER` 안이면 도는 중이다(새로 누르면 409).
  그보다 오래 소식이 없으면 멈춘 것으로 보고 '멈춘 채 끝남'으로 풀어 준다.
- **줄 일**: :data:`JOB_PATH` 를 RQ ``default`` 줄에 넣는다(:func:`enqueue_run`) — 그 줄은 WORKER 의 감독받는 큐 소비자만 꺼낸다.
  상담 두뇌 열쇠는 WORKER 에만 있다. 큐가 없으면 넣지 않고 거짓(동기로 대신 돌리지 않는다 — web 에는 열쇠가 없다).
- 감사 줄: 설정 저장 ``AI_STAFF_EVAL_SETTINGS_SAVED``(칸 · 앞뒤 값) · 돌리기 ``AI_STAFF_EVAL_RUN``(번호 · 묶음 크기). 커밋은 부르는 쪽.
"""

from __future__ import annotations

import copy
import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from foms.services.audit_writer import normalize_security_detail
from foms.services.brain.scope import Viewer, viewer_of
from foms.services.cs_agent.brain_prompt import ENABLED_BRANDS
from foms.services.cs_agent.checks import REASONS
from foms.services.datetime_kst import parse_datetime_utc
from foms.services.jobs.queue import get_rq_queue
from models import CsAgentTurn, SecurityLog, SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "AUDIT_RUN", "AUDIT_SETTINGS", "JOB_PATH", "RESULTS_KEY", "SETTINGS_KEY", "EvalCase", "EvalError", "EvalSet",
    "EvalSettings", "add_run", "begin_run", "blocking_codes", "build_eval_set", "claim_run", "enqueue_run", "is_stale",
    "latest_results", "money_text", "naive_utc", "parse_money", "read_eval_settings", "save_eval_settings", "update_run",
]

SETTINGS_KEY = "ai_staff_eval_settings"
RESULTS_KEY = "ai_staff_eval_results"
KEEP_RUNS, FAILURE_LIMIT = 10, 10
MAX_SET, RISK_POOL = 200, 2000
#: 이만큼 소식(차례 하나 끝날 때마다 남긴다)이 없으면 멈춘 것으로 본다 — 차례 하나는 두뇌 시간 상한 두 번 안에 끝난다.
STALE_AFTER = datetime.timedelta(minutes=15)
#: RQ 가 여는 함수 경로(WORKER 가 꺼낸다) · 시간 상한. 평가는 이 시간 안에서 스스로 멈춘다(:mod:`.evals_run`).
JOB_PATH = "foms.services.ai_staff.evals_run.run_eval_job"
JOB_TIMEOUT = "1h"
QUEUED, RUNNING, DONE = "queued", "running", "done"
CAP_STOPPED, TIME_STOPPED, NOT_READY, FAILED, STALE = "cap_stopped", "time_stopped", "not_ready", "failed", "stale"
ACTIVE = (QUEUED, RUNNING)
SCORED = (DONE, CAP_STOPPED, TIME_STOPPED, RUNNING)
SET_PAST, SET_RISK = "past", "risk"
UNSUPPORTED = "unsupported"
AUDIT_SETTINGS = "AI_STAFF_EVAL_SETTINGS_SAVED"
AUDIT_RUN = "AI_STAFF_EVAL_RUN"
MESSAGES: dict[str, str] = {
    "EVAL_FORBIDDEN": "찾을 수 없습니다.",
    "EVAL_SHAPE": "값이 맞지 않아요 — 다시 넣어 주세요.",
    "EVAL_NO_CAP": "돈 상한을 먼저 넣어 주세요.",
    "EVAL_NO_SIZE": "묶음 크기를 먼저 넣어 주세요.",
    "EVAL_BUSY": "시험이 이미 도는 중이에요.",
}
_INT_FIELDS: dict[str, int] = {"past_size": MAX_SET, "risk_size": MAX_SET, "past_target_pct": 100}
_DESCRIPTIONS = {SETTINGS_KEY: "AI 직원 — 상담 AI 평가 한 번 돈 상한 · 묶음 크기 · 기준(설계서 2026-11-14-foms-graft 3.15)",
                 RESULTS_KEY: "AI 직원 — 상담 AI 평가 결과 최근 10번(수 · 코드만, 글 없음 — 설계서 3.15)"}
_MICRO = Decimal("0.000001")


class EvalError(Exception):
    """평가 설정 · 돌리기 거절 — ``code`` 는 :data:`MESSAGES` 열쇠, ``fields`` 는 틀린 칸 이름."""

    def __init__(self, code: str, fields: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code, self.fields = code, tuple(fields)

    @property
    def message(self) -> str:
        """화면 말."""
        return MESSAGES[self.code]


@dataclass(frozen=True)
class EvalSettings:
    """평가 설정 — 한 번 돈 상한(달러) · '지난 상담' 수 · '위험 문장' 수 · '지난 상담' 기준(%, 0 = 기준 없음)."""

    cap_usd: Decimal = Decimal(0)
    past_size: int = 0
    risk_size: int = 0
    past_target_pct: int = 0

    @property
    def ready(self) -> bool:
        """돌 수 있나 — 상한이 0 보다 크고 묶음 크기 합이 0 보다 크다."""
        return self.cap_usd > 0 and self.past_size + self.risk_size > 0

    def as_dict(self) -> dict[str, Any]:
        """저장 · 화면 꼴(돈은 글)."""
        return {"cap_usd": str(self.cap_usd), "past_size": self.past_size, "risk_size": self.risk_size,
                "past_target_pct": self.past_target_pct}


@dataclass(frozen=True)
class EvalCase:
    """평가 차례 하나 — 글은 가린 칸뿐이고 repr 에 싣지 않는다."""

    turn_id: int
    kind: str
    brand: str
    chat_id: str
    question: str = field(repr=False)
    context: str = field(default="", repr=False)
    staff_reply: str = field(default="", repr=False)


@dataclass(frozen=True)
class EvalSet:
    """한 번 돌릴 묶음 — '지난 상담' · '위험 문장'."""

    past: tuple[EvalCase, ...] = ()
    risk: tuple[EvalCase, ...] = ()


# ── 시각 ─────────────────────────────────────────────────────────────────
def naive_utc(value: datetime.datetime) -> datetime.datetime:
    """UTC naive — 시간대 있는 값은 UTC 로 옮기고, 없는 값은 UTC 로 본다."""
    return value.astimezone(datetime.timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _iso(value: datetime.datetime) -> str:
    """결과 줄에 적는 때(UTC naive ISO, 초까지)."""
    return naive_utc(value).isoformat(timespec="seconds")


def _parsed(raw: Any) -> Optional[datetime.datetime]:
    """결과 줄의 때 글 → UTC naive(틀리면 ``None``)."""
    parsed = parse_datetime_utc(raw) if isinstance(raw, str) else None
    return parsed.replace(tzinfo=None) if parsed is not None else None


def is_stale(run: Mapping[str, Any], at: datetime.datetime) -> bool:
    """도는 중 · 줄 섬 줄이 마지막 소식에서 :data:`STALE_AFTER` 넘게 지났나."""
    seen = _parsed(run.get("heartbeat_at")) or _parsed(run.get("started_at"))
    return seen is None or at - seen > STALE_AFTER


# ── 설정 ─────────────────────────────────────────────────────────────────
def parse_money(raw: Any) -> Optional[Decimal]:
    """돈 값 → Decimal(0 이상 · 유한 · 소수 여섯째 자리까지). 틀리면 ``None``."""
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)) or len(str(raw)) > 16:
        return None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or int(value.as_tuple().exponent) < -6:
        return None
    return value


def _count(raw: Any, top: int) -> Optional[int]:
    """0 ~ ``top`` 정수(참거짓 · 글 · 소수는 ``None``)."""
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= top else None


def read_eval_settings(session: Any) -> EvalSettings:
    """설정 읽기 — 없거나 꼴이 틀리면 모두 0(돌지 않는다)."""
    row = session.get(SystemSetting, SETTINGS_KEY, populate_existing=True)
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    cap = parse_money(value.get("cap_usd", "0"))
    counts = {name: _count(value.get(name, 0), top) for name, top in _INT_FIELDS.items()}
    if cap is None or any(n is None for n in counts.values()):
        logger.warning("[AI 시험] 설정 꼴이 틀려 0 으로 본다 key=%s", SETTINGS_KEY)
        return EvalSettings()
    return EvalSettings(cap, **counts)  # type: ignore[arg-type]


def _admin(actor: Any) -> Viewer:
    """켜진 내부 ADMIN 만 — 아니면 ``EVAL_FORBIDDEN``(API 는 없는 것과 같은 404)."""
    viewer = viewer_of(actor)
    if not viewer.is_admin or viewer.user_id is None:
        raise EvalError("EVAL_FORBIDDEN")
    return viewer


def _parse_settings(body: Any) -> dict[str, Any]:
    """본문 ``{"cap_usd"?, "past_size"?, "past_target_pct"?, "risk_size"?}`` → 바꿀 칸. 하나라도 틀리면 거절."""
    if not isinstance(body, Mapping) or not body:
        raise EvalError("EVAL_SHAPE", ("settings",))
    out: dict[str, Any] = {}
    problems: list[str] = []
    for name, raw in body.items():
        if name == "cap_usd":
            value: Any = parse_money(raw)
            value = str(value) if value is not None else None
        elif name in _INT_FIELDS:
            value = _count(raw, _INT_FIELDS[name])
        else:
            value = None
        if value is None:
            problems.append(str(name)[:20])
        else:
            out[name] = value
    if problems:
        raise EvalError("EVAL_SHAPE", tuple(problems))
    return out


def _locked(session: Any, key: str) -> SystemSetting:
    """설정 줄을 잠가 읽는다(없으면 만든다 — 커밋은 부르는 쪽)."""
    row = (session.query(SystemSetting).filter(SystemSetting.setting_key == key)
           .populate_existing().with_for_update().first())
    if row is None:
        row = SystemSetting(setting_key=key, setting_value={}, description=_DESCRIPTIONS[key])
        session.add(row)
        session.flush()
    return row


def _put(row: SystemSetting, value: dict[str, Any]) -> None:
    row.setting_value = value
    flag_modified(row, "setting_value")
    row.version = int(row.version or 0) + 1


def _audit(session: Any, actor_id: int, action: str, message: str, detail: Mapping[str, Any]) -> None:
    """감사 한 줄 — 칸 이름 · 수 · 코드만."""
    session.add(SecurityLog(user_id=actor_id, action=action, target_type="system_setting", target_id=None,
                            message=message, detail=normalize_security_detail(dict(detail))))


def save_eval_settings(session: Any, actor: Any, body: Any) -> dict[str, Any]:
    """설정 저장(ADMIN 만 — 적은 칸만 바꾼다, 커밋은 부르는 쪽). 저장 뒤 설정 값을 돌려준다.

    Raises:
        EvalError: ``EVAL_FORBIDDEN``(ADMIN 아님) · ``EVAL_SHAPE``(모르는 칸 · 음수 · 상한 넘는 수 · 글자 · 참거짓).
    """
    viewer = _admin(actor)
    wanted = _parse_settings(body)
    before = read_eval_settings(session).as_dict()
    row = _locked(session, SETTINGS_KEY)
    after = {**before, **wanted}
    changes = {name: [before[name], after[name]] for name in wanted if before[name] != after[name]}
    if changes:
        _put(row, after)
        _audit(session, int(viewer.user_id), AUDIT_SETTINGS, f"AI 시험 설정 고침 {len(changes)}칸", {"changes": changes})
    session.flush()
    return read_eval_settings(session).as_dict()


# ── 묶음 ─────────────────────────────────────────────────────────────────
_TEXT_COLUMNS = (CsAgentTurn.id, CsAgentTurn.brand, CsAgentTurn.chat_id, CsAgentTurn.masked_question,
                 CsAgentTurn.masked_context, CsAgentTurn.staff_reply_masked)


def blocking_codes(codes: Any) -> tuple[str, ...]:
    """막는 검사 코드만(말투 알림 ``tone_*`` · 모르는 코드는 뺀다)."""
    if not isinstance(codes, list):
        return ()
    return tuple(code for code in codes if isinstance(code, str) and code in REASONS and not code.startswith("tone_"))


def _where(at: datetime.datetime) -> tuple[Any, ...]:
    """두 묶음 공통 — 두뇌를 켠 브랜드 · 가린 질문이 있음 · 돌리기 시작 전에 생긴 차례."""
    turn = CsAgentTurn
    return turn.brand.in_(tuple(ENABLED_BRANDS)), turn.masked_question.isnot(None), turn.created_at <= at


def _case(row: Any, kind: str) -> EvalCase:
    return EvalCase(turn_id=int(row.id), kind=kind, brand=row.brand, chat_id=row.chat_id,
                    question=row.masked_question or "", context=row.masked_context or "",
                    staff_reply=(row.staff_reply_masked or "") if kind == SET_PAST else "")


def _past_cases(session: Any, size: int, at: datetime.datetime) -> tuple[EvalCase, ...]:
    """'지난 상담' — 떼어 둔 차례 가운데 직원 답이 있는 것, 최근 것부터(없으면 빈 묶음)."""
    if size <= 0:
        return ()
    stmt = (select(*_TEXT_COLUMNS)
            .where(*_where(at), CsAgentTurn.held_out.is_(True), CsAgentTurn.staff_reply_masked.isnot(None))
            .order_by(CsAgentTurn.id.desc()).limit(size))
    return tuple(_case(row, SET_PAST) for row in session.execute(stmt))


def _risk_cases(session: Any, size: int, at: datetime.datetime) -> tuple[EvalCase, ...]:
    """'위험 문장' — 최근 :data:`RISK_POOL` 줄의 검사 코드만 읽어 막는 코드가 있는 차례를 고른 뒤 그 줄의 가린 칸을 읽는다."""
    if size <= 0:
        return ()
    pool = session.execute(select(CsAgentTurn.id, CsAgentTurn.check_codes)
                           .where(*_where(at), CsAgentTurn.check_codes.isnot(None))
                           .order_by(CsAgentTurn.id.desc()).limit(RISK_POOL))
    ids = [int(row.id) for row in pool if blocking_codes(row.check_codes)][:size]
    if not ids:
        return ()
    stmt = select(*_TEXT_COLUMNS).where(CsAgentTurn.id.in_(ids)).order_by(CsAgentTurn.id.desc())
    return tuple(_case(row, SET_RISK) for row in session.execute(stmt))


def build_eval_set(session: Any, now: datetime.datetime, settings: Optional[EvalSettings] = None) -> EvalSet:
    """돌릴 묶음을 DB 에서 만든다(가린 칸만 — 모듈 설명). ``now`` 뒤에 생긴 차례는 넣지 않는다.

    Args:
        session: DB 세션(읽기만).
        now: 돌리기 시작 때(시간대 있는 값이면 UTC 로 옮긴다).
        settings: 묶음 크기(없으면 저장된 설정).

    Returns:
        :class:`EvalSet` — 떼어 둔 차례가 없으면 '지난 상담'은 빈 묶음이다.
    """
    cfg = settings if settings is not None else read_eval_settings(session)
    at = naive_utc(now)
    return EvalSet(past=_past_cases(session, cfg.past_size, at), risk=_risk_cases(session, cfg.risk_size, at))


# ── 결과 ─────────────────────────────────────────────────────────────────
def _runs_of(row: Optional[SystemSetting]) -> list[dict[str, Any]]:
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    runs = value.get("runs")
    return [copy.deepcopy(run) for run in runs if isinstance(run, dict)] if isinstance(runs, list) else []


def latest_results(session: Any) -> list[dict[str, Any]]:
    """저장된 결과 — 새 것부터(최근 :data:`KEEP_RUNS` 번, 글 없음)."""
    return list(reversed(_runs_of(session.get(SystemSetting, RESULTS_KEY, populate_existing=True))))


def _find(runs: Iterable[dict[str, Any]], run_id: int) -> Optional[dict[str, Any]]:
    return next((run for run in runs if run.get("id") == run_id), None)


def _release_stale(runs: list[dict[str, Any]], at: datetime.datetime) -> Optional[dict[str, Any]]:
    """오래 소식 없는 줄 섬 · 도는 중 줄을 '멈춘 채 끝남'으로 풀고, 살아 있는 줄(있으면)을 돌려준다."""
    alive = None
    for run in runs:
        if run.get("status") not in ACTIVE:
            continue
        if is_stale(run, at):
            run.update(status=STALE, finished_at=_iso(at))
        else:
            alive = run
    return alive


def add_run(session: Any, *, actor_id: Optional[int], now: datetime.datetime, settings: EvalSettings) -> dict[str, Any]:
    """'줄 섬' 한 줄을 더한다(결과 줄을 잠근다 — 커밋은 부르는 쪽). 더한 줄의 사본.

    Raises:
        EvalError: ``EVAL_NO_CAP`` · ``EVAL_NO_SIZE``(설정 0) · ``EVAL_BUSY``(살아 있는 줄이 있음).
    """
    if settings.cap_usd <= 0:
        raise EvalError("EVAL_NO_CAP")
    if settings.past_size + settings.risk_size <= 0:
        raise EvalError("EVAL_NO_SIZE")
    at = naive_utc(now)
    row = _locked(session, RESULTS_KEY)
    runs = _runs_of(row)
    if _release_stale(runs, at) is not None:
        raise EvalError("EVAL_BUSY")
    run = {"id": max((int(r.get("id") or 0) for r in runs), default=0) + 1, "status": QUEUED, "code": None,
           "actor_id": actor_id, "started_at": _iso(at), "heartbeat_at": _iso(at), "finished_at": None, "model": None,
           "cost_usd": "0", "target_pct": settings.past_target_pct, "past": {"total": 0, "done": 0, "passed": 0},
           "risk": {"total": 0, "done": 0, "bad": 0}, "failures": []}
    _put(row, {"runs": [*runs, run][-KEEP_RUNS:]})
    session.flush()
    return copy.deepcopy(run)


def begin_run(session: Any, actor: Any, now: datetime.datetime) -> dict[str, Any]:
    """[시험 다시 돌리기] — ADMIN 확인 · 설정 확인 · '줄 섬' 한 줄 · 감사 줄(커밋은 부르는 쪽). 더한 줄의 사본.

    Raises:
        EvalError: ``EVAL_FORBIDDEN`` · ``EVAL_NO_CAP`` · ``EVAL_NO_SIZE`` · ``EVAL_BUSY``.
    """
    viewer = _admin(actor)
    settings = read_eval_settings(session)
    run = add_run(session, actor_id=viewer.user_id, now=now, settings=settings)
    _audit(session, int(viewer.user_id), AUDIT_RUN, f"AI 시험 돌리기 #{run['id']}",
           {"run": run["id"], "past_size": settings.past_size, "risk_size": settings.risk_size})
    session.flush()
    return run


def claim_run(session: Any, run_id: int, now: datetime.datetime) -> Optional[dict[str, Any]]:
    """줄 일이 '줄 섬' 줄을 '도는 중'으로 잡는다. 없거나 · 이미 잡혔거나 · 멈춘 것으로 풀렸으면 ``None``(커밋은 부르는 쪽)."""
    at = naive_utc(now)
    row = _locked(session, RESULTS_KEY)
    runs = _runs_of(row)
    run = _find(runs, int(run_id))
    if run is None or run.get("status") != QUEUED or is_stale(run, at):
        return None
    run.update(status=RUNNING, heartbeat_at=_iso(at))
    _put(row, {"runs": runs})
    session.flush()
    return copy.deepcopy(run)


def update_run(session: Any, run_id: int, now: datetime.datetime, **fields: Any) -> None:
    """도는 줄 하나를 고친다(마지막 소식 때도 — 커밋은 부르는 쪽). ``status`` 가 끝 상태면 끝 때를 적는다. 없는 줄은 그대로."""
    at = naive_utc(now)
    row = _locked(session, RESULTS_KEY)
    runs = _runs_of(row)
    run = _find(runs, int(run_id))
    if run is None:
        logger.warning("[AI 시험] 결과 줄이 없어 고치지 않는다 run=%s", run_id)
        return
    run.update(copy.deepcopy(fields), heartbeat_at=_iso(at))
    if run.get("status") not in ACTIVE:
        run["finished_at"] = _iso(at)
    _put(row, {"runs": runs})
    session.flush()


def enqueue_run(run_id: int) -> bool:
    """줄 일을 WORKER 의 RQ ``default`` 줄에 넣는다. 큐가 없거나 넣기가 실패하면 거짓(동기로 대신 돌리지 않는다)."""
    queue = get_rq_queue()
    if queue is None:
        return False
    try:
        queue.enqueue(JOB_PATH, int(run_id), job_id=f"ai_staff_eval_{int(run_id)}", job_timeout=JOB_TIMEOUT)
    except Exception as exc:  # 큐 장애 — 화면은 '지금은 돌릴 수 없어요'(까닭은 로그에 종류만)
        logger.error("[AI 시험] 줄 넣기 실패 run=%s err=%s", run_id, type(exc).__name__)
        return False
    return True


def money_text(value: Decimal) -> str:
    """돈 글(소수 여섯째 자리) — 결과 줄에 적는 꼴."""
    return str(Decimal(value).quantize(_MICRO))
