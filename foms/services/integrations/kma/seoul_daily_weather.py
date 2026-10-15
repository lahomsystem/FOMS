"""서울(수도권) 날짜별 날씨 — 기상청 API허브 단기·중기 예보를 받아 하루 한 칸으로 줄인다 (2026-10-14).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md

흐름
----
* 수집은 **요청 경로에서 하지 않는다**. SIDEFX 상시 루프(``tools/ops/run_domain_side_effect_outbox.py``
  ``--weather-interval``)가 한 시간마다 :func:`refresh_short`·:func:`refresh_mid` 를 따로 부른다 —
  한쪽이 실패해도 다른 쪽 저장은 남는다. 예외는 루프의 ``_safe`` 가 로그로 남긴다.
* 달력은 :func:`load_days` 로 저장된 값만 읽는다(예외 없이 — 자료가 없으면 빈 dict, 띠는 회백색).

날씨 종류(달력 그림 6종): ``sun`` 맑음 · ``cloud`` 구름 · ``drizzle`` 부슬비 · ``heavy`` 장대비 · ``flurry`` 부슬눈 · ``snow`` 함박눈.

지난 날
-------
사용자 결정(2026-10-14): 지난 날은 **그날 마지막 예보**를 그대로 둔다. 수집은 오늘 이후 날짜만 덮어쓰므로
날짜가 지나면 마지막으로 받은 값이 남는다. 오래된 날짜는 :data:`RETAIN_PAST_DAYS` 뒤에 지운다.

저장 자리
---------
새 표 없이 ``SystemSetting`` 키 :data:`WEATHER_KEY` 하나. 설정이 아니라 캐시라 버전 잠금은 쓰지 않는다.
``{"updated_at": iso, "days": {"YYYY-MM-DD": {"kind", "t_min", "t_max", "pop", "src", "base", "slots"}}}``

``slots`` 는 하루를 6시간 4칸(00·06·12·18시)으로 나눈 날씨 종류 목록이다 — '시간 줄' 보기(사람마다 고름)가 쓴다.
자료가 없는 칸은 ``None``(오늘 새벽처럼 이미 지난 시간), 옛 저장 값엔 키가 없다 — 그리는 쪽이 하루 날씨로 채운다.
"""

from __future__ import annotations

import copy
import datetime
import logging
import os
from typing import Any, Callable, Iterable, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_kst
from foms.services.integrations.kma.weather_classify import (  # 판정은 옆 모듈(500줄 래칫) — 예전 자리로도 부른다
    KINDS, _int_or_none, classify_mid_text, classify_short, classify_slot_detail, classify_slots, parse_pcp_mm,
    worst_kind,
)
from models import SystemSetting

__all__ = [
    "WEATHER_KEY",
    "KEY_ENV",
    "KINDS",
    "parse_pcp_mm",
    "classify_short",
    "classify_slots",
    "classify_slot_detail",
    "worst_kind",
    "classify_mid_text",
    "short_base_time",
    "mid_tm_fc",
    "refresh_short",
    "refresh_mid",
    "load_days",
    "weather_version",
]

_LOGGER = logging.getLogger(__name__)

WEATHER_KEY = "seoul_daily_weather"
#: 기상청 API허브 인증키(22자). 로그·응답·화면에 찍지 않는다.
KEY_ENV = "KMA_APIHUB_KEY"
BASE_URL = "https://apihub.kma.go.kr/api/typ02/openApi"

#: 서울 단기예보 격자(종로구 기준).
SHORT_NX, SHORT_NY = 60, 127
#: 중기 육상예보 구역(서울·인천·경기)과 중기 기온 지점(서울).
MID_LAND_REG = "11B00000"
MID_TA_REG = "11B10101"


