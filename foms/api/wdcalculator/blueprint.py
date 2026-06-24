"""WDCalculator (가구 견적 계산기) API Blueprint.

페이지: /wdcalculator, /wdcalculator/product-settings
API: /api/wdcalculator/*
"""
import copy
import os
import json
from flask import Blueprint, request, jsonify, render_template
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from db import get_db
from models import Order
from foms.services.erp_display import _ensure_dict, _normalize_for_search
from foms.web.auth import login_required
from wdcalculator_db import get_wdcalculator_db
from wdcalculator_models import (
    Estimate,
    EstimateHistory,
    EstimateOrderMatch,
    WDCalculatorProductSettings,
)

# 프로젝트 루트 기준 데이터 경로 (foms/api/wdcalculator/blueprint.py → repo root)
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
WD_CALCULATOR_DATA_PATH = os.path.join(_PROJECT_ROOT, 'data', 'products.json')
WD_ADDITIONAL_OPTIONS_PATH = os.path.join(_PROJECT_ROOT, 'data', 'additional_options.json')
WD_NOTES_CATEGORIES_PATH = os.path.join(_PROJECT_ROOT, 'data', 'notes_categories.json')
WD_SPEC_FIELD_PRESETS_PATH = os.path.join(_PROJECT_ROOT, 'data', 'spec_field_presets.json')

# ERP 현장 스펙 프리셋을 관리하는 필드 화이트리스트 (제품명=products, 옵션=additional_options 재사용)
SPEC_PRESET_FIELDS = ('color', 'handle', 'internal', 'misc')

wdcalculator_bp = Blueprint('wdcalculator', __name__, url_prefix='')


def clean_categories_data(categories):
    """카테고리 데이터에서 JSON 직렬화 불가능한 값 제거 및 id 자동 생성"""
    if not categories:
        return []
    cleaned = []
    base_option_id = 1000
    for cat_idx, category in enumerate(categories):
        if category is None:
            continue
        cleaned_category = {
            'id': category.get('id') if category.get('id') is not None else None,
            'name': category.get('name') or '',
            'options': []
        }
        options = category.get('options')
        if options and isinstance(options, list) and len(options) > 0:
            existing_ids = [o.get('id') for o in options if o and isinstance(o, dict) and o.get('id') is not None]
            max_existing_id = max(existing_ids + [0]) if existing_ids else 0
            next_id = max(max_existing_id + 1, base_option_id + (cat_idx * 100))
            for opt_idx, option in enumerate(options):
                if option is None or not isinstance(option, dict):
                    continue
                option_id = option.get('id')
                if option_id is None:
                    option_id = next_id
                    next_id += 1
                cleaned_option = {
                    'id': option_id,
                    'name': str(option.get('name') or '').strip(),
                    'price': float(option.get('price', 0)) if option.get('price') is not None else 0.0
                }
                cleaned_category['options'].append(cleaned_option)
        cleaned.append(cleaned_category)
    return cleaned


def _deepcopy_json(value, default):
    """JSON 직렬화 가능한 값을 안전하게 복사"""
    if value is None:
        return copy.deepcopy(default)
    return copy.deepcopy(value)


def _first_erp_product_label(items):
    if not isinstance(items, list):
        return ''
    product_names = []
    for item in items:
        if not isinstance(item, dict):
            continue
        product_name = (item.get('product_name') or item.get('name') or '').strip()
        if product_name:
            product_names.append(product_name)
    if not product_names:
        return ''
    if len(product_names) == 1:
        return product_names[0]
    return f"{product_names[0]} 외 {len(product_names) - 1}개"


def _parse_order_payment_amount(value):
    if value is None:
        return 0
    if isinstance(value, dict):
        return _parse_order_payment_amount(value.get('amount') or value.get('raw'))
    if isinstance(value, (int, float)):
        return max(0, int(value))

    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else 0


def _extract_order_payment_amount(order):
    """Return the prepaid/deposit amount used by matched WD estimates."""
    if getattr(order, 'is_erp_order', False):
        structured_data = _ensure_dict(order.structured_data)
        for payment_key in ('payment', 'payments'):
            payment_data = structured_data.get(payment_key) or {}
            if not isinstance(payment_data, dict):
                continue
            amount = _parse_order_payment_amount(payment_data.get('deposit'))
            if amount > 0:
                return amount

    return _parse_order_payment_amount(getattr(order, 'payment_amount', 0))


def _build_order_payment_payload(order):
    amount = _extract_order_payment_amount(order)
    is_erp_order = bool(getattr(order, 'is_erp_order', False))
    return {
        'amount': amount,
        'payment_amount': amount,
        'deposit_amount': amount if is_erp_order else 0,
        'label': '예약금(선금)' if is_erp_order else '선 결제 금액',
    }


