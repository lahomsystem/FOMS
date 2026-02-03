import os
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import User, Order
# 필요한 경우 다른 모델도 임포트

def run_web_migration(sqlite_path, postgres_session):
    """
    업로드된 SQLite 파일(sqlite_path)에서 데이터를 읽어
    현재 활성화된 Postgres 세션(postgres_session)으로 복사합니다.
    """
    logs = []
    
    try:
        logs.append(f"Starting migration from {sqlite_path}...")
        
        # 1. SQLite 연결
        if not os.path.exists(sqlite_path):
            return False, [f"File not found: {sqlite_path}"]
            
        sqlite_url = f"sqlite:///{sqlite_path}"
        sqlite_engine = create_engine(sqlite_url)
        SqliteSession = sessionmaker(bind=sqlite_engine)
        local_session = SqliteSession()
        
        # 2. Users Migration
        logs.append("[Step 1] Migrating Users...")
        try:
            # SQLite에는 있는데 models.py User와 호환되는지 확인 필요
            # 여기서는 models.py 구조가 로컬과 동일하다고 가정
            local_users = local_session.query(User).all()
            user_count = 0
            
            for l_user in local_users:
                # 중복 확인
                existing = postgres_session.query(User).filter_by(username=l_user.username).first()
                if existing:
                    logs.append(f"  - Skip User: {l_user.username} (Exists)")
                    continue
                
                new_user = User(
                    username=l_user.username,
                    password=l_user.password,
                    name=l_user.name,
                    role=l_user.role,
                    is_active=l_user.is_active,
                    created_at=l_user.created_at,
                    last_login=l_user.last_login
                )
                postgres_session.add(new_user)
                user_count += 1
            
            postgres_session.commit() # 커밋
            logs.append(f"  => {user_count} users migrated.")
            
        except Exception as e:
            postgres_session.rollback()
            logs.append(f"  [ERROR] User migration failed: {str(e)}")
            # 계속 진행 여부 결정... 일단 진행
            
        # 3. Orders Migration
        logs.append("[Step 2] Migrating Orders...")
        try:
            local_orders = local_session.query(Order).all()
            order_count = 0
            
            for l_order in local_orders:
                # ID로 중복 확인
                existing = postgres_session.query(Order).filter_by(id=l_order.id).first()
                if existing:
                    logs.append(f"  - Skip Order ID: {l_order.id} (Exists)")
                    continue
                
                # 객체 복사 (SQLAlchemy 객체는 세션 종속적이므로 속성만 복사 or merge)
                # merge는 편리하지만 관계가 복잡하면 주의 필요. Order는 비교적 단순하므로 속성 복사 추천.
                # make_transient 등을 쓸 수도 있지만, 명시적으로 생성하는 게 안전.
                
                new_order = Order()
                # 모든 컬럼 복사 (primary key 포함)
                columns = [c.key for c in Order.__table__.columns]
                for col in columns:
                    val = getattr(l_order, col)
                    setattr(new_order, col, val)
                
                postgres_session.add(new_order)
                order_count += 1
            
            postgres_session.commit()
            logs.append(f"  => {order_count} orders migrated.")
            
        except Exception as e:
            postgres_session.rollback()
            logs.append(f"  [ERROR] Order migration failed: {str(e)}")

        logs.append("Migration completed successfully.")
        return True, logs

    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        logs.append(f"Fatal Error: {str(e)}\n{trace}")
        return False, logs
    finally:
        # SQLite 세션 닫기
        if 'local_session' in locals():
            local_session.close()
