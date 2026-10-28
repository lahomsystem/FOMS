"""아침 보고 · 경보 — 상담 상태에서 사람이 읽을 글을 만들고, 한 번씩만 FOMS 앱 안 알림으로 낸다(플랜 C1-3).

- **손님 정보 0**: 재료는 상태 표의 파생 칸뿐이다(상담 id · 브랜드 · 운영 시간 기준 기다린 분 · 약속 꼴 · 기한).
  손님 글 · 이름 · 번호는 이 모듈에 들어오지 않는다.
- **받는 곳(원장 D2 '사장님 · FOMS 앱 안 알림')**: 사장님을 가리키는 규칙이 저장소에 없어 ADMIN 역할 전원이 받는다.
  길은 기존 그대로 — ROLE 알림 한 줄 + 수신자 펼침(:func:`fan_out_new_notification`, 워커 정지 감시와 같은 꼴).
  OS 푸시는 하지 않는다(RQ 를 거치지 않는다 — 알림 센터 · 배지로 본다).
- **종료 후보는 내지 않는다(원장 D23)**: 칸은 3일+ · 약속 넘김 · 답 필요 · 약속 기한 전 넷뿐이다.
- **한 번만(:func:`publish`)**: 약속 넘김은 약속마다, 넘기기 대기 웹훅 · 수신 누락은 줄마다, 아침 보고는 운영일 하루
  한 번. 기록은 SystemSetting :data:`STATE_KEY` 한 줄 — ``FOR UPDATE`` 로 잡아 다시 견준 뒤 알림과 같은 트랜잭션으로
  고친다(재시작 · 두 컨테이너가 겹쳐도 한 번). 보낼 것이 없는 바퀴는 그 줄을 쓰지 않는다 — ``system_settings`` 는
  화면 304 판정 표라 쓸 때마다 화면 조각이 다시 그려진다.
- 알림 화면은 줄바꿈을 접어 보여 준다 — 줄마다 머리표(``[라홈]`` · ``①``)를 달아 접혀도 읽히게 쓴다.
"""

from __future__ import annotations

import copy
import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from foms.services.cs_agent.channel_read import channel_for_brand, naive_utc
from foms.services.cs_agent.state import (
    KST,
    PRIORITY_BROKEN_PROMISE,
    PRIORITY_NEEDS_REPLY,
    PRIORITY_NONE,
    PRIORITY_PROMISE_PENDING,
    PRIORITY_STALE,
    BusinessDayFn,
    ChatState,
    StaffPromise,
    sort_by_priority,
)
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.sidefx_worker import WORKER_KIND_CS_LOOP
from models import ChannelWebhookJob, Notification, SideEffectWorkerHeartbeat, SystemSetting

#: 알림 유형(``notifications.notification_type``). 아침 보고와 경보 셋을 가른다.
NOTIFY_MORNING_REPORT = "CS_MORNING_REPORT"
NOTIFY_PROMISE_OVERDUE = "CS_PROMISE_OVERDUE"
NOTIFY_WEBHOOK_PENDING = "CS_WEBHOOK_PENDING"
NOTIFY_INBOUND_MISSING = "CS_INBOUND_MISSING"
#: 받는 역할 — 사장님 규칙이 없어 관리자 전원(원장 D2).
NOTIFY_ROLE = "ADMIN"
#: 루프 기록 SystemSetting 키(루프만 쓴다): 알린 열쇠 · 마지막 아침 보고 날. 바로 끄기 줄(``loop.SWITCH_KEY``)과
#: 나눈다 — 한 줄을 여럿이 쓰면 한쪽 갱신이 다른 쪽 값을 지운다.
STATE_KEY = "cs_agent_loop_state"
#: 하트비트 metadata 에서 마지막 정상 바퀴 시각(UTC ISO)을 담는 칸 — 러너가 쓰고 아침 보고가 읽는다.
HEARTBEAT_LAST_SUCCESS_KEY = "last_success_at"
REPORT_HOUR = 8  # KST, 운영일만

