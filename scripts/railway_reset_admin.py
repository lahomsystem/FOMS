# -*- coding: utf-8 -*-
"""ASCII-only output for Railway env. Resets admin password to admin1234."""
import sys
import os

# Force UTF-8 for source/decode; ASCII for print
if sys.stdout.encoding and 'utf' not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and 'utf' not in sys.stderr.encoding.lower():
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 로컬에서 프로덕션 DB 비밀번호 재설정 시: RAILWAY_PUBLIC_DATABASE_URL 사용
if not os.environ.get('DATABASE_URL') and os.environ.get('RAILWAY_PUBLIC_DATABASE_URL'):
    url = os.environ['RAILWAY_PUBLIC_DATABASE_URL']
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[11:]
    os.environ['DATABASE_URL'] = url

def main():
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    pwd = os.environ.get('FOMS_ADMIN_DEFAULT_PASSWORD', 'admin1234')
    session = db_session()
    try:
        admin = session.query(User).filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password=generate_password_hash(pwd),
                name='admin',
                role='ADMIN',
                is_active=True
            )
            session.add(admin)
            print('Created admin (admin / ' + pwd + ')')
        else:
            admin.password = generate_password_hash(pwd)
            print('Updated admin password to: ' + pwd)
        session.commit()
        print('OK - login with admin / ' + pwd)
    except Exception as e:
        session.rollback()
        print('FAIL: ' + str(e))
        raise
    finally:
        session.close()

if __name__ == '__main__':
    main()
