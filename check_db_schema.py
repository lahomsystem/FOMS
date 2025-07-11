#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from db import get_db
from sqlalchemy import text
import sys

def check_database_schema():
    """데이터베이스 스키마 상태 확인"""
    try:
        print('=== 데이터베이스 연결 테스트 ===')
        db = get_db()
        print('✅ 데이터베이스 연결 성공')
        
        print('\n=== Orders 테이블 컬럼 확인 ===')
        query = text("""
        SELECT column_name, data_type, is_nullable, column_default 
        FROM information_schema.columns 
        WHERE table_name='orders' 
        ORDER BY ordinal_position
        """)
        
        result = db.execute(query).fetchall()
        
        if result:
            print('현재 Orders 테이블의 컬럼들:')
            for row in result:
                print(f'  - {row[0]} ({row[1]}) - Nullable: {row[2]} - Default: {row[3]}')
        else:
            print('❌ Orders 테이블을 찾을 수 없습니다.')
            return False
            
        print(f'\n총 컬럼 수: {len(result)}')
        
        # 스키마 업데이트에서 추가하려는 컬럼들 확인
        columns_to_check = [
            'measurement_date', 'measurement_time', 'completion_date', 'manager_name',
            'payment_amount', 'scheduled_date', 'as_received_date', 'as_completed_date',
            'is_regional', 'regional_sales_order_upload', 'regional_blueprint_sent',
            'regional_order_upload', 'shipping_scheduled_date'
        ]
        
        print('\n=== 스키마 업데이트 대상 컬럼 존재 여부 확인 ===')
        
        existing_columns = []
        missing_columns = []
        
        for column in columns_to_check:
            query = text(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='orders' AND column_name='{column}'
            """)
            result = db.execute(query).fetchone()
            
            if result:
                print(f'✅ {column} - 존재함')
                existing_columns.append(column)
            else:
                print(f'❌ {column} - 존재하지 않음')
                missing_columns.append(column)
        
        print(f'\n=== 요약 ===')
        print(f'존재하는 컬럼: {len(existing_columns)}개')
        print(f'누락된 컬럼: {len(missing_columns)}개')
        
        if missing_columns:
            print(f'누락된 컬럼들: {", ".join(missing_columns)}')
        
        print('\n=== 데이터베이스 연결 정보 ===')
        print(f'데이터베이스 URL: {db.bind.url}')
        
        return True
        
    except Exception as e:
        print(f'❌ 오류 발생: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = check_database_schema()
    if not success:
        sys.exit(1)