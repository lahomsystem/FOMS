"""S2 — 도면 탭 보내기·확정 JS 를 Node 로 실제로 돌려 요청 순서·잠금·이동을 본다(설계서 2026-09-29 §3.6 + Q5).

문자열 존재 단언이 아니라 동작 단언이다: 갈래를 ``if (false)`` 로 꺼도 통과하는 단언은 아무것도 지키지 않는다.
- 보내기: 발송 전 실패(503 등)면 방금 만든 링크를 회수 · network/연결 끊김은 회수 없이 잠금 유지 ·
  벤더 거절은 회수 없이 잠금 해제 · 성공이면 새로고침 · 두 번 눌러도 링크 한 번 · 번호 바꾸기(to_phone·저장).
- 고객 OK: 확정 → (컨펌까지·new_stage CONFIRM 일 때만) 승인 → 도면 탭에 머묾 · ALREADY_TRANSITIONED 는 성공.
- 수정요청 출처 extras · 요청 고치기 본문 · PC 긴급 호출 · 전달 취소 [그래도 취소].
"""

from __future__ import annotations

import pytest

from tests.support.drawing_customer_js_harness import ROOT, run_js

SEND_JS = "static/js/foms/drawing-customer-send.js"
OK_JS = "static/js/foms/drawing-customer-ok.js"
EDIT_JS = "static/js/foms/drawing-revision-edit.js"
URGENT_JS = "static/js/foms/drawing-urgent-call-pc.js"

# 보내기 시트 가짜 DOM — 채널·번호 바꾸기는 driver 앞에서 CHANNEL·OVERRIDE·SAVE 로 정한다.
SEND_DOM = r"""
const root = makeEl({ id: 'dwCustomerSendModal', attrs: {
  'data-order-id': '77', 'data-round-label': '2차', 'data-customer-name': '홍길동', 'data-has-phone': 'true',
  'data-sent-text': '', 'data-doc-label-drawing': '도면', 'data-doc-label-bundle': '도면·계약서',
  'data-bundle-both-template': 'false', 'data-structured-updated-at': '2026-09-29 10:11:12' } });
const submitBtn = makeEl({ attrs: { 'data-send-submit': '' } });
submitBtn._closest['[data-send-submit]'] = submitBtn;
const errEl = makeEl({ cls: ['d-none'] });
const statusEl = makeEl({ cls: ['d-none'] });
const phoneBox = makeEl({ cls: OVERRIDE ? [] : ['d-none'] });
const phoneInput = makeEl({ id: 'dw-send-phone', value: OVERRIDE || '' });
const saveBox = makeEl({ checked: !!SAVE });
const kindDrawing = makeEl({ value: 'drawing', checked: true });
const channelEl = makeEl({ value: CHANNEL, checked: true });
Object.assign(root._sel, {
  '[data-send-submit]': submitBtn, '[data-send-error]': errEl, '[data-send-status]': statusEl,
  '[data-send-preview]': makeEl({}), '[data-send-nophone]': makeEl({ cls: ['d-none'] }),
  '[data-send-again]': makeEl({ cls: ['d-none'] }), '[data-send-again-text]': makeEl({}),
  '[data-send-phone-edit]': phoneBox, '#dw-send-phone': phoneInput, '#dw-send-save-phone': saveBox,
  '#dw-send-kind-drawing': kindDrawing, '#dw-send-channel-kakao': makeEl({}),
  'input[name="dw-send-kind"]:checked': kindDrawing, 'input[name="dw-send-channel"]:checked': channelEl,
});
root._all['input[name="dw-send-kind"], input[name="dw-send-channel"]'] = [kindDrawing, channelEl];
route('/api/share/create/77', function () {
  return Resp(200, { success: true, data: { share_id: 501, token: 'tok-secret', url: 'https://x/s/tok',
    to_phone: '01011112222', sms_text: '링크 tok' }, error: null });
});
route('/api/share/revoke/', function () { return Resp(200, { success: true, data: {}, error: null }); });
route('/structured/fields', function () { return Resp(200, { success: true }); });
loadSources();
fire('show.bs.modal', root, { relatedTarget: makeEl({ attrs: { 'data-customer-send-mode': 'first' } }) });
"""


