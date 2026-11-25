"""공장 칩(1공장 · 2공장) — 색 · 거리 · 대비 · 한 곳 원칙(사장님 2026-11-24 "1공장, 2공장 구분이 잘 안 돼 > 식별성 업그레이드").

- 두 공장 모두 색 칩(무채색 아님): 1공장 자주 · 2공장 청록. 값은 ``static/css/components/foms-factory-chip.css`` 한 곳.
- 두 칩 바탕 · 테두리 · 글 색 짝마다 ΔE2000 ≥ 10(정상) · ≥ 6(녹색맹 · 적색맹 흉내) — 밝은 · 어두운 화면 모두.
- 같은 화면 상태 색(완료 초록 · 작업 필요 연보라 · 늦음 빨강 · 보류/바뀜 주황 · 기본 단추 남색)과 칩 바탕끼리 · 칩 글끼리 ΔE2000 ≥ 10
  — 상태 값은 그 화면 CSS 토큰에서 읽는다(값이 바뀌면 여기서 다시 잰다).
- 칩 글 대비 ≥ 4.5:1, 테두리는 판 바탕과 ≥ 3:1. 생산 화면(늘 밝은 판)은 어두운 화면 설정에서도 밝은 값.
- 화면 글은 그대로 — 거르개 ``factory_chips`` 는 공장 이름만 감싼다(빈 글 · 공장 이름 없는 글은 바이트 그대로).
- 칩 모양 파일은 한 주소(같은 ?v=)로만 싣는다 — <link> 와 @import 가 같은 주소라 두 번 받지 않는다.

되돌리면 실패: 2공장을 '완료' 초록 가까이(옛 #0f6b63) · 1공장 무채색 · 공장 CSS 가 공장 색을 따로 둠 · 칩 글 바꿈 · 핀 어긋남.
"""
from __future__ import annotations

import colorsys
import re
from itertools import product
from pathlib import Path

import pytest
from markupsafe import Markup

from foms.services.production.factory_chip import factory_chips
from tests.support.color_contrast import contrast_ratio, hex_rgb, pair_distances

ROOT = Path(__file__).resolve().parents[2]
CHIP = ROOT / "static/css/components/foms-factory-chip.css"
CHIP_URL = "foms-factory-chip.css?v="
LIGHT = {"fac1": {"fill": "#f0abfc", "line": "#a21caf", "ink": "#86198f"},
         "fac2": {"fill": "#a5f3fc", "line": "#0891b2", "ink": "#164e63"}}
DARK = {"fac1": {"fill": "#701a75", "line": "#e879f9", "ink": "#f5d0fe"},
        "fac2": {"fill": "#0e7490", "line": "#67e8f9", "ink": "#ecfeff"}}
LIGHT_SURFACES = ("#ffffff", "#eef0f3", "#f7f8fa")  # 흰 칸 · 판 바탕 · 떠 있는 칸
DARK_SURFACES = ("#0a0c10", "#14171c", "#22262e")  # foms-tokens.css 어두운 바탕 셋


def _code(rel: str) -> str:
    return re.sub(r"/\*.*?\*/", "", (ROOT / rel).read_text(encoding="utf-8"), flags=re.S)


def _block(css: str, head: str) -> dict[str, str]:
    """선택자 ``head`` 덩이의 --foms-fac 토큰."""
    body = re.search(re.escape(head) + r"\s*\{([^}]*)\}", css).group(1)
    return dict(re.findall(r"--foms-(fac[12]-(?:fill|line|ink)):\s*(#[0-9a-f]{6});", body))


def _flat(table: dict) -> dict[str, str]:
    return {f"{f}-{k}": v for f, kv in table.items() for k, v in kv.items()}


def _tokens(*rels: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in rels:
        out.update(dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-f]{6});", _code(rel))))
    return out


def test_token_values_light_dark_and_production_stays_light():
    css = _code("static/css/components/foms-factory-chip.css")
    assert _block(css, ":root") == _flat(LIGHT)
    assert _block(css, "[data-theme='dark']") == _flat(DARK)
    # 생산 화면은 늘 밝은 판(토큰이 고정) — 어두운 설정에서도 밝은 칩
    # 늘 밝은 자리(생산 판 · 흰 바탕 고정 공장 고르기 단추 .dsf-sel) — 어두운 설정에서도 밝은 칩 값
    assert _block(css, "[data-theme='dark'] .foms-prod-home,\n[data-theme='dark'] .foms-prod-page,\n[data-theme='dark'] .dsf-sel") == _flat(LIGHT)
    assert "font-size" not in css  # 놓인 줄 글자 그대로(줄이지 않는다)
    for n in (1, 2):
        rule = re.search(r"\.foms-fac--%d \{([^}]*)\}" % n, css).group(1)
        assert f"var(--foms-fac{n}-fill)" in rule and f"var(--foms-fac{n}-line)" in rule and f"var(--foms-fac{n}-ink)" in rule


