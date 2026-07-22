"""주문 수정 페이지 Blueprint (canonical; SFC-B11B): edit_order (/edit/<order_id>)."""
import copy
import json
from flask import (
    Blueprint,
    make_response,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app,
    jsonify,
)
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import login_required, role_required, log_access, get_user_by_id
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_display import _ensure_dict
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_sync_columns import sync_erp_flat_columns
from db import get_db
from models import Order
from foms.services.orders.status_constants import STATUS
from foms.services.erp_order_deeplink import resolve_edit_return_back_endpoint
from foms.services.request_utils import get_preserved_filter_args, redirect_if_legacy_open_erp_beta
from foms.services.order_edit_view_context import build_order_edit_get_context
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.order_geocode import (
    apply_erp_order_site_address_to_sd,
    clear_order_geocode_coords,
    reset_order_geocode_on_address_change,
)

order_edit_bp = Blueprint('order_edit', __name__, url_prefix='')


@order_edit_bp.route('/erp/orders/<int:order_id>')
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def redirect_legacy_erp_order_detail(order_id):
    """Redirect legacy ChannelTalk order links to the actual ERP Order detail page."""
    params = request.args.to_dict()
    params.pop("order_id", None)
    params['open'] = 'erp-order'
    return redirect(url_for('order_edit.edit_order', order_id=order_id, **params))