def _send(send_route: str, *, channel: str = "kakao", override: str = "", save: bool = False, clicks: int = 1,
          create_route: str = "", then_hide: bool = False) -> dict:
    driver = (
        f"const CHANNEL = {channel!r}; const OVERRIDE = {override!r}; const SAVE = {str(save).lower()};\n"
        + (create_route + "\n" if create_route else "")
        + SEND_DOM
        + send_route
        + "\nfor (let i = 0; i < " + str(clicks) + "; i += 1) fire('click', submitBtn);\nawait flush();\n"
        + "const disabledBeforeHide = submitBtn.disabled;\n"
        + ("fire('hidden.bs.modal', root);\n" if then_hide else "")
        + "out({ err: hidden(errEl) ? '' : errEl.textContent, status: hidden(statusEl) ? '' : statusEl.textContent,"
        + " disabled: disabledBeforeHide });"
    )
    return run_js([SEND_JS], driver)


def _urls(result: dict) -> list[str]:
    return [c["url"] for c in result["calls"]]


def test_send_success_reloads_with_drawing_tab_marker():
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: true, data: { sent: true, error: null }, error: null }); });")
    assert _urls(r) == ["/api/share/create/77", "/api/share/send-alimtalk/501"]
    send_body = r["calls"][1]["body"]
    assert send_body == {"token": "tok-secret", "source_screen": "drawing_tab"}  # to_phone 은 바꿨을 때만
    assert r["calls"][0]["body"] == {"kind": "drawing"}
    assert r["reloaded"] == 1 and r["disabled"] is True
    assert r["storageWrites"] == []  # 토큰 원문을 저장소에 쓰지 않는다


@pytest.mark.parametrize("status,code", [(503, "not_configured"), (400, "no_valid_phone"), (409, "duplicate_send"),
                                         (410, "share_revoked"), (404, "share_not_found")])
def test_pre_send_failure_revokes_fresh_link_and_unlocks(status, code):
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              f" return Resp({status}, {{ success: false, data: null, error: '{code}' }}); }});")
    assert _urls(r) == ["/api/share/create/77", "/api/share/send-alimtalk/501", "/api/share/revoke/501"]
    assert r["disabled"] is False and r["reloaded"] == 0
    assert r["err"].startswith("알림톡을 보내지 못했어요")


def test_network_error_code_keeps_lock_without_revoke():
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: false, data: { sent: false, error: 'network' }, error: 'network' }); });")
    assert _urls(r) == ["/api/share/create/77", "/api/share/send-alimtalk/501"]  # 회수 없음
    assert r["disabled"] is True and "확실하지 않아요" in r["err"]


def test_connection_drop_keeps_lock_without_revoke():
    r = _send("route('/api/share/send-alimtalk/501', function () { throw new Error('offline'); });")
    assert _urls(r) == ["/api/share/create/77", "/api/share/send-alimtalk/501"]
    assert r["disabled"] is True and "확실하지 않아요" in r["err"] and r["reloaded"] == 0


def test_unknown_vendor_error_keeps_lock_like_network():
    """'unknown'(벤더 예외를 분류 못 함)은 접수됐는지 모른다 — 잠금 유지 · 회수 없음 · 닫으면 새로고침(두 통 방지)."""
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: false, data: { sent: false, error: 'unknown' }, error: 'unknown' }); });",
              then_hide=True)
    assert _urls(r) == ["/api/share/create/77", "/api/share/send-alimtalk/501"]
    assert r["disabled"] is True and "확실하지 않아요" in r["err"] and r["reloaded"] == 1


@pytest.mark.parametrize("code,text", [("template_mismatch", "템플릿"), ("length_exceeded", "1,000자")])
def test_vendor_reject_codes_have_korean_labels(code, text):
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              f" return Resp(200, {{ success: false, data: {{ sent: false, error: '{code}' }}, error: '{code}' }}); }});")
    assert r["disabled"] is False and text in r["err"] and code not in r["err"]


