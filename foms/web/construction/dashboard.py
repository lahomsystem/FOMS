"""
ERP 시공 대시보드 페이지 (ERP-SLIM-10)
erp.py에서 분리: /erp/construction/dashboard
"""

import time
from typing import Any

from flask import Blueprint, g, make_response, render_template, request
from sqlalchemy import or_

from foms.web.auth import login_required
from db import get_db
from foms.services.erp_order_detail import attach_order_detail_payloads
from foms.services.common.dashboard_cache import (
    KEY_VERSION,
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    build_dashboard_cache_key,
    format_slice_observations,
    get_or_compute_dashboard_slice,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers, phase
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.erp_permissions import (
    build_mine_sql_filter,
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.erp_policy import STAGE_LABELS
# namespace surface 계약(pin): 라우트 본문 미사용이어도 erp_display 재export 유지
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
    self_measurement_four_checks_done,
)
from foms.services.construction_dashboard_filters import parse_construction_dashboard_filters
from foms.services.construction_dashboard_display import (
    enrich_construction_mobile_rows,
    build_construction_row_dtos,
)
from foms.services.construction_read_model import (
    CONSTRUCTION_BROWSE_CAP,
    CONSTRUCTION_DASHBOARD_PAGE_SIZE,
    CONSTRUCTION_SEARCH_CAP,
    apply_construction_search_filter,
    apply_construction_list_scope_filter,
    build_construction_process_steps,
    compute_construction_summary_blob,
    fetch_construction_attachment_counts,
    paginate_construction_orders,
)
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached
from foms.services.datetime_kst import get_today_kst
from models import Order

erp_construction_page_bp = Blueprint("erp_construction_page", __name__, url_prefix="/erp")

TEAM_LABELS = {
    "CS": "라홈팀",
    "SALES": "영업팀",
    "MEASURE": "실측팀",
    "DRAWING": "도면팀",
    "PRODUCTION": "생산팀",
    "CONSTRUCTION": "시공팀",
}


@erp_construction_page_bp.route("/construction/dashboard")
@login_required
def erp_construction_dashboard():
    """시공 대시보드"""
    db = get_db()
    user = getattr(g, "current_user", None)
    is_admin = user and user.role == "ADMIN"

    _cf = parse_construction_dashboard_filters(request, user)
    f_stage = _cf.stage
    f_q = _cf.q
    focus_order_id = _cf.focus_order_id
    mine_only = _cf.mine_only

    query = db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_order.is_(True))

    if mine_only and user:
        mine_conds = build_mine_sql_filter(user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))
        else:
            query = query.filter(Order.id == -1)

    # 요약(KPI/step_stats)은 위 ``query`` 만 읽는다. 그 query 는 mine_only 일 때만 사용자
    # 조건을 얹으므로, 공용(mine=False) 결과는 누가 열어도 값이 같다. 그런데도 키에 uid/role 을
    # 넣으면 같은 숫자를 사용자 수만큼 따로 계산·저장하게 되어(캐시 미스 = 60일 주문 전량 순회
    # ≈ 88ms 실측) 만료 직후 사용자마다 그 비용을 다시 떠안았다. 공용 결과는 키를 공유한다.
    _summary_fp: dict[str, Any] = {
        # 스캔 스코프가 바뀌면 숫자의 의미도 바뀐다 — 구 스코프로 계산된 캐시 값을
        # 그대로 이어 쓰지 않도록 키에 스코프 표식을 남긴다(배포 즉시 자연 무효화).
        "v": KEY_VERSION,
        "scope": "construction_stage",
        "mine": bool(mine_only),
    }
    if mine_only:
        _summary_fp["uid"] = user.id if user else None
        _summary_fp["role"] = getattr(user, "role", None) if user else None
    _summary_key = build_dashboard_cache_key("construction", "summary_counts", _summary_fp)
    # 숫자판(긴급 발주·시공 D-3·단계별 건수)은 시공 대시보드의 것이므로 시공 표시단계
    # 주문만 센다. 목록과 같은 스코프(apply_construction_list_scope_filter)를 써서
    # "위 숫자와 아래 목록이 다른 모집단" 이던 어긋남도 함께 사라진다.
    _summary_query = apply_construction_list_scope_filter(query, "")
    with phase("summary_slice"):
        _summary_blob = get_or_compute_dashboard_slice(
            _summary_key,
            TTL_SUMMARY_COUNTS,
            lambda: compute_construction_summary_blob(_summary_query),
            page="construction",
            slice_name="summary_counts",
        )
    step_stats = _summary_blob["step_stats"]
    kpis = _summary_blob["kpis"]

    page = request.args.get("page", 1, type=int)
    per_page = CONSTRUCTION_DASHBOARD_PAGE_SIZE
    total_pages = 0
    total_orders = 0
    orders: list[Order] = []

    if focus_order_id:
        focus = (
            db.query(Order)
            .filter(
                Order.id == focus_order_id,
                Order.active_filter(),
                Order.is_erp_order.is_(True),
            )
            .first()
        )
        orders = (
            [focus]
            if focus
            and (not mine_only or is_order_related_to_user(focus, user))
            else []
        )
        total_orders = len(orders)
        total_pages = 1
        page = 1
    elif f_q:
        # 검색도 시공 단계로 선스코프(전 단계) 후 검색 — 페이지네이션이 시공 주문 위에서 동작.
        list_query = apply_construction_list_scope_filter(query, f_stage)
        list_query = apply_construction_search_filter(list_query, f_q)
        with phase("list_query"):
            page, total_pages, total_orders, orders = paginate_construction_orders(
                list_query,
                page=page,
                per_page=per_page,
                total_cap=CONSTRUCTION_SEARCH_CAP,
            )
    else:
        # 브라우즈 기본 뷰: 단계 미선택 시 전 시공 단계(대기+중+완료)로 SQL 선스코프 →
        # 페이지네이션이 시공 주문 위에서 동작(전체 60일 활성 리스트 newest-N에 시공 주문이
        # 없어 board가 0건 되던 회귀의 근본 차단). 단계 칩 선택 시 해당 단계로 좁혀진다.
        list_query = apply_construction_list_scope_filter(query, f_stage)
        with phase("list_query"):
            page, total_pages, total_orders, orders = paginate_construction_orders(
                list_query,
                page=page,
                per_page=per_page,
                total_cap=CONSTRUCTION_BROWSE_CAP,
            )

    # 첨부 개수는 주문 id 집합에만 의존한다(fetch_construction_attachment_counts 는 ids 로만
    # 집계). uid/mine/stage/q/page 는 그 ids 를 **고르는** 축일 뿐이라 키에 함께 넣으면
    # 같은 주문 묶음을 화면·사용자별로 다시 집계한다. 결과를 결정하는 축(ids)만 키로 쓴다.
    _att_fp = {
        "v": KEY_VERSION,
        "ids": sorted(o.id for o in orders),
    }
    _att_key = build_dashboard_cache_key("construction", "attachment_counts", _att_fp)

    def _compute_att_counts() -> dict[str, int]:
        raw = fetch_construction_attachment_counts(db, orders)
        return {str(k): int(v) for k, v in raw.items()}

    with phase("attachment_slice"):
        _att_blob = get_or_compute_dashboard_slice(
            _att_key,
            TTL_ATTACHMENT_COUNT_MAP,
            _compute_att_counts,
            page="construction",
            slice_name="attachment_counts",
        )
    att_counts = {int(k): int(v) for k, v in (_att_blob or {}).items()}

    with phase("row_dtos"):
        enriched = build_construction_row_dtos(orders, att_counts, f_stage)

    if f_q or focus_order_id:
        step_stats = {
            "시공대기": {"count": 0, "overdue": 0, "imminent": 0},
            "시공중": {"count": 0, "overdue": 0, "imminent": 0},
            "시공완료": {"count": 0, "overdue": 0, "imminent": 0},
        }
        for item in enriched:
            stage_name = item.get("stage")
            if stage_name in step_stats:
                step_stats[stage_name]["count"] += 1
                alerts = item.get("alerts") or {}
                if alerts.get("construction_d3"):
                    step_stats[stage_name]["imminent"] += 1

    process_steps = build_construction_process_steps(step_stats)

    current_user = getattr(g, "current_user", None)
    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )
    with phase("mobile_enrich"):
        enrich_construction_mobile_rows(
            enriched,
            db,
            mobile_v2_active=mobile_v2_active,
            drawing_only=True,
        )
    with phase("detail_payloads"):
        attach_order_detail_payloads(db, enriched)

    template_name = (
        "construction/partials/dashboard_fragment.html"
        if wants_erp_shell_tab_body(request)
        else "construction/dashboard.html"
    )
    _t0 = time.perf_counter()
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            kpis=kpis,
            process_steps=process_steps,
            filters={"stage": f_stage, "q": f_q},
            team_labels=TEAM_LABELS,
            stage_labels=STAGE_LABELS,
            is_admin=is_admin,
            can_edit_erp=can_edit_erp(user),
            erp_mine_only=mine_only,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_orders=total_orders,
            today_iso=get_today_kst().isoformat(),
        )
    )
    apply_ept_b7_render_headers(
        response,
        route_id="erp_construction_dashboard",
        render_ms=(time.perf_counter() - _t0) * 1000,
    )
    # 슬라이스 진단: 이번 요청이 어떤 read-model 조각을 hit/miss 했고 재계산에 몇 ms 를
    # 썼는지. render_ms 는 템플릿 시간만 담아 "캐시 만료 순간의 재계산 비용"이 안 보였다.
    _slice_obs = format_slice_observations()
    if _slice_obs:
        response.headers["X-FOMS-DASH-SLICES"] = _slice_obs
    apply_erp_shell_fragment_headers(response, request)
    return response
