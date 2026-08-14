"""AS 회차 차트(ver7) 뷰 빌더 — 상태 카드 + 회차 아코디언 + 접수 앵커.

sd['shipment']['as_log'](round 스탬프, T15a 규약)를 회차별로 묶어 ver7 차트가
그대로 렌더할 뷰 dict 를 만든다. 표면 SSOT: AS 대시보드 타임라인 대체 + 지도
카드 인라인 확장이 같은 부품(templates/cs/partials/as_round_chart.html)을 공유.

시스템 기록은 스트림에서 제거하고 상태 카드(방문일·가능시간·비용) 이력으로
흡수한다(ver7 확정 — 시스템 회색 강등이 아니라 표면 승격이 해법). 분류는 system
문구 접두어 기준이며, 접두어 SSOT 는 생성 지점(field_update·as_orders)이라
여기 상수와 어긋나면 계약 테스트가 red 다.
"""
from __future__ import annotations

import datetime
from typing import Any

from foms.services.as_content_safety import as_content_html_to_text
from foms.services.orders.as_availability import as_availability_label
from foms.services.orders.as_log import (
    _legacy_entries_from_content,
    current_as_round,
    decorate_entry,
)

# system 문구 접두어 → 상태 카드 필드 분류. 생성 지점 리터럴과 동일해야 한다
# (tests/domains/test_as_round_chart.py 가 원본 소스에 핀).
_VISIT_PREFIXES = ("방문일 확정:", "방문일 취소")
_AVAILABILITY_PREFIXES = ("가능시간:", "가능시간 초기화")
_BILLING_MARKERS = ("무상 확정", "유상 확정", "미정 처리", "전환")

# 진행 회차 슬롯 순서(ver7/v6 확정): 방안→자재→일정→컨택→방문→판정.
_SLOT_DEFS = (
    ("plan", "방안"), ("material", "자재"), ("schedule", "일정"),
    ("contact", "컨택"), ("visit", "방문"), ("verdict", "판정"),
)

_PREVIEW_MAX = 60
_SUMMARY_MAX = 25
# 회차당 기록 표 상한. as_log 는 append-only + 항목당 10,000자라 상한이 없으면 오래된
# 주문 하나가 수 MB fragment 가 된다(구 타임라인 '더보기' 200 캡의 회차판 등가).
_ROUND_ENTRY_LIMIT = 60


def _preview_text(raw: Any, *, limit: int = _PREVIEW_MAX) -> str:
    """sanitize 완료 HTML → 개행 접은 1줄 plain text, limit 초과는 말줄임."""
    text = as_content_html_to_text(raw, already_sanitized=True).replace("\n", " ").strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def _classify_system_entry(text: str) -> str:
    """system 문구를 상태 카드 필드로 분류. 방문일/가능시간/비용 외는 'other'."""
    stripped = (text or "").strip()
    if stripped.startswith(_VISIT_PREFIXES):
        return "visit"
    if stripped.startswith(_AVAILABILITY_PREFIXES):
        return "availability"
    if any(marker in stripped for marker in _BILLING_MARKERS):
        return "billing"
    return "other"