def test_create_connection_drop_is_unsure_and_reloads_on_close():
    """링크 만들기 요청이 끊기면 서버엔 링크가 생겼을 수 있다 — '확실하지 않아요' + 잠금 + 닫으면 새로고침."""
    r = _send("", create_route="route('/api/share/create/77', function () { throw new Error('offline'); });",
              then_hide=True)
    assert _urls(r) == ["/api/share/create/77"]
    assert "만들었는지 확실하지 않아요" in r["err"] and r["disabled"] is True and r["reloaded"] == 1


def test_create_server_reject_unlocks_without_reload():
    """대조군: 서버가 만들기를 거절(403 등)하면 링크가 없다 — 잠금 풀고 새로고침도 안 한다."""
    r = _send("", create_route="route('/api/share/create/77', function () {"
              " return Resp(403, { success: false, data: null, error: 'forbidden' }); });", then_hide=True)
    assert r["disabled"] is False and "링크를 만들지 못했어요" in r["err"] and r["reloaded"] == 0


def test_vendor_reject_unlocks_without_revoke():
    r = _send("route('/api/share/send-sms/501', function () {"
              " return Resp(200, { success: false, data: { sent: false, error: 'balance' }, error: 'balance' }); });",
              channel="company")
    assert _urls(r) == ["/api/share/create/77", "/api/share/send-sms/501"]
    assert r["disabled"] is False and "접수되지 않았어요" in r["err"] and "잔액" in r["err"]


def test_double_click_creates_one_link():
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: true, data: { sent: true, error: null }, error: null }); });", clicks=3)
    assert _urls(r).count("/api/share/create/77") == 1


def test_changed_number_goes_to_this_send_only_and_saves_when_checked():
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: true, data: { sent: true, error: null }, error: null }); });",
              override="010-3333-4444", save=True)
    assert r["calls"][1]["body"]["to_phone"] == "01033334444"
    patch = r["calls"][2]
    assert patch["method"] == "PATCH" and patch["url"] == "/api/orders/77/structured/fields"
    # 기존 번호 형식(하이픈)으로 저장 · 먼저 열어 둔 다른 저장과 겹치면 서버가 409 로 막게 X-If-Match 를 싣는다.
    assert patch["body"] == {"field": "parties.customer.phone", "value": "010-3333-4444"}
    assert patch["headers"].get("X-If-Match") == "2026-09-29 10:11:12"
    assert r["reloaded"] == 1


def test_save_phone_conflict_explains_and_keeps_sent_result():
    """주문이 그새 바뀌었으면(409 CONFLICT) 발송은 그대로 두고 '주문 번호 저장은 못 했어요' 를 알린다."""
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: true, data: { sent: true, error: null }, error: null }); });"
              "routes.unshift({ match: '/structured/fields', fn: function () {"
              " return Resp(409, { success: false, error: 'CONFLICT' }); } });",
              override="01033334444", save=True)
    assert "주문 번호 저장은 못 했어요" in r["status"] and "다른 곳에서 먼저 바뀌었어요" in r["status"]
    assert r["reloaded"] == 0


def test_changed_number_without_save_does_not_patch_order():
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(200, { success: true, data: { sent: true, error: null }, error: null }); });",
              override="010-3333-4444", save=False)
    assert all(c["method"] != "PATCH" for c in r["calls"])


def test_invalid_phone_400_revokes_and_bad_input_never_creates():
    r = _send("route('/api/share/send-alimtalk/501', function () {"
              " return Resp(400, { success: false, data: null, error: 'INVALID_PHONE' }); });", override="01099998888")
    assert _urls(r)[-1] == "/api/share/revoke/501" and "수신 번호" in r["err"]
    bad = _send("", override="12-34")
    assert bad["calls"] == [] and "수신 번호" in bad["err"]


def test_self_sms_opens_sms_app_with_server_text():
    r = _send("", channel="mine")
    assert _urls(r) == ["/api/share/create/77"]
    assert r["href"].startswith("sms:01011112222?body=")
    assert "기록되지 않아요" in r["status"]


# --------------------------------------------------------------------------- 고객 OK · 승인

