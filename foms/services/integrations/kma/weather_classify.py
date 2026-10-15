"""서울 날씨 판정 — 기상청 단기·중기 예보 글·값을 날씨 종류·강도로 바꾸는 순수 함수 (2026-10-15 분리).

수집·저장은 :mod:`foms.services.integrations.kma.seoul_daily_weather`. 근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §2.8·§3.2.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

KINDS = ("sun", "partly", "cloud", "drizzle", "rain", "heavy", "flurry", "snow")

#: 장대비 기준 — 하루 강수량 합(mm) 또는 한 시간 강수량(mm) 중 하나라도 넘으면 장대비.
HEAVY_DAY_MM = 20.0
HEAVY_HOUR_MM = 7.0
#: 함박눈 기준 — 하루 신적설 합(cm) 또는 한 시간 신적설(cm) 중 하나라도 넘으면 함박눈, 아니면 부슬눈.
HEAVY_SNOW_DAY_CM = 3.0
HEAVY_SNOW_HOUR_CM = 1.0
#: 낮(09~18시) 중 구름많음·흐림 시간이 이 비율 이상이면 구름.
CLOUD_DAY_RATIO = 0.5
DAYTIME_HOURS = range(9, 19)
#: 시간 줄 한 칸 = 6시간(하루 4칸: 0~5·6~11·12~17·18~23시).
SLOT_HOURS = 6
SLOTS_PER_DAY = 24 // SLOT_HOURS

_SEVERITY = {"sun": 0, "partly": 1, "cloud": 2, "drizzle": 3, "rain": 4, "heavy": 5, "flurry": 6, "snow": 7}
_NUM = re.compile(r"(-?\d+(?:\.\d+)?)")


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


def parse_sno_cm(text: Any) -> float:
    """단기예보 ``SNO``(1시간 신적설) 글 → cm. "적설없음"=0, "1cm 미만"=0.5, "1.0cm"=1, "5.0cm 이상"=5."""
    return parse_pcp_mm(text)  # 글 모양이 강수량과 같다(없음·미만·범위·이상)


def _int_or_none(text: Any) -> Optional[int]:
    m = _NUM.search(str(text or ""))
    return int(round(float(m.group(1)))) if m else None


def classify_short(items: Iterable[dict[str, Any]], *, sky_hours: Iterable[int] = DAYTIME_HOURS) -> dict[str, Any]:
    """하루치 단기예보 항목(``category``·``fcstTime``·``fcstValue``) → ``{"kind","t_min","t_max","pop"}``.

    판정 순서(위가 먼저): 함박눈(신적설 하루 ≥ 3cm 또는 한 시간 ≥ 1cm) → 부슬눈·진눈깨비 → 장대비(하루 합 ≥ 20mm 또는 한 시간 ≥ 7mm) → 부슬비 →
    구름(낮 시간 절반 이상 구름많음·흐림) → 맑음. ``sky_hours`` 는 구름 판정에 쓰는 시각(시간 줄 칸은 그 칸 전부).
    """
    sky_hours = set(sky_hours)
    pty: list[int] = []
    pcp: list[float] = []
    sno: list[float] = []
    sky_day: list[int] = []
    tmp: list[int] = []
    tmx: Optional[int] = None
    tmn: Optional[int] = None
    pop: list[int] = []
    for it in items:
        cat = str(it.get("category") or "")
        val = it.get("fcstValue")
        hour = _int_or_none(str(it.get("fcstTime") or "")[:2])
        if cat == "PTY":
            pty.append(_int_or_none(val) or 0)
        elif cat == "PCP":
            pcp.append(parse_pcp_mm(val))
        elif cat == "SNO":
            sno.append(parse_sno_cm(val))
        elif cat == "SKY" and hour in sky_hours:
            sky_day.append(_int_or_none(val) or 1)
        elif cat == "TMP":
            t = _int_or_none(val)
            if t is not None:
                tmp.append(t)
        elif cat == "TMX":
            tmx = _int_or_none(val)
        elif cat == "TMN":
            tmn = _int_or_none(val)
        elif cat == "POP":
            p = _int_or_none(val)
            if p is not None:
                pop.append(p)

    if any(p == 3 for p in pty) and (sum(sno) >= HEAVY_SNOW_DAY_CM or max(sno or [0.0]) >= HEAVY_SNOW_HOUR_CM):
        kind = "snow"  # 함박눈
    elif any(p in (2, 3) for p in pty):
        kind = "flurry"  # 부슬눈 · 진눈깨비(비/눈)
    elif any(p in (1, 4) for p in pty):
        kind = "heavy" if (sum(pcp) >= HEAVY_DAY_MM or max(pcp or [0.0]) >= HEAVY_HOUR_MM) else "drizzle"
    elif sky_day and sum(1 for s in sky_day if s >= 3) / len(sky_day) >= CLOUD_DAY_RATIO:
        kind = "cloud"
    else:
        kind = "sun"
    # 일 최고(TMX)·최저(TMN)는 발표 시각에 따라 빠지는 날이 있다(오늘 오후 발표엔 오늘 TMN 이 없다) → 시간별 기온으로 채운다.
    t_max = tmx if tmx is not None else (max(tmp) if tmp else None)
    t_min = tmn if tmn is not None else (min(tmp) if tmp else None)
    return {"kind": kind, "t_min": t_min, "t_max": t_max, "pop": max(pop) if pop else None}


#: 기상청 강수강도 구분(시간당) — 비: 이슬비 <1 · 약한 비 1~3 · 보통 비 3~15 · 강한 비 ≥15(mm/h),
#: 눈: 약한 눈 <1 · 보통 눈 1~5 · 강한 눈 ≥5(cm/h). 시간 줄 그림의 빗방울·눈송이 세기가 이 단계를 따른다.
RAIN_LEVEL_MM = (1.0, 3.0, 15.0)
SNOW_LEVEL_CM = (1.0, 5.0)


def _level(rate: float, edges: tuple[float, ...]) -> int:
    return sum(1 for e in edges if rate >= e)


def classify_slot_detail(items: Iterable[dict[str, Any]]) -> list[Optional[dict[str, Any]]]:
    """하루치 단기예보 → 6시간 칸 4개의 ``{"k","lv","pop","wind"}``(시간 줄 v2). 기온이 없는 칸은 ``None``.

    3~4일 뒤 예보는 3시간 간격이라 PCP·SNO 가 3시간 양이다 → 간격으로 나눠 시간당으로 본다.
    종류: 눈(PTY 3) — 보통 눈 이상이면 함박눈, 아니면 부슬눈 · 진눈깨비(PTY 2) = 부슬눈 ·
    비(PTY 1/4) — 강도 0~1 부슬비, 2 비, 3 장대비 · 강수 없으면 SKY 평균으로 맑음/구름조금/흐림.
    """
    rows = list(items)
    hours = sorted({h for h in (_int_or_none(str(r.get("fcstTime") or "")[:2]) for r in rows if r.get("category") == "TMP") if h is not None})
    step = min((b - a for a, b in zip(hours, hours[1:])), default=1) or 1
    out: list[Optional[dict[str, Any]]] = []
    for i in range(SLOTS_PER_DAY):
        lo, hi = i * SLOT_HOURS, (i + 1) * SLOT_HOURS
        sub = [r for r in rows if (h := _int_or_none(str(r.get("fcstTime") or "")[:2])) is not None and lo <= h < hi]
        if not any(r.get("category") == "TMP" for r in sub):
            out.append(None)
            continue
        val = lambda cat: [r.get("fcstValue") for r in sub if r.get("category") == cat]  # noqa: E731
        pty = [_int_or_none(v) or 0 for v in val("PTY")]
        rain = max([parse_pcp_mm(v) for v in val("PCP")] or [0.0]) / step
        snow = max([parse_sno_cm(v) for v in val("SNO")] or [0.0]) / step
        sky = [_int_or_none(v) or 1 for v in val("SKY")]
        pops = [p for p in (_int_or_none(v) for v in val("POP")) if p is not None]
        winds = [float(m.group(1)) for v in val("WSD") if (m := _NUM.search(str(v or "")))]
        pop = max(pops) if pops else None
        wind = round(max(winds), 1) if winds else None
        if any(p == 3 for p in pty):
            lv = _level(snow, SNOW_LEVEL_CM)
            k = "snow" if lv >= 1 else "flurry"
        elif any(p == 2 for p in pty):
            k, lv = "flurry", 0
        elif any(p in (1, 4) for p in pty):
            lv = _level(rain, RAIN_LEVEL_MM)
            k = ("drizzle", "drizzle", "rain", "heavy")[lv]
        else:
            avg = sum(sky) / len(sky) if sky else 1
            k, lv = ("cloud" if avg >= 3.5 else "partly" if avg >= 2.5 else "sun"), 0
        out.append({"k": k, "lv": lv, "pop": pop, "wind": wind})
    return out


def classify_slots(items: Iterable[dict[str, Any]]) -> list[Optional[str]]:
    """하루치 단기예보 항목 → 6시간 칸 4개의 날씨 종류. 기온(TMP)이 하나도 없는 칸(이미 지난 시간)은 ``None``."""
    groups: list[list[dict[str, Any]]] = [[] for _ in range(SLOTS_PER_DAY)]
    for it in items:
        hour = _int_or_none(str(it.get("fcstTime") or "")[:2])
        if hour is not None and 0 <= hour < 24:
            groups[hour // SLOT_HOURS].append(it)
    out: list[Optional[str]] = []
    for i, rows in enumerate(groups):
        if not any(r.get("category") == "TMP" for r in rows):
            out.append(None)
            continue
        out.append(classify_short(rows, sky_hours=range(i * SLOT_HOURS, (i + 1) * SLOT_HOURS))["kind"])
    return out


def classify_mid_text(*texts: Any) -> str:
    """중기 육상예보 글(오전·오후) → 날씨 종류. 더 궂은 쪽을 쓴다.

    중기예보에는 비·눈의 양이 없어서 비는 부슬비, 눈은 부슬눈 그림으로 둔다(장대비·함박눈을 지어내지 않는다).
    """
    worst = "sun"
    for t in texts:
        s = str(t or "")
        if "눈" in s:
            kind = "flurry"
        elif "비" in s or "소나기" in s:
            kind = "drizzle"
        elif "흐림" in s:
            kind = "cloud"
        elif "구름" in s:
            kind = "partly"  # 구름많음
        else:
            kind = "sun"
        if _SEVERITY[kind] > _SEVERITY[worst]:
            worst = kind
    return worst


def worst_kind(kinds: Iterable[Optional[str]], default: str = "sun") -> str:
    """여러 칸 날씨 중 가장 궂은 것(하루 대표 날씨)."""
    known = [k for k in kinds if k in _SEVERITY]
    return max(known, key=_SEVERITY.__getitem__) if known else default


#: 낮 칸(6~12시·12~18시). 밤 칸의 약한 비·이슬비는 하루 대표 날씨에 넣지 않는다.
DAY_SLOTS = (1, 2)


def day_kind(detail: Iterable[Optional[dict[str, Any]]], slots: Iterable[Optional[str]] = (), default: str = "sun") -> str:
    """6시간 칸 → 하루 대표 날씨: 낮 칸 중 가장 궂은 것 + 밤 칸은 보통 비 이상·눈만.

    2026-10-15 사용자: 16일은 자정 한 시간 2mm 뿐인데 하루가 '부슬비'로 보였다 — 밤의 약한 비는 시간 줄 그림에만 남긴다.
    칸 자료가 비면 같은 자리 칸 종류(slots)로 본다.
    """
    det = list(detail)
    kinds = list(slots) + [None] * SLOTS_PER_DAY
    picked = []
    for i in range(SLOTS_PER_DAY):
        d = det[i] if i < len(det) and isinstance(det[i], dict) else None
        k = d["k"] if d else kinds[i]
        if k not in _SEVERITY:
            continue
        lv = d.get("lv") if d else None
        night_light_rain = k == "drizzle" and (lv is None or lv <= 1)
        if i in DAY_SLOTS or not night_light_rain:
            picked.append(k)
    return worst_kind(picked, default)
