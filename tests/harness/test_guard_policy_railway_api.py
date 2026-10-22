"""Railway 공개 GraphQL 변경 요청(mutation) 가드 — SPEC docs/specs/2026-10-22-railway-api-mutation-guard_SPEC.md.

R1: 명령 글자(인자·heredoc 본문·파이프로 먹이는 heredoc)에 Railway API 주소와 mutation 연산이 함께 있으면 ask.
R2: python·py·node 가 실행하는 스크립트 파일 안에 같은 조합이 있으면 ask. 조회(query)만이면 allow.
test_guard_policy.py 가 파일 크기 상한(500줄)에 닿아 따로 둔다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_API = "https://backboard.railway.com/graphql/v2"

CASES: list[tuple[str, str]] = [
    ("ask", f"curl -s {_API} -d '{{\"query\":\"mutation{{tcpProxyDelete(id:1)}}\"}}'"),
    ("ask", f"python -c \"q='mutation Del($i:String!){{tcpProxyDelete(id:$i)}}'; u='{_API}'\""),
    ("ask", f"python - <<'PY'\nurl = '{_API}'\nq = 'mutation{{variableUpsert(input:{{}})}}'\nPY"),
    ("ask", f"python <<PY\nurl = '{_API}'\nq = 'mutation{{tcpProxyDelete(id:1)}}'\nPY"),
    ("ask", f"cat <<'EOF' | python -\nurl = '{_API}'\nq = 'mutation{{tcpProxyDelete(id:1)}}'\nEOF"),
    ("ask", "python tools/ops/railway_pitr.py --list"),
    ("ask", "python -m tools.ops.railway_pitr --list"),
    ("ask", "python -u tools/ops/railway_configure_cron_service.py --help"),
    ("ask", "uv run python tools/ops/railway_pitr.py --list"),
    ("allow", f"curl -s {_API} -d '{{\"query\":\"query{{me{{id}}}}\"}}'"),
    ("allow", "python tools/perf/prod_route_latency_compare.py --help"),
    ("allow", "python tools/ops/check_deploy_drift.py"),
    ("allow", "grep -rn \"mutation{tcpProxyDelete\" docs/ backboard.railway.com"),
    ("allow", "cat <<'MD' > notes.md\nbackboard.railway.com mutation{tcpProxyDelete(id:1)}\nMD"),
]


def _load_policy():
    """guard_policy 모듈을 저장소 경로에서 직접 로드한다."""
    module_path = REPO_ROOT / "tools" / "harness" / "guard_policy.py"
    spec = importlib.util.spec_from_file_location("guard_policy_railway_api", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("expected", "command"), CASES)
def test_policy_decision(expected: str, command: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """정책 함수가 직접 판정한다(상대 경로 도구는 저장소 루트 기준)."""
    monkeypatch.chdir(REPO_ROOT)
    assert _load_policy().classify_command(command, project_root=str(REPO_ROOT))[0] == expected


@pytest.mark.parametrize(("expected", "command"), [c for c in CASES if c[0] == "ask"][:3])
def test_claude_hook_asks(expected: str, command: str) -> None:
    """실제 Claude 훅도 같은 판정을 낸다."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, ".claude/hooks/guard_shell.py"], input=json.dumps(payload),
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    decision = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
    assert decision == expected


_MUTATION_SCRIPT = f"URL = '{_API}'\nQ = 'mutation{{tcpProxyDelete(id:\"x\")}}'\n"
_QUERY_SCRIPT = f"URL = '{_API}'\nQ = 'query{{me{{id}}}}'  # mutation 은 보내지 않는다\n"


@pytest.mark.parametrize(
    ("body", "argv", "expected"),
    [
        (_MUTATION_SCRIPT, "python {p}", "ask"),
        (_MUTATION_SCRIPT, "py -3 {p}", "ask"),
        (_MUTATION_SCRIPT, "python -X utf8 {p}", "ask"),
        (_QUERY_SCRIPT, "python {p}", "allow"),
    ],
)
def test_mutation_inside_script_file(tmp_path: Path, body: str, argv: str, expected: str) -> None:
    """스크립트 파일 안의 mutation 은 실행 전에 확인을 묻는다(조회만이면 통과)."""
    script = tmp_path / "s.py"
    script.write_text(body, encoding="utf-8")
    assert _load_policy().classify_command(argv.format(p=script.as_posix()))[0] == expected