def _parse_iso_date(value: Any) -> datetime.date | None:
    """앞 10자를 YYYY-MM-DD 로 관대 파싱. 실패/빈 값은 None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def _short_md(value: Any) -> str:
    """'YYYY-MM-DD' → 'M/D'(0 패딩 없음). 파싱 실패면 빈 문자열."""
    parsed = _parse_iso_date(value)
    return f"{parsed.month}/{parsed.day}" if parsed else ""


def _dday_fields(visit_date: Any, today: datetime.date) -> dict[str, Any]:
    """방문일 D-day 파생(dday·label·overdue). 미설정이면 전부 공값."""
    visit = _parse_iso_date(visit_date)
    if visit is None:
        return {"dday": None, "dday_label": "", "overdue": False}
    dday = (visit - today).days
    if dday < 0:
        label = f"{-dday}일 지남"  # 지난 방문일 = 빨강(사용자 확정 문구)
    elif dday == 0:
        label = "오늘"
    else:
        label = f"D-{dday}"
    return {"dday": dday, "dday_label": label, "overdue": dday < 0}


def _entry_round(entry: dict) -> int:
    """항목 소속 회차. round 없는 구항목은 1회차(T15a 규약과 동일)."""
    raw = entry.get("round")
    return raw if isinstance(raw, int) and raw >= 1 else 1


def _round_visit_date(round_systems: list[dict]) -> str:
    """그 회차의 마지막 '방문일 확정' system 문구에서 방문일(ISO)을 뽑는다. 없으면 ''."""
    for e in reversed(round_systems):
        text = str(e.get("text") or "").strip()
        if text.startswith("방문일 확정:"):
            return text.split(":", 1)[1].strip()
    return ""


def _effective_round_visit(
    round_visit: str, current_visit: str, today: datetime.date,
) -> str:
    """진행 회차 슬롯 판정용 방문일 — 그 회차에 확정된 날짜 우선.

    회차에 확정 로그가 없는데 현재 방문일이 이미 지났다면 그 날짜는 **이전 회차의
    방문**이다(미결 후 새 회차가 자동으로 '방문 완료'로 보이는 오판 방지). 미래/오늘
    날짜는 현재 회차 몫으로 인정한다(pre-T15 구기록은 전부 1회차라 회차 로그로 잡힌다).
    """
    if round_visit:
        return round_visit
    parsed = _parse_iso_date(current_visit)
    if parsed is not None and parsed >= today:
        return current_visit
    return ""


def _round_summary(entries: list[dict], visit_md: str) -> str:
    """접힌 회차 1줄 요약: '방안: <첫 방안 25자>'(없으면 첫 기록) + ' → 방문 M/D'."""
    plan = next((e for e in entries if e.get("type") == "plan"), None)
    base = plan or (entries[0] if entries else None)
    parts: list[str] = []
    if base is not None:
        prefix = "방안: " if base.get("type") == "plan" else ""
        parts.append(prefix + _preview_text(base.get("text"), limit=_SUMMARY_MAX))
    if visit_md:
        parts.append(f"방문 {visit_md}")
    return " → ".join(parts)


def _build_slots(
    *, entries: list[dict], has_verdict: bool, visit_date: Any, today: datetime.date,
) -> list[dict[str, str]]:
    """진행 회차 슬롯 칩 상태(done/next/wait) — 첫 미완 슬롯이 next 다.

    일정=현재 방문일 존재, 방문=방문일 경과(당일 포함), 판정=verdict 존재.
    방안/자재/컨택은 그 회차 사람 기록 유형 존재 여부.
    """
    types = {e.get("type") for e in entries}
    visit = _parse_iso_date(visit_date)
    done = {
        "plan": "plan" in types,
        "material": "material" in types,
        "schedule": visit is not None,
        "contact": "call" in types,
        "visit": visit is not None and visit <= today,
        "verdict": has_verdict,
    }
    slots: list[dict[str, str]] = []
    next_taken = False
    for key, label in _SLOT_DEFS:
        if done[key]:
            state = "done"
        elif not next_taken:
            state, next_taken = "next", True
        else:
            state = "wait"
        slots.append({"key": key, "label": label, "state": state})
    return slots


def _decorated_verdict(entry: dict) -> dict[str, Any]:
    """회차 verdict 표시 dict(decorate 파생 포함) — 템플릿이 그대로 배치."""
    d = decorate_entry(entry)
    d["reason_preview"] = _preview_text(entry.get("text"), limit=_SUMMARY_MAX)
    return d


def _sort_desc(entries: list[tuple[str, int, dict]]) -> list[dict]:
    """(ts, idx) 역순 정렬 — ts 동률은 삽입 역순(타임라인 뷰와 동일 tie-break)."""
    return [e for _, _, e in sorted(entries, key=lambda t: (t[0], t[1]), reverse=True)]


def build_as_round_chart_view(
    sd: dict | None,
    *,
    today: datetime.date | None = None,
    attachments_by_log_id: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """ver7 회차 차트 뷰 조립(표시 시점 비파괴 — sd 를 변경하지 않는다).

    Args:
        sd: 주문 structured_data (None 허용).
        today: 기준일(KST date). 미지정이면 get_today_kst().
        attachments_by_log_id: as_log 항목 id → 첨부 표시 dict 목록(AS-FRESH-01 T4).
            호출 라우트가 **1쿼리로 묶어** 주입한다 — 여기서 조회하면 항목마다 쿼리가
            도는 N+1 이 된다. 미주입이면 기록 줄에 썸네일이 붙지 않는다.

    Returns:
        ``{state_card, symptom_preview, rounds(최신 회차 먼저), reception, legacy,
        current_round, verdict_prompt, count}``. rounds 항목은
        ``{no, open, verdict, summary, visit_md, slots, entries}``.
    """
    from foms.services.as_dashboard_display import as_billing_badge_kind, as_billing_state_text
    from foms.services.erp_display import get_today_kst

    today = today or get_today_kst()
    sd = sd if isinstance(sd, dict) else {}
    files_map = attachments_by_log_id if isinstance(attachments_by_log_id, dict) else {}

    def _decorate(entry: dict) -> dict[str, Any]:
        """decorate_entry + 그 기록에 결합된 첨부(files)."""
        out = decorate_entry(entry)
        files = files_map.get(str(entry.get("id") or ""))
        if files:
            out["files"] = list(files)
        return out

    shipment = sd.get("shipment") or {}
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    as_visit = schedule.get("as_visit") if isinstance(schedule.get("as_visit"), dict) else {}
    visit_date = str(as_visit.get("date") or "").strip() or str(
        shipment.get("as_visit_date") or "").strip()

    reception: dict | None = None
    legacy: list[dict] = []
    histories: dict[str, list[dict]] = {
        "visit": [], "availability": [], "billing": [], "other": []}
    round_people: dict[int, list[tuple[str, int, dict]]] = {}
    round_systems: dict[int, list[dict]] = {}
    round_verdicts: dict[int, dict] = {}
    human_count = 0

    entries = shipment.get("as_log") if isinstance(shipment.get("as_log"), list) else []
    if not entries:
        # as_log 미생성(영구화 전) 주문: as_content 를 읽기 전용 legacy 로 lazy 변환 —
        # 표시 시점 비파괴(build_as_timeline_view 와 같은 계약). 없으면 이전 기록이
        # 차트에서 통째로 사라진다.
        legacy = [_decorate(x) for x in _legacy_entries_from_content(shipment)]
    for idx, e in enumerate(entries):
        if not isinstance(e, dict) or e.get("deleted") is True:
            continue
        no = _entry_round(e)
        etype = e.get("type")
        if e.get("legacy") is True:
            legacy.append(_decorate(e))
        elif etype == "system":
            histories[_classify_system_entry(str(e.get("text") or ""))].append(_decorate(e))
            round_systems.setdefault(no, []).append(e)
        elif etype == "reception" and reception is None:
            reception = _decorate(e)
        elif etype == "verdict":
            human_count += 1
            # 같은 회차 재판정(정정)은 마지막 판정이 이긴다 — 이전 판정은 기록 표에 남는다.
            prev = round_verdicts.get(no)
            if prev is not None:
                round_people.setdefault(no, []).append(
                    (prev.get("ts") or "", -1, prev))
            round_verdicts[no] = e
        else:
            human_count += 1
            round_people.setdefault(no, []).append((e.get("ts") or "", idx, e))

    current = current_as_round(sd)
    # 회차 목록: 기록·판정이 있는 회차 ∪ 현재 회차(막 열린 빈 회차 포함).
    round_nos = sorted(set(round_people) | set(round_verdicts) | {current}, reverse=True)
    rounds: list[dict[str, Any]] = []
    for no in round_nos:
        verdict = round_verdicts.get(no)
        people = _sort_desc(round_people.get(no, []))
        is_open = verdict is None
        round_visit = _round_visit_date(round_systems.get(no, []))
        visit_md = _short_md(round_visit)
        rounds.append({
            "no": no,
            "open": is_open,
            "verdict": _decorated_verdict(verdict) if verdict else None,
            "summary": _round_summary(list(reversed(people)), visit_md),
            "visit_md": visit_md,
            "slots": _build_slots(
                entries=people, has_verdict=False, today=today,
                visit_date=_effective_round_visit(round_visit, visit_date, today),
            ) if is_open else [],
            "entries": [_decorate(e) for e in people[:_ROUND_ENTRY_LIMIT]],
            "hidden_count": max(len(people) - _ROUND_ENTRY_LIMIT, 0),
        })

    open_round = next((r for r in rounds if r["open"]), None)
    verdict_prompt = bool(open_round) and any(
        s["key"] == "visit" and s["state"] == "done" for s in open_round["slots"])

    billing = shipment.get("as_billing")
    availability = as_visit.get("availability")
    availability = availability if isinstance(availability, dict) and availability else None
    symptom = _preview_text(shipment.get("as_content")) or (
        _preview_text(reception.get("text")) if reception else "")
    return {
        "state_card": {
            "visit": {
                "date": visit_date, "md": _short_md(visit_date),
                "time": str(as_visit.get("time") or "").strip(),
                "history": histories["visit"], **_dday_fields(visit_date, today),
            },
            "availability": {
                "label": as_availability_label(availability),
                "note": str((availability or {}).get("note") or "").strip(),
                # 편집 칩(erp-as-avail-chip)의 data-avail-* 프리필용 raw 값 —
                # 팝오버는 목록 칩과 같은 as-dashboard.js 위임을 그대로 탄다.
                "days": str((availability or {}).get("days") or "").strip(),
                "time": str((availability or {}).get("time") or "").strip(),
                "history": histories["availability"],
            },
            "billing": {
                "kind": as_billing_badge_kind(billing),
                "state_text": as_billing_state_text(billing),
                "history": histories["billing"],
            },
            "other_history": histories["other"],
        },
        "symptom_preview": symptom,
        "rounds": rounds,
        "reception": reception,
        "legacy": legacy,
        "current_round": current,
        "verdict_prompt": verdict_prompt,
        "count": human_count + (1 if reception else 0) + len(legacy),
    }


__all__ = ["build_as_round_chart_view"]
