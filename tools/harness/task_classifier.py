"""Shared deterministic task classification for FOMS harness entrypoints."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from paths import (
    HARNESS_BUNDLE_PREFIX,
    HARNESS_CLAUDE_BUNDLE_PATH,
    HARNESS_CLAUDE_HARNESS_BUNDLE_PATH,
    HARNESS_CODEX_BUNDLE_PATH,
    HARNESS_CODEX_HARNESS_BUNDLE_PATH,
    HARNESS_CURSOR_BUNDLE_PATH,
    HARNESS_CURSOR_HARNESS_BUNDLE_PATH,
    HARNESS_DECISIONS_PATH,
)
from spec_utils import find_latest_spec


PROMPT_KEYS = ("prompt", "userPrompt", "user_prompt", "message", "text")
PATH_KEYS = ("path", "file_path", "filePath", "relative_path", "relativePath")

URL_RE = re.compile(r"https?://[^\s`\"']+")
PATH_RE = re.compile(
    r"(?:[A-Za-z]:)?(?:[^\s`\"']*[\\/])+[^\s`\"']+|[A-Za-z0-9_.-]+\.(?:py|md|ps1|ya?ml|json|toml|js|ts|tsx|html)",
    re.IGNORECASE,
)

LEVEL_RANKS = {"low": 1, "medium": 2, "high": 3, "top": 4}
KOREAN_TOKENS = {
    "low": "\ud558",
    "medium": "\uc911",
    "high": "\uc0c1",
    "top": "\ucd5c\uc0c1",
    "level": "\ub808\ubca8",
    "progress": "\uc9c4\ud589",
}

REVIEW_KEYWORDS = (
    "review",
    "audit",
    "inspect",
    "check",
    "\uac80\ud1a0",
    "\ub9ac\ubdf0",
    "\uac10\uc0ac",
    "\uc810\uac80",
)
IMPLEMENT_KEYWORDS = (
    "implement",
    "fix",
    "update",
    "edit",
    "change",
    "add",
    "create",
    "build",
    "refactor",
    "\uad6c\ud604",
    "\uc218\uc815",
    "\ubcc0\uacbd",
    "\ucd94\uac00",
    "\uace0\uccd0",
    "\ub9cc\ub4e4",
    "\uc791\uc131",
)
QA_KOREAN_KEYWORDS = ("\uac80\uc99d", "\ud14c\uc2a4\ud2b8", "\uc7ac\ud604")
QA_REGEX_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bqa\b",
        r"\bsmoke\b",
        r"\be2e\b",
        r"\bbrowser\b",
        r"\bscreenshot\b",
        r"\btest(?:ing)?\b",
    )
)

HARNESS_EXACT_MATCHES = {
    "agents.md",
    "claude.md",
    "docs/context/analysis/task_plan.md",
    "docs/context/analysis/findings.md",
    "docs/context/analysis/progress.md",
    "docs/archive_index.md",
    ".agents/workflows/verify-result.md",
    HARNESS_DECISIONS_PATH.lower(),
    "docs/guides/harness_engineering_operator_guide.md",
    "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md",
}
HARNESS_PREFIXES = (
    "tools/harness/",
    ".cursor/hooks/",
    ".cursor/rules/",
    ".cursor/agents/",
    "docs/specs/",
    HARNESS_BUNDLE_PREFIX.lower(),
)
CORE_EXACT_MATCHES = {"app.py", "db.py", "models.py"}
CORE_PREFIXES = ("apps/api/", "foms/api/", "migrations/", "services/auth/", "auth/")
DEPLOY_EXACT_MATCHES = {"dockerfile", "procfile", "railway.toml", "railway.json"}
DEPLOY_PREFIXES = (".github/workflows/", "docker/", "deploy/")

AUTH_KEYWORDS = (
    "auth",
    "session",
    "token",
    "인증",
    "세션",
    "토큰",
    "로그인",
    "권한",
)
VERIFICATION_KEYWORDS = ("qa", "browser", "e2e", "screenshot", "smoke", "audit", "test")
WIDE_SCOPE_KEYWORDS = (
    "refactor",
    "architecture",
    "migration",
    "multi-file",
    "broad",
    "마이그레이션",
    "리팩토링",
    "리팩터",
    "아키텍처",
    "스키마",
)
TOP_RESOURCE_KEYWORDS = (
    "parallel",
    "research",
    "full verification",
    "benchmark",
    "canary",
    "release",
    "deep audit",
    "프로덕션",
    "운영 배포",
    "운영배포",
    "릴리스",
    "카나리",
    "벤치마크",
)
HARNESS_TEXT_KEYWORDS = ("harness", "하네스")

LEVEL_GUIDANCE = {
    "low": {
        "verification": "light review",
        "prompt_lines": (
            "Task level: low. Keep scope tight and avoid unnecessary broad context.",
            "Use lightweight verification appropriate for a small, non-core task.",
        ),
        "resource_hints": ("direct work", "light verification"),
    },
    "medium": {
        "verification": "related checks",
        "prompt_lines": (
            "Task level: medium. Stay on the daily bundle unless an explicit context override was requested.",
            "Do the relevant targeted checks, tests, or browser verification before claiming success.",
        ),
        "resource_hints": ("targeted tests", "browser or focused verification when relevant"),
    },
    "high": {
        "verification": "strong verification",
        "prompt_lines": (
            "Task level: high. Use harness-level rigor with stronger surrounding-code review.",
            "Include stronger verification and consult relevant project docs or decisions when needed.",
        ),
        "resource_hints": ("harness bundle", "decision log review", "strong verification"),
    },
    "top": {
        "verification": "full verification",
        "prompt_lines": (
            "Task level: top. Apply full harness rigor with broad verification and explicit residual-risk reporting.",
            "Consider research, browser QA, and parallel review or agent orchestration when the environment supports it.",
        ),
        "resource_hints": (
            "harness bundle",
            "research",
            "browser QA",
            "parallel review or agent orchestration",
            "full verification",
        ),
    },
}


@dataclass(frozen=True)
class PlanMetadata:
    """Lightweight metadata parsed from a Spec or plan file."""

    modified_file_count: int = 0
    step_count: int = 0


@dataclass(frozen=True)
class LevelOverride:
    """User-requested level override parsed from free text."""

    level: str | None = None
    source: str | None = None
    matched_text: str | None = None


@dataclass(frozen=True)
class TaskClassification:
    """Shared classification result consumed by hooks and wrappers."""

    route_kind: str
    profile: str
    level: str
    auto_level: str
    reason: str
    auto_reason: str
    context_mode: str
    bundle_path: str
    cursor_bundle_path: str
    claude_bundle_path: str
    codex_bundle_path: str
    verification: str
    prompt_lines: tuple[str, ...]
    resource_hints: tuple[str, ...]
    reasons: tuple[str, ...]
    path_scope_reasons: tuple[str, ...]
    needs_rpi: bool
    needs_user_direction: bool
    user_direction_reason: str | None
    primary_path: str | None
    plan_hint: str | None
    explicit_plan_path: str | None
    url: str | None
    scenario: str | None
    override_level: str | None
    override_source: str | None
    override_matched_text: str | None
    risky_override_ack_required: bool
    plan_metadata: PlanMetadata

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the classification."""
        return asdict(self)


