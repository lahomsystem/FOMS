"""Auth blueprint and helpers (canonical; SFC-B11B)."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, g
from functools import wraps
from datetime import datetime, timezone
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
from models import User, SecurityLog
from foms.services.user_deletion import detach_user_references_for_delete
from foms.services.post_auth_navigation import (
    authenticated_home_url,
    normalize_internal_next_url,
    resolve_post_login_redirect,
)

auth_bp = Blueprint('auth', __name__)

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
    'SHIPMENT': '출고팀'
}

def log_access(action, user_id=None, additional_data=None, auto_commit=True):
    try:
        db = get_db()
        log = SecurityLog(user_id=user_id, message=action)
        db.add(log)
        if auto_commit:
            db.commit()
    except Exception as e:
        print(f"[LOG ERROR] Failed to log access: {e}")
        try:
            db.rollback()
        except Exception:
            pass

def is_password_strong(password):
    """Check if password meets security requirements"""
    return len(password) >= 4

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
        
        if not user:
            log_access(f"로그인 실패: 사용자 {username} (계정 없음)")
            flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/login.html', next_url=next_url)
        
        if not user.is_active:
            log_access(f"로그인 실패: 비활성화된 계정 {username} (ID: {user.id})", user.id)
            flash('비활성화된 계정입니다. 관리자에게 문의하세요.', 'error')
            return render_template('auth/login.html', next_url=next_url)
        
        if not check_password_hash(user.password, password):
            log_access(f"로그인 실패: 사용자 {username} (ID: {user.id}) (비밀번호 오류)", user.id)
            flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/login.html', next_url=next_url)
        
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session.permanent = True
        
        update_last_login(user.id)
        log_access(f"로그인 성공: 사용자 {user.username} (ID: {user.id})", user.id)
        
        flash(f'{user.name}님, 환영합니다!', 'success')
        next_url = resolve_post_login_redirect(request.values.get('next'), user_id=user.id, request=request)
        return redirect(next_url)
    
    return render_template('auth/login.html', next_url=next_url)

@auth_bp.route('/logout')
def logout():
    if 'user_id' in session:
        user_id = session['user_id']
        username = session.get('username', 'Unknown')
        
        session.clear()
        log_access(f"로그아웃: 사용자 {username} (ID: {user_id})", user_id)
        
        flash('로그아웃되었습니다.', 'success')
    
    return redirect(url_for('auth.login'))


@auth_bp.route('/switch-user/<int:target_user_id>')
@login_required
@role_required(['ADMIN'])
def switch_user(target_user_id):
    """관리자가 다른 사용자로 전환(드롭다운 아이디 이동)."""
    target = get_user_by_id(target_user_id)
    if not target:
        flash('대상 사용자를 찾을 수 없습니다.', 'error')
        return redirect(request.referrer or url_for('order_pages.index'))
    if not target.is_active:
        flash('비활성화된 사용자로 전환할 수 없습니다.', 'error')
        return redirect(request.referrer or url_for('order_pages.index'))
    admin_id = session['user_id']
    if target_user_id == admin_id:
        flash('이미 본인 계정입니다.', 'info')
        return redirect(request.referrer or url_for('order_pages.index'))
    # 전환 전 관리자 저장 (원래 관리자로 돌아가기용)
    session['impersonating_from'] = admin_id
    session['user_id'] = target.id
    session['username'] = target.username
    session['role'] = target.role
    log_access(f"관리자(ID:{admin_id})가 사용자로 전환: {target.username} (ID:{target.id})", admin_id)
    flash(f'{target.name}({target.username})님으로 전환되었습니다.', 'success')
    # 시공팀 전환 시 출고 대시보드로 직접 이동 (이중 리다이렉트 방지)
    if target.team == 'CONSTRUCTION':
        return redirect(url_for('erp_shipment_page.erp_shipment_dashboard'))
    return redirect(request.referrer or authenticated_home_url(user_id=target.id, request=request))


@auth_bp.route('/switch-back')
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
    session.pop('impersonating_from', None)
    session['user_id'] = admin.id
    session['username'] = admin.username
    session['role'] = admin.role
    log_access(f"관리자 복귀: {admin.username} (ID:{admin.id})", admin.id)
    flash(f'관리자({admin.name}) 계정으로 복귀했습니다.', 'success')
    return redirect(request.referrer or url_for('order_pages.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(authenticated_home_url(user_id=session.get('user_id'), request=request))
    
    db = get_db()
    user_count = db.query(User).count()
    
    if user_count > 0:
        flash('사용자 등록은 관리자를 통해서만 가능합니다.', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = request.form.get('name', '관리자')
        
        if not username or not password or not confirm_password:
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('auth/register.html')
        
        if password != confirm_password:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('auth/register.html')
        
        if not is_password_strong(password):
            flash('비밀번호는 4자 이상이어야 합니다.', 'error')
            return render_template('auth/register.html')
        
        if get_user_by_username(username):
            flash('이미 존재하는 아이디입니다.', 'error')
            return render_template('auth/register.html')
        
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            name=name,
            role='ADMIN',
            is_active=True
        )
        
        try:
            db.add(new_user)
            db.commit()
            flash('관리자 계정이 성공적으로 등록되었습니다. 로그인해주세요.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.rollback()
            flash(f'등록 중 오류 발생: {e}', 'error')
            
    return render_template('auth/register.html')

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
    
    return render_template('auth/user_list.html', users=users, count_admin=count_admin, ROLES=ROLES, TEAMS=TEAMS)

@auth_bp.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN'])
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name', '사용자')
        role = request.form.get('role')
        team = request.form.get('team')
        
        # Validate required fields
        if not all([username, password, role]):
            flash('모든 필수 입력 필드를 입력해주세요.', 'error')
            return render_template('auth/add_user.html', roles=ROLES, teams=TEAMS)
        
        # Check password strength
        if not is_password_strong(password):
            flash('비밀번호는 4자리 이상이어야 합니다.', 'error')
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
            
            # Hash password
            hashed_password = generate_password_hash(password)
            
            # Create new user
            new_user = User(
                username=username,
                password=hashed_password,
                name=name,
                role=role,
                team=team,
                is_active=True
            )
            
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
        name = request.form.get('name', '사용자')
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
            # Update user
            user.name = name
            user.role = role
            user.team = team
            user.is_active = is_active

            # Handle password change if provided
            new_password = request.form.get('new_password')
            if new_password:
                if is_password_strong(new_password):
                    user.password = generate_password_hash(new_password)
                    flash('비밀번호가 변경되었습니다.', 'success')
                else:
                    flash('비밀번호는 4자리 이상이어야 합니다.', 'error')

            db.commit()

            # Log action
            log_access(f"사용자 #{user_id} 정보 수정", session.get('user_id'))

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
    # Prevent deleting self
    if user_id == session.get('user_id'):
        flash('자신의 계정은 삭제할 수 없습니다.', 'error')
        return redirect(url_for('auth.user_list'))
    
    db = get_db()
    
    # Get the user from database
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        flash('사용자를 찾을 수 없습니다.', 'error')
        return redirect(url_for('auth.user_list'))
    
    # Prevent deleting last admin
    if user.role == 'ADMIN':
        admin_count = db.query(User).filter(User.role == 'ADMIN').count()
        
        if admin_count == 1:
            flash('마지막 관리자는 삭제할 수 없습니다.', 'error')
            return redirect(url_for('auth.user_list'))
    
    try:
        cleanup_summary = detach_user_references_for_delete(db, user_id)
        db.delete(user)
        db.commit()
        current_app.logger.info("Deleted user_id=%s cleanup=%s", user_id, cleanup_summary)
        
        # Log action
        log_access(f"사용자 #{user_id} 삭제", session.get('user_id'))
        
        flash('사용자가 성공적으로 삭제되었습니다.', 'success')
    except IntegrityError:
        db.rollback()
        current_app.logger.exception("User deletion blocked by remaining references: user_id=%s", user_id)
        flash('사용자 삭제에 실패했습니다. 아직 정리되지 않은 참조 데이터가 있습니다.', 'error')
    except Exception:
        db.rollback()
        current_app.logger.exception("Unexpected user deletion failure: user_id=%s", user_id)
        flash('사용자 삭제 중 오류가 발생했습니다.', 'error')
    
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

                if not is_password_strong(new_password):
                    flash("비밀번호는 4자리 이상이어야 합니다.", "error")
                    return render_template("auth/profile.html", user=user)

                user.password = generate_password_hash(new_password)
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
