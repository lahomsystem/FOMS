"""모바일 홈 달력 — '시간 줄' 날씨 띠 (2026-10-15 v2: 유일한 보기, 강도·확률·바람·낮밤).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §시간 줄 보기.

한 주 띠를 SVG 한 장으로 그린다. 칸 하나 = 24시간 = 가로 100 단위, 6시간 칸 4개가 25 단위씩이다.
날씨는 날짜 경계가 아니라 **날씨가 바뀌는 시각**에서만 바뀐다.

6시간 칸 하나 = ``{"k": 종류, "lv": 강도, "pop": 강수확률, "wind": 풍속}`` (``slot_detail``, 없으면 ``slots`` 종류만).
* 종류 8가지: 맑음 sun · 구름조금 partly · 흐림 cloud · 부슬비 drizzle · 비 rain · 장대비 heavy · 부슬눈 flurry · 함박눈 snow.
* 강도(lv)는 기상청 강수강도 구분을 따른다 — 비: 0 이슬비(<1mm/h) · 1 약한 비(1~3) · 2 보통 비(3~15) · 3 강한 비(≥15),
  눈: 0 약한 눈(<1cm/h) · 1 보통 눈(1~5) · 2 강한 눈(≥5). 빗방울 수·크기·빠르기·튀김이 강도를 따라 커진다.
* 강수확률이 낮을수록 비·눈이 옅다(60% = 80% 진하기). 바람이 셀수록 빗줄기가 눕는다.
* 맑은 날은 하루 전체가 맑음 색이고 그날 가운데에 해 하나(밤 칸 남색·달·별은 뺐다 — 사용자 2026-10-15).
* 지난 날 부분은 하늘 색 막으로 흐리게, 오늘 칸엔 지금 시각 선.

움직임은 transform·opacity 만(CSS ``.tl-*``). 주 전체가 지난 날이면 멈춘다(``is-still``).
캐시된 달력 페이로드(JSON)는 칸마다 날씨 자료만 들고, 그림은 화면을 그릴 때 만든다(지금 선은 매번 새 시각).
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Iterable, Optional, Sequence

from markupsafe import Markup

from foms.services.datetime_kst import now_kst

__all__ = ["timeline_defs", "week_band_svg", "week_slots", "runs", "wx_timeline_band", "KINDS", "RAIN", "SNOW"]

KINDS = ("sun", "partly", "cloud", "drizzle", "rain", "heavy", "flurry", "snow")
RAIN = ("drizzle", "rain", "heavy")
SNOW = ("flurry", "snow")
#: 종류만 아는 옛 자료·중기예보의 기본 강도
DEFAULT_LV = {"drizzle": 1, "rain": 2, "heavy": 3, "flurry": 0, "snow": 1}
SLOTS_PER_DAY = 4
DAY_W = 100.0
SLOT_W = DAY_W / SLOTS_PER_DAY
FEATHER_OUT = 16
SKY_BLEND_SLOTS = 1.5
VH = 190

_CLOUD = "M0 26a13 13 0 0 1 2-25.8A17 17 0 0 1 34 5a11 11 0 0 1 1 21z"
_DROP = "M0-7C2.6-1.6 3.4.8 3.4 2.6a3.4 3.4 0 0 1-6.8 0C-3.4.8-2.6-1.6 0-7z"
_STREAK = "M0-15C1.7-6 2.5-1 2.5 1.8a2.5 2.5 0 0 1-5 0C-2.5-1-1.7-6 0-15z"
_RAYS = "".join(
    "M%.0f %.0fL%.0f %.0fL%.0f %.0fZ" % (
        22 * math.cos(math.radians(a - 4)), 22 * math.sin(math.radians(a - 4)),
        74 * math.cos(math.radians(a - 6)), 74 * math.sin(math.radians(a - 6)),
        74 * math.cos(math.radians(a + 6)), 74 * math.sin(math.radians(a + 6)))
    for a in range(0, 360, 30))
_FLAKE_ARMS = "M0-8V8M-6.9-4 6.9 4M-6.9 4 6.9-4M-2-6 0-4.4 2-6M-2 6 0 4.4 2 6M-6.2-1.6-4.4-2.4-4.8-4.4M6.2 1.6 4.4 2.4 4.8 4.4M-6.2 1.6-4.4 2.4-4.8 4.4M6.2-1.6 4.4-2.4 4.8-4.4"
# 초승달: 바깥 원(r14)에서 오른쪽 위로 비킨 원(r12)을 뺀 모양

# 공용 정의 조각 — 이 달에 나오는 날씨에 필요한 것만 싣는다(대시보드 전송 바이트 예산, perf-gate)
_DEF_SUN = (
    '<radialGradient id="tlDisc"><stop offset="0" stop-color="#fffdf0"/><stop offset=".5" stop-color="#ffe066"/><stop offset="1" stop-color="#ffb000"/></radialGradient>'
    '<radialGradient id="tlBloom"><stop offset="0" stop-color="#ffc21f" stop-opacity=".6"/><stop offset="1" stop-color="#ffc21f" stop-opacity="0"/></radialGradient>'
    '<radialGradient id="tlRay"><stop offset=".3" stop-color="#fff6c8" stop-opacity=".95"/><stop offset=".75" stop-color="#ffc94a" stop-opacity=".45"/><stop offset="1" stop-color="#ffc94a" stop-opacity="0"/></radialGradient>'
    f'<path id="tlRays" d="{_RAYS}" fill="url(#tlRay)" transform="scale(1.15)"/>'
    '<circle id="tlSB" r="104" fill="url(#tlBloom)"/><circle id="tlSD" r="17" fill="url(#tlDisc)"/>'
)
_DEF_CLOUD = (
    '<linearGradient id="tlCl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#dfe5ee"/></linearGradient>'
    '<linearGradient id="tlClD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e4e8ef"/><stop offset="1" stop-color="#8592a8"/></linearGradient>'
    f'<path id="tlCloud" d="{_CLOUD}"/>'
)
_DEF_RAIN = (
    '<linearGradient id="tlDz" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7fbcff"/><stop offset="1" stop-color="#1b64d8"/></linearGradient>'
    '<linearGradient id="tlVeil" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3d4f6e" stop-opacity=".28"/><stop offset=".55" stop-color="#3d4f6e" stop-opacity=".12"/><stop offset="1" stop-color="#e8eef8" stop-opacity=".35"/></linearGradient>'
    f'<path id="tlDrop" d="{_DROP}"/>'
)
_DEF_STRONG_RAIN = (
    '<linearGradient id="tlHv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6aaeff"/><stop offset="1" stop-color="#0a47b8"/></linearGradient>'
    '<radialGradient id="tlLit"><stop offset="0" stop-color="#fffbe0" stop-opacity=".95"/><stop offset="1" stop-color="#fffbe0" stop-opacity="0"/></radialGradient>'
    f'<path id="tlStreak" d="{_STREAK}"/>'
    '<ellipse id="tlSplash" rx="3.6" ry="1.1" fill="none" stroke="#3f7fe0" stroke-width="1"/>'
)
_DEF_SNOW = (
    '<g id="tlFlakeB" stroke-linecap="round" fill="none">'
    f'<path d="{_FLAKE_ARMS}" stroke="#3d63a8" stroke-width="3.4"/><path d="{_FLAKE_ARMS}" stroke="#fff" stroke-width="1.7"/></g>'
    '<linearGradient id="tlSnowVeil" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4b67a3" stop-opacity=".26"/><stop offset=".6" stop-color="#6f8cc6" stop-opacity=".14"/><stop offset="1" stop-color="#eef3ff" stop-opacity=".4"/></linearGradient>'
)


def timeline_defs(legend: Iterable[Any] = KINDS) -> Markup:
    """달력 한 장에 한 번 싣는 공용 그림 정의 — 이 달 범례(``cal.wx_legend``: ``[[종류, 이름], ...]``)의 날씨에 필요한 것만."""
    used = {(x[0] if isinstance(x, (list, tuple)) else x) for x in legend}
    parts = []
    if used & {"sun", "partly"}:
        parts.append(_DEF_SUN)
    if used - {"sun", "none"}:
        parts.append(_DEF_CLOUD)
    if used & set(RAIN):
        parts.append(_DEF_RAIN)
    if used & {"rain", "heavy"}:  # 보통 비 이상 = 빗줄기·튐 / 강한 비 = 번개 — 강도는 칸마다라 비 종류로 미리 싣는다
        parts.append(_DEF_STRONG_RAIN)
    if used & set(SNOW):
        parts.append(_DEF_SNOW)
    return Markup('<svg class="foms-wx-defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>'
                  + "".join(parts) + '</defs></svg>')


# ── 자료 → 6시간 칸 ───────────────────────────────────────────────

def _slot(raw: Any, day_kind: str) -> dict[str, Any]:
    if isinstance(raw, dict) and raw.get("k") in KINDS:
        k = raw["k"]
        lv = int(raw.get("lv") if raw.get("lv") is not None else DEFAULT_LV.get(k, 0))
        if k in RAIN:  # 종류와 강도를 맞춘다 — 부슬비 0~1 · 비 2 · 장대비 3 (그림 정의도 종류로 싣는다)
            lv = min(lv, 1) if k == "drizzle" else DEFAULT_LV[k]
        return {"k": k, "lv": lv, "pop": raw.get("pop"), "wind": raw.get("wind")}
    k = raw if raw in KINDS else day_kind
    return {"k": k, "lv": DEFAULT_LV.get(k, 0), "pop": None, "wind": None}


def week_slots(cells: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """띠 안 날짜 칸들 → 6시간 칸 목록(날짜 수 × 4). 칸 자료가 없으면 그날 날씨, 날씨가 없으면 ``none``."""
    out: list[dict[str, Any]] = []
    for c in cells:
        day = str(c.get("wx") or "")
        day = day if day in KINDS else "none"
        detail = c.get("wx_detail") if isinstance(c.get("wx_detail"), list) and len(c["wx_detail"]) == SLOTS_PER_DAY else [None] * SLOTS_PER_DAY
        kinds = c.get("wx_slots") if isinstance(c.get("wx_slots"), list) and len(c["wx_slots"]) == SLOTS_PER_DAY else [None] * SLOTS_PER_DAY
        for i in range(SLOTS_PER_DAY):
            # 칸 자료가 비면(오늘 지난 시간 등) 그 칸 종류(slots) → 없으면 하루 날씨 순으로 채운다
            # (2026-10-15 운영: 15일 0~6시가 하루 대표 '부슬비'로 그려졌다 — 그 칸은 '맑음' 이었다)
            r = detail[i] if isinstance(detail[i], dict) else kinds[i]
            s = _slot(r, day) if day != "none" else {"k": "none", "lv": 0, "pop": None, "wind": None}
            out.append(s)
    return out


def runs(sl: Sequence[Any], pred) -> list[tuple[int, int]]:
    """조건을 만족하는 칸이 이어지는 구간들 ``[(시작, 끝 다음)]``."""
    out, start = [], None
    for i, k in enumerate(list(sl) + [None]):
        if k is not None and pred(k):
            start = i if start is None else start
        elif start is not None:
            out.append((start, i))
            start = None
    return out


def _x(i: float) -> float:
    return i * SLOT_W


def _feather(uid: str, n: int, a: int, b: int, vw: float) -> str:
    """구간 양끝을 44 단위(약 10시간)에 걸쳐 서서히 사라지게 하는 마스크.

    알파 마스크(CSS .tl-m = mask-type: alpha)라 멈춤점은 투명도만 쓴다 — 색·영역 속성을 빼 전송 바이트를 줄였다(perf-gate).
    """
    x0, x1 = _x(a) - FEATHER_OUT, _x(b) + FEATHER_OUT
    edge = min(.5, 44 / (x1 - x0))
    return (f'<linearGradient id="{uid}f{n}" gradientUnits="userSpaceOnUse" x1="{x0:.0f}" x2="{x1:.0f}">'
            f'<stop stop-opacity="0"/><stop offset="{edge:.2f}"/><stop offset="{1 - edge:.2f}"/><stop offset="1" stop-opacity="0"/></linearGradient>'
            f'<mask id="{uid}m{n}" class="tl-m"><rect x="{x0:.0f}" width="{x1 - x0:.0f}" height="{VH}" fill="url(#{uid}f{n})"/></mask>')


def _sky_key(s: dict[str, Any]) -> str:
    # 밤 칸 남색은 뺐다 — 맑은 날 좌우(0~6시·18~24시)가 파랗게 보였다(사용자 2026-10-15: 맑음은 하루 전체가 맑게)
    return s["k"]


def _sky_stops(keys: Sequence[str]) -> list[tuple[float, str]]:
    """바탕 하늘 멈춤점 — 같은 하늘 안은 한 색, 바뀌는 자리는 6시간 칸 3개(18시간)에 걸쳐 섞는다."""
    total = len(keys) * SLOT_W
    out: list[tuple[float, str]] = []
    i = 0
    while i < len(keys):
        j = i
        while j < len(keys) and keys[j] == keys[i]:
            j += 1
        lo, hi = _x(i) + SLOT_W * SKY_BLEND_SLOTS, _x(j) - SLOT_W * SKY_BLEND_SLOTS
        if lo > hi:
            lo = hi = (_x(i) + _x(j)) / 2
        if i == 0:
            lo = 0.0
        if j == len(keys):
            hi = total
        out.append((lo / total, keys[i]))
        if hi > lo:
            out.append((hi / total, keys[i]))
        i = j
    return out


def _pop_opacity(pop: Any) -> float:
    """강수확률 → 비·눈 진하기. 확률 없음(중기·옛 자료)은 1."""
    try:
        p = int(pop)
    except (TypeError, ValueError):
        return 1.0
    return round(.4 + .6 * max(0, min(100, p)) / 100, 2)


def _wind_class(wind: Any) -> int:
    try:
        v = float(wind)
    except (TypeError, ValueError):
        return 0
    return 0 if v < 4 else (1 if v < 9 else 2)


# 강도별 빗방울: (모양, 그라데이션, 간격, 크기, 기본 기울기)
_RAIN_LV = {0: ("tlDrop", "tlDz", 17, 1.05, 6), 1: ("tlDrop", "tlDz", 11, 1.45, 8),
            2: ("tlStreak", "tlHv", 7, 1.0, 14), 3: ("tlStreak", "tlHv", 5, 1.2, 18)}
_WIND_TILT = (0, 12, 24)


def _spans(sl: Sequence[dict[str, Any]], a: int, b: int, key) -> list[tuple[int, int]]:
    """구간 [a, b) 안에서 key 가 같은 이웃 칸끼리 묶은 [(시작, 끝 다음)]."""
    out: list[tuple[int, int]] = []
    i = a
    while i < b:
        j = i + 1
        while j < b and key(sl[j]) == key(sl[i]):
            j += 1
        out.append((i, j))
        i = j
    return out


def _sun(cx: float, cy: float, scale: float) -> str:
    # 멈춘 부분(빛번짐·원반)은 정의 재사용, 움직이는 햇살·숨쉬기만 제자리에(<use> 안쪽엔 움직임이 안 걸린다)
    return (f'<g transform="translate({cx:.0f} {cy}) scale({scale:.2f})"><use href="#tlSB"/>'
            '<g class="up-spin"><use href="#tlRays"/></g><circle class="tl-breathe" r="30"/><use href="#tlSD"/></g>')


def week_band_svg(cells: Sequence[dict[str, Any]], *, uid: str, now_index: Optional[float] = None,
                  still: bool = False, past_days: int = 0) -> Markup:
    """한 주 띠(이 달 날짜만) SVG. now_index: 지금 시각의 날 위치(1.5 = 둘째 날 정오), past_days: 앞쪽 지난 날 수."""
    sl = week_slots(cells)
    kinds = [s["k"] for s in sl]
    vw = DAY_W * len(cells)
    d: list[str] = []
    body: list[str] = []
    n = 0
    sky = _sky_stops([_sky_key(s) for s in sl])
    d.append(f'<linearGradient id="{uid}s" x1="0" x2="1" y1="0" y2="0">'
             + "".join(f'<stop offset="{p:.4f}" class="tl-s-{k}"/>' for p, k in sky) + '</linearGradient>')
    body.append(f'<rect width="{vw:.0f}" height="{VH}" fill="url(#{uid}s)"/>')

    # 해: 낮(6~18시) 칸이 맑음·구름조금인 날마다 그날 가운데에 하나 — 구름조금이 더 많으면 작게(구름 뒤로)
    for day in range(len(cells)):
        noon = sl[day * SLOTS_PER_DAY + 1: day * SLOTS_PER_DAY + 3]
        clear = [x for x in noon if x["k"] in ("sun", "partly")]
        if not clear:
            continue
        partly = sum(1 for x in clear if x["k"] == "partly") * 2 > len(clear)
        cx = day * DAY_W + DAY_W / 2 + 10
        # 맑은 날이 이어지면 날마다 해가 뜬다 → 작게(.78) 위쪽에 두어 건수 숫자를 덜 가린다
        body.append(_sun(cx, 56 if partly else 60, .62 if partly else .78))

    # 구름: 맑음이 아닌 구간 — 구름조금은 듬성듬성 옅게, 흐림·비·눈은 겹겹이(원근 3단)
    sizes = (1.35, .9, 1.15, .75, 1.25, 1.0, .85)
    for a, b in runs(kinds, lambda k: k not in ("sun", "none")):
        n += 1
        d.append(_feather(uid, n, a, b, vw))
        back, front = [], []
        x, j = _x(a) + 2, 0
        while x < _x(b) - 8:
            s = sl[min(int(x // SLOT_W), len(sl) - 1)]
            dark = s["k"] in ("rain", "heavy")
            sc = sizes[j % len(sizes)] * (.85 if s["k"] == "partly" else 1)
            y = 58 + (j * 7) % 18
            front.append(f'<use href="#tlCloud" transform="translate({x:.0f} {y}) scale({sc:.1f})"{' fill="url(#tlClD)"' if dark else ""}/>')
            if s["k"] != "partly" and j % 2 == 0 and not still:  # 뒤 층은 하나 걸러, 멈춘 주는 없이(전송 바이트)
                back.append(f'<use href="#tlCloud" transform="translate({x + 14:.0f} {y - 14}) scale({sc * 1.1:.1f})"{' fill="#9aa7bb"' if dark else ""}/>')
            x += (36 if s["k"] == "partly" else 26) + (j * 11) % 14
            j += 1
        far = "".join(f'<use href="#tlCloud" transform="translate({_x(a) + 8 + 40 * i:.0f} {44 + (i % 2) * 6}) scale(.6)"/>'
                      for i in range(int((_x(b) - _x(a)) // 40) + 1) if not still and sl[min(a + int(i * 40 // SLOT_W), b - 1)]["k"] != "partly")
        edge = ""
        if a > 0 and kinds[a - 1] == "sun" and kinds[a] != "partly":
            edge = f'<use href="#tlCloud" transform="translate({_x(a) - 6:.0f} 50) scale(1.7)" fill="url(#tlClD)" opacity=".75"/>'
        # 같은 칠·투명도는 묶음에 한 번(전송 바이트, perf-gate 2026-10-15)
        body.append(f'<g mask="url(#{uid}m{n})"><g class="up-far" fill="#fff" opacity=".6">{far}</g>'
                    f'<g class="tl-drift2" fill="#fff" opacity=".55">{"".join(back)}</g>'
                    f'{edge}<g class="up-near" fill="url(#tlCl)">{"".join(front)}</g></g>')

    # 비: 칸마다 강도대로(빗방울 수·크기·빠르기), 강수확률만큼 진하게, 바람만큼 눕힌다. 보통 비부터 땅에 튀고, 강한 비엔 번개.
    for a, b in runs(kinds, lambda k: k in RAIN):
        n += 1
        d.append(_feather(uid, n, a, b, vw))
        top = max(s["lv"] for s in sl[a:b])
        veil = f'<rect class="up-veil" x="{_x(a) - FEATHER_OUT:.1f}" width="{_x(b) - _x(a) + 2 * FEATHER_OUT:.1f}" height="{VH}" fill="url(#tlVeil)" opacity="{.55 + .15 * top:.2f}"/>'
        parts = [veil]
        # 강도·바람·강수확률이 같은 이웃 칸은 한 묶음으로 그린다(칸마다 묶음을 만들면 전송 바이트가 크다 — perf-gate)
        for i0, i1 in _spans(sl, a, b, lambda s: (s["lv"], _wind_class(s["wind"]), _pop_opacity(s["pop"]))):
            s = sl[i0]
            shape, grad, step, sc, tilt = _RAIN_LV[max(0, min(3, s["lv"]))]
            wc = _wind_class(s["wind"])
            rot = tilt + _WIND_TILT[wc]
            groups: list[list[str]] = [[], [], []]
            x, j = _x(i0) + 3 + (i0 % 2) * 4, 0
            while x < _x(i1) + 2:
                y = 112 + ((i0 * 5 + j) * 37) % 60
                groups[j % 3].append(f'<use href="#{shape}" transform="translate({x:.0f} {y}) rotate({rot}) scale({sc})"/>')
                x += step
                j += 1
            drops = "".join(f'<g class="tl-r{s["lv"]} tl-w{wc} tl-p{p}" fill="url(#{grad})">{"".join(gr)}</g>' for p, gr in enumerate(groups) if gr)
            if s["lv"] >= 2:
                n_far = 3 * (i1 - i0)
                drops = (f'<g class="up-rainfar" fill="url(#{grad})" opacity=".6">' + "".join(
                    f'<use href="#{shape}" transform="translate({_x(i0) + 5 + 8.3 * q:.0f} {100 + ((i0 + q) * 23) % 70}) rotate({rot - 4}) scale(.6)"/>'
                    for q in range(n_far)) + '</g>' + drops)
                drops += "".join(f'<use href="#tlSplash" class="tl-splash tl-p{q % 2}" x="{_x(i0) + 4 + 12.5 * q:.0f}" y="180"/>'
                                 for q in range(2 * (i1 - i0)))
            op = _pop_opacity(s["pop"])
            parts.append(f'<g opacity="{op}">{drops}</g>' if op < 1 else drops)
        if top >= 3:
            bx = (_x(a) + _x(b)) / 2
            parts.append(f'<ellipse class="tl-flash" cx="{bx:.1f}" cy="70" rx="40" ry="18" fill="url(#tlLit)"/>'
                         f'<path class="tl-flash" d="M{bx:.1f} 82l-8 22h7l-4 18 14-26h-7l5-14z" fill="#ffe14d"/>')
        body.append(f'<g mask="url(#{uid}m{n})">{"".join(parts)}</g>')

    # 눈: 비처럼 진하게(사용자 2026-10-15 — 흰 눈이 옅은 하늘에 묻혀 안 보였다). 굵은 남색 테두리 결정 · 차가운 막 ·
    # 강도대로 촘촘·크게 — 부슬눈은 굵은 점, 보통 눈은 결정, 강한 눈은 더 촘촘한 큰 결정이 바람에 날린다.
    for a, b in runs(kinds, lambda k: k in SNOW):
        n += 1
        d.append(_feather(uid, n, a, b, vw))
        top = max((s["lv"] if s["k"] == "snow" else 0) for s in sl[a:b])
        parts = [f'<rect class="up-veil" x="{_x(a) - FEATHER_OUT:.1f}" width="{_x(b) - _x(a) + 2 * FEATHER_OUT:.1f}" height="{VH}" fill="url(#tlSnowVeil)" opacity="{.75 + .12 * top:.2f}"/>']
        for i0, i1 in _spans(sl, a, b, lambda s: (s["lv"] if s["k"] == "snow" else -1, _pop_opacity(s["pop"]))):
            s = sl[i0]
            lv = s["lv"] if s["k"] == "snow" else -1  # -1 = 부슬눈
            step = {-1: 10, 0: 9, 1: 7, 2: 5.5}[max(-1, min(2, lv))]
            groups: list[list[str]] = [[], [], []]
            x, j = _x(i0) + 3 + (i0 % 2) * 3, 0
            while x < _x(i1) + 2:
                y = 106 + ((i0 * 3 + j) * 29) % 68
                if lv >= 0:
                    sc = (1.15 if j % 3 else 1.5) * (1.15 if lv >= 2 else 1)
                    groups[j % 3].append(f'<use href="#tlFlakeB" transform="translate({x:.0f} {y}) scale({sc:.2f})"/>')
                else:
                    groups[j % 3].append(f'<circle cx="{x:.0f}" cy="{y}" r="{3.6 if j % 3 else 4.6}"/>')
                x += step
                j += 1
            far = "".join(f'<circle cx="{_x(i0) + 3 + 6 * q:.0f}" cy="{92 + ((i0 + q) * 19) % 84}" r="1.9"/>' for q in range(4 * (i1 - i0)))
            cls = "up-blow" if lv >= 2 else "up-sn"
            dots = ' fill="#fff" stroke="#3d63a8" stroke-width="1.6"' if lv < 0 else ""
            flakes = "".join(f'<g class="{cls} tl-p{p}"{dots}>{"".join(gr)}</g>' for p, gr in enumerate(groups) if gr)
            g = f'<g class="up-specks" fill="#fff" stroke="#5b7fbe" stroke-width=".9">{far}</g>{flakes}'
            op = _pop_opacity(s["pop"])
            parts.append(f'<g opacity="{op}">{g}</g>' if op < 1 else g)
        body.append(f'<g mask="url(#{uid}m{n})">{"".join(parts)}</g>')

    if past_days > 0:
        # 지난 날 흐리게: 바탕색(.tl-past = 화면 바탕 색, 투명도 .5) 막을 덮는다. 일부만 지난 주는 오늘 0시 직전에
        # 짧게 걷히는 두 멈춤점 그라데이션 — 하늘 멈춤점을 복사하지 않아 전송 바이트가 작다(perf-gate 2026-10-15).
        px = min(past_days, len(cells)) * DAY_W
        if px >= vw:
            body.append(f'<rect class="tl-past" width="{vw:.0f}" height="{VH}"/>')
        else:
            d.append(f'<linearGradient id="{uid}p" gradientUnits="userSpaceOnUse" x1="{px - 12:.0f}" x2="{px + 4:.0f}">'
                     '<stop class="tl-pv"/><stop offset="1" class="tl-pv" stop-opacity="0"/></linearGradient>')
            body.append(f'<rect class="tl-past is-part" width="{px + 4:.0f}" height="{VH}" fill="url(#{uid}p)"/>')

    if now_index is not None and 0 <= now_index <= len(cells):
        nx = now_index * DAY_W
        body.append(f'<g class="tl-now"><line x1="{nx:.1f}" x2="{nx:.1f}" y1="42" y2="96" stroke="#ff3b30" stroke-width="1" stroke-linecap="round" opacity=".7"/>'
                    f'<circle cx="{nx:.1f}" cy="42" r="2.6" fill="#ff3b30"/>'
                    f'<circle class="up-pulse" cx="{nx:.1f}" cy="42" r="2.6" fill="none" stroke="#ff3b30" stroke-width="1.2"/></g>')
    cls = "tl-svg is-still" if still else "tl-svg"
    return Markup(f'<svg class="{cls}" viewBox="0 0 {vw:.0f} {VH}" preserveAspectRatio="none">'
                  f'<defs>{"".join(d)}</defs>{"".join(body)}</svg>')


def wx_timeline_band(cells: Sequence[dict[str, Any]], uid: str) -> Markup:
    """템플릿용 — 띠 안 날짜 칸으로 주 SVG. 지금 선은 오늘 칸에(KST 지금 시각), 주 전체가 지난 날이면 멈춤."""
    now = now_kst()
    today_iso = now.date().isoformat()
    idx = next((i for i, c in enumerate(cells) if c.get("iso") == today_iso), None)
    now_index = idx + (now.hour + now.minute / 60) / 24 if idx is not None else None
    # 움직임은 오늘부터 7일 안에 날씨가 있는 주만 — 그림 하나라도 움직이면 브라우저가 띠 전체를 매 프레임 다시 그린다
    # (CPU 6배 느리게: 한 달 세 주가 움직이면 35~50fps, 두 주면 50+). 그 밖의 주는 멈춘 그림.
    horizon = (now.date() + timedelta(days=6)).isoformat()
    still = not any(c.get("wx") and today_iso <= str(c.get("iso") or "") <= horizon for c in cells)
    past_days = next((i for i, c in enumerate(cells) if not c.get("is_past")), len(cells))
    return week_band_svg(cells, uid=uid, now_index=now_index, still=still, past_days=past_days)
