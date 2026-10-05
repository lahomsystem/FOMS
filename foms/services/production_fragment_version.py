"""생산 탭 렌더 전 304 키 — 1단계 그림자 관측 (하트비트 설계서 2026-10-05 §3.4 생산).

키 재료(설계서 §3.2 공통 + §3.4 생산):

- 셸 공통(:func:`~foms.services.common.fragment_prerender.shell_material`): 화면 모드, 허용 인자와
  원래 쿼리 문자열, 쿠키 4종 원값, 사용자(id·역할·팀·활성·이름·username), 세션(user_id·대리 접속),
  코호트 플래그 전량, nav 배지 숫자, 메뉴, env 값 해시, 배포 id·커밋, KST 오늘, 300초 상한 버킷.
- 생산 재료: mine 최종 판정, 칸반 여부, 페이지.
- 조각 캐시 값의 digest — 숫자판(``summary_counts``)과 첨부 수(``attachment_counts``). 값을 키 단계가
  읽고 렌더가 **넘겨받는다**(다시 읽지 않는다). 낡은 조각이 갇히지 않게 하는 장치다(§3.3 조각 갇힘).
- 행 지문(PostgreSQL ``xmin``): 그릴 주문 창(칸반 최대 300행·페이지 50행, 렌더와 같은 필터·정렬),
  그 주문들의 첨부·제작 회차·변경 이벤트, 묘비(칸반일 때 — 취소 주문·확인 이벤트·회차),
  사용자 값 digest(이름·역할 등 — ``last_login`` 쓰기에 흔들리지 않게 ``xmin`` 을 안 쓴다),
  출고 설정 값 digest.

모르면 포기한다: 허용 목록 밖 인자, ``focus_order``(검색 딥링크 — 하트비트는 맨 경로만 부른다),
키 계산 오류 → 키 없음(지금 경로 그대로).

대조 키(§3.7): 본 키에서 재료 한 갈래를 뺀 것 — ``no_order_rows``(주문 창 지문)·
``no_order_events``(변경 이벤트 지문). 운영 관측에서 대조 키 mismatch 가 1건 이상 나와야 계기가
빠뜨림을 잡는다는 증거가 된다.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Final

from sqlalchemy import String, cast, literal, select, union_all

from models import Order, OrderAttachment, OrderEvent, ProductionRun, SystemSetting, User
from foms.services.common.dashboard_cache import (
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    get_or_compute_dashboard_slice,
)
from foms.services.common.ept_b7_profile import phase
from foms.services.common.fragment_prerender import (
    SHELL_ENV,
    PrerenderKey,
    digest,
    digest_rows,
    finish_key,
    row_version,
    shell_material,
    values_version,
)
from foms.services.erp_shipment_settings import ERP_SHIPMENT_SETTINGS_KEY
from foms.services.production_change_alerts import (
    PRODUCTION_CHANGE_EVENT_TYPES,
    production_tombstone_criteria,
)
from foms.services.production_read_model import (
    PRODUCTION_DASHBOARD_PAGE_SIZE,
    PRODUCTION_KANBAN_MAX_ROWS,
    apply_production_dashboard_sort,
    build_production_orders_query,
    compute_production_summary_blob,
    production_attachment_slice_key,
    production_attachment_slice_value,
    production_summary_slice_key,
)

logger = logging.getLogger(__name__)

ROUTE_ID: Final[str] = "erp_production_dashboard"
#: 생산 뷰가 읽는 인자(``production_dashboard_filters``). 셸 공통 ``mine``·``tower_mine`` 은 따로 더한다.
KEY_ARGS: Final[tuple[str, ...]] = ("stage", "q", "search", "focus_order", "page", "sort", "dir")
#: 렌더가 읽는 표 — 기록 계약(``tests/domains/test_production_prerender_key_contract.py``)이 고정한다.
KEY_TABLES: Final[frozenset[str]] = frozenset(
    {"orders", "order_attachments", "production_runs", "order_events", "users", "system_settings"}
)
KEY_SETTING_KEYS: Final[tuple[str, ...]] = (ERP_SHIPMENT_SETTINGS_KEY,)
CONTROL_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "no_order_rows": ("data", "window"),
    "no_order_events": ("data", "events"),
}
_USER_VALUE_COLUMNS = (User.id, User.name, User.username, User.role, User.team, User.is_active)


class _IdRow:
    """조각 계산 함수에 넘길 id 만 가진 행(전체 주문을 읽지 않는다)."""

    __slots__ = ("id",)

    def __init__(self, order_id: int) -> None:
        self.id = order_id


def _window(db: Any, sorted_q: Any, kanban_wanted: bool, total: int, page: int, dialect: str) -> tuple[list, list[int]]:
    """렌더와 같은 필터·정렬로 그릴 주문 창의 (표식, id, 버전) 목록과 id 순서(렌더의 ``_all_rows``)."""
    base = sorted_q.with_entities(Order.id, row_version(Order.__table__, dialect))
    rows: list[tuple[str, int, str]] = []
    kanban_ids: list[int] = []
    if kanban_wanted:
        kanban = base.limit(PRODUCTION_KANBAN_MAX_ROWS).all()
        rows += [("k", int(oid), ver) for oid, ver in kanban]
        kanban_ids = [int(oid) for oid, _ in kanban]
    page_ids: list[int] = []
    if not kanban_wanted or total > PRODUCTION_KANBAN_MAX_ROWS:
        paged = base.offset((page - 1) * PRODUCTION_DASHBOARD_PAGE_SIZE).limit(PRODUCTION_DASHBOARD_PAGE_SIZE).all()
        rows += [("p", int(oid), ver) for oid, ver in paged]
        page_ids = [int(oid) for oid, _ in paged]
    seen = set(kanban_ids)
    return rows, kanban_ids + [oid for oid in page_ids if oid not in seen]


def _dependents(db: Any, ids: list[int], kanban_wanted: bool, dialect: str) -> dict[str, str]:
    """딸린 표 지문을 SQL 한 번(UNION ALL)으로 뜬다 — 표식별 ``"행수:지문"``.

    ORM 전역 필터(첨부 tombstone)를 타지 않게 Core 로 실행한다 — 지운 행까지 포함한 상위집합이
    키로는 안전하다.
    """
    att, run, evt = OrderAttachment.__table__, ProductionRun.__table__, OrderEvent.__table__

    def branch(tag: str, rid: Any, ver: Any) -> Any:
        return select(literal(tag, String).label("tag"), cast(rid, String).label("rid"), ver.label("ver"))

    branches = [
        branch("att", att.c.id, row_version(att, dialect)).where(att.c.order_id.in_(ids)),
        branch("runs", run.c.id, row_version(run, dialect)).where(run.c.order_id.in_(ids)),
        branch("events", evt.c.id, row_version(evt, dialect)).where(
            evt.c.order_id.in_(ids), evt.c.event_type.in_(PRODUCTION_CHANGE_EVENT_TYPES)
        ),
        branch("users", User.id, values_version(_USER_VALUE_COLUMNS)),
        branch("settings", SystemSetting.setting_key, cast(SystemSetting.setting_value, String)).where(
            SystemSetting.setting_key.in_(KEY_SETTING_KEYS)
        ),
    ]
    if kanban_wanted:
        tomb_ids = select(Order.id).where(*production_tombstone_criteria())
        branches += [
            branch("tomb", Order.id, row_version(Order.__table__, dialect)).where(*production_tombstone_criteria()),
            branch("tomb_events", evt.c.id, row_version(evt, dialect)).where(
                evt.c.order_id.in_(tomb_ids), evt.c.event_type == "PRODUCTION_CHANGE_ACK"
            ),
            branch("tomb_runs", run.c.id, row_version(run, dialect)).where(run.c.order_id.in_(tomb_ids)),
        ]
    grouped: dict[str, list[tuple[str, str]]] = {}
    for tag, rid, ver in db.connection().execute(union_all(*branches)).all():
        grouped.setdefault(tag, []).append((str(rid), str(ver)))
    tags = ("att", "runs", "events", "users", "settings") + (("tomb", "tomb_events", "tomb_runs") if kanban_wanted else ())
    return {tag: digest_rows(sorted(grouped.get(tag, []))) for tag in tags}


def compute_production_key(db: Any, req: Any, user: Any, pf: Any, kanban_wanted: bool) -> tuple[PrerenderKey | None, str]:
    """생산 탭 렌더 전 키. 렌더보다 **먼저**(조각·행을 읽기 전에) 부른다(§3.1-3).

    Args:
        db: 요청 DB 세션.
        req: Flask 요청.
        user: 현재 사용자.
        pf: :func:`parse_production_dashboard_filters` 결과.
        kanban_wanted: 칸반을 그리는 요청인지(쿠키·env 만으로 정해진다).

    Returns:
        ``(키, "")`` 또는 포기하면 ``(None, 사유)``. 사유는 상태 단어뿐이다(업무 데이터 없음).
    """
    started = time.perf_counter()
    if pf.focus_order_id:
        return None, "focus_order"
    try:
        with phase("fragver_key"):
            material = shell_material(req, user, KEY_ARGS, SHELL_ENV)
            if material is None:
                return None, "unknown_arg"
            result = _production_material(db, user, pf, kanban_wanted, material)
    except Exception:
        logger.warning("[FragVer2] production key failed — shadow skipped for this request", exc_info=True)
        try:
            db.rollback()
        except Exception:
            logger.warning("[FragVer2] rollback after key failure failed", exc_info=True)
        return None, "error"
    result.key_ms = (time.perf_counter() - started) * 1000
    return result, ""


def _production_material(db: Any, user: Any, pf: Any, kanban_wanted: bool, material: dict[str, Any]) -> PrerenderKey:
    dialect = db.get_bind().dialect.name
    base_q = build_production_orders_query(db, user, pf.stage, pf.q, pf.erp_mine_only)
    summary = get_or_compute_dashboard_slice(
        production_summary_slice_key(user, pf.stage, pf.q, pf.erp_mine_only),
        TTL_SUMMARY_COUNTS,
        lambda: compute_production_summary_blob(base_q),
        page="production",
        slice_name="summary_counts",
    )
    total = int(summary["total_orders"])
    page = max(pf.page or 1, 1)
    window, ids = _window(db, apply_production_dashboard_sort(base_q, pf.sort, pf.sort_dir),
                          kanban_wanted, total, page, dialect)
    att_key = production_attachment_slice_key(user, pf.stage, pf.q, pf.erp_mine_only, ids)
    att_blob = get_or_compute_dashboard_slice(
        att_key,
        TTL_ATTACHMENT_COUNT_MAP,
        lambda: production_attachment_slice_value(db, [_IdRow(oid) for oid in ids]),
        page="production",
        slice_name="attachment_counts",
    )
    material["production"] = {"mine": bool(pf.erp_mine_only), "kanban": bool(kanban_wanted), "page": page}
    material["data"] = {
        "summary": digest(summary),
        "att_slice": digest(att_blob),
        "window": digest_rows(window),
        **_dependents(db, ids, kanban_wanted, dialect),
    }
    key, controls = finish_key(material, CONTROL_KEYS)
    return PrerenderKey(
        key=key,
        controls=controls,
        key_ms=0.0,
        rows=len(ids),
        reuse={"summary": summary, "att_key": att_key, "att": att_blob},
    )
