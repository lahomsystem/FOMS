"""
견적서/계약서 생성·관리 서비스.

주문(Order)의 structured_data에서 고객·아이템 정보를 추출하여
OrderEstimate 레코드를 생성하고, 견적번호를 자동 채번한다.
"""
import copy
import datetime
import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import Order, OrderEstimate
from constants import ESTIMATE_PAYMENT_INFO

logger = logging.getLogger(__name__)


def generate_estimate_number(db: Session, date_str: str) -> str:
    """해당 날짜에 대한 다음 견적번호를 생성한다.

    Args:
        db: DB 세션
        date_str: YYYY-MM-DD 형식 날짜

    Returns:
        'YYYYMMDD_N' 형식 견적번호 (예: 20260326_1)
    """
    date_prefix = date_str.replace('-', '')
    like_pattern = f'{date_prefix}_%'

    existing = (
        db.query(OrderEstimate.estimate_number)
        .filter(OrderEstimate.estimate_number.like(like_pattern))
        .all()
    )

    max_seq = 0
    for (num,) in existing:
        try:
            seq = int(num.split('_')[-1])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, IndexError):
            continue

    return f'{date_prefix}_{max_seq + 1}'


def _format_spec_rows(item: dict) -> str:
    """spec_rows 배열에서 다중 규격 표시 문자열을 생성한다.

    각 규격 행을 "폭x깊이x높이" 형식으로 변환하고 개행으로 연결한다.
    spec_rows가 없으면 item['spec'] 그대로 반환한다.

    Args:
        item: structured_data.items의 단일 항목 딕셔너리

    Returns:
        "3000x620x2300\\n3100x620x2310" 같은 다중 라인 문자열
    """
    spec_rows = item.get('spec_rows') or []
    if not spec_rows:
        return item.get('spec') or ''

    lines = []
    for row in spec_rows:
        w = str(row.get('spec_width') or row.get('w') or '').strip()
        d = str(row.get('spec_depth') or row.get('d') or '').strip()
        h = str(row.get('spec_height') or row.get('h') or '').strip()
        parts = [p for p in [w, d, h] if p]
        if parts:
            lines.append('x'.join(parts))

    return '\n'.join(lines) if lines else (item.get('spec') or '')


def extract_estimate_data_from_order(order: Order) -> dict:
    """주문의 structured_data에서 견적서에 필요한 필드를 추출한다.

    Returns:
        dict with keys: customer_name, customer_phone, site_address,
        construction_date, manager_name, manager_phone, items, total_amount,
        deposit_amount, balance_amount
    """
    sd = order.structured_data or {}
    parties = sd.get('parties', {})
    customer = parties.get('customer', {})
    manager = parties.get('manager', {})
    site = sd.get('site', {})
    schedule = sd.get('schedule', {})
    payments = sd.get('payments', {})

    customer_name = customer.get('name') or order.customer_name or ''
    customer_phone = customer.get('phone') or order.phone or ''
    site_address = site.get('address_full') or order.address or ''
    construction_date = (schedule.get('construction') or {}).get('date')
    manager_name = manager.get('name') or order.manager_name or ''
    manager_phone = manager.get('phone') or ''

    orderer = parties.get('orderer', {})
    orderer_name = str(orderer.get('name') or '')
    is_lahom = '라홈' in orderer_name

    raw_items = sd.get('items') or []
    estimate_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        estimate_items.append({
            'product_name': item.get('product_name') or '',
            'spec': _format_spec_rows(item),
            'color': item.get('color') or '',
            'option_detail': item.get('option_detail') or '',
            'quantity': int(item.get('quantity') or 1),
            'unit_price': int(item.get('price') or 0),
            'amount': int(item.get('price') or 0) * int(item.get('quantity') or 1),
        })

    total_amount = sum(it['amount'] for it in estimate_items)
    # ERP Beta는 payments.deposit을 평탄 숫자로 저장 (예: 100000).
    # 구형 데이터는 dict({amount: ...}) 형태일 수 있으므로 양쪽 처리.
    raw_deposit = payments.get('deposit') or 0
    if isinstance(raw_deposit, dict):
        deposit_amount = int(raw_deposit.get('amount') or 0)
    else:
        deposit_amount = int(raw_deposit or 0)
    balance_amount = total_amount - deposit_amount
    if balance_amount < 0:
        balance_amount = 0

    return {
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'site_address': site_address,
        'construction_date': construction_date,
        'manager_name': manager_name,
        'manager_phone': manager_phone,
        'is_lahom': is_lahom,
        'items': estimate_items,
        'total_amount': total_amount,
        'deposit_amount': int(deposit_amount or 0),
        'balance_amount': balance_amount,
    }


