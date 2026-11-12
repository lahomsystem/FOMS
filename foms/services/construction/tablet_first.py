"""태블릿 가로 시공 탭 첫 화면 읽기 모델 — 날짜 버튼 수 · 고른 날 + 미리 볼 날의 시공자 묶음.

설계서 ``docs/specs/2026-11-09-tablet-production-ui_SPEC.md`` §13.4 (D41 · D42). 읽기만 한다(쓰기 없음).

쿼리는 둘뿐이다.

* **A — 날짜별 집 수**: ``order_schedule_dates``(kind='construction') 를 주문과 이어 날짜마다
  ``COUNT(DISTINCT order_id)``. 줄(JSONB)을 싣지 않고 색인 ``(kind, date, order_id)`` 로 센다.
  모아 세기라 캡이 없다 — 지금 시공 목록의 "최신 접수 50건" 안에서만 고르던 결함 꼴이 없다.
* **B — 고른 날 + 미리 볼 날의 줄**: 같은 조건으로 주문 전부(구조 자료 포함)를 날짜 · 번호 순으로,
  합쳐 ``DAY_ROWS_CAP`` 까지. 숨은 수는 A 의 수에서 뺀 값이라 조용히 잘리지 않는다.

범위(두 쿼리 공통): 지움 · 초안 뺌, ERP 주문, 협력사 칸, AS 상태 뺌, 단계 = 생산 + 시공 단계(D42 ① —
시공일 잡힌 집은 생산 중이어도 넣고 줄에 ``생산중``), mine 이면 ``build_mine_sql_filter``(시공팀 · 켜진
프리랜서 — 지금 시공 목록과 같은 SQL), 시공자를 고르면 ``shipment.construction_workers`` 이름 조건.
60일 창(``dashboard_active_filter``)은 쓰지 않는다(앞날 집이 창 밖으로 밀리지 않게).

묶음 · 색은 출고 탭과 같은 ``build_tablet_day_sheet`` 를 날마다 따로 부른다. 줄 객체는 ORM 주문을
감싼 ``_DayRow`` 라 그날 품목(``shipment_visible_items``)을 ORM 객체에 붙이지 않는다.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Iterable

from sqlalchemy import and_, distinct, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import aliased

from foms.services.common.address_query import strip_sido
from foms.services.common.business_calendar import get_holidays_kr
from foms.services.common.partner_order_filter import partner_order_clause
from foms.services.construction_read_model import CONSTRUCTION_ACTIVE_STAGE_CODES, CONSTRUCTION_ALL_STAGE_CODES
from foms.services.datetime_kst import get_today_kst
from foms.services.erp_permissions import (
    _current_dialect_name,
    _json_string_token_condition,
    build_mine_sql_filter,
    mine_membership_clause,
)
from foms.services.erp_shipment_settings import load_erp_shipment_settings, normalize_erp_shipment_workers
from foms.services.erp_template_filters import strip_product_w_filter
from foms.services.orders.board_state_display import construction_display_stage
from foms.services.production_home_read_model import production_home_steps
from foms.services.shipment.tablet_day_sheet import build_tablet_day_sheet
from foms.services.shipment_dashboard_helpers import (
    AS_SHIPMENT_STATUSES,
    _normalize_worker_name,
    visible_items_for_dates,
    visible_spec_units,
)
from models import Order, OrderScheduleDate

STRIP_DAYS = 14
DAY_ROWS_CAP = 200
PRODUCTION_STAGE_CODES: tuple[str, ...] = ("PRODUCTION", "생산")
#: 첫 화면에 드는 단계(D42 ①): 생산 + 시공 대시보드 단계 전부.
FIRST_SCREEN_STAGE_CODES: tuple[str, ...] = PRODUCTION_STAGE_CODES + tuple(CONSTRUCTION_ALL_STAGE_CODES)
_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK_RE = re.compile(r"(\d{1,2})\s*[:시]\s*(\d{0,2})")
#: 쿼리 A 와 한 문장(UNION ALL)으로 센 날짜 미정 집 수의 열쇠(날짜 자리에 들어가는 표식 — 날짜가 아니다, D43 a51).
UNDATED_KEY = "undated"
#: 첫 화면에 드는 일정 종류(D43 a52): 시공일(construction) + AS 방문일(as_visit).
_KINDS = ("construction", "as_visit")


def _is_as(entity: Any = Order) -> Any:
    """AS 상태 주문(출고 판과 같은 목록 ``AS_SHIPMENT_STATUSES``)."""
    return entity.status.in_(AS_SHIPMENT_STATUSES)


def _not_as(entity: Any = Order) -> Any:
    return or_(entity.status.is_(None), ~entity.status.in_(AS_SHIPMENT_STATUSES))


def _kind_pair(entity: Any = Order) -> Any:
    """일정 줄 종류 ↔ 주문 상태 짝(출고 판 패널과 같은 꼴): AS 아님이면 시공일, AS 면 AS 방문일만.

    AS 상태인데 시공일만 있는 집(as_visit 없음)은 지금처럼 들지 않는다 — AS 를 넣는 기준은 as_visit 날짜뿐(D43).
    """
    return or_(
        and_(OrderScheduleDate.kind == "construction", _not_as(entity)),
        and_(OrderScheduleDate.kind == "as_visit", _is_as(entity)),
    )


class _DayRow:
    """그날 하나의 줄 — ORM 주문을 감싸 그날 품목만 따로 든다(ORM 객체에 속성을 붙이지 않는다)."""

    __slots__ = ("_order", "day", "shipment_visible_items")

    def __init__(self, order: Any, day: str) -> None:
        self._order = order
        self.day = day
        self.shipment_visible_items = visible_items_for_dates(order, target_date=day)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._order, name)


def parse_day(value: Any) -> str | None:
    """``YYYY-MM-DD`` 이고 실제 날짜면 그대로, 아니면 None."""
    text = str(value or "").strip()
    if not _DATE_RE.match(text):
        return None
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return None
    return text


def strip_dates(today: datetime.date) -> list[str]:
    """오늘부터 ``STRIP_DAYS`` 일."""
    return [(today + datetime.timedelta(days=i)).isoformat() for i in range(STRIP_DAYS)]


def scope_conditions(*, user: Any, mine_only: bool, partner_org: str, worker: str) -> list[Any]:
    """쿼리 A · B 가 함께 쓰는 주문 조건 목록(전부 AND).

    Args:
        user: 로그인 사용자(mine 판정용 — 이 함수 안에서만 속성을 읽는다).
        mine_only: 시공팀 · 켜진 프리랜서 · ``?mine=1`` 이면 True(라우트가 정한다).
        partner_org: ``partner_filter_value`` 결과('' = 전부).
        worker: 고른 시공자 이름('' = 전체).
    """
    conds: list[Any] = [
        Order.active_filter(),
        Order.is_erp_order.is_(True),
        partner_order_clause(partner_org),
        # 시공 줄 = AS 아님 + 생산 · 시공 단계(D42 ①), AS 방문 줄 = AS 상태(단계 무관 — 날짜는 as_visit 짝으로만, D43 a52).
        or_(and_(_not_as(), Order.erp_stage_code.in_(FIRST_SCREEN_STAGE_CODES)), _is_as()),
    ]
    if mine_only:
        mine = build_mine_sql_filter(user) if user is not None else []
        clause = mine_membership_clause(mine, scope_conds=list(conds)) if mine else None
        conds.append(clause if clause is not None else Order.id == -1)
    name = str(worker or "").strip()
    if name:
        conds.append(_json_string_token_condition(
            Order.structured_data["shipment"]["construction_workers"], name,
            dialect_name=_current_dialect_name(),
        ))
    return conds


def undated_conditions(conds: list[Any]) -> list[Any]:
    """날짜 미정 집(D43 a51) = 첫 화면 조건 + AS 아님 + 시공대기 · 시공중 단계 + 시공 일정 줄 없음.

    생산 단계 · 완료 단계 · AS 상태 집은 들지 않는다. mine · 협력사 · 사람 칸은 ``conds`` 그대로.
    """
    no_date = ~exists().where(OrderScheduleDate.order_id == Order.id, OrderScheduleDate.kind == "construction")
    return list(conds) + [_not_as(), Order.erp_stage_code.in_(CONSTRUCTION_ACTIVE_STAGE_CODES), no_date]


def count_houses_by_date(db: Any, conds: list[Any], dates: Iterable[str], *, with_undated: bool = False) -> dict[str, int]:
    """쿼리 A — 날짜마다 집 수(주문 단위 — 같은 날 일정 줄이 여럿이거나 시공 · AS 방문 둘 다여도 1).

    ``with_undated`` 면 날짜 미정 집 수를 같은 문장에 UNION ALL 로 붙여 ``UNDATED_KEY`` 열쇠로 돌려준다(쿼리 수 그대로).
    """
    days = sorted(set(dates))
    if not days:
        return {}
    stmt = (
        select(OrderScheduleDate.date.label("d"), func.count(distinct(OrderScheduleDate.order_id)).label("n"))
        .join(Order, Order.id == OrderScheduleDate.order_id)
        .where(OrderScheduleDate.kind.in_(_KINDS), OrderScheduleDate.date.in_(days), _kind_pair(), *conds)
        .group_by(OrderScheduleDate.date)
    )
    if with_undated:
        undated = select(literal(UNDATED_KEY).label("d"), func.count(Order.id).label("n")).where(*undated_conditions(conds))
        stmt = union_all(stmt, undated)
    return {str(d): int(n) for d, n in db.execute(stmt).all()}


def fetch_undated_orders(db: Any, conds: list[Any], cap: int | None = None) -> list[Any]:
    """날짜 미정 집 줄(주문 번호 순) — ``cap`` + 1 개까지 받아 넘침을 안다(남은 수는 세지 않는다)."""
    cap = DAY_ROWS_CAP if cap is None else cap
    return db.query(Order).filter(*undated_conditions(conds)).order_by(Order.id.asc()).limit(cap + 1).all()


def fetch_day_orders(db: Any, conds: list[Any], dates: Iterable[str], cap: int | None = None) -> list[tuple[str, Any]]:
    """쿼리 B — 날짜들의 (날짜, 주문) 줄, 날짜 · 주문 번호 순으로 합쳐 ``cap``(기본 ``DAY_ROWS_CAP``) 까지."""
    cap = DAY_ROWS_CAP if cap is None else cap
    days = sorted(set(dates))
    if not days:
        return []
    o2 = aliased(Order)
    pairs = (
        select(OrderScheduleDate.order_id.label("oid"), OrderScheduleDate.date.label("day"))
        .join(o2, o2.id == OrderScheduleDate.order_id)
        .where(OrderScheduleDate.kind.in_(_KINDS), OrderScheduleDate.date.in_(days), _kind_pair(o2))
        .distinct()
        .subquery()
    )
    rows = (
        db.query(Order, pairs.c.day)
        .join(pairs, pairs.c.oid == Order.id)
        .filter(*conds)
        .order_by(pairs.c.day.asc(), Order.id.asc())
        .limit(cap)
        .all()
    )
    return [(str(day), order) for order, day in rows]


def _sd(order: Any) -> dict:
    sd = getattr(order, "structured_data", None)
    return sd if isinstance(sd, dict) else {}


def _time_fields(sd: dict) -> tuple[str, bool, tuple[int, int]]:
    """(보일 글, 계획값(흐림) 여부, 정렬 열쇠). 출고 시공시간 → 주문 오전 · 오후 · 종일 → 미정."""
    real = str(((sd.get("shipment") or {}).get("construction_time")) or "").strip()
    plan = str((((sd.get("schedule") or {}).get("construction") or {}).get("time")) or "").strip()
    text = real or plan
    m = _CLOCK_RE.search(text)
    if m:
        hour = int(m.group(1)) + (12 if "오후" in text and int(m.group(1)) < 12 else 0)
        key = (0, hour * 60 + int(m.group(2) or 0))
    else:
        key = next(((rank, 0) for rank, word in ((1, "오전"), (2, "오후"), (3, "종일")) if word in text),
                   (4, 0) if text else (5, 0))
    return (text or "시간 미정"), bool(plan and not real), key


def _district_split(address: str) -> tuple[str, str]:
    """(구 이름, 나머지 주소). 시 · 도를 뗀 뒤 ``…시 …구`` 면 구, 아니면 첫 낱말이 구 · 시 · 군일 때 그것."""
    tokens = strip_sido(address or "").split()
    if not tokens:
        return "", ""
    if len(tokens) >= 2 and tokens[0].endswith("시") and tokens[1].endswith("구"):
        return tokens[1], " ".join([tokens[0]] + tokens[2:])
    if tokens[0].endswith(("구", "시", "군")):
        return tokens[0], " ".join(tokens[1:])
    return "", " ".join(tokens)


def _packing_fields(sd: dict) -> tuple[str, str]:
    """(글, 상태) — 상태 = departed · packing · none."""
    packing = (sd.get("shipment") or {}).get("packing")
    if not isinstance(packing, dict):
        return "포장 전", "none"
    departed = str(packing.get("departed_at") or "")
    if departed:
        return (f"출발 {departed[11:16]}" if len(departed) >= 16 else "출발"), "departed"
    items = [it for it in (packing.get("items") or []) if isinstance(it, dict)]
    if not items:
        return "포장 전", "none"
    done = sum(1 for it in items if it.get("checked"))
    return f"포장 {done}/{len(items)}", "packing"


def _drawing_fields(sd: dict) -> tuple[str, bool]:
    """(글, 없음 여부) — 도면 전달본 판 수."""
    hist = sd.get("drawing_transfer_history") or []
    count = len(hist) if isinstance(hist, list) else 0
    if not count and sd.get("last_drawing_transfer"):
        count = 1
    return (f"전달본 v{count}", False) if count else ("전달본 없음", True)


def _product_text(row: _DayRow) -> str:
    items = [it for it in (row.shipment_visible_items or []) if isinstance(it, dict)]
    first = strip_product_w_filter((items[0].get("product_name") or "")) if items else ""
    if first:
        return first + (f" 외 {len(items) - 1}" if len(items) > 1 else "")
    return strip_product_w_filter(getattr(row, "product", None) or "") or "-"


def production_progress(sd: dict) -> dict | None:
    """생산 공정 진행(D43 a53) — 기록(``production.steps`` 의 4칸 열쇠)이 하나도 없으면 None(0/4 라고 말하지 않는다).

    Returns:
        {'done': 끝난 칸 수, 'total': 4, 'last': 순서상 가장 뒤의 끝난 칸 이름('' = 없음)} 또는 None.
    """
    prod = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    raw = prod.get("steps") if isinstance(prod.get("steps"), list) else []
    steps = production_home_steps(sd, mark_now=False)
    keys = {s["key"] for s in steps}
    if not any(isinstance(it, dict) and it.get("key") in keys for it in raw):
        return None
    done = [s for s in steps if s["done"]]
    return {"done": len(done), "total": len(steps), "last": done[-1]["label"] if done else ""}


def production_note(sd: dict) -> str:
    """상세 가운데 안내 — ``아직 생산 중이에요 · 조립까지 끝남``(끝난 칸이 없거나 기록이 없으면 앞말만)."""
    prog = production_progress(sd)
    return f"아직 생산 중이에요 · {prog['last']}까지 끝남" if prog and prog["last"] else "아직 생산 중이에요"


def is_as_status(order: Any) -> bool:
    return getattr(order, "status", None) in AS_SHIPMENT_STATUSES


def _stage_label(order: Any, sd: dict) -> str:
    if is_as_status(order):
        return "AS 방문"
    if str(getattr(order, "erp_stage_code", "") or "").strip().upper() in PRODUCTION_STAGE_CODES:
        return "생산중"
    return construction_display_stage(order, sd) or ""


def _ship_cell(stage: str, sd: dict) -> tuple[str, str]:
    """출고 칸(글, 상태) — AS 방문 집은 '-'(포장 자료 없음), 생산 단계는 '생산 n/4'(기록 없으면 '생산중'), 그 밖은 포장."""
    if stage == "AS 방문":
        return "-", "none"
    if stage == "생산중":
        prog = production_progress(sd)
        return (f"생산 {prog['done']}/{prog['total']}" if prog else "생산중"), "production"
    return _packing_fields(sd)


def build_row_view(row: _DayRow) -> dict:
    """줄 칸 값(설계서 §13.3 줄 칸 표). 그날 품목 · 자수는 ``row.day`` 기준."""
    sd = _sd(row)
    parties = sd.get("parties") or {}
    site = sd.get("site") or {}
    address = str(site.get("address_full") or site.get("address_main") or getattr(row, "address", "") or "")
    time_text, time_plan, _ = _time_fields(sd)
    district, address_rest = _district_split(address)
    drawing_text, drawing_missing = _drawing_fields(sd)
    stage = _stage_label(row, sd)
    packing_text, packing_state = _ship_cell(stage, sd)
    return {
        "id": row.id,
        "day": row.day,
        "time_text": time_text,
        "time_plan": time_plan,
        "stage": stage,
        "in_production": stage == "생산중",
        "now_working": stage == "시공중",
        "done": stage == "시공완료",
        "as_visit": stage == "AS 방문",
        "customer": str(((parties.get("customer") or {}).get("name")) or getattr(row, "customer_name", "") or "-"),
        "agency": str(((parties.get("orderer") or {}).get("name")) or "").strip(),
        "product": _product_text(row),
        "units": 0.0 if stage == "AS 방문" else round(float(visible_spec_units(row) or 0.0), 1),
        "district": district,
        "address_rest": address_rest,
        "address": address,
        "packing_text": packing_text,
        "packing_state": packing_state,
        "drawing_text": drawing_text,
        "drawing_missing": drawing_missing,
    }


def time_sort_key(order: Any) -> tuple[int, int]:
    """시간 순 정렬 열쇠(시각 글 → 오전 → 오후 → 종일 → 미정) — 첫 화면 묶음 · 상세 왼쪽 목록 공용."""
    return _time_fields(_sd(order))[2]


def build_day_section(day: str, orders: list[Any], worker_settings: list, *, count: int, preview: bool) -> dict:
    """하루 묶음 — 시간 순으로 줄 세운 뒤 출고와 같은 ``build_tablet_day_sheet`` 로 묶고 색을 매긴다."""
    rows = sorted((_DayRow(o, day) for o in orders), key=lambda r: (_time_fields(_sd(r))[2], r.id))
    sheet = build_tablet_day_sheet(rows, worker_settings, day)
    groups = []
    for g in sheet["groups"]:
        names: list[str] = []
        for r in g["rows"]:
            for w in r["workers"]:
                if w["name"] not in names:
                    names.append(w["name"])
        groups.append({
            "key": g["key"], "unassigned": g["unassigned"], "color_index": g["color_index"],
            "names": names,
            "rows": [{**build_row_view(r["order"]), "workers": r["workers"]} for r in g["rows"]],
        })
    shown = sum(len(g["rows"]) for g in groups)
    return {"date": day, "count": count, "preview": preview, "groups": groups,
            "hidden": max(0, count - shown), "people": sheet["people"]}


def _day_meta(day: str, *, today: str, selected: str, holidays: set[str], count: int | None) -> dict:
    d = datetime.date.fromisoformat(day)
    return {"date": day, "count": count, "weekday": d.weekday(), "weekday_label": _WEEKDAYS[d.weekday()],
            "is_weekend": d.weekday() >= 5, "is_holiday": day in holidays,
            "is_today": day == today, "is_selected": day == selected}


def resolve_default_worker(worker: str | None, *, login_names: Iterable[str], option_names: Iterable[str]) -> str:
    """``worker`` 키가 없을 때(None) 로그인 이름이 칸 목록에 있으면 그 이름(D40), 있으면(빈 값 포함) 그대로."""
    if worker is not None:
        return str(worker).strip()
    options = {_normalize_worker_name(n): str(n).strip() for n in option_names if _normalize_worker_name(n)}
    for name in login_names:
        hit = options.get(_normalize_worker_name(name))
        if hit:
            return hit
    return ""


def _worker_options(worker_settings: list, sections: list[dict], *, include_settings: bool) -> list[str]:
    """칸 이름 목록 = 설정 시공자(설정 순) + 그날 · 미리 보기 줄에만 있는 이름. 프리랜서는 설정을 빼고 줄 이름만."""
    out: list[str] = []
    seen: set[str] = set()
    pool = [w.get("name") for w in (worker_settings or [])] if include_settings else []
    for sec in sections:
        pool += [w["name"] for g in sec["groups"] for r in g["rows"] for w in r["workers"]]
    for name in pool:
        norm = _normalize_worker_name(name)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(str(name).strip())
    return out


def build_tablet_first(db: Any, *, user: Any, mine_only: bool, partner_org: str = "",
                       selected: str | None = None, worker: str | None = None,
                       worker_settings: list | None = None, is_freelancer: bool = False,
                       today: datetime.date | None = None) -> dict:
    """첫 화면 자료 한 묶음(쿼리 A 1번 + 필요할 때 B 1번).

    Args:
        db: 세션. user: 로그인 사용자(이름은 여기서 한 번만 읽는다). mine_only: 라우트 판정.
        partner_org: 협력사 칸. selected: ``?date=``(틀리면 오늘). worker: ``?worker=``(None = 키 없음).
        worker_settings: 출고 설정 시공자(``normalize_erp_shipment_workers`` 결과). None 이면 읽는다(요청당 캐시).
        is_freelancer: 켜진 프리랜서면 회사 시공자 명단을 칸 목록 · 처음 칸에 쓰지 않는다.
        today: 시험용(기본 ``get_today_kst()``).
    """
    if worker_settings is None:
        worker_settings = normalize_erp_shipment_workers(load_erp_shipment_settings().get("construction_workers", []))
    login_names = [str(getattr(user, a, "") or "") for a in ("name", "username")] if user is not None else []
    base = today or get_today_kst()
    today_iso = base.isoformat()
    days = strip_dates(base)
    sel = parse_day(selected) or today_iso
    settings_names = [] if is_freelancer else [w.get("name") for w in worker_settings]
    chosen = resolve_default_worker(worker, login_names=login_names, option_names=settings_names)

    conds = scope_conditions(user=user, mine_only=mine_only, partner_org=partner_org, worker=chosen)
    counts = count_houses_by_date(db, conds, days + [sel], with_undated=True)
    preview = next((d for d in days if d > sel and counts.get(d, 0) > 0), None)
    want = [d for d in (sel, preview) if d and counts.get(d, 0) > 0]
    by_day: dict[str, list[Any]] = {d: [] for d in want}
    for day, order in fetch_day_orders(db, conds, want):
        by_day.setdefault(day, []).append(order)
    sections = [build_day_section(d, by_day.get(d, []), worker_settings, count=counts.get(d, 0),
                                  preview=(d != sel)) for d in want]

    holidays: set[str] = set()
    for year in {base.year, (base + datetime.timedelta(days=STRIP_DAYS)).year, int(sel[:4])}:
        holidays |= get_holidays_kr(year)
    strip = [_day_meta(d, today=today_iso, selected=sel, holidays=holidays, count=counts.get(d, 0)) for d in days]
    return {
        "today": today_iso, "selected": sel, "selected_in_strip": sel in days,
        "selected_meta": _day_meta(sel, today=today_iso, selected=sel, holidays=holidays, count=counts.get(sel, 0)),
        "days": strip, "selected_count": counts.get(sel, 0),
        "next_date": preview, "next_count": counts.get(preview, 0) if preview else 0,
        "worker": chosen,
        "worker_options": _worker_options(worker_settings, sections, include_settings=not is_freelancer),
        "worker_colors": {p["name"]: p["color_index"] for sec in reversed(sections) for p in sec["people"]},  # 고른 날 색 우선
        "sections": sections, "cap": DAY_ROWS_CAP, "undated_count": counts.get(UNDATED_KEY, 0),
    }