def _build_order_match_payload(order):
    """Return the display payload WDCalculator uses to choose an order."""
    customer_name = order.customer_name
    phone = order.phone
    address = order.address
    product = order.product

    if getattr(order, 'is_erp_order', False):
        structured_data = _ensure_dict(order.structured_data)
        parties = structured_data.get('parties') or {}
        customer = (parties.get('customer') or {}) if isinstance(parties, dict) else {}
        site = structured_data.get('site') or {}

        erp_customer_name = (customer.get('name') or '').strip()
        if erp_customer_name:
            customer_name = erp_customer_name

        erp_phone = (customer.get('phone') or '').strip()
        if erp_phone:
            phone = erp_phone

        address_full = (site.get('address_full') or '').strip() if isinstance(site, dict) else ''
        address_main = (site.get('address_main') or '').strip() if isinstance(site, dict) else ''
        address_detail = (site.get('address_detail') or '').strip() if isinstance(site, dict) else ''
        if address_full and address_full != '-':
            address = address_full
        elif address_main:
            address = f"{address_main} {address_detail}".strip() if address_detail and address_detail != '-' else address_main

        erp_product = _first_erp_product_label(structured_data.get('items') or [])
        if erp_product:
            product = erp_product

    return {
        'id': order.id,
        'customer_name': customer_name,
        'phone': phone,
        'address': address,
        'product': product,
        'status': order.status,
        'received_date': order.received_date if order.received_date else None,
    }


def _load_json_file(path, wrapper_key):
    """시드용 JSON 파일 로드"""
    try:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f).get(wrapper_key, [])
            except UnicodeDecodeError:
                with open(path, 'r', encoding='cp949') as f:
                    return json.load(f).get(wrapper_key, [])
        return []
    except Exception as e:
        print(f"Error loading JSON file {path}: {e}")
        return []


def _seed_products_from_file():
    """초기 시드용 제품 목록 로드"""
    return _load_json_file(WD_CALCULATOR_DATA_PATH, 'products')


def _seed_additional_option_categories_from_file():
    """초기 시드용 추가 옵션 카테고리 로드"""
    return clean_categories_data(_load_json_file(WD_ADDITIONAL_OPTIONS_PATH, 'categories'))


def _seed_notes_categories_from_file():
    """초기 시드용 비고 카테고리 로드"""
    return clean_categories_data(_load_json_file(WD_NOTES_CATEGORIES_PATH, 'categories'))


def _normalize_spec_field_presets(value):
    """ERP 스펙 필드 프리셋을 {field: [{id, name}]} 형태로 정규화한다.

    화이트리스트(:data:`SPEC_PRESET_FIELDS`) 키만 유지하고, 각 항목은 빈 이름을
    제거하며 누락된 id를 자동 채번한다. dict가 아니거나 손상된 입력은 빈 프리셋으로
    안전하게 환원한다.
    """
    result = {field: [] for field in SPEC_PRESET_FIELDS}
    if not isinstance(value, dict):
        return result
    for field in SPEC_PRESET_FIELDS:
        items = value.get(field)
        if not isinstance(items, list):
            continue
        existing_ids = [
            i.get('id') for i in items
            if isinstance(i, dict) and i.get('id') is not None
        ]
        next_id = (max(existing_ids) + 1) if existing_ids else 1
        cleaned = []
        seen_names = set()
        for item in items:
            if isinstance(item, dict):
                name = str(item.get('name') or '').strip()
                pid = item.get('id')
            else:
                name = str(item or '').strip()
                pid = None
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            if pid is None:
                pid = next_id
                next_id += 1
            cleaned.append({'id': int(pid), 'name': name})
        result[field] = cleaned
    return result


def _seed_spec_field_presets_from_file():
    """초기 시드용 ERP 스펙 필드 프리셋 로드"""
    return _normalize_spec_field_presets(
        _load_json_file(WD_SPEC_FIELD_PRESETS_PATH, 'spec_field_presets')
    )


def _build_settings_seed():
    """WDCalculator 설정 초기값 생성"""
    return {
        'products': _seed_products_from_file(),
        'additional_options': _seed_additional_option_categories_from_file(),
        'notes_categories': _seed_notes_categories_from_file(),
        'spec_field_presets': _seed_spec_field_presets_from_file(),
    }


def _get_product_settings(db=None):
    """저장된 WDCalculator 설정 싱글턴 조회"""
    session = db or get_wdcalculator_db()
    return session.query(WDCalculatorProductSettings).filter(WDCalculatorProductSettings.id == 1).first()


def _build_settings_record():
    """초기 시드 기반 설정 레코드 생성"""
    seed = _build_settings_seed()
    return WDCalculatorProductSettings(
        id=1,
        products=seed['products'],
        additional_options=seed['additional_options'],
        notes_categories=seed['notes_categories'],
        spec_field_presets=seed['spec_field_presets'],
    )


def _populate_missing_settings_fields(settings):
    """부분 레코드의 누락 필드를 시드로 보강"""
    seed = _build_settings_seed()
    if settings.products is None:
        settings.products = seed['products']
    if settings.additional_options is None:
        settings.additional_options = seed['additional_options']
    if settings.notes_categories is None:
        settings.notes_categories = seed['notes_categories']
    if getattr(settings, 'spec_field_presets', None) is None:
        settings.spec_field_presets = seed['spec_field_presets']


def load_additional_option_categories():
    """추가 옵션 카테고리 데이터를 DB에서 로드"""
    try:
        settings = _get_product_settings()
        if not settings or settings.additional_options is None:
            return _seed_additional_option_categories_from_file()
        return clean_categories_data(_deepcopy_json(settings.additional_options, []))
    except Exception as e:
        print(f"Error loading additional option categories: {e}")
        return []


