"""P1-05~07 contract tests."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_split_shell_templates() -> None:
    shell = (ROOT / "templates/partials/shared/foms_split_shell.html").read_text(encoding="utf-8")
    assert "data-foms-split-shell" in shell
    assert "foms_master_list.html" in shell
    css = (ROOT / "static/css/foundation/foms-split-view.css").read_text(encoding="utf-8")
    # 3-tier split band: tablet master-detail renders 992–1365.98px (D03).
    assert "max-width: 1365.98px" in css
    js = (ROOT / "static/js/foms/split-shell.js").read_text(encoding="utf-8")
    assert "data-foms-master-card" in js


_STYLESHEET_LINK_RE = re.compile(
    r"""<link\b[^>]*\brel=["']stylesheet["'][^>]*>""", re.I
)


def _stylesheet_links(template: str) -> list[str]:
    """템플릿 안 stylesheet <link> 태그를 나온 순서대로 돌려준다(Jinja 주석은 뺀다)."""
    return _STYLESHEET_LINK_RE.findall(re.sub(r"\{#.*?#\}", "", template, flags=re.S))


def test_token_alias_bridge() -> None:
    """P1-06 토큰 브리지 계약: erp-pro 를 쓰는 모든 화면에 --foms-* 토큰이 erp-pro 보다 먼저 깔린다.

    예전엔 이 계약을 `01-intro-tokens.css` 의 `@import url("../foms-tokens.css")` 글자로 지켰다.
    그 무버전 @import 는 layout_head 의 `?v=` 링크와 URL 이 달라 **같은 파일을 페이지마다 두 번**
    받았다(2026-10-01 성능 원장 P2 첫 로드 ③). 지키려던 것은 글자가 아니라 아래 세 가지다.

    1) 브리지 변수(`--foms-bridge-erp-*`)가 그대로 있다.
    2) erp-pro.css 를 싣는 템플릿은 **전부** foms-tokens.css 를 한 번, erp-pro.css **바로 앞**
       stylesheet 로 싣는다 — 옛 @import 자리(erp-pro 첫 규칙 앞)와 같은 캐스케이드 순서다.
       이 검사는 템플릿 전체를 훑으므로 새 레이아웃이 토큰 없이 erp-pro 만 실으면 여기서 걸린다.
    3) 토큰 링크는 어디서나 같은 `?v=` URL 이다(화면을 옮겨 다녀도 캐시 한 칸).
    """
    tokens = (ROOT / "static/css/foundation/erp-pro/01-intro-tokens.css").read_text(encoding="utf-8")
    assert "--foms-bridge-erp-primary: var(--erp-primary)" in tokens
    code = re.sub(r"/\*.*?\*/", "", tokens, flags=re.S)
    assert "@import" not in code, "01-intro-tokens.css 가 다시 @import 한다 — 토큰 이중 다운로드"

    token_urls: set[str] = set()
    users = 0
    for path in sorted((ROOT / "templates").rglob("*.html")):
        links = _stylesheet_links(path.read_text(encoding="utf-8"))
        erp_idx = [i for i, ln in enumerate(links) if "css/foundation/erp-pro.css" in ln]
        if not erp_idx:
            continue
        users += 1
        rel = path.relative_to(ROOT).as_posix()
        tok_idx = [i for i, ln in enumerate(links) if "css/foundation/foms-tokens.css" in ln]
        assert len(erp_idx) == 1, f"{rel}: erp-pro.css 링크가 {len(erp_idx)}개"
        assert len(tok_idx) == 1, f"{rel}: foms-tokens.css 링크가 {len(tok_idx)}개(정확히 1개여야 한다)"
        assert tok_idx[0] == erp_idx[0] - 1, (
            f"{rel}: foms-tokens.css 가 erp-pro.css 바로 앞 stylesheet 가 아니다 — 캐스케이드 순서 변경"
        )
        pin = re.search(r"foms-tokens\.css'\)\s*\}\}(\?v=[0-9a-z]+)", links[tok_idx[0]])
        assert pin, f"{rel}: foms-tokens.css 링크에 ?v= 핀이 없다"
        token_urls.add(pin.group(1))
    assert users >= 2, "erp-pro.css 를 싣는 템플릿(layout_head·WAM)을 못 찾았다 — 정규식 확인"
    assert len(token_urls) == 1, f"foms-tokens.css 핀이 템플릿마다 다르다(URL 이 갈린다): {token_urls}"


