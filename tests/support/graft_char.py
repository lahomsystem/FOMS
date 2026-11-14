"""특성 시험(T13 · D206) 공용 도우미 — 주문 하나의 '자국'을 뜨고 앞뒤 차이를 글자로 낸다.

처리기 셋(현재 작업 승인 · 도면 담당 맡기기 · 실측일 고치기)을 함수로 떼어 내기 전에(T14)
**지금 행동**을 그대로 찍어 둔다. 시험은 길을 부르기 전 · 뒤에 :func:`snapshot` 을 뜨고
:func:`delta` 가 낸 차이를 글자 그대로 적은 기대값과 통째로 견준다. 그래서 옆 효과 하나가
더 생기거나 사라져도 견주기가 빨개진다.

* 세는 것: 주문 일 기록(``order_events``) 종류별 · 감사 줄(``security_logs``) ``action`` 별 ·
  변경 원장(``order_field_changes``) ``경로 꼴 · op · 앞 → 뒤`` 별 · 사유 줄 · 알림 종류와
  받는 팀 · 받는 사람 줄 · 줄 세운 바깥 일(``domain_side_effect_outbox``) ``effect_type`` 별 ·
  영수증(``order_mutation_receipts``) 정책별 · 담당 줄 · 날짜 찾기 표 · 고른 ``structured_data``
  경로 값 · 납작 칸 · ``mutation_version`` 이 오른 폭.
* 빼는 것: 시각(``…_at`` 칸 · datetime 값은 ``<시각>`` 한 글자로 접는다) · 묶음 번호(uuid).
* :func:`new_rows` 는 새로 생긴 일 기록 · 감사 · 바깥 일 줄의 **내용**을 낸다(대표 장면의 줄을 글자 그대로 견준다).
* 바깥으로 나가는 것(푸시 · 화면 알림 · 알림톡)은 :func:`install_fakes` 가 가짜로 바꿔 끼우고
  부른 횟수만 적는다. 시험은 아무것도 밖으로 보내지 않는다.
"""

from __future__ import annotations

import datetime as _dt
import re
import time
from collections import Counter
from typing import Any, Callable, Iterable

from db import db_session
from foms.services import audit_writer
from models import (
    DomainSideEffectOutbox,
    Notification,
    NotificationUserState,
    Order,
    OrderAssignment,
    OrderChangeReason,
    OrderEvent,
    OrderFieldChange,
    OrderMutationReceipt,
    OrderScheduleDate,
    SecurityLog,
    User,
)

#: 시각 값을 접은 글자 — 값이 있었는지만 남긴다.
TS = "<시각>"
#: 경로에 값이 없을 때의 글자(빈 문자열 · None 과 가른다).
ABSENT = "<없음>"
#: 감사 줄 ``action`` 이 비었을 때의 글자.
NO_ACTION = "-"
#: 시험 안의 '오늘'(KST). 모든 시험 날짜는 이 날과 다르다 — 당일 실측 알림 시험만 이 날을 쓴다.
FAKE_TODAY = "2031-03-14"

#: 시각 칸이 다른 시각으로 바뀌었을 때의 글자.
NEW_TS = "<새 시각>"
#: 묶음 번호(uuid)를 접은 글자.
GROUP = "<묶음>"

_TS_KEY = re.compile(r"(^|_)at$")
_UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")
_COUNTED = ("events", "audit", "field_changes", "notifications", "outbox", "receipts")
_LISTS = ("assignments", "schedule_dates")


