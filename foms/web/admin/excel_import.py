"""주문 목록 엑셀 다운로드 Blueprint (canonical; SFC-B11B): /download_excel.

현재 필터/검색/정렬 조건으로 조회한 주문 목록을 xlsx 로 내보낸다. 이 Blueprint 는
**내보내기 전용**이다 — 엑셀 업로드(가져오기) 기능은 제거됐다.
"""
import os
import datetime
from flask import (
    Blueprint, request, redirect, url_for, flash, session, send_file,
)
from sqlalchemy import or_, func, String
import pandas as pd

from foms.web.auth import login_required, log_access
from db import get_db
from models import Order
from foms.services.files.storage_paths import UPLOAD_FOLDER
from foms.services.orders.status_constants import STATUS
from foms.services.order_display_utils import format_options_for_display

excel_bp = Blueprint('excel', __name__, url_prefix='')


@excel_bp.route('/download_excel')
@login_required
def download_excel():
    """현재 필터 기준으로 주문 목록 엑셀 다운로드."""
    db = get_db()
    status_filter = request.args.get('status')
    search_query = request.args.get('search', '').strip()
    sort_column = request.args.get('sort', 'id')
    sort_direction = request.args.get('direction', 'desc')

    query = db.query(Order).filter(Order.active_filter())

    if status_filter:
        if status_filter == 'RECEIVED':
            query = query.filter(Order.status.in_(['RECEIVED', 'ON_HOLD']))
        else:
            query = query.filter(Order.status == status_filter)

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
                Order.completion_date.like(search_term),
                Order.manager_name.like(search_term),
                func.cast(Order.payment_amount, String).like(search_term),
            )
        )

    filterable_columns = [
        'id', 'received_date', 'received_time', 'customer_name', 'phone',
        'address', 'product', 'options', 'notes', 'status',
        'measurement_date', 'measurement_time', 'completion_date', 'manager_name', 'payment_amount'
    ]
    for column_name in filterable_columns:
        filter_value = request.args.get(f'filter_{column_name}', '').strip()
        if filter_value and hasattr(Order, column_name):
            try:
                column_attr = getattr(Order, column_name)
                if isinstance(column_attr.type.python_type(), (int, float)):
                    query = query.filter(column_attr.cast(String).like(f"%{filter_value}%"))
                else:
                    query = query.filter(column_attr.like(f"%{filter_value}%"))
            except AttributeError:
                pass

    if hasattr(Order, sort_column):
        column_to_sort = getattr(Order, sort_column)
        query = query.order_by(column_to_sort.asc() if sort_direction == 'asc' else column_to_sort.desc())
    else:
        query = query.order_by(Order.id.desc())

    orders = query.all()
    if not orders:
        flash('다운로드할 데이터가 없습니다.', 'warning')
        return redirect(request.referrer or url_for('order_pages.index'))

    orders_data = []
    for order in orders:
        order_dict = order.to_dict()
        order_dict['options'] = format_options_for_display(order.options)
        orders_data.append(order_dict)

    df = pd.DataFrame(orders_data)
    if 'status' in df.columns:
        df['status'] = df['status'].map(STATUS).fillna(df['status'])

    excel_columns = [
        'id', 'received_date', 'received_time', 'customer_name', 'phone', 'address',
        'product', 'options', 'notes', 'payment_amount',
        'measurement_date', 'measurement_time', 'completion_date',
        'manager_name', 'status'
    ]
    df_excel_columns = [col for col in excel_columns if col in df.columns]
    df_excel = df[df_excel_columns]

    column_mapping_korean = {
        'id': '번호', 'received_date': '접수일', 'received_time': '접수시간',
        'customer_name': '고객명', 'phone': '연락처', 'address': '주소',
        'product': '제품', 'options': '옵션', 'notes': '비고',
        'payment_amount': '결제금액', 'measurement_date': '실측일',
        'measurement_time': '실측시간', 'completion_date': '설치완료일',
        'manager_name': '담당자', 'status': '상태'
    }
    df_excel.rename(columns=column_mapping_korean, inplace=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"furniture_orders_{timestamp}.xlsx"
    excel_path = os.path.join(UPLOAD_FOLDER, excel_filename)

    df_excel.to_excel(excel_path, index=False, engine='openpyxl')

    log_access(f"엑셀 다운로드: {excel_filename}", session.get('user_id'))

    return send_file(excel_path, as_attachment=True)
