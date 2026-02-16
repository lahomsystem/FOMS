import argparse
import datetime
import json
from sqlalchemy import text
from flask import Flask

# app.py의 Flask app과 db 헬퍼를 재사용
from app import app  # noqa
from db import get_db


STEP_SCHEMA = "ERP_BETA_STEP_1_SCHEMA"
STEP_ORDER_ATTACHMENTS_TABLE = "ERP_DASH_STEP_2_ORDER_ATTACHMENTS_TABLE"
STEP_HOLIDAY_CALENDAR = "ERP_DASH_STEP_3_HOLIDAY_CALENDAR_2026"
STEP_DASHBOARD_MVP = "ERP_DASH_STEP_4_DASHBOARD_MVP"
STEP_URL_NORMALIZE = "ERP_DASH_STEP_5_URL_NORMALIZE_VIEW"
STEP_EVENTS_TASKS_TABLES = "ERP_DASH_STEP_6_EVENTS_TASKS_TABLES"
STEP_BACKFILL_WORKFLOW = "ERP_DASH_STEP_7_BACKFILL_WORKFLOW"
STEP_TASKS_EVENTS_API_UI = "ERP_DASH_STEP_8_TASKS_EVENTS_API_UI"
STEP_DASHBOARD_3PANEL = "ERP_DASH_STEP_9_DASHBOARD_3PANEL"
STEP_AUTO_TASKS = "ERP_DASH_STEP_10_AUTO_TASKS"
STEP_BACKFILL_AUTO_TASKS = "ERP_DASH_STEP_11_BACKFILL_AUTO_TASKS"
STEP_POLICY_JSON = "ERP_DASH_STEP_12_POLICY_JSON"
STEP_TEMPLATES_JSON = "ERP_DASH_STEP_13_TEMPLATES_JSON"
STEP_ERP_BETA_FLAG = "ERP_DASH_STEP_14_ERP_BETA_FLAG"