@pytest.mark.parametrize("table", [LIGHT, DARK], ids=["light", "dark"])
def test_two_factories_differ_for_normal_and_colour_blind_eyes(table):
    for key in ("fill", "line", "ink"):
        normal, deu, pro = pair_distances(hex_rgb(table["fac1"][key]), hex_rgb(table["fac2"][key]))
        assert normal >= 10 and deu >= 6 and pro >= 6, (key, round(normal, 1), round(deu, 1), round(pro, 1))


@pytest.mark.parametrize("table,surfaces", [(LIGHT, LIGHT_SURFACES), (DARK, DARK_SURFACES)], ids=["light", "dark"])
def test_contrast_and_not_achromatic(table, surfaces):
    for fac in table.values():
        assert contrast_ratio(hex_rgb(fac["ink"]), hex_rgb(fac["fill"])) >= 4.5, fac
        for surface in surfaces:
            assert contrast_ratio(hex_rgb(fac["line"]), hex_rgb(surface)) >= 3, (fac["line"], surface)
        r, g, b = hex_rgb(fac["fill"])
        assert colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[2] >= 0.3, fac  # 무채색 칩 금지(D52)


def _status() -> tuple[dict[str, str], dict[str, str]]:
    """같은 화면 상태 색 — 생산 · 출고 패킹 CSS 토큰에서 읽는다(바탕 · 글)."""
    tok = _tokens("static/css/contexts/production/home.css", "static/css/contexts/production/parts.css",
                  "static/css/contexts/production/pc.css", "static/css/components/foms-packing-factory.css")
    fills = {"완료": ("--fph-done-50", "--fph-done-300", "--foms-pf-done-50"), "작업 필요": ("--fph-need-50",),
             "늦음": ("--fph-danger-50", "--fph-revise-50"), "보류 · 바뀜": ("--fph-hold-50", "--fph-old-50", "--fpc-hold-50"),
             "기본 단추": ("--fph-brand", "--fph-brand-dark", "--fph-brand-50")}
    inks = {"완료": ("--fph-done-700", "--fph-done-800", "--fph-ok"), "작업 필요": ("--fph-need-700",),
            "늦음": ("--fph-dw-late", "--fph-danger"), "보류 · 바뀜": ("--fph-hold-700", "--fph-warn", "--fpc-hold"),
            "기본 단추": ("--fph-brand", "--fph-brand-dark")}
    return ({f"{k} {t}": tok[t] for k, ts in fills.items() for t in ts},
            {f"{k} {t}": tok[t] for k, ts in inks.items() for t in ts})


def test_chips_stay_away_from_status_colours_on_the_same_screens():
    fills, inks = _status()
    assert fills["완료 --fph-done-50"] == "#a7f3d0" and inks["작업 필요 --fph-need-700"] == "#3a4490"  # 읽은 값 확인
    for fac, (name, status) in product(LIGHT.values(), fills.items()):
        normal = pair_distances(hex_rgb(fac["fill"]), hex_rgb(status))[0]
        assert normal >= 10, (fac["fill"], name, round(normal, 1))
    for fac, (name, status) in product(LIGHT.values(), inks.items()):
        normal = pair_distances(hex_rgb(fac["ink"]), hex_rgb(status))[0]
        assert normal >= 10, (fac["ink"], name, round(normal, 1))
    # 옛 2공장 청록(#0f6b63)은 '완료' 초록 글과 가까웠다 — 음성 대조군(이 시험이 그것을 잡는지)
    assert pair_distances(hex_rgb("#0f6b63"), hex_rgb(inks["완료 --fph-done-800"]))[0] < 10


def test_filter_wraps_only_factory_names_and_keeps_text():
    out = factory_chips("상차 1공장 2장 · 2공장 1장(제작 중)")
    assert isinstance(out, Markup)
    assert out == ('상차 <em class="foms-fac foms-fac--1">1공장</em> 2장 · '
                   '<em class="foms-fac foms-fac--2">2공장</em> 1장(제작 중)')
    assert re.sub(r"<[^>]+>", "", str(out)) == "상차 1공장 2장 · 2공장 1장(제작 중)"  # 글은 그대로
    assert factory_chips(None) is None and factory_chips("") == ""
    assert factory_chips("포장 3/4") == "포장 3/4" and factory_chips("<b>") == "&lt;b&gt;"  # 공장 이름 없음 = 이스케이프만


def test_one_url_for_the_chip_file_and_no_factory_colours_elsewhere():
    pins = set()
    for rel in ("templates/production/partials/home_styles.html", "templates/production/sheet.html", "templates/auth/user_list.html"):
        pins |= set(re.findall(r"foms-factory-chip\.css'\) \}\}\?v=(\w+)", (ROOT / rel).read_text(encoding="utf-8")))
    for rel in ("static/css/components/foms-load-split.css", "static/css/components/foms-packing-factory.css",
                "static/css/contexts/drawing/sheet-factory.css"):
        code = _code(rel)
        assert code.lstrip().startswith("@import url("), rel  # 첫 규칙(@import 는 맨 앞이어야 먹는다)
        pins |= set(re.findall(r"foms-factory-chip\.css\?v=(\w+)", code))
        assert not re.search(r"--(?:dsf|foms-load2|foms-pf)-fac", code) and "#0f6b63" not in code, rel
    assert len(pins) == 1, pins  # 같은 주소 — 두 번 받지 않는다