# foms-tokens.css 본문 해시(줄끝 LF 기준)와 그때의 ?v= 핀. 예전엔 무버전 @import 사본이 늘 재검증돼
# 핀을 안 올린 토큰 수정도 기기에 닿았다 — 그 사본을 걷어냈으니 이제는 핀이 유일한 신선도 장치다.
# 토큰을 고쳤다면: 두 템플릿(layout_head·WAM)의 핀을 같은 새 값으로 올리고 이 쌍도 함께 고친다.
_TOKENS_BODY_PIN_LOCK = ("e8b7a2b7d05b", "?v=20260915a")


def test_foms_tokens_body_and_pin_move_together() -> None:
    """foms-tokens.css 본문/핀 쌍이 표와 같아야 한다 — 본문만 고치고 핀을 그대로 두면 실패한다.

    (test_drawing_mobile_asset_pin_freshness.py 의 ASSET_PIN_LOCK 과 같은 방식.)
    """
    text = (ROOT / "static/css/foundation/foms-tokens.css").read_text(encoding="utf-8")
    sha12 = hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:12]
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    pin = re.search(r"foms-tokens\.css'\)\s*\}\}(\?v=[0-9a-z]+)", head)
    assert pin, "layout_head 에서 foms-tokens.css 핀을 못 찾았다"
    assert (sha12, pin.group(1)) == _TOKENS_BODY_PIN_LOCK, (
        f"foms-tokens.css 본문/핀 쌍이 표와 다르다(표={_TOKENS_BODY_PIN_LOCK}, 실제={(sha12, pin.group(1))}). "
        "본문을 고쳤다면 두 템플릿의 핀을 새 값으로 올리고 _TOKENS_BODY_PIN_LOCK 도 함께 갱신하라."
    )


def test_foms_kv_macro_deeplinks() -> None:
    macro = (ROOT / "templates/macros/foms_kv.html").read_text(encoding="utf-8")
    assert "tel:" in macro
    assert "map.kakao.com" in macro
    assert "mailto:" in macro


def test_wizard_alpine_validation_and_multi_product() -> None:
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    assert 'x-data="fomsWizardValidation"' in shell
    step1 = (ROOT / "templates/orders/wizard/step1_basic.html").read_text(encoding="utf-8")
    assert "foms-wizard__error" in step1
    step2 = (ROOT / "templates/orders/wizard/step2_products.html").read_text(encoding="utf-8")
    assert "foms-wizard-add-product" in step2
    js = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")
    assert "cloneProductCard" in js
    assert "applyAlpineErrors" in js
    css = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(encoding="utf-8")
    assert "foms-kv-row.css" in css


def test_wizard_product_card_renumber_and_remove() -> None:
    """복제 카드 헤더 번호 재매김 + 카드 삭제 버튼 계약."""
    step2 = (ROOT / "templates/orders/wizard/step2_products.html").read_text(encoding="utf-8")
    assert "data-foms-product-remove" in step2
    js = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")
    assert "renumberProductCards" in js
    assert '[data-foms-product-remove]' in js
    item_js = (ROOT / "static/js/foms/product-item.js").read_text(encoding="utf-8")
    # 헤더 삭제 버튼 클릭은 접기/펴기 토글이 아니다.
    assert "data-foms-product-remove" in item_js
    css = (ROOT / "static/css/components/foms-product-item.css").read_text(encoding="utf-8")
    assert "foms-product-item__remove" in css


def test_c14_product_item_contract() -> None:
    macro = (ROOT / "templates/macros/foms_product_item.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/foms/product-item.js").read_text(encoding="utf-8")
    assert "foms_product_item" in macro
    assert "foms-product-item__head" in macro
    assert "fomsProductItem" in js
    assert "foms-product-item--collapsed" in js
    edit = (ROOT / "templates/orders/edit_order.html").read_text(encoding="utf-8")
    assert "foms-product-item.css" in edit


def test_build_split_master_cards() -> None:
    from foms.services.foms_split_view import build_split_master_cards

    cards = build_split_master_cards(
        [{"id": 1, "customer_name": "A", "product": "장"}],
        active_order_id=1,
    )
    assert cards[0]["active"] is True
    assert "/api/foms/fragment/order/1/edit" in cards[0]["detail_href"]
