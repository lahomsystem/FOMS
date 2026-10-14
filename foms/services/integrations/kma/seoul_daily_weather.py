"""서울(수도권) 날짜별 날씨 — 기상청 API허브 단기·중기 예보를 받아 하루 한 칸으로 줄인다 (2026-10-14).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md

흐름
----
* 수집은 **요청 경로에서 하지 않는다**. SIDEFX 상시 루프(``tools/ops/run_domain_side_effect_outbox.py``
  ``--weather-interval``)가 한 시간마다 :func:`refresh_short`·:func:`refresh_mid` 를 따로 부른다 —
  한쪽이 실패해도 다른 쪽 저장은 남는다. 예외는 루프의 ``_safe`` 가 로그로 남긴다.
* 달력은 :func:`load_days` 로 저장된 값만 읽는다(예외 없이 — 자료가 없으면 빈 dict, 띠는 회백색).

날씨 종류(달력 그림 5종): ``sun`` 맑음 · ``cloud`` 구름 · ``drizzle`` 부슬비 · ``heavy`` 장대비 · ``snow`` 눈.

지난 날
-------
사용자 결정(2026-10-14): 지난 날은 **그날 마지막 예보**를 그대로 둔다. 수집은 오늘 이후 날짜만 덮어쓰므로
날짜가 지나면 마지막으로 받은 값이 남는다. 오래된 날짜는 :data:`RETAIN_PAST_DAYS` 뒤에 지운다.

저장 자리
---------
새 표 없이 ``SystemSetting`` 키 :data:`WEATHER_KEY` 하나. 설정이 아니라 캐시라 버전 잠금은 쓰지 않는다.
``{"updated_at": iso, "days": {"YYYY-MM-DD": {"kind", "t_max", "pop", "src", "base"}}}``
"""

from __future__ import annotations

import copy
import datetime
import logging
import os
import re
from typing import Any, Callable, Iterable, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_kst
from models import SystemSetting

