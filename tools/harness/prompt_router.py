"""Prompt-side harness auto-entry routing for Cursor hooks."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

from paths import (
    HARNESS_BUNDLE_PREFIX,
    HARNESS_CODEX_BUNDLE_PATH,
    HARNESS_CODEX_HARNESS_BUNDLE_PATH,
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

REVIEW_KEYWORDS = (
    "review",
    "audit",
    "inspect",
    "check",
    "검토",
    "리뷰",
    "감사",
    "점검",
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
    "구현",
    "수정",
    "변경",
    "추가",
    "고쳐",
    "만들",
    "작성",
)
QA_KOREAN_KEYWORDS = ("검증", "테스트", "재현")
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
    "task_plan.md",
    "findings.md",
    "progress.md",
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
CORE_PREFIXES = ("apps/api/", "migrations/", "services/auth/", "auth/")
DEPLOY_EXACT_MATCHES = {"dockerfile", "procfile", "railway.toml", "railway.json"}
DEPLOY_PREFIXES = (".github/workflows/", "docker/", "deploy/")


@dataclass(frozen=True)
class PromptRoute:
    """Resolved prompt route information for the before-submit hook."""

    kind: str
    context_mode: str
    primary_path: str | None = None
    plan_hint: str | None = None
    url: str | None = None
    scenario: str | None = None
    reason: str | None = None
    needs_rpi: bool = False


def _find_first_string(data: Any, target_keys: tuple[str, ...]) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in target_keys and isinstance(value, str) and value.strip():
                return value.strip()
            found = _find_first_string(value, target_keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_first_string(item, target_keys)
            if found:
                return found
    return None


def _collect_path_values(data: Any) -> list[str]:
    values: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in PATH_KEYS and isinstance(value, str) and value.strip():
                values.append(value.strip())
            values.extend(_collect_path_values(value))
    elif isinstance(data, list):
        for item in data:
            values.extend(_collect_path_values(item))
    return values


def extract_prompt_text(payload: dict[str, Any]) -> str:
    """Return the user prompt text from the hook payload."""
    prompt = _find_first_string(payload, PROMPT_KEYS)
    return prompt or ""


def extract_attachment_paths(payload: dict[str, Any]) -> list[str]:
    """Return all attachment-like paths advertised in the payload."""
    attachments = payload.get("attachments", [])
    return _collect_path_values(attachments)


def extract_urls(text: str) -> list[str]:
    """Return URL candidates from the prompt text."""
    return [match.rstrip(".,)") for match in URL_RE.findall(text or "")]


def extract_prompt_paths(text: str) -> list[str]:
    """Return file path candidates from the prompt text."""
    candidates: list[str] = []
    for raw in PATH_RE.findall(text or ""):
        candidate = raw.strip("`\"'()[]{}<>,.;")
        if candidate.lower().startswith(("http://", "https://")):
            continue
        if candidate:
            candidates.append(candidate)
    return candidates


def normalize_repo_relative_path(repo_root: Path, value: str) -> str:
    """Normalize a path-like string to repo-relative slash form when possible."""
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


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def is_harness_context_path(repo_relative_path: str) -> bool:
    """Return True when the path belongs to harness/operator context."""
    normalized = repo_relative_path.replace("\\", "/").lower()
    if normalized in HARNESS_EXACT_MATCHES:
        return True
    return any(normalized.startswith(prefix) for prefix in HARNESS_PREFIXES)


def get_path_scope_reasons(paths: list[str]) -> list[str]:
    """Return unique scope reasons for the provided repo-relative paths."""
    reasons: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/").lower()
        if is_harness_context_path(normalized) and "harness core path" not in reasons:
            reasons.append("harness core path")
        if normalized in CORE_EXACT_MATCHES or any(normalized.startswith(prefix) for prefix in CORE_PREFIXES):
            if "db/api/auth core path" not in reasons:
                reasons.append("db/api/auth core path")
        if normalized in DEPLOY_EXACT_MATCHES or any(normalized.startswith(prefix) for prefix in DEPLOY_PREFIXES):
            if "deployment path" not in reasons:
                reasons.append("deployment path")
    return reasons


def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _contains_explicit_qa_intent(text: str) -> bool:
    """Return True when the prompt explicitly asks for QA-style execution."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in QA_REGEX_PATTERNS) or any(
        token in text for token in QA_KOREAN_KEYWORDS
    )


def infer_route_kind(prompt_text: str, normalized_paths: list[str], urls: list[str]) -> str:
    """Infer whether this is a review, implementation, QA, or generic prompt."""
    lowered = prompt_text.lower()
    has_review_intent = _contains_any_keyword(lowered, REVIEW_KEYWORDS)
    has_implement_intent = _contains_any_keyword(lowered, IMPLEMENT_KEYWORDS)
    has_explicit_qa_intent = _contains_explicit_qa_intent(prompt_text)

    if has_review_intent:
        return "review"

    if has_implement_intent:
        return "implement"

    if any(path.lower().startswith(("docs/specs/", "docs/plans/")) for path in normalized_paths):
        return "implement"

    if has_explicit_qa_intent or urls:
        return "qa"

    return "generic"


def infer_context_mode(route_kind: str, reasons: list[str]) -> str:
    """Infer whether the prompt should be treated as daily or harness context."""
    if route_kind == "qa":
        return "daily"
    if any(reason in ("harness core path", "db/api/auth core path", "deployment path") for reason in reasons):
        return "harness"
    return "daily"