def save_additional_option_categories(categories):
    """추가 옵션 카테고리 데이터를 DB에 저장"""
    try:
        session = get_wdcalculator_db()
        settings = _get_product_settings(session)
        if not settings:
            settings = _build_settings_record()
            session.add(settings)
        _populate_missing_settings_fields(settings)
        settings.additional_options = clean_categories_data(categories or [])
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            settings = _get_product_settings(session)
            if not settings:
                raise
            _populate_missing_settings_fields(settings)
            settings.additional_options = clean_categories_data(categories or [])
            session.commit()
        return True
    except Exception as e:
        session = get_wdcalculator_db()
        session.rollback()
        print(f"Error saving additional option categories: {e}")
        return False


def load_notes_categories():
    """비고 카테고리 데이터를 DB에서 로드"""
    try:
        settings = _get_product_settings()
        if not settings or settings.notes_categories is None:
            return _seed_notes_categories_from_file()
        return clean_categories_data(_deepcopy_json(settings.notes_categories, []))
    except Exception as e:
        print(f"Error loading notes categories: {e}")
        return []


def save_notes_categories(categories):
    """비고 카테고리 데이터를 DB에 저장"""
    try:
        session = get_wdcalculator_db()
        settings = _get_product_settings(session)
        if not settings:
            settings = _build_settings_record()
            session.add(settings)
        _populate_missing_settings_fields(settings)
        settings.notes_categories = clean_categories_data(categories or [])
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            settings = _get_product_settings(session)
            if not settings:
                raise
            _populate_missing_settings_fields(settings)
            settings.notes_categories = clean_categories_data(categories or [])
            session.commit()
        return True
    except Exception as e:
        session = get_wdcalculator_db()
        session.rollback()
        print(f"Error saving notes categories: {e}")
        return False


def load_products():
    """제품 데이터를 DB에서 로드"""
    try:
        settings = _get_product_settings()
        if not settings or settings.products is None:
            return _seed_products_from_file()
        return _deepcopy_json(settings.products, [])
    except Exception as e:
        print(f"Error loading products: {e}")
        return []


def save_products(products):
    """제품 데이터를 DB에 저장"""
    try:
        session = get_wdcalculator_db()
        settings = _get_product_settings(session)
        if not settings:
            settings = _build_settings_record()
            session.add(settings)
        _populate_missing_settings_fields(settings)
        settings.products = _deepcopy_json(products, [])
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            settings = _get_product_settings(session)
            if not settings:
                raise
            _populate_missing_settings_fields(settings)
            settings.products = _deepcopy_json(products, [])
            session.commit()
        return True
    except Exception as e:
        session = get_wdcalculator_db()
        session.rollback()
        print(f"Error saving products: {e}")
        return False


def load_spec_field_presets():
    """ERP 스펙 필드 프리셋을 DB에서 로드 (없으면 시드 반환)"""
    try:
        settings = _get_product_settings()
        if not settings or getattr(settings, 'spec_field_presets', None) is None:
            return _seed_spec_field_presets_from_file()
        return _normalize_spec_field_presets(_deepcopy_json(settings.spec_field_presets, {}))
    except Exception as e:
        print(f"Error loading spec field presets: {e}")
        return _normalize_spec_field_presets({})


def save_spec_field_presets(presets):
    """ERP 스펙 필드 프리셋을 DB에 저장"""
    try:
        session = get_wdcalculator_db()
        settings = _get_product_settings(session)
        if not settings:
            settings = _build_settings_record()
            session.add(settings)
        _populate_missing_settings_fields(settings)
        settings.spec_field_presets = _normalize_spec_field_presets(presets or {})
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            settings = _get_product_settings(session)
            if not settings:
                raise
            _populate_missing_settings_fields(settings)
            settings.spec_field_presets = _normalize_spec_field_presets(presets or {})
            session.commit()
        return True
    except Exception as e:
        session = get_wdcalculator_db()
        session.rollback()
        print(f"Error saving spec field presets: {e}")
        return False


def calculate_estimate(product, width_mm, additional_options=None):
    """견적 계산 함수"""
    if not product:
        return 0
    base_price = 0
    if product['pricing_type'] == '1m':
        meters = width_mm / 1000
        base_price = meters * product.get('price_1m', 0)
    elif product['pricing_type'] == '30cm':
        units_30cm = width_mm // 300
        remainder_mm = width_mm % 300
        units_1cm = remainder_mm // 10
        base_price = (units_30cm * product.get('price_30cm', 0)) + (units_1cm * product.get('price_1cm', 0))
    additional_price = 0
    if additional_options:
        for option in additional_options:
            if isinstance(option, dict) and 'price' in option:
                additional_price += float(option.get('price', 0))
    return base_price + additional_price


def apply_coupon(total_price, coupon_type, coupon_value):
    """쿠폰가 적용"""
    if coupon_type == 'percentage':
        return total_price - (total_price * (float(coupon_value) / 100))
    elif coupon_type == 'fixed':
        return max(0, total_price - float(coupon_value))
    return total_price


# ==================== 페이지 라우트 ====================

@wdcalculator_bp.route('/wdcalculator')
@login_required
def wdcalculator():
    """견적 계산 메인 페이지"""
    try:
        categories = load_additional_option_categories()
        categories = clean_categories_data(categories or [])
    except Exception:
        categories = []
    try:
        notes_categories = load_notes_categories()
        notes_categories = clean_categories_data(notes_categories or [])
    except Exception:
        notes_categories = []
    return render_template('wdcalculator/calculator.html', categories=categories, notes_categories=notes_categories)


