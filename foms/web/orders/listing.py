"""주문 페이지 Blueprint (canonical; SFC-B11B): index, add_order, bulk_action, order_link filter. (edit_order는 order_edit_bp로 분리)"""
import copy
import json
import re
from typing import Optional
from flask import Blueprint, make_response, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from markupsafe import Markup, escape
from sqlalchemy import or_, String

from foms.web.auth import login_required, role_required, log_access, get_user_by_id
from foms.services.audit_message_display import describe_field_change
from foms.services.orders.audit_order_context import order_audit_context
from db import get_db
from models import Order, User
from foms.services.orders.estimate_defaults import (
    ERP_DRAFT_PLACEHOLDER_CUSTOMER,
    ERP_DRAFT_PLACEHOLDER_PHONE,
    ERP_DRAFT_PLACEHOLDER_PRODUCT,
)
from foms.services.orders.status_constants import STATUS
from foms.services.order_display_utils import format_options_for_display, _ensure_dict
# 지오코드 enqueue 는 이제 생성자(order_create)가 tx-내 GEOCODE outbox 로 예약한다. 이
# 바인딩은 namespace surface 계약(foms_namespace_surface_tests: order_pages 가 canonical
# jobs.queue 를 재노출)을 위해 유지한다.
from foms.services.jobs.queue import enqueue_geocode_order_address  # noqa: F401
from foms.services.orders.order_create import (
    OrderCreateError,
    create_order,
    resolve_order_owner,
)
from foms.services.order_copy import OrderCopyError, copy_orders_batch
from foms.services.erp_display import erp_deposit_amount_from_structured
from foms.services.datetime_kst import get_today_kst, now_kst, now_utc_naive
from foms.services.request_utils import (
    get_preserved_filter_args,
    get_search_query_arg,
    redirect_if_legacy_open_erp_beta,
)
from foms.services.feature_flags import (
    env_bool,
    should_render_new_order_wizard,
    wizard_new_order_enabled,
)
from foms.services.post_auth_navigation import redirect_to_authenticated_home, should_use_erp_mobile_home
from foms.services.gnav_contract import gnav_orders_layout_parent, wants_gnav_fragment
from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate


def _extract_orderer_from_options(options_str):
    """레거시 주문 options에서 발주사 추출. online_options_summary 내 '발주사 : X' 패턴."""
    if not options_str:
        return None
    try:
        data = json.loads(options_str) if isinstance(options_str, str) else options_str
        if not isinstance(data, dict):
            return None
        summary = data.get('online_options_summary') or ''
        if not summary:
            return None
        m = re.search(r'발주사\s*:\s*(.+?)(?:\n|$)', summary, re.MULTILINE)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def _first_product_name_from_structured_data(structured_data):
    items = structured_data.get('items') or []
    if not isinstance(items, list):
        return ''
    for item in items:
        if not isinstance(item, dict):
            continue
        product_name = (item.get('product_name') or item.get('name') or '').strip()
        if product_name:
            return product_name
    return ''


