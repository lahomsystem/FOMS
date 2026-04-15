"""Check admin user in remote DB."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

def main():
    from db import db_session
    from models import User
    from werkzeug.security import check_password_hash

    session = db_session()
    try:
        admin = session.query(User).filter_by(username='admin').first()
        if not admin:
            print('admin user NOT FOUND')
            return
        print('admin exists: id=%s, is_active=%s' % (admin.id, admin.is_active))
        print('password hash prefix: %s' % (admin.password[:50] if admin.password else 'None'))
        ok = check_password_hash(admin.password, 'admin1234')
        print('check_password_hash(admin.password, "admin1234"): %s' % ok)
    finally:
        session.close()

if __name__ == '__main__':
    main()
