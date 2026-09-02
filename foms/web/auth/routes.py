"""Auth blueprint and helpers (canonical; SFC-B11B)."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, g, abort
from functools import wraps
from datetime import datetime, timezone
import logging
import re
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from db import get_db
from models import PasswordResetRequest, User, SecurityLog
from foms.services.datetime_kst import now_utc_naive
from foms.services.security.account_requests import (
    APPROVAL_ACTIVE,
    APPROVAL_PENDING,
    NOTIF_ACCOUNT_SIGNUP,
    RESET_DISMISSED,
    RESET_DONE,
    RESET_PENDING,
    notify_admins_account_event,
    submit_password_reset_request,
)
from foms.services.audit_writer import normalize_security_detail
from foms.services.user_deletion import (
    UserDeletionBlockedError,
    deactivate_user_preserving_audit,
    detach_user_references_for_deactivate,
    detach_user_references_for_delete,
)
from foms.services.post_auth_navigation import (
    authenticated_home_url,
    normalize_internal_next_url,
    resolve_post_login_redirect,
)
from foms.services.error_logging import log_handled_exception
from foms.services.security.password_policy import (
    WeakPasswordError,
    active_legacy_count,
    is_password_legacy,
    is_policy_enforced,
    legacy_counts_by_role,
    set_strong_password,
    validate_password_strength,
)

auth_bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)

# User roles 
ROLES = {
    'ADMIN': '관리자',         # Full access
    'MANAGER': '매니저',       # Can manage orders but not users
    'STAFF': '직원',           # Can view and add orders, limited edit
    'VIEWER': '뷰어'           # Read-only access
}

TEAMS = {
    'CS': 'CS(라홈팀/하우드팀)',
    'SALES': '영업팀',
    'DRAWING': '도면팀',
    'PRODUCTION': '생산팀',
    'CONSTRUCTION': '시공팀',
    'SHIPMENT': '출고팀',
    # 2026-09-02 신설(NAVER-SETTLE-01). 채널(네이버) 정산 탭 열람 대상 팀 —
    # 정본 판정은 foms/services/settlement_channel_access.py 의 게이트 함수다.
    'ACCOUNTING': '회계팀'
}

def log_access(action_message, user_id=None, additional_data=None, auto_commit=True,
               *, action=None, target_type=None, target_id=None, detail=None, db=None):
    """SecurityLog 1건을 본 세션에 기록한다(이름과 달리 ``access_logs`` 가 아니다).

    AUDIT-LOG T8: 자유 텍스트 ``message`` 외에 SQL 로 물을 수 있는 구조화 컬럼
    (``action``·``target_type``·``target_id``·``detail``)을 함께 남길 수 있다. 구조화
    인자는 전부 keyword-only 이며 생략 시 NULL 이므로 **기존 호출부는 무변경으로 동작**한다.

    ``additional_data`` 는 T8 이전에는 격납할 컬럼이 없어 **버려졌다** — 이제 ``detail``
    에 격납된다(dict 이 아니면 ``additional_data`` 키에 담는다). ``detail`` 을 함께 주면
    같은 키는 ``detail`` 이 이긴다(호출부가 명시한 구조화 값이 우선).

    :param action_message: 기록할 메시지(사람이 읽는 요약 — 첫 positional, 의미 불변).
    :param user_id: 행위 주체 user id(없으면 ``None``).
    :param additional_data: 부가 정보(dict 권장) — ``detail`` 에 병합 격납된다.
    :param auto_commit: True 면 즉시 commit.
    :param action: 행위 종류 태그(``USER_UPDATE``·``LOGIN_OK`` 등).
    :param target_type: 행위 대상 종류(``user`` 등). 대상이 없으면 ``None``.
    :param target_id: 행위 대상 PK. 대상이 없으면 ``None``.
    :param detail: 구조화 부가정보 dict(**비밀번호·PII 원문 금지**).
    :param db: 감사 행을 실을 세션. 생략하면 요청 세션(:func:`get_db`)을 쓴다.
        **호출자가 세션을 인자로 받아 쓰는 함수**(도면 전달 등)는 반드시 그 세션을 넘겨라 —
        여기서 :func:`get_db` 를 부르면 ``g.db`` 가 새로 붙어 요청 teardown 이 세션을 닫고,
        호출자가 들고 있던 ORM 인스턴스가 detach 된다(수명주기 오염).
    """
    try:
        db = db if db is not None else get_db()
        log = SecurityLog(
            user_id=user_id,
            message=action_message,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=normalize_security_detail(_merge_audit_detail(additional_data, detail)),
        )
        db.add(log)
        if auto_commit:
            db.commit()
    except Exception:
        # 감사 기록 실패가 원 요청을 죽이면 안 된다(fail-open) — 단 스택까지 반드시 로그.
        logger.warning("[LOG ERROR] SecurityLog 기록 실패: action=%s", action_message, exc_info=True)
        try:
            db.rollback()
        except Exception:
            log_handled_exception("auth log_access rollback")


def _merge_audit_detail(additional_data: object, detail: dict | None) -> dict | None:
    """``additional_data`` 와 ``detail`` 을 하나의 감사 detail dict 으로 합친다.

    T8 이전에 버려지던 ``additional_data`` 를 살리는 지점이다. dict 이 아닌 값(레거시
    호출부가 문자열/리스트를 넘길 수 있다)은 ``additional_data`` 키에 그대로 담아
    정보를 잃지 않는다. 충돌 시 명시 인자인 ``detail`` 이 이긴다.

    :param additional_data: 레거시 부가 정보(dict 또는 임의 값, ``None`` 허용).
    :param detail: 호출부가 명시한 구조화 detail dict(``None`` 허용).
    :return: 병합 dict, 또는 담을 게 없으면 ``None``.
    """
    merged = {}
    if isinstance(additional_data, dict):
        merged.update(additional_data)
    elif additional_data is not None:
        merged['additional_data'] = additional_data
    if detail:
        merged.update(detail)
    return merged or None


# 관리자 사용자 수정에서 from→to 로 감사할 필드(권한·소속·활성·식별자).
_AUDITED_USER_FIELDS = ('username', 'role', 'team', 'is_active', 'sender_phone')


def _user_audit_snapshot(user):
    """감사 대상 사용자 필드의 현재 값 스냅샷을 뜬다.

    :param user: 대상 :class:`~models.User` 인스턴스.
    :return: ``{필드명: 값}`` dict(변경 전/후 비교용).
    """
    return {field: getattr(user, field, None) for field in _AUDITED_USER_FIELDS}


def _format_audit_value(value):
    """감사 메시지용 값 표기(빈 값은 ``미지정``).

    :param value: 원본 값.
    :return: 사람이 읽는 문자열.
    """
    if value is None or value == '':
        return '미지정'
    return str(value)


def _user_change_summary(before, after):
    """변경된 필드만 ``field from→to`` 문자열 목록으로 만든다.

    :param before: 변경 전 스냅샷(:func:`_user_audit_snapshot`).
    :param after: 변경 후 스냅샷.
    :return: ``['role STAFF→ADMIN', 'team CS→SALES']`` — 변경이 없으면 빈 리스트.
    """
    changes = []
    for field in _AUDITED_USER_FIELDS:
        old_value = before.get(field)
        new_value = after.get(field)
        if old_value != new_value:
            changes.append(
                f"{field} {_format_audit_value(old_value)}→{_format_audit_value(new_value)}"
            )
    return changes


def _user_change_detail(before: dict, after: dict) -> dict:
    """변경된 필드만 ``{field: {'from': old, 'to': new}}`` 구조로 만든다(T8 detail 격납용).

    :func:`_user_change_summary` 의 구조화 쌍이다 — 사람용 요약은 message 로, SQL 질의용
    from→to 는 ``security_logs.detail`` 로 각각 간다. 감사 대상 필드는 str/bool/None 뿐이라
    값을 그대로 싣는다(JSON 직렬화 보증은 ``normalize_security_detail`` 이 담당).

    :param before: 변경 전 스냅샷(:func:`_user_audit_snapshot`).
    :param after: 변경 후 스냅샷.
    :return: ``{'role': {'from': 'STAFF', 'to': 'ADMIN'}}`` — 변경이 없으면 빈 dict.
    """
    changes = {}
    for field in _AUDITED_USER_FIELDS:
        old_value = before.get(field)
        new_value = after.get(field)
        if old_value != new_value:
            changes[field] = {'from': old_value, 'to': new_value}
    return changes


def is_password_strong(password):
    """Check if a password meets the current strong policy (PASSWORD-POLICY-01 SSOT).

    Thin compatibility shim delegating to the password-policy service so strength
    is defined in exactly one place.
    """
    ok, _reason = validate_password_strength(password)
    return ok


def get_user_by_username(username):
    """Retrieve user by username"""
    db = get_db()
    return db.query(User).filter(User.username == username).first()

def get_user_by_id(user_id):
    """Retrieve user by ID"""
    db = get_db()
    return db.query(User).filter(User.id == user_id).first()

def update_last_login(user_id):
    """Update the last login timestamp for a user as UTC-naive DB time."""
    try:
        db = get_db()
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
    except Exception as e:
        db.rollback()

def _build_next_param():
    """로그인 후 돌아갈 상대 경로를 생성한다(절대 URL 사용 금지)."""
    path = request.path or url_for('order_pages.index')
    try:
        query_string = request.query_string.decode('utf-8', errors='ignore')
    except Exception:
        query_string = ''
    return f"{path}?{query_string}" if query_string else path

def _normalize_next_url(raw_next):
    """next 파라미터를 안전한 내부 경로로 정규화."""
    fallback = url_for('order_pages.index')
    return normalize_internal_next_url(raw_next, fallback=fallback)

def login_required(f):
    """Decorator to require login for routes.
    g.current_user는 app.before_request(_set_current_user)에서 이미 설정됨 → 중복 DB 쿼리 제거.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('로그인이 필요합니다.', 'error')
            return redirect(url_for('auth.login', next=_build_next_param()))

        # g.current_user 재사용 (before_request에서 이미 DB 조회 완료)
        user = getattr(g, 'current_user', None)

        if not user or not user.is_active:
            session.clear()
            flash('로그인 세션이 유효하지 않습니다. 다시 로그인해주세요.', 'error')
            return redirect(url_for('auth.login', next=_build_next_param()))

        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    """Decorator to require specific roles for routes"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('로그인이 필요합니다.', 'error')
                return redirect(url_for('auth.login', next=request.url))
            
            user = get_user_by_id(session['user_id'])
            if not user:
                session.clear()
                flash('사용자를 찾을 수 없습니다. 다시 로그인해주세요.', 'error')
                return redirect(url_for('auth.login'))
            
            if user.role not in roles:
                flash('이 페이지에 접근할 권한이 없습니다.', 'error')
                log_access(f"권한 없는 접근 시도: {request.path}", user.id)
                return redirect(authenticated_home_url(user_id=user.id, request=request))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    session_user_id = session.get('user_id')
    if session_user_id:
        try:
            existing_user = get_user_by_id(session_user_id)
        except Exception:
            existing_user = None

        if existing_user and existing_user.is_active:
            return redirect(authenticated_home_url(user_id=session_user_id, request=request))

        session.clear()
        flash('기존 로그인 세션이 만료되어 다시 로그인해주세요.', 'warning')

    next_url = _normalize_next_url(request.values.get('next'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('아이디와 비밀번호를 모두 입력해주세요.', 'error')
            return render_template('auth/login.html', next_url=next_url)
        
        user = get_user_by_username(username)
        
        # T8: 로그인 감사는 대상(target)이 없는 행위다 — action + 실패 사유만 구조화한다.
        # 비밀번호는 원문·해시 어떤 형태로도 detail 에 넣지 않는다.
        if not user:
            log_access(f"로그인 실패: 사용자 {username} (계정 없음)",
                       action='LOGIN_FAIL',
                       detail={'reason': 'unknown_username', 'username': username})
            flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/login.html', next_url=next_url)

        if not user.is_active:
            log_access(f"로그인 실패: 비활성화된 계정 {username} (ID: {user.id})", user.id,
                       action='LOGIN_FAIL',
                       detail={'reason': 'inactive_account', 'username': username})
            flash('비활성화된 계정입니다. 관리자에게 문의하세요.', 'error')
            return render_template('auth/login.html', next_url=next_url)

        if not check_password_hash(user.password, password):
            log_access(f"로그인 실패: 사용자 {username} (ID: {user.id}) (비밀번호 오류)", user.id,
                       action='LOGIN_FAIL',
                       detail={'reason': 'bad_password', 'username': username})
            flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/login.html', next_url=next_url)

        # ACCOUNT-SELF-01: 승인 대기 계정 로그인 차단. 비밀번호 검증 **후**에만 상태를
        # 노출해 계정 소유자에게만 대기 사실을 알린다(타인 열거 방지).
        if (user.approval_status or APPROVAL_ACTIVE) == APPROVAL_PENDING:
            log_access(f"로그인 거부: 승인 대기 계정 {username} (ID: {user.id})", user.id,
                       action='LOGIN_FAIL',
                       detail={'reason': 'pending_approval', 'username': username})
            flash('가입 승인 대기 중입니다. 관리자 승인 후 로그인할 수 있습니다.', 'warning')
            return render_template('auth/login.html', next_url=next_url)

        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session.permanent = True
        
        update_last_login(user.id)
        log_access(f"로그인 성공: 사용자 {user.username} (ID: {user.id})", user.id,
                   action='LOGIN_OK', detail={'username': user.username})

        flash(f'{user.name}님, 환영합니다!', 'success')
        next_url = resolve_post_login_redirect(request.values.get('next'), user_id=user.id, request=request)
        return redirect(next_url)
    
    return render_template('auth/login.html', next_url=next_url)

@auth_bp.route('/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session.get('username', 'Unknown')
        
        session.clear()
        log_access(f"로그아웃: 사용자 {username} (ID: {user_id})", user_id)
        
        flash('로그아웃되었습니다.', 'success')
    
    return redirect(url_for('auth.login'))


@auth_bp.route('/switch-user/<int:target_user_id>', methods=['POST'])
@login_required
def switch_user(target_user_id):
    """관리자가 다른 사용자로 전환(드롭다운 아이디 이동).

    POST 전용이며 공용 write guard(WRITE-GUARD-01)의 CSRF/Origin 검증을 소비한다.
    권한은 ADMIN 세션만 허용하고 그 외에는 302 리다이렉트가 아니라 **403** 으로 차단한다
    (공유 ``role_required`` 데코레이터를 재사용하지 않는 이유: delete 등 다른 관리자 route 의
    리다이렉트 동작을 바꾸지 않기 위해 이 route 에만 국소로 권한 게이트를 둔다).

    :param target_user_id: 전환할 대상 사용자 id.
    :return: 전환 성공 시 대상 홈으로 302, 권한 없으면 403.
    """
    actor = g.current_user
    if not actor or actor.role != 'ADMIN':
        actor_id = getattr(actor, 'id', None)
        log_access(
            f"switch-user 권한 없는 시도 (요청자 ID:{actor_id}, 대상 ID:{target_user_id})",
            actor_id,
        )
        abort(403)
    admin_id = actor.id
    target = get_user_by_id(target_user_id)
    if not target:
        flash('대상 사용자를 찾을 수 없습니다.', 'error')
        return redirect(request.referrer or url_for('order_pages.index'))
    if not target.is_active:
        flash('비활성화된 사용자로 전환할 수 없습니다.', 'error')
        return redirect(request.referrer or url_for('order_pages.index'))
    if target_user_id == admin_id:
        flash('이미 본인 계정입니다.', 'info')
        return redirect(request.referrer or url_for('order_pages.index'))
    # 전환 전 관리자 저장 (원래 관리자로 돌아가기용)
    session['impersonating_from'] = admin_id
    session['user_id'] = target.id
    session['username'] = target.username
    session['role'] = target.role
    # T8: 계정 전환은 "관리자(actor)가 대상 계정(target)의 권한을 빌리는" 특권 행위다.
    log_access(f"관리자(ID:{admin_id})가 사용자로 전환: {target.username} (ID:{target.id})", admin_id,
               action='IMPERSONATE', target_type='user', target_id=target.id,
               detail={'target_username': target.username})
    flash(f'{target.name}({target.username})님으로 전환되었습니다.', 'success')
    # 시공팀 전환 시 출고 대시보드로 직접 이동 (이중 리다이렉트 방지)
    if target.team == 'CONSTRUCTION':
        return redirect(url_for('erp_shipment_page.erp_shipment_dashboard'))
    return redirect(request.referrer or authenticated_home_url(user_id=target.id, request=request))


@auth_bp.route('/switch-back', methods=['POST'])
@login_required
def switch_back():
    """전환된 관리자가 원래 관리자 계정으로 복귀."""
    admin_id = session.get('impersonating_from')
    if not admin_id:
        flash('전환된 상태가 아닙니다.', 'info')
        return redirect(url_for('order_pages.index'))
    admin = get_user_by_id(admin_id)
    if not admin:
        session.pop('impersonating_from', None)
        flash('원래 관리자 정보를 찾을 수 없습니다. 로그인해 주세요.', 'error')
        return redirect(url_for('auth.logout'))
    impersonated_id = session.get('user_id')
    session.pop('impersonating_from', None)
    session['user_id'] = admin.id
    session['username'] = admin.username
    session['role'] = admin.role
    # back 감사: 원 관리자(original actor) 귀속 + 어떤 계정에서 복귀했는지(전환 계정) 추적.
    log_access(
        f"관리자 복귀: {admin.username} (ID:{admin.id}) — 전환 계정 ID:{impersonated_id}에서 복귀",
        admin.id,
    )
    flash(f'관리자({admin.name}) 계정으로 복귀했습니다.', 'success')
    return redirect(request.referrer or url_for('order_pages.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """ACCOUNT-SELF-01: 셀프 가입 신청.

    DB 에 사용자가 하나도 없으면 최초 관리자 부트스트랩(즉시 ADMIN·ACTIVE, 기존 동작
    유지). 그 외에는 승인 대기(PENDING·VIEWER) 계정을 만들고 관리자에게 알림을 보낸다.
    승인 전에는 로그인할 수 없다(login 게이트).

    :return: GET 폼 렌더 또는 POST 처리 후 로그인 페이지로 redirect.
    """
    if 'user_id' in session:
        return redirect(authenticated_home_url(user_id=session.get('user_id'), request=request))

    db = get_db()
    is_bootstrap = db.query(User).count() == 0

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = (request.form.get('name') or '').strip()
        team = request.form.get('team') or None

        def _render_form():
            return render_template(
                'auth/register.html', teams=TEAMS, is_bootstrap=is_bootstrap)

        if not username or not password or not confirm_password or not name:
            flash('모든 필수 필드를 입력해주세요.', 'error')
            return _render_form()

        if len(username) < 2 or len(username) > 64:
            flash('사용자 아이디는 2~64자여야 합니다.', 'error')
            return _render_form()

        if password != confirm_password:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return _render_form()

        strong_ok, strong_reason = validate_password_strength(password)
        if not strong_ok:
            flash(strong_reason, 'error')
            return _render_form()

        if team is not None and team not in TEAMS:
            flash('유효하지 않은 팀입니다.', 'error')
            return _render_form()

        if get_user_by_username(username):
            flash('이미 존재하는 아이디입니다.', 'error')
            return _render_form()

        new_user = User(
            username=username,
            name=name,
            role='ADMIN' if is_bootstrap else 'VIEWER',
            team=None if is_bootstrap else team,
            is_active=True,
            approval_status=APPROVAL_ACTIVE if is_bootstrap else APPROVAL_PENDING,
        )
        # 새 계정은 항상 strong: 검증 통과 hash 를 설정하며 STRONG 버전을 명시 기록한다.
        set_strong_password(new_user, password)

        try:
            db.add(new_user)
            db.flush()
            new_user_id = new_user.id
            if is_bootstrap:
                db.commit()
                # 최초 관리자 부트스트랩은 계정 0명 상태에서 ADMIN 을 만드는 특권 경로다 —
                # 무기록으로 두면 "관리자가 어디서 왔는지" 추적이 불가능하다(스펙 §4 T5).
                log_access(
                    f"최초 관리자 부트스트랩 가입: {username} (ID: {new_user_id})",
                    new_user_id,
                    action='USER_BOOTSTRAP',
                    target_type='user',
                    target_id=new_user_id,
                    detail={'username': username, 'role': 'ADMIN'},
                )
                flash('관리자 계정이 성공적으로 등록되었습니다. 로그인해주세요.', 'success')
                return redirect(url_for('auth.login'))

            team_label = TEAMS.get(team, '미지정')
            notify_admins_account_event(
                db,
                notification_type=NOTIF_ACCOUNT_SIGNUP,
                title='새 가입 신청',
                message=(
                    f'{name}({username}) 님이 가입을 신청했습니다. '
                    f'희망 팀: {team_label}. 사용자 관리에서 승인/거절하세요.'
                ),
            )
            db.commit()
            log_access(f"가입 신청 접수: {username} (ID: {new_user_id})", new_user_id)
            flash('가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.rollback()
            log_handled_exception("auth register commit")
            flash('가입 신청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.', 'error')
            return _render_form()

    return render_template('auth/register.html', teams=TEAMS, is_bootstrap=is_bootstrap)


@auth_bp.route('/password-reset/request', methods=['GET', 'POST'])
def password_reset_request():
    """ACCOUNT-SELF-01: 비밀번호 재설정 요청 접수(관리자 처리형).

    계정 열거 방지: username 실존 여부와 무관하게 항상 동일한 성공 메시지를 보여주고,
    미매칭 입력도 감사용으로 기록한다. 실제 재설정은 관리자가 사용자 관리에서 수행한다.

    :return: GET 폼 렌더 또는 POST 접수 후 로그인 페이지로 redirect.
    """
    if 'user_id' in session:
        return redirect(url_for('auth.profile'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        if not username:
            flash('아이디를 입력해주세요.', 'error')
            return render_template('auth/password_reset_request.html')

        db = get_db()
        try:
            _row, created = submit_password_reset_request(
                db, username, request_ip=request.remote_addr)
            db.commit()
            if created:
                log_access(f"비밀번호 재설정 요청 접수: 입력 '{username}'")
        except Exception:
            db.rollback()
            log_handled_exception("auth password_reset_request commit")

        # 열거 방지: 매칭/중복/오류 여부와 무관하게 항상 동일 안내.
        flash('재설정 요청이 접수되었습니다. 관리자가 확인 후 처리합니다.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/password_reset_request.html')

# User Management Routes
@auth_bp.route('/admin/users')
@login_required
@role_required(['ADMIN'])
def user_list():
    db = get_db()
    
    team_order = case(
        {team: index for index, team in enumerate(TEAMS)},
        value=User.team,
        else_=len(TEAMS),
    )
    users = (
        db.query(User)
        .order_by(team_order, User.name, User.username)
        .all()
    )
    
    # Count admin users for template
    count_admin = db.query(User).filter(User.role == 'ADMIN').count()

    # PASSWORD-POLICY-01: legacy 상태만(hash/평문 미노출) — role별 count + in-app LEGACY 필터.
    legacy_user_ids = {u.id for u in users if is_password_legacy(u)}
    if request.args.get('policy') == 'legacy':
        users = [u for u in users if u.id in legacy_user_ids]

    # ACCOUNT-SELF-01: 가입 승인 대기·비밀번호 재설정 요청 큐.
    pending_users = [u for u in users if (u.approval_status or APPROVAL_ACTIVE) == APPROVAL_PENDING]
    users = [u for u in users if u.id not in {p.id for p in pending_users}]
    reset_requests = (
        db.query(PasswordResetRequest)
        .filter(PasswordResetRequest.status == RESET_PENDING)
        .order_by(PasswordResetRequest.created_at.desc())
        .all()
    )

    return render_template(
        'auth/user_list.html',
        users=users,
        pending_users=pending_users,
        reset_requests=reset_requests,
        count_admin=count_admin,
        ROLES=ROLES,
        TEAMS=TEAMS,
        legacy_user_ids=legacy_user_ids,
        legacy_counts=legacy_counts_by_role(db, active_only=True),
        legacy_active_total=active_legacy_count(db),
        policy_enforced=is_policy_enforced(db),
        policy_filter=request.args.get('policy'),
    )

@auth_bp.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN'])
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = (request.form.get('name') or '').strip() or '사용자'
        role = request.form.get('role')
        team = request.form.get('team')
        
        # Validate required fields
        if not all([username, password, role]):
            flash('모든 필수 입력 필드를 입력해주세요.', 'error')
            return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)
        
        # Check password strength (new accounts are always strong)
        strong_ok, strong_reason = validate_password_strength(password)
        if not strong_ok:
            flash(strong_reason, 'error')
            return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)
        
        # Check if username already exists
        if get_user_by_username(username):
            flash('이미 사용 중인 아이디입니다.', 'error')
            return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)
        
        # Validate role
        if role not in ROLES:
            flash('유효하지 않은 역할입니다.', 'error')
            return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)
        
        try:
            db = get_db()

            # Create new user with a policy-versioned strong password (records STRONG).
            new_user = User(
                username=username,
                name=name,
                role=role,
                team=team,
                is_active=True
            )
            set_strong_password(new_user, password)

            # Add and commit
            db.add(new_user)
            db.commit()
            
            # Log action
            log_access(f"사용자 추가: {username}", session.get('user_id'))
            
            flash('사용자가 성공적으로 추가되었습니다.', 'success')
            return redirect(url_for('auth.user_list'))
                
        except Exception as e:
            db.rollback()
            flash(f'사용자 추가 중 오류가 발생했습니다: {str(e)}', 'error')
            return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)
    
    return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)

@auth_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN'])
def edit_user(user_id):
    db = get_db()
    
    # Get the user from database
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        flash('사용자를 찾을 수 없습니다.', 'error')
        return redirect(url_for('auth.user_list'))
    
    # Prevent editing admin user if it's the only admin
    if user.role == 'ADMIN':
        admin_count = db.query(User).filter(User.role == 'ADMIN').count()
        
        if admin_count == 1 and request.method == 'POST' and request.form.get('role') != 'ADMIN':
            flash('마지막 관리자의 역할은 변경할 수 없습니다.', 'error')
            return redirect(url_for('auth.edit_user', user_id=user_id))
    
    if request.method == 'POST':
        # 어떤 필드도 아직 건드리기 전에 스냅샷 — username 은 아래에서 먼저 바뀐다.
        audit_before = _user_audit_snapshot(user)
        name = (request.form.get('name') or '').strip() or '사용자'
        role = request.form.get('role')
        team = request.form.get('team')
        is_active = request.form.get('is_active') == 'on'
        new_username = (request.form.get('username') or '').strip()

        # Validate required fields
        if not role:
            flash('역할은 필수 입력 필드입니다.', 'error')
            return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

        # Validate role
        if role not in ROLES:
            flash('유효하지 않은 역할입니다.', 'error')
            return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

        # 관리자만 사용자 아이디(username) 변경 가능
        if new_username and new_username != user.username:
            if len(new_username) < 2 or len(new_username) > 64:
                flash('사용자 아이디는 2~64자여야 합니다.', 'error')
                return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())
            if get_user_by_username(new_username):
                flash('이미 사용 중인 아이디입니다.', 'error')
                return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())
            user.username = new_username
            if user.id == session.get('user_id'):
                session['username'] = new_username

        try:
            was_active = user.is_active
            reactivating = (not was_active) and is_active

            # Handle password change if provided (admin reset is always strong; records STRONG).
            new_password = request.form.get('new_password')
            password_set_strong = False
            if new_password:
                try:
                    set_strong_password(user, new_password)
                    password_set_strong = True
                    flash('비밀번호가 변경되었습니다.', 'success')
                except WeakPasswordError as strength_err:
                    db.rollback()
                    flash(str(strength_err), 'error')
                    return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

            # inactive legacy 계정 blind reactivate 금지: 비활성 legacy 계정을 다시
            # 활성화하려면 강도 재검사(강력한 새 비밀번호 동반)를 통과해야 한다.
            if reactivating and is_password_legacy(user) and not password_set_strong:
                db.rollback()
                flash('비활성 상태의 기존(legacy) 계정을 다시 활성화하려면 강력한 새 비밀번호를 함께 설정해야 합니다.', 'error')
                return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

            # Update user
            user.name = name
            user.role = role
            user.team = team
            user.is_active = is_active
            # SHARE-SMS(D2): 개인 발신번호 — 숫자만 격납(하이픈 제거), 빈 값은 NULL(대표번호 폴백).
            sender_phone_raw = (request.form.get('sender_phone') or '').strip()
            sender_phone_digits = re.sub(r'\D', '', sender_phone_raw)
            user.sender_phone = sender_phone_digits or None

            # commit 후에는 속성이 expire 되므로 커밋 전에 after 를 확정한다.
            audit_after = _user_audit_snapshot(user)
            changes = _user_change_summary(audit_before, audit_after)
            change_detail = _user_change_detail(audit_before, audit_after)
            admin_id = session.get('user_id')

            db.commit()

            # Log action — 권한·소속·활성·아이디 변경은 field 별 from→to 로 남긴다.
            # T8: 같은 from→to 를 detail.changes 에 구조화해 SQL 질의를 가능하게 한다.
            log_access(
                f"사용자 #{user_id} 수정: {', '.join(changes)}" if changes
                else f"사용자 #{user_id} 정보 수정",
                admin_id,
                action='USER_UPDATE',
                target_type='user',
                target_id=user_id,
                detail={'changes': change_detail} if change_detail else None,
            )

            # 타인(및 본인) 비밀번호 관리자 재설정은 별도 행으로 분리 기록한다.
            # 비밀번호 값은 원문·해시 어떤 형태로도 기록하지 않는다(detail 포함).
            if password_set_strong:
                log_access(f"사용자 #{user_id} 비밀번호 재설정(관리자 #{admin_id})", admin_id,
                           action='USER_PASSWORD_RESET',
                           target_type='user', target_id=user_id)

            flash('사용자 정보가 성공적으로 업데이트되었습니다.', 'success')
            return redirect(url_for('auth.user_list'))

        except Exception as e:
            db.rollback()
            flash(f'사용자 정보 업데이트 중 오류가 발생했습니다: {str(e)}', 'error')
            return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

    count_admin = db.query(User).filter(User.role == 'ADMIN').count()
    return render_template('auth/edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=count_admin)

@auth_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def delete_user(user_id):
    """AUDIT-LOG T11(결정 ⑤): 사용자 "삭제" = 감사 actor 를 보존하는 비활성화 전환.

    row 를 지우면 ``security_logs``·``order_events``·``access_logs``·
    ``order_attachments`` 의 actor 가 함께 소멸해 "누가 했는가"를 사후에 물을 수 없다.
    그래서 운영 참조(담당자·수신자)만 끊고 계정은 비활성화·익명화한다. 원본 아이디는
    곧바로 재사용할 수 있고, 로그인은 ``is_active=False`` + 난수 비밀번호로 이중 차단된다.

    row 를 남기므로 ``UserDeletionBlockedError``(주문 배정·cutover marker 등 끊을 수 없는
    참조) 는 이 경로에서 발생하지 않는다 — 그 거부는 hard delete 인 ``reject_user`` 전용이고,
    거부 메시지가 안내하는 "계정 비활성화"가 곧 이 라우트다.

    :param user_id: 비활성화할 사용자 id.
    :return: 사용자 목록으로 redirect.
    """
    # Prevent deactivating self
    if user_id == session.get('user_id'):
        flash('자신의 계정은 삭제할 수 없습니다.', 'error')
        return redirect(url_for('auth.user_list'))

    db = get_db()

    # Get the user from database
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        flash('사용자를 찾을 수 없습니다.', 'error')
        return redirect(url_for('auth.user_list'))

    # Prevent deactivating last admin
    if user.role == 'ADMIN':
        admin_count = db.query(User).filter(User.role == 'ADMIN').count()

        if admin_count == 1:
            flash('마지막 관리자는 삭제할 수 없습니다.', 'error')
            return redirect(url_for('auth.user_list'))

    try:
        cleanup_summary = detach_user_references_for_deactivate(db, user_id)
        deactivation = deactivate_user_preserving_audit(user)
        db.commit()
        current_app.logger.info(
            "Deactivated user_id=%s cleanup=%s", user_id, cleanup_summary
        )

        # Log action — 감사 원장에는 "어떤 아이디였는지"가 남아야 추적이 끊기지 않는다.
        log_access(
            f"사용자 #{user_id} 비활성화(탈퇴 처리): {deactivation['username_before']}",
            session.get('user_id'),
            action='USER_DEACTIVATE',
            target_type='user',
            target_id=user_id,
            detail={
                'username_before': deactivation['username_before'],
                'username_after': deactivation['username_after'],
                'was_active': deactivation['was_active'],
                'cleanup': cleanup_summary,
            },
        )

        flash('사용자를 비활성화(탈퇴) 처리했습니다. 감사 기록은 보존됩니다.', 'success')
    except IntegrityError:
        db.rollback()
        current_app.logger.exception("User deactivation blocked by remaining references: user_id=%s", user_id)
        flash('사용자 삭제에 실패했습니다. 아직 정리되지 않은 참조 데이터가 있습니다.', 'error')
    except Exception:
        db.rollback()
        current_app.logger.exception("Unexpected user deactivation failure: user_id=%s", user_id)
        flash('사용자 삭제 중 오류가 발생했습니다.', 'error')

    return redirect(url_for('auth.user_list'))


@auth_bp.route('/admin/users/approve/<int:user_id>', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def approve_user(user_id):
    """ACCOUNT-SELF-01: 가입 신청 승인 — role·team 지정 후 ACTIVE 전환.

    :param user_id: 승인할 PENDING 사용자 id.
    :return: 사용자 목록으로 redirect.
    """
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()

    if not user or (user.approval_status or APPROVAL_ACTIVE) != APPROVAL_PENDING:
        flash('승인 대기 상태의 사용자가 아닙니다.', 'error')
        return redirect(url_for('auth.user_list'))

    role = request.form.get('role') or 'VIEWER'
    team = request.form.get('team') or None
    if role not in ROLES:
        flash('유효하지 않은 역할입니다.', 'error')
        return redirect(url_for('auth.user_list'))
    if team is not None and team not in TEAMS:
        flash('유효하지 않은 팀입니다.', 'error')
        return redirect(url_for('auth.user_list'))

    audit_before = _user_audit_snapshot(user)
    username = user.username
    try:
        user.role = role
        user.team = team
        user.approval_status = APPROVAL_ACTIVE
        # 승인은 권한 부여 행위다 — 무엇이 무엇으로 바뀌었는지 field 별로 남긴다.
        audit_after = _user_audit_snapshot(user)
        changes = _user_change_summary(audit_before, audit_after)
        change_detail = _user_change_detail(audit_before, audit_after)
        db.commit()
        summary = f", {', '.join(changes)}" if changes else ''
        log_access(
            f"가입 승인: {username} (ID: {user_id}{summary})",
            session.get('user_id'),
            action='USER_APPROVE',
            target_type='user',
            target_id=user_id,
            detail={'username': username, 'changes': change_detail},
        )
        flash(f'{user.name}({user.username}) 님의 가입을 승인했습니다.', 'success')
    except Exception:
        db.rollback()
        log_handled_exception("auth approve_user commit")
        flash('가입 승인 처리 중 오류가 발생했습니다.', 'error')
    return redirect(url_for('auth.user_list'))


@auth_bp.route('/admin/users/reject/<int:user_id>', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def reject_user(user_id):
    """ACCOUNT-SELF-01: 가입 신청 거절 — 상태 보존 없이 row 삭제(재신청 허용).

    :param user_id: 거절할 PENDING 사용자 id.
    :return: 사용자 목록으로 redirect.
    """
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()

    if not user or (user.approval_status or APPROVAL_ACTIVE) != APPROVAL_PENDING:
        flash('승인 대기 상태의 사용자가 아닙니다.', 'error')
        return redirect(url_for('auth.user_list'))

    username = user.username
    try:
        detach_user_references_for_delete(db, user_id)
        db.delete(user)
        db.commit()
        log_access(f"가입 거절(삭제): {username} (ID: {user_id})", session.get('user_id'))
        flash(f'{username} 님의 가입 신청을 거절했습니다.', 'success')
    except UserDeletionBlockedError as blocked:
        db.rollback()
        current_app.logger.warning(
            "Signup rejection blocked by audit references: user_id=%s reason=%s",
            user_id, blocked)
        flash(str(blocked), 'error')
    except Exception:
        db.rollback()
        log_handled_exception("auth reject_user commit")
        flash('가입 거절 처리 중 오류가 발생했습니다.', 'error')
    return redirect(url_for('auth.user_list'))


@auth_bp.route('/admin/password-reset/<int:request_id>/handle', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def handle_reset_request(request_id):
    """ACCOUNT-SELF-01: 재설정 요청 마감(action=done|dismiss).

    실제 비밀번호 재설정은 edit_user 의 기존 기능으로 수행하고, 이 라우트는 큐 상태만
    DONE/DISMISSED 로 전이한다.

    :param request_id: 처리할 PasswordResetRequest id.
    :return: 사용자 목록으로 redirect.
    """
    action = request.form.get('action')
    status_by_action = {'done': RESET_DONE, 'dismiss': RESET_DISMISSED}
    if action not in status_by_action:
        flash('유효하지 않은 처리 유형입니다.', 'error')
        return redirect(url_for('auth.user_list'))

    db = get_db()
    row = db.query(PasswordResetRequest).filter(PasswordResetRequest.id == request_id).first()
    if not row or row.status != RESET_PENDING:
        flash('대기 중인 재설정 요청이 아닙니다.', 'error')
        return redirect(url_for('auth.user_list'))

    submitted = row.username_submitted
    status_before = row.status
    try:
        row.status = status_by_action[action]
        status_after = row.status
        row.handled_by_user_id = session.get('user_id')
        row.handled_at = now_utc_naive()
        db.commit()
        log_access(
            f"재설정 요청 #{request_id} 처리: status {status_before}→{status_after}, "
            f"입력 '{submitted}'",
            session.get('user_id'),
            action='RESET_REQUEST_HANDLE',
            target_type='password_reset_request',
            target_id=request_id,
            detail={'changes': {'status': {'from': status_before, 'to': status_after}}},
        )
        flash('재설정 요청을 처리했습니다.', 'success')
    except Exception:
        db.rollback()
        log_handled_exception("auth handle_reset_request commit")
        flash('재설정 요청 처리 중 오류가 발생했습니다.', 'error')
    return redirect(url_for('auth.user_list'))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """프로필 페이지 - 사용자 정보 및 비밀번호 변경."""
    user_id = session.get("user_id")
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        session.clear()
        flash("사용자를 찾을 수 없습니다. 다시 로그인해주세요.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        name = request.form.get("name")

        if not name:
            flash("이름을 입력해주세요.", "error")
            return render_template("auth/profile.html", user=user)

        try:
            user.name = name
            db.commit()

            if current_password and new_password and confirm_password:
                if not check_password_hash(user.password, current_password):
                    flash("현재 비밀번호가 일치하지 않습니다.", "error")
                    return render_template("auth/profile.html", user=user)

                if new_password != confirm_password:
                    flash("새 비밀번호가 일치하지 않습니다.", "error")
                    return render_template("auth/profile.html", user=user)

                strong_ok, strong_reason = validate_password_strength(new_password)
                if not strong_ok:
                    flash(strong_reason, "error")
                    return render_template("auth/profile.html", user=user)

                # 본인 변경도 항상 strong: 검증 통과 hash 설정 + STRONG 버전 기록.
                set_strong_password(user, new_password)
                db.commit()
                log_access("비밀번호 변경 완료", user_id)
                flash("비밀번호가 성공적으로 변경되었습니다.", "success")

            flash("프로필이 업데이트되었습니다.", "success")
            return redirect(url_for("auth.profile"))

        except Exception as e:
            db.rollback()
            flash(f"프로필 업데이트 중 오류가 발생했습니다: {str(e)}", "error")
            return render_template("auth/profile.html", user=user)

    return render_template("auth/profile.html", user=user)
