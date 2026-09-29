"""도면 상세 모바일(v2 셸) — 옛 하단 액션바가 새 액션바 뒤에서 새어 나오지 않는다.

2026-09-29 제보: 모바일 도면 상세 하단 액션바 위로 파랑·노랑·초록 색 막대가 튀어나와 보였다.
원인 두 가지를 고정한다.

(A) v2 셸에서 `d-none` 으로 숨긴 옛 바 `.dw-mobile-action-bar` 를 본문 <style> 의
    `@media (max-width: 992px) { .dw-mobile-action-bar { display: flex !important; } }` 가 되살렸다.
    둘 다 !important 이고 명시도가 같아 뒤에 오는 본문 규칙이 Bootstrap `.d-none` 을 이겼다.
    튀어나온 초록 조각을 누르면 수령 확정(confirmReceipt)이 실행될 수 있었다.
    → 규칙을 `:not(.d-none)` 으로 좁힌다(v2 가 꺼진 예전 셸에서는 계속 flex).
(B) v2 본문 아래 여백(84px)이 새 바 높이(73px) + 아이폰 홈 표시줄(safe-area)보다 작아
    스레드 마지막 카드가 바 뒤에 숨었다. → 여백에 env(safe-area-inset-bottom) 을 더한다.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates/drawing/partials/workbench_detail_body.html"
MOBILE_CSS = ROOT / "static/css/components/foms-drawing-mobile.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_mobile_bar_flex_rule_respects_d_none():
    body = _read(TEMPLATE)
    assert ".dw-mobile-action-bar:not(.d-none)" in body


def test_no_unguarded_legacy_bar_flex_important():
    body = _read(TEMPLATE)
    # :not(.d-none) 가 없는 선택자 바로 뒤(16자 안)에 display: flex !important 가 오면 d-none 을 이긴다.
    offenders = re.findall(r"\.dw-mobile-action-bar\s*\{[\s\S]{0,16}display:\s*flex\s*!important", body)
    assert not offenders, offenders


def test_handoff_body_bottom_padding_includes_safe_area():
    css = _read(MOBILE_CSS)
    m = re.search(
        r"body\.erp-mobile-v2-layout \.foms-drawing-handoff__body\s*\{([^}]*)\}",
        css,
    )
    assert m, "foms-drawing-handoff__body 규칙을 못 찾았다"
    block = m.group(1)
    padding = re.search(r"padding:\s*([^;]+);", block)
    assert padding, block
    assert "env(safe-area-inset-bottom" in padding.group(1), padding.group(1)
