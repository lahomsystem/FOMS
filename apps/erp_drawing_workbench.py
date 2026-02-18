"""
ERP 도면 작업실 (ERP-SLIM-5)
erp.py에서 분리: /erp/drawing-workbench, /erp/drawing-workbench/<id>
"""
from flask import Blueprint, render_template, request, session, url_for, redirect, flash
from db import get_db
from models import Order, User, OrderAttachment
from apps.auth import login_required, get_user_by_id
from services.erp_permissions import can_edit_erp
from services.erp_policy import STAGE_NAME_TO_CODE, get_assignee_ids
from services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_alerts,
    _can_modify_sales_domain,
    _drawing_status_label,
    _drawing_next_action_text,
)

erp_drawing_workbench_bp = Blueprint('erp_drawing_workbench', __name__, url_prefix='/erp')


@erp_drawing_workbench_bp.route('/drawing-workbench')
@login_required
def erp_drawing_workbench_dashboard():
    """도면 작업실 대시보드: 도면 단계 협업 전용 화면(목록형)"""
    db = get_db()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    q_raw = (request.args.get('q') or '').strip()
    q = q_raw.lower()
    status_filter = (request.args.get('status') or '').strip().upper()
    mine_only = (request.args.get('mine') or '').strip() == '1'
    unread_only = (request.args.get('unread') or '').strip() == '1'
    due_today_only = (request.args.get('due_today') or '').strip() == '1'
    assignee_filter_raw = (request.args.get('assignee') or '').strip()
    assignee_filter = assignee_filter_raw.lower()
    sort_by = (request.args.get('sort') or '').strip().lower()
    page = max(1, int(request.args.get('page') or '1'))
    per_page = 25

    orders = (
        db.query(Order)
        .filter(Order.deleted_at.is_(None), Order.is_erp_beta.is_(True))
        .order_by(Order.created_at.desc())
        .limit(500)
        .all()
    )

    rows = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage_raw = _erp_get_stage(o, sd)
        stage_code = STAGE_NAME_TO_CODE.get(stage_raw, stage_raw)
        drawing_obj = sd.get('drawing') or {}
        drawing_status = (drawing_obj.get('status') or sd.get('drawing_status') or 'PENDING').upper()
        is_drawing_stage = (stage_code == 'DRAWING')
        is_active_revision = (drawing_status == 'RETURNED')
        if not (is_drawing_stage or is_active_revision):
            continue

        customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-'
        manager_name = (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-'
        drawing_files = list(sd.get('drawing_current_files', []) or [])
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

        draw_assignee_ids = get_assignee_ids(o, 'DRAWING_DOMAIN')
        has_assignee = bool(draw_assignee_ids)
        user_id = current_user.id if current_user else None
        is_drawing_assignee = bool(user_id and user_id in draw_assignee_ids)
        can_sales = _can_modify_sales_domain(current_user, o, sd, False, None)
        my_todo = (
            (drawing_status in ('PENDING', 'RETURNED') and is_drawing_assignee)
            or (drawing_status == 'TRANSFERRED' and can_sales)
        )
        if mine_only and not my_todo:
            continue

        unchecked_requests = 0
        for h in history:
            if not isinstance(h, dict) or h.get('action') != 'REQUEST_REVISION':
                continue
            review = h.get('review_check') if isinstance(h.get('review_check'), dict) else {}
            if not bool(review.get('checked')):
                unchecked_requests += 1
        if unread_only and unchecked_requests <= 0:
            continue

        alerts = _erp_alerts(o, sd, 0)
        due_today = (alerts.get('measurement_days') == 0 or alerts.get('construction_days') == 0)
        if due_today_only and not due_today:
            continue
        if assignee_filter and assignee_filter not in (assignee_text or '').lower():
            continue
        if q:
            hay = ' '.join([
                str(o.id), str(customer_name), str(manager_name), str(assignee_text),
                str((last_event or {}).get('note') or ''),
            ]).lower()
            if q not in hay:
                continue

        latest_request_no = None
        for h in reversed(history):
            if isinstance(h, dict) and h.get('action') == 'REQUEST_REVISION':
                try:
                    latest_request_no = int(h.get('target_drawing_number'))
                except Exception:
                    pass
                break
        h_action = (last_event or {}).get('action') or ''
        h_action_label = {
            'TRANSFER': '도면 전달', 'REQUEST_REVISION': '수정 요청',
            'CANCEL_TRANSFER': '전달 취소', 'CONFIRM_RECEIPT': '수령 확정',
        }.get(h_action, h_action or '-')
        sla_level = '지연' if alerts.get('drawing_overdue') else ('오늘 마감' if due_today else '정상')

        rows.append({
            'id': o.id,
            'customer_name': customer_name,
            'manager_name': manager_name,
            'assignee_text': assignee_text,
            'drawing_status': drawing_status,
            'drawing_status_label': _drawing_status_label(drawing_status),
            'file_count': len(drawing_files),
            'target_no': latest_request_no,
            'next_action': _drawing_next_action_text(drawing_status, has_assignee),
            'latest_event_at': (last_event or {}).get('transferred_at') or (last_event or {}).get('at') or '-',
            'latest_event_label': h_action_label,
            'latest_event_note': (last_event or {}).get('note') or '',
            'sla_level': sla_level,
            'is_overdue': bool(alerts.get('drawing_overdue')),
            'due_today': due_today,
            'unread_count': unchecked_requests,
            'my_todo': my_todo,
        })

    stats = {'total': len(rows), 'WAITING': 0, 'IN_PROGRESS': 0, 'RETURNED': 0, 'TRANSFERRED': 0, 'CONFIRMED': 0, 'overdue': 0, 'unread': 0}
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

    if status_filter:
        def _match_status(row_status):
            s = (row_status or '').upper()
            return s in ('WAITING', 'PENDING') if status_filter == 'WAITING' else s == status_filter
        rows = [r for r in rows if _match_status(r.get('drawing_status') or '')]

    rows.sort(key=lambda r: (0 if r.get('my_todo') else 1, 0 if r.get('is_overdue') else 1, -int(r.get('id') or 0)))

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

    total_count = len(rows)
    total_pages = max(1, (total_count + per_page - 1) // per_page) if per_page > 0 else 1
    page = min(page, total_pages)
    start_idx = (page - 1) * per_page
    rows = rows[start_idx:start_idx + per_page]

    return render_template(
        'erp_drawing_workbench_dashboard.html',
        rows=rows,
        stats=stats,
        pagination={'page': page, 'per_page': per_page, 'total_count': total_count, 'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages},
        sort_by=request.args.get('sort') or '',
        filters={'q': q_raw, 'status': status_filter, 'mine': '1' if mine_only else '', 'unread': '1' if unread_only else '', 'due_today': '1' if due_today_only else '', 'assignee': assignee_filter_raw},
        can_edit_erp=can_edit_erp(current_user),
        erp_beta_enabled=True,
    )


@erp_drawing_workbench_bp.route('/drawing-workbench/<int:order_id>')
@login_required
def erp_drawing_workbench_detail(order_id):
    """도면 작업실 상세: 도면팀↔주문담당 협업 실행판."""
    db = get_db()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    order = db.query(Order).filter(Order.id == order_id, Order.deleted_at.is_(None), Order.is_erp_beta.is_(True)).first()
    if not order:
        flash('주문을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('erp_drawing_workbench.erp_drawing_workbench_dashboard'))

    s_data = _ensure_dict(order.structured_data)
    stage = _erp_get_stage(order, s_data)
    drawing_status = ((s_data.get('drawing') or {}).get('status') or s_data.get('drawing_status') or 'PENDING').upper()
    drawing_files = list(s_data.get('drawing_current_files', []) or [])
    history_raw = list(s_data.get('drawing_transfer_history', []) or [])

    history = []
    for idx, h in enumerate(history_raw):
        if not isinstance(h, dict):
            continue
        h_action = (h.get('action') or '').strip()
        event_key = f"{idx}:{h_action}:{h.get('at') or h.get('transferred_at') or ''}:{h.get('by_user_id') or ''}"
        history.append({
            **h,
            'event_key': event_key,
            'action_label': {'TRANSFER': '도면 전달', 'REQUEST_REVISION': '수정 요청', 'CANCEL_TRANSFER': '전달 취소', 'CONFIRM_RECEIPT': '수령 확정'}.get(h_action, h_action or '-'),
            'at_text': h.get('transferred_at') or h.get('at') or '-',
            'by_text': h.get('by_user_name') or '-',
            'target_no': h.get('target_drawing_number') or h.get('replace_target_number'),
            'files': list(h.get('files') or []) if isinstance(h.get('files'), list) else [],
        })

    revision_requests = [h for h in history if h.get('action') == 'REQUEST_REVISION']
    revision_requests.reverse()
    unread_count = 0
    for h in revision_requests:
        review = h.get('review_check') if isinstance(h.get('review_check'), dict) else {}
        if not bool(review.get('checked')):
            unread_count += 1
    transfer_events = [h for h in history if h.get('action') == 'TRANSFER']
    latest_transfer = transfer_events[-1] if transfer_events else None
    prev_transfer = transfer_events[-2] if len(transfer_events) > 1 else None

    if latest_transfer and revision_requests:
        latest_req = revision_requests[0]
        tf_at = latest_transfer.get('at') or latest_transfer.get('transferred_at') or ''
        req_at = latest_req.get('at') or latest_req.get('transferred_at') or ''
        if tf_at > req_at:
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
    is_drawing_assignee = bool(current_user_id and current_user_id in draw_assignee_ids)
    can_transfer = bool(has_assignee and ((current_user and current_user.role == 'ADMIN') or is_drawing_assignee))
    can_sales_domain = _can_modify_sales_domain(current_user, order, s_data, False, None)
    can_request_revision = can_sales_domain
    can_confirm_receipt = bool(can_sales_domain and drawing_status == 'TRANSFERRED')
    can_cancel_transfer = False
    if latest_transfer:
        if current_user and current_user.role == 'ADMIN':
            can_cancel_transfer = True
        elif can_transfer:
            can_cancel_transfer = True
        else:
            try:
                can_cancel_transfer = int(latest_transfer.get('by_user_id')) == int(current_user_id)
            except Exception:
                pass

    customer_name = (((s_data.get('parties') or {}).get('customer') or {}).get('name')) or '-'
    manager_name = (((s_data.get('parties') or {}).get('manager') or {}).get('name')) or (order.manager_name or '-') or '-'
    assignee_names = []
    for uid in draw_assignee_ids:
        u = db.query(User).filter(User.id == uid).first()
        if u and u.name:
            assignee_names.append(u.name)
    assignee_text = ', '.join(assignee_names) if assignee_names else '미지정'
    next_action = _drawing_next_action_text(drawing_status, has_assignee)
    status_label = _drawing_status_label(drawing_status)
    checklist = [
        {'label': '도면 담당자 지정', 'ok': has_assignee},
        {'label': '최신 전달본 확인', 'ok': bool(drawing_files)},
        {'label': '요청사항 확인', 'ok': unread_count == 0},
    ]

    raw_product_items = s_data.get('items') or s_data.get('products') or s_data.get('product_items') or []
    if isinstance(raw_product_items, dict):
        raw_product_items = [raw_product_items]
    product_items = []
    for it in list(raw_product_items):
        if not isinstance(it, dict):
            continue
        item = dict(it)
        item['width'] = item.get('width') or item.get('spec_width') or ''
        item['depth'] = item.get('depth') or item.get('spec_depth') or ''
        item['height'] = item.get('height') or item.get('spec_height') or ''
        item['measurement_images'] = []
        product_items.append(item)

    measure_photos = []
    common_measure_photos = []
    for att in db.query(OrderAttachment).filter(OrderAttachment.order_id == order_id, OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])).order_by(OrderAttachment.created_at.desc()).all():
        item_index_raw = getattr(att, 'item_index', None)
        try:
            item_index = int(item_index_raw) if item_index_raw is not None else None
            if item_index is not None and item_index < 0:
                item_index = None
        except (TypeError, ValueError):
            item_index = None
        photo = {'filename': att.filename, 'view_url': f'/api/files/view/{att.storage_key}', 'download_url': f'/api/files/download/{att.storage_key}', 'key': att.storage_key, 'item_index': item_index}
        measure_photos.append(photo)
        if item_index is not None and 0 <= item_index < len(product_items):
            product_items[item_index].setdefault('measurement_images', []).append(photo)
        else:
            common_measure_photos.append(photo)

    return render_template(
        'erp_drawing_workbench_detail.html',
        order=order,
        stage=stage,
        drawing_status=drawing_status,
        drawing_status_label=status_label,
        next_action=next_action,
        customer_name=customer_name,
        manager_name=manager_name,
        assignee_text=assignee_text,
        drawing_files=drawing_files,
        history=history,
        revision_requests=revision_requests,
        latest_transfer=latest_transfer,
        prev_transfer=prev_transfer,
        active_tab=active_tab,
        highlight_event_id=highlight_event_id,
        highlight_target_no=highlight_target_no,
        unread_count=unread_count,
        checklist=checklist,
        can_transfer=can_transfer,
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
    )
