"""도면 마감 알림 — 읽기만 하는 판(때 · 대상 주문 · 글 · 받는 사람). 쓰기는 :mod:`.drawing_deadline_alert` 가 한다.

설계서 ``docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md`` §9(2판 — §14 사장님 답 1 · 3 반영).

- 때(§9-1): 마감 날(늘 영업일) KST 아침 칸 08:00 ~ 10:59 · 저녁 칸 18:00 ~ 20:59. 마감 날이 지나도 안 내려오면 그 뒤
  일하는 날마다 아침 칸에만 다시(§9-7, 답 3) — 내려오거나 시공일이 지날 때까지(시공일 당일은 아직 안 지났다).
- 대상(§9-2): ERP · 지우지 않음 · 단계 ∈ :data:`TARGET_STAGE_CODES`(첫 화면 '기다림' 과 같은 단계) · 납작 시공일 ∈ 오늘 ~ 오늘 + 14일.
- 마감 · 까닭 · 담당 이름은 :mod:`foms.services.production.drawing_arrival` 그대로 — 화면과 알림이 늘 같은 말을 한다.
- 받는 사람(§9-3): 도면 담당(켜진 우리 직원) + 영업 쪽(도면 전달 알림과 같은 규칙). 닿는 도면 담당이 없으면 도면팀 전원 +
  관리자(ADMIN)를 더한다(답 1). 담당이 있으면 관리자를 넣지 않는다(영업 쪽 규칙의 '양산' 관리자 처리는 그대로).

주문 행은 칸만 골라 읽는다(ORM 주문 객체를 만들지 않는다) — 이 판은 주문 ``structured_data`` 를 쓸 길이 없다(§9-6).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func

from foms.services.auth.partner_scope import is_partner_sd
from foms.services.common.business_calendar import business_days_between
from foms.services.notifications.drawing_deadline_push import TITLE_EVENING, TITLE_LATE, TITLE_MORNING
from foms.services.notifications.drawing_notice_target import drawing_notice_target, notice_target_user_ids
from foms.services.notifications.recipients import broad_recipient_ids, team_condition
from foms.services.orders.erp_policy_permissions import get_assignee_ids
from foms.services.orders.manager_names import order_manager_label
from foms.services.production.drawing_arrival import day_md, drawing_blocker, drawing_deadline, drawing_people
from foms.services.production_dashboard_display import _production_first_item, _production_product_label
from models import Order, User

#: 첫 화면 '도면·컨펌 기다림'(``production_home_stage`` 보기 ``wait``)과 같은 단계 — 이 단계면 '아직 안 내려옴'.
TARGET_STAGE_CODES: Tuple[str, ...] = ('도면', 'DRAWING', '고객컨펌', 'CONFIRM')
#: 대상 시공일을 보는 날 수(오늘 ~ 오늘 + 이 날).
LOOKAHEAD_DAYS = 14
KIND_MORNING = 'am'
KIND_EVENING = 'pm'
KIND_LATE = 'late'
#: 칸 → (시작 시, 끝 시) — 끝 시는 들어가지 않는다(08:00 ~ 10:59, 18:00 ~ 20:59).
SLOT_HOURS: Dict[str, Tuple[int, int]] = {KIND_MORNING: (8, 11), KIND_EVENING: (18, 21)}
_KST = datetime.timezone(datetime.timedelta(hours=9))
_TITLES = {KIND_MORNING: TITLE_MORNING, KIND_EVENING: TITLE_EVENING, KIND_LATE: TITLE_LATE}
_WEEKDAY_KO = '월화수목금토일'


@dataclass
class DueAlert:
    """보낼 차례인 알림 하나(주문 하나 · 칸 하나)."""

    order_id: int
    key: str
    kind: str
    day: datetime.date
    deadline: datetime.date
    sd: Dict[str, Any] = field(repr=False)
    customer: str = ''
    product: str = ''
    sales_label: str = ''
    partner: bool = False


def to_kst(now: datetime.datetime) -> datetime.datetime:
    """주입한 시각 → KST 시각. 시간대가 없으면 이미 KST 라고 본다(시험은 KST 로 넣는다)."""
    if now.tzinfo is None:
        return now.replace(tzinfo=_KST)
    return now.astimezone(_KST)


def slot_of(now_k: datetime.datetime) -> Optional[str]:
    """지금 시각의 칸 — ``'am'`` · ``'pm'`` · 창 밖이면 None(KST 시각을 넣는다)."""
    for slot, (start, end) in SLOT_HOURS.items():
        if start <= now_k.hour < end:
            return slot
    return None


def _parse_day(value: Any) -> Optional[datetime.date]:
    text = str(value or '').strip()[:10]
    try:
        return datetime.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _kind_for(day: datetime.date, today: datetime.date, slot: str) -> Optional[Tuple[str, datetime.date]]:
    """그 시공일 주문이 이 칸에 받을 알림 (종류, 마감) — 없으면 None. 오늘은 영업일이라고 본다."""
    deadline = drawing_deadline(day)
    if deadline == today:
        return slot, deadline
    if slot == KIND_MORNING and deadline < today <= day:
        return KIND_LATE, deadline
    return None


def alert_key(order_id: int, kind: str, deadline: datetime.date, today: datetime.date) -> str:
    """한 번만 열쇠 — 마감 날 ``<id>:<마감>:<am|pm>``, 늦음 ``<id>:<그날>:late``(§9-6 · §9-7)."""
    day = today if kind == KIND_LATE else deadline
    return f"{int(order_id)}:{day.isoformat()}:{kind}"


def _due_from_row(row: Any, today: datetime.date, slot: str) -> Optional[DueAlert]:
    day = _parse_day(row.erp_construction_date)
    if day is None:
        return None
    hit = _kind_for(day, today, slot)
    if hit is None:
        return None
    kind, deadline = hit
    sd = row.structured_data if isinstance(row.structured_data, dict) else {}
    customer = str((((sd.get('parties') or {}).get('customer') or {}).get('name')) or row.customer_name or '').strip()
    return DueAlert(order_id=int(row.id), key=alert_key(row.id, kind, deadline, today), kind=kind, day=day,
                    deadline=deadline, sd=sd, customer=customer,
                    product=_production_product_label(_production_first_item(sd)[1]),
                    sales_label=order_manager_label(sd), partner=is_partner_sd(sd) or row.partner_org_id is not None)


def due_alerts(db: Any, today: datetime.date, slot: str) -> Tuple[int, List[DueAlert]]:
    """오늘 이 칸에 보낼 차례인 알림 — 쿼리 1개(``ix_orders_erp_construction_date`` · ``ix_orders_erp_stage_code``).

    Args:
        db: 세션(읽기만).
        today: KST 오늘(영업일이어야 한다 — 부르는 쪽이 본다).
        slot: ``'am'`` 또는 ``'pm'``.

    Returns:
        (본 주문 수, 알림 목록 — 시공일 · 번호 순).
    """
    ceil = today + datetime.timedelta(days=LOOKAHEAD_DAYS)
    rows = (
        db.query(Order.id, Order.erp_construction_date, Order.structured_data, Order.customer_name,
                 Order.partner_org_id)
        .filter(Order.active_filter(), Order.is_erp_order.is_(True),
                Order.erp_stage_code.in_(TARGET_STAGE_CODES),
                Order.erp_construction_date >= today.isoformat(),
                Order.erp_construction_date <= ceil.isoformat())
        .order_by(Order.erp_construction_date, Order.id)
        .all()
    )
    dues = [due for due in (_due_from_row(r, today, slot) for r in rows) if due is not None]
    return len(rows), dues


def still_waiting(db: Any, dues: List[DueAlert]) -> List[DueAlert]:
    """보내기 직전 다시 보기(§9-2) — 아직 기다림 단계이고 납작 시공일이 그대로인 것만(쿼리 1개, 읽기만)."""
    if not dues:
        return []
    rows = (
        db.query(Order.id, Order.erp_stage_code, Order.erp_construction_date)
        .filter(Order.id.in_(sorted({d.order_id for d in dues})), Order.active_filter())
        .all()
    )
    now = {int(r.id): (r.erp_stage_code, _parse_day(r.erp_construction_date)) for r in rows}
    out = []
    for due in dues:
        stage, day = now.get(due.order_id, (None, None))
        if stage in TARGET_STAGE_CODES and day == due.day:
            out.append(due)
    return out


def _md_inline(day: datetime.date) -> str:
    """'11/23 월' — 괄호 안에 넣는 날 글(본문 '오늘(11/23 월)' · '마감(11/23 월)')."""
    return f"{day.month}/{day.day} {_WEEKDAY_KO[day.weekday()]}"


def status_text(due: DueAlert) -> str:
    """'지금:' 뒤 글 — 까닭 · 도면 담당 · 영업 담당(화면 기다림 칸 둘째 줄과 같은 말)."""
    blocker = drawing_blocker(due.sd)
    people = drawing_people(due.sd, due.sales_label)
    return ' · '.join(p for p in (blocker['label'], people['text']) if p)


def alert_text(due: DueAlert, today: datetime.date) -> Tuple[str, str]:
    """(제목, 본문) — 해요체 · 금액 · 전화 · 주소 없음 · 받는 사람마다 같은 글(§9-4 · §9-7).

    Args:
        due: 보낼 알림.
        today: KST 오늘.

    Returns:
        아침 ``#12 김가짜 · 붙박이장 — 11/25 (수) 시공이라 오늘(11/23 월)까지 …``, 저녁 ``저녁 6시인데 #12 김가짜 …``,
        늦음 ``#12 김가짜 도면이 마감(11/23 월)을 1일 넘겼어요. …`` — 늦은 날 수는 영업일로 센다.
    """
    who = f"#{due.order_id} {due.customer}".strip()
    now = status_text(due)
    if due.kind == KIND_MORNING:
        head = f"{who} · {due.product}" if due.product else who
        body = (f"{head} — {day_md(due.day)} 시공이라 오늘({_md_inline(today)})까지 도면이 생산으로 내려와야 해요. "
                f"지금: {now}")
    elif due.kind == KIND_EVENING:
        body = f"저녁 6시인데 {who} 도면이 아직 생산으로 안 내려왔어요. 지금: {now}. 오늘 안에 넘겨 주세요."
    else:
        over = max(1, business_days_between(due.deadline, today))
        body = (f"{who} 도면이 마감({_md_inline(due.deadline)})을 {over}일 넘겼어요. {day_md(due.day)} 시공이에요. "
                f"지금: {now}")
    return _TITLES[due.kind], body


class PeopleCache:
    """한 바퀴 안에서 도면팀 · 관리자 명단을 한 번만 읽는다."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self._team: Optional[Set[int]] = None
        self._admins: Optional[Set[int]] = None

    def drawing_team(self) -> Set[int]:
        """켜진 우리 직원 가운데 도면팀(협력사 · 켜진 프리랜서 뺌)."""
        if self._team is None:
            self._team = broad_recipient_ids(self.db, team_condition('DRAWING'))
        return self._team

    def admins(self) -> Set[int]:
        """켜진 관리자(ADMIN) 계정."""
        if self._admins is None:
            self._admins = broad_recipient_ids(self.db, func.upper(User.role) == 'ADMIN')
        return self._admins