OK_DOM = r"""
const okRoot = makeEl({ id: 'dwCustomerOkModal', attrs: { 'data-order-id': '77', 'data-round-label': '2차',
  'data-can-approve': CAN_APPROVE ? 'true' : 'false', 'data-mode': 'customer' } });
const okBtn = makeEl({});
okBtn._closest['[data-ok-submit]'] = okBtn;
const okErr = makeEl({ cls: ['d-none'] });
const afterEl = makeEl({ value: AFTER, checked: true });
Object.assign(okRoot._sel, { '[data-ok-submit]': okBtn, '[data-ok-error]': okErr, '[data-ok-title]': makeEl({}),
  '[data-ok-lead]': makeEl({}), '#dw-ok-note': makeEl({ value: ' 이대로 해 주세요 ' }),
  'input[name="dw-ok-via"]:checked': makeEl({ value: 'kakao' }), '#dw-ok-after-approve': makeEl({}),
  '[data-ok-approve-warning]': makeEl({}) });
if (AFTER) okRoot._sel['input[name="dw-ok-after"]:checked'] = afterEl;
loadSources();
fire('show.bs.modal', okRoot, { relatedTarget: makeEl({ attrs: { 'data-customer-ok-mode': 'customer' } }) });
if (AFTER) okRoot._sel['input[name="dw-ok-after"]:checked'] = afterEl;
okRoot._sel['input[name="dw-ok-via"]:checked'] = makeEl({ value: 'kakao' });
okRoot._sel['#dw-ok-note'].value = ' 이대로 해 주세요 ';
"""


def _ok(confirm_route: str, approve_route: str = "", *, can_approve: bool = True, after: str = "approve") -> dict:
    driver = (
        f"const CAN_APPROVE = {str(can_approve).lower()}; const AFTER = {after!r};\n" + OK_DOM
        + confirm_route + approve_route
        + "\nfire('click', okBtn);\nawait flush();\n"
        + "out({ err: hidden(okErr) ? '' : okErr.textContent, disabled: okBtn.disabled });"
    )
    return run_js([OK_JS], driver)


CONFIRM_OK = ("route('/confirm-drawing-receipt', function () {"
              " return Resp(200, { success: true, message: '확정', new_stage: 'CONFIRM', stage_moved: true }); });")


def test_ok_confirm_then_approve_then_stay_on_drawing_tab():
    r = _ok(CONFIRM_OK, "route('/quest/approve', function () {"
            " return Resp(200, { success: true, all_approved: true, auto_transitioned: true, next_stage: '생산' }); });")
    assert _urls(r) == ["/api/orders/77/confirm-drawing-receipt", "/api/orders/77/quest/approve"]
    assert r["calls"][0]["body"] == {"customer_ok": True, "customer_ok_via": "kakao", "customer_ok_note": "이대로 해 주세요"}
    assert r["calls"][1]["body"]["idempotency_key"]
    assert r["href"] == "/erp/drawing-workbench/77?tab=timeline"
    assert any("생산으로 넘겼어요" in t for t in r["toasts"])


def test_ok_confirm_only_skips_approve():
    r = _ok(CONFIRM_OK, can_approve=True, after="only")
    assert _urls(r) == ["/api/orders/77/confirm-drawing-receipt"]
    assert r["href"] == "/erp/drawing-workbench/77?tab=timeline"


def test_ok_without_approve_power_never_approves():
    r = _ok(CONFIRM_OK, can_approve=False, after="")
    assert _urls(r) == ["/api/orders/77/confirm-drawing-receipt"]


def test_ok_approve_skipped_when_stage_did_not_move_to_confirm():
    r = _ok("route('/confirm-drawing-receipt', function () {"
            " return Resp(200, { success: true, new_stage: 'PRODUCTION', stage_moved: false }); });")
    assert _urls(r) == ["/api/orders/77/confirm-drawing-receipt"]


def test_ok_confirm_failure_changes_nothing():
    r = _ok("route('/confirm-drawing-receipt', function () {"
            " return Resp(403, { success: false, message: '지정된 영업 담당자만' }); });")
    assert _urls(r) == ["/api/orders/77/confirm-drawing-receipt"]
    assert r["href"] == "" and r["disabled"] is False and "지정된 영업 담당자만" in r["err"]


def test_ok_already_transitioned_counts_as_success():
    r = _ok(CONFIRM_OK, "route('/quest/approve', function () {"
            " return Resp(409, { success: false, code: 'ALREADY_TRANSITIONED', message: '이미' }); });")
    assert not [a for a in r["alerts"] if "못 했어요" in a]
    assert any("이미 생산으로 넘어갔어요" in t for t in r["toasts"])


