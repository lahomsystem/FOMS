"""휴지통/삭제 관련 Blueprint: delete_order, trash, restore, permanent_delete."""
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy import text

from apps.auth import login_required, role_required, log_access, get_user_by_id
from db import get_db
from models import Order
from services.request_utils import get_preserved_filter_args

order_trash_bp = Blueprint('order_trash', __name__, url_prefix='')


def reset_order_ids(db):
    """주문 ID를 1부터 연속적으로 재정렬합니다."""
    try:
        db.execute(text("CREATE TEMPORARY TABLE temp_order_mapping (old_id INT, new_id INT)"))
        orders = db.query(Order).filter(Order.status != 'DELETED').order_by(Order.id).all()
        new_id = 0
        for new_id, order in enumerate(orders, 1):
            if order.id != new_id:
                db.execute(text("INSERT INTO temp_order_mapping (old_id, new_id) VALUES (:old_id, :new_id)"),
                          {"old_id": order.id, "new_id": new_id})
        mapping_exists = db.execute(text("SELECT COUNT(*) FROM temp_order_mapping")).scalar() > 0
        max_id = new_id if orders else 0
        if mapping_exists:
            db.execute(text("""
                UPDATE orders
                SET id = (SELECT new_id FROM temp_order_mapping WHERE temp_order_mapping.old_id = orders.id)
                WHERE id IN (SELECT old_id FROM temp_order_mapping)
            """))
        try:
            seq_query = "SELECT pg_get_serial_sequence('orders', 'id')"
            seq_name = db.execute(text(seq_query)).scalar()
            if seq_name:
                db.execute(text(f"ALTER SEQUENCE {seq_name} RESTART WITH {max_id + 1}"))
            else:
                db.execute(text(f"ALTER SEQUENCE orders_id_seq RESTART WITH {max_id + 1}"))
        except Exception:
            try:
                db.execute(text(f"ALTER SEQUENCE orders_id_seq RESTART WITH {max_id + 1}"))
            except Exception:
                pass
        db.commit()
        db.execute(text("DROP TABLE IF EXISTS temp_order_mapping"))
    except Exception as e:
        db.rollback()
        try:
            db.execute(text("DROP TABLE IF EXISTS temp_order_mapping"))
        except Exception:
            pass
        raise e


@order_trash_bp.route('/delete/<int:order_id>')
@login_required
@role_required(['ADMIN', 'MANAGER'])
def delete_order(order_id):
    """주문을 휴지통으로 이동 (소프트 삭제)."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            flash('주문을 찾을 수 없거나 이미 삭제되었습니다.', 'error')
            return redirect(url_for('order_pages.index'))

        original_status = order.status
        deleted_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        customer_name_for_log = order.customer_name

        order.status = 'DELETED'
        order.original_status = original_status
        order.deleted_at = deleted_at
        db.commit()

        user_for_log = get_user_by_id(session.get('user_id'))
        user_name_for_log = user_for_log.name if user_for_log else "Unknown user"
        log_access(f"주문 #{order_id} ({customer_name_for_log}) 삭제 - 담당자: {user_name_for_log}", session.get('user_id'))
        flash('주문이 휴지통으로 이동되었습니다.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'주문 삭제 중 오류가 발생했습니다: {str(e)}', 'error')

    redirect_args = get_preserved_filter_args(request.args)
    return redirect(url_for('order_pages.index', **redirect_args))


@order_trash_bp.route('/trash')
@login_required
@role_required(['ADMIN', 'MANAGER'])
def trash():
    """휴지통 페이지."""
    search_term = request.args.get('search', '')
    db = get_db()
    query = db.query(Order).filter(Order.status == 'DELETED')
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(
            (Order.customer_name.like(search_pattern)) |
            (Order.phone.like(search_pattern)) |
            (Order.address.like(search_pattern)) |
            (Order.product.like(search_pattern)) |
            (Order.options.like(search_pattern)) |
            (Order.notes.like(search_pattern))
        )
    orders = query.order_by(Order.deleted_at.desc()).all()
    return render_template('trash.html', orders=orders, search_term=search_term)


@order_trash_bp.route('/restore_orders', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER'])
def restore_orders():
    """선택한 주문 복원."""
    selected_ids = request.form.getlist('selected_order')
    if not selected_ids:
        flash('복원할 주문을 선택해주세요.', 'warning')
        return redirect(url_for('order_trash.trash'))

    try:
        db = get_db()
        for order_id in selected_ids:
            order = db.query(Order).filter(Order.id == order_id, Order.status == 'DELETED').first()
            if order:
                original_status = order.original_status if order.original_status else 'RECEIVED'
                order.status = original_status
                order.original_status = None
                order.deleted_at = None
        db.commit()
        log_access(f"주문 {len(selected_ids)}개 복원", session.get('user_id'), {"count": len(selected_ids)})
        flash(f'{len(selected_ids)}개 주문이 성공적으로 복원되었습니다.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'주문 복원 중 오류가 발생했습니다: {str(e)}', 'error')
    return redirect(url_for('order_trash.trash'))


@order_trash_bp.route('/permanent_delete_orders', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def permanent_delete_orders():
    """선택한 주문 영구 삭제."""
    selected_ids = request.form.getlist('selected_order')
    if not selected_ids:
        flash('영구 삭제할 주문을 선택해주세요.', 'warning')
        return redirect(url_for('order_trash.trash'))

    try:
        db = get_db()
        for order_id in selected_ids:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                db.delete(order)
        db.commit()
        reset_order_ids(db)
        log_access(f"주문 {len(selected_ids)}개 영구 삭제", session.get('user_id'), {"count": len(selected_ids)})
        flash(f'{len(selected_ids)}개의 주문이 영구적으로 삭제되었습니다.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'주문 영구 삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    return redirect(url_for('order_trash.trash'))


@order_trash_bp.route('/permanent_delete_all_orders', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def permanent_delete_all_orders():
    """휴지통의 모든 주문 영구 삭제."""
    try:
        db = get_db()
        deleted_orders = db.query(Order).filter(Order.status == 'DELETED').all()
        if not deleted_orders:
            flash('휴지통에 삭제할 주문이 없습니다.', 'warning')
            return redirect(url_for('order_trash.trash'))

        deleted_count = len(deleted_orders)
        for order in deleted_orders:
            db.delete(order)
        db.commit()
        reset_order_ids(db)
        log_access(f"모든 주문 영구 삭제 ({deleted_count}개 항목)", session.get('user_id'), {"count": deleted_count})
        flash(f'모든 주문({deleted_count}개)이 영구적으로 삭제되었습니다.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'주문 영구 삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    return redirect(url_for('order_trash.trash'))
