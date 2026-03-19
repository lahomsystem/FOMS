"""ERP Beta 수정 권한: 관리자, CS, SALES 팀만 수정 가능. 시공 시작/완료/불가는 시공팀(CONSTRUCTION)도 가능."""
import re
from typing import Any, List
from flask import session, jsonify
from apps.auth import get_user_by_id
from sqlalchemy import cast, String, or_


ERP_EDIT_ALLOWED_TEAMS = ('CS', 'SALES')

# LIKE 와일드카드 이스케이프 패턴 (PostgreSQL escape char = '\')
_LIKE_ESCAPE_RE = re.compile(r'([%_\\])')


def _escape_like(value: str) -> str:
    """LIKE 패턴에서 와일드카드 문자(%,_,\\)를 이스케이프한다.

    Args:
        value: 원본 검색어

    Returns:
        이스케이프된 검색어
    """
    return _LIKE_ESCAPE_RE.sub(r'\\\1', value)


def build_mine_sql_filter(user) -> List[Any]:
    """사용자 기준 '내 주문' SQL WHERE 조건 리스트를 반환한다.

    manager_name 컬럼 및 structured_data JSONB 문자열에서 사용자 이름/계정명을 ilike 검색.
    SQL 레벨 필터로 Python 루프 대비 성능 우위 및 limit 전 선행 필터링 보장.

    Args:
        user: 로그인 사용자 객체 (name, username 속성 보유)

    Returns:
        SQLAlchemy OR 조건 리스트. 빈 리스트이면 필터 적용 불필요.

    Note:
        cast(structured_data, String).ilike() 패턴은 GIN 인덱스를 활용하지 못하므로
        테이블 크기가 증가하면 별도 JSONB 경로 인덱스 도입을 검토해야 한다.
    """
    from models import Order
    conds = []
    u_name = (user.name or '').strip()
    u_username = (user.username or '').strip()
    if u_name:
        safe_name = _escape_like(u_name)
        conds.append(Order.manager_name.ilike(f"%{safe_name}%", escape='\\'))
        conds.append(cast(Order.structured_data, String).ilike(f'%"{safe_name}"%', escape='\\'))
    if u_username:
        safe_uname = _escape_like(u_username)
        conds.append(Order.manager_name.ilike(f"%{safe_uname}%", escape='\\'))
        conds.append(cast(Order.structured_data, String).ilike(f'%"{safe_uname}"%', escape='\\'))
    return conds


def can_edit_erp(user):
    """ERP 페이지/API 수정 권한: 관리자 또는 CS/영업팀 소속만 True"""
    if not user:
        return False
    if user.role == 'ADMIN':
        return True
    return (user.team or '').strip() in ERP_EDIT_ALLOWED_TEAMS


def can_edit_erp_construction(user):
    """시공 대시보드 전용: 시공 시작/완료/불가 버튼 권한 — 관리자 또는 시공팀(CONSTRUCTION)"""
    if not user:
        return False
    if user.role == 'ADMIN':
        return True
    return (user.team or '').strip() == 'CONSTRUCTION'


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


def erp_construction_edit_required(f):
    """시공 시작/완료/불가 API 전용: can_edit_erp 또는 시공팀(CONSTRUCTION)이면 허용"""
    from functools import wraps

    @wraps(f)
    def wrapped(*args, **kwargs):
        user = get_user_by_id(session.get('user_id'))
        if not user:
            return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
        if can_edit_erp(user) or can_edit_erp_construction(user):
            return f(*args, **kwargs)
        return jsonify({
            'success': False,
            'message': '시공 시작/완료 권한이 없습니다. (관리자, 라홈팀, 영업팀 또는 시공팀만 가능)'
        }), 403
    return wrapped
