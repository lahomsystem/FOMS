/**
 * 생산 넘어간 주문의 도면 수정 — 보내기 미리 보기 · 보내기 전 확인 창(설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-3 · R1, D2). 작업실 전달 창(workbench-transfer-fix.js)과 마법사 [저장] 창(save-send.js)이 같이 쓴다.
 *
 * - '바뀐 도면' 줄 · 경고 글은 서버 R1(GET /api/orders/<id>/drawing/fix/progress)이 전달 API 와 같은 함수로 계산한다 — 여기는 그리기만.
 * - 확인은 한 번: 경고가 있으면 이 창 하나(아래 글 = 지금 생산 확인 글), 없으면 부른 쪽 확인 글(window.confirm).
 *   [그래도 보내기]를 누르면 물어본 도면 열쇠 목록(ack_worked) · 시공 대기 표지(ack_order_made)를 싣는다 — 서버는 목록에 없는
 *   작업된 도면이 있으면 그 도면 글로 다시 409 를 주고, 그때만 그 글로 한 번 더 묻는다(D2 검토 I).
 * - R1 을 못 받으면(통신 · 5xx · JSON 아님) 지금 확인 글로 한 번 묻는다 — 그 뒤 서버 409 창이 한 번 더 뜰 수 있다(셋째 판 1).
 * - 창은 <dialog>(맨 위 층). 부트스트랩 창 위에서도 초점이 갇히지 않게 그 창 안에 붙인다(host).
 */
