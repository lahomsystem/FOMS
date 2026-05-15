"""Railway 기동 시 WDPlanner V2 컬럼 존재 여부를 직접 확인하고 없으면 추가.

alembic_version 상태와 무관하게 실행되므로, alembic_version이 앞서 있어도
실제 컬럼이 빠진 경우를 복구한다.
"""
import os
import sys
import psycopg2
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("[SCHEMA] DATABASE_URL 없음 — 스킵")
    sys.exit(0)

p = urlparse(db_url)
conn = psycopg2.connect(
    host=p.hostname,
    port=p.port or 5432,
    dbname=p.path.lstrip("/"),
    user=p.username,
    password=p.password,
)
conn.autocommit = False
cur = conn.cursor()

DDL = [
    "ALTER TABLE designer_drawing_extractions ADD COLUMN IF NOT EXISTS routing_json JSON",
    "ALTER TABLE designer_drawing_extractions ADD COLUMN IF NOT EXISTS redaction_report_json JSON",
    "ALTER TABLE designer_extraction_candidates ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending_review'",
    "ALTER TABLE designer_extraction_candidates ADD COLUMN IF NOT EXISTS blocking_reasons_json JSON NOT NULL DEFAULT '[]'",
    "ALTER TABLE designer_design_cases ADD COLUMN IF NOT EXISTS source_candidate_id INTEGER REFERENCES designer_extraction_candidates(id)",
]

for sql in DDL:
    cur.execute(sql)
    print(f"[SCHEMA] OK: {sql[:80]}")

# alembic_version 보정: 아직 이전 버전으로 남아 있다면 HEAD로 올려준다
cur.execute("SELECT version_num FROM alembic_version")
versions = [r[0] for r in cur.fetchall()]
print(f"[SCHEMA] alembic_version: {versions}")

if "designer_wdplanner_v2_remediation" not in versions:
    cur.execute(
        "UPDATE alembic_version SET version_num = 'designer_wdplanner_v2_remediation' "
        "WHERE version_num = 'designer_eval_snapshots'"
    )
    print("[SCHEMA] alembic_version -> designer_wdplanner_v2_remediation 갱신")

conn.commit()
conn.close()
print("[SCHEMA] 완료")