#: 미래 날짜를 단기예보로 판정하려면 시간별 기온이 이만큼은 있어야 한다. 오후 발표의 4일 뒤는 자정 한두 시간뿐이라
#: 그 조각으로 '맑음 18°/18°' 같은 값이 나오고 중기예보(그날 '흐리고 비')를 막았다(2026-10-14 실측) → 중기에 맡긴다.
SHORT_MIN_HOURS = 12
#: 3~4일 뒤 단기예보는 3시간 간격(하루 8칸)이다 — 시간 수가 12 미만이어도 0~21시를 고루 덮으면 하루치로 본다
#: (2026-10-15 실측: 18일이 '조각'으로 버려져 비 양을 모르는 중기예보로 그려졌다).
SPARSE_STEP_HOURS = 3

#: 지난 날 보관 일수(달력은 지난달·다음달까지 넘겨 본다).
RETAIN_PAST_DAYS = 62
HTTP_TIMEOUT_SECONDS = 5

#: 단기예보 발표 시각(KST 시)과, 발표 뒤 자료가 올라오기까지 기다리는 분.
SHORT_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
SHORT_READY_MINUTES = 10
MID_BASE_HOURS = (6, 18)
MID_READY_MINUTES = 30


Transport = Callable[..., Any]


# ── 발표 시각 ───────────────────────────────────────────────────


def short_base_time(now: datetime.datetime) -> tuple[str, str]:
    """지금 받을 수 있는 가장 최근 단기예보 발표 ``(base_date, base_time)`` — 발표 10분 뒤부터."""
    ready = now - datetime.timedelta(minutes=SHORT_READY_MINUTES)
    hours = [h for h in SHORT_BASE_HOURS if h <= ready.hour]
    if hours:
        return ready.strftime("%Y%m%d"), f"{hours[-1]:02d}00"
    prev = ready - datetime.timedelta(days=1)
    return prev.strftime("%Y%m%d"), f"{SHORT_BASE_HOURS[-1]:02d}00"


def mid_tm_fc(now: datetime.datetime) -> str:
    """지금 받을 수 있는 가장 최근 중기예보 발표 ``tmFc``(YYYYMMDDHHMM) — 발표 30분 뒤부터."""
    ready = now - datetime.timedelta(minutes=MID_READY_MINUTES)
    hours = [h for h in MID_BASE_HOURS if h <= ready.hour]
    if hours:
        return ready.strftime("%Y%m%d") + f"{hours[-1]:02d}00"
    prev = ready - datetime.timedelta(days=1)
    return prev.strftime("%Y%m%d") + f"{MID_BASE_HOURS[-1]:02d}00"


# ── 수집 ────────────────────────────────────────────────────────


def _get_items(transport: Optional[Transport], path: str, params: dict[str, Any], key: str) -> Optional[list]:
    """API허브 호출 → ``items.item`` 목록. 활용신청 전(403)·빈 결과는 None(경고 로그만, 예외 없음).

    네트워크·JSON 오류는 그대로 올린다 — 루프의 ``_safe`` 가 기록하고 다음 회차에 다시 받는다.
    """
    if transport is None:
        import requests  # 지연 import: 요청 경로(load_days)는 requests 를 쓰지 않는다

        transport = requests.get
    query = dict(params, dataType="JSON", pageNo=1, authKey=key)
    resp = transport(f"{BASE_URL}/{path}", params=query, timeout=HTTP_TIMEOUT_SECONDS)
    status = int(getattr(resp, "status_code", 0) or 0)
    data = resp.json() if status in (200, 403) else None
    if not isinstance(data, dict):
        _LOGGER.warning("[weather] %s HTTP %s", path, status)
        return None
    result = data.get("result")
    if isinstance(result, dict) and result.get("status"):
        # 활용신청 전이면 API허브가 {"result":{"status":403,"message":...}} 를 준다.
        _LOGGER.warning("[weather] %s 거절 status=%s %s", path, result.get("status"), result.get("message"))
        return None
    header = ((data.get("response") or {}).get("header") or {})
    if str(header.get("resultCode") or "") != "00":
        _LOGGER.warning("[weather] %s resultCode=%s %s", path, header.get("resultCode"), header.get("resultMsg"))
        return None
    items = (((data.get("response") or {}).get("body") or {}).get("items") or {}).get("item")
    return items if isinstance(items, list) else None


