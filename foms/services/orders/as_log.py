"""AS 타임라인 로그(as_log) 도메인 서비스.

sd['shipment']['as_log'] append-only 리스트의 생성·정규화·lazy 마이그레이션과
렌더용 뷰(앵커+스트림) 구성을 담당한다. API 라우트가 비대해지지 않도록 분리.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from markupsafe import escape

from foms.services.as_content_safety import sanitize_as_content_html
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive, parse_datetime_utc

AS_LOG_TYPES = frozenset({
    "reception", "call", "action", "material", "schedule", "memo", "system",
    "plan", "verdict",
})
# T15 회차 개편으로 입력이 퇴역한 유형. _TYPE_LABELS 는 남긴다 — 기존 기록의 배지는
# 계속 렌더돼야 한다. 조용히 memo 로 강등하면 구 클라이언트 입력이 무경고로 유형을
# 잃으므로 coerce 가 명시적으로 거부한다(라우트에서 400).
_RETIRED_CLIENT_TYPES = frozenset({"action", "schedule"})
_CLIENT_TYPES = AS_LOG_TYPES - {"system", "verdict"} - _RETIRED_CLIENT_TYPES
_DEFAULT_TYPE = "memo"
# 회차 판정 값. 미결(unresolved) 판정 1건 = 다음 회차 개시(round+1 규약).
AS_VERDICT_RESOLVED = "resolved"
AS_VERDICT_UNRESOLVED = "unresolved"
_AS_VERDICTS = frozenset({AS_VERDICT_RESOLVED, AS_VERDICT_UNRESOLVED})
AS_VERDICT_LABELS = {AS_VERDICT_RESOLVED: "완결", AS_VERDICT_UNRESOLVED: "미결"}
# 항목 본문 상한(문자). **생성 지점 봉인** — 클라 경로는 라우트가 400으로 거르지만, system
# 문구는 사유·날짜 같은 무검증 입력을 서버가 조립하므로 여기서 자르지 않으면 append-only
# JSONB 가 요청 한 번에 부풀 수 있다. 상한 근처에서 escape 엔티티가 잘릴 수는 있으나
# (표시상 `&l` 같은 잔여) escape 는 이미 끝난 뒤라 주입 경로가 되지는 않는다.
AS_LOG_TEXT_MAX = 10000
_TYPE_LABELS = {
    "reception": "접수", "call": "통화", "action": "방문/조치",
    "material": "자재", "schedule": "일정", "memo": "메모", "system": "시스템",
    "plan": "방안", "verdict": "판정",
}


def new_as_log_id() -> str:
    """`al_<epoch_ms>_<rand4>` 형식의 항목 id."""
    return f"al_{int(time.time() * 1000)}_{secrets.token_hex(2)}"


def coerce_client_log_type(raw: Any) -> str:
    """클라이언트 유형을 허용 enum으로 정규화.

    'system'·'verdict'·퇴역 유형(action/schedule)은 거부(ValueError → 라우트 400),
    그 외 미허용 값은 memo 로 폴백한다. 판정(verdict)은 회차 전진(round+1)의 근거라
    quick-add 로 끼어들면 안 되고, 퇴역 유형은 조용한 memo 강등 대신 명시 거부한다.
    """
    value = str(raw or "").strip().lower()
    if value == "system":
        raise ValueError("system 유형은 서버만 생성할 수 있습니다.")
    if value == "verdict":
        raise ValueError("판정 기록은 회차 판정으로만 남길 수 있습니다.")
    if value in _RETIRED_CLIENT_TYPES:
        raise ValueError("방문/조치·일정 유형은 더 이상 입력할 수 없습니다.")
    return value if value in _CLIENT_TYPES else _DEFAULT_TYPE


def build_as_log_entry(
    *, log_type: str, text: str, by: str, by_id: int | None, round_no: int = 1
) -> dict[str, Any]:
    """as_log 항목 dict 생성. ts는 UTC naive ISO, 본문은 AS_LOG_TEXT_MAX 로 절단.

    Args:
        log_type: AS_LOG_TYPES 중 하나. text: 본문(호출자가 sanitize 완료).
        by/by_id: 작성자 표기·id. round_no: 소속 회차(1 시작 — round 없는 구항목은
            읽기 시점에 1로 간주하므로 기본값도 1).

    Returns:
        as_log 에 append 가능한 항목 dict.
    """
    return {
        "id": new_as_log_id(),
        "ts": now_utc_naive().isoformat(),
        "by": by or "",
        "by_id": by_id,
        "type": log_type,
        "text": (text or "")[:AS_LOG_TEXT_MAX],
        "round": round_no,
        "edited_at": None,
        "edited_by": None,
    }


def _legacy_entries_from_content(
    shipment: dict,
    sanitized: tuple[str | None, str | None] | None = None,
) -> list[dict]:
    """as_content/as_content_2를 읽기전용 legacy memo 항목으로 변환.

    id는 원본 필드에서 파생한 결정적 상수다. 렌더마다 재생성하면 같은 항목이
    매번 다른 id를 갖게 되어 DOM 키·중복 제거가 어긋나고, 영구화(migrate) 전후로
    id가 바뀌어 불연속이 생긴다. migrate도 이 헬퍼를 경유하므로 id가 그대로 이어진다.

    Args:
        shipment: sd['shipment'] dict.
        sanitized: 호출자가 이미 정리한 ``(as_content, as_content_2)`` HTML. 주입하면
            재-sanitize를 생략한다 — AS 대시보드 행 루프는 같은 두 값을 바로 뒤에서
            또 sanitize하므로 행마다 BeautifulSoup 파싱이 2배로 들던 중복을 없앤다.
            영구화(migrate) 경로는 주입 없이 shipment를 정본으로 읽는다.

    Returns:
        legacy memo 항목 리스트(내용이 없으면 빈 리스트).
    """
    out: list[dict] = []
    fields = (("as_content", "이전 기록"), ("as_content_2", "이전 기록(탭2)"))
    for idx, (field, label) in enumerate(fields):
        if sanitized is not None:
            html = sanitized[idx]
        else:
            html = sanitize_as_content_html(shipment.get(field))
        if not html:
            continue
        out.append({
            "id": f"al_legacy_{field}",
            "ts": None,
            "by": "",
            "by_id": None,
            "type": "memo",
            "text": html,
            "legacy": True,
            "legacy_label": label,
            "edited_at": None,
            "edited_by": None,
        })
    return out


def migrate_legacy_into_log(sd: dict) -> bool:
    """as_log가 비어있고 as_content가 있으면 legacy 항목으로 시드. 시드했으면 True."""
    shipment = sd.setdefault("shipment", {})
    existing = shipment.get("as_log")
    if isinstance(existing, list) and existing:
        return False
    seeded = _legacy_entries_from_content(shipment)
    shipment["as_log"] = seeded
    return bool(seeded)


def current_as_round(sd: dict | None) -> int:
    """진행 중 회차 번호(1 시작). 미결 판정 1건마다 다음 회차가 열린다.

    저장 카운터가 아니라 as_log 파생값이다 — append-only 리스트에서 미결 verdict
    항목 수가 회차 전진의 단일 근거가 된다(별도 상태를 두면 로그와 어긋날 수 있다).
    판정 항목은 API 가 수정/삭제를 막지만, soft-delete 흔적이 있어도 세지 않는
    동일 규칙을 방어적으로 유지한다.

    Args:
        sd: 주문 structured_data (None 허용).

    Returns:
        1 + 비삭제 미결 판정 수.
    """
    entries = ((sd or {}).get("shipment") or {}).get("as_log")
    if not isinstance(entries, list):
        return 1
    opened = sum(
        1 for e in entries
        if isinstance(e, dict) and e.get("deleted") is not True
        and e.get("type") == "verdict" and e.get("verdict") == AS_VERDICT_UNRESOLVED
    )
    return 1 + opened


def append_client_log(sd: dict, *, log_type: str, text: str, by: str, by_id: int | None) -> dict:
    """수기 항목 append(최초 append 시 legacy 영구화, 현재 회차 스탬프). 반환=append된 항목."""
    migrate_legacy_into_log(sd)
    entry = build_as_log_entry(
        log_type=log_type, text=text, by=by, by_id=by_id, round_no=current_as_round(sd))
    sd["shipment"]["as_log"].append(entry)
    return entry


def append_system_log(sd: dict, *, text: str) -> dict:
    """시스템 이벤트 항목 append(서버 전용, 현재 회차 스탬프). 본문은 escape 후 저장.

    system 문구는 상태·담당자·메모 같은 **사용자 입력을 문자열로 조립**해 만들어진다.
    항목 text는 렌더에서 `|safe`(sanitize 통과 rich HTML 전제)라 여기서 escape하지
    않으면 조립된 입력이 그대로 실행 가능한 마크업이 된다. 호출부마다 escape를 요구하는
    대신 유일한 생성 지점에서 봉인한다.
    """
    migrate_legacy_into_log(sd)
    entry = build_as_log_entry(
        log_type="system", text=str(escape(text or "")), by="시스템", by_id=None,
        round_no=current_as_round(sd),
    )
    sd["shipment"]["as_log"].append(entry)
    return entry


def append_verdict_log(sd: dict, *, verdict: str, text: str, by: str, by_id: int | None) -> dict:
    """회차 판정(완결/미결) append. 반환=append된 항목(round=판정 대상 회차).

    미결 판정이 append 되는 순간 current_as_round 가 1 오른다 — 이후 append 는
    자동으로 다음 회차 스탬프를 받는다(round+1 규약, 별도 상태 없음). 판정의 정정은
    수정/삭제가 아니라 **새 판정 append** 다(수정·삭제를 허용하면 이미 스탬프된
    이후 항목들의 round 와 파생 회차가 어긋난다 — API 가드와 같은 계약).

    Args:
        sd: 주문 structured_data.
        verdict: ``'resolved'``(완결) | ``'unresolved'``(미결).
        text: 판정 사유(호출 라우트가 sanitize 완료, 빈 값 허용).
        by/by_id: 판정자 표기·id.

    Raises:
        ValueError: 허용되지 않은 verdict 값(호출부에서 400).
    """
    value = str(verdict or "").strip().lower()
    if value not in _AS_VERDICTS:
        raise ValueError("판정은 완결(resolved)/미결(unresolved)만 허용됩니다.")
    migrate_legacy_into_log(sd)
    entry = build_as_log_entry(
        log_type="verdict", text=text, by=by, by_id=by_id, round_no=current_as_round(sd))
    entry["verdict"] = value
    sd["shipment"]["as_log"].append(entry)
    return entry


def format_relative_kst(ts: str | None) -> str:
    """UTC naive ISO → 상대 표기('N분 전'/'어제' 등). 없으면 빈 문자열."""
    dt = parse_datetime_utc(ts) if ts else None
    if dt is None:
        return ""
    now = parse_datetime_utc(now_utc_naive())
    delta = (now - dt).total_seconds()
    if delta < 60:
        return "방금"
    if delta < 3600:
        return f"{int(delta // 60)}분 전"
    if delta < 86400:
        return f"{int(delta // 3600)}시간 전"
    if delta < 172800:
        return "어제"
    return f"{int(delta // 86400)}일 전"


def decorate_entry(entry: dict) -> dict:
    """렌더용 파생 필드 추가(원본 불변, 얕은 복사). API 단건 렌더도 재사용(public)."""
    out = dict(entry)
    ts = entry.get("ts")
    out["ts_abs"] = (format_datetime_kst(ts, "%Y-%m-%d %H:%M") or "") if ts else ""
    out["ts_rel"] = format_relative_kst(ts)
    out["type_label"] = _TYPE_LABELS.get(entry.get("type"), "메모")
    out["is_system"] = entry.get("type") == "system"
    out["is_legacy"] = entry.get("legacy") is True
    out["is_edited"] = bool(entry.get("edited_at"))
    # round 없는 구항목은 1회차로 간주(T15 이전 기록 소급 스탬프 없음 — append-only).
    raw_round = entry.get("round")
    out["round"] = raw_round if isinstance(raw_round, int) and raw_round >= 1 else 1
    out["is_verdict"] = entry.get("type") == "verdict"
    out["verdict_label"] = AS_VERDICT_LABELS.get(entry.get("verdict"), "") if out["is_verdict"] else ""
    return out


def latest_client_log_text(sd: dict | None, *, log_type: str) -> str:
    """as_log에서 soft-delete·legacy 제외, 지정 유형의 최신 항목 text를 반환한다.

    Args:
        sd: 주문 structured_data (None 허용).
        log_type: as_log 항목 type (예: 'material').

    Returns:
        최신 항목의 text. 해당 항목이 없으면 빈 문자열. legacy 항목(as_content
        마이그레이션 산물, type='memo')은 build_as_timeline_view가 스트림
        최신 판정에서 분리하는 규칙과 정합하도록 여기서도 제외한다.
    """
    shipment = (sd or {}).get("shipment") or {}
    entries = shipment.get("as_log")
    if not isinstance(entries, list):
        return ""
    best: tuple[str, int] | None = None
    best_text = ""
    for idx, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        if e.get("deleted") is True:
            continue
        if e.get("legacy") is True:
            continue
        if e.get("type") != log_type:
            continue
        key = (e.get("ts") or "", idx)
        if best is None or key > best:
            best = key
            best_text = str(e.get("text") or "")
    return best_text


def build_as_timeline_view(
    sd: dict | None,
    *,
    recent_limit: int = 8,
    sanitized: tuple[str | None, str | None] | None = None,
) -> dict[str, Any]:
    """앵커(접수/legacy) + 역시간순 스트림 뷰. lazy 마이그레이션은 표시 시점 비파괴.

    Args:
        sd: 주문 structured_data.
        recent_limit: 스트림 노출 개수 상한.
        sanitized: 이미 정리한 ``(as_content, as_content_2)`` HTML(중복 sanitize 방지).
            `_legacy_entries_from_content`로 그대로 전달된다.

    Returns:
        ``{reception, legacy, stream, stream_total, has_more, count}``.
    """
    shipment = (sd or {}).get("shipment") or {}
    entries = shipment.get("as_log")
    reception: dict | None = None
    legacy: list[dict] = []
    ranked: list[tuple[str, int, dict]] = []
    if isinstance(entries, list) and entries:
        for idx, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            # 소프트 삭제: 화면·집계에서만 감추고 원문은 sd에 남긴다(as_log는 append-only —
            # AS 분쟁 시 "언제 뭘 했는지"의 증거라 물리 삭제하지 않는다).
            # 여기 한 곳이 앵커·legacy·스트림·count를 모두 덮는다 — 표면마다 거르면
            # 배지 수와 실제 노출이 갈린다(T9 리뷰에서 이미 한 번 난 회귀 유형).
            if e.get("deleted") is True:
                continue
            if e.get("legacy") is True:
                legacy.append(decorate_entry(e))
            elif e.get("type") == "reception" and reception is None:
                reception = decorate_entry(e)
            elif e.get("type") == "reception":
                ranked.append((e.get("ts") or "", idx, e))  # 두 번째 접수 이후는 스트림
            else:
                ranked.append((e.get("ts") or "", idx, e))
    else:
        legacy = [decorate_entry(x) for x in _legacy_entries_from_content(shipment, sanitized)]
    # ts 동률이면 삽입 인덱스로 tie-break. stable sort에 맡기면 동률 그룹이
    # 삽입 순서(오래된 것 우선)로 남아 recent_limit 절단 시 최신 항목이 탈락한다.
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    total = len(ranked)
    # decorate는 절단 후에만 — 항목당 ts 파싱 3회를 전체가 아닌 노출분에만 지불한다.
    stream = [decorate_entry(item[2]) for item in ranked[:recent_limit]]
    return {
        "reception": reception,
        "legacy": legacy,
        "stream": stream,
        "stream_total": total,
        "has_more": total > recent_limit,
        "count": total + (1 if reception else 0) + len(legacy),
    }
