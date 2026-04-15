"""
Legacy geocode_status/lat/lng 불일치 정리 스크립트 (2026-03-15).
- geocode_status='success'인데 lat IS NULL OR lng IS NULL → failed로 수정
- geocode_status='failed'인데 lat IS NOT NULL AND lng IS NOT NULL → success로 수정

실행: python scripts/maintenance/fix_geocode_status_inconsistency.py
      (Flask app context 필요 시: flask shell 내에서 실행)
"""
import os
import sys

# 프로젝트 루트 (scripts/maintenance/ → repo root)
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")),
)


def main():
    from db import get_db
    from models import Order
    from sqlalchemy import or_

    db = get_db()
    # success인데 좌표 없음
    success_no_coords = db.query(Order).filter(
        Order.geocode_status == 'success',
        or_(Order.lat.is_(None), Order.lng.is_(None))
    ).all()
    # failed인데 좌표 있음
    failed_with_coords = db.query(Order).filter(
        Order.geocode_status == 'failed',
        Order.lat.isnot(None),
        Order.lng.isnot(None)
    ).all()

    print(f"geocode_status='success' + 좌표 없음: {len(success_no_coords)}건")
    print(f"geocode_status='failed' + 좌표 있음: {len(failed_with_coords)}건")

    for o in success_no_coords:
        o.geocode_status = 'failed'
        print(f"  Order #{o.id}: success→failed (좌표 없음)")
    for o in failed_with_coords:
        o.geocode_status = 'success'
        print(f"  Order #{o.id}: failed→success (좌표 있음)")

    if success_no_coords or failed_with_coords:
        db.commit()
        print("정리 완료.")
    else:
        print("정리 대상 없음.")


if __name__ == '__main__':
    # Flask app context (get_db 사용 시)
    try:
        import app
        with app.app.app_context():
            main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
