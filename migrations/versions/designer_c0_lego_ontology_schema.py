"""C0 Contract Freeze: Lego Ontology & Reusable Block Schema.

신규 테이블 5개 생성:
  designer_reusable_blocks          — 재사용 가능한 geometry 블록 (Lego brick)
  designer_block_ontology_versions  — 블록 온톨로지 버전 스냅샷
  designer_block_ontology_relations — 버전 내 블록 간 관계 레코드
  designer_component_explanations   — PII-제거된 컴포넌트 설명 + 근거 분류
  designer_outline_polygons         — 도면에서 추출한 외곽 폴리곤 (mm 단위)

Contract:
- reusable_blocks, component_explanations: 사람이 승인(status='approved')해야만 사용 가능
- block_ontology_versions: 한 번에 하나만 'active' 허용 (별도 unique 인덱스 추가 예정)
- outline_polygons: is_valid=True 는 geometry validator 서비스 통과 후에만 설정
- AI는 어떤 테이블도 직접 approved/active 로 승격 불가 — 서비스 레이어 전용

Revision ID: designer_c0_lego_ontology
Revises: designer_b2_graph_contract
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "designer_c0_lego_ontology"
down_revision = "designer_b2_graph_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. designer_reusable_blocks ──────────────────────────
    op.create_table(
        "designer_reusable_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("block_key", sa.String(100), unique=True, nullable=False),
        sa.Column("label_ko", sa.String(200), nullable=False),
        sa.Column("label_en", sa.String(200), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "panel", "module", "assembly", "hardware", "other",
                name="designer_block_category",
                native_enum=False,
            ),
            nullable=False,
            server_default="panel",
        ),
        sa.Column("geometry_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("parameters_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("geometry_schema_version", sa.String(20), nullable=False, server_default="v2"),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "approved", "rejected", "retired",
                name="designer_block_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "source_design_case_id",
            sa.Integer(),
            sa.ForeignKey("designer_design_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ── 2. designer_block_ontology_versions ──────────────────
    op.create_table(
        "designer_block_ontology_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_key", sa.String(100), unique=True, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "active", "retired",
                name="designer_block_ontology_version_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ── 3. designer_block_ontology_relations ─────────────────
    op.create_table(
        "designer_block_ontology_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ontology_version_id",
            sa.Integer(),
            sa.ForeignKey("designer_block_ontology_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_key", sa.String(200), nullable=False),
        sa.Column("from_block_key", sa.String(100), nullable=False),
        sa.Column("to_block_key", sa.String(100), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence_case_ids_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replay_report_json", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "candidate", "approved", "rejected", "promoted",
                name="designer_block_relation_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="candidate",
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ── 4. designer_component_explanations ───────────────────
    op.create_table(
        "designer_component_explanations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "design_case_id",
            sa.Integer(),
            sa.ForeignKey("designer_design_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("component_id_in_graph", sa.String(200), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=False),
        sa.Column(
            "rationale_category",
            sa.Enum(
                "constraint", "preference", "customer_request", "codified_rule", "other",
                name="designer_explanation_rationale",
                native_enum=False,
            ),
            nullable=False,
            server_default="other",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "approved", "rejected", "retired",
                name="designer_explanation_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "embedding_id",
            sa.Integer(),
            sa.ForeignKey("designer_embeddings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ── 5. designer_outline_polygons ──────────────────────────
    op.create_table(
        "designer_outline_polygons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "extraction_id",
            sa.Integer(),
            sa.ForeignKey("designer_drawing_extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("view", sa.String(20), nullable=False, server_default="front"),
        sa.Column("vertices_mm_json", sa.JSON(), nullable=False),
        sa.Column("shape_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("area_mm2", sa.Float(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "validated", "rejected",
                name="designer_polygon_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    # 역순으로 DROP
    op.drop_table("designer_outline_polygons")
    op.drop_table("designer_component_explanations")
    op.drop_table("designer_block_ontology_relations")
    op.drop_table("designer_block_ontology_versions")
    op.drop_table("designer_reusable_blocks")
