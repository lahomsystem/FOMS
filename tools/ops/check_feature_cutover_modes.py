"""feature cutover mode fail-closed checker (§8.2 line 1544).

env mode(family별 env var) · image compatibility generation(build_compatibility.json) ·
DB marker/fence 를 mode manifest 와 비교해 다음을 **fail-closed**(nonzero) 한다:

* post-cutover(marker 존재)인데 env mode 가 incompatible(legacy/WARN 등 allowed_post 밖),
* post-cutover 인데 image generation < marker.minimum_compatibility_generation,
* env mode 가 해당 family 의 어떤 allowed mode 도 아님(unknown),
* DB/manifest 조회 불가(unknown status).

read-only 이며 approval token 을 요구하지 않는다(고위험 CLI 규약 대상 아님).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.security.cutover.mode_manifest import (  # noqa: E402
    MANIFEST_PATH, assert_row_shape, load_manifest,
)


def evaluate_family_modes(
    manifest: dict, env_modes: dict, db_states: dict, image_generation: int,
) -> list[dict]:
    """순수 판정: manifest + 관측 상태로 fail-closed 위반 목록을 만든다.

    :param env_modes: family → env var 값(str) 또는 None(미설정).
    :param db_states: family → ``{"has_marker": bool,
        "minimum_compatibility_generation": int|None, "fence_mode": str|None}``.
    :param image_generation: in-image compatibility generation.
    :returns: 위반 목록(빈 목록이면 green). 각 항목 ``{family, reason, detail}``.
    """
    failures: list[dict] = []
    families = manifest.get("families", {})
    for family, row in families.items():
        env_mode = env_modes.get(family)
        state = db_states.get(family, {})
        has_marker = bool(state.get("has_marker"))
        allowed_pre = row["allowed_pre_cutover_modes"]
        allowed_post = row["allowed_post_cutover_modes"]

        # unknown mode(어떤 allowed 에도 없음)는 pre/post 무관 red.
        if env_mode is not None and env_mode not in set(allowed_pre) | set(allowed_post):
            failures.append({"family": family, "reason": "unknown_mode", "detail": env_mode})
            continue

        if has_marker:
            if env_mode is None:
                failures.append({"family": family, "reason": "post_cutover_mode_unset",
                                 "detail": "post-cutover requires an explicit post mode"})
            elif env_mode not in allowed_post:
                failures.append({"family": family, "reason": "post_cutover_forbidden_mode",
                                 "detail": env_mode})
            min_gen = state.get("minimum_compatibility_generation")
            if min_gen is not None and image_generation < min_gen:
                failures.append({"family": family, "reason": "generation_shortfall",
                                 "detail": f"image {image_generation} < required {min_gen}"})
        else:
            # pre-cutover: env mode 가 있으면 allowed_pre 안이어야 한다(unset 은 legacy 기본 허용).
            if env_mode is not None and env_mode not in allowed_pre:
                failures.append({"family": family, "reason": "pre_cutover_invalid_mode",
                                 "detail": env_mode})
    return failures


def _read_db_states(database_url: "str | None") -> dict:
    """DB 에서 family별 fence mode + marker(min compat generation)를 읽는다.

    :raises RuntimeError: DB 조회 불가(checker fail-closed).
    """
    from sqlalchemy import create_engine, text
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        # db.py 의 resolved engine 을 재사용(로컬/Railway env 규칙).
        from db import engine
    else:
        engine = create_engine(url)
    states: dict[str, dict] = {}
    with engine.connect() as conn:
        for family, mode in conn.execute(text("SELECT family, mode FROM feature_cutover_fences")):
            states.setdefault(family, {})["fence_mode"] = mode
            states[family].setdefault("has_marker", False)
        for family, min_gen in conn.execute(
            text("SELECT family, minimum_compatibility_generation FROM feature_cutover_markers")
        ):
            states.setdefault(family, {})
            states[family]["has_marker"] = True
            states[family]["minimum_compatibility_generation"] = min_gen
    return states


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed feature cutover mode checker.")
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--database-url", default=None, help="DSN(기본 DATABASE_URL/db.py)")
    parser.add_argument("--image-generation", type=int, default=None,
                        help="override in-image generation(기본 build_compatibility.json)")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        assert_row_shape(manifest)
    except Exception as exc:  # noqa: BLE001 - checker fail-closed on any manifest fault
        print(json.dumps({"ok": False, "error": f"manifest unavailable: {exc}"}, ensure_ascii=False))
        return 3

    if args.image_generation is not None:
        image_generation = args.image_generation
    else:
        from tools.harness.verify_build_compatibility import load_build_compatibility
        image_generation = load_build_compatibility()["generation"]

    env_modes = {
        family: os.environ.get(row["env_var"])
        for family, row in manifest["families"].items()
    }

    try:
        db_states = _read_db_states(args.database_url)
    except Exception as exc:  # noqa: BLE001 - DB 불가 = unknown status = nonzero(fail-closed)
        print(json.dumps({"ok": False, "error": f"db unavailable: {exc}"}, ensure_ascii=False))
        return 3

    failures = evaluate_family_modes(manifest, env_modes, db_states, image_generation)
    print(json.dumps({"ok": not failures, "image_generation": image_generation,
                      "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