def _key(key: Optional[str]) -> str:
    return (key if key is not None else os.environ.get(KEY_ENV, "")).strip()


def _covers_day(rows: Iterable[dict[str, Any]]) -> bool:
    """하루치 단기예보인가 — 시간별(12칸 이상) 또는 3시간 간격으로 0~21시를 고루 덮는다."""
    hours = sorted({h for h in (_int_or_none(str(r.get("fcstTime") or "")[:2]) for r in rows if r.get("category") == "TMP") if h is not None})
    if len(hours) >= SHORT_MIN_HOURS:
        return True
    gaps = [b - a for a, b in zip(hours, hours[1:])]
    return bool(hours) and hours[0] <= SPARSE_STEP_HOURS and hours[-1] >= 24 - SPARSE_STEP_HOURS and max(gaps or [99]) <= SPARSE_STEP_HOURS


def refresh_short(session: Session, *, now: Optional[datetime.datetime] = None,
                  transport: Optional[Transport] = None, key: Optional[str] = None) -> dict[str, Any]:
    """단기예보(오늘~모레·글피)를 받아 날짜별로 줄여 저장한다. 오늘 이전 날짜는 덮어쓰지 않는다."""
    k = _key(key)
    if not k:
        return {"skipped": "no_key"}
    now = now or now_kst()
    base_date, base_time = short_base_time(now)
    items = _get_items(transport, "VilageFcstInfoService_2.0/getVilageFcst", {
        "numOfRows": 1200, "base_date": base_date, "base_time": base_time, "nx": SHORT_NX, "ny": SHORT_NY,
    }, k)
    if not items:
        return {"skipped": "no_data"}
    by_date: dict[str, list] = {}
    for it in items:
        d = str(it.get("fcstDate") or "")
        if len(d) == 8:
            by_date.setdefault(f"{d[:4]}-{d[4:6]}-{d[6:]}", []).append(it)
    today_iso = now.date().isoformat()
    days = {}
    partial = set()
    for iso, rows in by_date.items():
        hours = len({str(r.get("fcstTime") or "") for r in rows if r.get("category") == "TMP"})
        full = _covers_day(rows)
        if iso > today_iso and not full:
            partial.add(iso)  # 하루 일부만 있는 끝 날짜 — 중기예보가 채운다
            continue
        detail = classify_slot_detail(rows)
        # 하루 대표 날씨 = 6시간 칸 중 가장 궂은 것(기상청 강수강도 기준). 오늘은 지난 칸을 합친 뒤 다시 정한다(_merge).
        day = classify_short(rows)
        day["kind"] = worst_kind((d["k"] for d in detail if d), day["kind"])
        days[iso] = dict(day, src="short", base=f"{base_date}{base_time}", hours=hours, full=full,
                         slots=[d["k"] if d else None for d in detail], slot_detail=detail)
    n = _merge(session, days, today=now.date(), keep_short=False, drop_partial=partial)
    return {"stored": n, "base": f"{base_date}{base_time}"}


