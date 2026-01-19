"""
도면 이미지 URL 필드 마이그레이션 스크립트
orders 테이블에 blueprint_image_url 컬럼을 추가합니다.
"""
import sys
import os
from sqlalchemy import text, inspect
from db import engine
from app import app

def check_column_exists(column_name):
    """컬럼 존재 여부 확인"""
    try:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('orders')]
        return column_name in columns
    except Exception as e:
        print(f"컬럼 존재 확인 중 오류: {str(e)}")
        return False

def add_blueprint_column():
    """blueprint_image_url 컬럼 추가"""
    try:
        with engine.connect() as connection:
            # 컬럼이 이미 존재하는지 확인
            if check_column_exists('blueprint_image_url'):
                print("[OK] blueprint_image_url 컬럼이 이미 존재합니다.")
                return True
            
            # 컬럼 추가
            print("[INFO] blueprint_image_url 컬럼 추가 중...")
            connection.execute(text("ALTER TABLE orders ADD COLUMN blueprint_image_url TEXT"))
            connection.commit()
            print("[OK] blueprint_image_url 컬럼이 성공적으로 추가되었습니다.")
            return True
        
    except Exception as e:
        print(f"[ERROR] 마이그레이션 실패: {str(e)}")
        return False

if __name__ == '__main__':
    # 인코딩 설정
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    print("=" * 50)
    print("도면 이미지 URL 필드 마이그레이션 시작")
    print("=" * 50)
    
    with app.app_context():
        success = add_blueprint_column()
    
    if success:
        print("\n[SUCCESS] 마이그레이션이 성공적으로 완료되었습니다!")
        sys.exit(0)
    else:
        print("\n[ERROR] 마이그레이션이 실패했습니다.")
        sys.exit(1)
