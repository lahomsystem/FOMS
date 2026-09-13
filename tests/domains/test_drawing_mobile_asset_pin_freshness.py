"""자산 본문과 그 자산을 가리키는 ?v= 핀의 신선도를 한 쌍으로 고정한다.

2026-09-13 사고: foms-drawing-mobile.css 본문에 새 리본 변경 줄 규칙을 넣고도
그 파일을 가리키는 ?v= 핀을 안 올려, 실기기가 24시간 동안 옛 CSS 를 썼다
(app_factory 가 ?v= 붙은 정적 자산에 public, max-age=86400 을 박는다).

하드코딩 목록이 아니라 정규식 스캔이라 새 복제 자리가 생겨도 자동으로 잡힌다.
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 자식 자산(foms-drawing-mobile.css) 핀: <link ... ') }}?v=xxx" 와 @import url("...?v=xxx") 두 모양을 함께 잡는다.
DRAWING_MOBILE_CSS_PIN = re.compile(r"foms-drawing-mobile\.css(?:'\)\s*\}\})?\?v=([0-9a-z]+)")
ORDER_CHANGE_BANNER_JS_PIN = re.compile(r"order-change-banner\.js'\)\s*\}\}\?v=([0-9a-z]+)")
MOBILE_SURFACES_PIN = re.compile(r"foms-mobile-surfaces\.css'\)\s*\}\}\?v=([0-9a-z]+)")

# 이번 사고 이전의 옛 핀들 — 다시 나타나면 실패한다.
STALE_CSS_PINS = {"20260716b", "20260811a"}
STALE_JS_PINS = {"20260716a"}
STALE_SURFACES_PINS = {"20260826a"}

FRESH_MIN = 20260913


def _read(path: Path) -> str:
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _scan(roots, suffixes, pattern) -> dict:
    """(핀 값 -> 그 값이 나온 파일 경로 목록) 을 돌려준다."""
    found: dict = {}
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            for pin in pattern.findall(_read(path)):
                found.setdefault(pin, []).append(str(path.relative_to(ROOT)))
    return found


def _pin_date(pin: str) -> int:
    return int(pin[:8])


def test_drawing_mobile_css_pins_are_one_fresh_value() -> None:
    """foms-drawing-mobile.css 를 가리키는 핀은 저장소 전체에서 한 종류이고 옛 값이 아니다."""
    found = _scan(("templates", "static/css"), {".html", ".css"}, DRAWING_MOBILE_CSS_PIN)
    assert found, "foms-drawing-mobile.css 핀을 한 개도 못 찾았다 — 정규식이나 경로가 틀렸다"
    assert len(found) == 1, f"핀이 여러 종류다(부분 범프): {found}"
    pin = next(iter(found))
    assert pin not in STALE_CSS_PINS, f"옛 핀이 그대로다: {pin} -> {found[pin]}"


def test_order_change_banner_js_pins_are_one_fresh_value() -> None:
    """order-change-banner.js 를 가리키는 템플릿 핀도 한 종류이고 옛 값이 아니다."""
    found = _scan(("templates",), {".html"}, ORDER_CHANGE_BANNER_JS_PIN)
    assert found, "order-change-banner.js 핀을 한 개도 못 찾았다"
    assert len(found) == 1, f"핀이 여러 종류다(부분 범프): {found}"
    pin = next(iter(found))
    assert pin not in STALE_JS_PINS, f"옛 핀이 그대로다: {pin} -> {found[pin]}"


def test_parent_bundle_pin_moves_with_its_child() -> None:
    """자식 @import 핀만 올리면 기기에 도달하지 않는다 — 부모도 24시간 캐시되기 때문이다.

    캐시에 남은 옛 foms-mobile-surfaces.css 는 여전히 옛 자식 URL 을 가리키므로,
    자식(foms-drawing-mobile.css) 본문이 새 리본 규칙을 담고 있으면
    (a) surfaces 안의 그 @import 핀과 (b) layout_head 의 surfaces <link> 핀이
    둘 다 신선해야 한다.
    """
    child_css = _read(ROOT / "static/css/components/foms-drawing-mobile.css")
    if ".foms-drawing-turn__change-chip" not in child_css:
        return  # 전제가 거짓 — 이 계약은 적용되지 않는다

    surfaces = _read(ROOT / "static/css/foundation/foms-mobile-surfaces.css")
    child_pins = DRAWING_MOBILE_CSS_PIN.findall(surfaces)
    assert child_pins, "surfaces 번들이 foms-drawing-mobile.css 를 싣지 않는다"
    for pin in child_pins:
        assert _pin_date(pin) >= FRESH_MIN, f"자식 @import 핀이 낡았다: {pin}"

    layout_head = _read(ROOT / "templates/partials/shared/layout_head.html")
    parent_pins = MOBILE_SURFACES_PIN.findall(layout_head)
    assert parent_pins, "layout_head 가 foms-mobile-surfaces.css 를 싣지 않는다"
    assert len(set(parent_pins)) == 1, f"부모 핀이 코호트마다 다르다: {parent_pins}"
    for pin in parent_pins:
        assert pin not in STALE_SURFACES_PINS, f"부모 핀이 그대로다: {pin}"
        assert _pin_date(pin) >= FRESH_MIN, f"부모 <link> 핀이 낡았다: {pin}"


def test_focus_fix_forces_js_pin_bump() -> None:
    """가시성 가드(offsetParent)가 들어간 JS 는 그 스크립트 핀도 함께 올라가야 한다."""
    js_text = _read(ROOT / "static/js/drawing/order-change-banner.js")
    if "offsetParent" not in js_text:
        return  # 아직 가시성 가드가 없다 — 전제가 거짓

    detail_body = _read(ROOT / "templates/drawing/partials/workbench_detail_body.html")
    pins = ORDER_CHANGE_BANNER_JS_PIN.findall(detail_body)
    assert pins, "workbench_detail_body 가 order-change-banner.js 를 싣지 않는다"
    for pin in pins:
        assert _pin_date(pin) >= FRESH_MIN, f"JS 핀이 낡았다: {pin}"


# --- 본문 ↔ 핀 연동 자물쇠 -------------------------------------------------
# 날짜 하한만 있으면 '본문만 또 고치고 핀은 그대로' 가 초록이라 같은 사고가 재발한다.
# 자산 본문의 해시와 그때의 핀을 한 쌍으로 적어 두고, 해시가 달라졌는데 핀이 그대로면 실패시킨다.
# 자산을 고쳤다면: 핀을 새 값으로 올리고 아래 표의 (해시, 핀) 을 함께 갱신한다.
ASSET_PIN_LOCK = {
    "static/css/components/foms-drawing-mobile.css": ("9166283a420f", "20260913a"),
    "static/js/drawing/order-change-banner.js": ("ae62eeb24f63", "20260913a"),
}


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def test_asset_body_and_pin_move_together() -> None:
    """자산 본문이 바뀌면 핀도 바뀌어야 한다 — 2026-09-13 사고(본문 새것·핀 옛것)의 자물쇠."""
    scans = {
        "static/css/components/foms-drawing-mobile.css": _scan(
            ("templates", "static/css"), {".html", ".css"}, DRAWING_MOBILE_CSS_PIN
        ),
        "static/js/drawing/order-change-banner.js": _scan(
            ("templates",), {".html"}, ORDER_CHANGE_BANNER_JS_PIN
        ),
    }
    for rel, (expected_hash, expected_pin) in ASSET_PIN_LOCK.items():
        actual_hash = _sha12(ROOT / rel)
        found = scans[rel]
        assert len(found) == 1, f"{rel} 핀이 여러 종류다: {found}"
        actual_pin = next(iter(found))
        assert actual_hash == expected_hash and actual_pin == expected_pin, (
            f"{rel} 의 본문/핀 쌍이 표와 다르다 "
            f"(표={expected_hash}/{expected_pin}, 실제={actual_hash}/{actual_pin}). "
            "본문을 고쳤다면 핀을 새 값으로 올리고 ASSET_PIN_LOCK 도 함께 갱신하라 — "
            "핀을 안 올리면 기기가 24시간 동안 옛 자산을 쓴다."
        )
