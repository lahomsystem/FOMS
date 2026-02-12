import os
import urllib.parse
from sqlalchemy import create_engine, text

def _normalize_postgres_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url

def migrate():
    print("=== Railway DB Migration (Manual Input) ===")
    print("Railway 대시보드(Variables)에서 복사한 DATABASE_URL을 입력하고 Enter를 눌러주세요.")
    
    # input()을 사용하여 사용자로부터 직접 입력받음
    db_url = input("DATABASE_URL: ").strip()
    
    if not db_url:
        print("입력된 URL이 없습니다. 종료합니다.")
        return
    
    db_url = _normalize_postgres_url(db_url)
    print(f"Connecting to database...")
    
    try:
        # 인코딩 문제 방지를 위해 SQLAlchemy 사용
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # 컬럼 존재 여부 확인
            check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='order_attachments' AND column_name='user_id';")
            res = conn.execute(check_sql).fetchone()
            
            if not res:
                print("Adding 'user_id' column to 'order_attachments' table...")
                conn.execute(text("ALTER TABLE order_attachments ADD COLUMN user_id INTEGER REFERENCES users(id);"))
                conn.commit()
                print("✅ 마이그레이션 성공!")
            else:
                print("✨ 'user_id' 컬럼이 이미 존재합니다. (이미 완료됨)")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    migrate()
