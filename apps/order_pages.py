"""주문 페이지 Blueprint: index, add_order, bulk_action, edit_order."""
import copy
import json
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from sqlalchemy import or_, String

from apps.auth import login_required, role_required, log_access
from apps.auth import get_user_by_id
from apps.erp import can_edit_erp
from db import get_db
from models import Order
from constants import STATUS
from services.order_display_utils import format_options_for_display, _ensure_dict
from services.request_utils import get_preserved_filter_args

order_pages_bp = Blueprint('order_pages', __name__, url_prefix='')


@order_pages_bp.route('/')
@login_required
def index():
    """메인 주문 목록 페이지."""
    try:
        db = get_db()
        status_filter = request.args.get('status')
        region_filter = request.args.get('region')
        search_query = request.args.get('search', '').strip()
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

        query = db.query(Order).filter(Order.status != 'DELETED')
        if status_filter and status_filter != 'ALL':
            query = query.filter(Order.status == status_filter)
        if region_filter == 'metro':
            query = query.filter(Order.is_regional == False)
        elif region_filter == 'regional':
            query = query.filter(Order.is_regional == True)
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    Order.id.cast(String).like(search_term),
                    Order.received_date.like(search_term),
                    Order.received_time.like(search_term),
                    Order.customer_name.like(search_term),
                    Order.phone.like(search_term),
                    Order.address.like(search_term),
                    Order.product.like(search_term),
                    Order.options.like(search_term),
                    Order.notes.like(search_term),
                    Order.status.like(search_term),
                    Order.measurement_date.like(search_term),
                    Order.measurement_time.like(search_term),
                    Order.scheduled_date.like(search_term),
                    Order.completion_date.like(search_term),
                    Order.manager_name.like(search_term)
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
            if order_db_item.is_erp_beta and order_db_item.structured_data:
                sd = _ensure_dict(order_db_item.structured_data)
                customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
                if customer_name:
                    order_display_data.customer_name = customer_name
                phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
                if phone:
                    order_display_data.phone = phone
                address = ((sd.get('site') or {}).get('address_full') or (sd.get('site') or {}).get('address_main'))
                if address:
                    order_display_data.address = address
                items = sd.get('items') or []
                if items:
                    first_item = items[0]
                    product_name = first_item.get('product_name') or first_item.get('name')
                    if product_name:
                        order_display_data.product = f"{product_name} 외 {len(items) - 1}개" if len(items) > 1 else product_name
                measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if measurement_date:
                    order_display_data.measurement_date = measurement_date
                measurement_time = (((sd.get('schedule') or {}).get('measurement') or {}).get('time'))
                if measurement_time:
                    order_display_data.measurement_time = measurement_time
                construction_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
                if construction_date:
                    order_display_data.scheduled_date = construction_date
                manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
                if manager_name:
                    order_display_data.manager_name = manager_name
            processed_orders.append(order_display_data)

        user = get_user_by_id(session['user_id']) if 'user_id' in session else None
        return render_template(
            'index.html',
            orders=processed_orders,
            status_list=STATUS,
            STATUS=STATUS,
            current_status=status_filter,
            search_query=search_query,
            sort_column='id',
            sort_direction='desc',
            page=page,
            per_page=per_page,
            total_orders=total_orders,
            active_column_filters=column_filters,
            user=user,
            current_region=region_filter
        )
    except UnicodeDecodeError as e:
        print(f"Index 페이지 로딩 중 인코딩 오류: {str(e)}")
        flash('데이터베이스 연결 중 인코딩 문제가 발생했습니다. 관리자에게 문의하세요.', 'error')
        return render_template(
            'index.html', orders=[], status_list=STATUS, STATUS=STATUS,
            current_status=None, search_query='', sort_column='id', sort_direction='desc',
            page=1, per_page=100, total_orders=0, active_column_filters={},
            user=None, current_region=None
        )
    except Exception as e:
        print(f"Index 페이지 로딩 중 오류: {str(e)}")
        flash('페이지 로딩 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('auth.login'))


@order_pages_bp.route('/add', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def add_order():
    """주문 추가 페이지."""
    if request.method == 'POST':
        try:
            db = get_db()
            create_mode = (request.form.get('create_mode') or 'LEGACY').upper().strip()

            if create_mode == 'ERP_BETA':
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
                    except Exception:
                        pass

                structured_data.setdefault('workflow', {})
                structured_data['workflow']['stage'] = stage or 'RECEIVED'
                structured_data['workflow']['stage_updated_at'] = datetime.datetime.now().isoformat()
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

                cust_name = ((structured_data.get('parties') or {}).get('customer') or {}).get('name') or (request.form.get('erp_customer_name') or '').strip() or 'ERP Beta'
                cust_phone = ((structured_data.get('parties') or {}).get('customer') or {}).get('phone') or (request.form.get('erp_customer_phone') or '').strip() or '000-0000-0000'
                addr = ((structured_data.get('site') or {}).get('address_full') or (structured_data.get('site') or {}).get('address_main')) or (request.form.get('erp_address') or '').strip() or '-'
                prod = (request.form.get('erp_product') or '').strip() or 'ERP Beta'

                new_order = Order(
                    received_date=request.form.get('received_date') or datetime.datetime.now().strftime('%Y-%m-%d'),
                    received_time=request.form.get('received_time') or datetime.datetime.now().strftime('%H:%M'),
                    customer_name=cust_name, phone=cust_phone, address=addr, product=prod,
                    options=None, notes=request.form.get('notes') or None, status='RECEIVED',
                    is_erp_beta=True, raw_order_text=raw_text, structured_data=structured_data,
                    structured_schema_version=1, structured_confidence=None, structured_updated_at=datetime.datetime.now(),
                )
                db.add(new_order)
                db.flush()
                db.commit()
                flash('ERP Beta 주문이 성공적으로 추가되었습니다.', 'success')
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
                return render_template('add_order.html', today=datetime.datetime.now().strftime('%Y-%m-%d'), current_time=datetime.datetime.now().strftime('%H:%M'))

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

            new_order = Order(
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
                is_erp_beta=False,
            )
            db.add(new_order)
            db.flush()
            order_id_for_log = new_order.id
            customer_name_for_log = new_order.customer_name
            user_for_log = get_user_by_id(session.get('user_id'))
            user_name_for_log = user_for_log.name if user_for_log else "Unknown user"
            db.commit()
            log_access(f"주문 #{order_id_for_log} ({customer_name_for_log}) 추가 - 담당자: {user_name_for_log}", session.get('user_id'))
            flash('주문이 성공적으로 추가되었습니다.', 'success')
            return redirect(url_for('order_pages.index'))

        except Exception as e:
            db.rollback()
            flash(f'오류가 발생했습니다: {str(e)}', 'error')
            return redirect(url_for('order_pages.add_order'))

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.datetime.now().strftime('%H:%M')
    return render_template('add_order.html', today=today, current_time=current_time)


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
            for order_id in selected_ids:
                order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
                if order:
                    original_status = order.status
                    deleted_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    order.status = 'DELETED'
                    order.original_status = original_status
                    order.deleted_at = deleted_at
                    log_access(f"주문 #{order_id} 삭제 (일괄 작업)", current_user_id, {"order_id": order_id})
                    processed_count += 1
                else:
                    failed_count += 1

        elif action == 'copy':
            now = datetime.datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M')

            for order_id in selected_ids:
                original_order = db.query(Order).filter(Order.id == order_id).first()
                if original_order:
                    copied_order = Order()
                    for column in Order.__table__.columns:
                        col_name = column.name
                        if col_name not in ['id', 'status', 'received_date', 'received_time',
                                            'customer_name', 'notes', 'measurement_date', 'measurement_time',
                                            'completion_date', 'original_status', 'deleted_at']:
                            setattr(copied_order, col_name, getattr(original_order, col_name))
                    copied_order.status = 'RECEIVED'
                    copied_order.received_date = today_str
                    copied_order.received_time = time_str
                    copied_order.customer_name = f"[복사: 원본 #{original_order.id}] {original_order.customer_name}"
                    original_notes = original_order.notes or ""
                    copied_order.notes = f"원본 주문 #{original_order.id} 에서 복사됨.\n---\n" + original_notes
                    copied_order.measurement_date = None
                    copied_order.measurement_time = None
                    copied_order.completion_date = None
                    db.add(copied_order)
                    db.flush()
                    log_access(f"주문 #{original_order.id}를 새 주문 #{copied_order.id}로 복사 (일괄 작업)",
                               current_user_id, {"original_order_id": original_order.id, "new_order_id": copied_order.id})
                    processed_count += 1
                else:
                    failed_count += 1

        elif action.startswith('status_'):
            new_status = action.split('_', 1)[1]
            if new_status in STATUS:
                for order_id in selected_ids:
                    order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
                    if order and order.status != new_status:
                        old_status = order.status
                        order.status = new_status
                        old_status_kr = STATUS.get(old_status, old_status)
                        new_status_kr = STATUS.get(new_status, new_status)
                        log_access(f"주문 #{order_id} 상태 변경: {old_status_kr} => {new_status_kr} (일괄 작업)",
                                   current_user_id, {"order_id": order_id, "old_status": old_status, "new_status": new_status})
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


@order_pages_bp.route('/edit/<int:order_id>', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def edit_order(order_id):
    """주문 수정 페이지."""
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()

    if not order:
        flash('주문을 찾을 수 없거나 이미 삭제되었습니다.', 'error')
        return redirect(url_for('order_pages.index'))

    if order.is_erp_beta:
        user = get_user_by_id(session['user_id'])
        if not can_edit_erp(user):
            flash('ERP Beta 주문 수정 권한이 없습니다. (관리자, CS, 영업팀만 가능)', 'error')
            return redirect(url_for('order_pages.index'))

    option_type = 'online'
    online_options = ""
    direct_options = {
        'product_name': '', 'standard': '', 'internal': '', 'color': '',
        'option_detail': '', 'handle': '', 'misc': '', 'quote': ''
    }

    if order.options:
        try:
            options_data = json.loads(order.options)
            if isinstance(options_data, dict):
                if 'option_type' in options_data:
                    option_type = options_data['option_type']
                    if option_type == 'direct' and 'details' in options_data:
                        for key in direct_options:
                            if key in options_data['details']:
                                direct_options[key] = options_data['details'][key]
                    elif option_type == 'online' and 'online_options_summary' in options_data:
                        online_options = options_data['online_options_summary']
                elif any(k in options_data for k in direct_options):
                    option_type = 'direct'
                    for key in direct_options:
                        if key in options_data:
                            direct_options[key] = options_data[key]
                elif any(k in options_data for k in ['제품명', '규격', '내부', '색상', '상세옵션', '손잡이', '기타', '견적내용']):
                    option_type = 'direct'
                    key_map = {'제품명': 'product_name', '규격': 'standard', '내부': 'internal', '색상': 'color',
                               '상세옵션': 'option_detail', '손잡이': 'handle', '기타': 'misc', '견적내용': 'quote'}
                    for k_kor, k_eng in key_map.items():
                        if k_kor in options_data:
                            direct_options[k_eng] = options_data[k_kor]
                else:
                    option_type = 'online'
                    online_options = order.options or ""
            else:
                option_type = 'online'
                online_options = order.options or ""
        except json.JSONDecodeError:
            option_type = 'online'
            online_options = order.options if order.options else ""

    if request.method == 'POST':
        try:
            received_date = request.form.get('received_date', order.received_date)
            received_time = request.form.get('received_time', order.received_time)
            customer_name = request.form.get('customer_name', order.customer_name)
            phone = request.form.get('phone', order.phone)
            address = request.form.get('address', order.address)
            product = request.form.get('product', order.product)
            notes = request.form.get('notes', order.notes)
            status = request.form.get('status', order.status)
            measurement_date = request.form.get('measurement_date', order.measurement_date)
            measurement_time = request.form.get('measurement_time', order.measurement_time)
            completion_date = request.form.get('completion_date', order.completion_date)
            manager_name = request.form.get('manager_name', order.manager_name)
            scheduled_date = request.form.get('scheduled_date', order.scheduled_date)
            as_received_date = request.form.get('as_received_date', order.as_received_date)
            as_completed_date = request.form.get('as_completed_date', order.as_completed_date)
            shipping_scheduled_date = request.form.get('shipping_scheduled_date', order.shipping_scheduled_date)

            options_data_json_to_save = order.options
            if 'option_type' in request.form:
                ct = request.form.get('option_type')
                if ct == 'direct':
                    options_data_json_to_save = json.dumps({
                        "option_type": "direct",
                        "details": {
                            'product_name': request.form.get('direct_product_name', ''),
                            'standard': request.form.get('direct_standard', ''),
                            'internal': request.form.get('direct_internal', ''),
                            'color': request.form.get('direct_color', ''),
                            'option_detail': request.form.get('direct_option_detail', ''),
                            'handle': request.form.get('direct_handle', ''),
                            'misc': request.form.get('direct_misc', ''),
                            'quote': request.form.get('direct_quote', '')
                        }
                    }, ensure_ascii=False)
                else:
                    options_data_json_to_save = json.dumps({
                        "option_type": "online",
                        "online_options_summary": request.form.get('options_online', '')
                    }, ensure_ascii=False)

            changes = {}
            if order.received_date != received_date: changes['received_date'] = {'old': order.received_date, 'new': received_date}
            if order.received_time != received_time: changes['received_time'] = {'old': order.received_time, 'new': received_time}
            if order.customer_name != customer_name: changes['customer_name'] = {'old': order.customer_name, 'new': customer_name}
            if order.phone != phone: changes['phone'] = {'old': order.phone, 'new': phone}
            if order.address != address: changes['address'] = {'old': order.address, 'new': address}
            if order.product != product: changes['product'] = {'old': order.product, 'new': product}
            if order.options != options_data_json_to_save: changes['options'] = {'old': order.options, 'new': options_data_json_to_save}
            if order.notes != notes: changes['notes'] = {'old': order.notes, 'new': notes}
            if order.status != status: changes['status'] = {'old': order.status, 'new': status}
            if order.measurement_date != measurement_date: changes['measurement_date'] = {'old': order.measurement_date, 'new': measurement_date}
            if order.measurement_time != measurement_time: changes['measurement_time'] = {'old': order.measurement_time, 'new': measurement_time}
            if order.completion_date != completion_date: changes['completion_date'] = {'old': order.completion_date, 'new': completion_date}
            if order.manager_name != manager_name: changes['manager_name'] = {'old': order.manager_name, 'new': manager_name}
            if order.scheduled_date != scheduled_date: changes['scheduled_date'] = {'old': order.scheduled_date, 'new': scheduled_date}
            if order.as_received_date != as_received_date: changes['as_received_date'] = {'old': order.as_received_date, 'new': as_received_date}
            if order.as_completed_date != as_completed_date: changes['as_completed_date'] = {'old': order.as_completed_date, 'new': as_completed_date}
            if order.shipping_scheduled_date != shipping_scheduled_date: changes['shipping_scheduled_date'] = {'old': order.shipping_scheduled_date, 'new': shipping_scheduled_date}
            is_regional_new = 'is_regional' in request.form
            if order.is_regional != is_regional_new: changes['is_regional'] = {'old': order.is_regional, 'new': is_regional_new}
            is_self_measurement_new = 'is_self_measurement' in request.form
            if order.is_self_measurement != is_self_measurement_new: changes['is_self_measurement'] = {'old': order.is_self_measurement, 'new': is_self_measurement_new}
            measurement_completed_new = 'measurement_completed' in request.form
            if order.measurement_completed != measurement_completed_new: changes['measurement_completed'] = {'old': order.measurement_completed, 'new': measurement_completed_new}
            construction_type_new = request.form.get('construction_type', order.construction_type)
            if order.construction_type != construction_type_new: changes['construction_type'] = {'old': order.construction_type, 'new': construction_type_new}
            new_payment_amount = order.payment_amount
            if 'payment_amount' in request.form:
                pa_str = request.form.get('payment_amount', '').replace(',', '')
                if pa_str:
                    try:
                        new_payment_amount = int(pa_str)
                    except ValueError:
                        flash('결제금액은 숫자만 입력해주세요.', 'error')
                        raise ValueError("Invalid payment amount")
                else:
                    new_payment_amount = 0
            if order.payment_amount != new_payment_amount: changes['payment_amount'] = {'old': order.payment_amount, 'new': new_payment_amount}

            order.received_date = received_date
            order.received_time = received_time
            order.customer_name = customer_name
            order.phone = phone
            order.address = address
            order.product = product
            order.options = options_data_json_to_save
            order.notes = notes
            order.status = status
            order.measurement_date = measurement_date
            order.measurement_time = measurement_time
            order.completion_date = completion_date
            order.manager_name = manager_name
            order.scheduled_date = scheduled_date
            order.as_received_date = as_received_date
            order.as_completed_date = as_completed_date
            order.shipping_scheduled_date = shipping_scheduled_date
            order.payment_amount = new_payment_amount
            order.is_regional = is_regional_new
            order.is_self_measurement = is_self_measurement_new
            is_cabinet_new = 'is_cabinet' in request.form
            if order.is_cabinet != is_cabinet_new: changes['is_cabinet'] = {'old': order.is_cabinet, 'new': is_cabinet_new}
            order.is_cabinet = is_cabinet_new
            if is_cabinet_new and not order.cabinet_status:
                order.cabinet_status = 'RECEIVED'
            elif not is_cabinet_new:
                order.cabinet_status = None
            order.construction_type = construction_type_new
            if order.is_regional:
                for f in ['measurement_completed', 'regional_sales_order_upload', 'regional_blueprint_sent',
                          'regional_order_upload', 'regional_cargo_sent', 'regional_construction_info_sent']:
                    setattr(order, f, f in request.form)
            db.commit()

            field_labels = {
                'received_date': '접수일', 'received_time': '접수시간', 'customer_name': '고객명', 'phone': '전화번호',
                'address': '주소', 'product': '제품', 'options': '옵션 상세', 'notes': '비고', 'status': '상태',
                'measurement_date': '실측일', 'measurement_time': '실측시간', 'completion_date': '설치완료일',
                'manager_name': '담당자', 'payment_amount': '결제금액', 'is_regional': '지방 주문',
                'is_self_measurement': '자가실측', 'is_cabinet': '수납장', 'measurement_completed': '실측완료',
                'construction_type': '시공 구분', 'regional_sales_order_upload': '영업발주 업로드',
                'regional_blueprint_sent': '도면 발송', 'regional_order_upload': '발주 업로드',
                'regional_cargo_sent': '화물 발송', 'regional_construction_info_sent': '시공정보 발송',
                'shipping_scheduled_date': '상차 예정일'
            }
            change_descriptions = []
            for field, values in changes.items():
                if field not in field_labels:
                    continue
                old_val = values.get('old', '') or '없음'
                new_val = values.get('new', '') or '없음'
                if field == 'options':
                    try:
                        old_json = json.loads(old_val) if old_val != '없음' and old_val else None
                        new_json = json.loads(new_val) if new_val != '없음' and new_val else None
                        if old_json and new_json:
                            oot = old_json.get('option_type', '')
                            not_ = new_json.get('option_type', '')
                            if oot != not_:
                                old_display = (old_json.get('online_options_summary') or (old_json.get('details') or {}).get('product_name') or '옵션') if oot == 'online' else ((old_json.get('details') or {}).get('product_name') or '옵션')
                                new_display = (new_json.get('online_options_summary') or (new_json.get('details') or {}).get('product_name') or '옵션') if not_ == 'online' else ((new_json.get('details') or {}).get('product_name') or '옵션')
                            elif oot == 'online':
                                if old_json.get('online_options_summary') == new_json.get('online_options_summary'):
                                    continue
                                old_display = old_json.get('online_options_summary', '') or '없음'
                                new_display = new_json.get('online_options_summary', '') or '없음'
                            elif oot == 'direct':
                                od, nd = old_json.get('details', {}), new_json.get('details', {})
                                if (od.get('product_name') or '') + (od.get('color') or '') == (nd.get('product_name') or '') + (nd.get('color') or ''):
                                    continue
                                old_display = od.get('product_name') or od.get('color') or '옵션'
                                new_display = nd.get('product_name') or nd.get('color') or '옵션'
                            else:
                                continue
                        elif not old_json and not new_json:
                            continue
                        else:
                            old_display = '없음' if not old_json else (old_json.get('online_options_summary') or (old_json.get('details') or {}).get('product_name') or '옵션')
                            new_display = '없음' if not new_json else (new_json.get('online_options_summary') or (new_json.get('details') or {}).get('product_name') or '옵션')
                    except Exception:
                        if (old_val or '').strip() == (new_val or '').strip():
                            continue
                        old_display, new_display = old_val, new_val
                else:
                    old_display = str(old_val).strip() if old_val != '없음' else '없음'
                    new_display = str(new_val).strip() if new_val != '없음' else '없음'
                    if old_display == new_display:
                        continue
                    if field == 'status':
                        old_display = STATUS.get(old_display, old_display)
                        new_display = STATUS.get(new_display, new_display)
                change_descriptions.append(f"{field_labels[field]}: {old_display} ⇒ {new_display}")

            u = get_user_by_id(session['user_id'])
            uname = u.name if u else "Unknown user"
            prefix = f"주문 #{order_id} ({customer_name}) 수정 - 담당자: {uname} (ID: {session.get('user_id')})"
            log_message = f"{prefix} | 변경내용: {'; '.join(change_descriptions)}" if change_descriptions else f"{prefix} | 변경내용 없음"
            log_access(log_message, session.get('user_id'))
            flash('주문이 성공적으로 수정되었습니다.', 'success')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success'})
            referrer = request.form.get('referrer')
            if referrer:
                from urllib.parse import urlparse
                if urlparse(referrer).netloc == request.host:
                    return redirect(referrer)
            return redirect(url_for('order_pages.index'))
        except ValueError:
            db.rollback()
            flash('입력 데이터 오류가 있습니다.', 'error')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': '입력 데이터 오류'})
        except Exception as e:
            db.rollback()
            flash(f'주문 수정 중 오류가 발생했습니다: {str(e)}', 'error')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': '시스템 오류가 발생했습니다.'})
            return render_template('edit_order.html', order=order, option_type=option_type,
                                  online_options=online_options, direct_options=direct_options)

    preserved_args = get_preserved_filter_args(request.args)
    return render_template('edit_order.html', order=order, option_type=option_type,
                          online_options=online_options, direct_options=direct_options, preserved_args=preserved_args)
