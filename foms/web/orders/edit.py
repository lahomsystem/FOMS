"""주문 수정 페이지 Blueprint (canonical; SFC-B11B): edit_order (/edit/<order_id>)."""
import copy
import json
import uuid
from typing import Any

from flask import (
    Blueprint,
    g,
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
from foms.services.audit_message_display import FIELD_LABELS as AUDIT_FIELD_LABELS
from foms.services.orders.status_constants import STATUS
from foms.services.erp_order_deeplink import resolve_edit_return_back_endpoint
# 의존성 없는 상수 모듈이다(수집 파이프라인을 끌어오지 않는다 — constants.py 도입부 참고).
from foms.services.integrations.naver_commerce.constants import (
    LINKED_MARKER_KEY,
    SOURCE_MARKER,
)
from foms.services.request_utils import get_preserved_filter_args, redirect_if_legacy_open_erp_beta
from foms.services.order_edit_view_context import build_order_edit_get_context
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.orders.as_cycle_view import as_cycle_detail_payload
from foms.services.orders.construction_type import normalize_regional_construction_type
from foms.services.orders.order_flag_permissions import can_toggle_order_flags
from foms.services.orders.order_field_change_writer import record_field_changes
from foms.services.orders.structured_diff import diff_structured, normalize_for_ledger
from foms.services.order_geocode import (
    apply_erp_order_site_address_to_sd,
    clear_order_geocode_coords,
    reset_order_geocode_on_address_change,
)

order_edit_bp = Blueprint('order_edit', __name__, url_prefix='')

#: AUDIT-GAP-01: 이 폼이 쓰는 평면 컬럼 → 변경 원장 경로(점 없는 컬럼명 = ORDER-FLAG-01 규약).
#:
#: **빠진 것은 일부러 뺐다.** ``customer_name``·``phone``·``manager_name``·``product``·
#: ``address``·``measurement_date``·``measurement_time``·``scheduled_date`` 는
#: ``structured_data`` 쌍둥이(``parties.customer.name``·``schedule.measurement.date``·
#: ``site.address_full`` …)가 아래 sd diff 로 이미 원장에 실린다 — 평면으로 또 넣으면 같은
#: 사실이 경로 2벌이 되어 감사 화면의 ``path_template`` 필터가 반쪽만 잡는다.
#:
#: ``status`` 는 **자기 path 로** 남긴다(``workflow.stage`` 로 매핑하지 않는다). 두 축은 어휘가
#: 달라서(AS 판정은 status, stage 는 MEASURE 로 남는다 — 2026-08-14 사고 축) 합치면 거짓 이력이 된다.
_LEDGER_FLAT_PATHS: dict[str, str] = {
    'received_date': 'received_date',
    'received_time': 'received_time',
    'status': 'status',
    'options': 'options',
    # Order.notes 컬럼(주문 비고)은 sd 의 ``notes`` 와 **다른 값**이다(sync 대상도 아니다).
    # 같은 path 를 쓰면 서로 다른 두 필드가 한 이력으로 합쳐진다.
    'notes': 'order_notes',
    'completion_date': 'completion_date',
    'as_received_date': 'as_received_date',
    'as_completed_date': 'as_completed_date',
    'shipping_scheduled_date': 'shipping_scheduled_date',
    'payment_amount': 'payment_amount',
    'is_cabinet': 'is_cabinet',
    # 플래그 3종. path 이름이 PUT /structured(ORDER-FLAG-01)와 **같으므로** 경로가 2벌이 되지
    # 않고 오히려 통일된다 — 이 폼만 빼 두면 다른 경로에서 메운 구멍이 여기에만 그대로 남는다.
    # is_regional·construction_type 은 권한 게이트를 통과한 값만 바뀌므로(무권한이면 기존값이
    # 강제되어 변경 자체가 없다) 무권한 저장에서는 행이 생기지 않는 것이 정상이다.
    'is_regional': 'is_regional',
    'construction_type': 'construction_type',
    'is_self_measurement': 'is_self_measurement',
}

#: bool 컬럼. 양쪽을 bool 로 맞춰야 컬럼 NULL(``None``) → ``False`` 가 허위 변경으로 남지 않는다.
_LEDGER_BOOL_KEYS: frozenset[str] = frozenset({
    'is_cabinet', 'is_regional', 'is_self_measurement',
})

#: 금액 경로. 빈 금액 칸이 ``0`` 으로 채워지는 것을 변경으로 읽지 않기 위한 표식이다
#: (``structured_diff._is_unset`` 의 numeric 규칙과 같은 뜻 — 경로에 점이 없어 그 판정을 못 탄다).
_LEDGER_NUMERIC_PATHS: frozenset[str] = frozenset({'payment_amount'})

#: 지방 체크리스트 6종 — 이 폼은 ``changes`` dict 에 담지 않고 setattr 만 한다(순서 = 저장 루프 순서).
_REGIONAL_CHECKLIST_FIELDS: tuple[str, ...] = (
    'measurement_completed',
    'regional_sales_order_upload',
    'regional_blueprint_sent',
    'regional_order_upload',
    'regional_cargo_sent',
    'regional_construction_info_sent',
)


def _compare_value(value: Any) -> Any:
    """변경 여부 **판정용** 값(절단 없음).

    저장 표현은 :func:`normalize_for_ledger` 가 120자에서 자르지만, 판정까지 잘린 값으로 하면
    120자 뒤만 바뀐 저장이 '무변경'으로 사라진다(그게 곧 무기록이다). 그래서 판정은 원문으로 한다.

    :param value: 컬럼에서 읽은 원시 값.
    :return: 비교 가능한 값(빈 문자열은 ``None``).
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return normalize_for_ledger(value, '')
    return str(value).strip() or None


def _is_ledger_unset(value: Any, *, numeric: bool) -> bool:
    """정규 값이 "지정하지 않음"과 같은 뜻인지(``structured_diff._is_unset`` 과 같은 규칙).

    체크 안 한 체크박스(``False``)·빈 금액 칸(``0``)이 컬럼 기본값으로 채워지는 것을 변경으로
    적으면 저장 한 번마다 소음이 쌓여 진짜 변경이 묻힌다 — **양쪽이 모두** 이 상태일 때만 뺀다.

    :param value: :func:`normalize_for_ledger` 를 거친 값.
    :param numeric: 금액 경로면 ``True`` — 이때만 ``"0"`` 을 미지정과 같게 본다.
    :return: 미지정과 같은 뜻이면 ``True``.
    """
    if value is None or value is False:
        return True
    return bool(numeric and value == "0")


def _flat_change(path: str, before: Any, after: Any) -> dict[str, Any] | None:
    """평면 컬럼 변경 1건을 원장 change dict 로 만든다.

    저장 값은 sd diff 와 **같은 함수**(:func:`normalize_for_ledger`)를 거친다 — 빈값 동치와
    길이 절단 규칙이 갈라지면 같은 원장 안에서 두 갈래가 서로 다른 뜻으로 읽힌다.

    :param path: 원장 경로(점 없는 컬럼명).
    :param before: 저장 전 값.
    :param after: 저장 후 값.
    :return: ``{'path','before','after','op'}``. 실제 변경이 아니면 ``None``.
    """
    old_value = normalize_for_ledger(before, path)
    new_value = normalize_for_ledger(after, path)
    numeric = path in _LEDGER_NUMERIC_PATHS
    if (_is_ledger_unset(old_value, numeric=numeric)
            and _is_ledger_unset(new_value, numeric=numeric)):
        return None
    if _compare_value(before) == _compare_value(after):
        return None
    if old_value is None:
        op = 'add'
    elif new_value is None:
        op = 'clear'
    else:
        op = 'set'
    return {'path': path, 'before': old_value, 'after': new_value, 'op': op}


def _flat_ledger_changes(changes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """폼이 모은 ``changes`` 중 sd 쌍둥이가 없는 평면 컬럼만 원장 change 목록으로 옮긴다.

    :param changes: ``{필드: {'old','new'}}`` — 사람이 읽는 메시지용으로 이 라우트가 모은 dict.
    :return: 원장 change dict 목록(:data:`_LEDGER_FLAT_PATHS` 순서).
    """
    rows: list[dict[str, Any]] = []
    for field, path in _LEDGER_FLAT_PATHS.items():
        values = changes.get(field)
        if not values:
            continue
        before, after = values.get('old'), values.get('new')
        if field in _LEDGER_BOOL_KEYS:
            before, after = bool(before), bool(after)
        row = _flat_change(path, before, after)
        if row:
            rows.append(row)
    return rows


def _checklist_ledger_changes(order: Order, before: dict[str, bool]) -> list[dict[str, Any]]:
    """지방 체크리스트 6종 변경을 원장 change 목록으로 만든다.

    이 6종은 ``changes`` dict 에 담기지 않고 setattr 만 되므로, 쓰기 **직전**에 뜬 스냅샷과
    대조하는 것 말고는 before 를 알 방법이 없다.

    :param order: 저장 대상 주문(체크리스트 쓰기가 끝난 상태).
    :param before: 쓰기 직전 스냅샷(``{컬럼: bool}``).
    :return: 원장 change dict 목록.
    """
    rows: list[dict[str, Any]] = []
    for field in _REGIONAL_CHECKLIST_FIELDS:
        row = _flat_change(field, before.get(field, False), bool(getattr(order, field, False)))
        if row:
            rows.append(row)
    return rows


@order_edit_bp.route('/erp/orders/<int:order_id>')
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def redirect_legacy_erp_order_detail(order_id):
    """Redirect legacy ChannelTalk order links to the actual ERP Order detail page."""
    params = request.args.to_dict()
    params.pop("order_id", None)
    params['open'] = 'erp-order'
    return redirect(url_for('order_edit.edit_order', order_id=order_id, **params))


def _erp_sd_customer(order) -> dict:
    """ERP 주문의 ``structured_data.parties.customer`` (없으면 빈 dict).

    비ERP 주문은 sd 자체가 없으므로 늘 빈 dict 다 — 호출부가 flat 컬럼으로 떨어진다.

    Args:
        order: 주문 ORM 인스턴스.

    Returns:
        고객 dict. 모양이 어긋나면 빈 dict.
    """
    if not is_erp_order_record(order):
        return {}
    sd = getattr(order, 'structured_data', None)
    if not isinstance(sd, dict):
        return {}
    parties = sd.get('parties')
    if not isinstance(parties, dict):
        return {}
    customer = parties.get('customer')
    return customer if isinstance(customer, dict) else {}


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
            # 폼이 그 칸을 안 보냈을 때의 기본값은 **정본(sd)** 이 먼저다. flat 컬럼을
            # 기본값으로 쓰면, 어긋나 있는 주문(운영 130건)에서 부분 저장 한 번이 옛 값을
            # 정본 쪽으로 되돌려 쓴다 — 화면에 보이지도 않은 값이 정본을 덮는 셈이다.
            _sd_customer = _erp_sd_customer(_o)
            customer_name = request.form.get(
                'customer_name',
                (_sd_customer.get('name') or '').strip() or (getattr(_o, 'customer_name', None) or ''),
            )
            phone = request.form.get(
                'phone',
                (_sd_customer.get('phone') or '').strip() or (getattr(_o, 'phone', None) or ''),
            )
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
            # ORDER-FLAG-01: 지방주문은 CS(라홈팀/하우드팀)·관리자만 바꾼다. 체크박스를
            # 비활성으로 렌더하므로 폼에 안 실려 오는데, 미전송을 '해제'로 읽으면 저장 한
            # 번에 지방 대시보드에서 주문이 사라진다 — 무권한이면 기존값을 그대로 쓴다.
            flags_editable = can_toggle_order_flags(getattr(g, 'current_user', None))
            is_regional_new = ('is_regional' in request.form) if flags_editable else bool(_od('is_regional', False))
            if bool(_od('is_regional', False)) != is_regional_new: changes['is_regional'] = {'old': _od('is_regional'), 'new': is_regional_new}
            is_self_measurement_new = 'is_self_measurement' in request.form
            if bool(_od('is_self_measurement', False)) != is_self_measurement_new: changes['is_self_measurement'] = {'old': _od('is_self_measurement'), 'new': is_self_measurement_new}
            measurement_completed_new = 'measurement_completed' in request.form
            if bool(_od('measurement_completed', False)) != measurement_completed_new: changes['measurement_completed'] = {'old': _od('measurement_completed'), 'new': measurement_completed_new}
            construction_type_raw = (
                request.form.get('construction_type', _od('construction_type'))
                if flags_editable else _od('construction_type')
            )
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
            # AUDIT-GAP-01: 수납장 체크는 cabinet_status 를 **파생 변경**한다('RECEIVED'↔None).
            # is_cabinet 만 원장에 남기면 그 파생이 무기록으로 남는다 — 쓰기 직전 값을 떠 둔다.
            cabinet_status_before = getattr(order, 'cabinet_status', None)
            if is_cabinet_new and not getattr(order, 'cabinet_status', None):
                setattr(order, 'cabinet_status', 'RECEIVED')
            elif not is_cabinet_new:
                setattr(order, 'cabinet_status', None)
            setattr(order, 'construction_type', construction_type_new)
            # ERP Order: 실측일/시공일 JSONB 반영 + Order.address ↔ site 주소 정합(AS·목록은 site 우선 표시)
            site_address_jsonb_changed = False
            # AUDIT-GAP-01(갈래 1): 이 폼의 실측일·시공일·현장주소는 sd 를 고친다. 그 변경은
            # PUT /structured 와 **같은 경로**(schedule.measurement.date 등)로 원장에 실어야
            # 감사 화면 필터가 두 저장 경로를 한 벌로 잡는다(평면 컬럼명으로 적으면 2벌이 된다).
            # 비ERP 주문은 sd 를 안 고치므로 자동으로 빈 결과다.
            sd_ledger_changes: list[dict[str, Any]] = []
            _sd = getattr(order, 'structured_data', None)
            # structured_data가 빈 dict여도 실측/시공·site 정합이 필요함 (and _sd는 {}에서 falsy로 전체 스킵됨)
            if is_erp_order_record(order) and _sd is not None:
                sd = _ensure_dict(_sd)
                if isinstance(sd, dict):
                    audit_old_sd = copy.deepcopy(sd)
                    schedule = sd.setdefault('schedule', {})
                    measurement = schedule.setdefault('measurement', {})
                    measurement['date'] = measurement_date or ''
                    measurement['time'] = measurement_time or ''
                    if getattr(order, 'status', None) not in ('AS_RECEIVED', 'AS_COMPLETED'):
                        construction = schedule.setdefault('construction', {})
                        construction['date'] = scheduled_date or ''
                    # AUDIT-GAP-01(갈래 2, 2026-09-02): 고객명·전화도 sd 쌍둥이를 함께
                    # 고친다. 위 _LEDGER_FLAT_PATHS 주석은 이 두 값이 "sd diff 로 이미
                    # 원장에 실린다"고 적어 두었지만, 실제로는 이 폼이 sd ``parties`` 를
                    # 건드리지 않아 **전화 변경이 원장에 아무 흔적도 남기지 않았다**.
                    # 게다가 flat 만 새 값이 되어 정본(sd)과 어긋나고, 그 어긋남은 방향을
                    # 알 수 없는 채로 쌓인다(운영 48건이 그 상태다 —
                    # docs/incidents/2026-09-01-naver-triage-auto-match-miss.md 부록 A).
                    parties = sd.setdefault('parties', {})
                    if not isinstance(parties, dict):
                        parties = {}
                        sd['parties'] = parties
                    customer_sd = parties.setdefault('customer', {})
                    if not isinstance(customer_sd, dict):
                        customer_sd = {}
                        parties['customer'] = customer_sd
                    # 빈 칸으로 정본을 지우지 않는다 — 값이 들어왔을 때만 고친다.
                    if customer_name:
                        customer_sd['name'] = customer_name
                    if phone:
                        customer_sd['phone'] = phone

                    flat_addr = (getattr(order, 'address', None) or '').strip()
                    site_address_jsonb_changed = apply_erp_order_site_address_to_sd(sd, flat_addr)
                    setattr(order, 'structured_data', copy.deepcopy(sd))
                    flag_modified(order, 'structured_data')
                    sync_erp_flat_columns(order, sd)
                    # 원장에는 전량을 싣는다(상한은 화면용 detail 에만 거는 값이다).
                    sd_ledger_changes = diff_structured(audit_old_sd, sd, max_changes=-1).changes
            if site_address_jsonb_changed and 'address' not in changes:
                clear_order_geocode_coords(order)
            # AUDIT-GAP-01: 체크리스트 6종은 changes dict 에 안 담기고 setattr 만 된다 —
            # 쓰기 직전 값을 떠야 before/after 가 남는다(비지방 주문은 루프 자체가 안 돈다).
            checklist_before = {
                field: bool(getattr(order, field, False))
                for field in _REGIONAL_CHECKLIST_FIELDS
            }
            if bool(getattr(order, 'is_regional', False)):
                for f in _REGIONAL_CHECKLIST_FIELDS:
                    setattr(order, f, f in request.form)

            # AUDIT-GAP-01: 원장 행은 저장과 **같은 트랜잭션**에 싣는다(아래 commit 이 함께 커밋).
            # record_field_changes 는 이미 fail-open 이라 여기서 다시 감싸지 않는다.
            change_set_id = str(uuid.uuid4())
            ledger_changes = list(sd_ledger_changes)
            ledger_changes.extend(_flat_ledger_changes(changes))
            cabinet_status_change = _flat_change(
                'cabinet_status', cabinet_status_before, getattr(order, 'cabinet_status', None)
            )
            if cabinet_status_change:
                ledger_changes.append(cabinet_status_change)
            ledger_changes.extend(_checklist_ledger_changes(order, checklist_before))
            record_field_changes(
                db, ledger_changes,
                order_id=int(order_id),
                actor_user_id=session.get('user_id'),
                change_set_id=change_set_id,
            )
            db.commit()

            # MUT-CACHE-01: 이 폼 저장은 canonical mutation 엔진을 경유하지 않으므로
            # after_commit 자동 무효화가 걸리지 않는다. 상태·일정·완료일을 한 번에 바꾸는
            # 경로라 어느 탭 숫자판이든 흔들 수 있어 broad 로 비운다(저빈도 경로).
            try:
                from foms.services.common.dashboard_cache import (
                    invalidate_dashboard_caches_after_delete_transition,
                )

                invalidate_dashboard_caches_after_delete_transition("order_edit_form")
            except Exception:
                current_app.logger.warning(
                    "post order edit dashboard cache invalidate failed", exc_info=True
                )

            if 'address' in changes or site_address_jsonb_changed:
                enqueue_geocode_order_address(order_id)

            # 라벨 사전 SSOT: foms/services/audit_message_display.FIELD_LABELS.
            # (여기 지역 dict 로 두던 시절, 다른 저장 경로는 영문 필드명을 그대로 기록했다.)
            field_labels = AUDIT_FIELD_LABELS
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
            # AUDIT-GAP-01: 한글 자유문장은 사람이 읽는 용도로 그대로 두고, SQL 로 물을 수 있는
            # 구조화 컬럼을 **추가**한다. detail['change_set'] 이 위 원장 행과 잇는 유일한 열쇠다
            # (관리자 감사 화면이 detail->>'change_set' 으로 조인한다).
            log_access(
                log_message, session.get('user_id'),
                action='ORDER_FIELD_UPDATED', target_type='order', target_id=int(order_id),
                detail={
                    'change_set': change_set_id,
                    'change_count': len(ledger_changes),
                    'source': 'order_edit_form',
                },
            )
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
        # DATA-01: If-Match(mutation_version) 낙관 잠금 토큰. GET /structured 와 동일 —
        # 이게 빠지면 bootstrap 으로 첫 페인트한 세션의 첫 저장이 If-Match 없이 나가
        # 낙관 잠금이 무력화된다.
        'mutation_version': getattr(order, 'mutation_version', None),
        'received_date': order.received_date or '',
        'received_time': order.received_time or '',
        'notes': order.notes or '',
        'is_self_measurement': getattr(order, 'is_self_measurement', False),
        'is_regional': getattr(order, 'is_regional', False),
        'construction_type': getattr(order, 'construction_type', None) or '',
        # GET /structured 와 동일 shape — 지방주문 AS 재상차 모달 prefill용.
        'shipping_scheduled_date': getattr(order, 'shipping_scheduled_date', None) or '',
        # GET /structured 와 동일 shape — AS 재접수 모달의 'N번째 AS' 제목·지난 건 요약.
        # 두 지점이 갈리면 첫 페인트와 새로고침 후 모달이 서로 다른 걸 그린다.
        'as_cycle': as_cycle_detail_payload(order.structured_data),
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
    # 네이버 수집분이 있는 주문이면 원본 도크 데이터를 동봉한다(T14-B — 추가 fetch 0).
    # 게이트는 딕셔너리 조회 두 번뿐이라 일반 주문은 링크 쿼리조차 내지 않는다(hot path 비용 0).
    #
    # 키가 둘인 이유(설계서 2026-08-28-naver-repay-origin-cancel §7): ``source`` 는 주문
    # **출처**(네이버가 만든 주문), ``naver_linked`` 는 붙이기가 켜는 **도크 게이트**다.
    # 예약금 건처럼 ERP 에 직접 등록한 주문에 재결제를 붙이면 뒤만 참이고, 그때도 도크는
    # 떠야 한다 — 붙이기가 기록한 추가결제를 읽는 코드가 이 도크 하나뿐이기 때문이다.
    naver_gate_sd = order.structured_data or {}
    if (naver_gate_sd.get('source') == SOURCE_MARKER
            or naver_gate_sd.get(LINKED_MARKER_KEY)):
        from foms.services.integrations.naver_commerce.dock import build_dock_payload

        # viewer 는 워크벤치 링크(R2) 판정에만 쓴다 — ADMIN·MANAGER 가 아니거나 게이트가
        # 꺼져 있으면 payload 에 주소가 아예 실리지 않는다.
        payload['naver_origin'] = build_dock_payload(get_db(), order, viewer=user)
    return payload
