from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from functools import wraps
from datetime import datetime
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

# Import DB and Models - these are in the parent directory so we use absolute imports or relative imports
# Given the project structure, we might need to adjust paths if app.py is the main entry point
try:
    from db import get_db
    from models import User, SecurityLog, OrderEvent, OrderTask, Notification, ChatRoomMember
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from db import get_db
    from models import User, SecurityLog, OrderEvent, OrderTask, Notification, ChatRoomMember

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

def log_access(action, user_id=None, additional_data=None):
    try:
        db = get_db()
        log = SecurityLog(user_id=user_id, message=action)
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[LOG ERROR] Failed to log access: {e}")
        try:
            db.rollback()
        except:
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
    """Update the last login timestamp for a user"""
    try:
        db = get_db()
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_login = datetime.now()
            db.commit()
    except Exception as e:
        db.rollback()

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('로그인이 필요합니다.', 'error')
            return redirect(url_for('auth.login', next=request.url))
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
                return redirect(url_for('index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    next_url = request.args.get('next', url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('아이디와 비밀번호를 모두 입력해주세요.', 'error')
            return render_template('login.html')
        
        user = get_user_by_username(username)
        
        if not user:
            log_access(f"로그인 실패: 사용자 {username} (계정 없음)")
            flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('login.html')
        
        if not user.is_active:
            log_access(f"로그인 실패: 비활성화된 계정 {username} (ID: {user.id})", user.id)
            flash('비활성화된 계정입니다. 관리자에게 문의하세요.', 'error')
            return render_template('login.html')
        
        if not check_password_hash(user.password, password):
            log_access(f"로그인 실패: 사용자 {username} (ID: {user.id}) (비밀번호 오류)", user.id)
            flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('login.html')
        
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        
        update_last_login(user.id)
        log_access(f"로그인 성공: 사용자 {user.username} (ID: {user.id})", user.id)
        
        flash(f'{user.name}님, 환영합니다!', 'success')
        return redirect(next_url)
    
    return render_template('login.html')

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
        return redirect(request.referrer or url_for('index'))
    if not target.is_active:
        flash('비활성화된 사용자로 전환할 수 없습니다.', 'error')
        return redirect(request.referrer or url_for('index'))
    admin_id = session['user_id']
    if target_user_id == admin_id:
        flash('이미 본인 계정입니다.', 'info')
        return redirect(request.referrer or url_for('index'))
    # 전환 전 관리자 저장 (원래 관리자로 돌아가기용)
    session['impersonating_from'] = admin_id
    session['user_id'] = target.id
    session['username'] = target.username
    session['role'] = target.role
    log_access(f"관리자(ID:{admin_id})가 사용자로 전환: {target.username} (ID:{target.id})", admin_id)
    flash(f'{target.name}({target.username})님으로 전환되었습니다.', 'success')
    return redirect(request.referrer or url_for('index'))


@auth_bp.route('/switch-back')
@login_required
def switch_back():
    """전환된 관리자가 원래 관리자 계정으로 복귀."""
    admin_id = session.get('impersonating_from')
    if not admin_id:
        flash('전환된 상태가 아닙니다.', 'info')
        return redirect(url_for('index'))
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
    return redirect(request.referrer or url_for('index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
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
            return render_template('register.html')
        
        if password != confirm_password:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('register.html')
        
        if not is_password_strong(password):
            flash('비밀번호는 4자 이상이어야 합니다.', 'error')
            return render_template('register.html')
        
        if get_user_by_username(username):
            flash('이미 존재하는 아이디입니다.', 'error')
            return render_template('register.html')
        
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
            
    return render_template('register.html')

# User Management Routes
@auth_bp.route('/admin/users')
@login_required
@role_required(['ADMIN'])
def user_list():
    db = get_db()
    
    # Get all users
    users = db.query(User).order_by(User.username).all()
    
    # Count admin users for template
    count_admin = db.query(User).filter(User.role == 'ADMIN').count()
    
    return render_template('user_list.html', users=users, count_admin=count_admin, ROLES=ROLES, TEAMS=TEAMS)

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
            return render_template('add_user.html', roles=ROLES, teams=TEAMS)
        
        # Check password strength
        if not is_password_strong(password):
            flash('비밀번호는 4자리 이상이어야 합니다.', 'error')
            return render_template('add_user.html', roles=ROLES, teams=TEAMS)
        
        # Check if username already exists
        if get_user_by_username(username):
            flash('이미 사용 중인 아이디입니다.', 'error')
            return render_template('add_user.html', roles=ROLES, teams=TEAMS)
        
        # Validate role
        if role not in ROLES:
            flash('유효하지 않은 역할입니다.', 'error')
            return render_template('add_user.html', roles=ROLES, teams=TEAMS)
        
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
            return render_template('add_user.html', roles=ROLES, teams=TEAMS)
    
    return render_template('add_user.html', roles=ROLES, teams=TEAMS)

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
            return render_template('edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

        # Validate role
        if role not in ROLES:
            flash('유효하지 않은 역할입니다.', 'error')
            return render_template('edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

        # 관리자만 사용자 아이디(username) 변경 가능
        if new_username and new_username != user.username:
            if len(new_username) < 2 or len(new_username) > 64:
                flash('사용자 아이디는 2~64자여야 합니다.', 'error')
                return render_template('edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())
            if get_user_by_username(new_username):
                flash('이미 사용 중인 아이디입니다.', 'error')
                return render_template('edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())
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
            return render_template('edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=db.query(User).filter(User.role == 'ADMIN').count())

    count_admin = db.query(User).filter(User.role == 'ADMIN').count()
    return render_template('edit_user.html', user=user, roles=ROLES, teams=TEAMS, count_admin=count_admin)

@auth_bp.route('/admin/users/delete/<int:user_id>')
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
        # Resolve foreign key constraints before deleting user
        
        # 1. Update Security Logs (Set user_id to NULL)
        db.query(SecurityLog).filter(SecurityLog.user_id == user_id).update({SecurityLog.user_id: None}, synchronize_session=False)
        
        # 2. Update Order Events (Set created_by_user_id to NULL)
        db.query(OrderEvent).filter(OrderEvent.created_by_user_id == user_id).update({OrderEvent.created_by_user_id: None}, synchronize_session=False)
        
        # 3. Update Order Tasks (Set owner_user_id to NULL)
        db.query(OrderTask).filter(OrderTask.owner_user_id == user_id).update({OrderTask.owner_user_id: None}, synchronize_session=False)
        
        # 4. Update Notifications (Set created_by/read_by to NULL)
        db.query(Notification).filter(Notification.created_by_user_id == user_id).update({Notification.created_by_user_id: None}, synchronize_session=False)
        db.query(Notification).filter(Notification.read_by_user_id == user_id).update({Notification.read_by_user_id: None}, synchronize_session=False)
        
        # 5. Remove from Chat Rooms
        db.query(ChatRoomMember).filter(ChatRoomMember.user_id == user_id).delete(synchronize_session=False)
        
        # Delete user
        db.delete(user)
        db.commit()
        
        # Log action
        log_access(f"사용자 #{user_id} 삭제", session.get('user_id'))
        
        flash('사용자가 성공적으로 삭제되었습니다.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'사용자 삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('auth.user_list'))