def scrub(value: Any) -> Any:
    """시각을 ``<시각>`` 으로 접은 사본을 돌려준다(dict · list 는 안까지).

    Args:
        value: JSON 꼴 값 또는 datetime.

    Returns:
        시각 칸(키가 ``at`` · ``…_at``) 과 datetime 값을 ``<시각>`` 으로 바꾼 값.
    """
    if isinstance(value, (_dt.datetime, _dt.date)):
        return TS
    if isinstance(value, dict):
        return {
            k: (TS if _TS_KEY.search(str(k)) and v not in (None, "") else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str) and _UUID.fullmatch(value):
        return GROUP
    return value


def sd_get(sd: Any, path: str) -> Any:
    """점 경로 값(없으면 ``<없음>``)."""
    cur = sd
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return ABSENT
        cur = cur[part]
    return cur


def _order_counts(order_id: int) -> dict[str, Any]:
    """주문에 묶인 줄(일 기록 · 원장 · 사유 · 알림 · 담당 · 날짜)을 센다."""
    events = Counter(
        r.event_type for r in db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id)
    )
    changes = Counter(
        f"{r.path_template} {r.op} {r.before_value} -> {r.after_value}"
        for r in db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == order_id)
    )
    notifs = db_session.query(Notification).filter(Notification.order_id == order_id).all()
    notif_ids = [n.id for n in notifs]
    states = (
        db_session.query(NotificationUserState)
        .filter(NotificationUserState.notification_id.in_(notif_ids)).count()
        if notif_ids else 0
    )
    return {
        "events": events,
        "field_changes": changes,
        "reasons": db_session.query(OrderChangeReason)
        .filter(OrderChangeReason.order_id == order_id).count(),
        "notifications": Counter(
            f"{n.notification_type}/{n.target_type}/{n.target_team}" for n in notifs
        ),
        "notification_states": states,
        "assignments": sorted(
            (r.domain, int(r.user_id), bool(r.active))
            for r in db_session.query(OrderAssignment).filter(OrderAssignment.order_id == order_id)
        ),
        "schedule_dates": sorted(
            (r.kind, r.date, r.source)
            for r in db_session.query(OrderScheduleDate).filter(OrderScheduleDate.order_id == order_id)
        ),
    }


def _global_counts() -> dict[str, Any]:
    """시험마다 DB 가 비므로 전역으로 세는 줄(감사 · 바깥 일 · 영수증) + 줄 내용(번호 순)."""
    audits = db_session.query(SecurityLog).order_by(SecurityLog.id).all()
    boxes = db_session.query(DomainSideEffectOutbox).order_by(DomainSideEffectOutbox.id).all()
    return {
        "audit": Counter((r.action or NO_ACTION) for r in audits),
        "outbox": Counter(r.effect_type for r in boxes),
        "receipts": Counter(r.policy_id for r in db_session.query(OrderMutationReceipt)),
        "_audit_rows": [
            (r.id, (r.action or NO_ACTION, r.target_type, r.target_id, r.message, scrub(r.detail)))
            for r in audits
        ],
        "_outbox_rows": [(r.id, (r.effect_type, scrub(r.payload), r.status)) for r in boxes],
    }


def _event_rows(order_id: int) -> list[tuple[int, tuple]]:
    """주문 일 기록 줄 내용(번호 순 · 시각 뺌)."""
    rows = (
        db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id)
        .order_by(OrderEvent.id).all()
    )
    return [(r.id, (r.event_type, scrub(r.payload))) for r in rows]


def fresh_tick() -> None:
    """시계 눈금이 한 번 넘어갈 때까지 기다린다(1초 안).

    Windows 의 ``datetime.now()`` 는 눈금이 1 ~ 16ms 라, 데워진 프로세스에서 한 시험 안의 두 쓰기가 같은 눈금에
    들면 두 번째 시각이 첫 번째와 같아져 ``…_at`` 칸이 '안 바뀐' 것으로 보인다(접목판 원장 F-09). 자국을 뜨기 전에
    눈금을 넘겨 두면 그 뒤 쓰기의 시각은 앞선 쓰기보다 늘 크다. 시험이 지켜보는 행동은 바뀌지 않는다.
    """
    start = _dt.datetime.now()
    deadline = time.monotonic() + 1.0
    while _dt.datetime.now() == start and time.monotonic() < deadline:
        pass


