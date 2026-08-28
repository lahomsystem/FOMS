"""AS 회차 차트(ver7) 뷰 빌더 — 상태 카드 + 회차 아코디언 + 접수 앵커.

sd['shipment']['as_log'](round 스탬프, T15a 규약)를 **(건, 회차) 두 열쇠**로 묶어
ver7 차트가 그대로 렌더할 뷰 dict 를 만든다. 표면 SSOT: AS 대시보드 타임라인 대체 +
지도 카드 인라인 확장이 같은 부품(templates/cs/partials/as_round_chart.html)을 공유.

회차 번호를 정수 하나로만 묶으면 6월 건 1차와 8월 건 1차가 한 통에 들어가 기록이
섞이고, 방문일까지 같은 통에서 꺼내져 지난 건 방문이 새 건 슬롯에 '완료'로 찍힌다
(목업 3-C). 그래서 버킷 키가 ``(cycle_id, round)`` 다. 번호 계산·표시는 이 범위에서
바꾸지 않는다(S3). 건 요약 투영은 ``as_cycle_view`` SSOT 를 그대로 싣는다.

시스템 기록은 스트림에서 제거하고 상태 카드(방문일·가능시간·비용) 이력으로
흡수한다(ver7 확정 — 시스템 회색 강등이 아니라 표면 승격이 해법). 분류는 system
문구 접두어 기준이며, 접두어 SSOT 는 생성 지점(field_update·as_orders)이라
여기 상수와 어긋나면 계약 테스트가 red 다.
"""
from __future__ import annotations

import datetime
from typing import Any, Callable

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


def _entry_cycle(entry: dict) -> str:
    """항목 소속 AS 건(cycle) 표식. 스탬프 전 구항목은 ``''``(= 분류 안 됨).

    **시각으로 추정하지 않는다**(사용자 확정): 표식 없는 옛 기록을 날짜로 어느 건에
    끼워 넣으면 완료 뒤 늦게 달린 기록이 엉뚱한 건으로 들어가고, 화면은 그걸 단정해서
    보여준다. 모르는 것은 ``''`` 로 두고 '예전 기록' 블록에 모은다.
    """
    raw = entry.get("cycle_id")
    return str(raw) if raw else ""


def _absorb_cycle_key(sd: dict) -> str:
    """표식 없는 옛 기록을 귀속시킬 **유일해** 건 표식. 조건 미충족이면 ``''``.

    건이 **정확히 1개**뿐이고 그게 현재 건이면, 표식 없는 기록이 속할 수 있는 건은 그
    하나밖에 없다 — 시각으로 고르는 추정이 아니라 유일해다. 이 보정이 없으면 스탬프 도입
    **이전부터 진행 중이던 AS**(배포 당일 실운영 모집단 전체)가 현재 건 '기록 없음' +
    '예전 기록' 블록으로 쪼개져, 같은 회차 번호가 화면에 두 번 뜬다.

    건이 2개 이상이면 어느 건인지 알 수 없으므로 ``''`` 를 돌려 '예전 기록' 블록에 남긴다
    (완료 뒤 늦게 달린 기록을 엉뚱한 건에 끼워 넣지 않는다 — ``_entry_cycle`` 참조).

    Args:
        sd: 주문 structured_data.

    Returns:
        귀속시킬 ``cycle_id`` 또는 ``''``.
    """
    lifecycle = sd.get("as_lifecycle")
    if not isinstance(lifecycle, dict):
        return ""
    cycles = [c for c in (lifecycle.get("cycles") or []) if isinstance(c, dict)]
    if len(cycles) != 1:
        return ""
    only = str(cycles[0].get("cycle_id") or "")
    return only if only and only == str(lifecycle.get("current_cycle_id") or "") else ""


def _scoped(bucket: dict[tuple[str, int], Any], cycle_key: str | None) -> dict[int, Any]:
    """``(cycle_id, round)`` 버킷에서 한 건 몫만 회차 키로 뽑는다.

    ``cycle_key=None`` 은 건 구분 없이 합치는 **기존 동작 보존 경로**다(건 기록이 아예
    없는 개편 전 주문). 건이 하나라도 있으면 항상 건 단위로 뽑아야 6월 건 1차와 8월 건
    1차가 한 통에 섞이지 않는다.
    """
    if cycle_key is not None:
        return {no: value for (cid, no), value in bucket.items() if cid == cycle_key}
    merged: dict[int, Any] = {}
    for (_cid, no), value in bucket.items():
        if isinstance(value, list):
            merged.setdefault(no, []).extend(value)
        else:
            merged[no] = value
    return merged


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