BRAND_LABELS: dict[str, str] = {"LAHOM": "라홈", "HAUD": "하우드"}
TIER_LABELS: dict[int, str] = {
    PRIORITY_STALE: "3일+",
    PRIORITY_BROKEN_PROMISE: "약속 넘김",
    PRIORITY_NEEDS_REPLY: "답 필요",
    PRIORITY_PROMISE_PENDING: "약속 기한 전",
}
#: 아침 보고 '먼저 볼 상담' 수 · 경보 한 건에 적는 상담 수.
REPORT_TOP_N = 5
ALERT_LIST_MAX = 10
#: 채널톡 데스크 상담 주소 꼴 — 저장소 채널톡 구현 안내(2026-03-27)의 데스크 주소 ``#/channels/<채널 id>/team_chats/…``
#: 와 같은 길의 상담 쪽이다. 실제로 열리는지는 스테이징 보고 1건에서 눌러 확인한다(플랜 C1-3 완료 기준).
DESK_CHAT_URL = "https://desk.channel.io/#/channels/{channel_id}/user_chats/{chat_id}"
_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩"
_WEEKDAYS = "월화수목금토일"
_CHECK_LABELS = {
    "ok": "정상",
    "partial": "일부(시간 상한 — 다음 바퀴가 잇는다)",
    "not_configured": "키 없음(웹훅 기록만으로 셈)",
    "rate_limited": "채널톡 한도 — 다음 바퀴에",
    "error": "읽기 실패(로그 확인)",
}

ALERT_PROMISE, ALERT_WEBHOOK, ALERT_INBOUND = "promise", "webhook", "inbound"
ALERT_KINDS: tuple[str, ...] = (ALERT_PROMISE, ALERT_WEBHOOK, ALERT_INBOUND)
PENDING_WEBHOOK_AFTER = datetime.timedelta(minutes=1)
#: 넘기기 대기 웹훅 · 수신 누락을 경보할 나이 상한 — 처음 바퀴의 30일 채우기가 옛 누락을 쏟지 않게.
WATCH_LOOKBACK = datetime.timedelta(days=7)
PENDING_WEBHOOK_LIMIT = 500
#: 지금 후보가 아닌 알린 열쇠를 남겨 두는 기간 — 약속은 다시 열린 상담에 옛 약속을 또 알리지 않을 만큼만.
ALERT_KEEP = {ALERT_PROMISE: datetime.timedelta(days=3), ALERT_WEBHOOK: WATCH_LOOKBACK + datetime.timedelta(days=1),
              ALERT_INBOUND: WATCH_LOOKBACK + datetime.timedelta(days=1)}
ALERT_KEYS_MAX = 2000
_NOTIFY_TYPES = {ALERT_PROMISE: NOTIFY_PROMISE_OVERDUE, ALERT_WEBHOOK: NOTIFY_WEBHOOK_PENDING,
                 ALERT_INBOUND: NOTIFY_INBOUND_MISSING}


@dataclass(frozen=True)
class MissingInbound:
    """채널톡엔 있는데 수신 기록엔 없는 글 하나(웹훅이 빠짐 — 원장 R1-1). 글 원문은 없다."""

    brand: str
    chat_id: str
    message_id: str
    created_at: datetime.datetime  # 시간대 있는 UTC


@dataclass(frozen=True)
class ReportFacts:
    """아침 보고 재료. ``missing_inbound_24h`` 가 ``None`` 이면 수신 누락 감시가 꺼진 환경(웹훅 없음)이다."""

    day: datetime.date
    states: Sequence[ChatState]
    pending_webhooks: int
    missing_inbound_24h: Optional[int]
    checks: Mapping[str, str]  # 브랜드 → 채널톡 보정 상태
    last_success_at: Optional[datetime.datetime]  # 시간대 있는 값


# ── 글 만들기(순수) ──────────────────────────────────────────────────────
def brand_label(brand: str) -> str:
    """브랜드 한글 이름(모르면 코드 그대로)."""
    return BRAND_LABELS.get(brand, brand)


def desk_link(brand: str, chat_id: str) -> str:
    """채널톡 데스크에서 그 상담을 여는 주소."""
    return DESK_CHAT_URL.format(channel_id=channel_for_brand(brand), chat_id=chat_id)


def format_wait(minutes: int) -> str:
    """분 → '2시간 5분' · '45분'."""
    hours, rest = divmod(max(0, int(minutes)), 60)
    if not hours:
        return f"{rest}분"
    return f"{hours}시간" + (f" {rest}분" if rest else "")


def format_kst(value: datetime.datetime) -> str:
    """시간대 있는 시각 → KST '11-02 17:00'."""
    return value.astimezone(KST).strftime("%m-%d %H:%M")


def day_label(day: datetime.date) -> str:
    """날 → '11-02(월)'."""
    return f"{day:%m-%d}({_WEEKDAYS[day.weekday()]})"


