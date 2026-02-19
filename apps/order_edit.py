"""주문 수정 페이지 Blueprint: edit_order (/edit/<order_id>)."""
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify

from apps.auth import login_required, role_required, log_access, get_user_by_id
from services.erp_permissions import can_edit_erp
from db import get_db
from models import Order
from constants import STATUS
from services.request_utils import get_preserved_filter_args

order_edit_bp = Blueprint('order_edit', __name__, url_prefix='')


@order_edit_bp.route('/edit/<int:order_id>', methods=['GET', 'POST'])
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
