"""엑셀 업로드/다운로드 Blueprint: /upload, /download_excel."""
import os
import re
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func, String
import pandas as pd

from apps.auth import login_required, role_required, log_access
from db import get_db
from models import Order
from constants import STATUS, UPLOAD_FOLDER, ALLOWED_EXTENSIONS
from services.order_display_utils import format_options_for_display

excel_bp = Blueprint('excel', __name__, url_prefix='')


def _allowed_file(filename):
    """엑셀 파일 확장자 검사."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _parse_time_from_row(raw_val):
    """엑셀 행에서 시간 값을 HH:MM 문자열로 변환."""
    if pd.isna(raw_val):
        return None
    if isinstance(raw_val, datetime.time):
        return raw_val.strftime('%H:%M')
    if isinstance(raw_val, datetime.datetime):
        return raw_val.strftime('%H:%M')
    if isinstance(raw_val, str):
        if re.match(r'^\d{1,2}:\d{2}$', raw_val.strip()):
            return raw_val.strip()
        try:
            time_float = float(raw_val)
            hours = int(time_float * 24)
            minutes = int((time_float * 24 * 60) % 60)
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, TypeError):
            return None
    if isinstance(raw_val, (int, float)):
        try:
            total_seconds = int(raw_val * 24 * 60 * 60)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        except Exception:
            return None
    return None


@excel_bp.route('/upload', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER'])
def upload_excel():
    """엑셀 파일 업로드로 주문 일괄 등록."""
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash('파일이 선택되지 않았습니다.', 'error')
            log_access("엑셀 업로드 실패: 파일이 선택되지 않음", session.get('user_id'))
            return redirect(request.url)

        file = request.files['excel_file']
        if file.filename == '':
            flash('파일이 선택되지 않았습니다.', 'error')
            log_access("엑셀 업로드 실패: 빈 파일명", session.get('user_id'))
            return redirect(request.url)

        if not file or not _allowed_file(file.filename):
            flash('허용되지 않은 파일 형식입니다. .xlsx 또는 .xls 파일만 업로드 가능합니다.', 'error')
            log_access(f"엑셀 업로드 실패: 허용되지 않은 파일 형식 - {file.filename}", session.get('user_id'),
                      {"filename": file.filename})
            return redirect(request.url)

        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        db = get_db()
        try:
            df = pd.read_excel(file_path)
            required_columns = ['접수일', '고객명', '전화번호', '주소', '제품']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                flash(f'엑셀 파일에 필수 컬럼이 누락되었습니다: {", ".join(missing_columns)}', 'error')
                log_access(f"엑셀 업로드 실패: 필수 컬럼 누락 ({missing_columns}) - {filename}", session.get('user_id'))
                try:
                    os.remove(file_path)
                except OSError:
                    pass
                return redirect(request.url)

            order_count = 0
            added_order_ids = []
            for index, row in df.iterrows():
                received_date_dt = pd.to_datetime(row['접수일'], errors='coerce')
                received_date = received_date_dt.strftime('%Y-%m-%d') if pd.notna(received_date_dt) else datetime.datetime.now().strftime('%Y-%m-%d')

                measurement_date_dt = pd.to_datetime(row.get('실측일'), errors='coerce')
                measurement_date = measurement_date_dt.strftime('%Y-%m-%d') if pd.notna(measurement_date_dt) else None

                completion_date_dt = pd.to_datetime(row.get('설치완료일'), errors='coerce')
                completion_date = completion_date_dt.strftime('%Y-%m-%d') if pd.notna(completion_date_dt) else None

                received_time = _parse_time_from_row(row.get('접수시간'))
                measurement_time = _parse_time_from_row(row.get('실측시간'))

                options_raw = row.get('옵션')
                options = str(options_raw) if pd.notna(options_raw) else None

                notes_raw = row.get('비고')
                notes = str(notes_raw) if pd.notna(notes_raw) else None

                manager_name_raw = row.get('담당자')
                manager_name = str(manager_name_raw) if pd.notna(manager_name_raw) else None

                payment_amount_raw = row.get('결제금액')
                payment_amount = 0
                if pd.notna(payment_amount_raw):
                    try:
                        if isinstance(payment_amount_raw, str):
                            payment_amount = int(float(payment_amount_raw.replace(',', '')))
                        elif isinstance(payment_amount_raw, (int, float)):
                            payment_amount = int(payment_amount_raw)
                    except ValueError:
                        payment_amount = 0

                new_order = Order(
                    customer_name=str(row['고객명']) if pd.notna(row['고객명']) else '',
                    phone=str(row['전화번호']) if pd.notna(row['전화번호']) else '',
                    address=str(row['주소']) if pd.notna(row['주소']) else '',
                    product=str(row['제품']) if pd.notna(row['제품']) else '',
                    options=options,
                    notes=notes,
                    received_date=received_date,
                    received_time=received_time,
                    status='RECEIVED',
                    measurement_date=measurement_date,
                    measurement_time=measurement_time,
                    completion_date=completion_date,
                    manager_name=manager_name,
                    payment_amount=payment_amount,
                    scheduled_date=request.form.get('scheduled_date'),
                    as_received_date=request.form.get('as_received_date'),
                    as_completed_date=request.form.get('as_completed_date'),
                    is_regional=False,
                )
                db.add(new_order)
                db.flush()
                added_order_ids.append(new_order.id)
                order_count += 1

            db.commit()
            flash(f'{order_count}개의 주문이 성공적으로 등록되었습니다.', 'success')
            log_access(f"엑셀 업로드 성공: {filename} 파일에서 {order_count}개 주문 추가", session.get('user_id'),
                      {"filename": filename, "orders_added": order_count, "order_ids": added_order_ids})
        except Exception as e:
            if db:
                db.rollback()
            flash(f'엑셀 파일 처리 중 오류가 발생했습니다: {str(e)}', 'error')
            log_access(f"엑셀 업로드 실패: {filename} - {str(e)}", session.get('user_id'),
                      {"filename": filename, "error": str(e)})
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass

        return redirect(url_for('order_pages.index'))

    return render_template('upload.html')


@excel_bp.route('/download_excel')
@login_required
def download_excel():
    """현재 필터 기준으로 주문 목록 엑셀 다운로드."""
    db = get_db()
    status_filter = request.args.get('status')
    search_query = request.args.get('search', '').strip()
    sort_column = request.args.get('sort', 'id')
    sort_direction = request.args.get('direction', 'desc')

    query = db.query(Order).filter(Order.deleted_at.is_(None))

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