def promise_phrase(promise: StaffPromise, *, overdue: bool) -> str:
    """약속 한 줄. 전화 약속은 채팅으로는 지켰는지 알 수 없다고 적는다."""
    kind = "전화 약속 — 채팅으로는 확인 불가" if promise.kind == "call" else "약속(채팅)"
    return f"'{promise.rule}' {kind} · 기한 {format_kst(promise.due_at)}" + (" 지남" if overdue else "")


def tier_counts(states: Sequence[ChatState], brands: Sequence[str]) -> dict[str, dict[int, int]]:
    """브랜드마다 우선순위 칸별 상담 수(칸 밖 상담은 세지 않는다)."""
    counts = {brand: {tier: 0 for tier in TIER_LABELS} for brand in brands}
    for state in states:
        if state.brand in counts and state.priority in TIER_LABELS:
            counts[state.brand][state.priority] += 1
    return counts


def _chat_line(number: int, state: ChatState) -> str:
    """상담 한 줄 — 칸 · 브랜드 · 기다린 시간 · 약속 · 상담 id · 데스크 주소."""
    parts = [TIER_LABELS.get(state.priority, "기타"), brand_label(state.brand)]
    if state.needs_reply:
        parts.append(f"운영 시간 {format_wait(state.waited_business_minutes)} 기다림")
    if state.open_promise is not None:
        parts.append(promise_phrase(state.open_promise, overdue=state.promise_overdue))
    parts.append(f"상담 {state.chat_id} {desk_link(state.brand, state.chat_id)}")
    return f"{_NUMBERS[number] if number < len(_NUMBERS) else '-'} " + " · ".join(parts)


def morning_report(facts: ReportFacts) -> tuple[str, str]:
    """아침 보고 한 장(제목, 본문). 손님 글 · 이름 · 번호는 재료에 없다."""
    brands = list(facts.checks) or list(BRAND_LABELS)
    counts = tier_counts(facts.states, brands)
    needs = {b: sum(1 for s in facts.states if s.brand == b and s.needs_reply) for b in brands}
    title = f"상담 아침 보고 {day_label(facts.day)} — 답 필요 " + " · ".join(
        f"{brand_label(b)} {needs[b]}" for b in brands)
    lines = [f"[{brand_label(b)}] " + " · ".join(f"{TIER_LABELS[t]} {counts[b][t]}" for t in TIER_LABELS)
             for b in brands]
    top = sort_by_priority([s for s in facts.states if s.priority < PRIORITY_NONE])[:REPORT_TOP_N]
    lines.append(f"[먼저 볼 상담] {len(top)}건" if top else "[먼저 볼 상담] 없음")
    lines.extend(_chat_line(i, s) for i, s in enumerate(top))
    missing = ("수신 누락 감시 꺼짐(이 환경엔 웹훅이 오지 않음)" if facts.missing_inbound_24h is None
               else f"지난 24시간 수신 누락 {facts.missing_inbound_24h}건")
    lines.append(f"[웹훅] 넘기기 대기(1분 넘음) {facts.pending_webhooks}건 · {missing}")
    lines.append("[채널톡 확인] " + " · ".join(
        f"{brand_label(b)} {_CHECK_LABELS.get(facts.checks.get(b, ''), '건너뜀')}" for b in brands))
    last = format_kst(facts.last_success_at) if facts.last_success_at else "없음(이번이 첫 바퀴)"
    lines.append(f"[마지막 정상 바퀴] {last}")
    return title, "\n".join(lines)


def promise_alert(states: Sequence[ChatState]) -> tuple[str, str]:
    """약속 기한 넘김 경보(제목, 본문) — 새로 넘긴 약속만 받는다."""
    ordered = sort_by_priority(states)
    lines = ["직원이 손님에게 한 약속의 기한이 지났는데 그 뒤 공개 답이 없습니다."]
    lines.extend(_chat_line(i, s) for i, s in enumerate(ordered[:ALERT_LIST_MAX]))
    if len(ordered) > ALERT_LIST_MAX:
        lines.append(f"외 {len(ordered) - ALERT_LIST_MAX}건 — 아침 보고에서 이어서 봅니다")
    return f"상담 약속 기한 넘김 {len(ordered)}건", "\n".join(lines)


