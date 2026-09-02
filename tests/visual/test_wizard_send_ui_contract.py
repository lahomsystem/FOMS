"""모바일 마법사 4단계 발송 액션 UI 배선 계약 (WIZ-SEND-01 / T4).

버튼·시트 마크업, 신규 JS 의 shell 등재와 `?v=` 핀, CSS 핀 범프, 라우트 4종 문자열을
소스 내용으로 고정한다. 이 기능의 대표 회귀는 (1) JS 를 만들고 shell 에 등재하지 않아
"스타일만 있고 기능이 없는" 상태, (2) 자산을 고치고 핀을 안 올려 서비스워커가 옛 파일을
계속 서빙하는 것이라, 렌더 파이프라인이 아니라 파일 문자열을 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STEP4 = "templates/orders/wizard/step4_confirm.html"
SHELL = "templates/orders/wizard/wizard_shell.html"
CSS = "static/css/components/foms-wizard.css"
SEND_JS = "static/js/foms/wizard-send.js"
WIZARD_JS = "static/js/foms/wizard.js"

ENDPOINTS = (
    "/api/erp/order-draft/alimtalk/preview",
    "/api/erp/order-draft/alimtalk/send",
    "/api/erp/order-draft/channel-push/preview",
    "/api/erp/order-draft/channel-push/send",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_step4_has_both_send_buttons() -> None:
    """4단계 확인 화면에 실측 PUSH · 알림톡 버튼이 한 줄로 놓인다."""
    html = _read(STEP4)
    assert 'data-wizard-step="4"' in html
    assert 'id="foms-wizard-push-btn"' in html
    assert 'id="foms-wizard-alimtalk-btn"' in html
    assert 'data-wizard-send="channel"' in html
    assert 'data-wizard-send="alimtalk"' in html
    assert "실측 PUSH" in html
    assert "알림톡 · 예약 내역" in html
    # 합계 카드 뒤에 온다(요약 → 합계 → 액션).
    assert html.index("foms-wizard__summary-card--total") < html.index("foms-wizard__send-actions")


def test_step4_has_readonly_confirm_sheet_and_trace_lines() -> None:
    """미리보기는 읽기 전용 시트로 확인하고, 마지막 발송 흔적 줄이 종류별로 있다."""
    html = _read(STEP4)
    assert 'id="foms-wizard-send-sheet"' in html
    assert 'id="foms-wizard-send-sheet-preview"' in html
    assert 'id="foms-wizard-send-confirm"' in html
    assert "data-wizard-send-close" in html
    assert 'data-wizard-send-trace="channel"' in html
    assert 'data-wizard-send-trace="alimtalk"' in html
    assert 'id="foms-wizard-send-status"' in html


def test_step4_markup_has_no_inline_style_and_no_alert_class() -> None:
    """인라인 스타일 금지 + `.alert`(5초 자동 소멸) 금지."""
    html = _read(STEP4)
    assert not re.search(r"\sstyle\s*=\s*['\"]", html), "인라인 스타일이 있다"
    assert not re.search(r"class=\"[^\"]*\balert\b", html), ".alert 는 자동으로 사라진다"
    js = _read(SEND_JS)
    assert '"alert"' not in js and "'alert'" not in js


def test_shell_registers_send_js_with_version_pin() -> None:
    """신규 JS 가 shell 에 defer 로 등재되고 `?v=` 핀이 붙는다."""
    shell = _read(SHELL)
    match = re.search(
        r"<script[^>]*filename='js/foms/wizard-send\.js'\)\s*\}\}\?v=([0-9a-z]+)\"[^>]*>",
        shell,
    )
    assert match, "wizard-send.js 가 shell 에 등재되지 않았거나 ?v= 핀이 없다"
    assert match.group(1).startswith("2026"), match.group(1)
    tag = match.group(0)
    assert "defer" in tag, "렌더 차단 스크립트 금지(perf G1)"
    # 발송 JS 는 draft/wizard 배선 뒤에 와야 flush 진입점을 찾는다.
    assert shell.index("js/foms/wizard.js") < shell.index("js/foms/wizard-send.js")


def test_changed_assets_have_bumped_pins() -> None:
    """CSS·wizard.js 를 고쳤으므로 핀이 범프돼 있어야 한다(SW staticCacheFirst)."""
    shell = _read(SHELL)
    assert "css/components/foms-wizard.css') }}?v=20260823c" not in shell, "CSS 핀 미범프"
    assert "js/foms/wizard.js') }}?v=20260828b" not in shell, "wizard.js 핀 미범프"
    assert re.search(r"filename='css/components/foms-wizard\.css'\)\s*\}\}\?v=2026", shell)


def test_send_js_uses_contract_endpoints_and_draft_flush() -> None:
    """라우트 4종 + 초안 강제 flush 선행(D2) 이 JS 에 있다."""
    js = _read(SEND_JS)
    for endpoint in ENDPOINTS:
        assert endpoint in js, endpoint
    assert "fomsWizardDraftClient" in js
    assert "flush(" in js
    assert "draft_key" in js
    assert "change_note" in js
    # 응답 규약 검증과 실패 방어.
    assert "success !== true" in js
    assert "catch(" in js
    # jQuery 금지.
    assert "$(" not in js
    # 사유 라벨 매핑(PC 표면과 미러).
    assert "no_valid_phone" in js
    assert "not_configured" in js


def test_send_js_locks_buttons_during_send() -> None:
    """전송 중 버튼 잠금(중복 클릭 = 중복 발송 방지)."""
    js = _read(SEND_JS)
    assert "lockButtons" in js
    assert "state.busy" in js


def test_wizard_js_exposes_draft_client() -> None:
    """발송 JS 가 쓰는 flush 진입점이 실제로 노출돼 있다."""
    js = _read(WIZARD_JS)
    assert "window.fomsWizardDraftClient = draftClient" in js


def test_css_defines_send_and_sheet_blocks() -> None:
    """BEM 유지 + 좁은 폭 세로 깨짐 방지 규칙."""
    css = _read(CSS)
    assert ".foms-wizard__send-actions" in css
    assert ".foms-wizard__send-btn" in css
    assert ".foms-wizard__sheet" in css
    assert ".foms-wizard__sheet-preview" in css
    block = css[css.index(".foms-wizard__send-btn-label") :]
    assert "white-space: nowrap" in block[:400], "좁은 폭에서 글자가 세로로 깨진다"
    # 새 색상 하드코딩 금지 — 신규 블록의 색은 토큰(var(--foms-*)) 으로만 쓴다.
    #
    # 예외는 브랜드 고정색 정의 한 곳뿐이다. 카카오 노랑·채널톡 블루는 우리 팔레트가
    # 아니라 외부 서비스가 정한 값이라 테마를 따라 변하면 안 된다. 대신 `--foms-brand-*`
    # 선언 한 곳에만 리터럴을 두고 사용처는 var() 로 강제한다 — 값이 두 벌로 갈리는 것을
    # 막는 것이 이 계약의 목적이기 때문이다.
    new_block = css[css.index("/* ── Step 4: 등록 전 발송 액션") :]
    brand_decl = re.compile(r"--foms-brand-[\w-]+:\s*$")
    for match in re.finditer(r"#[0-9a-fA-F]{3,6}\b", new_block):
        before = new_block[max(0, match.start() - 60) : match.start()]
        if "var(--foms" in before:
            continue  # var(--x, #hex) fallback
        assert brand_decl.search(before), f"토큰 밖 색상: {match.group(0)}"

    # 브랜드 토큰은 선언만으로 끝나면 안 된다 — 두 버튼이 실제로 그 색을 입어야 한다.
    for token in ("--foms-brand-kakao-bg", "--foms-brand-channel-bg"):
        assert new_block.count(f"var({token})") >= 1, f"{token} 미사용"


def test_send_buttons_carry_channel_icons() -> None:
    """두 버튼은 색만이 아니라 아이콘으로도 채널을 구분한다.

    색만으로 구분하면 색각 이상 사용자에게는 같은 버튼 두 개다. 카카오 아이콘은
    FA6 free 에 없어 인라인 SVG 로 넣으므로, 링크가 아니라 마크업 자체를 못 박는다.
    """
    html = _read(STEP4)
    assert "fa-paper-plane" in html, "실측 PUSH 아이콘 없음"
    assert "<svg" in html and "foms-wizard__send-btn-icon" in html, "카카오 아이콘 없음"
    assert html.count('aria-hidden="true"') >= 2, "장식 아이콘은 스크린리더에서 숨긴다"
