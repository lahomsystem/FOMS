"""대시보드 Blueprint.

/regional_dashboard - 지방 주문 대시보드
/metropolitan_dashboard - 수도권 주문 대시보드
/self_measurement_dashboard - 자가실측 대시보드
"""
import datetime
from datetime import date, timedelta
from flask import Blueprint, render_template, request
from sqlalchemy import or_, and_, func, String

from apps.auth import login_required
from apps.erp import apply_erp_display_fields_to_orders
from db import get_db
from models import Order
from constants import STATUS

dashboards_bp = Blueprint('dashboards', __name__, url_prefix='')


@dashboards_bp.route('/regional_dashboard')
@login_required
def regional_dashboard():
    """지방 주문 관리 대시보드."""
    db = get_db()
    search_query = request.args.get('search_query', '').strip()

    base_query = db.query(Order).filter(
        Order.is_regional == True,
        Order.status != 'DELETED'
    )

    if search_query:
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            search_id = int(search_query)
            id_conditions.append(Order.id == search_id)
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))

        base_query = base_query.filter(
            or_(
                Order.customer_name.ilike(search_term),
                Order.phone.ilike(search_term),
                Order.address.ilike(search_term),
                Order.product.ilike(search_term),
                Order.regional_memo.ilike(search_term),
                Order.notes.ilike(search_term),
                *id_conditions
            )
        )

    all_regional_orders = base_query.order_by(Order.id.desc()).all()
    apply_erp_display_fields_to_orders(all_regional_orders)
    today = date.today()

    completed_orders = [o for o in all_regional_orders if o.status == 'COMPLETED']
    scheduled_orders = [o for o in all_regional_orders if o.status == 'SCHEDULED']
    hold_orders = [o for o in all_regional_orders if o.status == 'ON_HOLD']

    shipping_alerts = []
    for order in all_regional_orders:
        if (getattr(order, 'measurement_completed', False) and
            order.shipping_scheduled_date and order.shipping_scheduled_date.strip() and
            order.status not in ['COMPLETED', 'ON_HOLD']):
            try:
                shipping_date = datetime.datetime.strptime(order.shipping_scheduled_date, '%Y-%m-%d').date()
                if shipping_date >= today:
                    shipping_alerts.append(order)
            except (ValueError, TypeError):
                pass

    shipping_completed_orders = []
    for order in all_regional_orders:
        if (order.shipping_scheduled_date and order.shipping_scheduled_date.strip() and
            order.status not in ['COMPLETED', 'ON_HOLD']):
            try:
                shipping_date = datetime.datetime.strptime(order.shipping_scheduled_date, '%Y-%m-%d').date()
                if shipping_date < today:
                    shipping_completed_orders.append(order)
            except (ValueError, TypeError):
                pass

    shipping_alert_ids = {o.id for o in shipping_alerts}
    shipping_completed_ids = {o.id for o in shipping_completed_orders}
    pending_orders = [
        o for o in all_regional_orders
        if (o.status not in ['COMPLETED', 'ON_HOLD', 'SCHEDULED'] and
            o.id not in shipping_alert_ids and o.id not in shipping_completed_ids and
            (not getattr(o, 'measurement_completed', False) or
             not o.shipping_scheduled_date or not o.shipping_scheduled_date.strip()))
    ]

    shipping_alerts.sort(key=lambda x: datetime.datetime.strptime(x.shipping_scheduled_date, '%Y-%m-%d').date())
    shipping_completed_orders.sort(key=lambda x: datetime.datetime.strptime(x.shipping_scheduled_date, '%Y-%m-%d').date())

    return render_template('regional_dashboard.html',
        pending_orders=pending_orders,
        scheduled_orders=scheduled_orders,
        completed_orders=completed_orders,
        hold_orders=hold_orders,
        shipping_alerts=shipping_alerts,
        shipping_completed_orders=shipping_completed_orders,
        STATUS=STATUS,
        search_query=search_query,
        today=today.strftime('%Y-%m-%d'),
        tomorrow=(today + timedelta(days=1)).strftime('%Y-%m-%d')
    )


