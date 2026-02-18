"""
주문 팔로업(Task) API.
"""

import datetime
from flask import Blueprint, request, jsonify

from db import get_db
from models import OrderTask
from apps.auth import login_required, role_required

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api')


@tasks_bp.route('/orders/<int:order_id>/tasks', methods=['GET'])
@login_required
def api_order_tasks_list(order_id):
    """주문 팔로업(Task) 목록"""
    try:
        db = get_db()
        rows = db.query(OrderTask).filter(OrderTask.order_id == order_id).order_by(OrderTask.updated_at.desc()).all()
        tasks = []
        for t in rows:
            tasks.append({
                'id': t.id,
                'order_id': t.order_id,
                'title': t.title,
                'status': t.status,
                'owner_team': t.owner_team,
                'owner_user_id': t.owner_user_id,
                'due_date': t.due_date,
                'meta': t.meta,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else None,
                'updated_at': t.updated_at.strftime('%Y-%m-%d %H:%M:%S') if t.updated_at else None,
            })
        return jsonify({'success': True, 'tasks': tasks})
    except Exception as e:
        import traceback
        print(f"주문 Task 목록 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@tasks_bp.route('/orders/<int:order_id>/tasks', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_tasks_create(order_id):
    """주문 팔로업(Task) 생성"""
    try:
        db = get_db()
        payload = request.get_json(silent=True) or {}
        title = (payload.get('title') or '').strip()
        if not title:
            return jsonify({'success': False, 'message': 'title이 필요합니다.'}), 400

        task = OrderTask(
            order_id=order_id,
            title=title,
            status=(payload.get('status') or 'OPEN'),
            owner_team=(payload.get('owner_team') or None),
            owner_user_id=(payload.get('owner_user_id') or None),
            due_date=(payload.get('due_date') or None),
            meta=(payload.get('meta') if isinstance(payload.get('meta'), dict) else None),
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now(),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"주문 Task 생성 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@tasks_bp.route('/orders/<int:order_id>/tasks/<int:task_id>', methods=['PUT'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_tasks_update(order_id, task_id):
    """주문 팔로업(Task) 수정"""
    try:
        db = get_db()
        task = db.query(OrderTask).filter(OrderTask.id == task_id, OrderTask.order_id == order_id).first()
        if not task:
            return jsonify({'success': False, 'message': 'Task를 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        if 'title' in payload:
            task.title = (payload.get('title') or '').strip()
        if 'status' in payload:
            task.status = payload.get('status') or task.status
        if 'owner_team' in payload:
            task.owner_team = payload.get('owner_team') or None
        if 'owner_user_id' in payload:
            task.owner_user_id = payload.get('owner_user_id') or None
        if 'due_date' in payload:
            task.due_date = payload.get('due_date') or None
        if 'meta' in payload and isinstance(payload.get('meta'), dict):
            task.meta = payload.get('meta')

        task.updated_at = datetime.datetime.now()
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"주문 Task 수정 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@tasks_bp.route('/orders/<int:order_id>/tasks/<int:task_id>', methods=['DELETE'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_order_tasks_delete(order_id, task_id):
    """주문 팔로업(Task) 삭제"""
    try:
        db = get_db()
        task = db.query(OrderTask).filter(OrderTask.id == task_id, OrderTask.order_id == order_id).first()
        if not task:
            return jsonify({'success': False, 'message': 'Task를 찾을 수 없습니다.'}), 404
        db.delete(task)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db = get_db()
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"주문 Task 삭제 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
