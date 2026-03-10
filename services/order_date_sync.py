import re
from models import OrderScheduleDate
from db import get_db


def collect_order_schedule_date_specs(order):
    """Build the normalized schedule-date payloads for a single order."""
    specs = []

    # 1. Measurement Dates
    m_dates = set()
    legacy_m = getattr(order, 'measurement_date', None)
    if legacy_m:
        for d in str(legacy_m).split(','):
            if d.strip():
                specs.append({
                    'kind': 'measurement',
                    'date': d.strip(),
                    'source': 'legacy_column',
                    'item_index': None,
                })
                m_dates.add(d.strip())

    if getattr(order, 'is_erp_beta', False) and isinstance(getattr(order, 'structured_data', None), dict):
        sd = order.structured_data
        # Beta Schedule
        beta_m = (sd.get('schedule') or {}).get('measurement') or {}
        if isinstance(beta_m, dict):
            bmd = beta_m.get('date')
            if bmd:
                for d in str(bmd).split(','):
                    if d.strip() and d.strip() not in m_dates:
                        specs.append({
                            'kind': 'measurement',
                            'date': d.strip(),
                            'source': 'beta_schedule',
                            'item_index': None,
                        })
                        m_dates.add(d.strip())
        
        # Beta Items
        for idx, it in enumerate(sd.get('items') or []):
            if isinstance(it, dict):
                imd = it.get('measurement_date')
                if imd:
                    for d in str(imd).split(','):
                        if d.strip() and d.strip() not in m_dates:
                            specs.append({
                                'kind': 'measurement',
                                'date': d.strip(),
                                'source': 'beta_item',
                                'item_index': idx,
                            })
                            m_dates.add(d.strip())

    # 2. Construction Dates
    c_dates = set()
    legacy_c = getattr(order, 'scheduled_date', None)
    if legacy_c:
        for d in str(legacy_c).split(','):
            if d.strip():
                specs.append({
                    'kind': 'construction',
                    'date': d.strip(),
                    'source': 'legacy_column',
                    'item_index': None,
                })
                c_dates.add(d.strip())

    if getattr(order, 'is_erp_beta', False) and isinstance(getattr(order, 'structured_data', None), dict):
        sd = order.structured_data

        # Beta Schedule: 직접 입력된 시공일만 사용 (측정일+5일 추정 로직 제거)
        s_date = None
        sc = sd.get('schedule') or {}
        if isinstance(sc, dict):
            cd = sc.get('construction') or {}
            if isinstance(cd, dict):
                s_date = (cd.get('date') or '').strip() or None

        if s_date:
            for d in s_date.split(','):
                if d.strip() and d.strip() not in c_dates:
                    specs.append({
                        'kind': 'construction',
                        'date': d.strip(),
                        'source': 'beta_schedule',
                        'item_index': None,
                    })
                    c_dates.add(d.strip())
            
        # Beta Items
        for idx, it in enumerate(sd.get('items') or []):
            if isinstance(it, dict):
                icd = it.get('construction_date')
                if icd:
                    for d in str(icd).split(','):
                        if d.strip() and d.strip() not in c_dates:
                            specs.append({
                                'kind': 'construction',
                                'date': d.strip(),
                                'source': 'beta_item',
                                'item_index': idx,
                            })
                            c_dates.add(d.strip())

    return specs


def sync_order_dates(order, db_session=None):
    """
    Extracts dates from Order and updates the OrderScheduleDate relationship.
    Does NOT commit the session. Caller must commit.
    """
    if db_session is None:
        db_session = get_db()

    specs = collect_order_schedule_date_specs(order)
    order.schedule_dates = [
        OrderScheduleDate(
            kind=spec['kind'],
            date=spec['date'],
            source=spec['source'],
            item_index=spec['item_index'],
        )
        for spec in specs
    ]

def register_date_sync_listener():
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from models import Order
    
    @event.listens_for(Session, 'before_flush')
    def before_flush(session, flush_context, instances):
        # Triggering sync for any modified tracking targets 
        # Avoid recursion or flushing loop
        changed_orders = [
            obj for obj in session.new.union(session.dirty)
            if isinstance(obj, Order)
        ]
        
        for order in changed_orders:
            sync_order_dates(order, session)