def webhook_alert(created: Sequence[datetime.datetime]) -> tuple[str, str]:
    """넘기기 대기 웹훅 경보(원장 R4-11) — ``created`` 는 새로 1분을 넘긴 일들의 받은 시각(UTC naive)."""
    oldest = min(created).replace(tzinfo=datetime.timezone.utc)
    message = ("채널톡 웹훅을 받아 두었지만 처리 큐로 넘기지 못한 일이 1분 넘게 '대기'로 남아 있습니다 "
               "(자동으로 다시 넘기는 장치는 아직 없습니다). 그 상담 글은 15분 채널톡 보정이 상태 표에 채웁니다. "
               f"가장 오래된 일 {format_kst(oldest)}.")
    return f"채널톡 웹훅 넘기기 대기 {len(created)}건", message


def inbound_alert(missing: Sequence[MissingInbound]) -> tuple[str, str]:
    """수신 누락 경보 — 상담마다 묶어 상담 id · 데스크 주소 · 글 수 · 처음 시각만 적는다."""
    by_chat: dict[tuple[str, str], list[MissingInbound]] = {}
    for item in missing:
        by_chat.setdefault((item.brand, item.chat_id), []).append(item)
    lines = ["채널톡에는 있는데 FOMS 수신 기록에 없는 글입니다(웹훅이 빠졌습니다). 상태 표는 채널톡 보정으로 채웠습니다."]
    for i, ((brand, chat_id), items) in enumerate(sorted(by_chat.items())[:ALERT_LIST_MAX]):
        first = min(item.created_at for item in items)
        lines.append(f"{_NUMBERS[i]} {brand_label(brand)} · 글 {len(items)}건 · 처음 {format_kst(first)} · "
                     f"상담 {chat_id} {desk_link(brand, chat_id)}")
    if len(by_chat) > ALERT_LIST_MAX:
        lines.append(f"외 상담 {len(by_chat) - ALERT_LIST_MAX}건")
    return f"채널톡 수신 누락 {len(missing)}건", "\n".join(lines)


def post_admin_notification(session: Any, *, kind: str, title: str, message: str,
                            now: datetime.datetime) -> int:
    """관리자에게 FOMS 앱 안 알림 1건 — ROLE 알림 한 줄 + 수신자별 상태(기존 길). 커밋은 부르는 쪽 몫.

    Args:
        session: DB 세션.
        kind: 알림 유형(``NOTIFY_*``).
        title: 제목(200자까지).
        message: 본문.
        now: 만든 시각(UTC naive).

    Returns:
        만든 알림 id.
    """
    notification = Notification(
        order_id=None, notification_type=kind, target_type="ROLE", target_role=NOTIFY_ROLE,
        # is_urgent=True 는 상급자 에스컬레이션을 부른다 — 감시 보고는 그 대상이 아니다.
        is_urgent=False, title=title[:200], message=message, is_read=False, created_at=now,
    )
    session.add(notification)
    session.flush()
    fan_out_new_notification(session, notification, actor_user_id=None)
    return int(notification.id)


# ── 언제 · 한 번만 ───────────────────────────────────────────────────────
@dataclass
class Published:
    """:func:`publish` 결과 — 종류마다 새로 알린 수 · 아침 보고를 냈는가."""

    alerts: dict[str, int] = field(default_factory=dict)
    report_sent: bool = False


@dataclass
class _Plan:
    """이번 바퀴에 새로 알릴 것(이미 알린 열쇠는 뺐다)과 낼 아침 보고 날."""

    new: dict[str, dict[str, Any]]
    report_day: Optional[datetime.date]

    @property
    def has_work(self) -> bool:
        """쓸 것이 있는가."""
        return self.report_day is not None or any(self.new.values())


def report_day_for(now: datetime.datetime, hour: int, cal: BusinessDayFn) -> Optional[datetime.date]:
    """아침 보고를 낼 날 — 오늘이 운영일이고 보고 시각이 지났으면 오늘, 아니면 ``None``."""
    local = now.astimezone(KST)
    return local.date() if local.hour >= hour and cal(local.date()) else None


def seconds_until_report(now: datetime.datetime, hour: int = REPORT_HOUR) -> float:
    """다음 보고 시각(KST ``hour`` 시)까지 남은 초 — 러너가 그 시각에 맞춰 깬다."""
    local = now.astimezone(KST)
    target = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if local >= target:
        target += datetime.timedelta(days=1)
    return (target - local).total_seconds()