def recipients_for(db: Any, due: DueAlert, cache: PeopleCache) -> Dict[str, Any]:
    """받는 사람(§9-3) — ``{'drawing', 'sales', 'admins', 'fallback', 'all'}`` (id 집합, ``fallback`` = 닿는 담당 없음).

    Args:
        db: 세션(읽기만).
        due: 알림 하나.
        cache: 한 바퀴의 도면팀 · 관리자 명단.

    Returns:
        도면 담당 · 영업 쪽 · (담당 없을 때) 도면팀 + 관리자. ``all`` 은 겹침을 지운 합.
    """
    ids = get_assignee_ids(SimpleNamespace(structured_data=due.sd), 'DRAWING_DOMAIN')
    drawing = broad_recipient_ids(db, User.id.in_(sorted(set(ids)))) if ids else set()
    sales = notice_target_user_ids(db, drawing_notice_target(db, due.sales_label, partner=due.partner), due.order_id)
    admins: Set[int] = set()
    fallback = not drawing
    if fallback:
        drawing = set(cache.drawing_team())
        admins = set(cache.admins())
    return {'drawing': drawing, 'sales': sales, 'admins': admins, 'fallback': fallback,
            'all': drawing | sales | admins}


def user_names(db: Any, user_ids: Set[int]) -> Dict[int, str]:
    """id → 표시 이름(쿼리 1개). 이름이 없으면 ``#id``."""
    if not user_ids:
        return {}
    rows = db.query(User.id, User.name).filter(User.id.in_(sorted(user_ids))).all()
    names = {int(uid): str(name or '').strip() for uid, name in rows}
    return {uid: names.get(uid) or f"#{uid}" for uid in user_ids}


__all__ = [
    "DueAlert",
    "KIND_EVENING",
    "KIND_LATE",
    "KIND_MORNING",
    "LOOKAHEAD_DAYS",
    "PeopleCache",
    "SLOT_HOURS",
    "TARGET_STAGE_CODES",
    "alert_key",
    "alert_text",
    "due_alerts",
    "recipients_for",
    "slot_of",
    "status_text",
    "still_waiting",
    "to_kst",
    "user_names",
]