def _form_owner_user_id(form) -> Optional[int]:
    """폼의 ``sales_owner_id`` (Admin/Manager 가 지정하는 SALES owner)를 int 로 파싱한다.

    Args:
        form: ``request.form`` MultiDict.

    Returns:
        지정 owner user_id, 없으면 None(STAFF self default 경로).

    Raises:
        OrderCreateError: 값이 있으나 정수가 아님.
    """
    raw = (form.get('sales_owner_id') or '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise OrderCreateError('영업 담당자 지정이 올바르지 않습니다.') from exc


order_pages_bp = Blueprint('order_pages', __name__, url_prefix='')


@order_pages_bp.app_template_filter('order_link')
def order_link_filter(s):
    """메시지 텍스트를 HTML escape한 뒤 '주문 #<번호>'만 링크로 변환.

    저장형 XSS 방지(P0-19): SecurityLog.message에는 로그인 실패 시 공개
    username 등 신뢰할 수 없는 원문이 저장된다. 원문을 먼저 escape하여 텍스트로만
    렌더하고, ``주문 #<digits>`` 패턴(숫자만)만 서버가 생성한 안전한 ``<a>``
    링크로 치환한다. 기존에 저장된 hostile row도 escape 경로를 통과하므로 안전.

    Args:
        s: 렌더할 로그 메시지 문자열(신뢰 불가).

    Returns:
        Markup: escape된 텍스트 + 서버 생성 ``주문 #<n>`` 링크만 포함한 안전 HTML.
    """
    escaped = escape('' if s is None else s)  # Markup: < > & " ' 인코딩

    def repl(m):
        oid = m.group(1)  # \d+ 만 매칭 → 정수 링크 인자로 안전
        link = escape(url_for('order_edit.edit_order', order_id=oid))
        return f'<a href="{link}">주문 #{oid}</a>'

    return Markup(re.sub(r'주문 #(\d+)', repl, str(escaped)))


def _legacy_orders_list_redirect():
    """Legacy /orders/ path → desktop ``/`` or mobile ERP v2 ``/erp/dashboard``."""
    return redirect_to_authenticated_home(request, **request.args)


@order_pages_bp.route('/orders/')
@order_pages_bp.route('/orders')
@login_required
def orders_index_alias():
    """Legacy /orders/ path → canonical 주문 목록 (mobile ERP v2 → /erp/dashboard)."""
    return _legacy_orders_list_redirect()


@order_pages_bp.route('/')
@login_required
def index():
    """메인 주문 목록 페이지."""
    _uid_raw = session.get('user_id')
    _uid = int(_uid_raw) if _uid_raw is not None else None
    if should_use_erp_mobile_home(_uid, request):
        return redirect(url_for('erp_dashboard.erp_dashboard', **request.args))
    try:
        db = get_db()
        status_filter = request.args.get('status')
        if status_filter == 'MEASURED':  # 레거시 호환
            status_filter = 'MEASURE'
        region_filter = request.args.get('region')
        search_query = get_search_query_arg('search', 'q')
        effective_status_filter = None if search_query else status_filter
        effective_region_filter = None if search_query else region_filter
        page = request.args.get('page', 1, type=int)
        per_page = 100

        filterable_columns = [
            'id', 'received_date', 'received_time', 'customer_name', 'phone',
            'address', 'product', 'options', 'notes', 'status',
            'measurement_date', 'measurement_time', 'completion_date', 'manager_name', 'payment_amount'
        ]
        column_filters = {}
        for col in filterable_columns:
            filter_key = f'filter_{col}'
            if filter_key in request.args:
                column_filters[col] = request.args[filter_key]
        active_column_filters = {k: v for k, v in column_filters.items() if v}

        query = db.query(Order).filter(Order.active_filter())
        if effective_status_filter and effective_status_filter != 'ALL':
            query = query.filter(Order.status == effective_status_filter)
        if effective_region_filter == 'metro':
            query = query.filter(Order.is_regional == False)
        elif effective_region_filter == 'regional':
            query = query.filter(Order.is_regional == True)
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    erp_order_dashboard_search_predicate(
                        search_term,
                        include_structured_data_blob=False,
                    ),
                    Order.received_date.like(search_term),
                    Order.received_time.like(search_term),
                    Order.options.like(search_term),
                    Order.notes.like(search_term),
                    Order.status.like(search_term),
                    Order.measurement_date.like(search_term),
                    Order.measurement_time.like(search_term),
                    Order.scheduled_date.like(search_term),
                    Order.completion_date.like(search_term)
                )
            )
        for column, filter_value in active_column_filters.items():
            if filter_value:
                filter_term = f"%{filter_value}%"
                if column == 'id':
                    query = query.filter(Order.id.cast(String).like(filter_term))
                elif column == 'payment_amount':
                    query = query.filter(Order.payment_amount.cast(String).like(filter_term))
                elif hasattr(Order, column):
                    query = query.filter(getattr(Order, column).like(filter_term))

        query = query.order_by(Order.id.desc())
        total_orders = query.count()
        orders_from_db = query.offset((page - 1) * per_page).limit(per_page).all()

        processed_orders = []
        for order_db_item in orders_from_db:
            order_display_data = copy.deepcopy(order_db_item)
            order_display_data.display_options = format_options_for_display(order_db_item.options)
            if order_db_item.is_erp_order and order_db_item.structured_data:  # type: ignore
                sd = _ensure_dict(order_db_item.structured_data)
                customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
                if customer_name:
                    setattr(order_display_data, 'customer_name', customer_name)
                phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
                if phone:
                    setattr(order_display_data, 'phone', phone)
                address = ((sd.get('site') or {}).get('address_full') or (sd.get('site') or {}).get('address_main'))
                if address:
                    setattr(order_display_data, 'address', address)
                items = sd.get('items') or []
                if items:
                    first_item = items[0]
                    product_name = first_item.get('product_name') or first_item.get('name')
                    if product_name:
                        setattr(order_display_data, 'product', f"{product_name} 외 {len(items) - 1}개" if len(items) > 1 else product_name)
                measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if measurement_date:
                    setattr(order_display_data, 'measurement_date', measurement_date)
                measurement_time = (((sd.get('schedule') or {}).get('measurement') or {}).get('time'))
                if measurement_time:
                    setattr(order_display_data, 'measurement_time', measurement_time)
                construction_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
                if construction_date:
                    setattr(order_display_data, 'scheduled_date', construction_date)
                manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
                if manager_name:
                    setattr(order_display_data, 'manager_name', manager_name)
                orderer_name = ((sd.get('parties') or {}).get('orderer') or {}).get('name')
                if orderer_name:
                    setattr(order_display_data, 'orderer_name', str(orderer_name).strip())
                pa = erp_deposit_amount_from_structured(sd)
                if pa is not None:
                    setattr(order_display_data, 'payment_amount', pa)
            else:
                orderer_name = _extract_orderer_from_options(order_db_item.options)
                if orderer_name:
                    setattr(order_display_data, 'orderer_name', orderer_name)
            processed_orders.append(order_display_data)

        user = get_user_by_id(session['user_id']) if 'user_id' in session else None
        parent = gnav_orders_layout_parent()
        html = render_template(
            'orders/index.html',
            orders=processed_orders,
            status_list=STATUS,
            STATUS=STATUS,
            current_status=effective_status_filter,
            search_query=search_query,
            sort_column='id',
            sort_direction='desc',
            page=page,
            per_page=per_page,
            total_orders=total_orders,
            active_column_filters=column_filters,
            user=user,
            current_region=effective_region_filter,
            parent_template=parent,
        )
        resp = make_response(html)
        if wants_gnav_fragment():
            resp.headers['X-FOMS-GNAV-FRAGMENT'] = '1'
        return resp
    except UnicodeDecodeError as e:
        print(f"Index 페이지 로딩 중 인코딩 오류: {str(e)}")
        flash('데이터베이스 연결 중 인코딩 문제가 발생했습니다. 관리자에게 문의하세요.', 'error')
        parent = gnav_orders_layout_parent()
        html = render_template(
            'orders/index.html', orders=[], status_list=STATUS, STATUS=STATUS,
            current_status=None, search_query='', sort_column='id', sort_direction='desc',
            page=1, per_page=100, total_orders=0, active_column_filters={},
            user=None, current_region=None, parent_template=parent,
        )
        resp = make_response(html)
        if wants_gnav_fragment():
            resp.headers['X-FOMS-GNAV-FRAGMENT'] = '1'
        return resp
    except Exception as e:
        print(f"Index 페이지 로딩 중 오류: {str(e)}")
        try:
            current_app.logger.exception("Index 페이지 로딩 실패: %s", e)
        except Exception:
            pass  # failopen: intentional: 로거 호출 실패 무시 (이미 print로 관측)
        if 'user_id' in session:
            # 인증/세션 불일치 상태에서 / <-> /login 루프를 방지한다.
            session.clear()
        flash('페이지 로딩 중 오류가 발생했습니다. 다시 로그인해주세요.', 'error')
        return redirect(url_for('auth.login'))


