"""AS 타임라인 로그(as_log) 도메인 서비스.

sd['shipment']['as_log'] append-only 리스트의 생성·정규화·lazy 마이그레이션과
렌더용 뷰(앵커+스트림) 구성을 담당한다. API 라우트가 비대해지지 않도록 분리.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from foms.services.as_content_safety import sanitize_as_content_html
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive, parse_datetime_utc

AS_LOG_TYPES = frozenset({
    "reception", "call", "action", "material", "schedule", "memo", "system",
})
_CLIENT_TYPES = AS_LOG_TYPES - {"system"}
_DEFAULT_TYPE = "memo"
_TYPE_LABELS = {
    "reception": "접수", "call": "통화", "action": "방문/조치",
    "material": "자재", "schedule": "일정", "memo": "메모", "system": "시스템",
}


def new_as_log_id() -> str:
    """`al_<epoch_ms>_<rand4>` 형식의 항목 id."""
    return f"al_{int(time.time() * 1000)}_{secrets.token_hex(2)}"


def coerce_client_log_type(raw: Any) -> str:
    """클라이언트 유형을 허용 enum으로 정규화. 'system'은 거부(ValueError), 미허용은 memo."""
    value = str(raw or "").strip().lower()
    if value == "system":
        raise ValueError("system 유형은 서버만 생성할 수 있습니다.")
    return value if value in _CLIENT_TYPES else _DEFAULT_TYPE


def build_as_log_entry(*, log_type: str, text: str, by: str, by_id: int | None) -> dict[str, Any]:
    """as_log 항목 dict 생성. ts는 UTC naive ISO."""
    return {
        "id": new_as_log_id(),
        "ts": now_utc_naive().isoformat(),
        "by": by or "",
        "by_id": by_id,
        "type": log_type,
        "text": text,
        "edited_at": None,
        "edited_by": None,
    }


def _legacy_entries_from_content(shipment: dict) -> list[dict]:
    """as_content/as_content_2를 읽기전용 legacy memo 항목으로 변환."""
    out: list[dict] = []
    for field, label in (("as_content", "이전 기록"), ("as_content_2", "이전 기록(탭2)")):
        html = sanitize_as_content_html(shipment.get(field))
        if not html:
            continue
        out.append({
            "id": new_as_log_id(),
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


def append_client_log(sd: dict, *, log_type: str, text: str, by: str, by_id: int | None) -> dict:
    """수기 항목 append(최초 append 시 legacy 영구화). 반환=append된 항목."""
    migrate_legacy_into_log(sd)
    entry = build_as_log_entry(log_type=log_type, text=text, by=by, by_id=by_id)
    sd["shipment"]["as_log"].append(entry)
    return entry


def append_system_log(sd: dict, *, text: str) -> dict:
    """시스템 이벤트 항목 append(서버 전용)."""
    migrate_legacy_into_log(sd)
    entry = build_as_log_entry(log_type="system", text=text, by="시스템", by_id=None)
    sd["shipment"]["as_log"].append(entry)
    return entry


def format_relative_kst(ts: str | None) -> str:
    """UTC naive ISO → 상대 표기('N분 전'/'어제' 등). 없으면 빈 문자열."""
    dt = parse_datetime_utc(ts) if ts else None
    if dt is None:
        return ""
    now = parse_datetime_utc(now_utc_naive().isoformat())
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
    return out


def build_as_timeline_view(sd: dict | None, *, recent_limit: int = 8) -> dict[str, Any]:
    """앵커(접수/legacy) + 역시간순 스트림 뷰. lazy 마이그레이션은 표시 시점 비파괴."""
    shipment = (sd or {}).get("shipment") or {}
    entries = shipment.get("as_log")
    reception: dict | None = None
    legacy: list[dict] = []
    stream: list[dict] = []
    if isinstance(entries, list) and entries:
        for e in entries:
            if not isinstance(e, dict):
                continue
            if e.get("legacy") is True:
                legacy.append(decorate_entry(e))
            elif e.get("type") == "reception" and reception is None:
                reception = decorate_entry(e)
            elif e.get("type") == "reception":
                stream.append(decorate_entry(e))  # 두 번째 접수 이후는 스트림
            else:
                stream.append(decorate_entry(e))
    else:
        legacy = [decorate_entry(x) for x in _legacy_entries_from_content(shipment)]
    stream.sort(key=lambda x: x.get("ts") or "", reverse=True)
    total = len(stream)
    return {
        "reception": reception,
        "legacy": legacy,
        "stream": stream[:recent_limit],
        "stream_total": total,
        "has_more": total > recent_limit,
        "count": total + (1 if reception else 0) + len(legacy),
    }
