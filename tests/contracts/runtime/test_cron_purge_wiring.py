"""retention purge 가 실제로 도는 cron 에 배선돼 있는지 고정한다 (REV-CLEANUP-01 / AUDIT-LOG T9).

purge 도구·보존기간·전용 config 파일은 2026-08 에 다 만들어졌는데, 그 config 를 읽을
**Railway 서비스가 등록되지 않아** purge 가 한 번도 돌지 않았다. 2026-09-11 운영 실측에서
보존 7일짜리 ``order_mutation_receipts`` 에 7일 초과 행 6,329건이 남아 있는 것으로 드러났다.
코드도 테스트도 전부 green 인 채로 1개월 넘게 아무것도 지워지지 않은 것이다.

그래서 고정하는 계약은 "purge 도구가 동작한다"가 아니라 **"purge 명령이 실제로 도는 cron 의
startCommand 안에 있다"** 이다. 같은 문자열이 세 곳(config-as-code 정본 · GraphQL 사본 ·
검증 스크립트 needle)에 흩어져 있으므로 셋의 일치도 함께 고정한다 — 어긋나면 어느 쪽이
도는지 알 수 없고, 그게 이번 실패의 모양이었다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CRON_TOML = _REPO_ROOT / "railway-cron.toml"
_CONFIGURE_TOOL = _REPO_ROOT / "tools" / "ops" / "railway_configure_cron_service.py"
_VERIFY_SCRIPT = _REPO_ROOT / "scripts" / "ops" / "verify_foms_cron_prod.ps1"

#: startCommand 안에 반드시 있어야 하는 조각. ``--apply`` 까지 포함한다 — 이게 빠지면
#: dry-run 이라 매일 "성공"하면서 한 행도 안 지운다(가장 눈치채기 어려운 실패).
_REQUIRED_FRAGMENTS = (
    "tools/cron/cleanup_order_drafts.py --execute",
    "tools/ops/purge_order_mutation_receipts.py",
    "tools/ops/purge_audit_logs.py --apply",
)


def _cron_start_command() -> str:
    """config-as-code 정본(``railway-cron.toml``)의 startCommand."""
    with _CRON_TOML.open("rb") as handle:
        return tomllib.load(handle)["deploy"]["startCommand"]


def test_cron_start_command_runs_both_purges() -> None:
    """매일 도는 cron 이 receipt purge 와 감사 원장 purge 를 모두 실행한다."""
    command = _cron_start_command()
    missing = [piece for piece in _REQUIRED_FRAGMENTS if piece not in command]
    assert not missing, (
        "railway-cron.toml 의 startCommand 에서 purge 배선이 빠졌다 — 이게 빠지면 원장이 "
        f"무한 증식한다.\n  missing={missing}\n  startCommand={command!r}"
    )


def test_receipt_purge_runs_with_apply() -> None:
    """영수증 purge 가 ``--apply`` 로 돈다 — dry-run 은 매일 성공하면서 0건을 지운다."""
    command = _cron_start_command()
    receipt_step = next(
        part for part in command.split("&&")
        if "purge_order_mutation_receipts.py" in part
    )
    assert "--apply" in receipt_step, receipt_step.strip()


def test_configure_tool_command_matches_config_as_code() -> None:
    """GraphQL 로 대시보드에 심는 사본이 toml 정본과 글자까지 같다."""
    source = _CONFIGURE_TOOL.read_text(encoding="utf-8")
    assert _cron_start_command() in source, (
        "tools/ops/railway_configure_cron_service.py 의 CRON_START_COMMAND 가 "
        "railway-cron.toml 과 어긋났다 — 어느 쪽이 도는지 알 수 없게 된다."
    )


def test_verify_script_expects_the_same_command() -> None:
    """운영 검증 스크립트의 needle 도 같은 문자열이다(통과해도 옛 값이면 의미 없다)."""
    source = _VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert _cron_start_command() in source, (
        "scripts/ops/verify_foms_cron_prod.ps1 의 기대 startCommand 가 "
        "railway-cron.toml 과 어긋났다."
    )


def test_no_orphan_purge_cron_config_file() -> None:
    """등록되지 않은 채 남아 "곧 돌 것처럼 보이던" 별도 cron config 가 되살아나지 않는다."""
    orphan = _REPO_ROOT / "railway-cron-receipt-purge.toml"
    assert not orphan.exists(), (
        "railway-cron-receipt-purge.toml 이 돌아왔다 — 이 파일은 어느 프로젝트에도 서비스로 "
        "등록되지 않아 purge 가 한 번도 실행되지 않는 원인이었다. 배선은 railway-cron.toml 에 "
        "체이닝돼 있다."
    )
