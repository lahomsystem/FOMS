
import sys
import os

# 프로젝트 루트를 sys.path에 추가
sys.path.append(os.getcwd())

from sqlalchemy import text
from db import engine

def add_column():
    print("Attempting to add 'team' column to 'users' table...")
    try:
        with engine.connect() as conn:
            # 트랜잭션 시작
            trans = conn.begin()
            try:
                # PostgreSQL 구문
                conn.execute(text("ALTER TABLE users ADD COLUMN team VARCHAR(50)"))
                trans.commit()
                print("Successfully added 'team' column.")
            except Exception as e:
                trans.rollback()
                if "duplicate column" in str(e) or "already exists" in str(e):
                    print("Column 'team' already exists. Skipping.")
                else:
                    print(f"Error adding column: {e}")
                    # raise e # 에러 발생 시 굳이 멈출 필요 없으면 그냥 프린트만
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    add_column()