@order_edit_bp.route('/edit/<int:order_id>', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def edit_order(order_id):
    """주문 수정 페이지."""
    if request.method == 'GET':
        _legacy_open = redirect_if_legacy_open_erp_beta('order_edit.edit_order', order_id=order_id)
        if _legacy_open is not None:
            return _legacy_open
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()

    if not order:
        flash('주문을 찾을 수 없거나 이미 삭제되었습니다.', 'error')
        return redirect(url_for('order_pages.index'))

    if is_erp_order_record(order):
        user = get_user_by_id(session['user_id'])
        if not can_edit_erp(user):
            flash('ERP Order 주문 수정 권한이 없습니다. (관리자, CS, 영업팀만 가능)', 'error')
            return redirect(url_for('order_pages.index'))

    option_type = 'online'
    online_options = ""
    direct_options = {
        'product_name': '', 'standard': '', 'internal': '', 'color': '',
        'option_detail': '', 'handle': '', 'misc': '', 'quote': ''
    }

    _options_raw = getattr(order, 'options', None)
    if _options_raw:
        try:
            options_data = json.loads(str(_options_raw))
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
                    online_options = str(_options_raw or "")
            else:
                option_type = 'online'
                online_options = str(_options_raw or "")
        except json.JSONDecodeError:
            option_type = 'online'
            online_options = str(_options_raw or "") if _options_raw else ""

    if request.method == 'POST':
        try:
            _o = order  # local ref for getattr defaults
            received_date = request.form.get('received_date', getattr(_o, 'received_date', None) or '')
            received_time = request.form.get('received_time', getattr(_o, 'received_time', None) or '')
            customer_name = request.form.get('customer_name', getattr(_o, 'customer_name', None) or '')
            phone = request.form.get('phone', getattr(_o, 'phone', None) or '')
            address = request.form.get('address', getattr(_o, 'address', None) or '')
            product = request.form.get('product', getattr(_o, 'product', None) or '')
            notes = request.form.get('notes', getattr(_o, 'notes', None) or '')
            status = request.form.get('status', getattr(_o, 'status', None) or '')
            measurement_date = request.form.get('measurement_date', getattr(_o, 'measurement_date', None) or '')
            measurement_time = request.form.get('measurement_time', getattr(_o, 'measurement_time', None) or '')
            completion_date = request.form.get('completion_date', getattr(_o, 'completion_date', None) or '')
            manager_name = request.form.get('manager_name', getattr(_o, 'manager_name', None) or '')
            scheduled_date = request.form.get('scheduled_date', getattr(_o, 'scheduled_date', None) or '')
            as_received_date = request.form.get('as_received_date', getattr(_o, 'as_received_date', None) or '')
            as_completed_date = request.form.get('as_completed_date', getattr(_o, 'as_completed_date', None) or '')
            shipping_scheduled_date = request.form.get('shipping_scheduled_date', getattr(_o, 'shipping_scheduled_date', None) or '')

            options_data_json_to_save = getattr(order, 'options', None)
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
            _od = lambda a, d=None: getattr(order, a, d)
            if _od('received_date') != received_date: changes['received_date'] = {'old': _od('received_date'), 'new': received_date}
            if _od('received_time') != received_time: changes['received_time'] = {'old': _od('received_time'), 'new': received_time}
            if _od('customer_name') != customer_name: changes['customer_name'] = {'old': _od('customer_name'), 'new': customer_name}
            if _od('phone') != phone: changes['phone'] = {'old': _od('phone'), 'new': phone}
            if _od('address') != address: changes['address'] = {'old': _od('address'), 'new': address}
            if _od('product') != product: changes['product'] = {'old': _od('product'), 'new': product}
            if _od('options') != options_data_json_to_save: changes['options'] = {'old': _od('options'), 'new': options_data_json_to_save}
            if _od('notes') != notes: changes['notes'] = {'old': _od('notes'), 'new': notes}
            if _od('status') != status: changes['status'] = {'old': _od('status'), 'new': status}
            if _od('measurement_date') != measurement_date: changes['measurement_date'] = {'old': _od('measurement_date'), 'new': measurement_date}
            if _od('measurement_time') != measurement_time: changes['measurement_time'] = {'old': _od('measurement_time'), 'new': measurement_time}
            if _od('completion_date') != completion_date: changes['completion_date'] = {'old': _od('completion_date'), 'new': completion_date}
            if _od('manager_name') != manager_name: changes['manager_name'] = {'old': _od('manager_name'), 'new': manager_name}
            if _od('scheduled_date') != scheduled_date: changes['scheduled_date'] = {'old': _od('scheduled_date'), 'new': scheduled_date}
            if _od('as_received_date') != as_received_date: changes['as_received_date'] = {'old': _od('as_received_date'), 'new': as_received_date}
            if _od('as_completed_date') != as_completed_date: changes['as_completed_date'] = {'old': _od('as_completed_date'), 'new': as_completed_date}
            if _od('shipping_scheduled_date') != shipping_scheduled_date: changes['shipping_scheduled_date'] = {'old': _od('shipping_scheduled_date'), 'new': shipping_scheduled_date}
            is_regional_new = 'is_regional' in request.form
            if bool(_od('is_regional', False)) != is_regional_new: changes['is_regional'] = {'old': _od('is_regional'), 'new': is_regional_new}
            is_self_measurement_new = 'is_self_measurement' in request.form
            if bool(_od('is_self_measurement', False)) != is_self_measurement_new: changes['is_self_measurement'] = {'old': _od('is_self_measurement'), 'new': is_self_measurement_new}
            measurement_completed_new = 'measurement_completed' in request.form
            if bool(_od('measurement_completed', False)) != measurement_completed_new: changes['measurement_completed'] = {'old': _od('measurement_completed'), 'new': measurement_completed_new}
            construction_type_raw = request.form.get('construction_type', _od('construction_type'))
            construction_type_new = (
                normalize_regional_construction_type(construction_type_raw)
                if is_regional_new
                else None
            )
            if is_regional_new and str(construction_type_raw or '').strip() and not construction_type_new:
                flash('시공 구분은 하우드 시공 또는 협력사 시공만 가능합니다.', 'error')
                raise ValueError("Invalid construction_type")
            if is_regional_new and not construction_type_new:
                flash('지방주문 구분(하우드/협력사)을 선택해주세요.', 'error')
                raise ValueError("Missing construction_type")
            if _od('construction_type') != construction_type_new: changes['construction_type'] = {'old': _od('construction_type'), 'new': construction_type_new}
            new_payment_amount = getattr(order, 'payment_amount', 0) or 0
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
            if _od('payment_amount') != new_payment_amount: changes['payment_amount'] = {'old': _od('payment_amount'), 'new': new_payment_amount}

            setattr(order, 'received_date', received_date)
            setattr(order, 'received_time', received_time)
            setattr(order, 'customer_name', customer_name)
            setattr(order, 'phone', phone)
            if 'address' in changes:
                reset_order_geocode_on_address_change(order, address)
            else:
                setattr(order, 'address', address)
            setattr(order, 'product', product)
            setattr(order, 'options', options_data_json_to_save)
            setattr(order, 'notes', notes)
            setattr(order, 'status', status)
            setattr(order, 'measurement_date', measurement_date)
            setattr(order, 'measurement_time', measurement_time)
            setattr(order, 'completion_date', completion_date)
            setattr(order, 'manager_name', manager_name)
            setattr(order, 'scheduled_date', scheduled_date)
            setattr(order, 'as_received_date', as_received_date)
            setattr(order, 'as_completed_date', as_completed_date)
            setattr(order, 'shipping_scheduled_date', shipping_scheduled_date)
            setattr(order, 'payment_amount', new_payment_amount)
            setattr(order, 'is_regional', is_regional_new)
            setattr(order, 'is_self_measurement', is_self_measurement_new)
            is_cabinet_new = 'is_cabinet' in request.form
            if bool(_od('is_cabinet', False)) != is_cabinet_new: changes['is_cabinet'] = {'old': _od('is_cabinet'), 'new': is_cabinet_new}
            setattr(order, 'is_cabinet', is_cabinet_new)
            if is_cabinet_new and not getattr(order, 'cabinet_status', None):
                setattr(order, 'cabinet_status', 'RECEIVED')
            elif not is_cabinet_new:
                setattr(order, 'cabinet_status', None)
            setattr(order, 'construction_type', construction_type_new)
            # ERP Order: 실측일/시공일 JSONB 반영 + Order.address ↔ site 주소 정합(AS·목록은 site 우선 표시)
            site_address_jsonb_changed = False
            _sd = getattr(order, 'structured_data', None)
            # structured_data가 빈 dict여도 실측/시공·site 정합이 필요함 (and _sd는 {}에서 falsy로 전체 스킵됨)
            if is_erp_order_record(order) and _sd is not None:
                sd = _ensure_dict(_sd)
                if isinstance(sd, dict):
                    schedule = sd.setdefault('schedule', {})
                    measurement = schedule.setdefault('measurement', {})
                    measurement['date'] = measurement_date or ''
                    measurement['time'] = measurement_time or ''
                    if getattr(order, 'status', None) not in ('AS_RECEIVED', 'AS_COMPLETED'):
                        construction = schedule.setdefault('construction', {})
                        construction['date'] = scheduled_date or ''
                    flat_addr = (getattr(order, 'address', None) or '').strip()
                    site_address_jsonb_changed = apply_erp_order_site_address_to_sd(sd, flat_addr)
                    setattr(order, 'structured_data', copy.deepcopy(sd))
                    flag_modified(order, 'structured_data')
                    sync_erp_flat_columns(order, sd)
            if site_address_jsonb_changed and 'address' not in changes:
                clear_order_geocode_coords(order)
            if bool(getattr(order, 'is_regional', False)):
                for f in ['measurement_completed', 'regional_sales_order_upload', 'regional_blueprint_sent',
                          'regional_order_upload', 'regional_cargo_sent', 'regional_construction_info_sent']:
                    setattr(order, f, f in request.form)
            db.commit()

            if 'address' in changes or site_address_jsonb_changed:
                enqueue_geocode_order_address(order_id)

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
            tpl_err = 'orders/edit_order.html'
            resp_err = make_response(
                render_template(
                    tpl_err,
                    order=order,
                    option_type=option_type,
                    online_options=online_options,
                    direct_options=direct_options,
                    mobile_shell_title=(
                        f'{order.customer_name} 고객님'
                        if order.customer_name else '주문 수정'
                    ),
                    mobile_shell_show_back=True,
                    mobile_shell_back_href=url_for(
                        'erp_dashboard.erp_order_mobile_detail', order_id=order.id
                    ),
                    erp_sub_nav_active='dashboard',
                )
            )
            return resp_err

    preserved_args = get_preserved_filter_args(request.args)
    ctx = build_order_edit_get_context(order, user=get_user_by_id(session.get("user_id")))
    return_to = (request.args.get('return_to') or '').strip()
    if return_to:
        mobile_shell_back_href = url_for(resolve_edit_return_back_endpoint(return_to))
    else:
        mobile_shell_back_href = url_for(
            'erp_dashboard.erp_order_mobile_detail', order_id=order.id
        )
    tpl = 'orders/edit_order.html'
    response = make_response(
        render_template(
            tpl,
            preserved_args=preserved_args,
            mobile_shell_title='주문 수정',
            mobile_shell_show_back=True,
            mobile_shell_back_href=mobile_shell_back_href,
            erp_sub_nav_active='dashboard',
            **ctx,
        )
    )
    return response


def _build_erp_order_bootstrap(order, user=None):
    """서버 렌더 시점에 ERP Order 상세 데이터를 인라인 JSON 부트스트랩으로 제공.

    클라이언트 `/api/orders/<id>/structured` 응답과 동일한 shape를 사용해
    첫 페인트 이후 발생하던 2단계 로딩(빈 화면 → fetch → DOM 주입)을 제거한다.
    """
    from foms.services.order_attachment_permissions import can_manage_order_attachments

    updated_at = getattr(order, 'structured_updated_at', None)
    updated_at_str = updated_at.strftime('%Y-%m-%d %H:%M:%S') if updated_at is not None else None
    payload = {
        'success': True,
        'order_id': order.id,
        'raw_order_text': order.raw_order_text or '',
        'structured_data': order.structured_data or {},
        'structured_schema_version': getattr(order, 'structured_schema_version', None),
        'structured_confidence': getattr(order, 'structured_confidence', None),
        'structured_updated_at': updated_at_str,
        'received_date': order.received_date or '',
        'received_time': order.received_time or '',
        'notes': order.notes or '',
        'is_self_measurement': getattr(order, 'is_self_measurement', False),
        'is_regional': getattr(order, 'is_regional', False),
        'construction_type': getattr(order, 'construction_type', None) or '',
        # GET /structured 와 동일 shape — 지방주문 AS 재상차 모달 prefill용.
        'shipping_scheduled_date': getattr(order, 'shipping_scheduled_date', None) or '',
    }
    if user is not None:
        try:
            current_user_id = int(getattr(user, 'id', None))
        except (TypeError, ValueError):
            current_user_id = None
        payload['attachment_permissions'] = {
            'current_user_id': current_user_id,
            'is_admin': getattr(user, 'role', None) == 'ADMIN',
            'is_order_manager': can_manage_order_attachments(user, order),
        }
    return payload
