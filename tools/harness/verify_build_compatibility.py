"""in-image build-compatibility 정본 검증 (§8.2 line 1516).

``foms/build_compatibility.json`` 의 ``{schema_version, generation,
supersedes_generation, state_aware_families}`` 가 계약을 지키는지 검증한다:

* generation 은 양의 정수, supersedes_generation 은 음이 아닌 정수, generation ==
  supersedes_generation + 1 (chain exact).
* state_aware_families 는 15 family enum 의 부분집합(중복/미등록 family red).
* ``--merge-base <sha>`` 가 주어지면 git 으로 merge-base 시점 파일을 읽어 현재
  supersedes_generation == merge-base.generation (chain 연속)이고 generation 이
  엄격히 증가하는지 확인한다. ``--incompatible-change`` 면 정확히 +1 bump 를 요구한다.

Git SHA 에는 순서가 없다 — provenance/ancestry 용일 뿐 크기 비교 0 이다. 정본은 in-image
파일이다. 이 도구는 dry-run/read-only 이며 approval token 을 요구하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.cutover.families import FEATURE_CUTOVER_FAMILIES  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = _REPO_ROOT / "foms" / "build_compatibility.json"
IN_IMAGE_REL = "foms/build_compatibility.json"

_REQUIRED_FIELDS = frozenset({
    "schema_version", "generation", "supersedes_generation", "state_aware_families",
})
_FAMILY_SET = frozenset(FEATURE_CUTOVER_FAMILIES)


class BuildCompatibilityError(RuntimeError):
    """build_compatibility.json 이 계약을 위반할 때."""


def load_build_compatibility(path: "str | Path | None" = None) -> dict:
    """build_compatibility.json 로드.

    :raises OSError: 파일 부재.
    :raises ValueError: JSON 파싱 실패.
    """
    p = Path(path) if path is not None else DEFAULT_PATH
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def validate_structure(obj: dict) -> None:
    """단일 파일의 구조/generation 규칙/family enum 을 검증.

    :raises BuildCompatibilityError: 필드 결손, generation 규칙 위반, family enum 위반.
    """
    if not isinstance(obj, dict):
        raise BuildCompatibilityError("build_compatibility must be a JSON object.")
    keys = set(obj.keys())
    if keys != _REQUIRED_FIELDS:
        raise BuildCompatibilityError(
            f"fields mismatch; expected exactly {sorted(_REQUIRED_FIELDS)}, got {sorted(keys)}."
        )
    gen = obj["generation"]
    sup = obj["supersedes_generation"]
    if not (isinstance(gen, int) and not isinstance(gen, bool) and gen > 0):
        raise BuildCompatibilityError(f"generation must be a positive integer, got {gen!r}.")
    if not (isinstance(sup, int) and not isinstance(sup, bool) and sup >= 0):
        raise BuildCompatibilityError(
            f"supersedes_generation must be a non-negative integer, got {sup!r}."
        )
    if gen != sup + 1:
        raise BuildCompatibilityError(
            f"generation ({gen}) must equal supersedes_generation ({sup}) + 1 (chain exact)."
        )
    fams = obj["state_aware_families"]
    if not isinstance(fams, list):
        raise BuildCompatibilityError("state_aware_families must be a list.")
    if len(set(fams)) != len(fams):
        raise BuildCompatibilityError("state_aware_families must not contain duplicates.")
    unknown = sorted(set(fams) - _FAMILY_SET)
    if unknown:
        raise BuildCompatibilityError(f"state_aware_families has unknown families: {unknown}.")


def verify_against_merge_base(current: dict, merge_base: dict, *, incompatible_change: bool) -> None:
    """현재 파일이 merge-base 파일 대비 generation chain 을 지키는지 검증.

    :param incompatible_change: True 면 정확히 +1 generation bump 를 요구한다.
    :raises BuildCompatibilityError: chain 불연속 또는 bump 규칙 위반.
    """
    validate_structure(current)
    validate_structure(merge_base)
    base_gen = merge_base["generation"]
    cur_gen = current["generation"]
    cur_sup = current["supersedes_generation"]
    if cur_sup != base_gen:
        raise BuildCompatibilityError(
            f"supersedes_generation ({cur_sup}) must equal merge-base generation ({base_gen})."
        )
    if cur_gen <= base_gen:
        raise BuildCompatibilityError(
            f"generation must strictly increase over merge-base ({base_gen}), got {cur_gen}."
        )
    if incompatible_change and cur_gen != base_gen + 1:
        raise BuildCompatibilityError(
            f"incompatible change requires exactly +1 generation bump "
            f"(merge-base {base_gen} → {base_gen + 1}), got {cur_gen}."
        )


def _read_file_at_git_ref(ref: str, rel_path: str) -> dict:
    """git 으로 ``<ref>:<rel_path>`` 내용을 읽어 JSON 파싱."""
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "show", f"{ref}:{rel_path}"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BuildCompatibilityError(f"git show failed for {ref}:{rel_path}: {exc}") from exc
    if out.returncode != 0:
        raise BuildCompatibilityError(
            f"git show {ref}:{rel_path} failed: {out.stderr.strip()}"
        )
    return json.loads(out.stdout)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Verify foms/build_compatibility.json contract.")
    parser.add_argument("--path", default=str(DEFAULT_PATH), help="검증할 파일 경로")
    parser.add_argument("--commit-sha", default=None, help="현재 커밋 SHA(provenance 표기용)")
    parser.add_argument("--merge-base", default=None,
                        help="chain 비교 대상 merge-base SHA(git show 로 파일 조회)")
    parser.add_argument("--incompatible-change", action="store_true",
                        help="incompatible schema change → 정확히 +1 generation bump 요구")
    args = parser.parse_args(argv)

    try:
        current = load_build_compatibility(args.path)
        validate_structure(current)
        if args.merge_base:
            base = _read_file_at_git_ref(args.merge_base, IN_IMAGE_REL)
            verify_against_merge_base(current, base, incompatible_change=args.incompatible_change)
    except (BuildCompatibilityError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({
        "ok": True,
        "commit_sha": args.commit_sha,
        "generation": current["generation"],
        "supersedes_generation": current["supersedes_generation"],
        "state_aware_families": current["state_aware_families"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