def create_estimate(
    db: Session,
    order: Order,
    *,
    override_data: Optional[dict] = None,
    created_by_user_id: Optional[int] = None,
) -> OrderEstimate:
    """주문 기반으로 견적서를 생성한다.

    Args:
        db: DB 세션
        order: 대상 주문
        override_data: 자동 추출값을 덮어쓸 항목 (프론트에서 수정한 값)
        created_by_user_id: 생성자 user ID

    Returns:
        생성된 OrderEstimate 인스턴스 (flush 완료, commit은 호출자 책임)
    """
    today = datetime.date.today().strftime('%Y-%m-%d')
    data = extract_estimate_data_from_order(order)

    if override_data:
        for key in ('customer_name', 'customer_phone', 'site_address',
                    'construction_date', 'manager_name', 'manager_phone',
                    'items', 'total_amount', 'deposit_amount', 'balance_amount',
                    'notes'):
            if key in override_data:
                data[key] = override_data[key]

        if 'items' in override_data and 'total_amount' not in override_data:
            data['total_amount'] = sum(
                int(it.get('amount') or 0) for it in data['items']
            )
        if 'total_amount' in data or 'deposit_amount' in data:
            data['balance_amount'] = data.get('total_amount', 0) - data.get('deposit_amount', 0)
            if data['balance_amount'] < 0:
                data['balance_amount'] = 0

    estimate_date = (override_data or {}).get('estimate_date') or today
    estimate_number = generate_estimate_number(db, estimate_date)

    estimate = OrderEstimate(
        order_id=order.id,
        estimate_number=estimate_number,
        customer_name=data['customer_name'],
        customer_phone=data['customer_phone'],
        site_address=data['site_address'],
        estimate_date=estimate_date,
        construction_date=data.get('construction_date'),
        manager_name=data.get('manager_name'),
        manager_phone=data.get('manager_phone'),
        items=data['items'],
        total_amount=data['total_amount'],
        deposit_amount=data.get('deposit_amount', 0),
        balance_amount=data.get('balance_amount', data['total_amount']),
        payment_info=copy.deepcopy(ESTIMATE_PAYMENT_INFO),
        status='DRAFT',
        notes=data.get('notes'),
        created_by_user_id=created_by_user_id,
    )

    db.add(estimate)
    db.flush()

    logger.info(
        "견적서 생성: #%s (주문 %d, 금액 %s원)",
        estimate.estimate_number, order.id, f'{estimate.total_amount:,}'
    )
    return estimate


def update_estimate(
    db: Session,
    estimate: OrderEstimate,
    update_data: dict,
) -> OrderEstimate:
    """기존 견적서를 수정한다. DRAFT 상태에서만 수정 가능.

    Args:
        db: DB 세션
        estimate: 수정 대상 견적서
        update_data: 변경할 필드 dict

    Returns:
        수정된 OrderEstimate
    """
    allowed_fields = {
        'customer_name', 'customer_phone', 'site_address',
        'estimate_date', 'construction_date',
        'manager_name', 'manager_phone',
        'items', 'total_amount', 'deposit_amount', 'balance_amount',
        'notes', 'status',
    }

    for key, val in update_data.items():
        if key in allowed_fields:
            setattr(estimate, key, val)

    if 'items' in update_data:
        flag_modified(estimate, 'items')
        if 'total_amount' not in update_data:
            estimate.total_amount = sum(
                int(it.get('amount') or 0) for it in (estimate.items or [])
            )

    if 'total_amount' in update_data or 'deposit_amount' in update_data or 'items' in update_data:
        estimate.balance_amount = max(0, (estimate.total_amount or 0) - (estimate.deposit_amount or 0))

    estimate.updated_at = datetime.datetime.now()

    logger.info("견적서 수정: #%s", estimate.estimate_number)
    return estimate