def find_first_string(data: Any, target_keys: tuple[str, ...] = PROMPT_KEYS) -> str | None:
    """Return the first string value found for any of the target keys."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in target_keys and isinstance(value, str) and value.strip():
                return value.strip()
            found = find_first_string(value, target_keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_first_string(item, target_keys)
            if found:
                return found
    return None


def collect_path_values(data: Any) -> list[str]:
    """Return all path-like string values from a nested payload fragment."""
    values: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in PATH_KEYS and isinstance(value, str) and value.strip():
                values.append(value.strip())
            values.extend(collect_path_values(value))
    elif isinstance(data, list):
        for item in data:
            values.extend(collect_path_values(item))
    return values


def extract_prompt_text(payload: dict[str, Any]) -> str:
    """Return user prompt text from a Cursor hook payload."""
    return find_first_string(payload) or ""


def extract_urls(text: str) -> list[str]:
    """Return URL candidates from free text."""
    return [match.rstrip(".,)") for match in URL_RE.findall(text or "")]


def extract_prompt_paths(text: str) -> list[str]:
    """Return file path candidates from free text."""
    candidates: list[str] = []
    for raw in PATH_RE.findall(text or ""):
        candidate = raw.strip("`\"'()[]{}<>,.;")
        if candidate.lower().startswith(("http://", "https://")):
            continue
        if candidate:
            candidates.append(candidate)
    return candidates


def normalize_repo_relative_path(repo_root: Path, value: str) -> str:
    """Normalize a path-like value to repo-relative slash form when possible."""
    candidate = value.strip().replace("\\", "/")
    if not candidate:
        return candidate
    try:
        path_obj = Path(value)
    except Exception:
        return candidate.lstrip("./")
    try:
        if path_obj.is_absolute():
            return path_obj.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return candidate.lstrip("./")
    return candidate.lstrip("./")


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    """Deduplicate values without changing their first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def contains_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    """Return True when text contains any keyword, case-insensitively."""
    if not text:
        return False
    lowered = text.casefold()
    return any(keyword.casefold() in lowered for keyword in keywords)


