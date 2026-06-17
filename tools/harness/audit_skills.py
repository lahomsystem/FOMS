"""Audit skill directories across Cursor, Claude, Codex, and repo-local paths."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path


ROOTS: dict[str, Path] = {
    "claude": Path(os.environ["USERPROFILE"]) / ".claude/skills",
    "codex": Path(os.environ["USERPROFILE"]) / ".codex/skills",
    "cursor": Path(os.environ["USERPROFILE"]) / ".cursor/skills",
    "foms_agents": Path(__file__).resolve().parents[2] / ".agents/skills",
    "home_agents": Path(os.environ["USERPROFILE"]) / ".agents/skills",
}


def read_skill_name(skill_md: Path) -> str | None:
    """Extract the frontmatter name field from a SKILL.md file."""

    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip('"').strip("'")


def collect_skills(root: Path, host: str, prefix: str = "") -> list[tuple[str, str, str | None, str]]:
    """Recursively collect SKILL.md files under a host skills root."""

    entries: list[tuple[str, str, str | None, str]] = []
    if not root.exists():
        return entries

    for skill_md in sorted(root.rglob("SKILL.md")):
        rel = skill_md.parent.relative_to(root)
        dirname = rel.as_posix() if str(rel) != "." else skill_md.parent.name
        entries.append((host, dirname, read_skill_name(skill_md), str(skill_md)))

    return entries


def main() -> int:
    """Print duplicate and overlap reports."""

    all_entries: list[tuple[str, str, str | None, str]] = []
    for host, root in ROOTS.items():
        all_entries.extend(collect_skills(root, host))

    by_name: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for host, dirname, name, path in all_entries:
        key = name or f"[no-name:{dirname}]"
        by_name[key].append((host, dirname, path))

    print("=== DUPLICATE skill names (same `name:` field) ===")
    dup_count = 0
    for name, items in sorted(by_name.items()):
        if len(items) <= 1:
            continue
        dup_count += 1
        print(f"\n{name} ({len(items)} copies)")
        for host, dirname, path in items:
            print(f"  [{host}] {dirname}")
            print(f"    {path}")

    print(f"\nTotal duplicate name groups: {dup_count}")

    print("\n=== gstack overlap: prefixed vs unprefixed names ===")
    gstack_names = {n for n in by_name if n.startswith("gstack-") or n == "gstack"}
    base_names = {n.replace("gstack-", "", 1) for n in gstack_names if n.startswith("gstack-")}
    for base in sorted(base_names):
        prefixed = f"gstack-{base}"
        if base in by_name and prefixed in by_name:
            print(f"OVERLAP: /{base} and /{prefixed}")
            for host, dirname, path in by_name[base]:
                print(f"  /{base} -> [{host}] {dirname}")
            for host, dirname, path in by_name[prefixed]:
                print(f"  /{prefixed} -> [{host}] {dirname}")

    print("\n=== Per-host skill counts ===")
    for host, root in ROOTS.items():
        if not root.exists():
            print(f"{host}: missing")
            continue
        count = len(list(root.rglob("SKILL.md")))
        print(f"{host}: {count} SKILL.md files under {root}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