def _build_rounds(
    *,
    people: dict[int, list[tuple[str, int, dict]]],
    systems: dict[int, list[dict]],
    verdicts: dict[int, dict],
    is_current: bool,
    current_round: int,
    visit_date: str,
    today: datetime.date,
    decorate: Callable[[dict], dict[str, Any]],
) -> list[dict[str, Any]]:
    """한 건 몫의 회차 목록(최신 회차 먼저). 항목 모양은 기존 ``rounds`` 와 동일.

    Args:
        people/systems/verdicts: **그 건으로 이미 좁혀진** 회차별 버킷.
        is_current: 현재 건인가. 현재 건에서만 빈 진행 회차를 채우고 슬롯을 판정한다 —
            종결된 건·분류 안 된 옛 기록에 '다음: 방문' 슬롯을 그리면 거짓말이 된다.
        current_round: ``current_as_round`` 값(번호 규칙은 이번 범위에서 안 바꾼다).
        visit_date: 현재 방문일(flat) — 현재 건 진행 회차 슬롯 판정에만 쓴다.
        today: 기준일(KST). decorate: 항목 표시 dict 변환기.
    """
    # systems 도 회차 출처다. 평탄 목록이던 때는 ``{current}`` 를 무조건 합쳐 회차 1 이
    # 늘 존재했고 시스템 이벤트가 거기 붙었다. 건별로 좁힌 뒤에는 그 보정이 현재 건에만
    # 걸리므로, 사람 기록 없이 시스템 이벤트만 남은 **종결 건**이 회차 0개가 되어 지난 건
    # 블록이 통째로 '이 건 기록 없음'이 된다(접수 원문은 전역 reception 슬롯이 가져간다).
    nos = set(people) | set(verdicts) | set(systems)
    if is_current:
        nos.add(current_round)
    out: list[dict[str, Any]] = []
    for no in sorted(nos, reverse=True):
        verdict = verdicts.get(no)
        entries = _sort_desc(people.get(no, []))
        is_open = is_current and verdict is None
        # 방문일도 **같은 두 열쇠**로 찾는다 — 건 구분 없이 꺼내면 지난 건 방문일이
        # 새 건 슬롯에 done 으로 찍힌다(목업 3-C '터지는 것 2').
        round_visit = _round_visit_date(systems.get(no, []))
        visit_md = _short_md(round_visit)
        out.append({
            "no": no,
            "open": is_open,
            "verdict": _decorated_verdict(verdict) if verdict else None,
            "summary": _round_summary(list(reversed(entries)), visit_md),
            "visit_md": visit_md,
            "slots": _build_slots(
                entries=entries, has_verdict=False, today=today,
                visit_date=_effective_round_visit(round_visit, visit_date, today),
            ) if is_open else [],
            "entries": [decorate(e) for e in entries[:_ROUND_ENTRY_LIMIT]],
            "hidden_count": max(len(entries) - _ROUND_ENTRY_LIMIT, 0),
        })
    return out