def test_ok_approve_failure_explains_and_still_stays():
    r = _ok(CONFIRM_OK, "route('/quest/approve', function () {"
            " return Resp(403, { success: false, message: '권한 없음' }); });")
    assert any(a.startswith("도면은 확정했어요. 고객 컨펌은 못 했어요 — 권한 없음") for a in r["alerts"])
    assert r["href"] == "/erp/drawing-workbench/77?tab=timeline"


def test_ok_team_mode_quest_reports_missing_teams():
    r = _ok(CONFIRM_OK, "route('/quest/approve', function () {"
            " return Resp(200, { success: true, all_approved: false, missing_teams: ['CS'], auto_transitioned: false,"
            " next_stage: null }); });")
    assert any("남은 팀: CS" in t for t in r["toasts"])


@pytest.mark.parametrize("answer,expect_call", [(True, True), (False, False)])
def test_bar_approve_asks_first(answer, expect_call):
    driver = (
        f"window.__confirmAnswer = {str(answer).lower()};\nloadSources();\n"
        "route('/quest/approve', function () { return Resp(200, { success: true, auto_transitioned: true,"
        " next_stage: '생산' }); });\n"
        "const b = makeEl({ attrs: { 'data-order-id': '77' } }); b._closest['[data-customer-approve]'] = b;\n"
        "fire('click', b); await flush(); out({});"
    )
    r = run_js([OK_JS], driver)
    assert (_urls(r) == ["/api/orders/77/quest/approve"]) is expect_call
    assert any(a.startswith("CONFIRM:고객 컨펌을 승인하고 생산으로") for a in r["alerts"])


@pytest.mark.parametrize("source,via,expected", [
    ("customer", "kakao", {"source": "customer", "received_via": "kakao"}),
    ("sales", "kakao", {"source": "sales"}),
    ("", "", {}),
])
def test_revision_extras(source, via, expected):
    driver = (
        "const rev = makeEl({ id: 'dwRevisionModal' });\n"
        + (f"rev._sel['input[name=\"dw-revision-source\"]:checked'] = makeEl({{ value: {source!r} }});\n" if source else "")
        + (f"rev._sel['input[name=\"dw-revision-via\"]:checked'] = makeEl({{ value: {via!r} }});\n" if via else "")
        + "loadSources(); out({ extras: window.fomsDrawingRevisionExtras() });"
    )
    assert run_js([OK_JS], driver)["extras"] == expected


# --------------------------------------------------------------------------- 요청 고치기 · 긴급 호출 · 전달 취소