@dashboards_bp.route('/metropolitan_dashboard')
@login_required
def metropolitan_dashboard():
    """수도권 주문 대시보드."""
    db = get_db()
    search_query = request.args.get('search_query', '').strip()

    def get_filtered_orders(q):
        if not search_query:
            return q
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            id_conditions.append(Order.id == int(search_query))
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))
        return q.filter(or_(
            Order.customer_name.ilike(search_term),
            Order.phone.ilike(search_term),
            Order.address.ilike(search_term),
            Order.product.ilike(search_term),
            Order.notes.ilike(search_term),
            Order.manager_name.ilike(search_term),
            *id_conditions
        ))

    base_query = db.query(Order).filter(Order.is_regional == False)

    urgent_alerts = get_filtered_orders(base_query.filter(
        Order.status.in_(['MEASURED']),
        Order.measurement_date != None,
        Order.measurement_date != '',
        func.date(Order.measurement_date) == date.today()
    )).order_by(Order.measurement_date.asc()).all()

    measurement_alerts = get_filtered_orders(base_query.filter(
        Order.status.in_(['MEASURED']),
        Order.measurement_date != None,
        Order.measurement_date != '',
        func.date(Order.measurement_date) < date.today(),
        or_(Order.scheduled_date == None, Order.scheduled_date == '')
    )).order_by(Order.measurement_date.asc()).all()

    pre_measurement_alerts = get_filtered_orders(base_query.filter(or_(
        and_(
            Order.status.in_(['RECEIVED', 'MEASURED']),
            Order.measurement_date != None,
            Order.measurement_date != '',
            func.date(Order.measurement_date) > date.today()
        ),
        and_(
            Order.status == 'RECEIVED',
            or_(Order.measurement_date == None, Order.measurement_date == '')
        )
    ))).order_by(Order.measurement_date.asc()).all()

    installation_alerts = get_filtered_orders(base_query.filter(
        Order.status.in_(['SCHEDULED', 'SHIPPED_PENDING']),
        Order.scheduled_date != None,
        Order.scheduled_date != '',
        func.date(Order.scheduled_date) < date.today()
    )).order_by(Order.scheduled_date.asc()).all()

    alert_ids = {o.id for o in urgent_alerts + measurement_alerts + pre_measurement_alerts + installation_alerts}

    as_orders = get_filtered_orders(db.query(Order).filter(
        Order.status == 'AS_RECEIVED',
        Order.is_regional == False
    )).order_by(Order.created_at.desc()).all()

    hold_orders = get_filtered_orders(db.query(Order).filter(
        Order.status == 'ON_HOLD',
        Order.is_regional == False
    )).order_by(Order.created_at.desc()).all()

    normal_orders = get_filtered_orders(db.query(Order).filter(
        Order.status.notin_(['COMPLETED', 'DELETED', 'AS_RECEIVED', 'AS_COMPLETED', 'ON_HOLD']),
        ~Order.id.in_(alert_ids),
        Order.is_regional == False
    )).order_by(Order.created_at.desc()).limit(20).all()

    completed_orders = get_filtered_orders(db.query(Order).filter(
        Order.status.in_(['COMPLETED', 'AS_COMPLETED']),
        Order.is_regional == False
    )).order_by(Order.completion_date.desc()).limit(50).all()

    all_metro = urgent_alerts + measurement_alerts + pre_measurement_alerts + installation_alerts + as_orders + hold_orders + normal_orders + completed_orders
    apply_erp_display_fields_to_orders(all_metro)

    return render_template('metropolitan_dashboard.html',
        urgent_alerts=urgent_alerts,
        measurement_alerts=measurement_alerts,
        pre_measurement_alerts=pre_measurement_alerts,
        installation_alerts=installation_alerts,
        as_orders=as_orders,
        hold_orders=hold_orders,
        normal_orders=normal_orders,
        completed_orders=completed_orders,
        STATUS=STATUS,
        search_query=search_query
    )


@dashboards_bp.route('/self_measurement_dashboard')
@login_required
def self_measurement_dashboard():
    """자가실측 대시보드."""
    db = get_db()
    search_query = request.args.get('search_query', '').strip()

    base_query = db.query(Order).filter(
        Order.is_self_measurement == True,
        Order.status != 'DELETED'
    )

    if search_query:
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            id_conditions.append(Order.id == int(search_query))
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))
        base_query = base_query.filter(or_(
            Order.customer_name.ilike(search_term),
            Order.phone.ilike(search_term),
            Order.address.ilike(search_term),
            Order.product.ilike(search_term),
            Order.notes.ilike(search_term),
            *id_conditions
        ))

    all_orders = base_query.order_by(Order.id.desc()).all()
    apply_erp_display_fields_to_orders(all_orders)

    as_orders = [o for o in all_orders if o.status == 'AS_RECEIVED']
    completed_orders = [o for o in all_orders if o.status in ['COMPLETED', 'AS_COMPLETED']]
    scheduled_orders = [o for o in all_orders if o.status == 'SCHEDULED']
    pending_orders = [o for o in all_orders if o.status not in ['COMPLETED', 'AS_COMPLETED', 'SCHEDULED', 'AS_RECEIVED']]

    return render_template('self_measurement_dashboard.html',
        pending_orders=pending_orders,
        scheduled_orders=scheduled_orders,
        as_orders=as_orders,
        completed_orders=completed_orders,
        search_query=search_query,
        STATUS=STATUS
    )
