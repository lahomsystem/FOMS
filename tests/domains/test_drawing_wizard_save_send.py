"""도면 마법사 [저장]·[일괄 저장] → 도면 발송(영업 전달) · 도면방 PUSH 고르기 창 계약.

설계서 docs/specs/2026-11-05-wizard-save-send-options_SPEC.md (사용자 결정 2026-11-05).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import foms.web.drawing.wizard as wizard_route

ROOT = Path(__file__).resolve().parents[2]
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
SEND_JS = (ROOT / "static/js/drawing/save-send.js").read_text(encoding="utf-8")


def _config(monkeypatch, *, can_transfer: bool, hotfix: bool, partner_org_id):
    monkeypatch.setattr(wizard_route, "can_transfer_drawing", lambda user, order: can_transfer)
    monkeypatch.setattr(wizard_route, "is_drawing_hotfix_stage", lambda order: hotfix)
    user = SimpleNamespace(id=7, role="STAFF")
    order = SimpleNamespace(id=1, partner_org_id=partner_org_id)
    return wizard_route._save_send_config(user, order)


def test_save_send_config_reports_transfer_hotfix_partner(monkeypatch):
    cfg = _config(monkeypatch, can_transfer=True, hotfix=True, partner_org_id=3)
    assert cfg == {"user_id": 7, "can_transfer": True, "hotfix_stage": True, "is_partner": True}


def test_save_send_config_plain_order_without_transfer_right(monkeypatch):
    cfg = _config(monkeypatch, can_transfer=False, hotfix=False, partner_org_id=None)
    assert cfg == {"user_id": 7, "can_transfer": False, "hotfix_stage": False, "is_partner": False}


def test_save_send_config_without_user_is_locked(monkeypatch):
    monkeypatch.setattr(wizard_route, "can_transfer_drawing", lambda user, order: True)
    monkeypatch.setattr(wizard_route, "is_drawing_hotfix_stage", lambda order: False)
    cfg = wizard_route._save_send_config(None, SimpleNamespace(id=1, partner_org_id=None))
    assert cfg["can_transfer"] is False and cfg["user_id"] == 0


def test_popover_markup_sits_with_save_buttons_and_has_no_inline_style():
    start = TPL.index('class="dws-savesend-anchor"')
    end = TPL.index('id="dws-savesend"')
    assert start < TPL.index('id="dws-btn-save"') < TPL.index('id="dws-btn-save-all"') < end
    block = TPL[end:TPL.index('data-savesend-remember', end)]
    assert "style=" not in block
    assert 'data-savesend="send"' in block and 'data-savesend="push"' in block
    # 발송이 위, PUSH 가 아래(PUSH 는 발송 위에 얹히는 일)
    assert block.index('data-savesend="send"') < block.index('data-savesend="push"')


def test_save_send_script_loads_after_wizard_core():
    assert TPL.index("js/drawing/wizard.js') }}?v=20261105a") < TPL.index("js/drawing/save-send.js') }}?v=20261105a")


def test_buttons_open_popover_but_ctrl_s_saves_directly():
    assert "els.saveBtn.addEventListener('click', function () { if (!openSaveSend('one')) { save(); } });" in JS
    assert "if (!openSaveSend('all')) { saveAll(); }" in JS
    assert "(e.key === 's' || e.key === 'S')) { e.preventDefault(); save(); return; }" in JS


def test_core_exposes_hooks_for_popover():
    for hook in ("saveAll: saveAll,", "pushRoom: pushDrawingRoom,", "refreshPending: refreshPending,"):
        assert hook in JS
    # 저장 창이 대기함에 못 넣은 시트를 전달하지 않게 save() 가 결과를 돌려준다.
    assert "return queued === true;" in JS
    assert "if (!(opts && opts.skipConfirm === true) &&" in JS


def test_single_sheet_transfer_is_append_so_other_sheets_stay():
    # mode 를 비우면 영업 확정 전(TRANSFERRED)에 서버가 전체 교체로 본다 — 한 장 저장이 다른 장을 지운다.
    assert "mode: kind === 'one' ? 'APPEND' : ''" in SEND_JS
    assert "'/api/orders/' + ORDER_ID + '/transfer-drawing'" in SEND_JS


def test_push_implies_send_and_partner_has_no_push():
    assert "if (changed === pushBox && pushBox.checked) { sendBox.checked = true; }" in SEND_JS
    assert "if (changed === sendBox && !sendBox.checked) { pushBox.checked = false; }" in SEND_JS
    assert "function wantPush() { return wantSend() && !isPartner && pushBox.checked; }" in SEND_JS


def test_batch_with_failed_sheet_does_not_transfer():
    assert "if (res.fail && res.fail.length) {" in SEND_JS
    assert "장을 대기함에 못 넣어서 전달은 하지 않았어요" in SEND_JS


def test_hotfix_stage_asks_before_anything():
    assert "if (send && CFG.hotfix_stage === true && !window.confirm(HOTFIX_MSG)) { return; }" in SEND_JS
    assert SEND_JS.index("window.confirm(HOTFIX_MSG)") < SEND_JS.index("c.saveAll().then")
