"""11-08 점검 후속 — 작은 결함(사용자 "남은 작은 결함 고치기").

* 어두운 테마 닫기(X): "고객에게 보내기" 고르기 창 · 공유 링크 창의 X 가 검은 그림이라 어두운 창 바탕에 묻혔다
  (Bootstrap 5.3.0-alpha1 은 data-bs-theme 로 X 를 바꾸지 않는다) → btn-close-white 와 같은 필터.
* 견적 계산기 어두운 테마 나머지: 짙은 남색 금액 · 밝은 회색 고정 바탕.
* 화면에 보이는 기계 말 "큐"(PC 표 머리 · 태블릿 · 휴대폰 홈 링크 · 협력사 홈 · 출고 요약).
* 주문 수정 화면 PC · 휴대폰 두 표면의 같은 이름 라디오 — 근본 고침은 test_as_billing 의 표면 지우기 순서 시험.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_DARK_X = "filter: invert(1) grayscale(100%) brightness(200%);"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel,selector", [
    ("static/css/orders/erp-channel-push.css", "[data-theme='dark'] .erp-channel-push-picker-modal .btn-close"),
    ("static/css/orders/erp-share.css", "[data-theme='dark'] #erpShareModal .btn-close"),
])
def test_dark_theme_close_buttons_are_light(rel, selector):
    css = _read(rel)
    rule = css[css.index(selector):css.index("}", css.index(selector))]
    assert _DARK_X in rule


def test_calculator_dark_theme_amounts_and_fixed_light_backgrounds():
    css = _read("static/css/wdcalculator/builder.css")
    dark_lines = [line for line in css.splitlines() if line.strip().startswith("[data-theme='dark']")]
    for selector in (".wd-esec .wd-bc-price", ".wd-esec .wd-bc-subval", ".wd-fab__sum-v", ".estimate-total-price",
                     ".wd-editor__close", ".wd-esec__head", ".estimate-card-item"):
        assert any(selector in line for line in dark_lines), selector
    assert "builder.css') }}?v=20261108b" in _read("templates/wdcalculator/calculator.html")


@pytest.mark.parametrize("rel", [
    "templates/construction/partials/filters_grid.html",
    "templates/production/partials/filters_grid.html",
    "templates/orders/partials/dashboard_grid.html",
    "templates/partials/shared/foms_master_list.html",
    "templates/measurement/partials/tablet_split_body.html",
    "templates/orders/partials/dashboard_mobile_tower.html",
    "templates/partner/home.html",
    "templates/shipment/partials/dashboard_main.html",
])
def test_no_visible_queue_jargon(rel):
    html = _read(rel)
    for word in ("> 작업 큐", ">작업 큐", "실측 큐<", "출고 큐<", "작업 큐</"):
        assert word not in html, (rel, word)