@wdcalculator_bp.route('/wdcalculator/product-settings')
@login_required
def wdcalculator_product_settings():
    """제품 설정 페이지"""
    try:
        products = load_products() or []
    except Exception:
        products = []
    # 제품 목록 정렬: 카테고리 → 제품명 순(미분류는 맨 뒤).
    def _product_sort_key(product):
        category = str((product or {}).get('category') or '').strip()
        return (category == '', category, str((product or {}).get('name') or ''))
    products = sorted(products, key=_product_sort_key)
    try:
        categories = load_additional_option_categories()
        categories = clean_categories_data(categories or [])
    except Exception:
        categories = []
    try:
        notes_categories = load_notes_categories()
        notes_categories = clean_categories_data(notes_categories or [])
    except Exception:
        notes_categories = []
    try:
        spec_field_presets = load_spec_field_presets()
    except Exception:
        spec_field_presets = _normalize_spec_field_presets({})
    return render_template(
        'wdcalculator/product_settings.html',
        products=products,
        categories=categories,
        notes_categories=notes_categories,
        spec_field_presets=spec_field_presets,
    )


# ==================== API 라우트 ====================

@wdcalculator_bp.route('/api/wdcalculator/products', methods=['GET'])
@login_required
def api_wdcalculator_get_products():
    products = load_products()
    return jsonify({'success': True, 'products': products})


