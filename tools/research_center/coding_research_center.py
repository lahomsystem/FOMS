#!/usr/bin/env python
"""
Enterprise-grade coding/AI-coding research center runner.

Features:
- Weekly source crawl (RSS/Atom)
- Signal scoring by track
- Actionable apply-now queue generation
- Optional sync into evolution backlog/radar docs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "tools" / "research_center" / "sources.json"
DEFAULT_OUTPUT = ROOT / "docs" / "evolution" / "research"
DEFAULT_RADAR = ROOT / "docs" / "evolution" / "RADAR.md"
DEFAULT_BACKLOG = ROOT / "docs" / "evolution" / "HYPOTHESIS_BACKLOG.md"
DEFAULT_SELF_MANIFEST = ROOT / "tools" / "research_center" / "self_upgrade_manifest.json"
DEFAULT_MCP_CONFIG = Path(os.path.expanduser("~/.cursor/mcp.json"))

DEFAULT_TRACKS = (
    "tech_stack",
    "frontend",
    "backend",
    "uiux",
    "ai_coding",
    "integration",
)

DEFAULT_OWNER_MAP = {
    "tech_stack": "evolution-architect",
    "frontend": "frontend-ui",
    "backend": "python-backend",
    "uiux": "frontend-ui",
    "ai_coding": "coding-research-center",
    "integration": "devops-deploy",
    "security": "code-reviewer",
    "qa_testing": "code-reviewer",
    "observability": "devops-deploy",
    "devops_platform": "devops-deploy",
    "data_layer": "database-specialist",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def strip_html(text: str) -> str:
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    no_ws = re.sub(r"\s+", " ", no_tags)
    return no_ws.strip()


def parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    iso = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def text_or_none(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""
    return (node.text or "").strip()


def find_child_text(parent: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        node = parent.find(name)
        if node is not None and (node.text or "").strip():
            return (node.text or "").strip()
    return ""


def normalize_track(value: str, allowed_tracks: Iterable[str]) -> str:
    v = value.strip().lower()
    allowed = set(allowed_tracks)
    return v if v in allowed else "integration"


def discover_tracks(config: Dict[str, Any]) -> List[str]:
    ordered: List[str] = list(DEFAULT_TRACKS)
    seen = set(ordered)

    for track in (config.get("track_keywords") or {}).keys():
        t = str(track).strip().lower()
        if t and t not in seen:
            ordered.append(t)
            seen.add(t)

    for row in config.get("sources", []):
        for track in row.get("tracks", []):
            t = str(track).strip().lower()
            if t and t not in seen:
                ordered.append(t)
                seen.add(t)
    return ordered


def normalize_keywords(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    seen = set()
    for raw in values:
        kw = str(raw).strip().lower()
        if not kw or kw in seen:
            continue
        out.append(kw)
        seen.add(kw)
    return out


def build_program_focus(config: Dict[str, Any]) -> Dict[str, Any]:
    raw = config.get("program_focus")
    if not isinstance(raw, dict):
        return {
            "keywords": [],
            "critical_keywords": [],
            "per_hit": 2,
            "per_critical_hit": 4,
            "max_bonus": 0,
        }

    keywords = normalize_keywords(raw.get("keywords", []))
    critical_keywords = normalize_keywords(raw.get("critical_keywords", []))
    per_hit = max(1, int(raw.get("per_hit", 2)))
    per_critical_hit = max(2, int(raw.get("per_critical_hit", 4)))
    max_bonus = max(0, int(raw.get("max_bonus", 18)))
    return {
        "name": str(raw.get("name", "program_focus")).strip() or "program_focus",
        "keywords": keywords,
        "critical_keywords": critical_keywords,
        "per_hit": per_hit,
        "per_critical_hit": per_critical_hit,
        "max_bonus": max_bonus,
    }


def score_program_focus(text: str, program_focus: Dict[str, Any]) -> Tuple[int, List[str]]:
    keywords = [kw for kw in program_focus.get("keywords", []) if kw]
    critical_keywords = [kw for kw in program_focus.get("critical_keywords", []) if kw]
    if not keywords and not critical_keywords:
        return 0, []

    hit_keywords = [kw for kw in keywords if kw in text]
    hit_critical = [kw for kw in critical_keywords if kw in text]
    bonus = len(set(hit_keywords)) * int(program_focus.get("per_hit", 2))
    bonus += len(set(hit_critical)) * int(program_focus.get("per_critical_hit", 4))
    bonus = min(int(program_focus.get("max_bonus", 0)), bonus)

    merged: List[str] = []
    seen = set()
    for kw in hit_critical + hit_keywords:
        if kw in seen:
            continue
        merged.append(kw)
        seen.add(kw)
        if len(merged) >= 8:
            break
    return bonus, merged


@dataclass
class Source:
    source_id: str
    name: str
    type: str
    feed_url: str
    credibility: str
    official: bool
    tracks: List[str]


@dataclass
class ResearchItem:
    source_id: str
    source_name: str
    source_credibility: str
    source_official: bool
    title: str
    link: str
    published_at: Optional[datetime]
    summary: str
    raw_tracks: List[str]
    primary_track: str = "integration"
    score: int = 0
    confidence: str = "Medium"
    focus_score: int = 0
    focus_hits: List[str] = field(default_factory=list)


@dataclass
class ActionItem:
    action_id: str
    priority: str
    title: str
    rationale: str
    proposed_change: str
    owner: str
    track: str
    source_links: List[str]


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources(config: Dict[str, Any], tracks: List[str]) -> List[Source]:
    sources: List[Source] = []
    for row in config.get("sources", []):
        source_tracks = [normalize_track(x, tracks) for x in row.get("tracks", [])]
        sources.append(
            Source(
                source_id=row["id"],
                name=row["name"],
                type=row.get("type", "rss").lower(),
                feed_url=row["feed_url"],
                credibility=row.get("credibility", "medium").lower(),
                official=bool(row.get("official", True)),
                tracks=source_tracks or ["integration"],
            )
        )
    return sources


def parse_rss_items(xml_text: str, source: Source) -> List[ResearchItem]:
    root = ET.fromstring(xml_text)
    items: List[ResearchItem] = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = find_child_text(item, ("title",))
        link = find_child_text(item, ("link",))
        pub = find_child_text(item, ("pubDate", "date", "published"))
        desc = find_child_text(item, ("description", "summary"))
        if not title or not link:
            continue
        items.append(
            ResearchItem(
                source_id=source.source_id,
                source_name=source.name,
                source_credibility=source.credibility,
                source_official=source.official,
                title=strip_html(title),
                link=link.strip(),
                published_at=parse_date(pub),
                summary=strip_html(desc),
                raw_tracks=list(source.tracks),
            )
        )

    # Atom
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//atom:entry", ns)
        if not entries:
            entries = root.findall(".//entry")
        for entry in entries:
            title = text_or_none(entry.find("{http://www.w3.org/2005/Atom}title")) or text_or_none(
                entry.find("title")
            )
            link = ""
            link_node = entry.find("{http://www.w3.org/2005/Atom}link")
            if link_node is None:
                link_node = entry.find("link")
            if link_node is not None:
                link = (link_node.attrib.get("href") or link_node.text or "").strip()
            published = (
                text_or_none(entry.find("{http://www.w3.org/2005/Atom}published"))
                or text_or_none(entry.find("{http://www.w3.org/2005/Atom}updated"))
                or text_or_none(entry.find("published"))
                or text_or_none(entry.find("updated"))
            )
            summary = (
                text_or_none(entry.find("{http://www.w3.org/2005/Atom}summary"))
                or text_or_none(entry.find("{http://www.w3.org/2005/Atom}content"))
                or text_or_none(entry.find("summary"))
                or text_or_none(entry.find("content"))
            )
            if not title or not link:
                continue
            items.append(
                ResearchItem(
                    source_id=source.source_id,
                    source_name=source.name,
                    source_credibility=source.credibility,
                    source_official=source.official,
                    title=strip_html(title),
                    link=link,
                    published_at=parse_date(published),
                    summary=strip_html(summary),
                    raw_tracks=list(source.tracks),
                )
            )
    return items


def fetch_source_items(
    session: requests.Session,
    source: Source,
    timeout_sec: int,
) -> Tuple[List[ResearchItem], Optional[str]]:
    try:
        resp = session.get(source.feed_url, timeout=timeout_sec)
        resp.raise_for_status()
        items = parse_rss_items(resp.text, source)
        return items, None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def shorten_error(message: str, limit: int = 260) -> str:
    msg = re.sub(r"\s+", " ", message).strip()
    if len(msg) <= limit:
        return msg
    return msg[: limit - 3] + "..."


def apply_track_scores(
    item: ResearchItem,
    now: datetime,
    track_keywords: Dict[str, List[str]],
    tracks: List[str],
    program_focus: Dict[str, Any],
) -> ResearchItem:
    text = f"{item.title} {item.summary}".lower()
    base = {"high": 35, "medium": 22, "low": 12}.get(item.source_credibility, 18)
    if item.source_official:
        base += 8

    if item.published_at is None:
        freshness = 6
        age_days = 999
    else:
        age_days = max(0, int((now - item.published_at).total_seconds() // 86400))
        freshness = max(0, 30 - age_days)

    per_track: Dict[str, int] = {}
    for track in tracks:
        keywords = [k.lower() for k in track_keywords.get(track, [])]
        hits = sum(1 for kw in keywords if kw in text)
        source_track_bonus = 10 if track in item.raw_tracks else 0
        per_track[track] = hits * 5 + source_track_bonus

    primary_track = max(per_track.items(), key=lambda kv: kv[1])[0]
    relevance = per_track[primary_track]
    if relevance == 0 and item.raw_tracks:
        primary_track = item.raw_tracks[0]
        relevance = 8

    focus_bonus, focus_hits = score_program_focus(text, program_focus)
    score = min(100, base + freshness + relevance + focus_bonus)
    if score >= 75:
        confidence = "High"
    elif score >= 50:
        confidence = "Medium"
    else:
        confidence = "Low"

    item.primary_track = primary_track
    item.score = score
    item.confidence = confidence
    item.focus_score = focus_bonus
    item.focus_hits = focus_hits
    return item


def dedupe_items(items: List[ResearchItem]) -> List[ResearchItem]:
    seen: Dict[str, ResearchItem] = {}
    for item in items:
        key = item.link.strip().lower()
        existing = seen.get(key)
        if existing is None or item.score > existing.score:
            seen[key] = item
    return list(seen.values())


def pick_priority(item: ResearchItem) -> str:
    t = f"{item.title} {item.summary}".lower()
    security_signals = (
        "security",
        "vulnerability",
        "cve",
        "exploit",
    )
    lifecycle_signals = (
        "deprecate",
        "deprecated",
        "retired",
        "sunset",
        "breaking change",
        "breaking",
    )
    p1_signals = (
        "major",
        "release",
        "beta",
        "preview",
        "agent",
        "copilot",
        "codegen",
        "assistant",
        "model",
    )
    if any(x in t for x in security_signals) and item.source_credibility == "high":
        return "P0"
    if any(x in t for x in lifecycle_signals) and item.source_credibility in ("high", "medium"):
        return "P0"
    if any(x in t for x in p1_signals):
        return "P1"
    return "P2"


def proposed_change_by_track(track: str, title: str) -> str:
    if track == "backend":
        return f"Create spike branch to validate backend impact of '{title}', then run API smoke tests."
    if track == "frontend":
        return f"Prototype frontend change from '{title}' in isolated module and run UI regression checklist."
    if track == "uiux":
        return f"Design QA pass for '{title}' with measurable UX KPI and rollback-ready CSS/HTML diff."
    if track == "ai_coding":
        return f"Run controlled pilot for '{title}' in one workflow, compare dev-time and defect metrics."
    if track == "tech_stack":
        return f"Build compatibility matrix for '{title}' and execute dependency upgrade rehearsal."
    if track == "security":
        return f"Run security impact triage for '{title}' and patch/mitigate with rollback-ready deployment plan."
    if track == "qa_testing":
        return f"Extend regression suite for '{title}' and gate rollout with pass/fail CI criteria."
    if track == "observability":
        return f"Add metrics/log/trace checks for '{title}' and validate dashboard + alert behavior."
    if track == "devops_platform":
        return f"Validate infra/deploy impact of '{title}' in staging with canary and rollback rehearsal."
    if track == "data_layer":
        return f"Assess schema/query/index impact of '{title}' and verify migration safety with backup/restore test."
    return f"Review cross-stack impact of '{title}', then split work into backend/frontend/devops tasks."


def build_action_queue(items: List[ResearchItem], apply_limit: int, now: datetime) -> List[ActionItem]:
    actions: List[ActionItem] = []
    for idx, item in enumerate(items[:apply_limit], start=1):
        seed = hashlib.sha1(f"{item.link}|{idx}".encode("utf-8")).hexdigest()[:8]
        action_id = f"A-{now.date()}-{seed}"
        priority = pick_priority(item)
        rationale = (
            f"{item.source_name} source, score={item.score}, confidence={item.confidence}, "
            f"track={item.primary_track}, focus={item.focus_score}"
        )
        if item.focus_hits:
            rationale += f", focus_hits={','.join(item.focus_hits[:3])}"
        actions.append(
            ActionItem(
                action_id=action_id,
                priority=priority,
                title=item.title,
                rationale=rationale,
                proposed_change=proposed_change_by_track(item.primary_track, item.title),
                owner="evolution-architect",
                track=item.primary_track,
                source_links=[item.link],
            )
        )
    return actions


def infer_provider(item: ResearchItem) -> str:
    text = f"{item.source_name} {item.title} {item.link}".lower()
    provider_patterns = [
        ("openai", ("openai", "chatgpt", "gpt-", "codex")),
        ("anthropic", ("anthropic", "claude")),
        ("google", ("google", "gemini", "vertex ai")),
        ("microsoft", ("microsoft", "copilot", "vscode")),
        ("meta", ("meta", "llama")),
        ("github", ("github",)),
        ("arxiv", ("arxiv",)),
    ]
    for provider, patterns in provider_patterns:
        if any(p in text for p in patterns):
            return provider
    return "other"


def default_future_stack_options() -> List[Dict[str, Any]]:
    return [
        {
            "id": "adaptive-modular-monolith",
            "name": "Adaptive Modular Monolith + Agent Layer",
            "fit_tracks": ["backend", "integration", "ai_coding"],
            "stack": [
                "Flask API + selective FastAPI extraction",
                "PostgreSQL + Redis cache/queue",
                "Celery/RQ async jobs",
                "OpenTelemetry metrics/log traces",
                "MCP-based tool orchestration for AI coding",
            ],
            "macro_short": "측정/실험 기반으로 현재 모놀리스를 안전하게 모듈화하고 AI 코딩 워크플로우를 붙이는 전략",
            "macro_mid": "병목 도메인을 서비스화하고 배포/관측 자동화를 표준화",
            "macro_long": "지속적 자가 업그레이드 루프와 Agent-Driven Delivery 정착",
        },
        {
            "id": "agent-native-platform",
            "name": "Agent-Native Delivery Platform",
            "fit_tracks": ["ai_coding", "integration", "tech_stack"],
            "stack": [
                "LLM gateway abstraction (OpenAI/Claude/Gemini)",
                "Prompt/eval/version registry",
                "Policy-enforced MCP runtime",
                "Automated experiment runner + benchmark dashboard",
                "Rule/Skill/Hook auto-refinement pipeline",
            ],
            "macro_short": "멀티 모델 실험 허브와 공통 추상화 계층 구축",
            "macro_mid": "코딩 에이전트 품질 게이트와 안전 정책 자동화",
            "macro_long": "AI 코딩 운영체제 수준의 자율 개선 체계 확보",
        },
        {
            "id": "frontend-experience-forward",
            "name": "Frontend Experience Forward Stack",
            "fit_tracks": ["frontend", "uiux", "ai_coding"],
            "stack": [
                "Design tokens + component governance",
                "TypeScript-first frontend modules",
                "UI test automation + visual regression",
                "AI-assisted UX telemetry analysis",
                "Progressive enhancement + accessibility baseline",
            ],
            "macro_short": "UI 일관성/접근성/성능 기준 정립",
            "macro_mid": "대형 템플릿 분해와 컴포넌트 중심 구조 전환",
            "macro_long": "AI 기반 UX 최적화 루프 자동화",
        },
    ]


def get_future_stack_options(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    options = config.get("future_stack_options", [])
    if options:
        return options
    return default_future_stack_options()


def build_macro_micro_plan(
    items: List[ResearchItem],
    actions: List[ActionItem],
    config: Dict[str, Any],
    now: datetime,
) -> Dict[str, Any]:
    top_items = items[:120]
    track_counts: Dict[str, int] = dict(Counter(x.primary_track for x in top_items))
    provider_counts: Dict[str, int] = dict(Counter(infer_provider(x) for x in top_items))
    focus_aligned = sum(1 for x in top_items if x.focus_score > 0)

    options = get_future_stack_options(config)
    scored_options: List[Tuple[int, Dict[str, Any]]] = []
    for option in options:
        fit_tracks = [str(x).strip().lower() for x in option.get("fit_tracks", [])]
        fit_score = sum(track_counts.get(track, 0) for track in fit_tracks)
        scored_options.append((fit_score, option))
    scored_options.sort(key=lambda x: x[0], reverse=True)
    selected = [x[1] for x in scored_options[:3]]

    selected_names = [x.get("name", x.get("id", "unknown")) for x in selected]
    top_tracks = [x for x, _ in Counter(x.primary_track for x in top_items).most_common(4)]

    macro_plan = [
        {
            "horizon": "short_term_0_4_weeks",
            "goal": "멀티 AI 코딩 생태계 실험 기반 수용",
            "initiatives": [
                "모델/에이전트 비교 실험 트랙 수립 (OpenAI/Claude/Gemini/Copilot)",
                "현재 코드베이스 영향도 분석 및 호환성 매트릭스 작성",
                "P1 액션 2~3개 스파이크 실행 + 회귀 테스트 자동화",
            ],
        },
        {
            "horizon": "mid_term_1_3_months",
            "goal": "스택 전환 기반 구축 및 운영 표준화",
            "initiatives": [
                "상위 후보 스택 1개 선택 후 파일럿 마이그레이션",
                "서비스 경계/인터페이스 계약/배포 롤백 표준 수립",
                "AI 코딩 툴링 평가 기준(속도/품질/비용) 운영",
            ],
        },
        {
            "horizon": "long_term_3_12_months",
            "goal": "자가 업그레이드 가능한 AI-통합 개발 플랫폼 완성",
            "initiatives": [
                "Rules/Skills/Hooks/Agents 자동 개선 루프 고도화",
                "MCP 도구 체계의 안전 정책/감사 추적 자동화",
                "아키텍처 진화 의사결정을 KPI 기반으로 상시 운영",
            ],
        },
    ]

    micro_plan: List[Dict[str, Any]] = []
    for idx, action in enumerate(actions[:15], start=1):
        owner = DEFAULT_OWNER_MAP.get(action.track, "evolution-architect")
        micro_plan.append(
            {
                "task_id": f"M-{idx:03d}",
                "title": action.title,
                "priority": action.priority,
                "track": action.track,
                "owner": owner,
                "design_whole": "전체 설계: 영향 시스템/데이터/배포 경계 정의",
                "design_part": "부분 설계: 도메인 모듈, API 계약, 테스트 범위 정의",
                "design_detail": action.proposed_change,
                "dod": "기능/테스트/롤백 경로 검증 완료",
                "abort": "회귀 또는 성능/보안 기준 미달 시 즉시 중단",
                "rollback": "릴리즈 단위 revert + 데이터 영향 복구 절차 실행",
                "source_links": action.source_links,
            }
        )

    return {
        "generated_at_utc": now.isoformat(),
        "landscape": {
            "top_tracks": top_tracks,
            "track_counts": track_counts,
            "provider_counts": provider_counts,
            "focus_aligned_signals": focus_aligned,
        },
        "recommended_stack_combinations": selected,
        "recommended_stack_names": selected_names,
        "macro_plan": macro_plan,
        "micro_plan": micro_plan,
    }


def write_macro_micro_plan(output_dir: Path, plan: Dict[str, Any]) -> Tuple[Path, Path]:
    ensure_dir(output_dir)
    md_path = output_dir / "MACRO_MICRO_MIGRATION_PLAN.md"
    json_path = output_dir / "macro_micro_migration_plan.json"

    landscape = plan.get("landscape", {})
    top_tracks = landscape.get("top_tracks", [])
    provider_counts = landscape.get("provider_counts", {})
    focus_aligned = landscape.get("focus_aligned_signals", 0)
    stack_options = plan.get("recommended_stack_combinations", [])
    macro_plan = plan.get("macro_plan", [])
    micro_plan = plan.get("micro_plan", [])

    lines: List[str] = []
    lines.append("# Macro-Micro Migration Plan")
    lines.append("")
    lines.append(f"- Generated at (UTC): {plan.get('generated_at_utc', '')}")
    lines.append(f"- Top tracks: {', '.join(top_tracks) if top_tracks else 'n/a'}")
    lines.append(f"- Focus-aligned signals (current stack fit): {focus_aligned}")
    lines.append("")
    lines.append("## AI Coding Ecosystem Coverage")
    lines.append("")
    lines.append("| Provider | Signals |")
    lines.append("|----------|--------:|")
    for provider, cnt in sorted(provider_counts.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {provider} | {cnt} |")
    lines.append("")
    lines.append("## Recommended Stack Combinations")
    lines.append("")
    for idx, option in enumerate(stack_options, start=1):
        lines.append(f"### Option {idx}. {option.get('name', option.get('id', 'unknown'))}")
        lines.append(f"- Fit tracks: {', '.join(option.get('fit_tracks', []))}")
        stack = option.get("stack", [])
        if stack:
            lines.append("- Stack:")
            for s in stack:
                lines.append(f"  - {s}")
        lines.append(f"- Short-term focus: {option.get('macro_short', '')}")
        lines.append(f"- Mid-term focus: {option.get('macro_mid', '')}")
        lines.append(f"- Long-term focus: {option.get('macro_long', '')}")
        lines.append("")
    lines.append("## Macro Plan")
    lines.append("")
    for row in macro_plan:
        lines.append(f"### {row.get('horizon', '')} - {row.get('goal', '')}")
        for it in row.get("initiatives", []):
            lines.append(f"- {it}")
        lines.append("")
    lines.append("## Micro Execution Blueprint")
    lines.append("")
    lines.append("| ID | Priority | Track | Owner | Title | Detail Design | DoD |")
    lines.append("|----|----------|-------|-------|-------|---------------|-----|")
    for row in micro_plan:
        lines.append(
            f"| {row.get('task_id')} | {row.get('priority')} | {row.get('track')} | {row.get('owner')} | "
            f"{str(row.get('title', '')).replace('|', '/')} | "
            f"{str(row.get('design_detail', '')).replace('|', '/')} | "
            f"{str(row.get('dod', '')).replace('|', '/')} |"
        )
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def default_self_manifest() -> Dict[str, Any]:
    return {
        "agents": [
            {
                "name": "grand-develop-master",
                "path": ".cursor/agents/grand-develop-master.md",
                "auto_create_stub": False,
            },
            {
                "name": "coding-research-center",
                "path": ".cursor/agents/coding-research-center.md",
                "auto_create_stub": False,
            },
            {
                "name": "evolution-architect",
                "path": ".cursor/agents/evolution-architect.md",
                "auto_create_stub": False,
            },
            {
                "name": "migration-executor",
                "path": ".cursor/agents/migration-executor.md",
                "auto_create_stub": True,
            },
        ],
        "rules": [
            {
                "name": "12-macro-micro-migration-execution",
                "path": ".cursor/rules/12-macro-micro-migration-execution.mdc",
                "auto_create_stub": True,
            },
            {
                "name": "13-self-evolution-autoupgrade",
                "path": ".cursor/rules/13-self-evolution-autoupgrade.mdc",
                "auto_create_stub": True,
            },
        ],
        "skills": [
            {
                "name": "tech-stack-evaluator",
                "path": ".cursor/skills/skills/tech-stack-evaluator/SKILL.md",
            },
            {
                "name": "self-evolution-factory",
                "path": ".cursor/skills/skills/self-evolution-factory/SKILL.md",
            },
            {
                "name": "context7-auto-research",
                "path": ".cursor/skills/skills/context7-auto-research/SKILL.md",
            },
            {
                "name": "agent-orchestration-multi-agent-optimize",
                "path": ".cursor/skills/skills/agent-orchestration-multi-agent-optimize/SKILL.md",
            },
        ],
        "hooks": [
            {"name": "guard_shell", "path": ".cursor/hooks/guard_shell.py"},
            {"name": "session_start", "path": ".cursor/hooks/session_start.py"},
            {"name": "pre_compact", "path": ".cursor/hooks/pre_compact.py"},
            {"name": "track_edits", "path": ".cursor/hooks/track_edits.py"},
            {"name": "session_stop", "path": ".cursor/hooks/session_stop.py"},
        ],
        "docs": [
            {"name": "evolution_radar", "path": "docs/evolution/RADAR.md"},
            {"name": "evolution_backlog", "path": "docs/evolution/HYPOTHESIS_BACKLOG.md"},
            {"name": "evolution_decisions", "path": "docs/evolution/EVOLUTION_DECISIONS.md"},
            {"name": "research_latest", "path": "docs/evolution/research/LATEST.md"},
            {"name": "migration_plan", "path": "docs/evolution/research/MACRO_MICRO_MIGRATION_PLAN.md"},
            {"name": "self_upgrade_plan", "path": "docs/evolution/research/SELF_UPGRADE_PLAN.md"},
        ],
        "mcps": [
            {"name": "sequential-thinking"},
            {"name": "mcp-reasoner"},
            {"name": "context7"},
            {"name": "postgres"},
            {"name": "memory"},
            {"name": "markitdown"},
            {
                "name": "filesystem",
                "config": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", str(ROOT)],
                },
            },
        ],
    }


def load_self_manifest(path: Path) -> Dict[str, Any]:
    if path.exists():
        return load_json(path)
    return default_self_manifest()


def read_mcp_servers(mcp_config_path: Path) -> Dict[str, Any]:
    if not mcp_config_path.exists():
        return {}
    try:
        data = json.loads(mcp_config_path.read_text(encoding="utf-8"))
        return data.get("mcpServers", {}) or {}
    except Exception:
        return {}


def audit_self_upgrade(manifest: Dict[str, Any], mcp_config_path: Path) -> Dict[str, Any]:
    assets: Dict[str, List[Dict[str, Any]]] = {}
    for kind in ("agents", "rules", "skills", "hooks", "docs"):
        rows: List[Dict[str, Any]] = []
        for item in manifest.get(kind, []):
            path = Path(item.get("path", ""))
            rows.append(
                {
                    "kind": kind,
                    "name": item.get("name", path.stem),
                    "path": str(path),
                    "exists": path.exists(),
                    "auto_create_stub": bool(item.get("auto_create_stub", False)),
                    "install": item.get("install"),
                }
            )
        assets[kind] = rows

    current_mcp = read_mcp_servers(mcp_config_path)
    mcps: List[Dict[str, Any]] = []
    for item in manifest.get("mcps", []):
        name = item.get("name")
        mcps.append(
            {
                "kind": "mcps",
                "name": name,
                "exists": name in current_mcp,
                "config": item.get("config"),
            }
        )
    assets["mcps"] = mcps
    return assets


def create_agent_stub(path: Path, name: str) -> None:
    ensure_dir(path.parent)
    content = (
        "---\n"
        f"name: {name}\n"
        "description: Auto-generated migration execution agent.\n"
        "tools: Read, Grep, Glob, Shell, StrReplace, Write, SemanticSearch\n"
        "---\n\n"
        f"# {name}\n\n"
        "자동 생성된 에이전트 스텁입니다. 실제 실행 프로토콜을 보강하세요.\n"
    )
    path.write_text(content, encoding="utf-8")


def create_rule_stub(path: Path, name: str) -> None:
    ensure_dir(path.parent)
    content = (
        "---\n"
        f"description: Auto-generated rule for {name}\n"
        "alwaysApply: false\n"
        "---\n\n"
        f"# {name}\n\n"
        "자동 생성된 규칙 스텁입니다. 적용 조건과 체크리스트를 보강하세요.\n"
    )
    path.write_text(content, encoding="utf-8")


def apply_self_upgrade_stubs(audit: Dict[str, Any]) -> List[str]:
    created: List[str] = []
    for item in audit.get("agents", []):
        if item.get("exists"):
            continue
        if not item.get("auto_create_stub"):
            continue
        path = Path(item["path"])
        create_agent_stub(path, item.get("name", path.stem))
        created.append(str(path))

    for item in audit.get("rules", []):
        if item.get("exists"):
            continue
        if not item.get("auto_create_stub"):
            continue
        path = Path(item["path"])
        create_rule_stub(path, item.get("name", path.stem))
        created.append(str(path))
    return created


def install_missing_skills(audit: Dict[str, Any]) -> List[Dict[str, str]]:
    installer = Path(os.path.expanduser("~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py"))
    results: List[Dict[str, str]] = []
    if not installer.exists():
        return [{"name": "skill-installer", "status": "missing-installer"}]

    for item in audit.get("skills", []):
        if item.get("exists"):
            continue
        install = item.get("install")
        if not isinstance(install, dict):
            results.append({"name": item.get("name", "unknown"), "status": "no-install-config"})
            continue
        repo = install.get("repo")
        repo_path = install.get("path")
        if not repo or not repo_path:
            results.append({"name": item.get("name", "unknown"), "status": "invalid-install-config"})
            continue
        cmd = [
            sys.executable,
            str(installer),
            "--repo",
            str(repo),
            "--path",
            str(repo_path),
            "--name",
            str(item.get("name", "")),
            "--dest",
            str(ROOT / ".cursor" / "skills" / "skills"),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=180)
            if proc.returncode == 0:
                results.append({"name": item.get("name", "unknown"), "status": "installed"})
            else:
                msg = shorten_error(proc.stderr or proc.stdout or "unknown error")
                results.append({"name": item.get("name", "unknown"), "status": f"failed: {msg}"})
        except Exception as exc:
            results.append({"name": item.get("name", "unknown"), "status": f"error: {type(exc).__name__}"})
    return results


def sync_mcp_servers(audit: Dict[str, Any], manifest: Dict[str, Any], mcp_config_path: Path) -> List[str]:
    if not mcp_config_path.exists():
        return []
    try:
        data = json.loads(mcp_config_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    data.setdefault("mcpServers", {})
    current = data["mcpServers"]
    wanted = {x.get("name"): x for x in manifest.get("mcps", [])}
    added: List[str] = []
    for item in audit.get("mcps", []):
        if item.get("exists"):
            continue
        name = item.get("name")
        cfg = (wanted.get(name) or {}).get("config")
        if not name or not isinstance(cfg, dict):
            continue
        current[name] = cfg
        added.append(name)
    if added:
        mcp_config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def write_self_upgrade_plan(
    output_dir: Path,
    now: datetime,
    audit: Dict[str, Any],
    created_stubs: List[str],
    install_results: List[Dict[str, str]],
    synced_mcp: List[str],
    manifest_path: Path,
    mcp_config_path: Path,
) -> Tuple[Path, Path]:
    ensure_dir(output_dir)
    md_path = output_dir / "SELF_UPGRADE_PLAN.md"
    json_path = output_dir / "self_upgrade_audit.json"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Self Upgrade Plan")
    lines.append("")
    lines.append(f"- Generated at (UTC): {now.isoformat()}")
    lines.append(f"- Manifest: `{manifest_path}`")
    lines.append(f"- MCP Config: `{mcp_config_path}`")
    lines.append("")

    for kind in ("agents", "rules", "skills", "hooks", "docs", "mcps"):
        rows = audit.get(kind, [])
        missing = [x for x in rows if not x.get("exists")]
        lines.append(f"## {kind.capitalize()} Audit")
        lines.append("")
        lines.append(f"- Total: {len(rows)}")
        lines.append(f"- Missing: {len(missing)}")
        for x in missing:
            lines.append(f"  - {x.get('name')} ({x.get('path', x.get('name'))})")
        lines.append("")

    lines.append("## Auto Actions")
    lines.append("")
    lines.append(f"- Created stubs: {len(created_stubs)}")
    for p in created_stubs:
        lines.append(f"  - {p}")
    lines.append(f"- Skill install attempts: {len(install_results)}")
    for row in install_results:
        lines.append(f"  - {row.get('name')}: {row.get('status')}")
    lines.append(f"- Synced MCP servers: {len(synced_mcp)}")
    for name in synced_mcp:
        lines.append(f"  - {name}")
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.append("1. Review missing assets and approve/deny automatic creation.")
    lines.append("2. Convert successful patterns into persistent Rule/Skill/Hook assets.")
    lines.append("3. Re-run weekly research to keep the self-upgrade loop active.")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def dt_to_text(dt: Optional[datetime]) -> str:
    if dt is None:
        return "unknown"
    return dt.strftime("%Y-%m-%d")


def write_report(
    output_dir: Path,
    now: datetime,
    items: List[ResearchItem],
    actions: List[ActionItem],
    failures: Dict[str, str],
    days: int,
) -> Path:
    year_dir = output_dir / "reports" / str(now.year)
    ensure_dir(year_dir)
    iso_week = now.isocalendar().week
    report_path = year_dir / f"{now.date()}-W{iso_week:02d}-coding-research.md"

    success_sources = len({x.source_id for x in items})
    lines: List[str] = []
    lines.append("# Weekly Coding Research Center Report")
    lines.append("")
    lines.append(f"- Generated at (UTC): {now.isoformat()}")
    lines.append(f"- Research window: last {days} days")
    lines.append(f"- Signals collected: {len(items)}")
    lines.append(f"- Action queue size: {len(actions)}")
    lines.append(f"- Sources succeeded: {success_sources}")
    lines.append(f"- Sources failed: {len(failures)}")
    lines.append("")
    lines.append("## Top Signals")
    lines.append("")
    lines.append("| Score | Track | Date | Source | Title | Link |")
    lines.append("|------:|-------|------|--------|-------|------|")
    for item in items[:40]:
        title = item.title.replace("|", "/")
        lines.append(
            f"| {item.score} | {item.primary_track} | {dt_to_text(item.published_at)} | "
            f"{item.source_name} | {title} | {item.link} |"
        )
    lines.append("")
    lines.append("## Apply-Now Queue")
    lines.append("")
    lines.append("| Priority | Action ID | Track | Title | Proposed Change |")
    lines.append("|----------|-----------|-------|-------|-----------------|")
    for action in actions:
        lines.append(
            f"| {action.priority} | {action.action_id} | {action.track} | "
            f"{action.title.replace('|', '/')} | {action.proposed_change.replace('|', '/')} |"
        )
    lines.append("")
    lines.append("## Program Relevance (Current Stack Fit)")
    lines.append("")
    focus_items = [x for x in items if x.focus_score > 0]
    focus_counter: Counter[str] = Counter()
    for item in items[:120]:
        focus_counter.update(item.focus_hits)
    focus_top = ", ".join([f"{k}({v})" for k, v in focus_counter.most_common(8)])
    lines.append(f"- Focus-aligned signals: {len(focus_items)} / {len(items)}")
    lines.append(f"- Top focus keywords: {focus_top if focus_top else 'none'}")
    lines.append("")
    lines.append("| Score | Track | Focus | Title |")
    lines.append("|------:|-------|------:|-------|")
    for item in focus_items[:12]:
        lines.append(
            f"| {item.score} | {item.primary_track} | {item.focus_score} | "
            f"{item.title.replace('|', '/')} |"
        )
    if not focus_items:
        lines.append("| - | - | - | none |")
    lines.append("")
    lines.append("## Deep-Think Notes")
    lines.append("")
    lines.append("- Favor official/release-note based changes over trend-only signals.")
    lines.append("- Do not apply major upgrades without compatibility matrix + rollback rehearsal.")
    lines.append("- Convert repeated wins into reusable rule/skill/hook assets.")
    lines.append("")
    lines.append("## Source Failures")
    lines.append("")
    if failures:
        for source_id, error in failures.items():
            lines.append(f"- `{source_id}`: {error}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append("1. Review top P0/P1 actions.")
    lines.append("2. Select items for this week's implementation sprint.")
    lines.append("3. Open `MACRO_MICRO_MIGRATION_PLAN.md` and execute macro/micro blueprint.")
    lines.append("4. Run smoke/regression tests after each applied action.")
    lines.append("5. Review `SELF_UPGRADE_PLAN.md` for agent/rule/skill/mcp evolution.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    latest_path = output_dir / "LATEST.md"
    latest_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_apply_queue(output_dir: Path, actions: List[ActionItem]) -> Path:
    ensure_dir(output_dir)
    payload = [
        {
            "action_id": a.action_id,
            "priority": a.priority,
            "track": a.track,
            "title": a.title,
            "rationale": a.rationale,
            "proposed_change": a.proposed_change,
            "owner": a.owner,
            "source_links": a.source_links,
        }
        for a in actions
    ]
    out_path = output_dir / "apply_now_queue.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def append_radar_snapshot(radar_path: Path, items: List[ResearchItem], now: datetime) -> None:
    if not radar_path.exists():
        return
    top = items[:10]
    if not top:
        line = (
            f"| {now.date()} | system | No material evolution update | integration | "
            "Low | Low | hold | weekly run produced no signal |"
        )
    else:
        item = top[0]
        signal = f"{item.source_name}: {item.title[:80]}"
        line = (
            f"| {now.date()} | research-center | {signal.replace('|', '/')} | {item.primary_track} | "
            f"{item.confidence} | Medium | open | score={item.score}, link={item.link} |"
        )

    content = radar_path.read_text(encoding="utf-8")
    if top:
        stale_line = (
            f"| {now.date()} | system | No material evolution update | integration | "
            "Low | Low | hold | weekly run produced no signal |"
        )
        if stale_line in content:
            content = content.replace(stale_line, "").rstrip() + "\n"
            radar_path.write_text(content, encoding="utf-8")
            content = radar_path.read_text(encoding="utf-8")
    if line in content:
        return
    with radar_path.open("a", encoding="utf-8") as fp:
        fp.write("\n" + line + "\n")


def append_backlog(backlog_path: Path, actions: List[ActionItem], now: datetime) -> None:
    if not backlog_path.exists() or not actions:
        return
    content = backlog_path.read_text(encoding="utf-8")
    existing_ids = re.findall(r"\|\s*(H-\d+)\s*\|", content)
    max_num = max((int(x.split("-")[1]) for x in existing_ids), default=0)

    candidates = [a for a in actions if a.priority in ("P0", "P1")][:3]
    if not candidates:
        candidates = actions[:1]

    rows: List[str] = []
    for action in candidates:
        title_key = action.title.strip()
        if title_key and title_key in content:
            continue
        max_num += 1
        hid = f"H-{max_num:03d}"
        hypothesis = f"{action.track} 개선: {action.title[:90]} 적용 시 품질/속도 개선"
        row = (
            f"| {hid} | {now.date()} | {hypothesis.replace('|', '/')} | "
            f"4 | 2 | 2 | 4 | evolution-architect | proposed | "
            "리드타임/오류율/회귀건수 |"
        )
        rows.append(row)

    if not rows:
        return

    with backlog_path.open("a", encoding="utf-8") as fp:
        fp.write("\n" + "\n".join(rows) + "\n")


def run(args: argparse.Namespace) -> int:
    config = load_json(Path(args.config))
    tracks = discover_tracks(config)
    sources = load_sources(config, tracks=tracks)
    now = utc_now()
    cutoff = now - timedelta(days=args.days)
    track_keywords = config.get("track_keywords", {})
    program_focus = build_program_focus(config)

    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": "FOMS-Coding-Research-Center/1.0 (+weekly deep research runner)"
        }
    )

    collected: List[ResearchItem] = []
    failures: Dict[str, str] = {}

    for source in sources:
        items, error = fetch_source_items(session, source, args.timeout_sec)
        if error:
            failures[source.source_id] = shorten_error(error)
            continue
        for item in items[: args.max_per_source]:
            if item.published_at is not None and item.published_at < cutoff:
                continue
            collected.append(
                apply_track_scores(
                    item,
                    now=now,
                    track_keywords=track_keywords,
                    tracks=tracks,
                    program_focus=program_focus,
                )
            )

    items = dedupe_items(collected)
    items.sort(key=lambda x: (x.score, x.published_at or datetime(1970, 1, 1, tzinfo=timezone.utc)), reverse=True)

    actions = build_action_queue(items, apply_limit=args.apply_limit, now=now)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)
    report_path = write_report(
        output_dir=output_dir,
        now=now,
        items=items,
        actions=actions,
        failures=failures,
        days=args.days,
    )
    queue_path = write_apply_queue(output_dir=output_dir, actions=actions)

    if args.sync_backlog:
        append_backlog(Path(args.backlog), actions=actions, now=now)
    if args.sync_radar:
        append_radar_snapshot(Path(args.radar), items=items, now=now)

    macro_micro_plan = build_macro_micro_plan(items=items, actions=actions, config=config, now=now)
    macro_plan_md, macro_plan_json = write_macro_micro_plan(output_dir=output_dir, plan=macro_micro_plan)

    manifest_path = Path(args.self_manifest)
    self_manifest = load_self_manifest(manifest_path)
    mcp_config_path = Path(os.path.expanduser(args.mcp_config))
    audit = audit_self_upgrade(self_manifest, mcp_config_path)
    created_stubs: List[str] = []
    if args.self_upgrade_create_stubs:
        created_stubs = apply_self_upgrade_stubs(audit)
        if created_stubs:
            audit = audit_self_upgrade(self_manifest, mcp_config_path)

    install_results: List[Dict[str, str]] = []
    if args.self_upgrade_install_skills:
        install_results = install_missing_skills(audit)
        audit = audit_self_upgrade(self_manifest, mcp_config_path)

    synced_mcp: List[str] = []
    if args.self_upgrade_sync_mcp:
        synced_mcp = sync_mcp_servers(audit, self_manifest, mcp_config_path)
        if synced_mcp:
            audit = audit_self_upgrade(self_manifest, mcp_config_path)

    self_plan_md, self_audit_json = write_self_upgrade_plan(
        output_dir=output_dir,
        now=now,
        audit=audit,
        created_stubs=created_stubs,
        install_results=install_results,
        synced_mcp=synced_mcp,
        manifest_path=manifest_path,
        mcp_config_path=mcp_config_path,
    )

    print(f"[research-center] report={report_path}")
    print(f"[research-center] queue={queue_path}")
    print(f"[research-center] macro_micro_plan={macro_plan_md}")
    print(f"[research-center] macro_micro_plan_json={macro_plan_json}")
    print(f"[research-center] self_upgrade_plan={self_plan_md}")
    print(f"[research-center] self_upgrade_audit={self_audit_json}")
    print(f"[research-center] signals={len(items)} failures={len(failures)}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run weekly coding research center pipeline.")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to source config JSON.")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Directory for research outputs.")
    p.add_argument("--days", type=int, default=9, help="Research lookback window in days.")
    p.add_argument("--max-per-source", type=int, default=25, help="Max collected items per source.")
    p.add_argument("--apply-limit", type=int, default=12, help="Max apply-now actions to generate.")
    p.add_argument("--timeout-sec", type=int, default=20, help="HTTP timeout per source.")
    p.add_argument("--sync-backlog", action="store_true", help="Append top actions into hypothesis backlog.")
    p.add_argument("--sync-radar", action="store_true", help="Append weekly radar snapshot.")
    p.add_argument("--backlog", default=str(DEFAULT_BACKLOG), help="Path to HYPOTHESIS_BACKLOG.md")
    p.add_argument("--radar", default=str(DEFAULT_RADAR), help="Path to RADAR.md")
    p.add_argument("--self-manifest", default=str(DEFAULT_SELF_MANIFEST), help="Path to self-upgrade manifest JSON.")
    p.add_argument(
        "--self-upgrade-create-stubs",
        action="store_true",
        help="Create missing agent/rule stubs when manifest marks them auto-creatable.",
    )
    p.add_argument(
        "--self-upgrade-install-skills",
        action="store_true",
        help="Try installing missing skills using configured install metadata.",
    )
    p.add_argument(
        "--self-upgrade-sync-mcp",
        action="store_true",
        help="Sync missing MCP servers into mcp config when manifest includes full config.",
    )
    p.add_argument("--mcp-config", default=str(DEFAULT_MCP_CONFIG), help="Path to mcp.json")
    return p


if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    raise SystemExit(run(args))