def _assign_display_numbers(
    cycle_groups: list[dict[str, Any]], unassigned_rounds: list[dict[str, Any]],
) -> None:
    """회차 dict 에 **표시 전용** 통합 번호(``display_no``)를 붙인다(제자리 변경).

    사용자는 화면의 ``N차`` 를 "이 주문의 몇 번째 AS 처리인가"로 읽는다. 그런데 스탬프
    번호(``as_log[].round`` = ``current_as_round``)는 **한 건 안의 판정 회차**라, 재접수로
    새 건이 열려도 미결 판정이 없으면 그대로 1이다 — 지난 건도 1차, 새 건도 1차로 보인다
    (production #4434 실사례: ``current_cycle_ordinal == 2`` 인데 배지는 ``1차``).
    건 순번과 판정 회차가 같은 단어(``차``)를 쓰는 게 원인이다.

    그래서 **스탬프는 그대로 두고**(``data-round`` 계약·서버 규약 불변) 표시용 번호만
    오래된 건 → 그 건 안의 오래된 회차 순으로 1부터 다시 매긴다. 종결 건 회차에는
    ``closed_cycle`` 을 세워 템플릿이 ``· 종결`` 을 붙일 수 있게 한다.

    Args:
        cycle_groups: ``[현재 건, 종결 건 최신순]`` — 각 그룹의 ``rounds`` 는 최신 회차 먼저.
        unassigned_rounds: 건 표식이 없는 옛 기록 회차. 어느 건인지 모르므로 **번호를
            주지 않고** ``unassigned`` 를 세운다 — 여기에 번호를 붙이면 통합 순번과 나란히
            또 다른 "1차"가 떠서 방금 고친 혼동이 되살아난다(템플릿이 '옛 기록'으로 낸다).
    """
    counter = 0
    # 오래된 건부터(= groups 역순), 건 안에서는 오래된 회차부터(= rounds 역순).
    for group in reversed(cycle_groups):
        closed = not group.get("is_current")
        rounds = group.get("rounds") or []
        for r in reversed(rounds):
            counter += 1
            r["display_no"] = counter
            r["closed_cycle"] = closed
        if not rounds:
            # 기록이 한 줄도 없는 건도 번호 한 칸을 먹는다 — 안 그러면 "접수만 하고 아직
            # 아무것도 안 쓴 건" 뒤에 열린 재접수가 다시 1차로 보인다(사용자 신고 그대로).
            counter += 1
    for r in unassigned_rounds:
        r["closed_cycle"] = False
        r["unassigned"] = True


