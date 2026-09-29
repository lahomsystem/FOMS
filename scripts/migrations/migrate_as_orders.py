from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from foms.services.db_url_resolver import postgres_dbapi_connect, postgresql_connect_kwargs_from_url
import json
import os

STAGING_URL = os.environ["STAGING_DATABASE_URL"]  # 비밀번호를 코드에 두지 않는다
PROD_URL = os.environ["PROD_DATABASE_URL"]
EXECUTE_MIGRATION = True # 실제 DB에 Insert됨

def get_as_orders(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        # AS 조건: status가 AS관련이거나 structured_data의 stage가 AS인 경우
        cur.execute("""
            SELECT * FROM orders 
            WHERE status IN ('AS', 'AS_RECEIVED', 'AS_COMPLETED')
               OR structured_data->'workflow'->>'stage' = 'AS'
               OR structured_data->'workflow'->>'stage' = 'AS처리'
        """)
        return cur.fetchall()

def get_all_prod_orders(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, customer_name, phone, address, product, status FROM orders")
        return cur.fetchall()

def get_attachments_for_orders(conn, order_ids):
    if not order_ids: return []
    with conn.cursor(row_factory=dict_row) as cur:
        query = "SELECT * FROM order_attachments WHERE order_id = ANY(%s)"
        cur.execute(query, (order_ids,))
        return cur.fetchall()

def normalize_string(s):
    if not s: return ""
    return str(s).replace(" ", "").replace("-", "").strip().lower()

def main():
    print("Connecting to Staging...")
    conn_stg = postgres_dbapi_connect(postgresql_connect_kwargs_from_url(STAGING_URL))
    print("Connecting to Production...")
    conn_prd = postgres_dbapi_connect(postgresql_connect_kwargs_from_url(PROD_URL))
    
    stg_as_orders = get_as_orders(conn_stg)
    print(f"Staging AS orders count: {len(stg_as_orders)}")
    
    prd_orders = get_all_prod_orders(conn_prd)
    print(f"Production total orders count: {len(prd_orders)}")
    
    # 공통 주문 판별 로직
    # Key: (normalized(customer_name), normalized(phone))
    prd_keys = {}
    for o in prd_orders:
        key = (normalize_string(o['customer_name']), normalize_string(o['phone']))
        if key not in prd_keys:
            prd_keys[key] = []
        prd_keys[key].append(o)
        
    to_migrate = []
    already_exists = []
    
    for stg_o in stg_as_orders:
        key = (normalize_string(stg_o['customer_name']), normalize_string(stg_o['phone']))
        if key in prd_keys:
            # 존재함
            already_exists.append((stg_o, prd_keys[key]))
        else:
            to_migrate.append(stg_o)
            
    print("\n--- Dry Run 결과 ---")
    print(f"공통 주문 (Production에 이미 존재): {len(already_exists)}건")
    print(f"이관 대상 (Production에 없음): {len(to_migrate)}건")
    
    if not to_migrate:
        print("이관할 대상이 없습니다.")
        return
        
    print("\n[이관 대상 목록]")
    for o in to_migrate:
        print(f" - ID:{o['id']} | {o['customer_name']} | {o['phone']} | {o['status']}")

    if not EXECUTE_MIGRATION:
        print("\n[안내] EXECUTE_MIGRATION = False 입니다. 실제 이관을 원하시면 코드를 변경 후 실행하세요.")
        return
        
    print("\n>>> 실제 이관을 시작합니다 <<<")
    # 트랜잭션 시작
    stg_ids = [o['id'] for o in to_migrate]
    attachments = get_attachments_for_orders(conn_stg, stg_ids)
    
    # stg_id 별 attachment 정리
    att_by_order = {}
    for att in attachments:
        o_id = att['order_id']
        if o_id not in att_by_order:
            att_by_order[o_id] = []
        att_by_order[o_id].append(att)

    try:
        with conn_prd.cursor() as cur:
            for o in to_migrate:
                # order insert
                stg_order_id = o['id']
                cols = []
                vals = []
                for k, v in o.items():
                    if k == 'id': continue
                    cols.append(k)
                    # jsonb 컬럼에는 dict/list 를 Jsonb 로 감싸 넣는다
                    if isinstance(v, dict) or isinstance(v, list):
                        vals.append(Jsonb(v))
                    else:
                        vals.append(v)
                
                col_str = ", ".join(cols)
                placeholders = ", ".join(["%s"] * len(vals))
                
                insert_query = f"INSERT INTO orders ({col_str}) VALUES ({placeholders}) RETURNING id;"
                cur.execute(insert_query, tuple(vals))
                new_order_id = cur.fetchone()[0]
                print(f" -> Inserted order: Staging ID {stg_order_id} => Prod ID {new_order_id}")
                
                # attachments insert
                if stg_order_id in att_by_order:
                    for att in att_by_order[stg_order_id]:
                        att_cols = []
                        att_vals = []
                        for k, v in att.items():
                            if k == 'id': continue
                            att_cols.append(k)
                            if k == 'order_id':
                                att_vals.append(new_order_id)
                            else:
                                att_vals.append(v)
                        att_col_str = ", ".join(att_cols)
                        att_placeholders = ", ".join(["%s"] * len(att_vals))
                        att_insert_query = f"INSERT INTO order_attachments ({att_col_str}) VALUES ({att_placeholders});"
                        cur.execute(att_insert_query, tuple(att_vals))
                    print(f"    -> Inserted {len(att_by_order[stg_order_id])} attachments.")
        
        conn_prd.commit()
        print("성공적으로 이관 및 커밋되었습니다.")
    except Exception as e:
        conn_prd.rollback()
        print(f"이관 중 오류 발생, 롤백했습니다: {e}")

if __name__ == '__main__':
    main()