def test_revision_edit_posts_kept_and_new_files_with_targets():
    driver = r"""
const prefill = { note: '원래', source: 'customer', received_via: 'kakao',
  files: [{ key: 'orders/77/drawing_gateway/revisions/a.png', filename: 'a.png' },
          { key: 'orders/77/drawing_gateway/revisions/b.png', filename: 'b.png' }] };
const edit = makeEl({ id: 'dwRevisionEditModal', attrs: { 'data-order-id': '77', 'data-drawing-count': '2',
  'data-edit-revision': JSON.stringify(prefill) } });
const btn = makeEl({}); btn._closest['[data-edit-submit]'] = btn;
const note = makeEl({ id: 'dw-edit-note' });
const keepA = makeEl({ checked: true, attrs: { 'data-edit-keep-index': '0' } });
const keepB = makeEl({ checked: false, attrs: { 'data-edit-keep-index': '1' } });
const filesInput = makeEl({ files: ['NEWFILE'] });
Object.assign(edit._sel, { '[data-edit-submit]': btn, '[data-edit-error]': makeEl({ cls: ['d-none'] }),
  '#dw-edit-note': note, '#dw-edit-new-files': filesInput, '[data-edit-files]': makeEl({}),
  '#dw-edit-source-customer': makeEl({}), '[data-edit-via-block]': makeEl({}) });
const editStatus = makeEl({ cls: ['d-none'] }); edit._sel['[data-edit-status]'] = editStatus;
let statusDuringUpload = '';
window.fomsDrawingUploadRevisionFiles = async function (files) {
  statusDuringUpload = hidden(editStatus) ? '' : editStatus.textContent;
  return files.map(function () { return { key: 'orders/77/drawing_gateway/revisions/new.png', filename: 'new.png' }; });
};
route('/request-revision/edit', function () { return Resp(200, { success: true, data: { request: {} } }); });
loadSources();
fire('show.bs.modal', edit);
note.value = '고친 내용';
edit._all['[data-edit-keep-index]'] = [keepA, keepB];
edit._all['input[name="dw-edit-target"]:checked'] = [makeEl({ value: 'orders/77/drawing/plan-2.png' })];
edit._sel['input[name="dw-edit-source"]:checked'] = makeEl({ value: 'customer' });
edit._sel['input[name="dw-edit-via"]:checked'] = makeEl({ value: 'phone' });
fire('click', btn); await flush(); out({ note: note.value, during: statusDuringUpload });
"""
    r = run_js([EDIT_JS], driver)
    assert "올리는 중" in r["during"]  # 공용 진행 막대는 닫힌 창 안이라 이 창에 따로 보인다
    assert _urls(r) == ["/api/orders/77/request-revision/edit"]
    assert r["calls"][0]["body"] == {
        "note": "고친 내용",
        "files": [{"key": "orders/77/drawing_gateway/revisions/a.png", "filename": "a.png"},
                  {"key": "orders/77/drawing_gateway/revisions/new.png", "filename": "new.png"}],
        "source": "customer", "received_via": "phone",
        "target_file_keys": ["orders/77/drawing/plan-2.png"],
    }
    assert r["href"] == "/erp/drawing-workbench/77?tab=requests"


def test_pc_urgent_call_loads_same_endpoints_and_sends_int_target():
    driver = r"""
const m = makeEl({ id: 'dwUrgentCallModal', attrs: { 'data-order-id': '77' } });
const box = makeEl({}); const msg = makeEl({ id: 'dw-urgent-message' }); const send = makeEl({ disabled: true });
send._closest['[data-dw-urgent-send]'] = send;
Object.assign(m._sel, { '[data-dw-urgent-targets]': box, '#dw-urgent-message': msg, '[data-dw-urgent-send]': send,
  '[data-dw-urgent-error]': makeEl({ cls: ['d-none'] }) });
const writes = [];
window.FOMSNotificationWrite = { fetch: async function (url, opts) { writes.push([url, JSON.parse(opts.body)]);
  return Resp(200, { success: true, message: '보냄' }); } };
route('/urgent-targets', function () { return Resp(200, { success: true, targets: [
  { id: 5, name: '영업이', team: 'SALES', team_label: '영업팀', role: 'STAFF' }] }); });
loadSources();
const opener = makeEl({ attrs: { 'data-order-id': '77', 'data-urgent-message': '확인 부탁' } });
opener._closest['[data-dw-urgent-call]'] = opener;
fire('click', opener); await flush();
const target = makeEl({ attrs: { 'data-dw-urgent-target': '5' } });
target._closest['[data-dw-urgent-target]'] = target; m._inside.push(target);
fire('click', target);
fire('click', send); await flush();
out({ writes: writes, prefilled: msg.value, rendered: box.children.length });
"""
    r = run_js([URGENT_JS], driver)
    assert _urls(r) == ["/erp/api/orders/77/urgent-targets"]
    assert r["writes"] == [["/erp/api/orders/77/urgent-mention", {"target_user_id": 5, "message": "확인 부탁"}]]
    assert r["prefilled"] == "확인 부탁" and r["rendered"] == 1
    assert ["show", "dwUrgentCallModal"] in r["modalOps"] and ["hide", "dwUrgentCallModal"] in r["modalOps"]


def test_cancel_warn_confirm_calls_cancel_once_and_stays():
    driver = r"""
const w = makeEl({ id: 'dwCancelWarnModal', attrs: { 'data-order-id': '77' } });
w._sel['[data-cancel-warn-error]'] = makeEl({ cls: ['d-none'] });
route('/cancel-transfer', function () { return Resp(200, { success: true }); });
loadSources();
const b = makeEl({}); b._closest['[data-cancel-transfer-confirm]'] = b;
fire('click', b); fire('click', b); await flush(); out({});
"""
    r = run_js([URGENT_JS], driver)
    assert _urls(r) == ["/api/orders/77/cancel-transfer"]
    assert not [a for a in r["alerts"] if a.startswith("CONFIRM:")]  # 확인창 두 번 금지
    assert r["href"] == "/erp/drawing-workbench/77?tab=timeline"