def pending_webhooks(session: Any, now: datetime.datetime) -> dict[str, datetime.datetime]:
    """1분 넘게 'pending' 인 웹훅 일(원장 R4-11) — {일 id: 받은 시각(UTC naive)}. 경보 나이 상한 안만 본다."""
    base = naive_utc(now)
    stmt = (select(ChannelWebhookJob.id, ChannelWebhookJob.created_at)
            .where(ChannelWebhookJob.status == "pending", ChannelWebhookJob.created_at <= base - PENDING_WEBHOOK_AFTER,
                   ChannelWebhookJob.created_at >= base - WATCH_LOOKBACK)
            .order_by(ChannelWebhookJob.created_at).limit(PENDING_WEBHOOK_LIMIT))
    return {str(row.id): row.created_at for row in session.execute(stmt)}


def read_state(session: Any, *, for_update: bool = False) -> dict:
    """루프 기록 사본(없으면 빈 dict). ``for_update`` 면 그 줄을 잠근다(PostgreSQL)."""
    row = session.get(SystemSetting, STATE_KEY, populate_existing=True, with_for_update=True if for_update else None)
    value = row.setting_value if row is not None else None
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def read_last_success(session: Any) -> Optional[datetime.datetime]:
    """하트비트 metadata 의 마지막 정상 바퀴 시각(시간대 있는 UTC). 없거나 꼴이 틀리면 ``None``."""
    row = session.get(SideEffectWorkerHeartbeat, WORKER_KIND_CS_LOOP, populate_existing=True)
    meta = row.metadata_json if row is not None else None
    stamp = _stamp_of(meta.get(HEARTBEAT_LAST_SUCCESS_KEY)) if isinstance(meta, dict) else None
    return stamp.replace(tzinfo=datetime.timezone.utc) if stamp is not None else None


def _stamp_of(value: Any) -> Optional[datetime.datetime]:
    """기록의 시각(UTC naive ISO) → datetime. 없거나 꼴이 틀리면 ``None``."""
    try:
        return datetime.datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _plan(state: dict, candidates: Mapping[str, Mapping[str, Any]], report_day: Optional[datetime.date]) -> _Plan:
    """기록과 견주어 새로 알릴 것만 고른다."""
    alerted = state.get("alerted") if isinstance(state.get("alerted"), dict) else {}
    new = {kind: {key: item for key, item in candidates[kind].items() if key not in (alerted.get(kind) or {})}
           for kind in ALERT_KINDS}
    due = report_day if report_day is not None and state.get("report_date") != report_day.isoformat() else None
    return _Plan(new, due)


def _prune(keys: dict[str, str], current: Mapping[str, Any], keep: datetime.timedelta,
           now: datetime.datetime) -> dict[str, str]:
    """알린 열쇠 정리 — 지금 후보는 남기고, 후보가 아닌 것은 ``keep`` 이 지나면 지운다. 개수 상한은 새 것부터."""
    floor = naive_utc(now) - keep
    kept = {k: v for k, v in keys.items() if (stamp := _stamp_of(v)) is not None and (k in current or stamp >= floor)}
    return dict(sorted(sorted(kept.items(), key=lambda kv: kv[1], reverse=True)[:ALERT_KEYS_MAX]))


def _next_state(state: dict, plan: _Plan, candidates: Mapping[str, Mapping[str, Any]],
                now: datetime.datetime) -> dict:
    """알린 열쇠 · 보고 날을 더한 새 기록."""
    stamp = naive_utc(now).isoformat(timespec="seconds")
    old = state.get("alerted") if isinstance(state.get("alerted"), dict) else {}
    alerted = {kind: _prune({**dict(old.get(kind) or {}), **{key: stamp for key in plan.new[kind]}},
                            candidates[kind], ALERT_KEEP[kind], now) for kind in ALERT_KINDS}
    nxt = {**state, "alerted": alerted, "rev": int(state.get("rev") or 0) + 1}
    if plan.report_day is not None:
        nxt.update(report_date=plan.report_day.isoformat(), report_sent_at=stamp)
    return nxt


def _recent(state: dict, kind: str, now: datetime.datetime, within: datetime.timedelta) -> int:
    """기록에서 ``within`` 안에 알린 열쇠 수."""
    floor = naive_utc(now) - within
    keys = (state.get("alerted") or {}).get(kind) or {}
    return sum(1 for v in keys.values() if (stamp := _stamp_of(v)) is not None and stamp >= floor)


def _ensure_state_row(session: Any) -> None:
    """루프 기록 줄이 없으면 만든다(커밋). 같은 때 다른 컨테이너가 먼저 만들었으면 그 줄을 쓴다."""
    if session.get(SystemSetting, STATE_KEY) is not None:
        return
    session.add(SystemSetting(setting_key=STATE_KEY, setting_value={},
                              description="AI 상담팀원 감시 루프 기록 — 알린 열쇠 · 아침 보고 날(플랜 C1-3)"))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()