(function () {
  'use strict';

  if (window.FomsFixSend) { return; }   // ERP 셸 조각이 다시 읽어도 한 번만(G4)

  var NOTE_MSG = '공장에 남길 메모를 적어 주세요.';
  var PICK_MSG = '바꿀 도면을 골라 주세요.';
  var HOTFIX_TEXT = '생산·시공 단계라 영업 확인 없이 바로 최종 도면이 되고 생산팀에 알림이 갑니다. 전달 취소로 되돌릴 수 없습니다.';
  var ASK_CODES = { WORKED_DRAWING: true, ORDER_MADE: true };

  /** 보낼 것 → R1 질의 글(sheet · pick · target 은 여러 번). 보낼 것이 없어도 미리 보기는 받는다(sheet=). */
  function query(o) {
    var parts = [];
    function add(name, list) {
      (list || []).forEach(function (v) { parts.push(name + '=' + encodeURIComponent(v || '')); });
    }
    add('sheet', o.sheets);
    add('pick', o.picks);
    add('target', o.targets);
    if (o.mode) { parts.push('mode=' + encodeURIComponent(o.mode)); }
    if (o.retransfer) { parts.push('retransfer=1'); }
    if (!(o.sheets && o.sheets.length) && !(o.picks && o.picks.length)) { parts.push('sheet='); }
    return parts.join('&');
  }

  /** R1 미리 보기 — {changed, changed_line, warnings, order_made, error} 또는 null(못 읽음 · 권한 없음). */
  function preview(orderId, o) {
    var url = '/api/orders/' + orderId + '/drawing/fix/progress?' + query(o || {});
    return window.fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        return data && data.success === true && data.data ? (data.data.plan || null) : null;
      })
      .catch(function (err) {
        console.warn('[drawing-fix] preview', err);
        return null;
      });
  }

  /** '바뀐 도면' 줄을 그린다(없으면 숨김). */
  function setChanged(el, plan) {
    if (!el) { return; }
    var text = (plan && plan.changed_line) || '';
    el.textContent = text;
    el.hidden = !text;
  }

  function node(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (text) { el.textContent = text; }
    return el;
  }

  /** 보내기 전 확인 창 — 경고마다 빨간 칸(문장 + 진행 줄), 아래 글, [취소] [그래도 보내기]. 보내면 true. */
  function ask(warnings, noteText, host) {
    var list = (warnings || []).filter(function (w) { return w && w.text; });
    var dialog = node('dialog', 'dfx-dialog');
    if (typeof dialog.showModal !== 'function') {
      var plain = list.map(function (w) { return w.text + (w.line ? '\n' + w.line : ''); }).join('\n\n');
      return Promise.resolve(window.confirm(plain + (noteText ? '\n\n' + noteText : '')));
    }
    dialog.setAttribute('aria-labelledby', 'dfx-dialog-head');
    var head = node('div', 'dfx-dialog__head', '보내기 전 확인');
    head.id = 'dfx-dialog-head';
    var body = node('div', 'dfx-dialog__body');
    list.forEach(function (w) {
      var box = node('div', 'dfx-warn');
      box.appendChild(node('div', 'dfx-warn__text', w.text));
      if (w.line) { box.appendChild(node('div', 'dfx-warn__line', w.line)); }
      body.appendChild(box);
    });
    if (noteText) { body.appendChild(node('p', 'dfx-dialog__note mb-0', noteText)); }
    var foot = node('div', 'dfx-dialog__foot');
    var cancel = node('button', 'dfx-btn dfx-btn--cancel', '취소');
    var go = node('button', 'dfx-btn dfx-btn--go', '그래도 보내기');
    cancel.type = 'button';
    go.type = 'button';
    foot.appendChild(cancel);
    foot.appendChild(go);
    dialog.appendChild(head);
    dialog.appendChild(body);
    dialog.appendChild(foot);
    (host || document.body).appendChild(dialog);
    return new Promise(function (resolve) {
      var answer = false;
      cancel.addEventListener('click', function () { dialog.close(); });
      go.addEventListener('click', function () { answer = true; dialog.close(); });
      dialog.addEventListener('close', function () {
        dialog.remove();
        resolve(answer);
      });
      dialog.showModal();
      go.focus();
    });
  }

  function noAck() { return { idents: [], orderMade: false }; }

  /** 물어본 경고 → 실어 보낼 ack({idents: 도면 열쇠, orderMade: 시공 대기 표지}). */
  function ackOf(warnings) {
    var out = noAck();
    (warnings || []).forEach(function (w) {
      if (w && w.ident && out.idents.indexOf(w.ident) < 0) { out.idents.push(w.ident); }
      if (w && w.order_made) { out.orderMade = true; }
    });
    return out;
  }

  /** 보내기 전 한 번 묻기 — {ok, ack}. 경고가 있으면 확인 창, 없으면 fallback 글(글 또는 plan → 글). opts 는 값 또는 Promise.
      미리 보기를 못 받았으면(R1 실패 · 보낼 것 모름) 지금 확인 글(oldText, 없으면 글 fallback)로 묻는다 — 최종 도면이 되는 길을 확인 없이
      두지 않는다. 미리 보기가 거절될 계획(plan.error)이면 묻지 않는다 — 서버가 400 으로 답하고 아무것도 안 바뀐다. */
  function gate(orderId, opts, fallback, host, oldText) {
    return Promise.resolve(opts).then(function (o) { return o ? preview(orderId, o) : null; }).then(function (plan) {
      if (!plan) {
        var text = oldText || (typeof fallback === 'string' ? fallback : HOTFIX_TEXT);
        return { ok: window.confirm(text), ack: noAck() };
      }
      if (plan.error) { return { ok: true, ack: noAck() }; }
      var warnings = plan.warnings || [];
      if (warnings.length) {
        return ask(warnings, HOTFIX_TEXT, host).then(function (ok) { return { ok: ok, ack: ok ? ackOf(warnings) : noAck() }; });
      }
      return { ok: window.confirm(typeof fallback === 'function' ? fallback(plan) : fallback), ack: noAck() };
    });
  }

  function postJson(url, body) {
    return window.fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      return resp.json().then(
        function (data) { return data || {}; },
        function () { return { success: false, message: '응답을 해석할 수 없습니다. (' + resp.status + ')' }; }
      );
    });
  }

  /** 보내기 — 서버가 409(물어보지 않은 작업된 도면 · 시공 대기)로 물으면 그 글로 창을 띄우고, [그래도 보내기]면 그 도면 열쇠를
      앞 목록에 더해 다시 보낸다(그사이 또 바뀌면 또 묻는다 — 세 번까지). 취소하면 {success:false, cancelled:true}. */
  function post(url, body, host, round) {
    return postJson(url, body).then(function (data) {
      var code = data && data.data && data.data.code;
      if (data.success === true || !ASK_CODES[code] || (round || 0) >= 3) { return data; }
      var warnings = (data.data && data.data.warnings) || [{ text: data.error || data.message }];
      return ask(warnings, HOTFIX_TEXT, host).then(function (ok) {
        if (!ok) { return { success: false, cancelled: true, message: '' }; }
        var more = ackOf(warnings);
        var idents = (body.ack_worked || []).concat(more.idents.filter(function (i) { return (body.ack_worked || []).indexOf(i) < 0; }));
        return post(url, Object.assign({}, body, { ack_worked: idents, ack_order_made: !!body.ack_order_made || more.orderMade }),
          host, (round || 0) + 1);
      });
    });
  }

  window.FomsFixSend = {
    NOTE_MSG: NOTE_MSG,
    PICK_MSG: PICK_MSG,
    HOTFIX_TEXT: HOTFIX_TEXT,
    preview: preview,
    setChanged: setChanged,
    ask: ask,
    ackOf: ackOf,
    noAck: noAck,
    gate: gate,
    post: post
  };
})();
