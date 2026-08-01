"""엑셀 업로드/다운로드 Blueprint (canonical; SFC-B11B): /upload, /download_excel.

import(POST /upload)는 ORDER-IMPORT-01 정본 서비스(:mod:`foms.services.orders.order_import`)
로 위임한다 — strict schema·full validate·create_order batch all-or-none·file-hash receipt·
private artifact 24h 는 서비스가 소유하고, 이 route 는 in-handler ``evaluate_policy``
(``MANAGER_MUTATION`` = Admin/Manager)·파일 수신·flash/redirect·error download 스트림만 배선한다.
"""
import os
import datetime
from io import BytesIO
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session,
    send_file, abort,
)
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func, String
import pandas as pd

from foms.web.auth import login_required, log_access, get_user_by_id
from db import get_db
from models import Order, OrderImportArtifact, User
from foms.services.files.storage_paths import UPLOAD_FOLDER
from foms.services.orders.status_constants import STATUS
from foms.services.files.file_utils import allowed_file
from foms.services.order_display_utils import format_options_for_display
from foms.services.storage import get_storage
from foms.services.orders.order_mutation_policy import (
    POLICY_REGISTRY, evaluate_policy, normalize_team,
)
from foms.services.orders.order_create import OwnerPolicyError
from foms.services.orders.order_import import (
    REQUIRED_COLUMNS,
    OrderImportError,
    OrderImportValidationError,
    import_orders,
)

excel_bp = Blueprint('excel', __name__, url_prefix='')

#: import route 정책 — bulk delete/restore/excel-import(Admin/Manager). manifest 정본과 동일.
_IMPORT_POLICY_ID = 'MANAGER_MUTATION'
#: 빈 템플릿 헤더(필수 + 흔한 선택 컬럼). import 서비스 정규화 키와 일치.
_TEMPLATE_COLUMNS = list(REQUIRED_COLUMNS) + [
    '옵션', '비고', '접수시간', '실측일', '실측시간', '설치완료일', '담당자', '결제금액']


def _current_user():
    """세션 user_id 로 현재 사용자 로드(in-handler 권한 판정용)."""
    uid = session.get('user_id')
    return get_user_by_id(uid) if uid else None


def _require_import_policy():
    """MANAGER_MUTATION 정책을 in-handler 로 판정하고 거부면 abort(그 외 403)."""
    decision = evaluate_policy(POLICY_REGISTRY[_IMPORT_POLICY_ID], _current_user())
    if not decision.allowed:
        log_access(f"엑셀 import 권한 거부({decision.code})", session.get('user_id'))
        abort(decision.status)


def _form_owner_id():
    """폼의 explicit owner user_id 를 int 로 파싱한다(없으면 None)."""
    raw = request.form.get('owner_user_id')
    try:
        return int(raw) if raw not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _active_sales_owners(db):
    """import owner 후보 = 활성 SALES(MEASURE→SALES 정규화) 사용자 (id, name) 목록."""
    rows = (db.query(User.id, User.name, User.team)
            .filter(User.is_active.is_(True)).order_by(User.name).all())
    return [{"id": uid, "name": (nm or '').strip() or f"user#{uid}"}
            for uid, nm, team in rows if normalize_team(team) == 'SALES']


@excel_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_excel():
    """엑셀 파일 업로드로 주문 일괄 등록(Admin/Manager, strict·all-or-none·멱등)."""
    _require_import_policy()
    if request.method != 'POST':
        return render_template('admin/upload.html',
                               sales_owners=_active_sales_owners(get_db()))

    if 'excel_file' not in request.files or request.files['excel_file'].filename == '':
        flash('파일이 선택되지 않았습니다.', 'error')
        return redirect(request.url)
    file = request.files['excel_file']
    if not allowed_file(file.filename):
        flash('허용되지 않은 파일 형식입니다. .xlsx 또는 .xls 파일만 업로드 가능합니다.', 'error')
        log_access(f"엑셀 import 실패: 형식 - {file.filename}", session.get('user_id'))
        return redirect(request.url)

    filename = secure_filename(file.filename) or 'import.xlsx'
    defaults = {k: request.form.get(k)
                for k in ('scheduled_date', 'as_received_date', 'as_completed_date')}
    db = get_db()
    try:
        receipt = import_orders(
            db, actor=_current_user(), owner_user_id=_form_owner_id(),
            file_bytes=file.read(), filename=filename,
            storage=get_storage(), form_defaults=defaults)
    except OrderImportValidationError as exc:
        return _flash_validation_error(exc, filename)
    except (OrderImportError, OwnerPolicyError) as exc:
        db.rollback()
        flash(f'엑셀 import 실패: {exc}', 'error')
        log_access(f"엑셀 import 실패: {filename} - {exc}", session.get('user_id'))
        return redirect(request.url)

    if receipt.idempotent:
        flash(f'이미 등록된 파일입니다({receipt.row_count}건, 재생성 없음).', 'info')
    else:
        flash(f'{receipt.row_count}개의 주문이 성공적으로 등록되었습니다.', 'success')
    log_access(f"엑셀 import: {filename} → {receipt.row_count}건(artifact={receipt.artifact_id})",
               session.get('user_id'),
               {"artifact_id": receipt.artifact_id, "idempotent": receipt.idempotent,
                "order_ids": receipt.resource_order_ids})
    return redirect(url_for('order_pages.index'))


def _flash_validation_error(exc: OrderImportValidationError, filename: str):
    """full validate 실패를 flash 하고 error download 링크를 안내한다(주문 미생성)."""
    receipt = exc.receipt
    errors_url = url_for('excel.download_order_import_errors', artifact_id=receipt.artifact_id)
    flash(f'{len(receipt.row_errors)}개 행 검증 실패 — 주문이 생성되지 않았습니다. '
          f'에러 리포트: {errors_url}', 'error')
    log_access(f"엑셀 import 검증 실패: {filename} - {len(receipt.row_errors)}행"
               f"(artifact={receipt.artifact_id})", session.get('user_id'))
    return redirect(request.url)


@excel_bp.route('/admin/order-imports/<int:artifact_id>/errors')
@login_required
def download_order_import_errors(artifact_id):
    """FAILED import artifact 의 에러 리포트를 private key 에서 스트림한다(Admin/Manager)."""
    _require_import_policy()
    db = get_db()
    artifact = db.get(OrderImportArtifact, artifact_id)
    if artifact is None or not artifact.error_object_key:
        abort(404)
    data = get_storage().read_file_bytes(artifact.error_object_key)
    if data is None:
        abort(404)
    return send_file(BytesIO(data), as_attachment=True,
                     download_name=f'import_errors_{artifact_id}.csv', mimetype='text/csv')


@excel_bp.route('/download_excel_template')
@login_required
def download_excel_template():
    """import 용 빈 템플릿(필수+선택 컬럼 헤더)을 다운로드한다(Admin/Manager)."""
    _require_import_policy()
    buf = BytesIO()
    pd.DataFrame(columns=_TEMPLATE_COLUMNS).to_excel(buf, index=False, engine='openpyxl')
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name='order_import_template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


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
