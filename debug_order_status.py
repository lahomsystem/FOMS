import psycopg2
import json

# DB 연결
try:
    conn = psycopg2.connect("postgresql://postgres:lahom@localhost:5432/furniture_orders")
    cur = conn.cursor()

    # 조회 대상 ID
    target_ids = (2125, 2119, 2118, 2117)
    
    # 쿼리 실행
    query = """
        SELECT id, status, structured_data 
        FROM orders 
        WHERE id IN %s
        ORDER BY id DESC
    """
    cur.execute(query, (target_ids,))
    rows = cur.fetchall()

    print(f"총 {len(rows)}건 조회됨\n" + "="*50)

    for row in rows:
        oid, status, sd = row
        print(f"[ID: {oid}]")
        print(f"1. DB Status Column: '{status}'")
        
        # JSONB 데이터 분석
        if sd:
            workflow = sd.get('workflow', {})
            current_stage = workflow.get('current_stage')
            stage = workflow.get('stage') # 일부 레거시 데이터 확인용
            
            print(f"2. structured_data['workflow']: {json.dumps(workflow, ensure_ascii=False)}")
            
            # 비교 분석
            match = (status == current_stage)
            print(f"3. 일치 여부: {'✅ 일치' if match else '❌ 불일치 (DB Status vs Workflow Stage)'}")
        else:
            print("2. structured_data: None")
            
        print("-" * 50)

    conn.close()

except Exception as e:
    print(f"Error: {e}")
