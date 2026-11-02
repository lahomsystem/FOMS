"""CI 조각 나누기용 테스트 파일별 시간 기록(tests/ci_shard_durations.json)을 새로 만든다.

CI-SHARD-01 은 이 기록으로 큰 파일부터 가장 덜 찬 조각에 넣는다(tests/conftest.py
`ci_shard_plan`). 기록에 없는 새 파일은 중간값으로 친다 — 기록이 낡아도 빠지는 파일은 없고,
고르기만 조금 나빠진다. 새 테스트 파일이 많이 늘었을 때 다시 만든다.

사용(저장소 루트):
    python -m pytest -q --ignore=tests/visual --ignore=tests/harness -p no:playwright \\
        -n 4 --dist loadfile --durations=0 --durations-min=0 > durations.txt
    python tools/harness/refresh_ci_shard_durations.py durations.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "tests" / "ci_shard_durations.json"
#: `--durations` 한 줄: "0.53s call     tests/domains/test_x.py::test_y[...]"
_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s+(?:setup|call|teardown)\s+(tests/[^:\s]+\.py)::")


def parse(text: str) -> dict[str, float]:
    """`--durations=0` 출력에서 파일별 초 합계를 뽑는다(경로 구분자는 `/`)."""
    totals: dict[str, float] = defaultdict(float)
    for line in text.splitlines():
        match = _LINE.match(line.replace("\\", "/"))
        if match:
            totals[match.group(2)] += float(match.group(1))
    return {path: round(sec, 2) for path, sec in sorted(totals.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("durations_file", type=Path, help="pytest --durations=0 출력 파일")
    args = parser.parse_args(argv)
    seconds = parse(args.durations_file.read_text(encoding="utf-8", errors="replace"))
    if len(seconds) < 100:
        print(f"[중단] 파일 {len(seconds)}개만 읽혔다 — --durations=0 --durations-min=0 출력인지 확인", file=sys.stderr)
        return 1
    payload = {
        "generated": date.today().isoformat(),
        "how": "tools/harness/refresh_ci_shard_durations.py",
        "seconds": seconds,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[완료] {OUTPUT.relative_to(REPO_ROOT)}: 파일 {len(seconds)}개, 합계 {sum(seconds.values()):.0f}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
