"""FOMS Brain AX Designer – initial tables.

Revision ID: designer_ax_initial
Revises: add_orders_erp_stage_updated_at
Create Date: 2026-05-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "designer_ax_initial"
down_revision: Union[str, None] = "add_orders_erp_stage_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_postgresql_enum(name: str, values: Sequence[str]) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if not name.replace("_", "").isalnum() or not name[0].isalpha():
        raise ValueError(f"Invalid PostgreSQL enum name: {name}")

    enum_identifier = bind.dialect.identifier_preparer.quote(name)
    enum_name_literal = name.replace("'", "''")
    escaped_values = [value.replace("'", "''") for value in values]
    values_sql = ", ".join(f"'{value}'" for value in escaped_values)
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regtype('{enum_name_literal}') IS NULL THEN
                    CREATE TYPE {enum_identifier} AS ENUM ({values_sql});
                END IF;
            EXCEPTION
                WHEN duplicate_object THEN
                    NULL;
            END
            $$;
            """
        )
    )

    actual_values = tuple(
        bind.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.oid = to_regtype(:enum_name)
                ORDER BY e.enumsortorder
                """
            ),
            {"enum_name": name},
        ).scalars()
    )
    expected_values = tuple(values)
    if actual_values != expected_values:
        raise RuntimeError(
            f"PostgreSQL enum {name} has labels {actual_values}, "
            f"expected {expected_values}."
        )


def upgrade() -> None:
    # Enums
    _ensure_postgresql_enum("designer_ontology_status", ("active", "draft", "retired"))
    _ensure_postgresql_enum(
        "designer_ai_run_status",
        ("queued", "running", "interrupt", "succeeded", "failed", "cancelled"),
    )
    _ensure_postgresql_enum(
        "designer_rule_candidate_status",
        ("draft", "approved", "rejected", "promoted"),
    )

    ontology_status = postgresql.ENUM("active", "draft", "retired", name="designer_ontology_status", create_type=False)
    ai_run_status = postgresql.ENUM(
        "queued", "running", "interrupt", "succeeded", "failed", "cancelled",
        name="designer_ai_run_status", create_type=False
    )
    rule_candidate_status = postgresql.ENUM("draft", "approved", "rejected", "promoted", name="designer_rule_candidate_status", create_type=False)

    # designer_ontology_versions
    op.create_table(
        "designer_ontology_versions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("version_key", sa.String(100), unique=True, nullable=False),
        sa.Column("status", ontology_status, nullable=False, server_default="draft"),
        sa.Column("rules_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # designer_projects
    op.create_table(
        "designer_projects",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # designer_project_versions
    op.create_table(
        "designer_project_versions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("designer_projects.id"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ontology_version_id", sa.Integer(), sa.ForeignKey("designer_ontology_versions.id"), nullable=True),
        sa.Column("design_json", postgresql.JSONB(), nullable=False),
        sa.Column("validation_json", postgresql.JSONB(), nullable=True),
        sa.Column("bom_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # designer_ai_runs
    op.create_table(
        "designer_ai_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("graph_name", sa.String(100), nullable=False),
        sa.Column("graph_version", sa.String(50), nullable=False, server_default="0.1.0"),
        sa.Column("thread_id", sa.String(200), nullable=False),
        sa.Column("status", ai_run_status, nullable=False, server_default="queued"),
        sa.Column("input_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("state_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # designer_corrections
    op.create_table(
        "designer_corrections",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("designer_projects.id"), nullable=True),
        sa.Column("project_version_id", sa.Integer(), sa.ForeignKey("designer_project_versions.id"), nullable=True),
        sa.Column("ai_run_id", sa.Integer(), sa.ForeignKey("designer_ai_runs.id"), nullable=True),
        sa.Column("before_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("after_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # designer_rule_candidates
    op.create_table(
        "designer_rule_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_correction_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("candidate_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("replay_report_json", postgresql.JSONB(), nullable=True),
        sa.Column("status", rule_candidate_status, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # designer_embeddings (text only; vector column added in pgvector migration)
    op.create_table(
        "designer_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_type", sa.String(100), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("designer_embeddings")
    op.drop_table("designer_rule_candidates")
    op.drop_table("designer_corrections")
    op.drop_table("designer_ai_runs")
    op.drop_table("designer_project_versions")
    op.drop_table("designer_projects")
    op.drop_table("designer_ontology_versions")

    op.execute("DROP TYPE IF EXISTS designer_rule_candidate_status")
    op.execute("DROP TYPE IF EXISTS designer_ai_run_status")
    op.execute("DROP TYPE IF EXISTS designer_ontology_status")
