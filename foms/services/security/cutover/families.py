"""feature cutover 15 family SSOT + per-family 스펙 (§8.2 line 1500-1518, §8.2.1 line 1524-1540).

이 모듈은 fence/marker 테이블, mode manifest, build-compatibility, CLI, transactional
helper 가 공유하는 **단일 진리원**이다. family enum·fence mode·effect policy 와 SSOT
§8.2.1 표(policy/stability/effect_source/check_id)를 여기 한 곳에서 선언해 드리프트를
막는다. 값을 바꾸려면 SSOT 를 먼저 고치고 여기와 mode manifest JSON 을 함께 갱신한다.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# family / mode / policy enum (§8.2 line 1516)
# --------------------------------------------------------------------------- #
# DESIGNER_AUTH 는 Brain 삭제로 제외된 14→15 최종 목록.
FEATURE_CUTOVER_FAMILIES: tuple[str, ...] = (
    "ASSIGNMENT",
    "ORDER_MUTATION",
    "STATE_COMMAND",
    "QUEST",
    "PRODUCTION_RUN",
    "AS_CYCLE",
    "DRAWING_REVISION",
    "UPLOAD",
    "CONSTRUCTION",
    "CHAT_SCOPE",
    "NOTIFICATION_DELIVERY",
    "TASK",
    "PASSWORD_POLICY",
    "OFFLINE_SW",
    "WDC_LINK",
)

FENCE_MODES: tuple[str, ...] = ("OPEN", "DRAINING", "CUTOVER")
EFFECT_POLICIES: tuple[str, ...] = ("DRAIN", "COMPATIBLE")

# post-cutover 에서 금지되는 mode 토큰(check_feature_cutover_modes fail-closed 대상).
# §8.2 line 1544: "post-cutover legacy/WARN … fail-closed".
_FORBIDDEN_POST_CUTOVER_MODES: frozenset[str] = frozenset({"LEGACY", "WARN"})


def _post_modes(pre_modes: tuple[str, ...]) -> tuple[str, ...]:
    """pre-cutover 허용 mode 에서 post-cutover 금지 토큰(LEGACY/WARN)을 제거."""
    return tuple(m for m in pre_modes if m not in _FORBIDDEN_POST_CUTOVER_MODES)


def _incompatible_modes(pre_modes: tuple[str, ...], post_modes: tuple[str, ...]) -> tuple[str, ...]:
    """cutover 후 incompatible 해지는 mode(= pre − post), 순서 보존."""
    postset = set(post_modes)
    return tuple(m for m in pre_modes if m not in postset)


# --------------------------------------------------------------------------- #
# per-family raw 스펙 (SSOT §8.2 표 + §8.2.1 표)
#   (env_var, pre_modes, policy, stability_seconds, effect_source, check_id,
#    readiness_class)
# post_modes / incompatible_modes 는 파생한다.
# minimum_compatibility_generation 은 현행 seed generation(1).
# --------------------------------------------------------------------------- #
_DOMAIN_SIDEFX = ("DOMAIN_SIDEFX_V1", "CUTOVER_SIDEFX_COMPAT", "DEGRADED_OK")
_NONE_QUIET = ("NONE", "CUTOVER_NONE_QUIET", "NONE")

MINIMUM_COMPATIBILITY_GENERATION = 1

_RAW_SPECS: dict[str, dict] = {
    "ASSIGNMENT": {
        "env_var": "FOMS_ASSIGNMENT_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "ORDER_MUTATION": {
        "env_var": "FOMS_ORDER_MUTATION_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "STATE_COMMAND": {
        "env_var": "FOMS_STATE_COMMAND_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "QUEST": {
        "env_var": "FOMS_QUEST_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "PRODUCTION_RUN": {
        "env_var": "FOMS_PRODUCTION_RUN_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "AS_CYCLE": {
        "env_var": "FOMS_AS_CYCLE_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "DRAWING_REVISION": {
        "env_var": "FOMS_DRAWING_REVISION_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "UPLOAD": {
        "env_var": "FOMS_UPLOAD_MODE",
        "pre_modes": ("LEGACY", "TICKET", "DISABLED"),
        "policy": "DRAIN", "stability_seconds": 120,
        "effect_source": "STORAGE_DELETE_V1", "check_id": "CUTOVER_STORAGE_DRAIN",
        "readiness_class": "REQUIRE_EXPIRY_SCAN",
    },
    "CONSTRUCTION": {
        "env_var": "FOMS_CONSTRUCTION_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "CHAT_SCOPE": {
        "env_var": "FOMS_CHAT_SCOPE_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _NONE_QUIET[0], "check_id": _NONE_QUIET[1],
        "readiness_class": _NONE_QUIET[2],
    },
    "NOTIFICATION_DELIVERY": {
        "env_var": "FOMS_NOTIFICATION_DELIVERY_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "DRAIN", "stability_seconds": 120,
        "effect_source": "NOTIFICATION_PROVIDER_V1", "check_id": "CUTOVER_NOTIFICATION_DRAIN",
        "readiness_class": "REQUIRE_DELIVERY",
    },
    "TASK": {
        "env_var": "FOMS_TASK_MODE",
        "pre_modes": ("LEGACY", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _DOMAIN_SIDEFX[0], "check_id": _DOMAIN_SIDEFX[1],
        "readiness_class": _DOMAIN_SIDEFX[2],
    },
    "PASSWORD_POLICY": {
        "env_var": "FOMS_PASSWORD_POLICY_MODE",
        "pre_modes": ("WARN", "ENFORCED", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _NONE_QUIET[0], "check_id": _NONE_QUIET[1],
        "readiness_class": _NONE_QUIET[2],
    },
    "OFFLINE_SW": {
        "env_var": "FOMS_OFFLINE_SW_MODE",
        "pre_modes": ("READ_ONLY", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _NONE_QUIET[0], "check_id": _NONE_QUIET[1],
        "readiness_class": _NONE_QUIET[2],
    },
    "WDC_LINK": {
        "env_var": "FOMS_WDC_LINK_MODE",
        "pre_modes": ("LEGACY", "CANONICAL", "DISABLED"),
        "policy": "COMPATIBLE", "stability_seconds": 30,
        "effect_source": _NONE_QUIET[0], "check_id": _NONE_QUIET[1],
        "readiness_class": _NONE_QUIET[2],
    },
}


def _build_family_specs() -> dict[str, dict]:
    """_RAW_SPECS 를 완전한 per-family 스펙(파생 필드 포함)으로 확장.

    :returns: family → {env_var, allowed_pre_cutover_modes, allowed_post_cutover_modes,
        minimum_compatibility_generation, pre_cutover_effect_policy, stability_seconds,
        effect_source, provider_reconciliation_check_id, runtime_readiness_class,
        incompatible_modes} (mode manifest row 와 동일 필드).
    :raises AssertionError: family 목록이 enum 과 불일치.
    """
    assert set(_RAW_SPECS) == set(FEATURE_CUTOVER_FAMILIES), "raw spec ↔ family enum mismatch"
    out: dict[str, dict] = {}
    for family in FEATURE_CUTOVER_FAMILIES:  # enum 순서 보존
        raw = _RAW_SPECS[family]
        pre = tuple(raw["pre_modes"])
        post = _post_modes(pre)
        out[family] = {
            "env_var": raw["env_var"],
            "allowed_pre_cutover_modes": list(pre),
            "allowed_post_cutover_modes": list(post),
            "minimum_compatibility_generation": MINIMUM_COMPATIBILITY_GENERATION,
            "pre_cutover_effect_policy": raw["policy"],
            "stability_seconds": raw["stability_seconds"],
            "effect_source": raw["effect_source"],
            "provider_reconciliation_check_id": raw["check_id"],
            # prerequisite_packet_ids / affected_control_ids 는 각 family cutover packet 이
            # 자기 URL-map/의존성 inventory 로 채운다. 메커니즘 seed 는 빈 목록이다
            # (fabrication 금지 — SSOT §8.2.1 에 family별 packet/control ID 표가 없음).
            "prerequisite_packet_ids": [],
            "affected_control_ids": [],
            "runtime_readiness_class": raw["readiness_class"],
            "incompatible_modes": list(_incompatible_modes(pre, post)),
        }
    return out


FAMILY_SPECS: dict[str, dict] = _build_family_specs()

# mode manifest row 의 exact 필드 집합(§8.2 line 1544).
MANIFEST_ROW_FIELDS: frozenset[str] = frozenset({
    "family",
    "env_var",
    "allowed_pre_cutover_modes",
    "allowed_post_cutover_modes",
    "minimum_compatibility_generation",
    "pre_cutover_effect_policy",
    "stability_seconds",
    "effect_source",
    "provider_reconciliation_check_id",
    "prerequisite_packet_ids",
    "affected_control_ids",
    "runtime_readiness_class",
    "incompatible_modes",
})


def is_drain_family(family: str) -> bool:
    """family 가 DRAIN policy(begin_drain 필수)인지."""
    return _RAW_SPECS[family]["policy"] == "DRAIN"
