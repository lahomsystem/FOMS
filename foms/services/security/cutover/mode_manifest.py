"""mode manifest 로드 + 15-row 양방향 비교 (§8.2 line 1544).

``docs/harness/foms_feature_cutover_modes.json`` 은 15 family 의 cutover mode 계약
exact SSOT 다. CUTOVER-MODE-01 이 전체를 소유한다(ops approval manifest 의 seed+append
와 달리 wholesale). 이 모듈은 :data:`~foms.services.security.cutover.families.FAMILY_SPECS`
(코드 SSOT)와 JSON 을 **양방향** 비교해 개수/enum/필드 불일치를 red 로 만든다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from foms.services.security.cutover.families import (
    EFFECT_POLICIES,
    FAMILY_SPECS,
    FEATURE_CUTOVER_FAMILIES,
    MANIFEST_ROW_FIELDS,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = _REPO_ROOT / "docs" / "harness" / "foms_feature_cutover_modes.json"

MANIFEST_SCHEMA_VERSION = 1


class ModeManifestError(RuntimeError):
    """mode manifest 가 코드 SSOT(FAMILY_SPECS)와 계약을 위반할 때."""


def build_canonical_manifest() -> dict[str, Any]:
    """FAMILY_SPECS 로부터 정본 manifest dict 를 생성(디스크 JSON 의 기대값).

    각 family row 는 자기 key 와 동일한 ``family`` 필드를 포함해 self-describing 하다.
    """
    families: dict[str, Any] = {}
    for family in FEATURE_CUTOVER_FAMILIES:
        row = {"family": family}
        row.update(FAMILY_SPECS[family])
        families[family] = row
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "description": (
            "CUTOVER-MODE-01 feature cutover mode manifest (§8.2 line 1544). 15 family 의 "
            "env_var·allowed pre/post modes·minimum_compatibility_generation·"
            "pre_cutover_effect_policy·stability_seconds·effect_source·"
            "provider_reconciliation_check_id·runtime_readiness_class·incompatible_modes 를 "
            "exact literal 로 선언한다. foms/services/cutover/families.py(FAMILY_SPECS)와 "
            "양방향 비교하며 개수/enum/필드 불일치는 test 가 red 로 거부한다. "
            "prerequisite_packet_ids·affected_control_ids 는 각 family cutover packet 이 "
            "자기 inventory 로 채우며 메커니즘 seed 는 빈 목록이다."
        ),
        "families": families,
    }


def load_manifest(path: "str | Path | None" = None) -> dict[str, Any]:
    """mode manifest JSON 을 로드.

    :raises OSError: 파일 부재.
    :raises ValueError: JSON 파싱 실패.
    """
    p = Path(path) if path is not None else MANIFEST_PATH
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def assert_row_shape(manifest: dict[str, Any]) -> None:
    """manifest 각 row 가 exact 필드 집합·유효 enum·파생 규칙을 만족하는지 검증.

    :raises ModeManifestError: schema_version/필드/enum/policy/stability/family-key 위반.
    """
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ModeManifestError(
            f"schema_version must be {MANIFEST_SCHEMA_VERSION}, got {manifest.get('schema_version')!r}."
        )
    fams = manifest.get("families")
    if not isinstance(fams, dict):
        raise ModeManifestError("manifest.families must be an object.")

    for key, row in fams.items():
        if not isinstance(row, dict):
            raise ModeManifestError(f"family {key} row must be an object.")
        if set(row.keys()) != MANIFEST_ROW_FIELDS:
            raise ModeManifestError(
                f"family {key} fields mismatch; expected {sorted(MANIFEST_ROW_FIELDS)}, "
                f"got {sorted(row.keys())}."
            )
        if row["family"] != key:
            raise ModeManifestError(f"family row key {key!r} != row.family {row['family']!r}.")
        if row["pre_cutover_effect_policy"] not in EFFECT_POLICIES:
            raise ModeManifestError(
                f"family {key} policy invalid: {row['pre_cutover_effect_policy']!r}."
            )
        if not (isinstance(row["stability_seconds"], int) and row["stability_seconds"] > 0):
            raise ModeManifestError(f"family {key} stability_seconds must be a positive int.")
        # incompatible_modes == pre − post (파생 규칙 검증).
        pre = row["allowed_pre_cutover_modes"]
        post = row["allowed_post_cutover_modes"]
        expected_incompat = [m for m in pre if m not in set(post)]
        if row["incompatible_modes"] != expected_incompat:
            raise ModeManifestError(
                f"family {key} incompatible_modes must equal pre−post "
                f"({expected_incompat}), got {row['incompatible_modes']}."
            )


def manifest_vs_inventory_bidirectional(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """JSON manifest 와 코드 inventory(FAMILY_SPECS)를 양방향 비교.

    :returns: ``{"missing_families": [...], "extra_families": [...],
        "field_mismatch": ["<family>.<field>", ...]}`` — 모두 비어야 green.
    """
    canonical = build_canonical_manifest()["families"]
    fams = manifest.get("families", {})

    manifest_ids = set(fams.keys())
    canonical_ids = set(canonical.keys())
    missing = sorted(canonical_ids - manifest_ids)   # 코드엔 있는데 JSON 에 없음
    extra = sorted(manifest_ids - canonical_ids)      # JSON 에만 있는 미승인 family

    field_mismatch: list[str] = []
    for family in sorted(canonical_ids & manifest_ids):
        exp = canonical[family]
        got = fams[family]
        for field in sorted(MANIFEST_ROW_FIELDS):
            if got.get(field) != exp.get(field):
                field_mismatch.append(f"{family}.{field}")

    return {
        "missing_families": missing,
        "extra_families": extra,
        "field_mismatch": field_mismatch,
    }
