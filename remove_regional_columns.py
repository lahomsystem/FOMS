#!/usr/bin/env python3
"""
지방 주문 관리에서 삭제된 컬럼들을 데이터베이스에서 제거하는 마이그레이션 스크립트

삭제할 컬럼:
- regional_measurement_upload (실측 업로드)
- regional_contract_sent (계약서 발송)
"""

from app import app, get_db
from sqlalchemy import text
import sys

def remove_columns():
    """삭제된 컬럼들을 데이터베이스에서 제거"""
    
    columns_to_remove = [
        'regional_measurement_upload',
        'regional_contract_sent'
    ]
    
    with app.app_context():
        db = get_db()
        
        try:
            print("지방 주문 관리 컬럼 삭제 시작...")
            
            for column in columns_to_remove:
                # 컬럼이 존재하는지 확인
                check_query = text(f"""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='orders' AND column_name='{column}'
                """)
                result = db.execute(check_query).fetchone()
                
                if result:
                    # 컬럼 삭제
                    drop_query = text(f"ALTER TABLE orders DROP COLUMN {column}")
                    db.execute(drop_query)
                    print(f"✓ 컬럼 '{column}' 삭제 완료")
                else:
                    print(f"- 컬럼 '{column}'이 이미 존재하지 않습니다")
            
            db.commit()
            print("\n모든 컬럼 삭제가 완료되었습니다!")
            
            # 현재 남은 지방 주문 관련 컬럼들 확인
            remaining_query = text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='orders' AND column_name LIKE 'regional_%'
            ORDER BY column_name
            """)
            remaining_columns = db.execute(remaining_query).fetchall()
            
            print("\n남은 지방 주문 관련 컬럼들:")
            for row in remaining_columns:
                print(f"  - {row[0]}")
                
        except Exception as e:
            db.rollback()
            print(f"오류 발생: {str(e)}")
            sys.exit(1)

if __name__ == '__main__':
    print("=== 지방 주문 관리 컬럼 삭제 마이그레이션 ===")
    print("다음 컬럼들이 삭제됩니다:")
    print("- regional_measurement_upload (실측 업로드)")
    print("- regional_contract_sent (계약서 발송)")
    print()
    
    confirm = input("계속 진행하시겠습니까? (y/N): ")
    if confirm.lower() in ['y', 'yes']:
        remove_columns()
    else:
        print("작업이 취소되었습니다.") 