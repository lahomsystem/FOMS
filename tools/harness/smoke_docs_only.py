"""pre_push_smoke 빠른 길 판정 — 문서(docs/**/*.md)만 바뀐 푸시는 문서를 읽는 시험만 돌린다.

설계서: docs/specs/2026-11-07-test-run-speed_SPEC.md §2.2.

exit 0 + stdout 에 돌릴 시험 파일(한 줄에 하나) = 빠른 길.
exit 1 = 전체 스위트(문서 밖 파일이 섞였거나, 바뀐 게 없거나, git 이 실패).

시험 파일 목록은 손으로 적지 않는다 — 매번 tests/ 소스에서 docs 를 읽는 파일을 찾는다
(2026-09-22 교훈: 손으로 고른 목록은 반드시 낡는다). 푸시 뒤 CI 는 여전히 전체를 돈다.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = re.compile(r"^docs/.+\.md$")
READS_DOCS = re.compile(r"""docs/|["']docs["']""")
READS_MD = re.compile(r"\.md\b")


def is_docs_only(paths: list[str]) -> bool:
    """바뀐 파일이 하나 이상이고 모두 docs/ 아래 .md 면 True."""
    cleaned = [p.strip().replace("\\", "/") for p in paths if p.strip()]
    return bool(cleaned) and all(DOC_PATH.match(p) for p in cleaned)


def doc_reading_tests(root: Path = ROOT) -> list[str]:
    """tests/ 아래 test_*.py 중 docs 의 .md 를 읽을 수 있는 파일(저장소 기준 상대 경로, 정렬).

    docs 경로와 .md 를 둘 다 적은 파일을 고른다 — 바뀐 문서 이름만 찾으면 docs 를 통째로 훑는
    시험(링크 · 정본 경로 · 예산 검사)을 놓친다. 넉넉하게 잡는 쪽이 안전하다(2026-11-07 약 200개).
    """
    found = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if READS_DOCS.search(text) and READS_MD.search(text):
            found.append(path.relative_to(root).as_posix())
    return found


def changed_paths(since_ref: str, root: Path = ROOT) -> list[str] | None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{since_ref}...HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since-ref", default="origin/deploy")
    args = parser.parse_args(argv)
    paths = changed_paths(args.since_ref)
    if paths is None or not is_docs_only(paths):
        return 1
    tests = doc_reading_tests()
    if not tests:
        return 1
    sys.stdout.write("\n".join(tests) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
