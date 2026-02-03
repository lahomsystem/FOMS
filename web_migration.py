import json
import os
import sqlalchemy
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker
from models import User, Order, ChatRoom, ChatMessage, OrderEvent, OrderTask, AccessLog, SecurityLog, ChatRoomMember, ChatAttachment, OrderAttachment

def run_web_migration(sqlite_path, postgres_session, reset=False):
    """
    Reflected Web Migration:
    Reads from SQLite using reflection and writes to Postgres.
    reset: If True, deletes all data from target tables before migrating.
    """
    logs = []
    
    try:
        logs.append(f"Starting migration from {sqlite_path}...")

        # 0. Reset (if requested)
        if reset:
            logs.append("[RESET] Deleting existing data...")
            try:
                # Delete in order of dependencies (child first)
                postgres_session.query(ChatAttachment).delete()
                postgres_session.query(ChatMessage).delete()
                postgres_session.query(ChatRoomMember).delete()
                postgres_session.query(ChatRoom).delete()
                
                postgres_session.query(OrderEvent).delete()
                postgres_session.query(OrderTask).delete()
                postgres_session.query(OrderAttachment).delete()
                
                postgres_session.query(SecurityLog).delete()
                postgres_session.query(AccessLog).delete()
                
                postgres_session.query(Order).delete()
                postgres_session.query(User).delete()
                
                postgres_session.commit()
                logs.append("[RESET] All tables cleared.")
            except Exception as e:
                postgres_session.rollback()
                logs.append(f"[RESET ERROR] Failed to clear tables: {e}")
                return False, logs
        
        # 1. SQLite Connection & Reflection
        if not os.path.exists(sqlite_path):
            return False, [f"File not found: {sqlite_path}"]
            
        sqlite_url = f"sqlite:///{sqlite_path}"
        sqlite_engine = create_engine(sqlite_url)
        sqlite_meta = MetaData()
        
        try:
            # Reflect tables from SQLite
            sqlite_meta.reflect(bind=sqlite_engine)
            logs.append(f"SQLite Tables found: {list(sqlite_meta.tables.keys())}")
        except Exception as e:
            return False, [f"Failed to reflect SQLite tables: {e}"]

        # Used for JSON parsing
        JSON_COLUMNS = ['structured_data', 'meta', 'payload', 'file_info']

        # Define migration order (Parent -> Child)
        MODELS_TO_MIGRATE = [
            User, 
            Order, 
            AccessLog, 
            SecurityLog, 
            OrderEvent, 
            OrderTask, 
            OrderAttachment, 
            ChatRoom, 
            ChatRoomMember, 
            ChatMessage, 
            ChatAttachment
        ]

        total_migrated_count = 0

        for model_cls in MODELS_TO_MIGRATE:
             tablename = model_cls.__tablename__
             
             if tablename in sqlite_meta.tables:
                logs.append(f"[Migrating] Table: {tablename} ...")
                try:
                    source_table = sqlite_meta.tables[tablename]
                    with sqlite_engine.connect() as conn:
                        result = conn.execute(select(source_table))
                        rows = result.fetchall()
                        
                        count = 0
                        target_columns = set(c.key for c in model_cls.__table__.columns)
                        
                        # Primary Key check (assume 'id' is PK for all these models)
                        pk_name = 'id' 
                        
                        for row in rows:
                            row_dict = dict(row._mapping)
                            
                            # Check existence if PK exists in row
                            if pk_name in row_dict:
                                existing = postgres_session.query(model_cls).get(row_dict[pk_name])
                                if existing:
                                    continue
                            
                            filtered_data = {}
                            for k, v in row_dict.items():
                                if k in target_columns:
                                    # JSONB parsing
                                    if k in JSON_COLUMNS and isinstance(v, str):
                                        try:
                                            filtered_data[k] = json.loads(v)
                                        except:
                                            filtered_data[k] = {} # Fallback
                                    else:
                                        filtered_data[k] = v
                            
                            new_obj = model_cls(**filtered_data)
                            postgres_session.add(new_obj)
                            count += 1
                            
                        postgres_session.commit()
                        logs.append(f"  => {count} rows migrated.")
                        total_migrated_count += count
                        
                except Exception as e:
                    postgres_session.rollback()
                    logs.append(f"  [ERROR] {tablename} migration failed: {str(e)}")
             else:
                logs.append(f"[SKIP] Table '{tablename}' not found in SQLite.")

        logs.append(f"Migration completed. Total {total_migrated_count} rows.")
        return True, logs

    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        logs.append(f"Fatal Error: {str(e)}\n{trace}")
        return False, logs