def snapshot(order_id: int, *, sd_paths: Iterable[str] = (), flat: Iterable[str] = (),
             views: dict[str, Callable[[dict], Any]] | None = None) -> dict:
    """주문 하나의 자국을 뜬다(DB 를 새로 읽는다).

    Args:
        order_id: 대상 주문 번호.
        sd_paths: 값을 뜰 ``structured_data`` 점 경로들.
        flat: 값을 뜰 ``orders`` 납작 칸 이름들.
        views: ``이름 → 함수(sd)`` — 긴 값을 시험이 고른 꼴로 줄여 ``sd`` 칸에 함께 싣는다.

    Returns:
        :func:`delta` 가 받는 자국 dict.
    """
    fresh_tick()  # 앞선 쓰기와 같은 시계 눈금에 다음 쓰기가 들지 않게(F-09)
    # 거부 감사 줄의 60초 겹침 거르기는 프로세스 안 캐시다 — 같은 일손에서 먼저 돈 시험이 같은 번호 사용자 · 같은 끝점으로
    # 거부를 남겼으면 이 시험의 ACCESS_DENIED 줄이 빠진다(F-09). 자국을 뜰 때마다 비워 시험끼리 섞이지 않게 한다.
    audit_writer.reset_dedupe_cache()
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = (order.structured_data if order is not None else None) or {}
    snap: dict[str, Any] = {**_order_counts(order_id), **_global_counts()}
    snap["_event_rows"] = _event_rows(order_id)
    snap["sd"] = {p: scrub(sd_get(sd, p)) for p in sd_paths}
    for name, view in (views or {}).items():
        snap["sd"][name] = scrub(view(sd))
    snap["_flat_raw"] = {c: getattr(order, c, ABSENT) for c in flat}
    snap["flat"] = {c: scrub(v) for c, v in snap["_flat_raw"].items()}
    snap["mutation_version"] = int(getattr(order, "mutation_version", 0) or 0)
    return snap


def _counter_delta(before: Counter, after: Counter) -> dict[str, int]:
    """두 셈의 차이(0 이 아닌 것만)."""
    keys = set(before) | set(after)
    return {k: after[k] - before[k] for k in sorted(keys) if after[k] != before[k]}


def _value_delta(before: dict, after: dict) -> dict[str, tuple]:
    """같은 키의 값이 바뀐 것만 ``(앞, 뒤)`` 로."""
    return {k: (before[k], after[k]) for k in before if before[k] != after[k]}


def _flat_delta(before: dict, after: dict) -> dict[str, tuple]:
    """납작 칸 차이 — 시각이 다른 시각으로 바뀌면 ``(<시각>, <새 시각>)`` 으로 보인다."""
    out: dict[str, tuple] = {}
    for col, raw in before["_flat_raw"].items():
        if raw == after["_flat_raw"][col]:
            continue
        b, a = before["flat"][col], after["flat"][col]
        out[col] = (b, a if a != b else NEW_TS)
    return out


def delta(before: dict, after: dict) -> dict:
    """뒤 − 앞. 바뀐 칸만 남긴다(아무것도 안 바뀌면 빈 dict).

    Args:
        before: 길을 부르기 전 :func:`snapshot`.
        after: 길을 부른 뒤 :func:`snapshot`(같은 ``sd_paths`` · ``flat``).

    Returns:
        ``{'events': {...}, 'audit': {...}, …, 'sd': {경로: (앞, 뒤)}, 'mutation_version': 폭}``.
    """
    out: dict[str, Any] = {}
    for key in _COUNTED:
        d = _counter_delta(before[key], after[key])
        if d:
            out[key] = d
    for key in ("reasons", "notification_states"):
        if after[key] != before[key]:
            out[key] = after[key] - before[key]
    for key in _LISTS:
        added = sorted(set(after[key]) - set(before[key]))
        removed = sorted(set(before[key]) - set(after[key]))
        if added or removed:
            out[key] = {"+": added, "-": removed}
    d = _value_delta(before["sd"], after["sd"])
    if d:
        out["sd"] = d
    d = _flat_delta(before, after)
    if d:
        out["flat"] = d
    if after["mutation_version"] != before["mutation_version"]:
        out["mutation_version"] = after["mutation_version"] - before["mutation_version"]
    return out


