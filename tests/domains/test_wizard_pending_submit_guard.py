"""발송만 하고 나가서 주문이 유실되는 것을 막는다 (WIZ-SEND-01 후속, 2026-09-11).

사고: 2026-09-10 KST 10:40 마법사 4단계에서 실측 PUSH 가 성공했지만(초안
``new.ff7475d50b3a42ac``) "주문 등록" 요청이 서버에 한 번도 오지 않아 주문이 존재하지
않았다. 초안 단계 푸시는 설계상 주문을 만들지 않으므로(설계 D1) 이것은 서버 버그가
아니라 **화면이 남은 한 걸음을 알려주지 않은 것**이다. 같은 일이 초안 푸시 54건 중
3건 있었다(9/2 user 38, 9/3 user 21, 9/10 user 53).

게다가 등록 버튼은 실패해도 무음이었다 — ``submitOrder().then(...)`` 뿐이라 fetch 거부나
JSON 이 아닌 응답(500 HTML·로그인 리다이렉트)이면 alert 조차 뜨지 않았다. 그래서
"안 눌렀다" 와 "눌렀는데 안 나갔다" 를 사후에 가릴 수도 없었다.

계약 세 겹:
1. 발송 성공이 "등록 전" 상태를 남긴다(문구 + 버튼 강조 + wizard.js 가 읽을 수 있는 신호).
2. 그 상태로 닫기를 누르면 확인창이 막는다.
3. 등록 실패는 반드시 사용자에게 보인다(``.catch`` + 버튼 잠금/복구).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEND_JS = ROOT / "static/js/foms/wizard-send.js"
WIZARD_JS = ROOT / "static/js/foms/wizard.js"
WIZARD_CSS = ROOT / "static/css/components/foms-wizard.css"
SHELL = ROOT / "templates/orders/wizard/wizard_shell.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_send_success_marks_pending_submit() -> None:
    """발송 성공 = "아직 등록 전" 상태. 문구·버튼 강조·공유 신호가 함께 걸린다."""
    js = _read(SEND_JS)
    assert "sentPendingSubmit: false," in js, "상태 플래그가 없다"
    assert "function markPendingSubmit()" in js
    assert 'next.classList.add("is-pending-submit")' in js, "등록 버튼 강조가 없다"
    # 발송 성공 분기에서 호출해야 한다 — 실패한 발송은 등록을 재촉하면 안 된다.
    success_branch = js.split('if (body && body.success === true && data && data.sent) {')[1]
    assert "markPendingSubmit();" in success_branch.split("return;")[0]
    assert "아직 주문 등록 전입니다" in js, "발송 완료 문구가 등록이 남았음을 말하지 않는다"


def test_pending_send_signal_is_exposed_to_wizard() -> None:
    """wizard.js 가 읽을 수 있게 전역으로 노출한다(두 파일은 별개 IIFE 다)."""
    js = _read(SEND_JS)
    assert "window.FomsWizardHasPendingSend = function () {" in js
    assert "return !!state.sentPendingSubmit;" in js


def test_close_button_confirms_when_send_pending_submit() -> None:
    """발송했는데 등록 안 한 채 닫으면 확인창이 뜨고, 취소하면 안 나간다."""
    js = _read(WIZARD_JS)
    close_handler = js.split('closeBtn.addEventListener("click", function () {')[1]
    close_handler = close_handler.split("readWizardExitHref(root)")[0]
    assert "window.FomsWizardHasPendingSend" in close_handler
    assert "window.confirm(" in close_handler
    assert "주문은 아직 등록되지 않았습니다" in close_handler
    # 취소하면 이동하지 않는다.
    assert "if (!ok) {" in close_handler


def test_submit_failure_is_never_silent() -> None:
    """등록 실패는 통신 오류까지 포함해 반드시 사용자에게 보인다."""
    js = _read(WIZARD_JS)
    assert "function submitOrderWithFeedback(root, draftClient) {" in js
    body = js.split("function submitOrderWithFeedback(root, draftClient) {")[1].split("\n  }\n")[0]
    assert ".catch(function () {" in body, "fetch 거부를 잡는 자리가 없다(무음 실패 회귀)"
    assert body.count("window.alert(") == 2, "서버 실패·통신 실패 두 갈래 모두 알려야 한다"
    assert "통신이 끊겼습니다" in body
    # 누르는 즉시 잠그고, 실패하면 되돌린다(다시 누를 수 있어야 한다).
    assert "submitBtn.disabled = true;" in body
    assert '"등록 중…"' in body
    assert "function unlock()" in body
    assert body.count("unlock();") == 2, "두 실패 갈래 모두에서 복구해야 한다"


def test_submit_is_not_called_bare_anywhere() -> None:
    """맨 ``submitOrder().then`` 이 남아 있으면 무음 실패가 되살아난다."""
    js = _read(WIZARD_JS)
    assert "draftClient.submitOrder().then(" not in js
    # 주석(설명·회귀 기록)에도 같은 문자열이 나오므로 코드 줄만 센다.
    code_lines = [
        line
        for line in js.splitlines()
        if not line.lstrip().startswith(("*", "//", "/*"))
    ]
    hits = sum(line.count("submitOrder()") for line in code_lines)
    assert hits == 1, "등록 진입점은 한 곳이어야 한다"


def test_pending_submit_style_exists_and_respects_reduced_motion() -> None:
    """강조는 CSS 클래스로만 준다(인라인 스타일 금지) + 모션 축소 설정 존중."""
    css = _read(WIZARD_CSS)
    assert ".foms-btn.is-pending-submit {" in css
    assert "@keyframes foms-wizard-pending-submit" in css
    reduced = css.split("@media (prefers-reduced-motion: reduce) {")
    assert any("is-pending-submit" in block for block in reduced[1:]), "모션 축소 대응이 없다"


def test_changed_assets_have_bumped_pins() -> None:
    """wizard.js·wizard-send.js·CSS 를 고쳤으므로 `?v=` 핀이 올라가 있어야 한다."""
    shell = _read(SHELL)
    for name in ("js/foms/wizard.js", "js/foms/wizard-send.js", "css/components/foms-wizard.css"):
        assert f"filename='{name}') }}}}?v=20260902" not in shell, f"{name} 핀 미범프"
        match = re.search(
            r"filename='" + re.escape(name) + r"'\)\s*\}\}\?v=([0-9a-z]+)", shell
        )
        assert match, name
        assert match.group(1).startswith("2026"), match.group(1)