def _build_cycle_groups(
    sd: dict,
    *,
    buckets: tuple[dict, dict, dict],
    current_round: int,
    visit_date: str,
    today: datetime.date,
    decorate: Callable[[dict], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """건(cycle) 단위 묶음 조립. 반환 ``(cycle_groups, rounds, unassigned_rounds)``.

    현재 건이 맨 앞이고 그다음이 종결 건 최신순이다. 건 요약은 투영 SSOT
    (``as_cycle_view.cycle_summary``)를 그대로 실어 ``history_unknown``(이력 시작 전)
    까지 템플릿이 그릴 수 있게 한다.
    """
    from foms.services.orders.as_cycle_service import current_cycle
    from foms.services.orders.as_cycle_view import closed_cycle_summaries, cycle_summary

    people, systems, verdicts = buckets

    def _rounds(cycle_key: str | None, is_current: bool) -> list[dict[str, Any]]:
        return _build_rounds(
            people=_scoped(people, cycle_key), systems=_scoped(systems, cycle_key),
            verdicts=_scoped(verdicts, cycle_key), is_current=is_current,
            current_round=current_round, visit_date=visit_date, today=today,
            decorate=decorate)

    current = cycle_summary(sd, current_cycle(sd))
    if current is None:
        # 건 기록이 없는 주문: 건 구분 없이 전체를 세던 기존 계산 그대로(회귀 0).
        return [], _rounds(None, True), []
    groups = [{
        "summary": current, "is_current": True,
        "rounds": _rounds(str(current.get("cycle_id") or ""), True),
    }]
    for summary in closed_cycle_summaries(sd):
        groups.append({
            "summary": summary, "is_current": False,
            "rounds": _rounds(str(summary.get("cycle_id") or ""), False),
        })
    unassigned = _rounds("", False)
    # 표시 전용 통합 번호는 그룹이 다 모인 뒤에 매긴다. rounds 객체는 groups[0]["rounds"]
    # 와 **같은 객체**라 제자리 변경이면 최상위 rounds 에도 그대로 보인다.
    _assign_display_numbers(groups, unassigned)
    return groups, groups[0]["rounds"], unassigned


def _current_display_round(rounds: list[dict[str, Any]], fallback: int) -> int:
    """헤드/입력창이 쓸 **표시용 현재 회차**. 진행 중 회차의 ``display_no`` 가 정답이다.

    진행 회차가 없으면(=현재 건이 완결) 마지막으로 매긴 번호, 재번호 자체가 없는
    개편 전 주문이면 스탬프 값(``fallback`` = ``current_as_round``)을 그대로 쓴다.
    """
    open_round = next((r for r in rounds if r.get("open") and r.get("display_no")), None)
    if open_round is not None:
        return int(open_round["display_no"])
    numbers = [r["display_no"] for r in rounds if r.get("display_no")]
    return max(numbers) if numbers else fallback


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
        ``{state_card, symptom_preview, rounds(최신 회차 먼저), cycle_groups,
        unassigned_rounds, reception, legacy, current_round, current_display_round,
        verdict_prompt, count}``.
        rounds 항목은 ``{no, open, verdict, summary, visit_md, slots, entries}``.
        건(cycle)에 속한 회차에는 표시 전용 ``display_no``·``closed_cycle`` 이 더 붙는다
        (``_assign_display_numbers``). ``current_round``/``no`` 는 스탬프 그대로다 —
        ``data-round``·``data-current-round`` 계약이 이 값을 읽는다.

        ``cycle_groups`` = ``[{summary, is_current, rounds}]`` — 현재 건이 맨 앞,
        그다음 종결 건 최신순. ``rounds`` 는 **현재 건 그룹의 rounds** 와 같은 객체다
        (건 기록이 없는 개편 전 주문은 건 구분 없는 기존 전체 계산). ``unassigned_rounds``
        는 ``cycle_id`` 표식이 없는 옛 기록 — 시각으로 추정해 건에 끼워 넣지 않는다.
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
    # 버킷 키 = (cycle_id, round) — 건 표식이 없는 옛 항목은 cycle_id 자리가 ''.
    round_people: dict[tuple[str, int], list[tuple[str, int, dict]]] = {}
    round_systems: dict[tuple[str, int], list[dict]] = {}
    round_verdicts: dict[tuple[str, int], dict] = {}
    human_count = 0

    # 건이 하나뿐인 주문에서는 표식 없는 옛 기록도 그 건 몫이다(_absorb_cycle_key).
    absorb_cycle = _absorb_cycle_key(sd)

    entries = shipment.get("as_log") if isinstance(shipment.get("as_log"), list) else []
    if not entries:
        # as_log 미생성(영구화 전) 주문: as_content 를 읽기 전용 legacy 로 lazy 변환 —
        # 표시 시점 비파괴(build_as_timeline_view 와 같은 계약). 없으면 이전 기록이
        # 차트에서 통째로 사라진다.
        legacy = [_decorate(x) for x in _legacy_entries_from_content(shipment)]
    for idx, e in enumerate(entries):
        if not isinstance(e, dict) or e.get("deleted") is True:
            continue
        key = (_entry_cycle(e) or absorb_cycle, _entry_round(e))
        etype = e.get("type")
        if e.get("legacy") is True:
            legacy.append(_decorate(e))
        elif etype == "system":
            histories[_classify_system_entry(str(e.get("text") or ""))].append(_decorate(e))
            round_systems.setdefault(key, []).append(e)
        elif etype == "reception" and reception is None:
            reception = _decorate(e)
        elif etype == "verdict":
            human_count += 1
            # 같은 회차 재판정(정정)은 마지막 판정이 이긴다 — 이전 판정은 기록 표에 남는다.
            prev = round_verdicts.get(key)
            if prev is not None:
                round_people.setdefault(key, []).append(
                    (prev.get("ts") or "", -1, prev))
            round_verdicts[key] = e
        else:
            human_count += 1
            round_people.setdefault(key, []).append((e.get("ts") or "", idx, e))

    current = current_as_round(sd)
    # 회차 목록: 기록·판정이 있는 회차 ∪ 현재 회차(막 열린 빈 회차 포함)를 **건 안에서만**.
    cycle_groups, rounds, unassigned_rounds = _build_cycle_groups(
        sd, buckets=(round_people, round_systems, round_verdicts),
        current_round=current, visit_date=visit_date, today=today, decorate=_decorate)

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
        "cycle_groups": cycle_groups,
        "unassigned_rounds": unassigned_rounds,
        "reception": reception,
        "legacy": legacy,
        "current_round": current,
        # 화면 표기용 회차 — 스탬프(current_round)와 달리 건을 넘어 이어서 센다.
        "current_display_round": _current_display_round(rounds, current),
        "verdict_prompt": verdict_prompt,
        "count": human_count + (1 if reception else 0) + len(legacy),
    }


__all__ = ["build_as_round_chart_view"]