def refresh_mid(session: Session, *, now: Optional[datetime.datetime] = None,
                transport: Optional[Transport] = None, key: Optional[str] = None) -> dict[str, Any]:
    """중기예보(3~10일 뒤)를 받아 저장한다. 단기예보가 이미 있는 날짜는 단기 값을 둔다(더 정확하다)."""
    k = _key(key)
    if not k:
        return {"skipped": "no_key"}
    now = now or now_kst()
    tm_fc = mid_tm_fc(now)
    land = _get_items(transport, "MidFcstInfoService/getMidLandFcst",
                      {"numOfRows": 10, "regId": MID_LAND_REG, "tmFc": tm_fc}, k)
    if not land:
        return {"skipped": "no_data"}
    ta = _get_items(transport, "MidFcstInfoService/getMidTa",
                    {"numOfRows": 10, "regId": MID_TA_REG, "tmFc": tm_fc}, k) or [{}]
    row, ta_row = land[0], ta[0]
    base_day = datetime.date(int(tm_fc[:4]), int(tm_fc[4:6]), int(tm_fc[6:8]))
    days: dict[str, dict[str, Any]] = {}
    for n in range(3, 11):
        texts = [row.get(f"wf{n}Am"), row.get(f"wf{n}Pm"), row.get(f"wf{n}")]
        if not any(texts):
            continue
        pops = [_int_or_none(row.get(f"rnSt{n}{s}")) for s in ("Am", "Pm", "")]
        pops = [p for p in pops if p is not None]
        # 시간 줄 칸: 오전 글 = 0~11시, 오후 글 = 12~23시(8일 뒤부터는 하루 글 하나)
        am = classify_mid_text(texts[0] or texts[2] or texts[1])
        pm = classify_mid_text(texts[1] or texts[2] or texts[0])
        pop_am = _int_or_none(row.get(f"rnSt{n}Am") if row.get(f"rnSt{n}Am") is not None else row.get(f"rnSt{n}"))
        pop_pm = _int_or_none(row.get(f"rnSt{n}Pm") if row.get(f"rnSt{n}Pm") is not None else row.get(f"rnSt{n}"))
        # 중기예보는 비·눈 양이 없다 → 강도는 비우고(그림은 종류 기본값), 오전/오후 강수확률만 싣는다
        detail = [{"k": am, "lv": None, "pop": pop_am, "wind": None}] * 2 + [{"k": pm, "lv": None, "pop": pop_pm, "wind": None}] * 2
        days[(base_day + datetime.timedelta(days=n)).isoformat()] = {
            "kind": worst_kind([am, pm], classify_mid_text(*texts)),
            "slots": [am, am, pm, pm],
            "slot_detail": [dict(d) for d in detail],
            "t_min": _int_or_none(ta_row.get(f"taMin{n}")),
            "t_max": _int_or_none(ta_row.get(f"taMax{n}")),
            "pop": max(pops) if pops else None,
            "src": "mid",
            "base": tm_fc,
        }
    n = _merge(session, days, today=now.date(), keep_short=True)
    return {"stored": n, "base": tm_fc}


