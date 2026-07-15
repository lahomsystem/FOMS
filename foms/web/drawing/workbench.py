"""ERP 도면 작업실 (ERP-SLIM-5; canonical, SFC-B11B). /erp/drawing-workbench."""
from typing import Any, Mapping

from flask import Blueprint, make_response, render_template, request, url_for, redirect, flash, g
from sqlalchemy import or_

from db import get_db
from models import Order, User, OrderAttachment
from foms.web.auth import login_required
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.datetime_kst import format_datetime_kst, parse_datetime_utc
from foms.services.erp_permissions import (
    build_mine_sql_filter,
    can_edit_erp,
    is_order_related_to_user,
    resolve_mine_scope_for_user,
)
from foms.services.erp_quest_display import load_assignee_user_map_batch, resolve_order_role_assignees
from foms.services.erp_policy import (
    STAGE_NAME_TO_CODE,
    get_assignee_ids,
    has_pending_unchecked_drawing_revision_requests,
    is_drawing_workbench_participant,
)
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_alerts,
    _can_modify_sales_domain,
    _drawing_status_label,
    _drawing_next_action_text,
    _normalize_date_to_yyyymmdd,
)
from foms.services.erp_product_items import build_product_items_for_order
from foms.services.notifications.drawing_order_change import is_order_change_pending
from foms.services.common.dashboard_cache import (
    KEY_VERSION,
    TTL_PANEL_ROWS,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.drawing_workbench_read_model import (
    fetch_drawing_seed_order_ids,
    hydrate_drawing_orders_by_ids,
)
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.request_utils import get_search_query_arg
from foms.services.drawing_workbench_display import (
    drawing_thumb_enabled,
    resolve_row_thumbnail_url,
)
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached

erp_drawing_workbench_bp = Blueprint('erp_drawing_workbench', __name__, url_prefix='/erp')

_DRAWING_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.heic', '.heif')


def _is_drawing_image(filename: str) -> bool:
    """Return True when a drawing filename can be previewed as an image."""
    return (filename or '').lower().endswith(_DRAWING_IMAGE_EXTENSIONS)


def _drawing_file_key(file_obj: Any, index: int) -> str:
    """Resolve a stable drawing file key for URL/query selection."""
    if isinstance(file_obj, Mapping):
        return str(file_obj.get('key') or f'drawing-{index + 1}')
    return f'drawing-{index + 1}'


def _resolve_construction_date_display(order: Any, sd: dict[str, Any]) -> str:
    """Return normalized construction date text for workbench list rows."""
    raw = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
    if raw:
        if isinstance(raw, str):
            parts = [part.strip() for part in raw.split(',') if part.strip()]
            normalized = [_normalize_date_to_yyyymmdd(part) for part in parts]
            dates = [value for value in normalized if value]
            if dates:
                return ', '.join(dates)
        else:
            single = _normalize_date_to_yyyymmdd(raw)
            if single:
                return single
    fallback = _normalize_date_to_yyyymmdd(getattr(order, 'erp_construction_date', None))
    return fallback or ''


def _event_target_numbers(event: Mapping[str, Any]) -> list[int]:
    """Normalize drawing target numbers from transfer/revision history events."""
    raw = event.get('target_drawing_numbers') or event.get('replace_target_numbers') or []
    if not isinstance(raw, list):
        raw = [raw]
    if not raw:
        raw = [event.get('target_drawing_number') or event.get('replace_target_number')]
    numbers = []
    for value in raw:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return numbers


def _history_event_at_raw(event: Mapping[str, Any]) -> str:
    """Return the raw instant-ish timestamp from drawing history."""
    return str(event.get('transferred_at') or event.get('at') or event.get('updated_at') or '').strip()


def _history_event_at_text(event: Mapping[str, Any]) -> str:
    raw = _history_event_at_raw(event)
    return format_datetime_kst(raw) or raw or '-'


def _history_event_sort_key(event: Mapping[str, Any], index: int) -> tuple[float, int]:
    parsed = parse_datetime_utc(_history_event_at_raw(event))
    if parsed is None:
        return (0.0, index)
    return (parsed.timestamp(), index)


def _history_event_after(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_dt = parse_datetime_utc(_history_event_at_raw(left))
    right_dt = parse_datetime_utc(_history_event_at_raw(right))
    if left_dt is not None and right_dt is not None:
        return left_dt > right_dt
    return _history_event_at_raw(left) > _history_event_at_raw(right)


def _build_drawing_turn(
    drawing_status: str,
    has_assignee: bool,
    can_transfer: bool,
    can_confirm_receipt: bool,
    file_count: int,
    transfer_round: int,
) -> dict[str, str]:
    """Build order-level turn ribbon copy for the mobile handoff UI."""
    status = (drawing_status or 'PENDING').upper()
    if status == 'TRANSFERRED':
        label = '영업 확인 차례'
    elif status == 'RETURNED':
        label = '도면팀 수정 차례'
    elif status == 'CONFIRMED':
        label = '완료'
    else:
        label = '도면팀 작업 차례' if has_assignee else '도면 담당 지정 필요'
    is_mine = (status == 'TRANSFERRED' and can_confirm_receipt) or (status in ('PENDING', 'IN_PROGRESS', 'RETURNED') and can_transfer)
    tone = 'done' if status == 'CONFIRMED' else ('mine' if is_mine else 'other')
    round_text = f'도면팀 {transfer_round}차 전달' if transfer_round else '도면 전달 대기'
    return {
        'label': label,
        'sub': f'{round_text} · 도면 {file_count}장 · 주문 단위 상태 1개',
        'tone': tone,
    }


def _build_handoff_files(order_id: int, drawing_files: list[Any], history: list[Mapping[str, Any]], selected_key: str) -> list[dict[str, Any]]:
    """Build drawing file rows for the mobile handoff list/detail surfaces."""
    latest_transfer_round = 0
    latest_transfer_note = ''
    revision_targets: set[int] = set()
    revision_applied: set[int] = set()
    target_notes: dict[int, str] = {}
    for event in history:
        action = (event.get('action') or '').upper()
        targets = _event_target_numbers(event)
        if action == 'TRANSFER':
            latest_transfer_round += 1
            latest_transfer_note = event.get('note') or latest_transfer_note
            for number in targets:
                revision_applied.add(number)
                target_notes[number] = event.get('note') or target_notes.get(number, '')
        elif action == 'REQUEST_REVISION':
            for number in targets:
                revision_targets.add(number)
                target_notes[number] = event.get('note') or target_notes.get(number, '')
    rows = []
    for idx, file_obj in enumerate(drawing_files):
        file_map = file_obj if isinstance(file_obj, Mapping) else {}
        key = _drawing_file_key(file_obj, idx)
        filename = str(file_map.get('filename') or key.rsplit('/', 1)[-1] or f'{idx + 1}번 도면')
        view_url = str(file_map.get('view_url') or (f'/api/files/view/{key}' if key else ''))
        download_url = str(file_map.get('download_url') or (f'/api/files/download/{key}' if key else ''))
        number = idx + 1
        chip = '수정 반영' if number in revision_applied else ('수정요청 대상' if number in revision_targets else '')
        rows.append({
            'no': number,
            'key': key,
            'filename': filename,
            'view_url': view_url,
            'download_url': download_url,
            'is_image': _is_drawing_image(filename),
            'is_selected': bool(selected_key and key == selected_key),
            'detail_url': url_for('erp_drawing_workbench.erp_drawing_workbench_detail', order_id=order_id, drawing_key=key),
            'chip': chip,
            'meta': f'최신 {latest_transfer_round}차 전달본' if latest_transfer_round else '전달 대기',
            'note': target_notes.get(number) or latest_transfer_note or '',
        })
    return rows


def _build_handoff_thread(history: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build chat-like mobile timeline entries from order-level drawing history."""
    thread = []
    indexed_history = [
        (idx, event) for idx, event in enumerate(history) if isinstance(event, Mapping)
    ]
    newest_first = sorted(
        indexed_history,
        key=lambda item: _history_event_sort_key(item[1], item[0]),
        reverse=True,
    )
    action_labels = {
        'TRANSFER': '도면 전달',
        'REQUEST_REVISION': '수정 요청',
        'CANCEL_TRANSFER': '전달 취소',
        'CONFIRM_RECEIPT': '수령 확정',
        'ERP_ORDER_CHANGED': '주문 변경',
    }
    for _, event in newest_first:
        action = (event.get('action') or '').upper()
        targets = _event_target_numbers(event)
        target_text = ', '.join(str(n) for n in targets)
        if action == 'ERP_ORDER_CHANGED':
            side = 'alert'
        elif action in ('TRANSFER', 'CANCEL_TRANSFER'):
            side = 'left'
        else:
            side = 'right'
        thread.append({
            **event,
            'side': side,
            'tag': event.get('action_label') or action_labels.get(action) or action or '-',
            'target_text': f'{target_text}번 대상' if target_text else '',
            'files': list(event.get('files') or []) if isinstance(event.get('files'), list) else [],
        })
    return thread


@erp_drawing_workbench_bp.route('/drawing-workbench')
@login_required
def erp_drawing_workbench_dashboard():
    """도면 작업실 대시보드: 도면 단계 협업 전용 화면(목록형)"""
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    q_raw = get_search_query_arg('q', 'search')
    q = q_raw.lower()
    status_filter = (request.args.get('status') or '').strip().upper()
    # ERP 공통: mine은 URL 쿼리 + erp_mine_only 쿠키 SSOT (foms.services.common.erp_mine_filter)
    mine_only = erp_mine_only_from_request(request)
    unread_only = (request.args.get('unread') or '').strip() == '1'
    due_today_only = (request.args.get('due_today') or '').strip() == '1'
    # 태블릿 도면 작업실 필터(추가, 부재 시 무영향): D-3 이내(시공 임박)만 / 전달 대기(마법사 저장분)만.
    dday3_only = (request.args.get('dday3') or '').strip() == '1'
    pending_only = (request.args.get('pending') or '').strip() == '1'
    assignee_filter_raw = (request.args.get('assignee') or '').strip()
    assignee_filter = assignee_filter_raw.lower()
    sort_by = (request.args.get('sort') or '').strip().lower()
    page = max(1, int(request.args.get('page') or '1'))
    per_page = 25
    mine_scope = resolve_mine_scope_for_user(current_user)
    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )

    orders_query = (
        db.query(Order)
        .filter(Order.active_filter(), Order.is_erp_order.is_(True))
    )
    if mine_only:
        mine_conditions = build_mine_sql_filter(current_user, scope=mine_scope)
        orders_query = (
            orders_query.filter(or_(*mine_conditions))
            if mine_conditions
            else orders_query.filter(Order.id == -1)
        )

    _seed_fp = {
        "v": KEY_VERSION,
        "uid": current_user.id if current_user else None,
        "role": getattr(current_user, "role", None) if current_user else None,
        "team": getattr(current_user, "team", None) if current_user else None,
        "mine": bool(mine_only),
    }
    _seed_key = build_dashboard_cache_key("drawing", "workbench_seed_ids", _seed_fp)
    _seed_blob = get_or_compute_dashboard_slice(
        _seed_key,
        TTL_PANEL_ROWS,
        lambda: {"order_ids": fetch_drawing_seed_order_ids(orders_query)},
        page="drawing",
        slice_name="workbench_seed_ids",
    )
    order_ids = [int(x) for x in (_seed_blob.get("order_ids") or [])]
    orders = hydrate_drawing_orders_by_ids(orders_query, order_ids)

    # 검색 카드 딥링크(?focus_order=)는 seed 캡·필터와 무관하게 해당 주문이 착지해야 한다.
    # orders/construction/measurement 대시보드와 동일한 deep-link SSOT.
    focus_order_id = request.args.get('focus_order', type=int)
    if focus_order_id and focus_order_id not in {o.id for o in orders}:
        focus_order = (
            db.query(Order)
            .filter(Order.id == focus_order_id, Order.active_filter(), Order.is_erp_order.is_(True))
            .first()
        )
        if focus_order is not None and (
            not mine_only
            or is_order_related_to_user(focus_order, current_user, scope=mine_scope)
        ):
            orders = [focus_order] + orders

    rows = []
    order_sds = [_ensure_dict(o.structured_data) for o in orders]
    assignee_user_map = load_assignee_user_map_batch(db, order_sds)
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage_raw = _erp_get_stage(o, sd)
        stage_code = STAGE_NAME_TO_CODE.get(stage_raw or '', stage_raw or '')
        drawing_obj = sd.get('drawing') or {}
        drawing_status = (drawing_obj.get('status') or sd.get('drawing_status') or 'PENDING').upper()
        is_drawing_stage = (stage_code == 'DRAWING')
        is_active_revision = (drawing_status == 'RETURNED')
        if not (is_drawing_stage or is_active_revision):
            continue

        customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-'
        manager_name = (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-'
        drawing_files = list(sd.get('drawing_current_files', []) or [])
        # 전달 대기 도면(마법사 저장분): structured_data['drawing_wizard']['pending'] 길이.
        # 이미 로드된 sd 에서 계산(추가 쿼리 없음). 작업실 일괄 전송 UI의 행 배지/판별 소스.
        drawing_wizard = sd.get('drawing_wizard') or {}
        pending_count = len(drawing_wizard.get('pending') or {})
        history = list(sd.get('drawing_transfer_history', []) or [])
        last_event = history[-1] if history else {}
        assignees = list(sd.get('drawing_assignees', []) or [])
        assignee_names = []
        for a in assignees:
            if isinstance(a, dict) and (a.get('name') or '').strip():
                assignee_names.append((a.get('name') or '').strip())
            elif isinstance(a, str) and a.strip():
                assignee_names.append(a.strip())
        assignee_text = ', '.join(assignee_names) if assignee_names else '미지정'
        role_assignees = resolve_order_role_assignees(sd, order=o, user_map=assignee_user_map)
        measurement_assignee_text = role_assignees.get('measurement_assignee') or '-'

        draw_assignee_ids = get_assignee_ids(o, 'DRAWING_DOMAIN')
        has_assignee = bool(draw_assignee_ids)
        user_id = current_user.id if current_user else None
        is_drawing_assignee = bool(user_id and user_id in draw_assignee_ids)
        is_sales_owner = is_order_related_to_user(o, current_user, scope='sales')
        include_for_mine = is_order_related_to_user(o, current_user, scope=mine_scope)
        can_sales = _can_modify_sales_domain(current_user, o, sd, False, None)
        can_transfer_row = bool(
            has_assignee
            and current_user
            and is_drawing_workbench_participant(current_user, o)
        )
        can_confirm_row = bool(can_sales and drawing_status == 'TRANSFERRED')
        transfer_round = sum(1 for h in history if isinstance(h, dict) and h.get('action') == 'TRANSFER')
        turn = _build_drawing_turn(
            drawing_status,
            has_assignee,
            can_transfer_row,
            can_confirm_row,
            len(drawing_files),
            transfer_round,
        )
        if can_confirm_row:
            primary_action = {'label': '수령 확인', 'icon': 'fa-check-double'}
        elif can_transfer_row:
            primary_action = {'label': '도면 전달', 'icon': 'fa-paper-plane'}
        elif drawing_status == 'TRANSFERRED' and can_sales:
            primary_action = {'label': '수정 요청', 'icon': 'fa-undo'}
        else:
            primary_action = {'label': '작업 열기', 'icon': 'fa-external-link-alt'}
        my_todo = (
            (drawing_status in ('PENDING', 'RETURNED') and is_drawing_assignee)
            or (drawing_status == 'TRANSFERRED' and is_sales_owner)
        )

        unchecked_requests = 0
        for h in history:
            if not isinstance(h, dict) or h.get('action') != 'REQUEST_REVISION':
                continue
            review_raw = h.get('review_check')
            review = review_raw if isinstance(review_raw, dict) else {}
            if not bool(review.get('checked')):
                unchecked_requests += 1

        alerts = _erp_alerts(o, sd, 0)
        due_today = (alerts.get('measurement_days') == 0 or alerts.get('construction_days') == 0)

        latest_request_no = None
        latest_request_note = ''
        for h in reversed(history):
            if isinstance(h, dict) and h.get('action') == 'REQUEST_REVISION':
                try:
                    target_no_raw = h.get('target_drawing_number')
                    latest_request_no = int(target_no_raw) if target_no_raw is not None else None
                except Exception:
                    pass
                latest_request_note = str(h.get('note') or '').strip()
                break
        # 최신 전달(TRANSFER) 요약 1줄: 'vN 전달 · M/D HH:MM · 이름' (이미 로드된 history 파생, 추가 쿼리 없음).
        latest_transfer_line = ''
        for h in reversed(history):
            if isinstance(h, dict) and h.get('action') == 'TRANSFER':
                _t_at = format_datetime_kst(_history_event_at_raw(h), '%m/%d %H:%M') or ''
                _t_by = str(h.get('by_user_name') or '').strip()
                _t_seg = [f'v{transfer_round} 전달' if transfer_round else '전달']
                if _t_at:
                    _t_seg.append(_t_at)
                if _t_by:
                    _t_seg.append(_t_by)
                latest_transfer_line = ' · '.join(_t_seg)
                break
        h_action = (last_event or {}).get('action') or ''
        h_action_label = {
            'TRANSFER': '도면 전달', 'REQUEST_REVISION': '수정 요청',
            'CANCEL_TRANSFER': '전달 취소', 'CONFIRM_RECEIPT': '수령 확정',
            'ERP_ORDER_CHANGED': '주문 변경',
        }.get(h_action, h_action or '-')
        order_change_pending = is_order_change_pending(sd)
        sla_level = '지연' if alerts.get('drawing_overdue') else ('오늘 마감' if due_today else '정상')
        search_hay = ' '.join([
            str(o.id), str(customer_name), str(manager_name), str(assignee_text),
            str((last_event or {}).get('note') or ''),
            '주문변경' if order_change_pending else '',
        ]).lower()

        construction_date = _resolve_construction_date_display(o, sd)
        # 제품 요약(고객·제품 카드용) — 이미 로드된 sd['items']에서 파생(추가 쿼리 없음).
        _sd_items = sd.get('items') or []
        product_summary = ', '.join(
            str((it.get('product_name') or '').strip())
            for it in _sd_items
            if isinstance(it, dict) and (it.get('product_name') or '').strip()
        )[:60]

        rows.append({
            'id': o.id,
            'is_self_measurement': getattr(o, 'is_self_measurement', False),
            'customer_name': customer_name,
            'construction_date': construction_date,
            'product_summary': product_summary,
            'manager_name': manager_name,
            'assignee_text': assignee_text,
            'measurement_assignee_text': measurement_assignee_text,
            'drawing_status': drawing_status,
            'drawing_status_label': _drawing_status_label(drawing_status),
            'file_count': len(drawing_files),
            'transfer_round': transfer_round,
            'pending_count': pending_count,
            'thumbnail_url': resolve_row_thumbnail_url(
                o.id, drawing_files, db, mobile_v2_active=mobile_v2_active
            ),
            'target_no': latest_request_no,
            'turn_label': turn['label'],
            'turn_sub': turn['sub'],
            'turn_tone': turn['tone'],
            'primary_action_label': primary_action['label'],
            'primary_action_icon': primary_action['icon'],
            'next_action': _drawing_next_action_text(drawing_status, has_assignee),
            'latest_event_at': (last_event or {}).get('transferred_at') or (last_event or {}).get('at') or '-',
            'latest_event_label': h_action_label,
            'latest_event_note': (last_event or {}).get('note') or '',
            'latest_transfer_line': latest_transfer_line,
            'latest_request_note': latest_request_note,
            'sla_level': sla_level,
            'is_overdue': bool(alerts.get('drawing_overdue')),
            'due_today': due_today,
            # 시공 D-day(영업일 기준, 미정=None) + D-3 이내 플래그(시공 임박순 정렬·KPI·필터 소스).
            'construction_days': alerts.get('construction_days'),
            'construction_d3': bool(alerts.get('construction_d3')),
            'unread_count': unchecked_requests,
            'order_change_pending': order_change_pending,
            'my_todo': my_todo,
            'include_for_mine': include_for_mine,
            'search_hay': search_hay,
        })

    # 프로세스 맵 카운트는 목록 필터와 무관하게 전체 큐 기준(파이프라인 bar SSOT).
    stats = {'total': len(rows), 'WAITING': 0, 'IN_PROGRESS': 0, 'RETURNED': 0, 'TRANSFERRED': 0, 'CONFIRMED': 0, 'overdue': 0, 'unread': 0, 'd3': 0, 'pending_transfer': 0}
    for r in rows:
        status = (r.get('drawing_status') or 'WAITING').upper()
        if status == 'PENDING':
            status = 'WAITING'
        if status in stats:
            stats[status] += 1
        if r.get('is_overdue'):
            stats['overdue'] += 1
        if r.get('unread_count', 0) > 0:
            stats['unread'] += 1
        # 태블릿 KPI 타일 SSOT(전체 큐 기준, 목록 필터와 무관): D-3 이내 / 전달 대기(마법사 저장분).
        if r.get('construction_d3'):
            stats['d3'] += 1
        if int(r.get('pending_count') or 0) > 0:
            stats['pending_transfer'] += 1

    if focus_order_id:
        # 검색 카드 딥링크: 단건만 착지시키고 목록 필터·페이지는 적용하지 않는다.
        rows = [r for r in rows if r.get('id') == focus_order_id]
        if mine_only:
            rows = [r for r in rows if r.get('include_for_mine')]
    else:
        if mine_only:
            rows = [r for r in rows if r.get('include_for_mine')]
        if unread_only:
            rows = [r for r in rows if r.get('unread_count', 0) > 0]
        if due_today_only:
            rows = [r for r in rows if r.get('due_today')]
        if dday3_only:
            rows = [r for r in rows if r.get('construction_d3')]
        if pending_only:
            rows = [r for r in rows if int(r.get('pending_count') or 0) > 0]
        if assignee_filter:
            rows = [r for r in rows if assignee_filter in (r.get('assignee_text') or '').lower()]
        if q:
            rows = [r for r in rows if q in (r.get('search_hay') or '')]

        if status_filter:
            def _match_status(row_status):
                s = (row_status or '').upper()
                return s in ('WAITING', 'PENDING') if status_filter == 'WAITING' else s == status_filter
            rows = [r for r in rows if _match_status(r.get('drawing_status') or '')]

    rows.sort(key=lambda r: (
        0 if r.get('order_change_pending') else 1,
        0 if r.get('my_todo') else 1,
        0 if r.get('is_overdue') else 1,
        -int(r.get('id') or 0),
    ))

    if sort_by:
        reverse = sort_by.startswith('-')
        sort_by = sort_by[1:] if reverse else sort_by
        if sort_by == 'sla':
            rows.sort(key=lambda r: (0 if r.get('is_overdue') else (1 if r.get('due_today') else 2), -int(r.get('id') or 0)), reverse=reverse)
        elif sort_by == 'status':
            status_order = {'RETURNED': 1, 'TRANSFERRED': 2, 'IN_PROGRESS': 3, 'WAITING': 4, 'CONFIRMED': 5}
            rows.sort(key=lambda r: (status_order.get(r.get('drawing_status'), 99), -int(r.get('id') or 0)), reverse=reverse)
        elif sort_by == 'updated_at':
            rows.sort(key=lambda r: r.get('latest_event_at') or '', reverse=not reverse)
        elif sort_by == 'unread':
            rows.sort(key=lambda r: (-int(r.get('unread_count') or 0), -int(r.get('id') or 0)), reverse=reverse)
        elif sort_by == 'id':
            rows.sort(key=lambda r: int(r.get('id') or 0), reverse=reverse)
        elif sort_by == 'schedule':
            # 시공일 임박순: 시공 D-day 오름차순(임박·지연 먼저), 미정은 맨 뒤.
            rows.sort(
                key=lambda r: (0, r['construction_days']) if r.get('construction_days') is not None else (1, 0),
                reverse=reverse,
            )

    # 모바일 단일 리스트 무한스크롤: 정렬 무관 '내 차례'를 항상 앞으로(안정 정렬로 그룹 보존).
    rows.sort(key=lambda r: 0 if r.get('my_todo') else 1)

    total_count = len(rows)
    total_pages = max(1, (total_count + per_page - 1) // per_page) if per_page > 0 else 1
    page = min(page, total_pages)
    start_idx = (page - 1) * per_page
    rows = rows[start_idx:start_idx + per_page]

    template_name = (
        'drawing/partials/workbench_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'drawing/workbench_dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            rows=rows,
            stats=stats,
            pagination={'page': page, 'per_page': per_page, 'total_count': total_count, 'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages},
            sort_by=request.args.get('sort') or '',
            filters={'q': q_raw, 'status': status_filter, 'mine': '1' if mine_only else '', 'unread': '1' if unread_only else '', 'due_today': '1' if due_today_only else '', 'assignee': assignee_filter_raw, 'dday3': '1' if dday3_only else '', 'pending': '1' if pending_only else ''},
            can_edit_erp=can_edit_erp(current_user),
            erp_order_enabled=True,
            erp_mine_only=mine_only,
            drawing_thumb_enabled=drawing_thumb_enabled(mobile_v2_active=mobile_v2_active),
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response


@erp_drawing_workbench_bp.route('/drawing-workbench/<int:order_id>')
@login_required
def erp_drawing_workbench_detail(order_id):
    """도면 작업실 상세: 도면팀↔주문담당 협업 실행판."""
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True)).first()
    if not order:
        flash('주문을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('erp_drawing_workbench.erp_drawing_workbench_dashboard'))

    s_data = _ensure_dict(order.structured_data)
    # 도면 마법사 [저장]본(전달 대기) 목록 — 상세 상단 패널·전달 모달 카드에서 사용.
    from foms.api.drawing.wizard import _pending_list
    drawing_pending = _pending_list(s_data)
    stage = _erp_get_stage(order, s_data)
    drawing_status = ((s_data.get('drawing') or {}).get('status') or s_data.get('drawing_status') or 'PENDING').upper()
    drawing_files = list(s_data.get('drawing_current_files', []) or [])
    history_raw = list(s_data.get('drawing_transfer_history', []) or [])
    requested_drawing_key = (request.args.get('drawing_key') or '').strip()

    history = []
    for idx, h in enumerate(history_raw):
        if not isinstance(h, dict):
            continue
        h_action = (h.get('action') or '').strip()
        event_key = f"{idx}:{h_action}:{_history_event_at_raw(h)}:{h.get('by_user_id') or ''}"
        history.append({
            **h,
            'event_key': event_key,
            'action_label': {
                'TRANSFER': '도면 전달',
                'REQUEST_REVISION': '수정 요청',
                'CANCEL_TRANSFER': '전달 취소',
                'CONFIRM_RECEIPT': '수령 확정',
                'ERP_ORDER_CHANGED': '주문 변경',
            }.get(h_action, h_action or '-'),
            'at_text': _history_event_at_text(h),
            'by_text': h.get('by_user_name') or '-',
            'target_no': h.get('target_drawing_number') or h.get('replace_target_number'),
            'files': list(h.get('files') or []) if isinstance(h.get('files'), list) else [],
        })

    revision_requests = [h for h in history if h.get('action') == 'REQUEST_REVISION']
    revision_requests.reverse()
    unread_count = 0
    for h in revision_requests:
        review_raw = h.get('review_check')
        review = review_raw if isinstance(review_raw, dict) else {}
        if not bool(review.get('checked')):
            unread_count += 1
    transfer_events = [h for h in history if h.get('action') == 'TRANSFER']
    latest_transfer = transfer_events[-1] if transfer_events else None
    prev_transfer = transfer_events[-2] if len(transfer_events) > 1 else None

    if latest_transfer and revision_requests:
        latest_req = revision_requests[0]
        if _history_event_after(latest_transfer, latest_req):
            latest_keys = {f.get('key') for f in (latest_transfer.get('files') or []) if isinstance(f, dict) and f.get('key')}
            for df in drawing_files:
                if isinstance(df, dict) and df.get('key') in latest_keys:
                    df['is_revision'] = True

    active_tab = (request.args.get('tab') or 'timeline').strip().lower()
    if active_tab not in ('timeline', 'requests', 'compare'):
        active_tab = 'timeline'
    highlight_event_id = (request.args.get('event_id') or '').strip()
    try:
        highlight_target_no = int(request.args.get('target_no') or 0) or None
    except (TypeError, ValueError):
        highlight_target_no = None

    for h in history:
        h['is_highlight'] = bool(highlight_event_id) and h.get('event_key') == highlight_event_id
    for h in revision_requests:
        h['is_highlight'] = (bool(highlight_event_id) and h.get('event_key') == highlight_event_id) or (highlight_target_no and int(h.get('target_no') or 0) == int(highlight_target_no))

    draw_assignee_ids = get_assignee_ids(order, 'DRAWING_DOMAIN')
    has_assignee = bool(draw_assignee_ids)
    current_user_id = current_user.id if current_user else None
    is_drawing_participant = bool(
        current_user and is_drawing_workbench_participant(current_user, order)
    )
    # 액션바 4버튼 상호배타 노출: 전달/전달취소=도면팀+관리자, 수정요청/수령확정=영업측+관리자(도면팀 제외).
    # is_drawing_team(정확히 team=='DRAWING' 리터럴 비교)은 is_drawing_workbench_participant
    # (워크벤치 접근 참여자 판정, 배정된 비도면팀 직원도 True인 더 넓은 개념)와 별개 축이다.
    is_admin = bool(current_user and current_user.role == 'ADMIN')
    is_drawing_team = bool(
        current_user and (getattr(current_user, 'team', None) or '').strip() == 'DRAWING'
    )
    # 전달 버튼은 도면팀+관리자 전용. 배정 로직은 그대로 두고 팀 조건을 추가로 AND.
    is_transfer_authorized_team = bool(is_admin or is_drawing_team)
    can_transfer = bool(has_assignee and is_drawing_participant and is_transfer_authorized_team)
    transfer_gated_by_revision_checklist = bool(
        drawing_status == 'RETURNED'
        and has_pending_unchecked_drawing_revision_requests(s_data)
    )
    can_open_transfer = bool(can_transfer and not transfer_gated_by_revision_checklist)
    can_toggle_revision_check = is_drawing_participant
    can_sales_domain = _can_modify_sales_domain(current_user, order, s_data, False, None)
    # 수정요청/수령확정=영업측 전용(도면팀에는 안 보임). 관리자는 예외로 무조건 통과.
    can_request_revision = bool(is_admin or (can_sales_domain and not is_drawing_team))
    can_confirm_receipt = bool(
        (is_admin or (can_sales_domain and not is_drawing_team))
        and drawing_status == 'TRANSFERRED'
    )
    can_cancel_transfer = False
    if latest_transfer:
        if current_user is not None and current_user.role == 'ADMIN':
            can_cancel_transfer = True
        elif can_transfer:
            can_cancel_transfer = True
        else:
            try:
                by_user_raw = latest_transfer.get('by_user_id')
                can_cancel_transfer = (
                    by_user_raw is not None
                    and current_user_id is not None
                    and int(by_user_raw) == int(current_user_id)
                )
            except Exception:
                pass
    # 전달취소는 표시상 도면팀+관리자로 한정 — self-cancel 레거시 분기(by_user_id 일치)가
    # 팀 무관하게 통과시키던 문제를 최종 게이트로 봉합(과거 데이터 호환은 위 분기가 유지).
    can_cancel_transfer = bool(can_cancel_transfer and is_transfer_authorized_team)

    customer_name = (((s_data.get('parties') or {}).get('customer') or {}).get('name')) or '-'
    manager_name = (((s_data.get('parties') or {}).get('manager') or {}).get('name')) or (order.manager_name or '-') or '-'
    users_by_id = {
        u.id: u for u in db.query(User).filter(User.id.in_(draw_assignee_ids)).all()  # perf-ok
    } if draw_assignee_ids else {}
    assignee_names = []
    for uid in draw_assignee_ids:
        u = users_by_id.get(uid)
        if u is not None and u.name is not None:
            assignee_names.append(u.name)
    assignee_text = ', '.join(assignee_names) if assignee_names else '미지정'
    next_action = _drawing_next_action_text(drawing_status, has_assignee)
    status_label = _drawing_status_label(drawing_status)
    checklist = [
        {'label': '도면 담당자 지정', 'ok': has_assignee},
        {'label': '최신 전달본 확인', 'ok': bool(drawing_files)},
        {'label': '요청사항 확인', 'ok': unread_count == 0},
    ]
    transfer_round = sum(1 for h in history if h.get('action') == 'TRANSFER')
    file_keys = [_drawing_file_key(f, idx) for idx, f in enumerate(drawing_files)]
    handoff_invalid_drawing_key = ''
    selected_key = requested_drawing_key if requested_drawing_key in file_keys else ''
    deep_link_requested = bool(highlight_event_id or highlight_target_no)
    if requested_drawing_key and requested_drawing_key not in file_keys:
        handoff_invalid_drawing_key = '선택한 도면을 찾을 수 없습니다.'
    if not selected_key and highlight_target_no and 1 <= highlight_target_no <= len(file_keys):
        selected_key = file_keys[highlight_target_no - 1]
    if not selected_key and (len(file_keys) == 1 or deep_link_requested):
        selected_key = file_keys[0] if file_keys else ''
    handoff_view = 'detail' if (len(file_keys) <= 1 or selected_key or deep_link_requested) else 'list'
    if handoff_invalid_drawing_key and len(file_keys) > 1 and not deep_link_requested:
        handoff_view = 'list'
    handoff_files = _build_handoff_files(order.id, drawing_files, history, selected_key)
    selected_file = next((f for f in handoff_files if f.get('is_selected')), None)
    if not selected_file and handoff_files and handoff_view == 'detail':
        selected_file = handoff_files[0]
        selected_file['is_selected'] = True
    selected_index = handoff_files.index(selected_file) if selected_file in handoff_files else -1
    handoff_prev_url = handoff_files[selected_index - 1]['detail_url'] if selected_index > 0 else ''
    handoff_next_url = handoff_files[selected_index + 1]['detail_url'] if 0 <= selected_index < len(handoff_files) - 1 else ''
    handoff_turn = _build_drawing_turn(
        drawing_status,
        has_assignee,
        can_transfer,
        can_confirm_receipt,
        len(handoff_files),
        transfer_round,
    )
    handoff_thread = _build_handoff_thread(history)

    product_items = build_product_items_for_order(db, order)
    order_change_pending = is_order_change_pending(s_data)
    latest_order_change_note = ''
    for h in reversed(history):
        if h.get('action') == 'ERP_ORDER_CHANGED':
            latest_order_change_note = str(h.get('note') or '').strip()
            break
    # 도면 상세 전용: 공통 실측 이미지(항목에 매핑되지 않은 첨부) 수집
    common_measure_photos = []
    for att in db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])
    ).order_by(OrderAttachment.created_at.desc()).all():
        item_index_raw = getattr(att, 'item_index', None)
        try:
            item_index = int(item_index_raw) if item_index_raw is not None else None
            if item_index is not None and item_index < 0:
                item_index = None
        except (TypeError, ValueError):
            item_index = None
        if item_index is None or item_index < 0 or item_index >= len(product_items):
            common_measure_photos.append({
                'filename': att.filename,
                'view_url': f'/api/files/view/{att.storage_key}',
                'download_url': f'/api/files/download/{att.storage_key}',
                'key': att.storage_key,
                'item_index': item_index,
            })
    measure_photos = []  # 템플릿 호환용 (미사용)

    ctx = dict(
        order=order,
        stage=stage,
        drawing_status=drawing_status,
        drawing_status_label=status_label,
        next_action=next_action,
        customer_name=customer_name,
        manager_name=manager_name,
        assignee_text=assignee_text,
        drawing_files=drawing_files,
        drawing_pending=drawing_pending,
        history=history,
        revision_requests=revision_requests,
        latest_transfer=latest_transfer,
        prev_transfer=prev_transfer,
        active_tab=active_tab,
        highlight_event_id=highlight_event_id,
        highlight_target_no=highlight_target_no,
        unread_count=unread_count,
        order_change_pending=order_change_pending,
        latest_order_change_note=latest_order_change_note,
        checklist=checklist,
        mobile_handoff_view=handoff_view,
        mobile_handoff_files=handoff_files,
        mobile_handoff_selected_file=selected_file,
        mobile_handoff_selected_index=selected_index,
        mobile_handoff_prev_url=handoff_prev_url,
        mobile_handoff_next_url=handoff_next_url,
        mobile_handoff_list_url=url_for('erp_drawing_workbench.erp_drawing_workbench_detail', order_id=order.id),
        mobile_handoff_turn=handoff_turn,
        mobile_handoff_thread=handoff_thread,
        mobile_handoff_invalid_drawing_key=handoff_invalid_drawing_key,
        mobile_handoff_active=mobile_v2_active,
        can_transfer=can_transfer,
        can_open_transfer=can_open_transfer,
        transfer_gated_by_revision_checklist=transfer_gated_by_revision_checklist,
        can_toggle_revision_check=can_toggle_revision_check,
        can_request_revision=can_request_revision,
        can_confirm_receipt=can_confirm_receipt,
        can_cancel_transfer=can_cancel_transfer,
        can_edit_erp=can_edit_erp(current_user),
        my_id=current_user.id if current_user else 0,
        my_role=current_user.role if current_user else '',
        my_team=current_user.team if current_user else '',
        my_name=current_user.name if current_user else '',
        history_json=history_raw,
        product_items=product_items,
        measure_photos=measure_photos,
        common_measure_photos=common_measure_photos,
        erp_order_enabled=True,
    )
    template_name = (
        'drawing/workbench_detail_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'drawing/workbench_detail.html'
    )
    response = make_response(render_template(template_name, **ctx))
    apply_erp_shell_fragment_headers(response, request)
    return response