@order_pages_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def add_order():
    """주문 추가 페이지."""
    if request.method == 'GET':
        _legacy_open = redirect_if_legacy_open_erp_beta('order_pages.add_order')
        if _legacy_open is not None:
            return _legacy_open
    if request.method == 'POST':
        db = None
        try:
            db = get_db()
            create_mode = (request.form.get('create_mode') or 'LEGACY').upper().strip()

            if create_mode == 'ERP_ORDER':
                raw_text = (request.form.get('raw_order_text') or '').strip()
                structured_json = (request.form.get('structured_data_json') or '').strip()
                stage = (request.form.get('erp_stage') or 'RECEIVED').strip()
                owner_team = (request.form.get('erp_owner_team') or '').strip()
                urgent = bool(request.form.get('erp_urgent') == '1')
                urgent_reason = (request.form.get('erp_urgent_reason') or '').strip()
                meas_date = (request.form.get('erp_measurement_date') or '').strip()
                cons_date = (request.form.get('erp_construction_date') or '').strip()

                structured_data = {}
                if structured_json:
                    try:
                        parsed = json.loads(structured_json)
                        if isinstance(parsed, dict):
                            structured_data = parsed
                    except Exception as exc:
                        current_app.logger.warning("ERP Order structured_data_json parse failed: %s", exc, exc_info=True)
                        flash('ERP Order 데이터 형식이 올바르지 않습니다.', 'error')
                        return redirect(url_for('order_pages.add_order'))

                structured_data.setdefault('workflow', {})
                structured_data['workflow']['stage'] = stage or 'RECEIVED'
                structured_data['workflow']['stage_updated_at'] = now_utc_naive().isoformat()
                structured_data.setdefault('assignments', {})
                if owner_team:
                    structured_data['assignments']['owner_team'] = owner_team
                structured_data.setdefault('flags', {})
                if urgent:
                    structured_data['flags']['urgent'] = True
                    if urgent_reason:
                        structured_data['flags']['urgent_reason'] = urgent_reason
                structured_data.setdefault('schedule', {})
                if meas_date:
                    structured_data['schedule'].setdefault('measurement', {})
                    structured_data['schedule']['measurement']['date'] = meas_date
                if cons_date:
                    structured_data['schedule'].setdefault('construction', {})
                    structured_data['schedule']['construction']['date'] = cons_date

                cust_name = (((structured_data.get('parties') or {}).get('customer') or {}).get('name') or (request.form.get('erp_customer_name') or '')).strip()
                cust_phone = (((structured_data.get('parties') or {}).get('customer') or {}).get('phone') or (request.form.get('erp_customer_phone') or '')).strip()
                addr = (((structured_data.get('site') or {}).get('address_full') or (structured_data.get('site') or {}).get('address_main')) or (request.form.get('erp_address') or '')).strip()
                prod = (_first_product_name_from_structured_data(structured_data) or (request.form.get('erp_product') or '')).strip()

                missing = []
                if not cust_name or cust_name == ERP_DRAFT_PLACEHOLDER_CUSTOMER:
                    missing.append('고객명')
                if not cust_phone or cust_phone == ERP_DRAFT_PLACEHOLDER_PHONE:
                    missing.append('전화번호')
                if not addr or addr == '-':
                    missing.append('주소')
                if not prod or prod == ERP_DRAFT_PLACEHOLDER_PRODUCT:
                    missing.append('제품명')
                if missing:
                    flash(f"필수 항목을 입력해주세요: {', '.join(missing)}", 'error')
                    return redirect(url_for('order_pages.add_order'))

                actor = get_user_by_id(session.get('user_id'))
                owner_user_id = resolve_order_owner(
                    db, actor=actor,
                    requested_owner_user_id=_form_owner_user_id(request.form),
                )
                create_order(
                    db,
                    actor_user_id=actor.id,
                    owner_user_id=owner_user_id,
                    order_fields=dict(
                        received_date=request.form.get('received_date') or get_today_kst().strftime('%Y-%m-%d'),
                        received_time=request.form.get('received_time') or now_kst().strftime('%H:%M'),
                        customer_name=cust_name, phone=cust_phone, address=addr, product=prod,
                        options=None, notes=request.form.get('notes') or None, status='RECEIVED',
                        raw_order_text=raw_text, structured_confidence=None,
                    ),
                    structured_data=structured_data,
                    is_erp_order=True,
                )
                db.commit()
                flash('ERP Order 주문이 성공적으로 추가되었습니다.', 'success')
                return redirect(url_for('order_pages.index'))

            required_fields = ['customer_name', 'phone', 'address', 'product']
            for field in required_fields:
                if not request.form.get(field):
                    flash(f'{field} 필드는 필수입니다.', 'error')
                    return redirect(url_for('order_pages.add_order'))

            option_type = request.form.get('option_type')
            if option_type == 'direct':
                options_data = json.dumps({
                    'product_name': request.form.get('direct_product_name'),
                    'standard': request.form.get('direct_standard'),
                    'internal': request.form.get('direct_internal'),
                    'color': request.form.get('direct_color'),
                    'option_detail': request.form.get('direct_option_detail'),
                    'handle': request.form.get('direct_handle'),
                    'misc': request.form.get('direct_misc'),
                    'quote': request.form.get('direct_quote')
                }, ensure_ascii=False)
            else:
                options_data = request.form.get('options_online')

            payment_amount_str = (request.form.get('payment_amount') or '').replace(',', '')
            try:
                payment_amount = int(payment_amount_str) if payment_amount_str else 0
            except ValueError:
                flash('결제금액은 숫자만 입력해주세요.', 'error')
                return render_template('orders/add_order.html', today=get_today_kst().strftime('%Y-%m-%d'), current_time=now_kst().strftime('%H:%M'))

            is_regional_val = 'is_regional' in request.form
            is_self_measurement_val = 'is_self_measurement' in request.form
            is_cabinet_val = 'is_cabinet' in request.form
            measurement_completed_val = regional_sales_order_upload_val = regional_blueprint_sent_val = regional_order_upload_val = False
            construction_type_val = None
            if is_regional_val:
                measurement_completed_val = 'measurement_completed' in request.form
                regional_sales_order_upload_val = 'regional_sales_order_upload' in request.form
                regional_blueprint_sent_val = 'regional_blueprint_sent' in request.form
                regional_order_upload_val = 'regional_order_upload' in request.form
                construction_type_val = request.form.get('construction_type')

            actor = get_user_by_id(session.get('user_id'))
            owner_user_id = resolve_order_owner(
                db, actor=actor,
                requested_owner_user_id=_form_owner_user_id(request.form),
            )
            new_order = create_order(
                db,
                actor_user_id=actor.id,
                owner_user_id=owner_user_id,
                order_fields=dict(
                    received_date=request.form.get('received_date'),
                    received_time=request.form.get('received_time'),
                    customer_name=request.form.get('customer_name'),
                    phone=request.form.get('phone'),
                    address=request.form.get('address'),
                    product=request.form.get('product'),
                    options=options_data,
                    notes=request.form.get('notes'),
                    status=request.form.get('status', 'RECEIVED'),
                    measurement_date=request.form.get('measurement_date'),
                    measurement_time=request.form.get('measurement_time'),
                    completion_date=request.form.get('completion_date'),
                    manager_name=request.form.get('manager_name'),
                    payment_amount=payment_amount,
                    scheduled_date=request.form.get('scheduled_date'),
                    as_received_date=request.form.get('as_received_date'),
                    as_completed_date=request.form.get('as_completed_date'),
                    is_regional=is_regional_val,
                    is_self_measurement=is_self_measurement_val,
                    is_cabinet=is_cabinet_val,
                    cabinet_status='RECEIVED' if is_cabinet_val else None,
                    measurement_completed=measurement_completed_val,
                    regional_sales_order_upload=regional_sales_order_upload_val,
                    regional_blueprint_sent=regional_blueprint_sent_val,
                    regional_order_upload=regional_order_upload_val,
                    construction_type=construction_type_val,
                ),
                is_erp_order=False,
            )
            order_id_for_log = new_order.id
            customer_name_for_log = new_order.customer_name
            user_name_for_log = actor.name if actor else "Unknown user"
            db.commit()
            log_access(f"주문 #{order_id_for_log} ({customer_name_for_log}) 추가 - 담당자: {user_name_for_log}", session.get('user_id'))
            flash('주문이 성공적으로 추가되었습니다.', 'success')
            return redirect(url_for('order_pages.index'))

        except Exception as e:
            if db is not None:
                db.rollback()
            flash(f'오류가 발생했습니다: {str(e)}', 'error')
            return redirect(url_for('order_pages.add_order'))

    today = get_today_kst().strftime('%Y-%m-%d')
    current_time = now_kst().strftime('%H:%M')
    _uid_raw = session.get('user_id')
    _uid = int(_uid_raw) if _uid_raw is not None else None
    # 모바일 v2 코호트·FAB·휴대폰 UA만 wizard; PC 브라우저는 데스크톱 add_order 탭.
    if should_render_new_order_wizard(_uid, request):
        import uuid

        draft_key = (request.args.get('key') or '').strip() or f"new.{uuid.uuid4().hex[:16]}"
        try:
            initial_step = max(1, min(4, int(request.args.get('step') or 1)))
        except (TypeError, ValueError):
            initial_step = 1
        # 담당 드롭다운: 영업담당 = 영업팀(SALES) + 관리자(ADMIN), 시공담당 = 시공팀(CONSTRUCTION).
        wizard_sales_staff = []
        wizard_construction_staff = []
        try:
            _rows = (
                get_db()
                .query(User.name, User.team, User.role)
                .filter(User.is_active.is_(True))
                .order_by(User.name)
                .all()
            )
            _seen_sales = set()
            _seen_cons = set()
            for _name, _team, _role in _rows:
                _nm = (_name or '').strip()
                if not _nm:
                    continue
                if (_team == 'SALES' or _role == 'ADMIN') and _nm not in _seen_sales:
                    _seen_sales.add(_nm)
                    wizard_sales_staff.append(_nm)
                if _team == 'CONSTRUCTION' and _nm not in _seen_cons:
                    _seen_cons.add(_nm)
                    wizard_construction_staff.append(_nm)
        except Exception:
            wizard_sales_staff = []
            wizard_construction_staff = []
        return render_template(
            'orders/wizard/wizard_shell.html',
            today=today,
            current_time=current_time,
            draft_key=draft_key,
            initial_step=initial_step,
            wizard_sales_staff=wizard_sales_staff,
            wizard_construction_staff=wizard_construction_staff,
        )
    return render_template('orders/add_order.html', today=today, current_time=current_time)


