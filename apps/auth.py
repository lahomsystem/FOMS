from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from functools import wraps
from datetime import datetime
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

# Import DB and Models - these are in the parent directory so we use absolute imports or relative imports
# Given the project structure, we might need to adjust paths if app.py is the main entry point
try:
    from db import get_db
    from models import User, SecurityLog
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from db import get_db
    from models import User, SecurityLog

auth_bp = Blueprint('auth', __name__)

# User roles 
ROLES = {
    'ADMIN': '관리자',         # Full access
    'MANAGER': '매니저',       # Can manage orders but not users
    'STAFF': '직원',           # Can view and add orders, limited edit
    'VIEWER': '뷰어'           # Read-only access
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