def _ensure_build_steps_table(db):
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS system_build_steps (
        step_key VARCHAR(100) PRIMARY KEY,
        status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
        started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        message TEXT NULL,
        meta JSONB NULL
    );
    """))
    db.commit()


def _upsert_step(db, step_key, status, message=None, meta=None, started_at=None, completed_at=None):
    meta_json = json.dumps(meta, ensure_ascii=False) if isinstance(meta, (dict, list)) else None
    db.execute(
        text("""
        INSERT INTO system_build_steps (step_key, status, started_at, completed_at, message, meta)
        VALUES (:step_key, :status, :started_at, :completed_at, :message, CAST(:meta AS JSONB))
        ON CONFLICT (step_key)
        DO UPDATE SET
            status = EXCLUDED.status,
            started_at = COALESCE(system_build_steps.started_at, EXCLUDED.started_at),
            completed_at = EXCLUDED.completed_at,
            message = EXCLUDED.message,
            meta = COALESCE(EXCLUDED.meta, system_build_steps.meta);
        """),
        {
            "step_key": step_key,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "message": message,
            "meta": meta_json,
        }
    )
    db.commit()


def _get_step_status(db, step_key):
    row = db.execute(
        text("SELECT step_key, status, started_at, completed_at, message FROM system_build_steps WHERE step_key=:k"),
        {"k": step_key},
    ).fetchone()
    return dict(row._mapping) if row else None


def step_1_schema(db):
    """
    Step 1: orders 테이블에 ERP Beta 컬럼 추가 + 진행상태 기록
    - 재실행 가능(idempotent)
    """
    _ensure_build_steps_table(db)

    existing = _get_step_status(db, STEP_SCHEMA)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_SCHEMA} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_SCHEMA, "RUNNING", message="Applying ERP Beta schema to orders table", started_at=started_at)

    try:
        # orders 컬럼 추가 (Postgres: ADD COLUMN IF NOT EXISTS)
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS raw_order_text TEXT"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_data JSONB"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_schema_version INTEGER NOT NULL DEFAULT 1"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_confidence VARCHAR(20)"))
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS structured_updated_at TIMESTAMP"))
        db.commit()

        completed_at = datetime.datetime.now()
        _upsert_step(
            db,
            STEP_SCHEMA,
            "COMPLETED",
            message="ERP Beta schema applied successfully",
            completed_at=completed_at,
            meta={"orders_columns_added": ["raw_order_text", "structured_data", "structured_schema_version", "structured_confidence", "structured_updated_at"]},
        )
        print(f"[OK] {STEP_SCHEMA} completed")
    except Exception as e:
        db.rollback()
        completed_at = datetime.datetime.now()
        _upsert_step(
            db,
            STEP_SCHEMA,
            "FAILED",
            message=f"Failed: {str(e)}",
            completed_at=completed_at,
        )
        raise


def step_2_order_attachments_table(db):
    """Step 2: order_attachments 테이블 생성 (idempotent)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_ORDER_ATTACHMENTS_TABLE)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_ORDER_ATTACHMENTS_TABLE} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_ORDER_ATTACHMENTS_TABLE, "RUNNING", message="Creating order_attachments table", started_at=started_at)
    try:
        db.execute(text("""
        CREATE TABLE IF NOT EXISTS order_attachments (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            filename VARCHAR(255) NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            storage_key VARCHAR(500) NOT NULL,
            thumbnail_key VARCHAR(500) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_order_attachments_order_id ON order_attachments(order_id)"))
        db.commit()

        completed_at = datetime.datetime.now()
        _upsert_step(
            db,
            STEP_ORDER_ATTACHMENTS_TABLE,
            "COMPLETED",
            message="order_attachments table ready",
            completed_at=completed_at,
        )
        print(f"[OK] {STEP_ORDER_ATTACHMENTS_TABLE} completed")
    except Exception as e:
        db.rollback()
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_ORDER_ATTACHMENTS_TABLE, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_3_holiday_calendar_2026(db):
    """Step 3: data/holidays_kr_2026.json 생성 확인 (idempotent)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_HOLIDAY_CALENDAR)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_HOLIDAY_CALENDAR} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_HOLIDAY_CALENDAR, "RUNNING", message="Ensuring holiday calendar json exists", started_at=started_at)
    try:
        from services.business_calendar import get_holidays_kr
        _ = get_holidays_kr(2026)
        completed_at = datetime.datetime.now()
        _upsert_step(
            db,
            STEP_HOLIDAY_CALENDAR,
            "COMPLETED",
            message="holiday calendar ready (2026)",
            completed_at=completed_at,
        )
        print(f"[OK] {STEP_HOLIDAY_CALENDAR} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_HOLIDAY_CALENDAR, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_4_dashboard_mvp(db):
    """Step 4: ERP 대시보드 MVP 라우트/템플릿 반영 체크포인트 (코드 변경은 이미 적용됨)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_DASHBOARD_MVP)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_DASHBOARD_MVP} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_DASHBOARD_MVP, "RUNNING", message="Verifying ERP dashboard route/template", started_at=started_at)
    try:
        import os
        tpl_ok = os.path.exists(os.path.join(os.path.dirname(__file__), "templates", "erp_dashboard.html"))
        if not tpl_ok:
            raise RuntimeError("templates/erp_dashboard.html not found")
        # 라우트는 app import 시 등록되므로 import만 확인
        from app import app as _app  # noqa
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_DASHBOARD_MVP, "COMPLETED", message="ERP dashboard MVP ready", completed_at=completed_at)
        print(f"[OK] {STEP_DASHBOARD_MVP} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_DASHBOARD_MVP, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_5_url_normalize_view(db):
    """
    Step 5: presigned 만료 방지를 위한 URL 정규화(기존 로컬 URL -> /api/files/view/<key>)
    - chat_attachments.storage_url/thumbnail_url
    - orders.blueprint_image_url
    """
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_URL_NORMALIZE)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_URL_NORMALIZE} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_URL_NORMALIZE, "RUNNING", message="Normalizing stored URLs to /api/files/view/<key>", started_at=started_at)
    try:
        # chat_attachments: storage_url / thumbnail_url이 /static/uploads/* 인 경우 key 추출 후 view로 변환
        db.execute(text("""
        UPDATE chat_attachments
        SET storage_url = CONCAT('/api/files/view/', storage_key)
        WHERE storage_url LIKE '/static/uploads/%' OR storage_url LIKE '/api/chat/download/%';
        """))

        # thumbnail_url: /static/uploads/<key> 형태만 변환 (thumb key는 URL에서 잘라냄)
        db.execute(text("""
        UPDATE chat_attachments
        SET thumbnail_url = CONCAT('/api/files/view/', REPLACE(thumbnail_url, '/static/uploads/', ''))
        WHERE thumbnail_url LIKE '/static/uploads/%';
        """))

        # orders.blueprint_image_url: /static/uploads/<key> 형태만 변환
        db.execute(text("""
        UPDATE orders
        SET blueprint_image_url = CONCAT('/api/files/view/', REPLACE(blueprint_image_url, '/static/uploads/', ''))
        WHERE blueprint_image_url LIKE '/static/uploads/%';
        """))

        db.commit()
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_URL_NORMALIZE, "COMPLETED", message="URL normalization done", completed_at=completed_at)
        print(f"[OK] {STEP_URL_NORMALIZE} completed")
    except Exception as e:
        db.rollback()
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_URL_NORMALIZE, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_6_events_tasks_tables(db):
    """Step 6: order_events / order_tasks 테이블 생성 (idempotent)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_EVENTS_TASKS_TABLES)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_EVENTS_TASKS_TABLES} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_EVENTS_TASKS_TABLES, "RUNNING", message="Creating order_events/order_tasks tables", started_at=started_at)
    try:
        db.execute(text("""
        CREATE TABLE IF NOT EXISTS order_events (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            payload JSONB NULL,
            created_by_user_id INTEGER NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_order_events_order_id ON order_events(order_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_order_events_type ON order_events(event_type)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_order_events_created_at ON order_events(created_at)"))

        db.execute(text("""
        CREATE TABLE IF NOT EXISTS order_tasks (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
            owner_team VARCHAR(50) NULL,
            owner_user_id INTEGER NULL REFERENCES users(id),
            due_date VARCHAR NULL,
            meta JSONB NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_order_tasks_order_id ON order_tasks(order_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_order_tasks_status ON order_tasks(status)"))
        db.commit()

        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_EVENTS_TASKS_TABLES, "COMPLETED", message="order_events/order_tasks ready", completed_at=completed_at)
        print(f"[OK] {STEP_EVENTS_TASKS_TABLES} completed")
    except Exception as e:
        db.rollback()
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_EVENTS_TASKS_TABLES, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_7_backfill_workflow(db):
    """Step 7: structured_data에 workflow.stage가 없으면 기본값을 채움 (idempotent)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_BACKFILL_WORKFLOW)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_BACKFILL_WORKFLOW} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_BACKFILL_WORKFLOW, "RUNNING", message="Backfilling structured_data.workflow defaults", started_at=started_at)
    try:
        # workflow 키가 없거나 stage가 없는 경우에만 채운다.
        db.execute(text("""
        UPDATE orders
        SET structured_data = jsonb_set(
            COALESCE(structured_data, '{}'::jsonb),
            '{workflow}',
            jsonb_build_object(
                'stage', 'RECEIVED',
                'stage_updated_at', to_jsonb(NOW()::text)
            ),
            true
        )
        WHERE structured_data IS NOT NULL
          AND (structured_data->'workflow' IS NULL OR (structured_data->'workflow'->>'stage') IS NULL OR (structured_data->'workflow'->>'stage') = '');
        """))
        db.commit()

        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_BACKFILL_WORKFLOW, "COMPLETED", message="workflow defaults backfilled", completed_at=completed_at)
        print(f"[OK] {STEP_BACKFILL_WORKFLOW} completed")
    except Exception as e:
        db.rollback()
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_BACKFILL_WORKFLOW, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_8_tasks_events_api_ui(db):
    """
    Step 8: Tasks/Events API + ERP Beta UI 반영 체크포인트
    (코드 변경은 이미 적용되어 있으므로 존재 확인만)
    """
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_TASKS_EVENTS_API_UI)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_TASKS_EVENTS_API_UI} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_TASKS_EVENTS_API_UI, "RUNNING", message="Verifying tasks/events API and UI present", started_at=started_at)
    try:
        import os
        tpl = os.path.exists(os.path.join(os.path.dirname(__file__), "templates", "edit_order.html"))
        if not tpl:
            raise RuntimeError("templates/edit_order.html not found")
        from app import app as _app  # noqa
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_TASKS_EVENTS_API_UI, "COMPLETED", message="tasks/events API+UI ready", completed_at=completed_at)
        print(f"[OK] {STEP_TASKS_EVENTS_API_UI} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_TASKS_EVENTS_API_UI, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_9_dashboard_3panel(db):
    """Step 9: ERP 대시보드 3패널 UI 체크포인트"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_DASHBOARD_3PANEL)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_DASHBOARD_3PANEL} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_DASHBOARD_3PANEL, "RUNNING", message="Verifying ERP dashboard 3-panel UI present", started_at=started_at)
    try:
        import os
        tpl = os.path.exists(os.path.join(os.path.dirname(__file__), "templates", "erp_dashboard.html"))
        if not tpl:
            raise RuntimeError("templates/erp_dashboard.html not found")
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_DASHBOARD_3PANEL, "COMPLETED", message="dashboard 3-panel ready", completed_at=completed_at)
        print(f"[OK] {STEP_DASHBOARD_3PANEL} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_DASHBOARD_3PANEL, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_10_auto_tasks(db):
    """Step 10: SLA 기반 자동 Task 생성 로직 체크포인트"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_AUTO_TASKS)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_AUTO_TASKS} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_AUTO_TASKS, "RUNNING", message="Verifying auto task logic present", started_at=started_at)
    try:
        from app import app as _app  # noqa
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_AUTO_TASKS, "COMPLETED", message="auto tasks ready", completed_at=completed_at)
        print(f"[OK] {STEP_AUTO_TASKS} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_AUTO_TASKS, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_11_backfill_auto_tasks(db):
    """Step 11: 기존 주문 structured_data 기반 자동 Task 백필(중복 방지)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_BACKFILL_AUTO_TASKS)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_BACKFILL_AUTO_TASKS} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_BACKFILL_AUTO_TASKS, "RUNNING", message="Backfilling auto tasks from structured_data", started_at=started_at)
    try:
        from models import Order  # local import
        from erp_automation import apply_auto_tasks  # noqa

        orders = db.query(Order).filter(Order.deleted_at.is_(None), Order.structured_data.isnot(None)).order_by(Order.created_at.desc()).limit(500).all()

        changed = 0
        for o in orders:
            sd = o.structured_data or {}
            apply_auto_tasks(db, o.id, sd)
            changed += 1

        db.commit()
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_BACKFILL_AUTO_TASKS, "COMPLETED", message=f"Backfilled auto tasks for {changed} orders", completed_at=completed_at)
        print(f"[OK] {STEP_BACKFILL_AUTO_TASKS} completed ({changed} orders)")
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_BACKFILL_AUTO_TASKS, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_12_policy_json(db):
    """Step 12: data/erp_policy.json 존재 보장(없으면 기본 파일 생성)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_POLICY_JSON)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_POLICY_JSON} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_POLICY_JSON, "RUNNING", message="Ensuring data/erp_policy.json", started_at=started_at)
    try:
        import os
        import json as _json
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "erp_policy.json")
        if not os.path.exists(path):
            payload = {
                "version": 1,
                "rules": {
                    "blueprint_sla_hours": 48,
                    "measurement_imminent_business_days": 4,
                    "construction_imminent_business_days": 3,
                    "production_imminent_business_days": 2
                },
                "teams": {
                    "default_owner_team_by_stage": {
                        "RECEIVED": "SALES",
                        "HAPPYCALL": "CS",
                        "MEASURE": "MEASURE",
                        "DRAWING": "DRAWING",
                        "CONFIRM": "DRAWING",
                        "PRODUCTION": "PRODUCTION",
                        "CONSTRUCTION": "CONSTRUCTION"
                    }
                },
                "automation": {
                    "enable_auto_tasks": True,
                    "enable_stage_templates": True,
                    "enabled_auto_keys": [
                        "AUTO_URGENT",
                        "AUTO_BLUEPRINT_48H",
                        "AUTO_MEASURE_D4",
                        "AUTO_CONSTRUCT_D3",
                        "AUTO_PRODUCTION_D2"
                    ]
                }
            }
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(payload, f, ensure_ascii=False, indent=2)

        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_POLICY_JSON, "COMPLETED", message="erp_policy.json ready", completed_at=completed_at)
        print(f"[OK] {STEP_POLICY_JSON} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_POLICY_JSON, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_13_templates_json(db):
    """Step 13: data/erp_task_templates.json 존재 보장(없으면 기본 파일 생성)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_TEMPLATES_JSON)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_TEMPLATES_JSON} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_TEMPLATES_JSON, "RUNNING", message="Ensuring data/erp_task_templates.json", started_at=started_at)
    try:
        import os
        import json as _json
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "erp_task_templates.json")
        if not os.path.exists(path):
            payload = {
                "version": 1,
                "stages": {
                    "RECEIVED": [
                        {"key": "VERIFY_INFO", "title": "주문 정보 확인(고객/연락처/주소)", "owner_team": "SALES"}
                    ],
                    "HAPPYCALL": [
                        {"key": "HAPPYCALL_CONTACT", "title": "해피콜 진행(실측/시공 일정 확정)", "owner_team": "CS", "due": {"type": "measurement_date", "offset_business_days": -4}}
                    ],
                    "MEASURE": [
                        {"key": "MEASURE_CONFIRM", "title": "실측 진행 및 결과 정리", "owner_team": "MEASURE", "due": {"type": "measurement_date", "offset_business_days": 0}}
                    ],
                    "DRAWING": [
                        {"key": "DRAWING_CREATE", "title": "도면 작성/업로드", "owner_team": "DRAWING", "due": {"type": "blueprint_sla", "offset_hours": 48}},
                        {"key": "REQUEST_CONFIRM", "title": "고객 컨펌 요청/추적", "owner_team": "CS", "due": {"type": "construction_date", "offset_business_days": -3}}
                    ],
                    "CONFIRM": [
                        {"key": "FINAL_CONFIRM", "title": "최종 컨펌 수집/기록", "owner_team": "CS", "due": {"type": "construction_date", "offset_business_days": -3}}
                    ],
                    "PRODUCTION": [
                        {"key": "PRODUCTION_PLAN", "title": "생산 착수/일정 확정", "owner_team": "PRODUCTION", "due": {"type": "construction_date", "offset_business_days": -2}}
                    ],
                    "CONSTRUCTION": [
                        {"key": "CONSTRUCTION_PREP", "title": "시공 준비/자재/인력 확인", "owner_team": "CONSTRUCTION", "due": {"type": "construction_date", "offset_business_days": -1}},
                        {"key": "CONSTRUCTION_DONE", "title": "시공 완료 처리/사진 정리", "owner_team": "CONSTRUCTION", "due": {"type": "construction_date", "offset_business_days": 0}}
                    ]
                }
            }
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(payload, f, ensure_ascii=False, indent=2)

        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_TEMPLATES_JSON, "COMPLETED", message="erp_task_templates.json ready", completed_at=completed_at)
        print(f"[OK] {STEP_TEMPLATES_JSON} completed")
    except Exception as e:
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_TEMPLATES_JSON, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def step_14_erp_beta_flag(db):
    """Step 14: orders.is_erp_beta 컬럼 추가 + 인덱스 생성 (idempotent)"""
    _ensure_build_steps_table(db)
    existing = _get_step_status(db, STEP_ERP_BETA_FLAG)
    if existing and existing.get("status") == "COMPLETED":
        print(f"[SKIP] {STEP_ERP_BETA_FLAG} already completed")
        return

    started_at = datetime.datetime.now()
    _upsert_step(db, STEP_ERP_BETA_FLAG, "RUNNING", message="Adding orders.is_erp_beta flag", started_at=started_at)
    try:
        db.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_erp_beta BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_is_erp_beta ON orders(is_erp_beta)"))
        db.commit()

        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_ERP_BETA_FLAG, "COMPLETED", message="orders.is_erp_beta ready", completed_at=completed_at)
        print(f"[OK] {STEP_ERP_BETA_FLAG} completed")
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        completed_at = datetime.datetime.now()
        _upsert_step(db, STEP_ERP_BETA_FLAG, "FAILED", message=f"Failed: {str(e)}", completed_at=completed_at)
        raise