def test_scripts_draw_the_same_chip():
    for rel in ("static/js/production/foms-production-pc-sheet.js", "static/js/shipment/foms-packing-factory-view.js",
                "static/js/drawing/workbench-sheet-factory.js"):
        assert "'foms-fac foms-fac--'" in (ROOT / rel).read_text(encoding="utf-8"), rel
    view = (ROOT / "static/js/shipment/foms-packing-factory-view.js").read_text(encoding="utf-8")
    assert "facText: facText" in view and "split(/([12]공장)/)" in view
    pk = (ROOT / "static/js/shipment/foms-packing-factory.js").read_text(encoding="utf-8")
    assert pk.count("V().facText(") == 2  # [패킹] 숫자 글 · 상차 완료 단추 되돌리기도 칩을 지킨다


def test_ink_only_places_are_white_backed_and_kept_light():
    """칩 글 색만 쓰고 바탕은 고정색인 자리 — 어두운 화면 값(밝은 글)이 흰 바탕에 앉으면 대비 1.37 · 1.04(2026-11-24 검토 4).
    그런 자리는 도면 공장 고르기 단추(.dsf-sel__b, 바탕 흰색 고정)뿐이고, 칩 파일이 .dsf-sel 을 '늘 밝은 자리'로 둔다."""
    ink_only = set()
    for path in (ROOT / "static/css").rglob("*.css"):
        if path.name == CHIP.name:
            continue
        code = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", code):
            if re.search(r"(?<![-\w])color:\s*var\(--foms-fac[12]-ink\)", body) and "-fill)" not in body:
                ink_only |= {s.strip() for s in sel.split(",")}
    assert ink_only == {".dsf-sel__b.is-1", ".dsf-sel__b.is-2"}, ink_only
    base = re.search(r"\.dsf-sel__b \{([^}]*)\}", _code("static/css/contexts/drawing/sheet-factory.css")).group(1)
    assert "background: #fff" in base
    assert "[data-theme='dark'] .dsf-sel {" in _code("static/css/components/foms-factory-chip.css")
    for fac in ("fac1", "fac2"):
        assert contrast_ratio(hex_rgb(LIGHT[fac]["ink"]), hex_rgb("#ffffff")) >= 4.5  # 고르기 전(흰 바탕)
        assert contrast_ratio(hex_rgb(LIGHT[fac]["ink"]), hex_rgb(LIGHT[fac]["fill"])) >= 4.5  # 고른 뒤(칩 바탕)
        assert contrast_ratio(hex_rgb(DARK[fac]["ink"]), hex_rgb("#ffffff")) < 2  # 음성 대조 — 어두운 값이면 안 읽힌다


def test_line_filter_keeps_text_and_makes_one_chunk_per_factory():
    from foms.services.production.factory_chip import factory_line_chips

    text = "상차 1공장 2장(제작 중) · 2공장 1장(제작 중)"
    out = str(factory_line_chips(text))
    assert re.sub(r"<[^>]+>", "", out) == text  # 글은 그대로(이어 붙이면 같은 글)
    assert out.count('class="foms-fac-seg"') == 2 and out.count('<span class="foms-fac-sep"> · </span>') == 1
    assert ('<span class="foms-fac-seg">상차 <span class="foms-fac-nw"><em class="foms-fac foms-fac--1">1공장</em> 2장</span>'
            '<wbr><span class="foms-fac-nw">(제작 중)</span></span>') in out  # "상차" 는 첫 몫 첫 줄 앞, "(제작 중)" 은 한 덩이
    assert factory_line_chips(None) is None and factory_line_chips("") == ""
    css = _code("static/css/components/foms-load-split.css")
    # 줄이 갈리면 " · " 가 줄 머리 왼쪽 밖(1em)으로 밀려 가려진다 — 이 네 규칙이 같이 있어야 한다
    for rule in (".foms-fac-line { display: block; overflow: hidden; }",
                 ".foms-fac-line__in { display: block; margin-left: -1em; text-indent: 1em; }",
                 ".foms-fac-seg + .foms-fac-seg { padding-left: 1em; text-indent: -1em; }",
                 ".foms-fac-sep { display: inline-block; width: 1em; text-align: center; text-indent: 0; }"):
        assert rule in css, rule
    for rel in ("templates/shipment/partials/tablet_ship_grid.html", "templates/shipment/partials/dashboard_main.html",
                "templates/shipment/partials/shipment_mobile_queue.html", "templates/shipment/partials/tablet_sheet.html",
                "templates/construction/partials/tablet_first_body.html"):
        assert "| factory_line_chips }}" in (ROOT / rel).read_text(encoding="utf-8"), rel
