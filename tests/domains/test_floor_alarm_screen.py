"""생산 현장 알람 조각(일꾼 ⓔ) — 스위치(flag_floor_alarm)가 거짓이면 생산 화면 글자가 하나도 안 바뀐다.

설계서 docs/specs/2026-11-28-production-floor-alarm_SPEC.md §6-2 약속 8 · §6-4. 조각은 종 조각(notif_bell.html)이 싣고,
종 조각은 생산 첫 화면 · 전체 화면 시트가 같이 쓴다. 스위치 값은 다른 일꾼(ⓓ)이 context_processors 에 넣는다 — 여기서는
넣어 준다(없을 때도 거짓으로 본다).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
BELL = "production/partials/notif_bell.html"
PART = "production/partials/floor_alarm.html"
INCLUDE = "{% include 'production/partials/floor_alarm.html' %}"
PIN = "20261128a"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html"]))
    env.globals["url_for"] = lambda endpoint, filename=None, **_kw: f"/static/{filename}"
    return env


def _render(ns: str, **ctx) -> str:
    return _env().get_template(BELL).render(foms_prod_bell_ns=ns, **ctx)


def _render_without_part(ns: str, **ctx) -> str:
    src = (ROOT / "templates" / BELL).read_text(encoding="utf-8")
    assert src.count(INCLUDE) == 1
    return _env().from_string(src.replace(INCLUDE, "")).render(foms_prod_bell_ns=ns, **ctx)


@pytest.mark.parametrize("ns", ["foms-prod-home", "foms-prod-page"])
@pytest.mark.parametrize("ctx", [{}, {"flag_floor_alarm": False}, {"flag_floor_alarm": None}])
def test_스위치_거짓이면_종_조각_글자_그대로(ns, ctx) -> None:
    assert _render(ns, **ctx) == _render_without_part(ns, **ctx)


@pytest.mark.parametrize("ns", ["foms-prod-home", "foms-prod-page"])
def test_스위치_참이면_소리_단추_하나_CSS_스크립트_문서당_한_번(ns) -> None:
    html = _render(ns, flag_floor_alarm=True)
    rest = html.replace(_render_without_part(ns, flag_floor_alarm=True), "", 1)
    assert rest.count("<button") == 1 and rest.count("<script") == 1 and rest.count("<link") == 1
    assert f'class="{ns}__btn foms-floor-sound is-locked"' in rest
    assert "data-foms-floor-sound data-foms-urgent-sound-toggle" in rest  # 누름은 urgent-sound.js 가 받는다
    assert ">소리 켜기</span>" in rest and 'class="fas fa-volume-up"' in rest
    assert f'css/contexts/production/floor-alarm.css?v={PIN}"' in rest
    assert re.search(rf'js/foms/foms-floor-alarm\.js\?v={PIN}" defer data-foms-run-once="floor-alarm"', rest)
    assert "style=" not in rest and "\n" not in rest.strip()
    # 종 단추 바로 뒤(종 옆)
    assert html.index("data-foms-notif-open") < html.index("data-foms-floor-sound")


def test_조각을_싣는_곳은_종_조각_한_줄뿐() -> None:
    users = [p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*.html")
             if "floor_alarm.html" in p.read_text(encoding="utf-8")]
    assert users == ["templates/production/partials/notif_bell.html"]
    part = (ROOT / "templates" / PART).read_text(encoding="utf-8")
    assert "{%- if flag_floor_alarm -%}" in part and "style=" not in part


def test_긴급_창_자산_핀_네_곳이_같이_올라갔다() -> None:
    assets = ("css/components/foms-urgent-alert.css", "js/foms/urgent-sound.js", "js/foms/foms-urgent-alert.js")
    for rel, want in (("partials/shared/layout_head.html", assets), ("drawing/wizard.html", assets),
                      ("measurement/map_view.html", assets), ("brain/ds/layout.html", assets[:1])):
        html = (ROOT / "templates" / rel).read_text(encoding="utf-8")
        for asset in want:
            assert re.search(re.escape(asset) + rf"'\) \}}\}}\?v={PIN}", html), (rel, asset)
        assert "foms-urgent-alert.css') }}?v=20261016a" not in html
