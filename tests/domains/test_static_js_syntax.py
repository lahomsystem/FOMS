"""FE-SYNTAX parser CI — every static/js file must parse as JavaScript.

Root-cause guard for P0-6: a Python ``#`` comment leaked into
``static/js/foms/erp-attachment-preview-open.js`` and broke the whole module
(``SyntaxError: Invalid or unexpected token``). Any non-parsing JS shipped to
the browser is a hard failure, so this test parses the entire ``static/js``
tree and fails on every file that does not parse.

CI-NODE-01: 예전에는 파일마다 ``node --check`` 프로세스를 하나씩 띄웠다. 파일이
160 개라 프로세스 기동 비용만으로 이 테스트 하나가 12.5 초를 먹었다(전체 스위트
단일 최장). 지금은 node 를 **한 번만** 띄우고 그 안에서 전부 파싱한다.

파서는 그대로다. 저장소에 package.json 이 없고 static/js 에 ESM 구문(import/
export)을 쓰는 파일이 0 개이므로, node 는 이 파일들을 전부 클래식 스크립트로
읽는다 — ``node --check`` 가 하는 일과 ``new vm.Script(...)`` 가 하는 일이 같은
V8 파서를 같은 모드로 태우는 것이다. 검출력은 변하지 않는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC_JS = ROOT / "static" / "js"

# node 를 한 번만 띄우는 드라이버. 파일 목록은 stdin 으로 받는다(경로 160 개를
# argv 로 넘기면 플랫폼 인자 길이 한계에 걸릴 수 있다).
_NODE_DRIVER = """
const vm = require('vm');
const fs = require('fs');
let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { buf += chunk; });
process.stdin.on('end', () => {
  const files = buf.split('\\n').map((s) => s.trim()).filter(Boolean);
  const broken = [];
  for (const file of files) {
    try {
      new vm.Script(fs.readFileSync(file, 'utf8'), { filename: file });
    } catch (err) {
      broken.push({ file: file, error: String((err && err.message) || err) });
    }
  }
  process.stdout.write(JSON.stringify({ checked: files.length, broken: broken }));
});
"""


def _all_js_files() -> list[Path]:
    return sorted(STATIC_JS.rglob("*.js"))


def _parse_all(paths: list[Path]) -> dict:
    """node 를 1회 기동해 주어진 파일들을 전부 파싱하고 결과를 돌려준다.

    Args:
        paths: 파싱할 .js 파일 경로 목록.

    Returns:
        ``{"checked": int, "broken": [{"file": str, "error": str}, ...]}``.
    """
    node = shutil.which("node")
    assert node, "node must be on PATH for the FE-SYNTAX parser CI test"

    proc = subprocess.run(
        [node, "-e", _NODE_DRIVER],
        input="\n".join(str(p) for p in paths),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, (
        "FE-SYNTAX 배치 파서 드라이버가 비정상 종료했다 "
        f"(exit={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:500]}"
    )
    return json.loads(proc.stdout)


def test_static_js_tree_is_nonempty() -> None:
    """Guard against a glob that silently matches nothing."""
    assert _all_js_files(), f"no .js files found under {STATIC_JS}"


def test_every_static_js_parses() -> None:
    files = _all_js_files()
    result = _parse_all(files)

    # 드라이버가 조용히 일부만 보고 끝나면 이 테스트는 아무것도 검사하지 않은 채
    # 통과한다. 파일 수가 맞는지 먼저 못 박는다.
    assert result["checked"] == len(files), (
        f"FE-SYNTAX 배치 파서가 {len(files)} 개 중 {result['checked']} 개만 검사했다"
    )

    broken = [
        f"{Path(item['file']).relative_to(ROOT).as_posix()}: {item['error']}"
        for item in result["broken"]
    ]
    assert not broken, "static/js files failed to parse:\n" + "\n".join(broken)
