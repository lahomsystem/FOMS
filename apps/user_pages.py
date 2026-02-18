"""사용자 페이지 Blueprint.

/change-logs - 변경 로그
/profile - 프로필
/security_logs - 보안 로그 (관리자)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

from apps.auth import login_required, role_required, is_password_strong, log_access
from db import get_db
from models import User, SecurityLog

user_pages_bp = Blueprint('user_pages', __name__, url_prefix='')


@user_pages_bp.route('/change-logs')
@login_required
def change_logs():
    """변경 로그 페이지 - 모든 사용자가 본인의 변경 이력 확인 가능."""
    return render_template('change_logs.html')


@user_pages_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """프로필 페이지 - 사용자 정보 및 비밀번호 변경."""
    user_id = session.get('user_id')
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        session.clear()
        flash('사용자를 찾을 수 없습니다. 다시 로그인해주세요.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        name = request.form.get('name')

        if not name:
            flash('이름을 입력해주세요.', 'error')
            return render_template('profile.html', user=user)

        try:
            user.name = name
            db.commit()

            if current_password and new_password and confirm_password:
                if not check_password_hash(user.password, current_password):
                    flash('현재 비밀번호가 일치하지 않습니다.', 'error')
                    return render_template('profile.html', user=user)

                if new_password != confirm_password:
                    flash('새 비밀번호가 일치하지 않습니다.', 'error')
                    return render_template('profile.html', user=user)

                if not is_password_strong(new_password):
                    flash('비밀번호는 4자리 이상이어야 합니다.', 'error')
                    return render_template('profile.html', user=user)

                user.password = generate_password_hash(new_password)
                db.commit()
                log_access("비밀번호 변경 완료", user_id)
                flash('비밀번호가 성공적으로 변경되었습니다.', 'success')

            flash('프로필이 업데이트되었습니다.', 'success')
            return redirect(url_for('user_pages.profile'))

        except Exception as e:
            db.rollback()
            flash(f'프로필 업데이트 중 오류가 발생했습니다: {str(e)}', 'error')
            return render_template('profile.html', user=user)

    return render_template('profile.html', user=user)


@user_pages_bp.route('/security_logs')
@login_required
@role_required(['ADMIN'])
def security_logs():
    """보안 로그 목록 조회 (관리자 전용)."""
    db = get_db()

    page = request.args.get('page', 1, type=int)
    per_page = 50
    search_query = request.args.get('search', '')

    query = db.query(SecurityLog).order_by(SecurityLog.timestamp.desc())

    if search_query:
        query = query.join(User, User.id == SecurityLog.user_id, isouter=True).filter(
            or_(
                User.name.ilike(f'%{search_query}%'),
                SecurityLog.message.ilike(f'%{search_query}%')
            )
        )

    total_logs = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total_logs + per_page - 1) // per_page

    return render_template(
        'security_logs.html',
        logs=logs,
        page=page,
        total_pages=total_pages,
        search_query=search_query,
        total_logs=total_logs
    )
