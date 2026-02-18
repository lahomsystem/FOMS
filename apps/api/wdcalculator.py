"""WDCalculator (가구 견적 계산기) API Blueprint.

페이지: /wdcalculator, /wdcalculator/product-settings
API: /api/wdcalculator/*
"""
import os
import json
from flask import Blueprint, request, jsonify, render_template
from db import get_db
from models import Order
from apps.auth import login_required
from wdcalculator_db import get_wdcalculator_db
from wdcalculator_models import Estimate, EstimateOrderMatch, EstimateHistory

# 프로젝트 루트 기준 데이터 경로
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WD_CALCULATOR_DATA_PATH = os.path.join(_PROJECT_ROOT, 'data', 'products.json')
WD_ADDITIONAL_OPTIONS_PATH = os.path.join(_PROJECT_ROOT, 'data', 'additional_options.json')
WD_NOTES_CATEGORIES_PATH = os.path.join(_PROJECT_ROOT, 'data', 'notes_categories.json')

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


def load_additional_option_categories():
    """추가 옵션 카테고리 데이터를 JSON 파일에서 로드"""
    try:
        if os.path.exists(WD_ADDITIONAL_OPTIONS_PATH):
            try:
                with open(WD_ADDITIONAL_OPTIONS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return clean_categories_data(data.get('categories', []))
            except UnicodeDecodeError:
                with open(WD_ADDITIONAL_OPTIONS_PATH, 'r', encoding='cp949') as f:
                    data = json.load(f)
                    return clean_categories_data(data.get('categories', []))
        return []
    except Exception as e:
        print(f"Error loading additional option categories: {e}")
        return []


def save_additional_option_categories(categories):
    """추가 옵션 카테고리 데이터를 JSON 파일에 저장"""
    try:
        os.makedirs(os.path.dirname(WD_ADDITIONAL_OPTIONS_PATH), exist_ok=True)
        with open(WD_ADDITIONAL_OPTIONS_PATH, 'w', encoding='utf-8') as f:
            json.dump({'categories': categories}, f, ensure_ascii=True, indent=2)
        return True
    except Exception as e:
        print(f"Error saving additional option categories: {e}")
        return False


def load_notes_categories():
    """비고 카테고리 데이터를 JSON 파일에서 로드"""
    try:
        if os.path.exists(WD_NOTES_CATEGORIES_PATH):
            try:
                with open(WD_NOTES_CATEGORIES_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return clean_categories_data(data.get('categories', []))
            except UnicodeDecodeError:
                with open(WD_NOTES_CATEGORIES_PATH, 'r', encoding='cp949') as f:
                    data = json.load(f)
                    return clean_categories_data(data.get('categories', []))
        return []
    except Exception as e:
        print(f"Error loading notes categories: {e}")
        return []


def save_notes_categories(categories):
    """비고 카테고리 데이터를 JSON 파일에 저장"""
    try:
        os.makedirs(os.path.dirname(WD_NOTES_CATEGORIES_PATH), exist_ok=True)
        with open(WD_NOTES_CATEGORIES_PATH, 'w', encoding='utf-8') as f:
            json.dump({'categories': categories}, f, ensure_ascii=True, indent=2)
        return True
    except Exception as e:
        print(f"Error saving notes categories: {e}")
        return False


def load_products():
    """제품 데이터를 JSON 파일에서 로드"""
    try:
        if os.path.exists(WD_CALCULATOR_DATA_PATH):
            try:
                with open(WD_CALCULATOR_DATA_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f).get('products', [])
            except UnicodeDecodeError:
                with open(WD_CALCULATOR_DATA_PATH, 'r', encoding='cp949') as f:
                    return json.load(f).get('products', [])
        return []
    except Exception as e:
        print(f"Error loading products: {e}")
        return []


def save_products(products):
    """제품 데이터를 JSON 파일에 저장"""
    try:
        os.makedirs(os.path.dirname(WD_CALCULATOR_DATA_PATH), exist_ok=True)
        with open(WD_CALCULATOR_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump({'products': products}, f, ensure_ascii=True, indent=2)
        return True
    except Exception as e:
        print(f"Error saving products: {e}")
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
    return render_template('wdcalculator/product_settings.html', products=products, categories=categories, notes_categories=notes_categories)


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


@wdcalculator_bp.route('/api/wdcalculator/save-estimate', methods=['POST'])
@login_required
def api_wdcalculator_save_estimate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '요청 데이터가 없습니다.'})
        estimate_id = data.get('estimate_id')
        customer_name = (data.get('customer_name') or '').strip()
        estimate_data = data.get('estimate_data', {})
        if not customer_name:
            return jsonify({'success': False, 'message': '고객명을 입력해주세요.'})
        if not estimate_data:
            return jsonify({'success': False, 'message': '견적 데이터가 없습니다.'})
        db = get_wdcalculator_db()
        if estimate_id:
            estimate = db.query(Estimate).filter(Estimate.id == estimate_id).first()
            if not estimate:
                return jsonify({'success': False, 'message': '수정할 견적을 찾을 수 없습니다.'})
            try:
                db.add(EstimateHistory(estimate_id=estimate.id, estimate_data=estimate.estimate_data))
            except Exception:
                pass
            estimate.customer_name = customer_name
            estimate.estimate_data = estimate_data
            message = '견적이 수정되었습니다.'
        else:
            estimate = Estimate(customer_name=customer_name, estimate_data=estimate_data)
            db.add(estimate)
            message = '견적이 저장되었습니다.'
        db.commit()
        return jsonify({'success': True, 'message': message, 'estimate_id': estimate.id})
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
        order = foms_db.query(Order).filter(Order.id == order_id).first()
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


@wdcalculator_bp.route('/api/wdcalculator/order-estimates/<int:order_id>', methods=['GET'])
@login_required
def api_wdcalculator_get_order_estimates(order_id):
    try:
        foms_db = get_db()
        order = foms_db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'})
        wd_db = get_wdcalculator_db()
        matches = wd_db.query(EstimateOrderMatch).filter(EstimateOrderMatch.order_id == order_id).all()
        estimates = []
        for match in matches:
            est = wd_db.query(Estimate).filter(Estimate.id == match.estimate_id).first()
            if est:
                estimates.append(est.to_dict())
        return jsonify({'success': True, 'estimates': estimates, 'count': len(estimates)})
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
        orders = foms_db.query(Order).filter(
            Order.customer_name.ilike(f'%{customer_name}%')
        ).order_by(Order.created_at.desc()).limit(50).all()
        orders_list = [{
            'id': o.id, 'customer_name': o.customer_name, 'phone': o.phone, 'address': o.address,
            'product': o.product, 'status': o.status, 'received_date': o.received_date.isoformat() if o.received_date else None
        } for o in orders]
        return jsonify({'success': True, 'orders': orders_list, 'count': len(orders_list)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