def new_rows(before: dict, after: dict) -> dict[str, list]:
    """앞 자국 뒤에 새로 생긴 줄의 내용(시각 · 묶음 번호 뺌, 번호 순).

    Args:
        before: 길을 부르기 전 :func:`snapshot`.
        after: 길을 부른 뒤 :func:`snapshot`.

    Returns:
        ``{'events': [(종류, payload)], 'audit': [(action, 대상 종류, 대상 번호, 글, detail)],
        'outbox': [(effect_type, payload, status)]}``.
    """
    out: dict[str, list] = {}
    for key, name in (("_event_rows", "events"), ("_audit_rows", "audit"), ("_outbox_rows", "outbox")):
        seen = {rid for rid, _ in before[key]}
        out[name] = [row for rid, row in after[key] if rid not in seen]
    return out


def quest_rows(sd: dict) -> list[tuple]:
    """퀘스트를 (단계, 상태, 방식, 팀 승인, 담당 승인, 주인) 줄로 줄인다(:func:`snapshot` 의 ``views`` 용).

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        퀘스트마다 ``(stage, status, approval_mode, {팀: (approved, approved_by, by_team)},
        (담당 approved, approved_by), owner_person)`` — 시각 칸은 뺀다.
    """
    rows = []
    for q in sd.get("quests") or []:
        team = {t: (v.get("approved"), v.get("approved_by"), v.get("by_team"))
                for t, v in (q.get("team_approvals") or {}).items()}
        a = q.get("assignee_approval") or {}
        rows.append((q.get("stage"), q.get("status"), q.get("approval_mode"), team,
                     (a.get("approved"), a.get("approved_by")), q.get("owner_person")))
    return rows


class Outbound:
    """가짜로 바꿔 끼운 바깥 보내기의 기록(부른 횟수 · 받는 사람 수 · 알림 종류)."""

    def __init__(self) -> None:
        self.push: list[int] = []
        self.emit: list[tuple[int, str]] = []
        self.alimtalk: list[int] = []
        #: 대시보드 · AS 추천 캐시 비우기 호출(부른 차례대로). ``summary`` 에는 싣지 않는다.
        self.cache: list[tuple] = []

    def summary(self) -> dict[str, Any]:
        """시험이 견줄 꼴 — 안 부른 것은 빠진다(알림 번호는 뺀다)."""
        out: dict[str, Any] = {}
        if self.push:
            out["push"] = len(self.push)
        if self.emit:
            out["emit"] = sorted(self.emit)
        if self.alimtalk:
            out["alimtalk"] = len(self.alimtalk)
        return out


def install_fakes(monkeypatch: Any) -> Outbound:
    """푸시 · 화면 알림 · 실측 알림톡 · 캐시 비우기를 가짜로 바꾸고 '오늘'을 :data:`FAKE_TODAY` 로 고정한다.

    Args:
        monkeypatch: pytest ``monkeypatch``.

    Returns:
        부른 기록을 모으는 :class:`Outbound`.
    """
    from foms.services import kakao_alimtalk
    from foms.services.notifications import measure_same_day, push_sender, realtime_notifications
    from foms.services.partners import notify_listeners

    rec = Outbound()

    def _push(notification_id: Any, db: Any = None) -> dict:
        rec.push.append(int(notification_id))
        return {"enqueued": True, "reason": None}

    def _emit(user_ids: Any, payload: Any = None) -> int:
        ids = list(user_ids or [])
        rec.emit.append((len(ids), str((payload or {}).get("notification_type") or "")))
        return len(ids)

    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", _push)
    monkeypatch.setattr(notify_listeners, "enqueue_push_for_notification", _push)
    monkeypatch.setattr(realtime_notifications, "emit_erp_notification_to_users", _emit)
    monkeypatch.setattr(kakao_alimtalk, "maybe_send_measure_alimtalk", lambda oid: rec.alimtalk.append(int(oid)))
    monkeypatch.setattr(
        measure_same_day, "get_today_kst", lambda: _dt.date.fromisoformat(FAKE_TODAY)
    )
    _record_cache_calls(monkeypatch, rec)
    return rec