@pytest.mark.parametrize("opener_source,expect", [("customer", "customer"), ("", "sales")])
def test_revision_sheet_preselects_source_from_opener(opener_source, expect):
    """[고객이 고쳐 달래요]는 '고객 요청'을, 출처 없는 옛 버튼은 '내 의견'(지금 동작)을 미리 고른다."""
    driver = (
        "const rev = makeEl({ id: 'dwRevisionModal' });\n"
        "const rc = makeEl({ value: 'customer' }); const rs = makeEl({ value: 'sales' });\n"
        "const via = makeEl({ cls: ['d-none'] }); const hint = makeEl({ cls: ['d-none'] });\n"
        "Object.assign(rev._sel, { '#dw-revision-source-customer': rc, '#dw-revision-source-sales': rs,\n"
        "  '[data-revision-via-block]': via, '[data-revision-note-hint]': hint, '[data-revision-title]': makeEl({}),\n"
        "  '[data-revision-note-label]': makeEl({}) });\n"
        "loadSources();\n"
        f"const opener = makeEl({{ attrs: {{ 'data-revision-source': {opener_source!r} }} }});\n"
        "const origQ = rev.querySelector;\n"
        "rev.querySelector = function (s) { if (s === 'input[name=\"dw-revision-source\"]:checked') {"
        " return rc.checked ? rc : (rs.checked ? rs : null); } return origQ(s); };\n"
        "fire('show.bs.modal', rev, { relatedTarget: opener });\n"
        "out({ customer: rc.checked, sales: rs.checked, viaShown: !hidden(via),"
        " attr: rev.getAttribute('data-revision-source') });"
    )
    r = run_js([OK_JS], driver)
    assert r["attr"] == expect
    assert r["customer"] is (expect == "customer") and r["viaShown"] is (expect == "customer")


# --------------------------------------------------------------------------- 전달 취소 경고 갈래(리뷰 P2)

WARN_DOM = r"""
const warn = makeEl({ id: 'dwCancelWarnModal', attrs: { 'data-order-id': '77' } });
const warnText = makeEl({});
warn._sel['[data-cancel-warn-text]'] = warnText;
const cancelBtn = makeEl({ id: 'btn-cancel-transfer', attrs: ATTRS });
window.matchMedia = function (q) { return { matches: NARROW && q === '(max-width: 991.98px)' }; };
"""


def _warn(attrs: dict, *, narrow: bool = False, with_modal: bool = True) -> dict:
    driver = (
        f"const ATTRS = {attrs!r}; const NARROW = {str(narrow).lower()};\n" + WARN_DOM
        + ("" if with_modal else "delete byId['dwCancelWarnModal'];\n")
        + "loadSources();\n"
        + "const handled = window.fomsDrawingCancelWarn(cancelBtn);\n"
        + "out({ handled: handled, text: warnText.textContent });"
    )
    return run_js([URGENT_JS], driver)


PC_TEXT = {"data-customer-sent-text-pc": "보냈어요(PC)", "data-customer-sent-text-mobile": "보냈어요(모바일)"}


@pytest.mark.parametrize("narrow,expect", [(False, "보냈어요(PC)"), (True, "보냈어요(모바일)")])
def test_cancel_warn_picks_text_by_width_and_opens_sheet_without_confirm(narrow, expect):
    r = _warn(PC_TEXT, narrow=narrow)
    assert r["handled"] is True and r["text"] == expect
    assert ["show", "dwCancelWarnModal"] in r["modalOps"]
    assert not [a for a in r["alerts"] if a.startswith("CONFIRM:")] and r["calls"] == []


def test_cancel_warn_without_text_leaves_plain_confirm_path():
    r = _warn({})
    assert r["handled"] is False and r["modalOps"] == []


def test_cancel_warn_without_sheet_falls_back():
    r = _warn(PC_TEXT, with_modal=False)
    assert r["handled"] is False and r["modalOps"] == []


