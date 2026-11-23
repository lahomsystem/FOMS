"""상태 색 시험 도구 — CIEDE2000 색 차이 · 색약 흉내 · WCAG 글 대비(순수 계산, 새 패키지 없음).

상태 색 쌍 규칙(사장님 2026-11-13 '무채색 배지 금지' 뒤 상시 규칙): 짝마다 ΔE2000 ≥ 10(정상 시각) · ≥ 6(녹색맹 · 적색맹 흉내),
글 대비 ≥ 4.5:1(큰 굵은 글 ≥ 3:1). 색약 흉내 = Machado · Oliveira · Fernandes(2009) 정도 1.0 행렬, 선형 sRGB 에서 곱한다.
"""
from __future__ import annotations

import math
from typing import Sequence

DEUTERANOPIA = ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881))
PROTANOPIA = ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998))
RGB = Sequence[float]


def hex_rgb(value: str) -> tuple[int, int, int]:
    """'#b91c1c' → (185, 28, 28)."""
    text = value.strip().lstrip('#')
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _to_linear(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(v: float) -> float:
    v = min(max(v, 0.0), 1.0)
    return 255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)


def blend(fg: RGB, alpha: float, bg: RGB) -> tuple[float, float, float]:
    """반투명 글(rgba)을 바탕 위에 얹은 색."""
    return tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))  # type: ignore[return-value]


def simulate(rgb: RGB, matrix=DEUTERANOPIA) -> tuple[float, float, float]:
    """색약 흉내(선형 sRGB 에서 행렬 곱)."""
    lin = [_to_linear(c) for c in rgb]
    return tuple(_to_srgb(sum(matrix[i][j] * lin[j] for j in range(3))) for i in range(3))  # type: ignore[return-value]


def _lab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e2000(c1: RGB, c2: RGB) -> float:
    """CIEDE2000 색 차이(sRGB 0~255 두 색)."""
    (l1, a1, b1), (l2, a2, b2) = _lab(c1), _lab(c2)
    cbar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(cbar ** 7 / (cbar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = math.degrees(math.atan2(b1, a1p)) % 360, math.degrees(math.atan2(b2, a2p)) % 360
    dh = 0.0 if c1p * c2p == 0 else (h2p - h1p + 180) % 360 - 180
    d_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    lbp, cbp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.2 * math.cos(math.radians(4 * hbp - 63)))
    rc = 2 * math.sqrt(cbp ** 7 / (cbp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / math.sqrt(20 + (lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * cbp, 1 + 0.015 * cbp * t
    rt = -math.sin(math.radians(60 * math.exp(-((hbp - 275) / 25) ** 2))) * rc
    dl, dc, dhh = (l2 - l1) / sl, (c2p - c1p) / sc, d_hp / sh
    return math.sqrt(dl ** 2 + dc ** 2 + dhh ** 2 + rt * dc * dhh)


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    """WCAG 2 글 대비."""
    def lum(c: RGB) -> float:
        r, g, b = (_to_linear(v) for v in c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    a, b = lum(fg), lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def pair_distances(a: RGB, b: RGB) -> tuple[float, float, float]:
    """(정상, 녹색맹 흉내, 적색맹 흉내) ΔE2000."""
    return (delta_e2000(a, b), delta_e2000(simulate(a, DEUTERANOPIA), simulate(b, DEUTERANOPIA)),
            delta_e2000(simulate(a, PROTANOPIA), simulate(b, PROTANOPIA)))