def main():
    parser = argparse.ArgumentParser(description="ERP Beta step-by-step builder (resumable via DB checkpoints)")
    parser.add_argument("--step", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14"], help="Run a single step")
    parser.add_argument("--resume", action="store_true", help="Resume from the next incomplete step")
    args = parser.parse_args()

    with app.app_context():
        db = get_db()
        _ensure_build_steps_table(db)

        if args.step == "1":
            step_1_schema(db)
            return
        if args.step == "2":
            step_2_order_attachments_table(db)
            return
        if args.step == "3":
            step_3_holiday_calendar_2026(db)
            return
        if args.step == "4":
            step_4_dashboard_mvp(db)
            return
        if args.step == "5":
            step_5_url_normalize_view(db)
            return
        if args.step == "6":
            step_6_events_tasks_tables(db)
            return
        if args.step == "7":
            step_7_backfill_workflow(db)
            return
        if args.step == "8":
            step_8_tasks_events_api_ui(db)
            return
        if args.step == "9":
            step_9_dashboard_3panel(db)
            return
        if args.step == "10":
            step_10_auto_tasks(db)
            return
        if args.step == "11":
            step_11_backfill_auto_tasks(db)
            return
        if args.step == "12":
            step_12_policy_json(db)
            return
        if args.step == "13":
            step_13_templates_json(db)
            return
        if args.step == "14":
            step_14_erp_beta_flag(db)
            return

        if args.resume:
            # 순차 실행(이미 COMPLETED면 skip) - 커넥션 로스트 시 재개
            step_1_schema(db)
            step_2_order_attachments_table(db)
            step_3_holiday_calendar_2026(db)
            step_4_dashboard_mvp(db)
            step_5_url_normalize_view(db)
            step_6_events_tasks_tables(db)
            step_7_backfill_workflow(db)
            step_8_tasks_events_api_ui(db)
            step_9_dashboard_3panel(db)
            step_10_auto_tasks(db)
            step_11_backfill_auto_tasks(db)
            step_12_policy_json(db)
            step_13_templates_json(db)
            step_14_erp_beta_flag(db)
            return

        print("Usage: python erp_build_step_runner.py --step 1..14  (or --resume)")


if __name__ == "__main__":
    main()

