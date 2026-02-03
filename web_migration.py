import json
import os
import sqlalchemy
from sqlalchemy import create_engine, MetaData, Table, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Boolean
import glob
from models import User, Order, ChatRoom, ChatMessage, OrderEvent, OrderTask, AccessLog, SecurityLog, ChatRoomMember, ChatAttachment, OrderAttachment
from models import User, Order, ChatRoom, ChatMessage, OrderEvent, OrderTask, AccessLog, SecurityLog, ChatRoomMember, ChatAttachment, OrderAttachment
from wdcalculator_models import Estimate, EstimateHistory, EstimateOrderMatch
from wdcalculator_db import wd_calculator_session

def run_web_migration(sqlite_path, postgres_session, reset=False):
    """
    Reflected Web Migration:
    Reads from SQLite using reflection and writes to Postgres.
    reset: If True, deletes all data from target tables before migrating.
    """
    logs = []
    
    try:
        logs.append(f"Starting migration from {sqlite_path}...")
        
        # Determine Session for each model
        def get_session_for_model(model):
            if model in [Estimate, EstimateHistory, EstimateOrderMatch]:
                return wd_calculator_session
            return postgres_session

        # 0. Reset (if requested)
        if reset:
            logs.append("[RESET] Deleting existing data...")
            try:
                # Delete WDCalculator tables First (using WD session)
                wd_calculator_session.query(EstimateOrderMatch).delete()
                wd_calculator_session.query(EstimateHistory).delete()
                wd_calculator_session.query(Estimate).delete()
                wd_calculator_session.commit()

                # Delete Main tables (in order of dependencies)
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
                wd_calculator_session.rollback()
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
        JSON_COLUMNS = ['structured_data', 'meta', 'payload', 'file_info', 'estimate_data']

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
            ChatAttachment,
            Estimate,
            EstimateHistory,
            EstimateOrderMatch
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
                        
                        # Precheck for Booleans
                        bool_columns = [c.key for c in model_cls.__table__.columns if isinstance(c.type, Boolean)]

                        for row in rows:
                            row_dict = dict(row._mapping)
                            
                            # Check existence if PK exists in row
                            if pk_name in row_dict:
                                # Use correct session for query
                                exist_session = get_session_for_model(model_cls)
                                existing = exist_session.query(model_cls).get(row_dict[pk_name])
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
                                    # Forced Boolean Conversion
                                    elif k in bool_columns:
                                        if str(v) in ['1', 't', 'true', 'True']:
                                            filtered_data[k] = True
                                        elif str(v) in ['0', 'f', 'false', 'False', 'None']:
                                            filtered_data[k] = False
                                        else:
                                            filtered_data[k] = bool(v)
                                    else:
                                        filtered_data[k] = v
                            
                            new_obj = model_cls(**filtered_data)
                            
                            # Use correct session
                            session = get_session_for_model(model_cls)
                            session.add(new_obj)
                            count += 1
                            
                        # Commit both sessions
                        postgres_session.commit()
                        wd_calculator_session.commit()
                        
                        # Reset Sequence (Fix IntegrityError)
                        try:
                            schema = 'wdcalculator' if model_cls in [Estimate, EstimateHistory, EstimateOrderMatch] else 'public'
                            seq_sql = text(f"SELECT setval(pg_get_serial_sequence('{schema}.{tablename}', 'id'), coalesce(max(id), 1), true) FROM {schema}.{tablename}")
                            session.execute(seq_sql)
                            session.commit()
                            logs.append(f"  => Sequence reset for {tablename}.")
                        except Exception as e:
                            logs.append(f"  [WARN] Sequence reset failed for {tablename}: {e}")
                        
                        logs.append(f"  => {count} rows migrated.")
                        total_migrated_count += count
                        
                except Exception as e:
                    postgres_session.rollback()
                    wd_calculator_session.rollback()
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
