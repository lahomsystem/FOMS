"""도면 마법사 잠금(locked)·이미지 뒤집기(flipX/flipY)·스포이트 계약 테스트.

- 프런트: wizard.js / wizard.html / wizard.css 문자열 계약(버튼·단축키·저장 보존).
- 백엔드: PUT→GET 왕복으로 새 필드가 살아남는지, 불리언이 아니면 거절되는지.
"""

from pathlib import Path

from tests.domains.test_drawing_wizard_api import (
    _erp_order,
    _login_participant_admin,
    _put_state,
)

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
HTML = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")


# ---- 프런트 문자열 계약 -----------------------------------------------------

def test_template_has_lock_flip_eyedrop_buttons():
    for el_id in (
        "dws-mt-lock-text", "dws-mt-lock-image", "dws-mt-lock-shape",
        "dws-mt-flip-x", "dws-mt-flip-y",
        "dws-mt-eyedrop-text", "dws-mt-eyedrop-shape",
    ):
        assert f'id="{el_id}"' in HTML, el_id
    assert "좌우 뒤집기" in HTML and "상하 뒤집기" in HTML
    assert "스포이트" in HTML
    # 뒤집기 버튼은 이미지 툴바의 여백 자르기 옆에 둔다
    image_bar = HTML.split('id="dws-mt-image"', 1)[1].split('id="dws-mt-shape"', 1)[0]
    assert "dws-mt-trim" in image_bar and "dws-mt-flip-x" in image_bar


def test_lock_rules_in_js():
    assert "node.setAttr('annoLocked', !!o.locked)" in JS
    assert "!isLockedNode(n)" in JS  # 드래그 불가
    assert "transformer.rotateEnabled(!lockedOne)" in JS  # 변형 불가
    assert "if (!n || o.locked) { return; }" in JS  # 러버밴드 제외
    assert "잠긴 객체는 삭제할 수 없습니다" in JS  # Delete 차단
    assert "e.code === 'KeyL'" in JS
    assert "unlockAllOnSheet()" in JS and "toggleLockSelected()" in JS


def test_flip_preserved_through_transform_and_save():
    # 뒤집기는 노드 scale 이 아니라 뒤집은 캔버스 소스로 그려 commitNode 정규화와 분리된다
    assert "function flippedImageSource(img, o)" in JS
    assert "node.image(flippedImageSource(img, o))" in JS
    assert "function flipSelectedImage(axis)" in JS
    flip_body = JS.split("function flipSelectedImage(axis)", 1)[1].split("\n  }\n", 1)[0]
    assert "recordUndo()" in flip_body  # 실행 취소 포함


def test_save_load_wrappers_keep_new_fields():
    assert "function serializeObj(o) { return withLockFlip(o, serializeObjCore(o)); }" in JS
    assert "function normalizeObj(o) { return withLockFlip(o, normalizeObjCore(o)); }" in JS
    for key in ("out.locked = true", "out.flipX = true", "out.flipY = true"):
        assert key in JS


def test_eyedrop_uses_swatch_apply_paths_and_esc_cancels():
    body = JS.split("function pickEyedropColor(sourceId)", 1)[1].split("\n  }\n", 1)[0]
    assert "updateSelectedText({ color: color })" in body
    assert "updateSelectedShape({ stroke: color })" in body
    assert "if (eyedropArmed) { cancelEyedrop(); return; }" in JS
    assert "if (eyedropArmed) { pickEyedropColor(id); return; }" in JS
    assert ".dws-eyedrop-armed" in CSS


def test_no_inline_styles_in_new_buttons():
    for line in HTML.splitlines():
        if "dws-mt-lock" in line or "dws-mt-flip" in line or "dws-mt-eyedrop" in line:
            assert "style=" not in line


# ---- 백엔드 왕복 ------------------------------------------------------------

def test_put_then_get_round_trips_locked_and_flip(client):
    _login_participant_admin(client, username="wizard-lockflip")
    order = _erp_order()
    order_id = order.id
    objects = [
        {
            "id": "o-img", "type": "image", "x": 90, "y": 420, "w": 620, "h": 360,
            "key": f"orders/{order_id}/drawing_wizard/assets/x.png",
            "natural_w": 1240, "natural_h": 720,
            "locked": True, "flipX": True, "flipY": True,
        },
        {
            "id": "o-rect", "type": "rect", "x": 10, "y": 10, "w": 50, "h": 40,
            "stroke": "#000000", "strokeWidth": 2, "locked": True,
        },
    ]
    resp = _put_state(client, order_id, objects)
    assert resp.status_code == 200, resp.get_json()
    state = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    saved = {o["id"]: o for o in state["sheets"][0]["objects"]}
    assert saved["o-img"]["locked"] is True
    assert saved["o-img"]["flipX"] is True
    assert saved["o-img"]["flipY"] is True
    assert saved["o-rect"]["locked"] is True


def test_put_rejects_non_boolean_lock_flip(client):
    _login_participant_admin(client, username="wizard-lockflip-bad")
    order = _erp_order()
    for bad in ({"locked": "yes"}, {"flipX": 1}):
        obj = {
            "id": "o-rect", "type": "rect", "x": 10, "y": 10, "w": 50, "h": 40,
            "stroke": "#000000", "strokeWidth": 2,
        }
        obj.update(bad)
        resp = _put_state(client, order.id, [obj])
        assert resp.status_code == 400, bad


def test_text_color_swatches_include_yellow_and_white():
    tpl = Path("templates/drawing/wizard.html").read_text(encoding="utf-8")
    assert 'data-color="#ffd43b"' in tpl and 'data-color="#ffffff"' in tpl