def _record_cache_calls(monkeypatch: Any, rec: Outbound) -> None:
    """캐시 비우기 함수 넷을 '부른 기록'으로 바꾼다(처리기는 함수 안에서 모듈 값을 다시 읽는다).

    Args:
        monkeypatch: pytest ``monkeypatch``.
        rec: 기록을 모을 :class:`Outbound`.
    """
    from foms.services import shipment_as_recommendation_cache as asrec
    from foms.services.common import dashboard_cache as dc

    def _families(*families: str) -> int:
        rec.cache.append(("families", tuple(families)))
        return 0

    def _order(order: Any, extra: tuple = ()) -> int:
        rec.cache.append(("order", int(order.id), tuple(extra)))
        return 0

    monkeypatch.setattr(dc, "invalidate_dashboard_families", _families)
    monkeypatch.setattr(dc, "invalidate_all_dashboard_slice_caches", lambda: rec.cache.append(("all",)) or 0)
    monkeypatch.setattr(dc, "invalidate_order_dashboard_families", _order)
    monkeypatch.setattr(asrec, "invalidate_shipment_as_recommendation_cache",
                        lambda reason=None: rec.cache.append(("asrec", reason)))


class Actor:
    """요청 사이 세션이 닫혀도 쓰는 사용자 값 묶음."""

    def __init__(self, user: User) -> None:
        self.id = int(user.id)
        self.username = user.username
        self.role = user.role
        self.team = user.team
        self.name = user.name


def make_user(username: str, *, role: str = "STAFF", team: str | None = "SALES",
              active: bool = True) -> Actor:
    """지어낸 사용자 1명을 커밋한다(이름은 ``<아이디> 직원``)."""
    from werkzeug.security import generate_password_hash

    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 직원", is_active=active)
    db_session.add(user)
    db_session.commit()
    return Actor(user)


def login_as(client: Any, actor: Actor) -> None:
    """시험 손님 세션을 ``actor`` 로 바꾼다."""
    with client.session_transaction() as sess:
        sess["user_id"] = actor.id
        sess["username"] = actor.username
        sess["role"] = actor.role


def make_order(sd: dict | None, *, status: str = "RECEIVED", erp: bool = True, **cols: Any) -> int:
    """지어낸 주문 1건을 커밋하고 번호를 돌려준다(손님 값은 모두 지어낸 것).

    ERP 주문은 저장된 주문처럼 납작 칸을 ``structured_data`` 에 맞춰 둔다(``sync_erp_flat_columns``) —
    그래야 앞뒤 차이에 길이 실제로 바꾼 칸만 남는다. ``cols`` 는 그 뒤에 얹는다.

    Args:
        sd: ``structured_data``(비 ERP 주문이면 None 가능).
        status: ``orders.status``.
        erp: ERP 주문인가.
        **cols: 그 밖의 ``orders`` 칸(``erp_stage_code`` · ``deleted_at`` 등).

    Returns:
        새 주문 번호.
    """
    from foms.services.erp_sync_columns import sync_erp_flat_columns

    order = Order(
        received_date="2031-01-02", customer_name="특성시험 손님", phone="000-0000-0000",
        address="가상시 가상구 시험로 1", product="시험장", status=status,
        is_erp_order=erp, structured_data=sd,
    )
    if erp and isinstance(sd, dict):
        sync_erp_flat_columns(order, sd)
    for name, value in cols.items():
        setattr(order, name, value)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


__all__ = [
    "ABSENT",
    "Actor",
    "FAKE_TODAY",
    "GROUP",
    "NEW_TS",
    "NO_ACTION",
    "Outbound",
    "TS",
    "delta",
    "install_fakes",
    "login_as",
    "make_order",
    "make_user",
    "new_rows",
    "quest_rows",
    "scrub",
    "sd_get",
    "snapshot",
]
