"""FOMS Brain AX Designer – Vector memory service stub.

pgvector extension is optional at MVP stage.  If unavailable, the service
logs the failure explicitly – it MUST NOT silently swallow errors.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_FAKE_EMBEDDING = os.environ.get("DESIGNER_FAKE_EMBEDDING", "0") == "1"


def store_embedding(
    owner_type: str,
    owner_id: int,
    text: str,
    metadata_json: Optional[dict] = None,
) -> dict:
    """Store text embedding for design memory retrieval.

    In fake mode: stores text only (no vector), returns stub row.
    In real mode: requires pgvector extension and an embedding model.

    NEVER silently ignores failures – always raises or logs explicitly.
    """
    from foms.persistence.designer.models import DesignerEmbedding
    from db import db_session

    if _FAKE_EMBEDDING:
        row = DesignerEmbedding(
            owner_type=owner_type,
            owner_id=owner_id,
            text=text,
            metadata_json=metadata_json or {},
        )
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        logger.info("[DESIGNER] fake embedding stored: id=%s", row.id)
        return {"id": row.id, "mode": "fake"}

    # Real mode: check pgvector availability
    try:
        from db import engine
        with engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
    except Exception as exc:
        logger.error("[DESIGNER] pgvector extension not available: %s", exc)
        raise RuntimeError(f"pgvector extension unavailable: {exc}") from exc

    # Placeholder for actual embedding model call
    raise NotImplementedError("Real embedding mode not yet implemented. Set DESIGNER_FAKE_EMBEDDING=1 for MVP.")
