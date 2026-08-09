"""ALEMBIC-HEADS-01 — alembic 단일 head 강제 게이트 (pre_push_smoke 포함).

2026-08-06 railway dev 빌드 2건 연속 FAILED 재발 방지: 동시 세션이 같은
부모 리비전에서 마이그레이션을 분기 푸시하면 predeploy의
``alembic upgrade head`` 가 "Multiple head revisions" 로 파산한다
(실사례: typedrift_00 + account_self_00, 둘 다 wiz_pending_00 부모).
push 전에 로컬에서 초 단위로 잡는다.

DB 연결 불필요 — ScriptDirectory가 migrations/versions 파일만 스캔한다
(env.py는 실행되지 않는다).
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_single_head() -> None:
    """migrations/versions 리비전 그래프의 head가 정확히 1개인지 검증한다.

    반환값 없음 — head가 2개 이상이면 AssertionError로 병합 절차를 안내한다.
    """
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"alembic head {len(heads)}개 발견: {heads} — 동시 세션 마이그레이션 분기. "
        "railway predeploy(alembic upgrade head)가 'Multiple head revisions'로 "
        "빌드를 파산시킨다. no-op merge 리비전으로 병합하라 "
        "(관례: migrations/versions/merge_account_self_typedrift_heads.py)."
    )
