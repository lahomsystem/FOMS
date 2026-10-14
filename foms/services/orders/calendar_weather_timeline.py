"""모바일 홈 달력 — '시간 줄' 날씨 띠 (사람마다 고르는 두 번째 보기, 2026-10-14).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §시간 줄 보기 · 목업 '시간 줄 ② 업그레이드'.

한 주 띠를 SVG 한 장으로 그린다. 칸 하나 = 24시간 = 가로 100 단위, 6시간 칸(``slots``) 4개가 25 단위씩이다.
날씨는 날짜 경계가 아니라 **날씨가 바뀌는 시각**에서만 바뀐다 — 같은 날씨가 이어지는 구간(run)마다
해 하나·구름 한 무리·비/눈 한 묶음을 그리고, 구간 양끝은 마스크로 서서히 사라진다.

* 바탕 하늘: 6시간 칸 가운데마다 그 날씨 색을 찍는 가로 그라데이션. 색은 CSS 변수(--wx-*)라 어두운 화면도 따른다.
* 움직임: transform·opacity 만(CSS ``.tl-*``/``.up-*``). 주 전체가 지난 날이면 멈춘다(``is-still``) — 칸 보기와 같은 성능 규칙.
* 오늘 칸에는 지금 시각 빨간 세로선(점이 맥박친다).
* 그림 모양·그라데이션은 달력 한 장에 한 번(:func:`timeline_defs`), 주마다 바뀌는 하늘·마스크만 주 SVG 안에 둔다.

캐시된 달력 페이로드(JSON)는 칸마다 ``wx``·``wx_slots`` 만 들고, 이 그림은 화면을 그릴 때 만든다(지금 선은 매번 새 시각).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional, Sequence

from markupsafe import Markup

from foms.services.datetime_kst import now_kst

__all__ = ["STYLE_COOKIE", "timeline_defs", "week_band_svg", "week_slots", "runs", "wx_style", "wx_timeline_band"]

KINDS = ("sun", "cloud", "drizzle", "heavy", "flurry", "snow")
SLOTS_PER_DAY = 4
DAY_W = 100.0
SLOT_W = DAY_W / SLOTS_PER_DAY
VH = 190  # 띠 비율(한 주 376×102)에 맞춘 높이 — 가로·세로 단위가 거의 같아 그림이 찌그러지지 않는다

_CLOUD = "M0 26a13 13 0 0 1 2-25.8A17 17 0 0 1 34 5a11 11 0 0 1 1 21z"
_DROP = "M0-7C2.6-1.6 3.4.8 3.4 2.6a3.4 3.4 0 0 1-6.8 0C-3.4.8-2.6-1.6 0-7z"
_STREAK = "M0-15C1.7-6 2.5-1 2.5 1.8a2.5 2.5 0 0 1-5 0C-2.5-1-1.7-6 0-15z"
_RAYS = "".join(
    "M%.1f %.1fL%.1f %.1fL%.1f %.1fZ" % (
        22 * math.cos(math.radians(a - 4)), 22 * math.sin(math.radians(a - 4)),
        74 * math.cos(math.radians(a - 6)), 74 * math.sin(math.radians(a - 6)),
        74 * math.cos(math.radians(a + 6)), 74 * math.sin(math.radians(a + 6)))
    for a in range(0, 360, 30))
# 함박눈 결정(칸 보기 fwxFlake 와 같은 모양, 크기만 이 좌표계에 맞춤)
_FLAKE_ARMS = "M0-8V8M-6.9-4 6.9 4M-6.9 4 6.9-4M-2-6 0-4.4 2-6M-2 6 0 4.4 2 6M-6.2-1.6-4.4-2.4-4.8-4.4M6.2 1.6 4.4 2.4 4.8 4.4M-6.2 1.6-4.4 2.4-4.8 4.4M6.2-1.6 4.4-2.4 4.8-4.4"
_FLAKE = ('<g id="tlFlake" stroke-width="1.6" stroke-linecap="round" fill="none">'
          f'<path d="{_FLAKE_ARMS}" stroke="#7d9cc8" stroke-opacity=".45" transform="translate(0 1)"/>'
          f'<path d="{_FLAKE_ARMS}" stroke="#fff"/></g>')

_DEFS = (
    '<svg class="foms-wx-defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>'
    '<radialGradient id="tlDisc"><stop offset="0" stop-color="#fffdf0"/><stop offset=".5" stop-color="#ffe066"/><stop offset="1" stop-color="#ffb000"/></radialGradient>'
    '<radialGradient id="tlBloom"><stop offset="0" stop-color="#ffc21f" stop-opacity=".6"/><stop offset="1" stop-color="#ffc21f" stop-opacity="0"/></radialGradient>'
    '<radialGradient id="tlRay"><stop offset=".3" stop-color="#fff6c8" stop-opacity=".95"/><stop offset=".75" stop-color="#ffc94a" stop-opacity=".45"/><stop offset="1" stop-color="#ffc94a" stop-opacity="0"/></radialGradient>'
    '<linearGradient id="tlCl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#dfe5ee"/></linearGradient>'
    '<linearGradient id="tlClD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e4e8ef"/><stop offset="1" stop-color="#8592a8"/></linearGradient>'
    '<linearGradient id="tlDz" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7fbcff"/><stop offset="1" stop-color="#1b64d8"/></linearGradient>'
    '<linearGradient id="tlHv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6aaeff"/><stop offset="1" stop-color="#0a47b8"/></linearGradient>'
    '<linearGradient id="tlVeil" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3d4f6e" stop-opacity=".28"/><stop offset=".55" stop-color="#3d4f6e" stop-opacity=".12"/><stop offset="1" stop-color="#e8eef8" stop-opacity=".35"/></linearGradient>'
    '<radialGradient id="tlLit"><stop offset="0" stop-color="#fffbe0" stop-opacity=".95"/><stop offset="1" stop-color="#fffbe0" stop-opacity="0"/></radialGradient>'
    f'<path id="tlCloud" d="{_CLOUD}"/><path id="tlDrop" d="{_DROP}"/><path id="tlStreak" d="{_STREAK}"/>'
    f'<path id="tlRays" d="{_RAYS}"/>{_FLAKE}'
    '</defs></svg>'
)


def timeline_defs() -> Markup:
    """달력 한 장에 한 번 싣는 공용 그림 정의(그라데이션·구름·빗방울·햇살·눈 결정)."""
    return Markup(_DEFS)


def week_slots(cells: Iterable[dict[str, Any]]) -> list[str]:
    """띠 안 날짜 칸들 → 6시간 칸 날씨 목록(날짜 수 × 4). 칸 값이 없으면 그날 날씨, 날씨가 없으면 ``none``."""
    out: list[str] = []
    for c in cells:
        day = str(c.get("wx") or "") or "none"
        raw = c.get("wx_slots")
        raw = raw if isinstance(raw, list) and len(raw) == SLOTS_PER_DAY else [None] * SLOTS_PER_DAY
        out.extend(k if (day != "none" and k in KINDS) else day for k in raw)
    return out


def runs(sl: Sequence[str], pred) -> list[tuple[int, int]]:
    """조건을 만족하는 칸이 이어지는 구간들 ``[(시작, 끝 다음)]``."""
    out, start = [], None
    for i, k in enumerate(list(sl) + [None]):
        if k is not None and pred(k):
            start = i if start is None else start
        elif start is not None:
            out.append((start, i))
            start = None
    return out


def _x(i: int) -> float:
    return i * SLOT_W


def _feather(uid: str, n: int, a: int, b: int, vw: float) -> str:
    """구간 양끝을 30 단위(약 7시간, 폰에서 16px)에 걸쳐 서서히 사라지게 하는 마스크 — 짧으면 물안개 막 끝이 칼선처럼 보인다."""
    x0, x1 = _x(a) - 10, _x(b) + 10
    edge = min(.5, 30 / (x1 - x0))
    return (f'<linearGradient id="{uid}f{n}" gradientUnits="userSpaceOnUse" x1="{x0:.1f}" x2="{x1:.1f}" y1="0" y2="0">'
            f'<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="{edge:.3f}" stop-color="#fff"/>'
            f'<stop offset="{1 - edge:.3f}" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<mask id="{uid}m{n}" maskUnits="userSpaceOnUse" x="0" y="0" width="{vw:.0f}" height="{VH}">'
            f'<rect x="{x0:.1f}" width="{x1 - x0:.1f}" height="{VH}" fill="url(#{uid}f{n})"/></mask>')


def _sky_stops(sl: Sequence[str]) -> list[tuple[float, str]]:
    """바탕 하늘 색 멈춤점 — 같은 날씨 구간 안은 한 색, 바뀌는 자리는 6시간 칸 2개(반나절)에 걸쳐 섞는다.

    칸 가운데마다 찍으면 섞이는 폭이 6시간(폰에서 13px)이라 경계가 칼로 자른 듯 보인다.
    """
    total = len(sl) * SLOT_W
    out: list[tuple[float, str]] = []
    i = 0
    while i < len(sl):
        j = i
        while j < len(sl) and sl[j] == sl[i]:
            j += 1
        lo, hi = _x(i) + SLOT_W, _x(j) - SLOT_W
        if lo > hi:
            lo = hi = (_x(i) + _x(j)) / 2
        if i == 0:
            lo = 0.0
        if j == len(sl):
            hi = total
        out.append((lo / total, sl[i]))
        if hi > lo:
            out.append((hi / total, sl[i]))
        i = j
    return out


def week_band_svg(cells: Sequence[dict[str, Any]], *, uid: str, now_index: Optional[float] = None,
                  still: bool = False) -> Markup:
    """한 주 띠(이 달 날짜만) SVG.

    cells: 띠 안 날짜 칸(``wx``·``wx_slots``). uid: 문서 안에서 겹치지 않는 접두어(주마다).
    now_index: 지금 시각의 칸 위치(0 = 띠 첫날 0시, 1.5 = 둘째 날 정오). None 이면 지금 선 없음.
    still: 움직임 없이(주 전체가 지난 날).
    """
    sl = week_slots(cells)
    vw = DAY_W * len(cells)
    d: list[str] = []
    body: list[str] = []
    n = 0
    stops = "".join(f'<stop offset="{pos:.4f}" class="tl-s-{k}"/>' for pos, k in _sky_stops(sl))
    d.append(f'<linearGradient id="{uid}s" x1="0" x2="1" y1="0" y2="0">{stops}</linearGradient>')
    body.append(f'<rect width="{vw:.0f}" height="{VH}" fill="url(#{uid}s)"/>')

    # 해: 맑음이 이어지는 구간마다 한가운데 해 하나 — 빛번짐이 떠다니며 숨쉬고 햇살은 30초에 한 바퀴
    for a, b in runs(sl, lambda k: k == "sun"):
        cx = (_x(a) + _x(b)) / 2 + 12
        body.append(f'<g transform="translate({cx:.1f} 70)"><g class="up-glow"><circle r="92" fill="url(#tlBloom)"/></g>'
                    '<g class="up-spin"><use href="#tlRays" fill="url(#tlRay)" opacity=".85"/></g>'
                    '<circle class="tl-breathe" r="30" fill="#ffe27a"/><circle r="17" fill="url(#tlDisc)"/></g>')

    # 구름: 맑음이 아닌 구간 전체 — 원근 3단(먼 층 작고 옅고 느림 · 가운데 · 가까운 층 크고 빠름)
    sizes = (1.35, .9, 1.15, .75, 1.25, 1.0, .85)
    for a, b in runs(sl, lambda k: k not in ("sun", "none")):
        n += 1
        d.append(_feather(uid, n, a, b, vw))
        back, front = [], []
        x, j = _x(a) + 2, 0
        while x < _x(b) - 8:
            dark = sl[min(int(x // SLOT_W), len(sl) - 1)] == "heavy"
            sc = sizes[j % len(sizes)]
            y = 58 + (j * 7) % 18
            front.append(f'<use href="#tlCloud" transform="translate({x:.1f} {y}) scale({sc:.2f})" fill="url(#{"tlClD" if dark else "tlCl"})"/>')
            back.append(f'<use href="#tlCloud" transform="translate({x + 14:.1f} {y - 14}) scale({sc * 1.1:.2f})" fill="{"#9aa7bb" if dark else "#fff"}" opacity=".55"/>')
            x += 20 + (j * 11) % 14
            j += 1
        w = _x(b) - _x(a)
        far = "".join(f'<use href="#tlCloud" transform="translate({_x(a) + 8 + 23 * i:.1f} {44 + (i % 2) * 6}) scale(.6)" fill="#fff" opacity=".45"/>'
                      for i in range(int(w // 23) + 1))
        edge = ""
        if a > 0 and sl[a - 1] == "sun":
            # 맑음 → 궂음으로 바뀌는 자리에 짙은 구름 벽
            edge = f'<use href="#tlCloud" transform="translate({_x(a) - 6:.1f} 50) scale(1.7)" fill="url(#tlClD)" opacity=".75"/>'
        body.append(f'<g mask="url(#{uid}m{n})"><g class="up-far">{far}</g><g class="tl-drift2">{"".join(back)}</g>'
                    f'{edge}<g class="up-near">{"".join(front)}</g></g>')

    # 비: 부슬비는 듬성, 장대비는 촘촘·빠르게(세 묶음) + 먼 빗줄기 층 + 물안개 막, 장대비는 먹구름 속 번개
    for kind, shape, grad, step, cls in (("drizzle", "tlDrop", "tlDz", 14, "tl-dz"), ("heavy", "tlStreak", "tlHv", 7, "tl-hv")):
        for a, b in runs(sl, lambda k, kind=kind: k == kind):
            n += 1
            d.append(_feather(uid, n, a, b, vw))
            groups: list[list[str]] = [[], [], []]
            x, j = _x(a) + 3, 0
            rot, sc = (18, "1") if kind == "heavy" else (8, "1.3")
            while x < _x(b):
                y = 112 + (j * 37) % 60
                groups[j % 3].append(f'<use href="#{shape}" transform="translate({x:.1f} {y}) rotate({rot}) scale({sc})" fill="url(#{grad})"/>')
                x += step
                j += 1
            far = "".join(f'<use href="#{shape}" transform="translate({_x(a) + 5 + 9 * i:.1f} {100 + (i * 23) % 70}) rotate({14 if kind == "heavy" else 6}) scale(.55)" fill="url(#{grad})" opacity=".45"/>'
                          for i in range(int((_x(b) - _x(a)) // 9)))
            # 물안개 막은 마스크 범위(구간 ±10)까지 넓혀야 끝이 마스크로 사라진다 — 구간 폭 그대로면 끝이 칼선
            extra = f'<rect class="up-veil" x="{_x(a) - 10:.1f}" width="{_x(b) - _x(a) + 20:.1f}" height="{VH}" fill="url(#tlVeil)"/>'
            if kind == "heavy":
                bx = (_x(a) + _x(b)) / 2
                extra += (f'<ellipse class="tl-flash" cx="{bx:.1f}" cy="70" rx="40" ry="18" fill="url(#tlLit)"/>'
                          f'<path class="tl-flash" d="M{bx:.1f} 82l-8 22h7l-4 18 14-26h-7l5-14z" fill="#ffe14d"/>')
            drops = "".join(f'<g class="{cls} tl-p{p}">{"".join(gr)}</g>' for p, gr in enumerate(groups))
            body.append(f'<g mask="url(#{uid}m{n})">{extra}<g class="up-rainfar">{far}</g>{drops}</g>')

    # 눈: 부슬눈은 듬성 점, 함박눈은 촘촘 결정(천천히 돌며) + 먼 눈송이
    for kind, step, r in (("flurry", 22, 2.2), ("snow", 11, 3.4)):
        for a, b in runs(sl, lambda k, kind=kind: k == kind):
            n += 1
            d.append(_feather(uid, n, a, b, vw))
            groups = [[], []]
            x, j = _x(a) + 4, 0
            while x < _x(b):
                y = 112 + (j * 29) % 62
                if kind == "snow":
                    groups[j % 2].append(f'<use href="#tlFlake" transform="translate({x:.1f} {y}) scale({.75 if j % 3 else 1.0:.2f})"/>')
                else:
                    groups[j % 2].append(f'<circle cx="{x:.1f}" cy="{y}" r="{r if j % 3 else r * 1.3:.1f}" fill="#fff" stroke="#9db6dc" stroke-width=".7"/>')
                x += step
                j += 1
            specks = "".join(f'<circle cx="{_x(a) + 3 + 7 * i:.1f}" cy="{96 + (i * 19) % 80}" r="1.3" fill="#fff" opacity=".8"/>'
                             for i in range(int((_x(b) - _x(a)) // 7)))
            flakes = "".join(f'<g class="up-sn tl-p{p}">{"".join(gr)}</g>' for p, gr in enumerate(groups))
            body.append(f'<g mask="url(#{uid}m{n})"><g class="up-specks">{specks}</g>{flakes}</g>')

    if now_index is not None and 0 <= now_index <= len(cells):
        nx = now_index * DAY_W
        body.append(f'<g class="tl-now"><line x1="{nx:.1f}" x2="{nx:.1f}" y1="40" y2="{VH - 30}" stroke="#ff3b30" stroke-width="1.6" stroke-linecap="round" opacity=".85"/>'
                    f'<circle cx="{nx:.1f}" cy="40" r="3.4" fill="#ff3b30"/>'
                    f'<circle class="up-pulse" cx="{nx:.1f}" cy="40" r="3.4" fill="none" stroke="#ff3b30" stroke-width="1.4"/></g>')
    cls = "tl-svg is-still" if still else "tl-svg"
    return Markup(f'<svg class="{cls}" viewBox="0 0 {vw:.0f} {VH}" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
                  f'<defs>{"".join(d)}</defs>{"".join(body)}</svg>')


# ── 화면 그릴 때 (Jinja 전역) ─────────────────────────────────────

#: 사람마다 고르는 날씨 보기 쿠키 — ``cell``(기본, 칸마다 그림) · ``timeline``(시간 줄). 버튼이 브라우저에서 저장한다.
STYLE_COOKIE = "foms_wx_style"
STYLES = ("cell", "timeline")


def wx_style(cookies: Any) -> str:
    """요청 쿠키 → 날씨 보기. 모르는 값·없음은 기본 ``cell``."""
    value = str((cookies or {}).get(STYLE_COOKIE) or "")
    return value if value in STYLES else "cell"


def wx_timeline_band(cells: Sequence[dict[str, Any]], uid: str) -> Markup:
    """템플릿용 — 띠 안 날짜 칸으로 주 SVG. 지금 선은 오늘 칸에(KST 지금 시각), 주 전체가 지난 날이면 멈춤."""
    now = now_kst()
    today_iso = now.date().isoformat()
    idx = next((i for i, c in enumerate(cells) if c.get("iso") == today_iso), None)
    now_index = idx + (now.hour + now.minute / 60) / 24 if idx is not None else None
    still = bool(cells) and all(c.get("is_past") for c in cells)
    return week_band_svg(cells, uid=uid, now_index=now_index, still=still)
