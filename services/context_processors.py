"""Flask context processors 및 템플릿 필터 (app.py에서 분리)."""
import json
import os
from flask import session

from db import get_db
from models import User
from constants import STATUS, BULK_ACTION_STATUS
from apps.auth import get_user_by_id, ROLES
from services.menu_config import load_menu_config


def parse_json_string_filter(value):
    """템플릿 필터: value를 JSON으로 파싱, 실패 시 {} 반환."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}


def parse_json_string(json_string):
    """템플릿 유틸: json_string 파싱, 실패 시 None."""
    if not json_string:
        return None
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return None


def inject_statuses():
    """상태 상수 주입."""
    return dict(
        ALL_STATUS=STATUS,
        BULK_ACTION_STATUS=BULK_ACTION_STATUS
    )


def inject_status_list():
    """상태 목록과 현재 사용자 정보를 템플릿에 주입."""
    display_status = {k: v for k, v in STATUS.items() if k != 'DELETED'}
    bulk_action_status = {k: v for k, v in STATUS.items() if k != 'DELETED'}
    current_user = None
    if 'user_id' in session:
        current_user = get_user_by_id(session['user_id'])

    admin_switch_users = []
    impersonating_from_id = session.get('impersonating_from')
    if current_user and current_user.role == 'ADMIN':
        db = get_db()
        admin_switch_users = db.query(User).filter(
            User.is_active == True,
            User.id != current_user.id
        ).order_by(User.name).all()

    erp_beta_enabled = str(os.getenv('ERP_BETA_ENABLED', 'true')).lower() in ['1', 'true', 'yes', 'y', 'on']
    return dict(
        STATUS=display_status,
        BULK_ACTION_STATUS=bulk_action_status,
        ALL_STATUS=STATUS,
        ROLES=ROLES,
        current_user=current_user,
        admin_switch_users=admin_switch_users,
        impersonating_from_id=impersonating_from_id,
        erp_beta_enabled=erp_beta_enabled
    )


def utility_processor():
    """parse_json_string 유틸 함수 주입."""
    return dict(parse_json_string=parse_json_string)


def inject_menu():
    """메뉴 설정 주입."""
    return dict(menu=load_menu_config())


def register_context_processors(app):
    """app에 context processor 및 템플릿 필터 등록."""
    app.add_template_filter(parse_json_string_filter, 'parse_json_string')
    app.context_processor(inject_statuses)
    app.context_processor(inject_status_list)
    app.context_processor(utility_processor)
    app.context_processor(inject_menu)
