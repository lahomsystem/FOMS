"""B1: SketchUp Intake — parse jobs, model snapshots, artifact + candidate columns.

Adds:
- `designer_drawing_artifacts.file_type` accepts skp/skb (string column, no
  native enum) plus new audit columns (original_filename, storage_key,
  mime_type, size_bytes, sha256, analysis_kind).
- `designer_drawing_artifacts.source` accepts sketchup_upload/sketchup_worker.
- `designer_extraction_candidates.last_preview_ack_at` / `_hash` / `_error`
  for the approve gate (plan §4.2.4, §9.4).
- `designer_sketchup_parse_jobs` — PostgreSQL row-locking queue.
- `designer_sketchup_model_snapshots` — immutable raw model snapshot.

Idempotency: every DDL is IF NOT EXISTS / CREATE INDEX IF NOT EXISTS so
the migration is safe to re-run if a previous deploy half-applied. The
downgrade drops snapshot/job tables and the new candidate columns; the
artifact audit columns are left in place because they double as legacy
upload metadata and removing them would lose data.

Revision ID: designer_sketchup_intake
Revises: designer_c0_lego_ontology
"""

from __future__ import annotations

from alembic import op


revision = "designer_sketchup_intake"
down_revision = "designer_c0_lego_ontology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── designer_drawing_artifacts — SketchUp aware columns ──────
    # file_type / source are non-native-enum string columns in the ORM
    # (Enum(..., native_enum=False)), so widening the allowed values
    # requires no DDL on PostgreSQL — only adding the new audit columns.
    op.execute(
        "ALTER TABLE designer_drawing_artifacts "
        "ADD COLUMN IF NOT EXISTS original_filename VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE designer_drawing_artifacts "
        "ADD COLUMN IF NOT EXISTS storage_key VARCHAR(2000)"
    )
    op.execute(
        "ALTER TABLE designer_drawing_artifacts "
        "ADD COLUMN IF NOT EXISTS mime_type VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE designer_drawing_artifacts "
        "ADD COLUMN IF NOT EXISTS size_bytes INTEGER"
    )
    op.execute(
        "ALTER TABLE designer_drawing_artifacts "
        "ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE designer_drawing_artifacts "
        "ADD COLUMN IF NOT EXISTS analysis_kind VARCHAR(50)"
    )

    # ── designer_extraction_candidates — preview ack ledger ──────
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS last_preview_ack_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS last_preview_ack_hash VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "ADD COLUMN IF NOT EXISTS last_preview_ack_error TEXT"
    )

    # ── designer_sketchup_parse_jobs ─────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS designer_sketchup_parse_jobs (
            id SERIAL PRIMARY KEY,
            artifact_id INTEGER NOT NULL REFERENCES designer_drawing_artifacts(id),
            project_id INTEGER REFERENCES designer_projects(id),
            status VARCHAR(30) NOT NULL DEFAULT 'queued',
            worker_kind VARCHAR(50),
            parser_version VARCHAR(100) NOT NULL,
            input_sha256 VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(255) NOT NULL,
            lease_owner VARCHAR(120),
            lease_token VARCHAR(64),
            lease_expires_at TIMESTAMP WITH TIME ZONE,
            last_heartbeat_at TIMESTAMP WITH TIME ZONE,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            storage_keys_json JSON NOT NULL DEFAULT '{}'::json,
            error_code VARCHAR(100),
            error_text TEXT,
            metrics_json JSON,
            created_by_user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE
        )
        """
    )
    # Unique constraint — `(project_id, input_sha256, parser_code,
    # analyzer_contract_version)` collapses into a stable hash stored as
    # idempotency_key. Duplicate uploads on the same parser version surface
    # the existing job instead of creating a new one.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_sketchup_jobs_idempotency_key "
        "ON designer_sketchup_parse_jobs (idempotency_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_jobs_status_created_at "
        "ON designer_sketchup_parse_jobs (status, created_at)"
    )
    # Worker claim path — `FOR UPDATE SKIP LOCKED` ordering depends on this.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_jobs_claim "
        "ON designer_sketchup_parse_jobs (status, lease_expires_at, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_jobs_lease_owner "
        "ON designer_sketchup_parse_jobs (lease_owner)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_jobs_artifact_id "
        "ON designer_sketchup_parse_jobs (artifact_id)"
    )

    # ── designer_sketchup_model_snapshots ────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS designer_sketchup_model_snapshots (
            id SERIAL PRIMARY KEY,
            artifact_id INTEGER NOT NULL REFERENCES designer_drawing_artifacts(id),
            parse_job_id INTEGER NOT NULL REFERENCES designer_sketchup_parse_jobs(id),
            extraction_id INTEGER REFERENCES designer_drawing_extractions(id),
            parser_version VARCHAR(100) NOT NULL,
            sketchup_api_version VARCHAR(100),
            sketchup_model_version VARCHAR(100),
            load_status VARCHAR(100),
            units_json JSON NOT NULL DEFAULT '{}'::json,
            bbox_json JSON NOT NULL DEFAULT '{}'::json,
            raw_model_json JSON NOT NULL DEFAULT '{}'::json,
            layout_graph_json JSON NOT NULL DEFAULT '{}'::json,
            component_index_json JSON NOT NULL DEFAULT '{}'::json,
            material_index_json JSON NOT NULL DEFAULT '{}'::json,
            preview_assets_json JSON,
            warnings_json JSON NOT NULL DEFAULT '[]'::json,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_snapshots_artifact_id "
        "ON designer_sketchup_model_snapshots (artifact_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_snapshots_parse_job_id "
        "ON designer_sketchup_model_snapshots (parse_job_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sketchup_snapshots_extraction_id "
        "ON designer_sketchup_model_snapshots (extraction_id)"
    )


def downgrade() -> None:
    # Snapshot rows depend on parse jobs — drop in reverse FK order.
    op.execute("DROP TABLE IF EXISTS designer_sketchup_model_snapshots")
    op.execute("DROP TABLE IF EXISTS designer_sketchup_parse_jobs")

    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "DROP COLUMN IF EXISTS last_preview_ack_error"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "DROP COLUMN IF EXISTS last_preview_ack_hash"
    )
    op.execute(
        "ALTER TABLE designer_extraction_candidates "
        "DROP COLUMN IF EXISTS last_preview_ack_at"
    )

    # The artifact audit columns (original_filename, storage_key, mime_type,
    # size_bytes, sha256, analysis_kind) are intentionally left in place on
    # downgrade — they are passive audit metadata, dropping them would lose
    # user data, and the ORM treats them as nullable so older code keeps
    # working. Re-running upgrade() is a no-op for those columns.