def _inline_fn(signature: str) -> str:
    """작업실 인라인 스크립트의 함수 본문을 그대로 떼어 낸다(문자열 단언이 아니라 실행하려고)."""
    body = (ROOT / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")
    start = body.index(signature)
    depth, i = 0, body.index("{", start)
    while True:
        ch = body[i]
        depth += 1 if ch == "{" else -1 if ch == "}" else 0
        i += 1
        if depth == 0:
            return body[start:i]


def _run_inline(attrs: dict, *, helper: str, confirm: bool = True) -> dict:
    driver = (
        f"const ATTRS = {attrs!r}; const NARROW = false;\n" + WARN_DOM
        + "const orderId = 77; const shown = [];\n"
        + "function showWorkbenchToast(m) { shown.push(m); }\n"
        + f"window.__confirmAnswer = {str(confirm).lower()};\n"
        + "route('/cancel-transfer', function () { return Resp(200, { success: true }); });\n"
        + helper + "\n"
        + _inline_fn("async function cancelTransfer() {") + "\n"
        + "await cancelTransfer(); await flush();\n"
        + "out({ helperCalls: window.__helperCalls || 0 });"
    )
    return run_js([], driver)


def test_inline_cancel_transfer_uses_warn_sheet_when_js_loaded():
    r = _run_inline(PC_TEXT, helper="window.__FOMS_DRAWING_URGENT_PC_BOUND = true;"
                    " window.fomsDrawingCancelWarn = function () { window.__helperCalls = (window.__helperCalls || 0) + 1;"
                    " return true; };")
    assert r["helperCalls"] == 1
    assert r["calls"] == [] and not [a for a in r["alerts"] if a.startswith("CONFIRM:")]


def test_inline_cancel_transfer_falls_back_to_confirm_with_warning_when_js_missing():
    """새 JS 가 핀·캐시 문제로 안 떴으면 경고 문구를 확인창으로 보이고, 예를 누르면 전달 취소가 된다(막히지 않는다)."""
    r = _run_inline(PC_TEXT, helper="")
    assert "CONFIRM:보냈어요(PC)" in r["alerts"]
    assert _urls(r) == ["/api/orders/77/cancel-transfer"] and r["href"] == "/erp/drawing-workbench/77?tab=timeline"


def test_inline_cancel_transfer_without_warning_keeps_old_confirm():
    r = _run_inline({}, helper="window.fomsDrawingCancelWarn = function () { return false; };", confirm=False)
    assert [a for a in r["alerts"] if a.startswith("CONFIRM:")] == [
        "CONFIRM:전달 취소 시 최신 전달본 파일과 이력이 함께 정리됩니다. 진행할까요?"]
    assert r["calls"] == []


@pytest.mark.parametrize("attr,flag,loaded", [
    ("data-ok-submit", "__FOMS_DRAWING_CUSTOMER_OK_BOUND", False),
    ("data-send-submit", "__FOMS_DRAWING_CUSTOMER_SEND_BOUND", False),
    ("data-edit-submit", "__FOMS_DRAWING_REVISION_EDIT_BOUND", False),
    ("data-ok-submit", "__FOMS_DRAWING_CUSTOMER_OK_BOUND", True),
])
def test_inline_warns_when_sheet_js_missing(attr, flag, loaded):
    """시트 JS 가 안 떴으면 주 버튼을 눌렀을 때 새로고침 안내가 뜬다. 떴으면(대조군) 아무 말도 안 한다."""
    driver = (
        "const shown = []; function showWorkbenchToast(m) { shown.push(m); }\n"
        + (f"window.{flag} = true;\n" if loaded else "")
        + _inline_fn("function warnIfSheetJsMissing(e) {") + "\n"
        + f"const b = makeEl({{ attrs: {{ {attr!r}: '' }} }});\n"
        + "b._closest['[data-ok-submit], [data-send-submit], [data-edit-submit]'] = b;\n"
        + "warnIfSheetJsMissing({ target: b });\n"
        + "out({ shown: shown });"
    )
    r = run_js([], driver)
    if loaded:
        assert r["shown"] == []
    else:
        assert len(r["shown"]) == 1 and "새로고침" in r["shown"][0]
