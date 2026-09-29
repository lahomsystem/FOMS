"""``app.py`` applies the gevent monkey patch before importing anything else.

psycopg 3 chooses its wait function when it is imported (``psycopg/waiting.py``): if the
gevent patch is not in place yet, DB waits block the whole gunicorn gevent worker. psycogreen
(psycopg2) has the same ordering need. So the only statement allowed before the
``SERVER_SOFTWARE`` patch block is ``import os`` (docs/plans/2026-09-28-psycopg3-migration-plan.md).
The PG lane test ``tests/postgres/test_gevent_db_cooperation_pg.py`` measures the block itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[3] / "app.py"


def _is_gevent_patch_block(node: ast.stmt) -> bool:
    return isinstance(node, ast.If) and "SERVER_SOFTWARE" in ast.unparse(node.test)


def test_gevent_patch_block_exists_and_patches_everything() -> None:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    blocks = [node for node in tree.body if _is_gevent_patch_block(node)]
    assert len(blocks) == 1
    assert "patch_all" in ast.unparse(blocks[0])


def test_only_import_os_precedes_the_gevent_patch() -> None:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    before = []
    for node in tree.body:
        if _is_gevent_patch_block(node):
            break
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # module docstring
        before.append(ast.unparse(node))
    assert before == ["import os"], before
