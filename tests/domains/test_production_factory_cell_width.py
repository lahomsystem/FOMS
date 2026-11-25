"""생산 첫 화면 도면 칸 — 섞인 주문 "[2공장] 1장 완료"가 한 줄(2026-11-24 검토 1: PC 끝 칸 5rem · 태블릿 92px 에서 "완료"가 떨어졌다).

- 줄마다 ``white-space: nowrap`` + 끝 칸이 글자 배율을 따르는 폭: PC 6.75rem(뿌리 글자가 100% × 배율이라 rem 이 배율을 따른다),
  태블릿 ``calc(108px * var(--foms-fs, 1))``. 실측 "2공장 1장 완료" 93.4px(배율 1) · 110 · 135 → "12장"까지 ≈ 102px × 배율.
- 칸 폭을 바꾸면 접는 문턱(컨테이너 쿼리 — var() 를 못 쓴다)도 같은 합으로: 이 시험이 칸 합과 문턱을 견준다.
되돌리면 실패: nowrap 빼기 · 끝 칸을 px 고정 · 폭만 늘리고 문턱 그대로.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PC = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
HOME = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
NEED_REM = 102 / 16  # "2공장 12장 완료"(14px 굵게 + 칩) ≈ 102px × 배율


def _min_rem(template: str) -> float:
    total = 0.0
    for col in re.findall(r"minmax\(([\d.]+)rem,[^)]*\)|([\d.]+)rem", template):
        total += float(col[0] or col[1])
    return total


def test_pc_last_column_follows_font_scale_and_thresholds_match():
    assert re.search(r"html\[data-foms-fs\] \{\s*font-size: calc\(100% \* var\(--foms-fs, 1\)\);",
                     (ROOT / "static/css/components/foms-ui-zoom.css").read_text(encoding="utf-8"))  # rem = 16px × 배율
    wide = re.search(r"\.fpc-r \{ display: grid; grid-template-columns: ([^;]+);", PC).group(1)
    narrow = re.search(r"\.fpc-r:not\(\.fpc-r--mini\) \{ grid-template-columns: (8\.5rem 7rem minmax\(10rem[^;]+);", PC).group(1)
    huge = re.search(r"\.fpc-r:not\(\.fpc-r--mini\) \{ grid-template-columns: (9rem 8rem[^;]+);", PC).group(1)
    for tpl in (wide, narrow, huge):
        last = tpl.split()[-1]
        assert last.endswith("rem") and float(last[:-3]) >= NEED_REM, tpl  # px 고정이 아니고, 한 줄 폭 이상
    assert f"@container fpc (max-width: calc({_min_rem(wide):g}rem + 78px - 0.02px))" in PC
    assert f"@container fpc (max-width: calc({_min_rem(narrow):g}rem + 68px - 0.02px))" in PC
    assert "white-space: nowrap" in re.search(r"\.fpc-dw\.is-split \.fph-fac \{([^}]*)\}", PC).group(1)


def test_tablet_last_column_follows_font_scale_and_thresholds_match():
    col = re.search(r"grid-template-columns: 128px minmax\(0, 1fr\) auto calc\((\d+)px \* var\(--foms-fs, 1\)\);", HOME)
    px = int(col.group(1))
    assert px / 16 >= NEED_REM
    two_line = 15 + px / 16  # 이름 12 × 1.25rem + 도면 칸
    hide_name = 20 + px / 16  # 이름 16 × 1.25rem + 도면 칸
    assert f"@container fph-pane (max-width: calc(196px + 4 * max(34px, 1.5rem) + {two_line:g}rem - 0.02px))" in HOME
    assert f"@container fph-pane (max-width: calc(190px + 4 * 4.75rem + {hide_name:g}rem - 0.02px))" in HOME
    assert "white-space: nowrap" in re.search(r"\.fph-dr__dw\.is-split \.fph-fac \{([^}]*)\}", HOME).group(1)