@order_pages_bp.route('/bulk_action', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER'])
def bulk_action():
    """선택된 주문에 대한 일괄 작업 (삭제/복사/상태 변경)."""
    action = request.form.get('action')
    selected_ids = request.form.getlist('selected_order')

    if not selected_ids:
        flash('작업할 주문을 선택해주세요.', 'warning')
        redirect_args = get_preserved_filter_args(request.args)
        return redirect(url_for('order_pages.index', **redirect_args))

    if not action:
        flash('수행할 작업을 선택해주세요.', 'warning')
        redirect_args = get_preserved_filter_args(request.args)
        return redirect(url_for('order_pages.index', **redirect_args))

    db = None
    current_user_id = session.get('user_id')
    processed_count = 0
    failed_count = 0

    try:
        db = get_db()
        if action == 'delete':
            order_ids = [int(order_id) for order_id in selected_ids]
            orders_by_id = {
                order.id: order
                for order in db.query(Order).filter(Order.id.in_(order_ids), Order.active_filter()).all()  # perf-ok
            }
            for order_id in selected_ids:
                order = orders_by_id.get(int(order_id))
                if order:
                    original_status = getattr(order, 'status', None)
                    deleted_at = now_kst().strftime('%Y-%m-%d %H:%M:%S')
                    setattr(order, 'status', 'DELETED')
                    setattr(order, 'original_status', original_status)
                    setattr(order, 'deleted_at', deleted_at)
                    log_access(f"주문 #{order_id} 삭제 (일괄 작업)", current_user_id, {"order_id": order_id})
                    processed_count += 1
                else:
                    failed_count += 1

        elif action == 'copy':
            # ORDER-COPY-01: raw Order() column clone 제거 → create_order 경유 fresh
            # identity(all-or-none). 하나라도 없거나 owner 정책 위반이면 전체 abort.
            actor = get_user_by_id(current_user_id)
            try:
                copied = copy_orders_batch(
                    db,
                    actor=actor,
                    order_ids=[int(order_id) for order_id in selected_ids],
                    requested_owner_user_id=_form_owner_user_id(request.form),
                )
            except (OrderCopyError, OrderCreateError) as copy_exc:
                db.rollback()
                flash(str(copy_exc), 'error')
                redirect_args = get_preserved_filter_args(request.args)
                return redirect(url_for('order_pages.index', **redirect_args))
            for original_id, new_order in copied:
                log_access(
                    f"주문 #{original_id}를 새 주문 #{new_order.id}로 복사 (일괄 작업)",
                    current_user_id,
                    {"original_order_id": original_id, "new_order_id": new_order.id},
                )
                processed_count += 1

        elif action.startswith('status_'):
            new_status = action.split('_', 1)[1]
            if new_status in STATUS:
                order_ids = [int(order_id) for order_id in selected_ids]
                orders_by_id = {
                    order.id: order
                    for order in db.query(Order).filter(Order.id.in_(order_ids), Order.active_filter()).all()  # perf-ok
                }
                for order_id in selected_ids:
                    order = orders_by_id.get(int(order_id))
                    old_status_val = getattr(order, 'status', None) if order is not None else None
                    if order is not None and old_status_val != new_status:
                        setattr(order, 'status', new_status)
                        # AS 접수(AS_RECEIVED)로 바꿀 때도 scheduled_date(AS 방문일) 자동 입력하지 않음
                        bulk_context = order_audit_context(order)
                        log_access(
                            describe_field_change(
                                order_id=order_id, field="status", before=old_status_val,
                                after=new_status, has_before=True, **bulk_context,
                            ) + " (일괄 작업)",
                            current_user_id,
                            action="ORDER_STATUS_CHANGED", target_type="order", target_id=int(order_id),
                            detail={"field": "status", "before": old_status_val,
                                    "after": new_status, "bulk": True, **bulk_context},
                        )
                        processed_count += 1
                    elif not order:
                        failed_count += 1
            else:
                flash("'" + new_status + "'" + '는 유효하지 않은 상태입니다.', 'error')
                redirect_args = get_preserved_filter_args(request.args)
                return redirect(url_for('order_pages.index', **redirect_args))

        db.commit()

        if action.startswith('status_'):
            status_code = action.split('_', 1)[1]
            status_name = STATUS.get(status_code, status_code)
            action_display_name = f"상태를 '{status_name}'(으)로 변경"
        elif action == 'copy':
            action_display_name = "'복사'"
        elif action == 'delete':
            action_display_name = "'삭제'"
        else:
            action_display_name = f"\'{action}\'"

        success_msg = f"{processed_count}개의 주문에 대해 {action_display_name} 작업을 완료했습니다."
        if failed_count > 0:
            warning_msg = f"{failed_count}개의 주문은 처리할 수 없었습니다 (이미 삭제되었거나 존재하지 않음)."
            flash(warning_msg, 'warning')
        if processed_count > 0:
            flash(success_msg, 'success')
        elif failed_count == len(selected_ids):
            flash('선택한 주문을 처리할 수 없습니다.', 'error')
        else:
            flash('변경된 사항이 없습니다.', 'info')

    except Exception as e:
        if db:
            db.rollback()
        flash(f'일괄 작업 중 오류 발생: {str(e)}', 'error')
        current_app.logger.error(f"일괄 작업 실패: {e}", exc_info=True)

    redirect_args = get_preserved_filter_args(request.args)
    return redirect(url_for('order_pages.index', **redirect_args))
