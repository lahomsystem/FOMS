"""AS 건(cycle) 읽기 투영 SSOT — 화면 4표면(PC 표·모바일 카드·회차 차트·주문 상세)이 공유.

``as_lifecycle.cycles[]`` 는 지금까지 **화면이 한 곳도 읽지 않았다**. 그 결과 "이번이 몇 번째
AS인지", "지난 건은 언제 끝났고 유상이었는지"가 어디에도 안 보였고, 완료 뒤 재접수가 같은 건
되살리기(reopen)와 구분되지 않았다. 이 모듈은 그 투영을 **한 곳**에 모은다 — 표면마다 따로
세면 화면끼리 숫자가 어긋난다(네이버 집 세기 사고와 같은 구조).

규약:

* **순번(ordinal)은 1부터**, ``cycles[]`` 등장 순서다(append-only 라 순서가 곧 시간순).
  1번째 건은 화면에서 배지를 **안 붙인다**(소음 방지) — 판단은 호출자가 ``ordinal > 1`` 로 한다.
* **지난 건 값은 cycle 봉인분만** 읽는다(``completed_date``/``billing_snapshot``). flat 컬럼
  (``order.as_completed_date``)은 다음 건이 열리면 지워지므로 지난 건 근거가 될 수 없다.
* **LEGACY_BRIDGE 건은 이력 불명**이다(``origin``). 접수일이 실제 접수가 아니라 브리지 실행
  시각이라 그대로 표시하면 화면이 거짓말을 한다 — ``history_unknown`` 으로 표시만 하고
  날짜는 내보내지 않는다.
* 표시 시점 **비파괴** — sd 를 변경하지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from foms.services.orders.as_cycle_service import (
    AS_COMPLETED,
    LEGACY_BRIDGE_ORIGIN,
    cycle_status,
)


def _cycles(sd: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """``as_lifecycle.cycles`` 를 dict 리스트로 정규화해 돌려준다(없으면 빈 리스트)."""
    lifecycle = (sd or {}).get("as_lifecycle")
    if not isinstance(lifecycle, dict):
        return []
    cycles = lifecycle.get("cycles")
    if not isinstance(cycles, list):
        return []
    return [c for c in cycles if isinstance(c, dict)]


def cycle_ordinal(sd: Optional[Dict[str, Any]], cycle_id: Optional[str]) -> int:
    """``cycle_id`` 의 1-기반 순번. 못 찾으면 0.

    Args:
        sd: 주문 structured_data. cycle_id: 대상 건 id.

    Returns:
        1 이상 순번, 없으면 0.
    """
    if not cycle_id:
        return 0
    for idx, cycle in enumerate(_cycles(sd), start=1):
        if str(cycle.get("cycle_id") or "") == str(cycle_id):
            return idx
    return 0


def current_cycle_ordinal(sd: Optional[Dict[str, Any]]) -> int:
    """현재 건의 순번(건이 없으면 0). 1번째 건이면 1."""
    lifecycle = (sd or {}).get("as_lifecycle")
    if not isinstance(lifecycle, dict):
        return 0
    return cycle_ordinal(sd, lifecycle.get("current_cycle_id"))


def is_history_unknown(cycle: Optional[Dict[str, Any]]) -> bool:
    """레거시 전환으로 열린 건인가(= 접수일·과거 이력을 신뢰할 수 없다)."""
    return isinstance(cycle, dict) and cycle.get("origin") == LEGACY_BRIDGE_ORIGIN


def _billing_text(cycle: Dict[str, Any]) -> str:
    """봉인된 비용 스냅샷의 표시 문구(봉인 없으면 빈 문자열)."""
    snapshot = cycle.get("billing_snapshot")
    if not isinstance(snapshot, dict):
        return ""
    from foms.services.as_dashboard_display import as_billing_state_text

    return as_billing_state_text(snapshot)


def cycle_summary(sd: Optional[Dict[str, Any]], cycle: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """한 건의 화면용 요약(순번·상태·접수일·완료일·비용·재발·이력불명).

    Args:
        sd: 주문 structured_data. cycle: 대상 cycle dict.

    Returns:
        요약 dict 또는 None(cycle 없음). ``history_unknown`` 이면 ``received_date`` 는 빈 값이다.
    """
    if not isinstance(cycle, dict):
        return None
    unknown = is_history_unknown(cycle)
    return {
        "cycle_id": cycle.get("cycle_id"),
        "ordinal": cycle_ordinal(sd, cycle.get("cycle_id")),
        "status": cycle_status(cycle),
        "received_date": "" if unknown else str(cycle.get("received_date") or ""),
        "completed_date": str(cycle.get("completed_date") or ""),
        "billing_text": _billing_text(cycle),
        "recurrence": bool(cycle.get("recurrence")),
        "history_unknown": unknown,
    }


# 지난 건 '증상' 한 줄의 표시 상한(문자). 원문은 회차 차트 접수 줄이 정본이라 여기서는
# 전화 응대용 발췌만 낸다 — 길면 모달 요약이 통째로 스크롤 덩어리가 된다.
_SYMPTOM_EXCERPT_MAX = 80


def _find_cycle(sd: Optional[Dict[str, Any]], cycle_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """``cycle_id`` 의 원본 cycle dict(못 찾으면 None)."""
    if not cycle_id:
        return None
    for cycle in _cycles(sd):
        if str(cycle.get("cycle_id") or "") == str(cycle_id):
            return cycle
    return None


def cycle_symptom_text(cycle: Optional[Dict[str, Any]]) -> str:
    """그 건 접수 원문(``initial_content``)의 plain-text 발췌(없으면 빈 문자열).

    ``initial_content`` 는 저장 시점에 sanitize 된 rich HTML 이라 그대로 textContent 로
    넣으면 태그가 글자로 보인다. 표시 전에 텍스트로 풀고 공백을 정규화한 뒤 자른다.

    Args:
        cycle: 대상 cycle dict.

    Returns:
        한 줄 발췌(상한 초과분은 '…'). 내용이 없으면 빈 문자열.
    """
    raw = str((cycle or {}).get("initial_content") or "").strip()
    if not raw:
        return ""
    from foms.services.as_content_safety import as_content_html_to_text

    text = " ".join(as_content_html_to_text(raw, already_sanitized=True).split())
    if not text:
        return ""
    return text if len(text) <= _SYMPTOM_EXCERPT_MAX else text[:_SYMPTOM_EXCERPT_MAX] + "…"


def cycle_max_round(sd: Optional[Dict[str, Any]], cycle_id: Optional[str]) -> int:
    """그 건에 속한 as_log 항목의 **최대 회차**(스탬프가 없으면 0).

    회차는 저장 카운터가 아니라 as_log 파생값이고(as_log.current_as_round), 항목은 소속
    건이 정해질 때만 ``cycle_id`` 로 스탬프된다. 건 표식이 생기기 전 기록에는 스탬프가
    없으므로 0 을 돌려준다 — 화면은 그 줄을 통째로 숨겨야 한다(추정 금지).

    Args:
        sd: 주문 structured_data. cycle_id: 대상 건 id.

    Returns:
        1 이상 최대 회차, 근거가 없으면 0.
    """
    if not cycle_id:
        return 0
    entries = ((sd or {}).get("shipment") or {}).get("as_log")
    if not isinstance(entries, list):
        return 0
    best = 0
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("deleted") is True:
            continue
        if str(entry.get("cycle_id") or "") != str(cycle_id):
            continue
        raw = entry.get("round")
        if isinstance(raw, int) and raw > best:
            best = raw
    return best


def with_cycle_detail_extras(
    sd: Optional[Dict[str, Any]], summary: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """요약 dict 에 주문 상세 전용 키를 **가산**한다(기존 키는 그대로 둔다).

    대시보드 행 투영(:func:`project_as_cycle_row`)에는 붙이지 않는다 — 증상 발췌가
    행마다 HTML 파싱을 한 번씩 더 돌려 100행 목록의 hot path 를 무겁게 만든다.

    Args:
        sd: 주문 structured_data. summary: :func:`cycle_summary` 결과(None 허용).

    Returns:
        ``symptom_text``·``max_round`` 가 더해진 사본(summary 가 None 이면 None).
    """
    if not summary:
        return summary
    cycle_id = summary.get("cycle_id")
    enriched = dict(summary)
    enriched["symptom_text"] = cycle_symptom_text(_find_cycle(sd, cycle_id))
    enriched["max_round"] = cycle_max_round(sd, cycle_id)
    return enriched


def previous_cycle_summary(sd: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """현재 건 **직전**의 종결된 건 요약(없으면 None).

    현재 건이 없으면(=AS 이력만 있고 지금은 닫힘) 마지막 건을 직전으로 본다.
    """
    cycles = _cycles(sd)
    if not cycles:
        return None
    lifecycle = (sd or {}).get("as_lifecycle") or {}
    current_id = str(lifecycle.get("current_cycle_id") or "")
    if not current_id:
        return cycle_summary(sd, cycles[-1])
    for idx, cycle in enumerate(cycles):
        if str(cycle.get("cycle_id") or "") == current_id:
            return cycle_summary(sd, cycles[idx - 1]) if idx > 0 else None
    return None


def last_closed_cycle_summary(sd: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """가장 최근 **종결된** 건 요약 — 재접수 모달 '지난 건' 정본(없으면 None).

    ``previous_cycle_summary`` 는 '현재 건의 하나 앞'이라 **완료 직후에는 한 칸 어긋난다**:
    1번째 건이 완료된 주문은 ``current_cycle_id`` 가 그 건을 계속 가리키므로 직전 건이
    없어(None) 지난 건 요약이 통째로 사라진다 — 완료 뒤 재접수의 가장 흔한 경우다
    (``current_cycle_id`` 는 완료 시 비워지지 않는다, as_cycle_service:274·422).
    그래서 현재 건이 COMPLETED 면 **그 건 자신**이 지난 건이다.

    Args:
        sd: 주문 structured_data.

    Returns:
        :func:`cycle_summary` shape 또는 None.
    """
    lifecycle = (sd or {}).get("as_lifecycle")
    if isinstance(lifecycle, dict):
        current_id = str(lifecycle.get("current_cycle_id") or "")
        current = next(
            (c for c in _cycles(sd) if str(c.get("cycle_id") or "") == current_id),
            None,
        )
        if current is not None and cycle_status(current) == AS_COMPLETED:
            return cycle_summary(sd, current)
    return previous_cycle_summary(sd)


def project_as_cycle_row(sd: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """대시보드 행/카드가 쓰는 건 표식 묶음.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``{as_cycle_no, as_cycle_status, as_recurrence, as_history_unknown, as_prev_cycle}``.
        ``as_cycle_no`` 는 1 이면 화면에 배지를 붙이지 않는 규약이다(0=건 없음).
    """
    lifecycle = (sd or {}).get("as_lifecycle")
    current = None
    if isinstance(lifecycle, dict):
        current_id = lifecycle.get("current_cycle_id")
        current = next(
            (c for c in _cycles(sd) if str(c.get("cycle_id") or "") == str(current_id or "")),
            None,
        )
    return {
        "as_cycle_no": current_cycle_ordinal(sd),
        "as_cycle_status": cycle_status(current) if current else "NONE",
        "as_recurrence": bool((current or {}).get("recurrence")),
        "as_history_unknown": is_history_unknown(current),
        "as_prev_cycle": previous_cycle_summary(sd),
    }


def as_cycle_detail_payload(sd: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """주문 상세(ERP) payload 의 ``as_cycle`` 블록 — 재접수 모달 제목·지난 건 요약용.

    행 투영(:func:`project_as_cycle_row`)과 **같은 계산**을 키 이름만 상세 payload 규약
    (``as_`` 접두어 없음)으로 옮긴다. 두 payload 생성 지점(부트스트랩 인라인 JSON·
    ``GET /structured``)이 같은 shape 여야 첫 페인트와 새로고침 후 모달이 갈리지 않는다.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``{cycle_no, cycle_status, recurrence, history_unknown, prev_cycle,
        last_closed_cycle}``. 재접수 모달의 '지난 건' 블록은 ``prev_cycle`` 이 아니라
        ``last_closed_cycle`` 을 읽어야 한다(완료 직후 한 칸 어긋남 — 그 함수 docstring).
        두 건 요약에는 상세 전용 키(``symptom_text``·``max_round``)가 **더해져** 나온다
        (:func:`with_cycle_detail_extras` — 목업 4-C 의 '증상'·'처리' 줄).
    """
    row = project_as_cycle_row(sd)
    return {
        "cycle_no": row["as_cycle_no"],
        "cycle_status": row["as_cycle_status"],
        "recurrence": row["as_recurrence"],
        "history_unknown": row["as_history_unknown"],
        "prev_cycle": with_cycle_detail_extras(sd, row["as_prev_cycle"]),
        "last_closed_cycle": with_cycle_detail_extras(sd, last_closed_cycle_summary(sd)),
    }


def closed_cycle_summaries(sd: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """종결된(현재 건이 아닌) 건 요약 목록 — 최신 건이 앞이다(차트 지난 건 블록용)."""
    lifecycle = (sd or {}).get("as_lifecycle") or {}
    current_id = str(lifecycle.get("current_cycle_id") or "")
    out: List[Dict[str, Any]] = []
    for cycle in _cycles(sd):
        if str(cycle.get("cycle_id") or "") == current_id:
            continue
        summary = cycle_summary(sd, cycle)
        if summary:
            out.append(summary)
    out.reverse()
    return out


__all__ = [
    "AS_COMPLETED",
    "cycle_ordinal",
    "current_cycle_ordinal",
    "is_history_unknown",
    "cycle_summary",
    "cycle_symptom_text",
    "cycle_max_round",
    "with_cycle_detail_extras",
    "previous_cycle_summary",
    "last_closed_cycle_summary",
    "project_as_cycle_row",
    "as_cycle_detail_payload",
    "closed_cycle_summaries",
]