def _merge(session: Session, days: dict[str, dict[str, Any]], *, today: datetime.date, keep_short: bool,
           drop_partial: Iterable[str] = ()) -> int:
    """새 날짜 값을 저장된 값에 합친다 — 오늘 이전은 그대로(그날 마지막 예보), 오래된 날짜는 지운다."""
    row = session.query(SystemSetting).filter(SystemSetting.setting_key == WEATHER_KEY).with_for_update().first()
    current = copy.deepcopy(row.setting_value) if row is not None and isinstance(row.setting_value, dict) else {}
    stored = current.get("days") if isinstance(current.get("days"), dict) else {}
    today_iso = today.isoformat()
    oldest = (today - datetime.timedelta(days=RETAIN_PAST_DAYS)).isoformat()
    written = 0
    for iso, val in days.items():
        if iso < today_iso or val.get("kind") not in KINDS:
            continue
        old = stored.get(iso)
        if keep_short and isinstance(old, dict) and old.get("src") == "short" and (old.get("full") or int(old.get("hours") or 0) >= SHORT_MIN_HOURS):
            continue  # 하루치가 다 있는 단기 값이 더 정확하다(시간 수 없는 옛 값은 중기로 덮는다)
        if iso == today_iso and isinstance(old, dict) and old.get("t_min") is not None:
            # 오후 발표엔 오늘 TMN(새벽 최저)이 없어 남은 시간 기온으로 채운다 → 아침에 받아 둔 더 낮은 값을 지킨다.
            new_min = val.get("t_min")
            val = dict(val, t_min=old["t_min"] if new_min is None else min(old["t_min"], new_min))
        if iso == today_iso and isinstance(old, dict) and old.get("t_max") is not None:
            # 저녁 발표엔 낮 최고(TMX)가 없어 남은 시간 기온으로 채운다 → 더 높은 값을 지킨다
            # (2026-10-15 실측: 14일이 '14°/13°'로 저장됐다, 실제 9~17°).
            new_max = val.get("t_max")
            val = dict(val, t_max=old["t_max"] if new_max is None else max(old["t_max"], new_max))
        if iso == today_iso and isinstance(old, dict) and isinstance(val.get("slots"), list):
            # 오늘 지난 칸은 새 발표에 없다(None) → 앞서 받아 둔 그 칸 값을 지킨다
            prev = old.get("slots") if isinstance(old.get("slots"), list) else []
            val = dict(val, slots=[s if s is not None else (prev[i] if i < len(prev) else None)
                                   for i, s in enumerate(val["slots"])])
            if isinstance(val.get("slot_detail"), list):
                prev_d = old.get("slot_detail") if isinstance(old.get("slot_detail"), list) else []
                merged = [d if d else (prev_d[i] if i < len(prev_d) and prev_d[i] else None) for i, d in enumerate(val["slot_detail"])]
                # 하루 대표 날씨도 합친 칸으로 다시 — 늦은 발표의 저녁 몇 시간만으로 '맑음'이 되지 않게
                kinds = [d["k"] if isinstance(d, dict) else None for d in merged] + [k for k in val["slots"] if k]
                val = dict(val, slot_detail=merged, kind=worst_kind(kinds, val["kind"]))
        stored[iso] = val
        written += 1
    for iso in drop_partial:
        old = stored.get(iso)
        # 시간 수를 모르는(이 규칙 전) 단기 값은 같은 조각으로 판정됐을 수 있다 — 지우고 다음 발표·중기에 맡긴다
        if isinstance(old, dict) and old.get("src") == "short" and not old.get("full") and int(old.get("hours") or 0) < SHORT_MIN_HOURS:
            del stored[iso]
    stored = {iso: v for iso, v in stored.items() if iso >= oldest}
    value = {"updated_at": now_kst().replace(microsecond=0).isoformat(), "days": stored}
    if row is None:
        session.add(SystemSetting(setting_key=WEATHER_KEY, setting_value=value,
                                  description="모바일 달력 서울 날짜별 날씨(기상청 예보 캐시, SIDEFX 루프가 갱신)"))
    else:
        row.setting_value = value
        flag_modified(row, "setting_value")
    session.commit()
    return written


# ── 읽기 (요청 경로, 예외 없음) ──────────────────────────────────


def weather_version(session: Session) -> str:
    """캐시 지문용 — 마지막 저장 시각(새 예보가 들어오면 달력 캐시 키가 바뀐다). 없으면 빈 문자열."""
    row = session.query(SystemSetting.setting_value).filter(SystemSetting.setting_key == WEATHER_KEY).first()
    value = row[0] if row is not None and isinstance(row[0], dict) else {}
    return str(value.get("updated_at") or "")


def load_days(session: Session, first: datetime.date, last: datetime.date) -> dict[str, Any]:
    """기간 날씨 → ``{"updated_at": str, "days": {iso: {"kind","t_max",...}}}``. 없거나 깨졌으면 빈 값."""
    row = session.query(SystemSetting).filter(SystemSetting.setting_key == WEATHER_KEY).first()
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    stored = value.get("days") if isinstance(value.get("days"), dict) else {}
    lo, hi = first.isoformat(), last.isoformat()
    days = {iso: v for iso, v in stored.items()
            if lo <= iso <= hi and isinstance(v, dict) and v.get("kind") in KINDS}
    return {"updated_at": str(value.get("updated_at") or ""), "days": days}
