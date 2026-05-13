"""Add pgvector extension and embedding column to designer_embeddings.

Revision ID: designer_pgvector
Revises: designer_ax_initial
Create Date: 2026-05-13

IMPORTANT: This migration requires the pgvector extension to be installed in PostgreSQL.
If pgvector is NOT available, this migration must explicitly fail – do not silently skip.
Run: CREATE EXTENSION vector; before applying.

Railway: add PGVECTOR=1 to env vars and ensure the PostgreSQL service supports vector.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "designer_pgvector"
down_revision: Union[str, None] = "designer_ax_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_pgvector() -> bool:
    """Check if pgvector extension is available."""
    try:
        result = op.get_bind().execute(
            sa.text("SELECT COUNT(*) FROM pg_available_extensions WHERE name = 'vector'")
        )
        row = result.fetchone()
        return bool(row and row[0] > 0)
    except Exception:
        return False


def upgrade() -> None:
    # Check if running on PostgreSQL (not SQLite)
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        print("[SKIP] pgvector migration skipped: not running on PostgreSQL")
        return

    if not _has_pgvector():
        raise RuntimeError(
            "pgvector extension is NOT available in this PostgreSQL installation. "
            "Run 'CREATE EXTENSION vector;' as superuser, or use a PostgreSQL "
            "service that supports pgvector before running this migration. "
            "This migration MUST NOT be silently skipped."
        )

    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column (1536-dim for OpenAI text-embedding-3-small)
    op.execute(
        "ALTER TABLE designer_embeddings ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )

    # Create HNSW index for efficient similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_designer_embeddings_hnsw "
        "ON designer_embeddings USING hnsw (embedding vector_cosine_ops)"
    )

    print("[INFO] pgvector migration applied: designer_embeddings.embedding column added")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    try:
        op.execute("DROP INDEX IF EXISTS ix_designer_embeddings_hnsw")
        op.execute("ALTER TABLE designer_embeddings DROP COLUMN IF EXISTS embedding")
    except Exception as e:
        print(f"[WARN] pgvector downgrade warning: {e}")
