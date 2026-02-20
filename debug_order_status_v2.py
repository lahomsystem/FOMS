import psycopg2
import json
import sys

# 인코딩 설정 (윈도우 콘솔 호환)
sys.stdout.reconfigure(encoding='utf-8')

try:
    conn = psycopg2.connect("postgresql://postgres:lahom@localhost:5432/furniture_orders")
    cur = conn.cursor()

    target_ids = (2125, 2119, 2118, 2117)
    
    query = """
        SELECT id, status, structured_data 
        FROM orders 
        WHERE id IN %s
        ORDER BY id DESC
    """
    cur.execute(query, (target_ids,))
    rows = cur.fetchall()

    print(f"Count: {len(rows)}\n" + "="*50)

    for row in rows:
        oid, status, sd = row
        print(f"[ID: {oid}]")
        print(f"1. DB Status Column: '{status}'")
        
        if sd:
            workflow = sd.get('workflow', {})
            current_stage = workflow.get('current_stage')
            
            # 한글 포함된 JSON 출력 시 ensure_ascii=False 사용
            print(f"2. workflow: {json.dumps(workflow, ensure_ascii=False)}")
            
            match = (status == current_stage)
            match_str = "MATCH" if match else "MISMATCH (Status vs Workflow.current_stage)"
            print(f"3. Result: {match_str}")
        else:
            print("2. structured_data: None")
            
        print("-" * 50)

    conn.close()

except Exception as e:
    print(f"Error: {e}")