__all__ = [
    "WEATHER_KEY",
    "KEY_ENV",
    "KINDS",
    "parse_pcp_mm",
    "classify_short",
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
KINDS = ("sun", "cloud", "drizzle", "heavy", "snow")

#: 서울 단기예보 격자(종로구 기준).
SHORT_NX, SHORT_NY = 60, 127
#: 중기 육상예보 구역(서울·인천·경기)과 중기 기온 지점(서울).
MID_LAND_REG = "11B00000"
MID_TA_REG = "11B10101"

#: 장대비 기준 — 하루 강수량 합(mm) 또는 한 시간 강수량(mm) 중 하나라도 넘으면 장대비.
HEAVY_DAY_MM = 20.0
HEAVY_HOUR_MM = 7.0
#: 낮(09~18시) 중 구름많음·흐림 시간이 이 비율 이상이면 구름.
CLOUD_DAY_RATIO = 0.5
DAYTIME_HOURS = range(9, 19)

#: 지난 날 보관 일수(달력은 지난달·다음달까지 넘겨 본다).
RETAIN_PAST_DAYS = 62
HTTP_TIMEOUT_SECONDS = 5

#: 단기예보 발표 시각(KST 시)과, 발표 뒤 자료가 올라오기까지 기다리는 분.
SHORT_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
SHORT_READY_MINUTES = 10
MID_BASE_HOURS = (6, 18)
MID_READY_MINUTES = 30

_SEVERITY = {"sun": 0, "cloud": 1, "drizzle": 2, "heavy": 3, "snow": 4}
_NUM = re.compile(r"(-?\d+(?:\.\d+)?)")

Transport = Callable[..., Any]


# ── 판정 (순수 함수) ─────────────────────────────────────────────


def parse_pcp_mm(text: Any) -> float:
    """단기예보 ``PCP``(1시간 강수량) 글 → mm. "강수없음"=0, "1mm 미만"=0.5, "30.0~50.0mm"=30, "50.0mm 이상"=50."""
    s = str(text or "").strip()
    if not s or "없음" in s:
        return 0.0
    if "미만" in s:
        return 0.5
    m = _NUM.search(s)
    return float(m.group(1)) if m else 0.0


def _int_or_none(text: Any) -> Optional[int]:
    m = _NUM.search(str(text or ""))
    return int(round(float(m.group(1)))) if m else None


def classify_short(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """하루치 단기예보 항목(``category``·``fcstTime``·``fcstValue``) → ``{"kind","t_max","pop"}``.

    판정 순서(위가 먼저): 눈·진눈깨비 → 장대비(하루 합 ≥ 20mm 또는 한 시간 ≥ 7mm) → 부슬비 →
    구름(낮 시간 절반 이상 구름많음·흐림) → 맑음.
    """
    pty: list[int] = []
    pcp: list[float] = []
    sky_day: list[int] = []
    tmp: list[int] = []
    tmx: Optional[int] = None
    pop: list[int] = []
    for it in items:
        cat = str(it.get("category") or "")
        val = it.get("fcstValue")
        hour = _int_or_none(str(it.get("fcstTime") or "")[:2])
        if cat == "PTY":
            pty.append(_int_or_none(val) or 0)
        elif cat == "PCP":
            pcp.append(parse_pcp_mm(val))
        elif cat == "SKY" and hour in DAYTIME_HOURS:
            sky_day.append(_int_or_none(val) or 1)
        elif cat == "TMP":
            t = _int_or_none(val)
            if t is not None:
                tmp.append(t)
        elif cat == "TMX":
            tmx = _int_or_none(val)
        elif cat == "POP":
            p = _int_or_none(val)
            if p is not None:
                pop.append(p)

    if any(p in (2, 3) for p in pty):
        kind = "snow"
    elif any(p in (1, 4) for p in pty):
        kind = "heavy" if (sum(pcp) >= HEAVY_DAY_MM or max(pcp or [0.0]) >= HEAVY_HOUR_MM) else "drizzle"
    elif sky_day and sum(1 for s in sky_day if s >= 3) / len(sky_day) >= CLOUD_DAY_RATIO:
        kind = "cloud"
    else:
        kind = "sun"
    t_max = tmx if tmx is not None else (max(tmp) if tmp else None)
    return {"kind": kind, "t_max": t_max, "pop": max(pop) if pop else None}


def classify_mid_text(*texts: Any) -> str:
    """중기 육상예보 글(오전·오후) → 날씨 종류. 더 궂은 쪽을 쓴다.

    중기예보에는 비의 양이 없어서 비는 모두 부슬비 그림으로 둔다(장대비를 지어내지 않는다).
    """
    worst = "sun"
    for t in texts:
        s = str(t or "")
        if "눈" in s:
            kind = "snow"
        elif "비" in s or "소나기" in s:
            kind = "drizzle"
        elif "흐림" in s or "구름" in s:
            kind = "cloud"
        else:
            kind = "sun"
        if _SEVERITY[kind] > _SEVERITY[worst]:
            worst = kind
    return worst


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
    days = {iso: dict(classify_short(rows), src="short", base=f"{base_date}{base_time}")
            for iso, rows in by_date.items()}
    n = _merge(session, days, today=now.date(), keep_short=False)
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
        days[(base_day + datetime.timedelta(days=n)).isoformat()] = {
            "kind": classify_mid_text(*texts),
            "t_max": _int_or_none(ta_row.get(f"taMax{n}")),
            "pop": max(pops) if pops else None,
            "src": "mid",
            "base": tm_fc,
        }
    n = _merge(session, days, today=now.date(), keep_short=True)
    return {"stored": n, "base": tm_fc}


def _merge(session: Session, days: dict[str, dict[str, Any]], *, today: datetime.date, keep_short: bool) -> int:
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
        if keep_short and isinstance(old, dict) and old.get("src") == "short":
            continue
        stored[iso] = val
        written += 1
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