_ALERT_BUILDERS: dict[str, Callable[[list], tuple[str, str]]] = {
    ALERT_PROMISE: promise_alert, ALERT_WEBHOOK: webhook_alert, ALERT_INBOUND: inbound_alert}


def publish(session: Any, *, states: Sequence[ChatState], missing: Sequence[MissingInbound],
            checks: Mapping[str, str], watch_missing_inbound: bool, now: datetime.datetime,
            is_business_day: BusinessDayFn, report_hour: int = REPORT_HOUR,
            stop_check: Optional[Callable[[], None]] = None) -> Published:
    """경보 · 아침 보고를 낸다 — 새로 알릴 것이 있을 때만 기록 줄을 잠그고 다시 견준 뒤 알림과 함께 커밋한다.

    Args:
        session: DB 세션(이 함수가 커밋한다).
        states: 열린 상담 상태.
        missing: 이번 바퀴 채널톡 보정이 찾은 수신 누락 글.
        checks: 브랜드 → 채널톡 보정 상태.
        watch_missing_inbound: 수신 누락 경보를 켠 환경인가(웹훅이 오는 운영만).
        now: 지금(시간대 있는 값).
        is_business_day: 운영일 판정 — 아침 보고는 운영일만.
        report_hour: 아침 보고 시각(KST).
        stop_check: 쓰기 바로 앞마다 부르는 TERM 깃발 확인(멈추면 예외 — 부르는 쪽이 롤백해 줄 잠금도 풀린다, 원장 R5-3).

    Returns:
        :class:`Published`.
    """
    check_stop = stop_check or (lambda: None)
    candidates = {
        ALERT_PROMISE: {f"{s.chat_id}|{s.open_promise.message_id}": s for s in states
                        if s.promise_overdue and s.open_promise is not None},
        ALERT_WEBHOOK: pending_webhooks(session, now),
        ALERT_INBOUND: {f"{m.chat_id}|{m.message_id}": m for m in missing} if watch_missing_inbound else {},
    }
    report_day = report_day_for(now, report_hour, is_business_day)
    if not _plan(read_state(session), candidates, report_day).has_work:
        session.commit()
        return Published()
    check_stop()  # 기록 줄 쓰기 전
    _ensure_state_row(session)
    state = read_state(session, for_update=True)  # 두 컨테이너가 겹쳐도 여기서 한 줄로 선다
    plan = _plan(state, candidates, report_day)
    if not plan.has_work:  # 기다리는 사이 다른 컨테이너가 이미 냈다
        session.commit()
        return Published()
    check_stop()  # 알림 쓰기 전(줄 잠금을 기다리는 사이 TERM 이 왔을 수 있다)
    nxt = _next_state(state, plan, candidates, now)
    published = _send(session, plan, nxt, states=states, candidates=candidates, checks=checks,
                      watch_missing_inbound=watch_missing_inbound, now=now)
    row = session.get(SystemSetting, STATE_KEY)
    row.setting_value = nxt
    row.version = int(row.version or 1) + 1
    session.commit()
    return published


def _send(session: Any, plan: _Plan, nxt: dict, *, states: Sequence[ChatState],
          candidates: Mapping[str, Mapping[str, Any]], checks: Mapping[str, str], watch_missing_inbound: bool,
          now: datetime.datetime) -> Published:
    """새 경보(종류마다 한 건)와 아침 보고를 알림으로 만든다(커밋은 부르는 쪽 — 기록과 한 트랜잭션)."""
    stamp, published = naive_utc(now), Published()
    for kind in ALERT_KINDS:
        if plan.new[kind]:
            title, message = _ALERT_BUILDERS[kind](list(plan.new[kind].values()))
            post_admin_notification(session, kind=_NOTIFY_TYPES[kind], title=title, message=message, now=stamp)
            published.alerts[kind] = len(plan.new[kind])
    if plan.report_day is None:
        return published
    facts = ReportFacts(
        day=plan.report_day, states=states, pending_webhooks=len(candidates[ALERT_WEBHOOK]),
        missing_inbound_24h=(_recent(nxt, ALERT_INBOUND, now, datetime.timedelta(hours=24))
                             if watch_missing_inbound else None),
        checks=checks, last_success_at=read_last_success(session))
    title, message = morning_report(facts)
    post_admin_notification(session, kind=NOTIFY_MORNING_REPORT, title=title, message=message, now=stamp)
    published.report_sent = True
    return published
