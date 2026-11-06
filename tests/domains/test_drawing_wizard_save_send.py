"""도면 마법사 [저장]·[일괄 저장] → 도면 발송(영업 전달) · 도면방 PUSH 고르기 창 계약.

설계서 docs/specs/2026-11-05-wizard-save-send-options_SPEC.md (사용자 결정 2026-11-05).
"""
from __future__ import annotations

import json
import shutil
import subprocess
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
    assert TPL.index("js/drawing/wizard.js') }}?v=20261106b") < TPL.index("js/drawing/save-send.js') }}?v=20261106a")


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


# ---- 2026-11-06 보고: 일괄 전달 뒤 한 장을 고쳐 다시 보내면 고치기 전 도면이 나간다 ----
# 운영 주문 5862 · 5803: 시트 A 를 고쳐 [저장](대기함만) → 시트 B 에서 [저장 + 전달 + 도면방] → 전달은 B 만,
# 도면방에는 A 의 옛 전달본이 나갔다. [저장] + 발송은 대기함에 먼저 넣어 둔 다른 시트도 같이 전달해야 한다.

RUNNER = ROOT / "tests/domains/save_send_runner.js"
SEND_PATH = ROOT / "static/js/drawing/save-send.js"


def _run(scenario: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(RUNNER), str(SEND_PATH)], input=json.dumps(scenario),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _transfer_body(out: dict) -> dict:
    bodies = [c["body"] for c in out["calls"] if c["url"].endswith("/transfer-drawing")]
    assert len(bodies) == 1, out["calls"]
    return bodies[0]


def test_single_save_send_also_transfers_other_waiting_sheets():
    out = _run({"kind": "one", "sheets": ["s-1", "s-2"], "current": "s-2",
                "pending": ["s-1", "s-2"], "send": True, "push": True})
    body = _transfer_body(out)
    assert sorted(body["pending_sheet_ids"]) == ["s-1", "s-2"], body
    assert body["mode"] == "APPEND"   # 대기함에 없는 장(옛 전달본)은 그대로 둔다
    calls = [c["url"] for c in out["calls"]]
    assert calls.index(next(u for u in calls if u.endswith("/transfer-drawing"))) < calls.index("pushRoom")


def test_single_save_send_ignores_waiting_entries_of_deleted_sheets():
    out = _run({"kind": "one", "sheets": ["s-2"], "current": "s-2",
                "pending": ["s-gone", "s-2"], "send": True, "push": False})
    assert _transfer_body(out)["pending_sheet_ids"] == ["s-2"]


def test_single_save_send_when_only_current_sheet_waits():
    out = _run({"kind": "one", "sheets": ["s-1", "s-2"], "current": "s-2",
                "pending": ["s-2"], "send": True, "push": False})
    assert _transfer_body(out)["pending_sheet_ids"] == ["s-2"]
    assert not any(c["url"] == "pushRoom" for c in out["calls"])


class _UniqueStorage:
    """실제 storage 처럼 올릴 때마다 새 key."""

    def __init__(self):
        self.n = 0

    def upload_file(self, file_obj, filename, folder):
        self.n += 1
        return {"success": True, "key": f"{folder}/{self.n}_{filename}"}

    def delete_file(self, key):
        return True


def test_server_replaces_both_waiting_sheets_and_keeps_the_rest(client, monkeypatch):
    """운영 5862 순서: 4장 일괄 전달 → A 고쳐 저장만 → B 고쳐 저장 + 전달(A · B, APPEND) → A · B 새 판, 나머지 그대로."""
    import copy
    import io

    from sqlalchemy.orm.attributes import flag_modified

    from db import db_session
    from models import Order
    from tests.domains.test_drawing_wizard_api import _login_participant_admin, _order_with_assignee

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: _UniqueStorage())
    user = _login_participant_admin(client, username="save-send-resend")
    order = _order_with_assignee(user.id)
    oid = order.id
    ids = ["s-a", "s-b", "s-c", "s-d"]
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"] = {"v": 1, "sheets": [{"id": i, "name": i, "form": {}, "objects": []} for i in ids]}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()

    def save_png(sheet_id):
        resp = client.post(f"/api/orders/{oid}/drawing-wizard/sheet-png", content_type="multipart/form-data",
                           data={"file": (io.BytesIO(b"PNG-" + sheet_id.encode()), f"{sheet_id}.png"), "sheet_id": sheet_id})
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["data"]["key"]

    def transfer(sheet_ids, mode):
        resp = client.post(f"/api/orders/{oid}/transfer-drawing",
                           json={"note": "", "files": [], "pending_sheet_ids": sheet_ids, "mode": mode})
        assert resp.status_code == 200 and resp.get_json()["success"] is True, resp.get_json()

    old = {i: save_png(i) for i in ids}
    transfer(ids, "")
    new_a = save_png("s-a")            # 고쳐서 [저장]만
    new_b = save_png("s-b")            # 고쳐서 [저장 + 전달]
    transfer(["s-a", "s-b"], "APPEND")

    db_session.expire_all()
    cur = db_session.query(Order).filter_by(id=oid).first().structured_data["drawing_current_files"]
    assert [(f["sheet_id"], f["key"]) for f in cur] == [
        ("s-a", new_a), ("s-b", new_b), ("s-c", old["s-c"]), ("s-d", old["s-d"])]
