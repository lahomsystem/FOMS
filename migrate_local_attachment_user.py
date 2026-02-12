"""
로컬 PostgreSQL 데이터베이스 마이그레이션
order_attachments 테이블에 user_id 컬럼 추가
"""
from sqlalchemy import create_engine, text

# 로컬 DB URL (db.py 기본값 사용)
LOCAL_DB_URL = "postgresql+psycopg2://postgres:lahom@localhost/furniture_orders"

def migrate_local():
    print("=== 로컬 DB 마이그레이션 시작 ===")
    print(f"연결 대상: {LOCAL_DB_URL}")
    
    try:
        engine = create_engine(LOCAL_DB_URL)
        with engine.connect() as conn:
            # 컬럼 존재 여부 확인
            check_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='order_attachments' 
                AND column_name='user_id';
            """)
            res = conn.execute(check_sql).fetchone()
            
            if not res:
                print("'user_id' 컬럼 추가 중...")
                conn.execute(text("ALTER TABLE order_attachments ADD COLUMN user_id INTEGER REFERENCES users(id);"))
                conn.commit()
                print("✅ 로컬 DB 마이그레이션 완료!")
            else:
                print("✨ 'user_id' 컬럼이 이미 존재합니다.")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        print("\n💡 DB 접속 정보가 다른 경우, 스크립트 상단의 LOCAL_DB_URL을 수정해주세요.")

if __name__ == "__main__":
    migrate_local()
