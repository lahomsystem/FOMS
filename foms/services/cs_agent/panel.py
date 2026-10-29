"""관리 패널 재료 · 스위치 쓰기 — 'AI 상담팀원' 관리자 화면(설계서 16.1 · 16.6 단계 1)의 스위치 · 두뇌 · 기록 탭.

- **스위치**: 바로 끄기 줄(:data:`.loop.SWITCH_KEY`)의 ``loop`` · ``draft`` 칸을 기존 함수 그대로 바꾼다
  (:func:`.loop.set_switch` · :func:`.turns.set_draft_mode` — 다른 칸은 그대로). 화면에서 바꾼 것마다 수정 기록
  (``SystemSettingReceipt`` — 누가 · 언제 · 무엇을)과 감사 원장 한 줄을 스위치 값과 같은 트랜잭션에 남긴다. 버전 대조는
  하지 않는다 — 값이 '켬 · 멈춤'처럼 목표 값이라 두 사람이 겹쳐도 마지막 값이 맞고, 비상 정지는 막히면 안 된다.
  같은 값이면 쓰지 않는다.
- **읽기판(:func:`panel_state`)**: 스위치 · 설정 칸 · 오늘(KST) 돈 줄 · 오늘 차례 상태 · 감시 루프 하트비트 · 마지막 아침
  보고 · 최근 바꿈 20개. 숫자 · 코드 · 시각 · 직원 이름만 싣는다 — 손님 글 · 상담 id 는 싣지 않는다.
- 하루 상한 천장은 WORKER(두뇌가 도는 곳)가 감시 루프 하트비트에 남긴 자기 env 값이다(:func:`.brain_spend.worker_daily_cap`
  — 이 화면은 env 를 읽지 않는다). 모르면 'WORKER 상한 확인 안 됨'이고, 돈은 늘 WORKER 가 부를 때 자기 env 로 다시 자른다.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select

from foms.services.cs_agent.brain_spend import kst_now, today_spend, worker_daily_cap
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.loop import SWITCH_KEY, SWITCH_OFF, SWITCH_ON, read_switch, set_switch
from foms.services.cs_agent.report import NOTIFY_MORNING_REPORT, format_kst, read_last_success
from foms.services.cs_agent.settings import (
    FIELD_BY_NAME, FIELDS, POLICY_ID, RECEIPT_KEEP, SETTINGS_KEY, PanelSettings, field_view, read_settings,
    value_label,
)
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.turns import DRAFT_MODES, DRAFT_OFF, STATES, draft_mode, set_draft_mode
from foms.services.sidefx_worker import WORKER_KIND_CS_LOOP, WORKER_KIND_SPECS
from models import (
    CsAgentTurn, Notification, SecurityLog, SideEffectWorkerHeartbeat, SystemSetting, SystemSettingReceipt, User,
)

__all__ = [
    "CHANGES_LIMIT", "PANEL_REASON", "SWITCH_POLICY_ID", "change_draft_mode", "change_loop", "panel_state",
    "recent_changes",
]

#: 스위치 수정 기록 이름(``SystemSettingReceipt.policy_id``).
SWITCH_POLICY_ID = "CS_AGENT_SWITCH"
#: 화면에서 초안 스위치를 바꾼 까닭 코드(스위치 줄 ``draft_reason`` 칸 — 막는 장치 코드와 가른다).
PANEL_REASON = "admin_panel"
CHANGES_LIMIT = 20
_SWITCH_RECEIPTS = 50  # '누가' 를 찾을 때 볼 최근 스위치 기록 수
FIELD_LOOP, FIELD_DRAFT = "loop", "draft"
_FIELD_DEFAULT = {FIELD_LOOP: SWITCH_ON, FIELD_DRAFT: DRAFT_OFF}
_SWITCH_LABELS = {FIELD_LOOP: {SWITCH_ON: "켜짐", SWITCH_OFF: "멈춤"},
                  FIELD_DRAFT: {"off": "끔", "store": "저장만", "memo": "내부 메모"}}
_SWITCH_NAMES = {FIELD_LOOP: "비상 정지(감시 루프)", FIELD_DRAFT: "초안 스위치"}
UTC = datetime.timezone.utc


# ── 스위치 쓰기 ──────────────────────────────────────────────────────────
def _already(row: Optional[SystemSetting], field: str, target: str) -> bool:
    """줄에 이미 그 값이 그대로 있나. 줄 · 칸이 없으면 처음 값(감시 루프 켬 · 초안 끔)과 견준다."""
    if row is None:
        return target == _FIELD_DEFAULT[field]
    value = row.setting_value
    return isinstance(value, dict) and value.get(field, _FIELD_DEFAULT[field]) == target


def _record(session: Any, *, field: str, before: str, after: str, version: int, actor_user_id: int,
            now: datetime.datetime) -> None:
    """스위치 수정 기록 + 감사 원장 한 줄(커밋은 부르는 쪽). ``at`` 은 스위치 줄의 바꾼 때 칸과 같은 글이다."""
    data = {"field": field, "from": before, "to": after, "at": naive_utc(now).isoformat(timespec="seconds")}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
    session.add(SystemSettingReceipt(
        read_receipt_id=str(uuid.uuid4()), actor_user_id=actor_user_id, setting_key=SWITCH_KEY,
        policy_id=SWITCH_POLICY_ID, idempotency_key=None, request_hash=digest, response_status=200,
        response_body={"success": True, "data": data}, resulting_version=version,
        expires_at=naive_utc(now) + RECEIPT_KEEP))
    session.add(SecurityLog(
        user_id=actor_user_id, action="CS_AGENT_SWITCH", target_type="system_setting",
        message=f"CS_AGENT_SWITCH key={SWITCH_KEY} field={field} {before}->{after} version={version}",
        detail={"key": SWITCH_KEY, "version": version, **data}))


def change_loop(session: Any, *, on: bool, actor_user_id: int, now: datetime.datetime) -> bool:
    """비상 정지 — 감시 루프 켬 · 멈춤. 바꿨으면 True(같은 값이면 쓰지 않는다). 커밋까지 한다.

    :func:`.loop.set_switch` 가 값 · 버전과 함께 앞서 넣은 수정 기록 · 감사도 한 번에 커밋한다.
    """
    row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True, with_for_update=True)
    target = SWITCH_ON if on else SWITCH_OFF
    if _already(row, FIELD_LOOP, target):
        session.commit()  # 잠금을 푼다
        return False
    before = SWITCH_ON if read_switch(session) else SWITCH_OFF
    version = int(row.version or 1) + 1 if row is not None else 1  # set_switch 가 올릴 버전(새 줄은 1)
    _record(session, field=FIELD_LOOP, before=before, after=target, version=version, actor_user_id=actor_user_id,
            now=now)
    set_switch(session, on=on, now=now)
    return True


def change_draft_mode(session: Any, *, mode: str, actor_user_id: int, now: datetime.datetime) -> bool:
    """초안 스위치 — ``off`` · ``store`` · ``memo``. 바꿨으면 True(같은 값이면 쓰지 않는다). 커밋까지 한다.

    Raises:
        ValueError: 모르는 값.
    """
    if mode not in DRAFT_MODES:
        raise ValueError("모르는 초안 스위치 값")
    row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True, with_for_update=True)
    if _already(row, FIELD_DRAFT, mode):
        session.commit()
        return False
    before = draft_mode(session)
    set_draft_mode(session, mode, reason=PANEL_REASON, now=now)
    session.flush()
    version = int(session.get(SystemSetting, SWITCH_KEY).version or 1)
    _record(session, field=FIELD_DRAFT, before=before, after=mode, version=version, actor_user_id=actor_user_id,
            now=now)
    session.commit()
    return True


# ── 읽기판 ───────────────────────────────────────────────────────────────
def _stamp(value: Any) -> Optional[datetime.datetime]:
    """기록의 시각(UTC naive ISO 글) → 시간대 있는 UTC. 없거나 꼴이 틀리면 ``None``."""
    try:
        return datetime.datetime.fromisoformat(str(value)).replace(tzinfo=UTC) if value else None
    except ValueError:
        return None


def _label(value: Optional[datetime.datetime]) -> Optional[str]:
    """시각 → KST '10-29 14:03'(없으면 ``None``)."""
    return format_kst(value) if value is not None else None


def _data(receipt: SystemSettingReceipt) -> dict[str, Any]:
    """수정 기록 본문의 ``data`` 칸(꼴이 틀리면 빈 dict)."""
    body = receipt.response_body if isinstance(receipt.response_body, dict) else {}
    return body["data"] if isinstance(body.get("data"), dict) else {}


def _receipts(session: Any, policies: tuple[str, ...], limit: int) -> list[tuple[SystemSettingReceipt, Any]]:
    """최근 수정 기록(새 것부터) + 넣은 사람 이름(계정을 지웠으면 ``None``). 설정 키 색인으로 고른다."""
    stmt = (select(SystemSettingReceipt, User.name)
            .outerjoin(User, User.id == SystemSettingReceipt.actor_user_id)
            .where(SystemSettingReceipt.setting_key.in_((SETTINGS_KEY, SWITCH_KEY)),
                   SystemSettingReceipt.policy_id.in_(policies))
            .order_by(SystemSettingReceipt.id.desc()).limit(limit))
    return [(receipt, name) for receipt, name in session.execute(stmt)]


def _changed_by(stamp: Any, current: str, receipts: list[tuple[SystemSettingReceipt, Any]],
                field: str) -> dict[str, Any]:
    """바꾼 때 · 누가 — 그 칸의 **가장 새** 화면 기록의 때 · 바꾼 값이 줄과 같으면 그 사람(``panel``), 아니면 화면 밖
    (``other`` — 스크립트 · 막는 장치). 때는 초 단위라 값도 같이 견주고, 옛 화면 기록은 보지 않는다(그 뒤에 화면 밖에서
    같은 초 · 같은 값으로 되돌린 것을 옛 기록으로 보지 않게)."""
    if not stamp:
        return {"at": None, "by": None, "source": None}
    latest = next(((receipt, name) for receipt, name in receipts if _data(receipt).get("field") == field), None)
    who = None
    if latest is not None and (_data(latest[0]).get("at"), _data(latest[0]).get("to")) == (stamp, current):
        who = latest[1] or "(지운 계정)"
    return {"at": _label(_stamp(stamp)), "by": who, "source": "panel" if who else "other"}


def _switch_view(session: Any) -> dict[str, Any]:
    """스위치 탭 — 감시 루프 · 초안 스위치 값과 바꾼 때 · 누가(손님 정보 없음)."""
    row = session.get(SystemSetting, SWITCH_KEY, populate_existing=True)
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    receipts = _receipts(session, (SWITCH_POLICY_ID,), _SWITCH_RECEIPTS)
    reason = value.get("draft_reason")
    running, mode = SWITCH_ON if read_switch(session) else SWITCH_OFF, draft_mode(session)
    return {"loop": running, "draft": mode,
            "loop_changed": _changed_by(value.get("changed_at"), running, receipts, FIELD_LOOP),
            "draft_changed": _changed_by(value.get("draft_changed_at"), mode, receipts, FIELD_DRAFT),
            "draft_reason": reason if isinstance(reason, str) else None,
            "version": int(row.version or 0) if row is not None else 0}


def _caps(session: Any, cfg: PanelSettings) -> dict[str, Any]:
    """하루 상한 — WORKER env 값(하트비트) · 그 상태(ok · missing · unknown) · 화면 값 · 쓰는 값(둘 가운데 작은 것 — 모르면 ``None``)."""
    worker = worker_daily_cap(session)
    cap: Optional[Decimal] = worker.cap
    seen = worker.seen_at.replace(tzinfo=UTC) if worker.seen_at is not None else None
    return {"worker": None if cap is None else str(cap), "worker_state": worker.state, "worker_seen": _label(seen),
            "panel": cfg.get("daily_cap_usd_panel"),
            "effective": None if cap is None else str(cfg.daily_cap(cap))}


def _settings_view(cfg: PanelSettings) -> dict[str, Any]:
    """두뇌 탭 — 칸(고를 수 있는 값 · 범위 · 지금 값) · 버전 · 처음 값으로 돌린 칸."""
    return {"version": cfg.version, "fallback_fields": list(cfg.fallback_fields),
            "fields": [field_view(field, cfg.get(field.name)) for field in FIELDS]}


def _turn_counts(session: Any, since: datetime.datetime) -> dict[str, Any]:
    """오늘 바뀐 차례 수 — 상태별 · (상태, 까닭 코드)별. ``state IN (…)`` 이라 (state, updated_at) 색인을 탄다."""
    stmt = (select(CsAgentTurn.state, CsAgentTurn.error_code, func.count())
            .where(CsAgentTurn.state.in_(STATES), CsAgentTurn.updated_at >= since)
            .group_by(CsAgentTurn.state, CsAgentTurn.error_code))
    by_state = {state: 0 for state in STATES}
    detail = []
    for state, code, count in session.execute(stmt):
        by_state[state] += int(count)
        detail.append({"state": state, "code": code, "count": int(count)})
    detail.sort(key=lambda item: (-item["count"], item["state"], item["code"] or ""))
    return {"total": sum(by_state.values()), "by_state": by_state, "by_code": detail}


def _heartbeat(session: Any, now: datetime.datetime) -> dict[str, Any]:
    """감시 루프(CS_LOOP) 하트비트 — 마지막 시각 · 몇 분 전 · 늦음(3틱) · 바퀴 결과 코드 · 마지막 정상 바퀴."""
    row = session.get(SideEffectWorkerHeartbeat, WORKER_KIND_CS_LOOP, populate_existing=True)
    if row is None or row.last_heartbeat_at is None:
        return {"at": None, "age_minutes": None, "stale": True, "outcome": None, "last_success": None}
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    beat = row.last_heartbeat_at.replace(tzinfo=UTC)
    age = max(0, int((now - beat).total_seconds()))
    outcome = meta.get("outcome")
    return {"at": _label(beat), "age_minutes": age // 60,
            "stale": age > WORKER_KIND_SPECS[WORKER_KIND_CS_LOOP].max_heartbeat_age,
            "outcome": outcome if isinstance(outcome, str) else None,
            "last_success": _label(read_last_success(session))}


def _last_report(session: Any) -> Optional[dict[str, Any]]:
    """마지막 아침 보고 — 제목(손님 정보 없음 — 칸별 수만) · 낸 때."""
    row = session.execute(select(Notification.title, Notification.created_at)
                          .where(Notification.notification_type == NOTIFY_MORNING_REPORT)
                          .order_by(Notification.id.desc()).limit(1)).first()
    if row is None:
        return None
    created = row.created_at.replace(tzinfo=UTC) if isinstance(row.created_at, datetime.datetime) else None
    return {"title": row.title, "at": _label(created)}


def _change_entry(receipt: SystemSettingReceipt, name: Any) -> dict[str, Any]:
    """기록 표 한 줄 — 때 · 누가 · 무엇 · 바뀐 값(설정은 칸 이름과 화면 글)."""
    data = _data(receipt)
    created = receipt.created_at.replace(tzinfo=UTC) if isinstance(receipt.created_at, datetime.datetime) else None
    entry = {"at": _label(_stamp(data.get("at")) or created), "who": name or "(지운 계정)",
             "version": receipt.resulting_version}
    if receipt.policy_id == SWITCH_POLICY_ID:
        field = str(data.get("field"))
        labels = _SWITCH_LABELS.get(field, {})
        before, after = str(data.get("from")), str(data.get("to"))
        entry.update(what=_SWITCH_NAMES.get(field, "스위치"),
                     detail=f"{labels.get(before, before)} → {labels.get(after, after)}")
        return entry
    changed = data.get("changed") if isinstance(data.get("changed"), dict) else {}
    parts = [f"{FIELD_BY_NAME[n].label} {value_label(n, c.get('from'))} → {value_label(n, c.get('to'))}"
             + (" (틀린 값 고침)" if c.get("repaired") else "")
             for n, c in changed.items() if n in FIELD_BY_NAME and isinstance(c, dict)]
    entry.update(what="두뇌 · 돈 설정", detail=" · ".join(parts) or "-")
    return entry


def recent_changes(session: Any, *, limit: int = CHANGES_LIMIT) -> list[dict[str, Any]]:
    """최근 설정 · 스위치 바꿈(새 것부터, 화면에서 바꾼 것만 — 스크립트 · 막는 장치는 스위치 탭의 '화면 밖'으로 보인다)."""
    return [_change_entry(receipt, name) for receipt, name in _receipts(session, (POLICY_ID, SWITCH_POLICY_ID), limit)]


def panel_state(session: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """관리 화면 한 덩어리(JSON 꼴) — 스위치 · 두뇌 설정 · 하루 상한 · 기록. 읽기만 한다(커밋 · 잠금 없음)."""
    now = kst_now(now)
    day_start = naive_utc(datetime.datetime(now.year, now.month, now.day, tzinfo=KST))
    cfg = read_settings(session, log=False)  # 틀린 칸은 화면이 보인다 — 경고 로그는 초안 바퀴가 바퀴마다 한 번
    return {"now": format_kst(now), "day": now.date().isoformat(), "switch": _switch_view(session),
            "settings": _settings_view(cfg), "caps": _caps(session, cfg),
            "records": {"spend": today_spend(session, now=now), "turns": _turn_counts(session, day_start),
                        "heartbeat": _heartbeat(session, now), "report": _last_report(session)},
            "changes": recent_changes(session)}
