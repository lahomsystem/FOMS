/**
 * 완료 주문 AS 도면을 채널톡 도면방으로 보낸다(설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md D4).
 *
 * 지금 도면방 PUSH 길(POST /api/channel/push-manual push_kind='drawing_room')에 as_drawing: true 를 싣는다.
 * 서버가 본문 앞에 [AS] 를 붙이고, 첨부는 AS 차수 파일, 이력은 원래 도면 도면방 이력과 따로 둔다.
 * 담당 영업 개인방에도 같이 간다(원래 도면방 PUSH 와 같은 규칙).
 *
 * window.FomsAsRoomPush.send(orderId, { skipConfirm, toast }) → Promise<boolean>
 * - 담당자 개인방을 못 찾으면(409 manager_room_unresolved) 공용방에만 보낼지 묻는다.
 * - 이미 보낸 적이 있으면(재전송) 다시 보내는 까닭을 묻는다(서버가 1자 이상 요구).
 * 마법사(wizard-as.js)와 도면 작업실 실행판(workbench-as.js)이 같이 쓴다.
 */
(function () {
  'use strict';
  if (window.FomsAsRoomPush) return;

  async function post(body) {
    var status = 0;
    var data = {};
    try {
      var res = await fetch('/api/channel/push-manual', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body),
      });
      status = res.status;
      try { data = await res.json(); } catch (_) { data = {}; }
    } catch (e) {
      data = { success: false, message: '인터넷 연결을 확인해 주세요.' };
    }
    return { status: status, data: data || {} };
  }

  function say(toast, text, isError) {
    if (typeof toast === 'function') { toast(text, isError ? { error: true } : undefined); return; }
    window.alert(text);
  }

  async function send(orderId, opts) {
    opts = opts || {};
    var toast = opts.toast;
    if (!opts.skipConfirm && !window.confirm('채널톡 도면방에 [AS] AS 도면을 보내요.\n담당 영업 개인방에도 같이 가요.')) {
      return false;
    }
    var body = { order_id: Number(orderId), push_kind: 'drawing_room', as_drawing: true };
    var r = await post(body);
    if (r.status === 409 && r.data.error === 'manager_room_unresolved') {
      if (!window.confirm((r.data.message || '담당자 개인방을 찾지 못했어요.') + '\n공용 도면방에만 보낼까요?')) return false;
      body.allow_without_manager_room = true;
      r = await post(body);
    }
    if (r.status === 400 && /재전송/.test(String(r.data.message || ''))) {
      var note = window.prompt('이미 보낸 AS 도면이에요. 다시 보내는 까닭을 적어 주세요. (예: 손잡이 위치 고침)', '');
      if (!note || !note.trim()) return false;
      body.change_note = note.trim().slice(0, 500);
      r = await post(body);
    }
    if (!r.data.success) {
      say(toast, (r.data.message || r.data.error || '도면방에 보내지 못했어요.'), true);
      return false;
    }
    say(toast, r.data.message || '도면방에 [AS] AS 도면을 보냈어요.', false);
    return true;
  }

  window.FomsAsRoomPush = { send: send };
})();
