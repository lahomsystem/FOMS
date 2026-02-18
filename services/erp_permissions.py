"""ERP Beta 수정 권한: 관리자, CS, SALES 팀만 수정 가능."""
from flask import session, jsonify
from apps.auth import get_user_by_id


ERP_EDIT_ALLOWED_TEAMS = ('CS', 'SALES')


def can_edit_erp(user):
    """ERP 페이지/API 수정 권한: 관리자 또는 CS/영업팀 소속만 True"""
    if not user:
        return False
    if user.role == 'ADMIN':
        return True
    return (user.team or '').strip() in ERP_EDIT_ALLOWED_TEAMS


def erp_edit_required(f):
    """ERP Beta 수정 API용 데코레이터: 수정 권한 없으면 403"""
    from functools import wraps

    @wraps(f)
    def wrapped(*args, **kwargs):
        user = get_user_by_id(session.get('user_id'))
        if not user:
            return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
        if not can_edit_erp(user):
            return jsonify({
                'success': False,
                'message': 'ERP Beta 수정 권한이 없습니다. (관리자, 라홈팀, 하우드팀, 영업팀만 수정 가능)'
            }), 403
        return f(*args, **kwargs)
    return wrapped