@wdcalculator_bp.route('/api/wdcalculator/products', methods=['POST'])
@login_required
def api_wdcalculator_save_product():
    try:
        data = request.get_json()
        products = load_products()
        product_id = data.get('id')
        if product_id:
            for i, product in enumerate(products):
                if product['id'] == product_id:
                    products[i] = data
                    break
        else:
            new_id = max([p['id'] for p in products], default=0) + 1
            data['id'] = new_id
            products.append(data)
        if save_products(products):
            return jsonify({'success': True, 'message': '제품이 저장되었습니다.'})
        return jsonify({'success': False, 'message': '제품 저장에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/products/<int:product_id>', methods=['DELETE'])
@login_required
def api_wdcalculator_delete_product(product_id):
    try:
        products = [p for p in load_products() if p['id'] != product_id]
        if save_products(products):
            return jsonify({'success': True, 'message': '제품이 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '제품 삭제에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/calculate', methods=['POST'])
@login_required
def api_wdcalculator_calculate():
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        width_mm = float(data.get('width_mm', 0))
        additional_options = data.get('additional_options', [])
        coupon_type = data.get('coupon_type', 'percentage')
        coupon_value = data.get('coupon_value', 0)
        products = load_products()
        product = next((p for p in products if p['id'] == product_id), None)
        if not product:
            return jsonify({'success': False, 'message': '제품을 찾을 수 없습니다.'})
        total_price = calculate_estimate(product, width_mm, additional_options)
        final_price = apply_coupon(total_price, coupon_type, coupon_value)
        return jsonify({'success': True, 'base_price': total_price, 'final_price': final_price})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/additional-options/categories', methods=['GET'])
@login_required
def api_wdcalculator_get_categories():
    categories = load_additional_option_categories()
    return jsonify({'success': True, 'categories': categories})


@wdcalculator_bp.route('/api/wdcalculator/additional-options/categories', methods=['POST'])
@login_required
def api_wdcalculator_save_category():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '데이터가 없습니다.'})
        if not data.get('name'):
            return jsonify({'success': False, 'message': '카테고리명을 입력해주세요.'})
        categories = load_additional_option_categories()
        category_id = data.get('id')
        category_data = {'name': data.get('name', '').strip(), 'options': data.get('options', [])}
        if category_id:
            found = False
            for i, category in enumerate(categories):
                if category.get('id') == category_id:
                    category['name'] = category_data['name']
                    if 'options' in category_data and category_data['options'] is not None:
                        existing_options = category.get('options', [])
                        for new_option in category_data['options']:
                            if 'id' not in new_option or not new_option.get('id'):
                                option_ids = [o.get('id') or 0 for o in existing_options if o.get('id')]
                                new_option['id'] = max(option_ids, default=0) + 1
                                existing_options.append(new_option)
                        category['options'] = existing_options
                    found = True
                    break
            if not found:
                return jsonify({'success': False, 'message': '카테고리를 찾을 수 없습니다.'})
        else:
            existing_category = next((c for c in categories if c.get('name') == category_data['name']), None)
            if existing_category:
                if 'options' in category_data and category_data['options']:
                    existing_options = existing_category.get('options', [])
                    for new_option in category_data['options']:
                        if 'id' not in new_option or not new_option.get('id'):
                            option_ids = [o.get('id') or 0 for o in existing_options if o.get('id')]
                            new_option['id'] = max(option_ids, default=0) + 1
                            existing_options.append(new_option)
                    existing_category['options'] = existing_options
            else:
                new_id = max([c.get('id', 0) for c in categories], default=0) + 1
                category_data['id'] = new_id
                category_data.setdefault('options', [])
                for option in category_data['options']:
                    if 'id' not in option or not option.get('id'):
                        all_option_ids = []
                        for cat in categories:
                            if cat.get('options'):
                                all_option_ids.extend([o.get('id') or 0 for o in cat['options'] if o.get('id')])
                        all_option_ids.extend([o.get('id') or 0 for o in category_data['options'] if o.get('id')])
                        option['id'] = max(all_option_ids, default=0) + 1
                categories.append(category_data)
        cleaned = clean_categories_data(categories)
        if save_additional_option_categories(cleaned):
            if category_id:
                updated = next((c for c in cleaned if c.get('id') == category_id), None)
                if updated:
                    return jsonify({
                        'success': True, 'message': '카테고리가 저장되었습니다.',
                        'category': {'id': updated.get('id'), 'name': updated.get('name', ''), 'options': (updated.get('options') or [])[:]}
                    })
            return jsonify({'success': True, 'message': '카테고리가 저장되었습니다.'})
        return jsonify({'success': False, 'message': '카테고리 저장에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/additional-options/categories/<int:category_id>', methods=['DELETE'])
@login_required
def api_wdcalculator_delete_category(category_id):
    try:
        categories = [c for c in load_additional_option_categories() if c['id'] != category_id]
        if save_additional_option_categories(categories):
            return jsonify({'success': True, 'message': '카테고리가 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '카테고리 삭제에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/additional-options/categories/<int:category_id>/options', methods=['POST'])
@login_required
def api_wdcalculator_save_option(category_id):
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'success': False, 'message': '옵션명을 입력해주세요.'})
        if data.get('price') is None:
            return jsonify({'success': False, 'message': '가격을 입력해주세요.'})
        categories = load_additional_option_categories()
        category = next((c for c in categories if c.get('id') == category_id), None)
        if not category:
            return jsonify({'success': False, 'message': '카테고리를 찾을 수 없습니다.'})
        option_data = {'name': data.get('name', '').strip(), 'price': int(float(data.get('price', 0)))}
        option_id = data.get('id')
        if option_id:
            found = False
            for i, option in enumerate(category.get('options', [])):
                if option.get('id') == option_id:
                    category['options'][i] = option_data
                    found = True
                    break
            if not found:
                return jsonify({'success': False, 'message': '옵션을 찾을 수 없습니다.'})
        else:
            category.setdefault('options', [])
            option_ids = [o.get('id') or 0 for o in category['options'] if o.get('id')]
            option_data['id'] = max(option_ids, default=0) + 1
            category['options'].append(option_data)
        cleaned = clean_categories_data(categories)
        if save_additional_option_categories(cleaned):
            return jsonify({'success': True, 'message': '옵션이 저장되었습니다.'})
        return jsonify({'success': False, 'message': '옵션 저장에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/additional-options/categories/<int:category_id>/options/<int:option_id>', methods=['DELETE'])
@login_required
def api_wdcalculator_delete_option(category_id, option_id):
    try:
        categories = load_additional_option_categories()
        category = next((c for c in categories if c['id'] == category_id), None)
        if not category:
            return jsonify({'success': False, 'message': '카테고리를 찾을 수 없습니다.'})
        category['options'] = [o for o in category['options'] if o.get('id') != option_id]
        if save_additional_option_categories(categories):
            return jsonify({'success': True, 'message': '옵션이 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '옵션 삭제에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/notes/categories', methods=['GET'])
@login_required
def api_wdcalculator_get_notes_categories():
    categories = load_notes_categories()
    return jsonify({'success': True, 'categories': categories})


@wdcalculator_bp.route('/api/wdcalculator/notes/categories', methods=['POST'])
@login_required
def api_wdcalculator_save_notes_category():
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'success': False, 'message': '카테고리명을 입력해주세요.'})
        categories = load_notes_categories()
        category_id = data.get('id')
        if category_id:
            category = next((c for c in categories if c.get('id') == category_id), None)
            if not category:
                return jsonify({'success': False, 'message': '카테고리를 찾을 수 없습니다.'})
            category['name'] = data.get('name', '').strip()
            if 'options' in data and data['options'] is not None:
                category['options'] = data['options']
        else:
            category_data = {'name': data.get('name', '').strip(), 'options': data.get('options', [])}
            category_data['id'] = max([c.get('id', 0) for c in categories] + [0]) + 1
            categories.append(category_data)
        if save_notes_categories(categories):
            return_category = next((c for c in categories if c.get('id') == (category_id or category_data['id'])), None) if category_id else category_data
            if return_category:
                return jsonify({
                    'success': True, 'message': '비고 카테고리가 저장되었습니다.',
                    'category': {'id': return_category.get('id'), 'name': return_category.get('name'), 'options': (return_category.get('options') or [])[:]}
                })
            return jsonify({'success': True, 'message': '비고 카테고리가 저장되었습니다.'})
        return jsonify({'success': False, 'message': '비고 카테고리 저장에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/notes/categories/<int:category_id>', methods=['DELETE'])
@login_required
def api_wdcalculator_delete_notes_category(category_id):
    try:
        categories = [c for c in load_notes_categories() if c.get('id') != category_id]
        if save_notes_categories(categories):
            return jsonify({'success': True, 'message': '비고 카테고리가 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '비고 카테고리 삭제에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/notes/categories/<int:category_id>/options', methods=['POST'])
@login_required
def api_wdcalculator_save_notes_option(category_id):
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'success': False, 'message': '옵션명을 입력해주세요.'})
        categories = load_notes_categories()
        category = next((c for c in categories if c.get('id') == category_id), None)
        if not category:
            return jsonify({'success': False, 'message': '카테고리를 찾을 수 없습니다.'})
        option_data = {'name': data.get('name', '').strip(), 'price': 0}
        option_id = data.get('id')
        if option_id:
            option = next((o for o in category.get('options', []) if o.get('id') == option_id), None)
            if not option:
                return jsonify({'success': False, 'message': '옵션을 찾을 수 없습니다.'})
            option.update(option_data)
        else:
            category.setdefault('options', [])
            existing_ids = [o.get('id') for o in category['options'] if o and o.get('id') is not None]
            option_data['id'] = max(existing_ids + [0]) + 1
            category['options'].append(option_data)
        if save_notes_categories(categories):
            return jsonify({'success': True, 'message': '비고 옵션이 저장되었습니다.', 'option': option_data})
        return jsonify({'success': False, 'message': '비고 옵션 저장에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/notes/categories/<int:category_id>/options/<int:option_id>', methods=['DELETE'])
@login_required
def api_wdcalculator_delete_notes_option(category_id, option_id):
    try:
        categories = load_notes_categories()
        category = next((c for c in categories if c.get('id') == category_id), None)
        if not category:
            return jsonify({'success': False, 'message': '카테고리를 찾을 수 없습니다.'})
        original = category.get('options', [])
        for opt in original:
            if opt and opt.get('id') is None:
                existing_ids = [o.get('id') for o in original if o and o.get('id') is not None]
                opt['id'] = max(existing_ids + [0]) + 1
        remaining = []
        found = False
        for opt in original:
            if not opt:
                continue
            oid = opt.get('id')
            if oid is not None and int(oid) == option_id:
                found = True
                continue
            remaining.append(opt)
        if not found and 0 <= option_id < len(original):
            remaining = [o for i, o in enumerate(original) if i != option_id]
        elif not found:
            return jsonify({'success': False, 'message': f'삭제할 옵션을 찾을 수 없습니다. (option_id: {option_id})'})
        category['options'] = remaining
        if save_notes_categories(categories):
            return jsonify({'success': True, 'message': '비고 옵션이 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '비고 옵션 삭제에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/spec-field-presets', methods=['GET'])
@login_required
def api_wdcalculator_get_spec_field_presets():
    """ERP 스펙 필드(색상/손잡이/내부/기타) 드롭다운 프리셋 전체 조회"""
    return jsonify({'success': True, 'spec_field_presets': load_spec_field_presets()})


@wdcalculator_bp.route('/api/wdcalculator/spec-field-presets', methods=['POST'])
@login_required
def api_wdcalculator_save_spec_field_preset():
    """ERP 스펙 필드 프리셋 저장.

    - ``{field, values:[...]}``: 해당 필드 프리셋 전체 교체
    - ``{field, name, id?}``: 단건 추가(또는 id 지정 시 수정)
    """
    try:
        data = request.get_json() or {}
        field = (data.get('field') or '').strip()
        if field not in SPEC_PRESET_FIELDS:
            return jsonify({'success': False, 'message': '지원하지 않는 스펙 필드입니다.'})
        presets = load_spec_field_presets()
        # 전체 교체 모드
        if isinstance(data.get('values'), list):
            presets[field] = [{'name': str(v or '').strip()} for v in data['values']]
            if save_spec_field_presets(presets):
                return jsonify({
                    'success': True, 'message': '프리셋이 저장되었습니다.',
                    'spec_field_presets': load_spec_field_presets(),
                })
            return jsonify({'success': False, 'message': '프리셋 저장에 실패했습니다.'})
        # 단건 추가/수정 모드
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'message': '값을 입력해주세요.'})
        field_items = presets.get(field, [])
        preset_id = data.get('id')
        if preset_id:
            target = next((p for p in field_items if p.get('id') == preset_id), None)
            if not target:
                return jsonify({'success': False, 'message': '프리셋을 찾을 수 없습니다.'})
            target['name'] = name
        else:
            existing_ids = [p.get('id') for p in field_items if p.get('id') is not None]
            field_items.append({'id': max(existing_ids + [0]) + 1, 'name': name})
            presets[field] = field_items
        if save_spec_field_presets(presets):
            saved_field = load_spec_field_presets().get(field, [])
            saved = next((p for p in saved_field if p.get('name') == name), None)
            return jsonify({
                'success': True, 'message': '프리셋이 저장되었습니다.',
                'preset': saved, 'spec_field_presets': {field: saved_field},
            })
        return jsonify({'success': False, 'message': '프리셋 저장에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/spec-field-presets/<field>/<int:preset_id>', methods=['DELETE'])
@login_required
def api_wdcalculator_delete_spec_field_preset(field, preset_id):
    """ERP 스펙 필드 프리셋 단건 삭제"""
    try:
        field = (field or '').strip()
        if field not in SPEC_PRESET_FIELDS:
            return jsonify({'success': False, 'message': '지원하지 않는 스펙 필드입니다.'})
        presets = load_spec_field_presets()
        presets[field] = [p for p in presets.get(field, []) if p.get('id') != preset_id]
        if save_spec_field_presets(presets):
            return jsonify({'success': True, 'message': '프리셋이 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '프리셋 삭제에 실패했습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/save-estimate', methods=['POST'])
@login_required
def api_wdcalculator_save_estimate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '요청 데이터가 없습니다.'})
        estimate_id = data.get('estimate_id')
        order_id = data.get('order_id')
        customer_name = (data.get('customer_name') or '').strip()
        estimate_data = data.get('estimate_data', {})
        if not customer_name:
            return jsonify({'success': False, 'message': '고객명을 입력해주세요.'})
        if not estimate_data:
            return jsonify({'success': False, 'message': '견적 데이터가 없습니다.'})
        db = get_wdcalculator_db()
        foms_db = None
        order = None
        if order_id:
            try:
                order_id = int(order_id)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': '주문 ID가 올바르지 않습니다.'})
            foms_db = get_db()
            order = foms_db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
            if not order:
                return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'})
        if estimate_id:
            estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
            if not estimate:
                return jsonify({'success': False, 'message': '수정할 견적을 찾을 수 없습니다.'})
            try:
                db.add(EstimateHistory(estimate_id=estimate.id, estimate_data=estimate.estimate_data))
            except Exception as history_error:
                print(f"[wdcalculator-save] history snapshot 실패(계속 진행): {history_error}")
            estimate.customer_name = customer_name
            estimate.estimate_data = estimate_data
            message = '견적이 수정되었습니다.'
        else:
            estimate = Estimate(customer_name=customer_name, estimate_data=estimate_data)
            db.add(estimate)
            message = '견적이 저장되었습니다.'
        matched = False
        if order_id:
            db.flush()
            existing = db.query(EstimateOrderMatch).filter(
                EstimateOrderMatch.estimate_id == estimate.id,
                EstimateOrderMatch.order_id == order_id,
            ).first()
            if not existing:
                db.add(EstimateOrderMatch(estimate_id=estimate.id, order_id=order_id))
            matched = True
        db.commit()
        if order_id and foms_db and order:
            try:
                from datetime import datetime, timezone
                from sqlalchemy.orm.attributes import flag_modified
                sd = copy.deepcopy(order.structured_data or {})
                meta = sd.get('meta')
                if not isinstance(meta, dict):
                    meta = {}
                if meta.get('wdc_estimate_id') != estimate.id:
                    meta['wdc_estimate_id'] = estimate.id
                    meta['wdc_synced_at'] = datetime.now(timezone.utc).isoformat()
                    sd['meta'] = meta
                    order.structured_data = sd
                    flag_modified(order, 'structured_data')
                    foms_db.commit()
            except Exception as link_error:
                foms_db.rollback()
                print(f"[wdcalculator-save] order_id={order_id} meta 링크 실패(계속 진행): {link_error}")
        return jsonify({
            'success': True,
            'message': message,
            'estimate_id': estimate.id,
            'matched': matched,
            'order_id': order_id,
        })
    except Exception as e:
        db = get_wdcalculator_db()
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/search-estimates', methods=['GET'])
@login_required
def api_wdcalculator_search_estimates():
    try:
        customer_name = (request.args.get('customer_name') or '').strip()
        db = get_wdcalculator_db()
        query = db.query(Estimate)
        if customer_name:
            query = query.filter(Estimate.customer_name.ilike(f'%{customer_name}%'))
        estimates = query.order_by(Estimate.created_at.desc()).limit(50).all()
        return jsonify({'success': True, 'estimates': [e.to_dict() for e in estimates], 'count': len(estimates)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/estimate/<int:estimate_id>', methods=['GET', 'DELETE'])
@login_required
def api_wdcalculator_estimate(estimate_id):
    try:
        db = get_wdcalculator_db()
        estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
        if not estimate:
            return jsonify({'success': False, 'message': '견적을 찾을 수 없습니다.'})
        if request.method == 'DELETE':
            db.delete(estimate)
            db.commit()
            return jsonify({'success': True, 'message': '견적이 삭제되었습니다.'})
        return jsonify({'success': True, 'estimate': estimate.to_dict()})
    except Exception as e:
        db = get_wdcalculator_db()
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/match-order', methods=['POST'])
@login_required
def api_wdcalculator_match_order():
    try:
        data = request.get_json()
        estimate_id = data.get('estimate_id')
        order_id = data.get('order_id')
        if not estimate_id or not order_id:
            return jsonify({'success': False, 'message': '견적 ID와 주문 ID가 필요합니다.'})
        wd_db = get_wdcalculator_db()
        estimate = wd_db.query(Estimate).filter(Estimate.id == estimate_id).first()
        if not estimate:
            return jsonify({'success': False, 'message': '견적을 찾을 수 없습니다.'})
        foms_db = get_db()
        order = foms_db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'})
        existing = wd_db.query(EstimateOrderMatch).filter(
            EstimateOrderMatch.estimate_id == estimate_id, EstimateOrderMatch.order_id == order_id
        ).first()
        if existing:
            return jsonify({'success': False, 'message': '이미 매칭된 주문입니다.'})
        match = EstimateOrderMatch(estimate_id=estimate_id, order_id=order_id)
        wd_db.add(match)
        wd_db.commit()
        return jsonify({'success': True, 'message': '견적과 주문이 매칭되었습니다.', 'match_id': match.id})
    except Exception as e:
        wd_db = get_wdcalculator_db()
        wd_db.rollback()
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/orders/<int:order_id>/wdc-estimate-sync', methods=['POST'])
@login_required
def api_orders_wdc_estimate_sync(order_id):
    """ERP 주문 저장(SSOT) 직후 호출되는 보조 동기화 엔드포인트.

    계산기 견적(:class:`Estimate`)을 upsert하고 주문과 멱등 매칭한다. ERP 주문
    저장은 이미 완료된 전제이며, 본 엔드포인트 실패는 주문 저장을 되돌리지 않는다
    (클라이언트가 경고만 표시; fail-open + 로그). 단일 ``wd_db`` 트랜잭션으로
    upsert+매칭을 원자 처리한다.

    Args:
        order_id: 매칭 대상 FOMS 주문 id (URL).

    Returns:
        ``{'success', 'estimate_id', 'matched'}`` JSON. 실패 시 ``message`` 포함.
    """
    try:
        data = request.get_json() or {}
        customer_name = (data.get('customer_name') or '').strip()
        estimate_data = data.get('estimate_data') or {}
        estimate_id = data.get('estimate_id')
        if not estimate_data:
            return jsonify({'success': False, 'message': '견적 데이터가 없습니다.'})
        # 주문 존재/active 검증 (FOMS DB) — 권한 경계는 match-order와 동일
        foms_db = get_db()
        order = foms_db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'})
        if not customer_name:
            customer_name = (getattr(order, 'customer_name', None) or '고객').strip() or '고객'
        wd_db = get_wdcalculator_db()
        # 1) Estimate upsert
        estimate = None
        if estimate_id:
            estimate = wd_db.query(Estimate).filter(Estimate.id == estimate_id).first()
        if estimate:
            try:
                wd_db.add(EstimateHistory(estimate_id=estimate.id, estimate_data=estimate.estimate_data))
            except Exception as hist_err:
                print(f"[wdc-estimate-sync] history snapshot 실패(계속 진행): {hist_err}")
            estimate.customer_name = customer_name
            estimate.estimate_data = estimate_data
        else:
            estimate = Estimate(customer_name=customer_name, estimate_data=estimate_data)
            wd_db.add(estimate)
        wd_db.flush()  # estimate.id 확보
        # 2) 멱등 매칭 (중복은 오류 아님)
        existing = wd_db.query(EstimateOrderMatch).filter(
            EstimateOrderMatch.estimate_id == estimate.id,
            EstimateOrderMatch.order_id == order_id,
        ).first()
        if not existing:
            wd_db.add(EstimateOrderMatch(estimate_id=estimate.id, order_id=order_id))
        wd_db.commit()
        # 3) FOMS 주문 structured_data.meta에 estimate_id 영속화(멱등 링크 = SSOT).
        #    이미 동일 id면 쓰지 않는다. 링크 실패는 견적 저장을 되돌리지 않는다(fail-open + 로그).
        try:
            from datetime import datetime, timezone
            from sqlalchemy.orm.attributes import flag_modified
            sd = copy.deepcopy(order.structured_data or {})
            meta = sd.get('meta')
            if not isinstance(meta, dict):
                meta = {}
            if meta.get('wdc_estimate_id') != estimate.id:
                meta['wdc_estimate_id'] = estimate.id
                meta['wdc_synced_at'] = datetime.now(timezone.utc).isoformat()
                sd['meta'] = meta
                order.structured_data = sd
                flag_modified(order, 'structured_data')
                foms_db.commit()
        except Exception as link_err:
            foms_db.rollback()
            print(f"[wdc-estimate-sync] meta.wdc_estimate_id 영속화 실패(계속 진행): {link_err}")
        return jsonify({'success': True, 'estimate_id': estimate.id, 'matched': True})
    except Exception as e:
        wd_db = get_wdcalculator_db()
        wd_db.rollback()
        print(f"[wdc-estimate-sync] order_id={order_id} 동기화 실패: {e}")
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/order-estimates/<int:order_id>', methods=['GET'])
@login_required
def api_wdcalculator_get_order_estimates(order_id):
    try:
        foms_db = get_db()
        order = foms_db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'})
        wd_db = get_wdcalculator_db()
        matches = wd_db.query(EstimateOrderMatch).filter(EstimateOrderMatch.order_id == order_id).all()
        estimates = []
        for match in matches:
            est = wd_db.query(Estimate).filter(Estimate.id == match.estimate_id).first()
            if est:
                estimates.append(est.to_dict())
        order_payment = _build_order_payment_payload(order)
        return jsonify({
            'success': True,
            'estimates': estimates,
            'count': len(estimates),
            'order_payment': order_payment,
            'order_payment_amount': order_payment['amount'],
            'order_payment_label': order_payment['label'],
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@wdcalculator_bp.route('/api/wdcalculator/search-orders', methods=['GET'])
@login_required
def api_wdcalculator_search_orders():
    try:
        customer_name = (request.args.get('customer_name') or '').strip()
        if not customer_name:
            return jsonify({'success': False, 'message': '고객명을 입력해주세요.'})
        foms_db = get_db()
        search_term = f'%{customer_name}%'
        structured_customer_name = Order.structured_data[('parties', 'customer', 'name')].as_string()
        orders = foms_db.query(Order).filter(
            Order.active_filter(),
            or_(
                Order.customer_name.ilike(search_term),
                structured_customer_name.ilike(search_term),
            ),
        ).order_by(Order.created_at.desc()).limit(50).all()
        needle = _normalize_for_search(customer_name).lower()
        orders_list = []
        for order in orders:
            payload = _build_order_match_payload(order)
            display_name = _normalize_for_search(payload.get('customer_name')).lower()
            if needle not in display_name:
                continue
            orders_list.append(payload)
        return jsonify({'success': True, 'orders': orders_list, 'count': len(orders_list)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