def contains_explicit_qa_intent(text: str) -> bool:
    """Return True when text asks for QA-style execution."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in QA_REGEX_PATTERNS) or any(
        token in text for token in QA_KOREAN_KEYWORDS
    )


def is_harness_context_path(repo_relative_path: str) -> bool:
    """Return True when a path belongs to harness/operator context."""
    normalized = repo_relative_path.replace("\\", "/").casefold()
    if normalized in HARNESS_EXACT_MATCHES:
        return True
    return any(normalized.startswith(prefix) for prefix in HARNESS_PREFIXES)


def get_path_scope_reasons(paths: Iterable[str]) -> list[str]:
    """Return scope reasons from path risk buckets."""
    reasons: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/").casefold()
        if is_harness_context_path(normalized) and "harness core path" not in reasons:
            reasons.append("harness core path")
        if normalized in CORE_EXACT_MATCHES or any(normalized.startswith(prefix) for prefix in CORE_PREFIXES):
            if "db/api/auth core path" not in reasons:
                reasons.append("db/api/auth core path")
        if normalized in DEPLOY_EXACT_MATCHES or any(normalized.startswith(prefix) for prefix in DEPLOY_PREFIXES):
            if "deployment path" not in reasons:
                reasons.append("deployment path")
    return reasons


def infer_route_kind(prompt_text: str, normalized_paths: list[str], urls: list[str], profile: str = "auto") -> str:
    """Infer whether the prompt is review, implement, QA, or generic."""
    if profile in {"review", "implement", "qa"}:
        return profile
    lowered = prompt_text.casefold()
    if contains_any_keyword(lowered, REVIEW_KEYWORDS):
        return "review"
    if contains_any_keyword(lowered, IMPLEMENT_KEYWORDS):
        return "implement"
    if any(path.casefold().startswith(("docs/specs/", "docs/plans/")) for path in normalized_paths):
        return "implement"
    if contains_explicit_qa_intent(prompt_text) or urls:
        return "qa"
    return "generic"


def infer_scenario(prompt_text: str, fallback: str | None = None) -> str:
    """Infer a QA scenario label from text."""
    if fallback:
        return fallback
    lowered = prompt_text.casefold()
    if "erp" in lowered and "smoke" in lowered:
        return "erp-smoke"
    if "erp" in lowered and "e2e" in lowered:
        return "erp-e2e"
    if "browser" in lowered and "smoke" in lowered:
        return "browser-smoke"
    if "smoke" in lowered:
        return "smoke"
    if "e2e" in lowered:
        return "e2e"
    return "qa"


def choose_primary_path(paths: list[str]) -> str | None:
    """Choose the most relevant non-plan path."""
    for path in paths:
        if path.casefold().startswith(("docs/specs/", "docs/plans/")):
            continue
        return path
    return paths[0] if paths else None


def choose_explicit_plan_path(paths: list[str]) -> str | None:
    """Return the explicit plan/spec path from prompt or attachment paths."""
    for path in paths:
        if path.casefold().startswith(("docs/specs/", "docs/plans/")):
            return path
    return None


def choose_plan_hint(repo_root: Path, paths: list[str], explicit_plan: str | None) -> str:
    """Return the best plan/spec hint for implementation prompts."""
    if explicit_plan:
        return explicit_plan
    latest_spec = find_latest_spec(repo_root)
    if latest_spec is not None:
        try:
            return latest_spec.resolve().relative_to(repo_root.resolve()).as_posix()
        except Exception:
            return latest_spec.as_posix()
    return "<approved-plan-or-spec-path>"


def parse_plan_metadata_from_text(contents: str) -> PlanMetadata:
    """Extract modified file and Step counts from a Spec/plan body."""
    if not contents:
        return PlanMetadata()
    modified_file_count = 0
    step_count = 0
    in_file_table = False
    in_steps = False
    for line in contents.splitlines():
        if re.match(r"^###\s+2\.1", line):
            in_file_table = True
            in_steps = False
            continue
        if re.match(r"^##\s+3\.", line):
            in_file_table = False
            in_steps = True
            continue
        if re.match(r"^##\s+", line) and not re.match(r"^##\s+3\.", line):
            in_steps = False
        if re.match(r"^###\s+", line) and not re.match(r"^###\s+2\.1", line):
            in_file_table = False
        if in_file_table and re.match(r"^\|\s*`.+?`\s*\|", line):
            modified_file_count += 1
        if in_steps and re.match(r"^-\s+\[[ xX]\]\s+Step", line):
            step_count += 1
    return PlanMetadata(modified_file_count=modified_file_count, step_count=step_count)


def parse_plan_metadata(plan_path: Path | None) -> PlanMetadata:
    """Extract lightweight plan metadata from a file path."""
    if plan_path is None or not plan_path.is_file():
        return PlanMetadata()
    try:
        contents = plan_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        contents = plan_path.read_text(errors="replace")
    return parse_plan_metadata_from_text(contents)


def resolve_level_name(value: str | None) -> str | None:
    """Map English or Korean level tokens to canonical level names."""
    if value is None or not value.strip():
        return None
    trimmed = value.strip()
    normalized = trimmed.casefold()
    if normalized in LEVEL_RANKS:
        return normalized
    for level in ("low", "medium", "high", "top"):
        if trimmed == KOREAN_TOKENS[level]:
            return level
    return None


def higher_level(current_level: str, candidate_level: str) -> str:
    """Return the higher-ranked level."""
    return candidate_level if LEVEL_RANKS[candidate_level] > LEVEL_RANKS[current_level] else current_level


def join_reasons(reasons: list[str]) -> str:
    """Return the public short reason string."""
    if not reasons:
        return "narrow non-core scope"
    return " + ".join(reasons[:2])


def parse_requested_level_override(text: str | None) -> LevelOverride:
    """Parse a user-requested level override from text."""
    if not text or not text.strip():
        return LevelOverride()
    level_options = (
        KOREAN_TOKENS["top"],
        KOREAN_TOKENS["high"],
        KOREAN_TOKENS["medium"],
        KOREAN_TOKENS["low"],
        "top",
        "high",
        "medium",
        "low",
    )
    joined_level_pattern = "|".join(re.escape(option) for option in level_options)
    level_key_pattern = "|".join(("level", re.escape(KOREAN_TOKENS["level"])))
    patterns = (
        (rf"(?:\[(?:{level_key_pattern})\s*[:=]\s*({joined_level_pattern})\])", "fixed tag"),
        (rf"(?:^|[\s,;])(?:{level_key_pattern})\s*[:=]\s*({joined_level_pattern})(?:$|[\s,;\]])", "fixed tag"),
        (
            r"(?:this\s*task|this\s*run)?\s*(top|high|medium|low)\s*(?:level)?\s*(?:please\s+run|please\s+proceed|run|proceed)",
            "natural language",
        ),
    )
    for pattern, source in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        level = resolve_level_name(match.group(1))
        if level:
            return LevelOverride(level=level, source=source, matched_text=match.group(0).strip())
    for level in ("top", "high", "medium", "low"):
        if KOREAN_TOKENS[level] in text and KOREAN_TOKENS["progress"] in text:
            return LevelOverride(level=level, source="natural language", matched_text=KOREAN_TOKENS[level])
    return LevelOverride()


def add_reason(reasons: list[str], reason: str) -> None:
    """Add a unique reason in first-seen order."""
    if reason and reason not in reasons:
        reasons.append(reason)


def compute_auto_level(
    profile: str,
    context_signal_path: str | None,
    plan_metadata: PlanMetadata,
    scenario_text: str | None,
    additional_prompt_text: str | None,
) -> tuple[str, list[str]]:
    """Compute the Wave 3 auto level and ordered reason list."""
    level = "low"
    reasons: list[str] = []
    combined_text = " ".join(value for value in (context_signal_path, scenario_text, additional_prompt_text) if value)
    for reason in get_path_scope_reasons([context_signal_path] if context_signal_path else []):
        add_reason(reasons, reason)
        if reason in {"harness core path", "db/api/auth core path", "deployment path"}:
            level = higher_level(level, "high")
    if contains_any_keyword(combined_text, AUTH_KEYWORDS):
        add_reason(reasons, "auth keywords")
        level = higher_level(level, "high")
    prompt_signal_text = " ".join(value for value in (scenario_text, additional_prompt_text) if value)
    if contains_any_keyword(prompt_signal_text, HARNESS_TEXT_KEYWORDS):
        add_reason(reasons, "harness keyword")
        level = higher_level(level, "high")
    if profile == "qa":
        add_reason(reasons, "qa verification flow")
        level = higher_level(level, "medium")
    if contains_any_keyword(combined_text, VERIFICATION_KEYWORDS):
        add_reason(reasons, "verification-heavy flow")
        level = higher_level(level, "medium")
    wide_scope = False
    if plan_metadata.modified_file_count >= 4 or plan_metadata.step_count >= 4:
        add_reason(reasons, "multi-file plan")
        level = higher_level(level, "medium")
        wide_scope = True
    if (
        plan_metadata.modified_file_count >= 7
        or plan_metadata.step_count >= 6
        or contains_any_keyword(combined_text, WIDE_SCOPE_KEYWORDS)
    ):
        add_reason(reasons, "wide structural scope")
        level = higher_level(level, "high")
        wide_scope = True
    if contains_any_keyword(combined_text, TOP_RESOURCE_KEYWORDS):
        add_reason(reasons, "full-rigor resource signals")
        level = higher_level(level, "top")
    if wide_scope and LEVEL_RANKS[level] >= LEVEL_RANKS["high"] and profile == "implement":
        add_reason(reasons, "broad implementation plan")
        level = higher_level(level, "top")
    if not reasons:
        add_reason(reasons, "narrow non-core scope")
    return level, reasons


def resolve_bundle_path(requested_bundle_path: str | None, requested_context_mode: str, resolved_level: str) -> str:
    """Resolve the Codex bundle path from context and level."""
    if requested_bundle_path:
        return requested_bundle_path
    if requested_context_mode == "harness":
        return HARNESS_CODEX_HARNESS_BUNDLE_PATH
    if requested_context_mode == "daily":
        return HARNESS_CODEX_BUNDLE_PATH
    if LEVEL_RANKS[resolved_level] >= LEVEL_RANKS["high"]:
        return HARNESS_CODEX_HARNESS_BUNDLE_PATH
    return HARNESS_CODEX_BUNDLE_PATH


def bundle_family_paths(context_mode: str) -> tuple[str, str]:
    """Return Cursor and Claude bundle paths for the resolved context."""
    if context_mode == "harness":
        return HARNESS_CURSOR_HARNESS_BUNDLE_PATH, HARNESS_CLAUDE_HARNESS_BUNDLE_PATH
    return HARNESS_CURSOR_BUNDLE_PATH, HARNESS_CLAUDE_BUNDLE_PATH


def classify_task(
    *,
    repo_root: Path,
    profile: str = "auto",
    prompt_text: str = "",
    paths: Iterable[str] = (),
    context_signal_path: str | None = None,
    plan_path: str | None = None,
    url: str | None = None,
    scenario: str | None = None,
    additional_prompt: str | None = None,
    context_mode: str = "auto",
    bundle_path: str | None = None,
) -> TaskClassification:
    """Classify a task for Cursor hooks, Codex wrapper, and operator preflight."""
    normalized_paths = dedupe_preserve_order(
        normalize_repo_relative_path(repo_root, value) for value in paths
    )
    urls = [url] if url else extract_urls(prompt_text)
    route_kind = infer_route_kind(prompt_text, normalized_paths, urls, profile=profile)
    primary_path = choose_primary_path(normalized_paths)
    explicit_plan = normalize_repo_relative_path(repo_root, plan_path) if plan_path else choose_explicit_plan_path(normalized_paths)
    plan_hint = choose_plan_hint(repo_root, normalized_paths, explicit_plan) if route_kind == "implement" else None
    scenario_label = infer_scenario(prompt_text, fallback=scenario) if route_kind == "qa" else scenario
    signal_path = context_signal_path or primary_path or explicit_plan

    resolved_plan_path: Path | None = None
    if explicit_plan:
        candidate = Path(explicit_plan)
        resolved_plan_path = candidate if candidate.is_absolute() else repo_root / explicit_plan
    plan_metadata = parse_plan_metadata(resolved_plan_path)

    auto_profile = route_kind if route_kind in {"review", "implement", "qa"} else profile
    if auto_profile == "auto":
        auto_profile = "review"
    level_signal_text = " ".join(
        dedupe_preserve_order(text for text in (additional_prompt or "", prompt_text or "") if text)
    ) or None
    auto_level, reason_list = compute_auto_level(
        auto_profile,
        signal_path,
        plan_metadata,
        scenario_label,
        level_signal_text,
    )
    override = parse_requested_level_override(additional_prompt)
    resolved_level = override.level or auto_level
    auto_reason = join_reasons(reason_list)
    reason = (
        f"user override via {override.source}; auto was {auto_level} ({auto_reason})"
        if override.level
        else auto_reason
    )
    risky_ack = bool(
        override.level
        and LEVEL_RANKS[auto_level] >= LEVEL_RANKS["high"]
        and LEVEL_RANKS[override.level] < LEVEL_RANKS[auto_level]
    )
    codex_bundle = resolve_bundle_path(bundle_path, context_mode, resolved_level)
    resolved_context_mode = "harness" if codex_bundle.endswith("_HARNESS.md") else "daily"
    cursor_bundle, claude_bundle = bundle_family_paths(resolved_context_mode)
    guidance = LEVEL_GUIDANCE[resolved_level]
    path_scope_reasons = tuple(get_path_scope_reasons(normalized_paths + ([signal_path] if signal_path else [])))
    needs_rpi = bool(
        route_kind == "implement"
        and (
            resolved_context_mode == "harness"
            or any(reason in {"harness core path", "db/api/auth core path", "deployment path"} for reason in path_scope_reasons)
        )
    )
    has_explicit_plan = bool(explicit_plan)
    needs_user_direction = bool(
        risky_ack
        or (route_kind == "implement" and needs_rpi and not has_explicit_plan)
        or (route_kind == "implement" and primary_path is None and not has_explicit_plan)
    )
    user_direction_reason = None
    if risky_ack:
        user_direction_reason = "high-risk level downgrade requires confirmation"
    elif route_kind == "implement" and needs_rpi and not has_explicit_plan:
        user_direction_reason = "harness/core implementation requires an approved plan/spec"
    elif route_kind == "implement" and primary_path is None and not has_explicit_plan:
        user_direction_reason = "implementation target is ambiguous"

    return TaskClassification(
        route_kind=route_kind,
        profile=auto_profile,
        level=resolved_level,
        auto_level=auto_level,
        reason=reason,
        auto_reason=auto_reason,
        context_mode=resolved_context_mode,
        bundle_path=codex_bundle,
        cursor_bundle_path=cursor_bundle,
        claude_bundle_path=claude_bundle,
        codex_bundle_path=codex_bundle,
        verification=str(guidance["verification"]),
        prompt_lines=tuple(guidance["prompt_lines"]),
        resource_hints=tuple(guidance["resource_hints"]),
        reasons=tuple(reason_list),
        path_scope_reasons=path_scope_reasons,
        needs_rpi=needs_rpi,
        needs_user_direction=needs_user_direction,
        user_direction_reason=user_direction_reason,
        primary_path=primary_path,
        plan_hint=plan_hint,
        explicit_plan_path=explicit_plan,
        url=urls[0] if urls else None,
        scenario=scenario_label,
        override_level=override.level,
        override_source=override.source,
        override_matched_text=override.matched_text,
        risky_override_ack_required=risky_ack,
        plan_metadata=plan_metadata,
    )


def classify_payload(payload: dict[str, Any], repo_root: Path) -> TaskClassification:
    """Classify a Cursor hook payload."""
    prompt_text = extract_prompt_text(payload)
    attachment_paths = collect_path_values(payload.get("attachments", []))
    prompt_paths = extract_prompt_paths(prompt_text)
    return classify_task(
        repo_root=repo_root,
        profile="auto",
        prompt_text=prompt_text,
        paths=attachment_paths + prompt_paths,
        additional_prompt=prompt_text,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--profile", default="auto", choices=("auto", "review", "implement", "qa"))
    parser.add_argument("--prompt", default="")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--context-signal-path")
    parser.add_argument("--plan")
    parser.add_argument("--url")
    parser.add_argument("--scenario")
    parser.add_argument("--additional-prompt")
    parser.add_argument("--context-mode", default="auto", choices=("auto", "daily", "harness"))
    parser.add_argument("--bundle-path")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for runners that need the shared classifier."""
    args = _build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    classification = classify_task(
        repo_root=repo_root,
        profile=args.profile,
        prompt_text=args.prompt,
        paths=args.path,
        context_signal_path=args.context_signal_path,
        plan_path=args.plan,
        url=args.url,
        scenario=args.scenario,
        additional_prompt=args.additional_prompt,
        context_mode=args.context_mode,
        bundle_path=args.bundle_path,
    )
    payload = classification.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"{payload['level']} ({payload['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
