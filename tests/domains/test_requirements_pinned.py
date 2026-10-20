"""의존성은 정확한 버전으로 고정한다 (SPEC 2026-10-20-dependency-pins).

범위 핀(``>=``)은 빌드할 때마다 그날의 최신판을 받아 와서, 같은 커밋이 언제 빌드됐느냐에
따라 다른 코드가 돌았다. 버전 올리기는 Dependabot PR(deploy 대상)로만 한다.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_REQ = re.compile(r"^(?P<name>[A-Za-z0-9_.\-]+)(\[[^\]]+\])?==(?P<ver>[0-9][^\s;#]*)\s*(#.*)?$")


def _requirement_lines():
    for raw in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line


def test_every_requirement_is_exactly_pinned():
    loose = [ln for ln in _requirement_lines() if not _REQ.match(ln)]
    assert not loose, "정확한 버전(==)이 아닌 의존성:\n" + "\n".join(loose)


def test_pillow_is_patched():
    versions = {m.group("name").lower(): m.group("ver") for m in map(_REQ.match, _requirement_lines()) if m}
    major, minor = (int(x) for x in versions["pillow"].split(".")[:2])
    assert (major, minor) >= (12, 3), versions["pillow"]


def test_dependabot_targets_deploy_branch():
    text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    ecosystems = re.findall(r'package-ecosystem:\s*"([^"]+)"', text)
    assert {"pip", "github-actions"} <= set(ecosystems)
    assert text.count('target-branch: "deploy"') == len(ecosystems)