def infer_scenario(prompt_text: str) -> str:
    """Infer a QA scenario label from a natural-language prompt."""
    lowered = prompt_text.lower()
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
    """Choose the most relevant non-plan file path from the candidates."""
    for path in paths:
        lowered = path.lower()
        if lowered.startswith(("docs/specs/", "docs/plans/")):
            continue
        return path
    return paths[0] if paths else None


def choose_plan_hint(repo_root: Path, paths: list[str]) -> str:
    """Return the best plan/spec hint for wrapper-first implementation."""
    for path in paths:
        lowered = path.lower()
        if lowered.startswith(("docs/specs/", "docs/plans/")):
            return path

    latest_spec = find_latest_spec(repo_root)
    if latest_spec is not None:
        try:
            return latest_spec.resolve().relative_to(repo_root.resolve()).as_posix()
        except Exception:
            return latest_spec.as_posix()

    return "<approved-plan-or-spec-path>"


def route_prompt(payload: dict[str, Any], repo_root: Path) -> PromptRoute:
    """Classify a prompt and build the routing contract used by the hook."""
    prompt_text = extract_prompt_text(payload)
    urls = extract_urls(prompt_text)
    attachment_paths = [
        normalize_repo_relative_path(repo_root, value)
        for value in extract_attachment_paths(payload)
    ]
    prompt_paths = [
        normalize_repo_relative_path(repo_root, value)
        for value in extract_prompt_paths(prompt_text)
    ]
    normalized_paths = _dedupe_preserve_order(attachment_paths + prompt_paths)
    reasons = get_path_scope_reasons(normalized_paths)
    route_kind = infer_route_kind(prompt_text, normalized_paths, urls)
    context_mode = infer_context_mode(route_kind, reasons)
    primary_path = choose_primary_path(normalized_paths)

    if route_kind == "qa":
        return PromptRoute(
            kind="qa",
            context_mode="daily",
            url=urls[0] if urls else None,
            scenario=infer_scenario(prompt_text),
            reason="qa verification flow",
        )

    if route_kind == "review":
        return PromptRoute(
            kind="review",
            context_mode=context_mode,
            primary_path=primary_path or "<target-file>",
            reason=", ".join(reasons) if reasons else "review intent",
        )

    if route_kind == "implement":
        return PromptRoute(
            kind="implement",
            context_mode=context_mode,
            primary_path=primary_path,
            plan_hint=choose_plan_hint(repo_root, normalized_paths),
            reason=", ".join(reasons) if reasons else "implementation intent",
            needs_rpi=bool(
                context_mode == "harness"
                or any(reason in ("harness core path", "db/api/auth core path", "deployment path") for reason in reasons)
            ),
        )

    return PromptRoute(kind="generic", context_mode="daily")


def build_agent_message(route: PromptRoute) -> str | None:
    """Return the hook-side system message for the resolved route."""
    if route.kind == "generic":
        return None

    lines = [
        "[SYSTEM] Harness auto-entry router",
    ]

    if route.kind == "review":
        lines.extend(
            [
                "This prompt looks like a review request. Prefer the wrapper-first review path.",
                (
                    '`powershell -NoProfile -File "tools/harness/run_codex.ps1" '
                    f'-Profile review -Target "{route.primary_path or "<target-file>"}"`'
                ),
            ]
        )
        if route.context_mode == "harness":
            lines.append(
                f"Because the scope touches harness/core/deploy files, prefer `{HARNESS_CODEX_HARNESS_BUNDLE_PATH}` and strong verification."
            )
        return "\n".join(lines)

    if route.kind == "implement":
        lines.extend(
            [
                "This prompt looks like an implementation request. Prefer the wrapper-first implementation path.",
                "Because `run_codex.ps1 -Profile implement` requires an approved plan/spec, confirm or create that plan before coding.",
                (
                    '`powershell -NoProfile -File "tools/harness/run_codex.ps1" '
                    f'-Profile implement -Plan "{route.plan_hint or "<approved-plan-or-spec-path>"}"`'
                ),
            ]
        )
        if route.needs_rpi:
            lines.append("RPI applies here: Research -> Plan -> Implement.")
        if route.primary_path:
            lines.append(f'Scope hint: `{route.primary_path}`')
        if route.context_mode == "harness":
            lines.append(f"Prefer harness context: `{HARNESS_CODEX_HARNESS_BUNDLE_PATH}`.")
        return "\n".join(lines)

    if route.kind == "qa":
        lines.extend(
            [
                "This prompt looks like a QA request. Prefer the QA wrapper path.",
                (
                    '`powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" '
                    f'-Url "{route.url or "<http-url>"}" -Scenario "{route.scenario or "qa"}"`'
                ),
                f"The QA wrapper keeps the daily bundle (`{HARNESS_CODEX_BUNDLE_PATH}`) by default and lets `run_codex.ps1` promote risk when needed.",
            ]
        )
        return "\n".join(lines)

    return None


def build_hook_output(payload: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Return the JSON-serializable hook output for Cursor."""
    route = route_prompt(payload, repo_root)
    agent_message = build_agent_message(route)
    output: dict[str, Any] = {"continue": True}
    if agent_message:
        output["agentMessage"] = agent_message
    return output
