/**
 * 긴급 호출 공용 창(#fomsUrgentCallModal) — SPEC docs/specs/2026-10-01-urgent-call-global_SPEC.md §4.
 *
 * ⚡ [data-foms-urgent-open]·주문 [data-foms-urgent-call]·window.fomsUrgentCall.open이 공용 창을 연다.
 * 여러 팀의 사람을 선택·해제하고 한 요청으로 보낸다(SPEC 2026-10-16).
 * 주문 줄(골라짐·검색)은 urgent-call-order.js(window.fomsUrgentOrder)가 맡는다 — 이 파일보다 먼저 싣는다.
 * 보내기는 POST /erp/api/urgent-call(window.FOMSNotificationWrite — same-origin 쓰기 헤더). 주문은 없어도 된다.
 *
 * 사람 이름 등 서버 문자열은 textContent 로만 넣는다. 리스너는 document 위임 + 한 번 가드(perf guard G4).
 */
(function () {
  'use strict';
  if (window.__FOMS_URGENT_CALL_BOUND) return;
  window.__FOMS_URGENT_CALL_BOUND = true;

  var MODAL_ID = 'fomsUrgentCallModal';
  var MAX_MESSAGE = 500;
  var TEAM_SHORT = {
    CS: 'CS', SALES: '영업', DRAWING: '도면', PRODUCTION: '생산',
    CONSTRUCTION: '시공', SHIPMENT: '출고', ACCOUNTING: '회계'
  };

  var state = {
    team: '',
    selected: [],
    targets: null,      // 서버 목록 캐시(창을 열 때마다 새로 받는다)
    sending: false
  };

  function root() { return document.getElementById(MODAL_ID); }
  function q(sel) { var r = root(); return r ? r.querySelector(sel) : null; }
  function modalApi() { return window.bootstrap && window.bootstrap.Modal ? window.bootstrap.Modal : null; }
  function toggle(el, on) { if (el) el.classList.toggle('d-none', !on); }
  function toast(message) {
    if (typeof window.fomsShowToast === 'function') window.fomsShowToast(message);
    else window.alert(message);
  }
  function showError(text) {
    var el = q('[data-foms-urgent-error]');
    if (!el) return;
    el.textContent = text || '';
    toggle(el, !!text);
  }
  function messageText() {
    var el = q('[data-foms-urgent-message]');
    return el ? String(el.value || '').trim() : '';
  }
  // 팀 표에 없는 코드(ADMIN 등)와 팀 없음은 모두 '기타' 하나로 묶는다 — 서버 team_label 도 둘 다 '기타'다.
  function teamKey(u) {
    var code = String((u && (u.selection_team || u.team)) || '');
    return TEAM_SHORT[code] ? code : '_ETC';
  }
  function teamText(key) { return TEAM_SHORT[key] || '기타'; }

  function syncSend() {
    var btn = q('[data-foms-urgent-send]');
    if (!btn) return;
    var label;
    var ready = false;
    if (!state.selected.length) label = '받을 사람을 골라 주세요';
    else if (!messageText()) label = '사유를 적어 주세요';
    else { label = targetLabel() + '에게 보내기'; ready = true; }
    if (state.sending) label = '보내는 중...';
    btn.textContent = label;
    btn.disabled = !ready || state.sending;
    btn.classList.toggle('btn-danger', ready);
    btn.classList.toggle('btn-secondary', !ready);
  }

  function orderApi() { return window.fomsUrgentOrder || null; }

  function targetLabel() {
    return state.selected[0].name + (state.selected.length > 1 ? ' 외 ' + (state.selected.length - 1) + '명' : '');
  }
  function renderSelected() {
    var box = q('[data-foms-urgent-selected]');
    if (!box) return;
    box.textContent = '';
    state.selected.forEach(function (u) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-sm foms-urgent-pick is-selected';
      b.setAttribute('data-foms-urgent-remove', String(u.id));
      b.setAttribute('aria-label', u.name + ' 선택 해제');
      b.textContent = u.name + ' ×';
      b.disabled = state.sending;
      box.appendChild(b);
    });
    var count = q('[data-foms-urgent-count]');
    if (count) count.textContent = state.selected.length ? '선택 ' + state.selected.length + '명' : '여러 명을 선택할 수 있어요';
  }

  function groups() {
    var order = [];
    var byKey = {};
    (state.targets || []).forEach(function (u) {
      if (!u || !Number.isInteger(Number(u.id))) return;
      var key = teamKey(u);
      if (!byKey[key]) { byKey[key] = { key: key, label: teamText(key), members: [] }; order.push(byKey[key]); }
      byKey[key].members.push(u);
    });
    var etc = byKey._ETC;
    if (etc) { order.splice(order.indexOf(etc), 1); order.push(etc); }
    return order;
  }

  function renderTeams() {
    renderSelected();
    var box = q('[data-foms-urgent-teams]');
    var people = q('[data-foms-urgent-people]');
    if (!box || !people) return;
    box.textContent = '';
    people.textContent = '';
    var gs = groups();
    if (!gs.length) {
      people.textContent = state.targets ? '호출할 담당자가 없어요.' : '';
      return;
    }
    if (!gs.some(function (g) { return g.key === state.team; })) state.team = gs[0].key;
    gs.forEach(function (g) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-sm ' + (g.key === state.team ? 'btn-dark' : 'btn-outline-secondary');
      b.setAttribute('data-foms-urgent-team', g.key);
      b.setAttribute('aria-pressed', g.key === state.team ? 'true' : 'false');
      b.textContent = g.label;
      box.appendChild(b);
    });
    var current = gs.filter(function (g) { return g.key === state.team; })[0];
    current.members.forEach(function (u) {
      var on = state.selected.some(function (s) { return s.id === Number(u.id); });
      var p = document.createElement('button');
      p.type = 'button';
      p.className = 'btn btn-sm foms-urgent-pick' + (on ? ' is-selected' : '');
      p.setAttribute('data-foms-urgent-target', String(Number(u.id)));
      p.setAttribute('data-target-name', String(u.name || '').trim());
      p.setAttribute('aria-pressed', on ? 'true' : 'false');
      p.textContent = String(u.name || '').trim();
      people.appendChild(p);
    });
  }

  function loadTargets() {
    var people = q('[data-foms-urgent-people]');
    state.targets = null;
    if (people) people.textContent = '불러오는 중...';
    fetch('/erp/api/urgent-targets', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
      .then(function (r) {
        if (!r.ok || !r.data || !r.data.success) throw new Error((r.data && r.data.message) || 'targets error');
        state.targets = Array.isArray(r.data.targets) ? r.data.targets : [];
        renderTeams();
      })
      .catch(function () {
        if (people) people.textContent = '호출할 사람 목록을 불러오지 못했어요.';
      });
  }

  /** 지금 화면의 주문 — 페이지가 실은 표지, 아니면 대시보드에서 펼쳐 둔 주문 상세. */
  function contextOrder() {
    var el = document.querySelector('[data-urgent-context-order-id]');
    if (el) {
      var id = el.getAttribute('data-urgent-context-order-id');
      if (id) return { id: id, label: el.getAttribute('data-urgent-context-order-label') || '' };
    }
    var open = document.querySelector('.collapse.show[id^="order-detail-collapse-"]');
    if (open) return { id: open.id.replace('order-detail-collapse-', ''), label: '' };
    return null;
  }

  function open(opts) {
    var r = root();
    var api = modalApi();
    if (!r || !api) {
      toast('긴급 호출 창을 열 수 없어요. 화면을 새로고침해 주세요.');
      return false;
    }
    if (state.sending) return false;
    opts = opts || {};
    state.team = String(opts.team || '');
    state.selected = [];
    renderSelected();
    var msg = q('[data-foms-urgent-message]');
    if (msg) msg.value = String(opts.message || '').slice(0, MAX_MESSAGE);
    showError('');
    var oa = orderApi();
    if (oa) oa.set(opts.orderId != null && String(opts.orderId) !== '' ? { id: opts.orderId, label: opts.orderLabel } : null);
    syncSend();
    api.getOrCreateInstance(r).show();
    loadTargets();
    return true;
  }

  function send() {
    var btn = q('[data-foms-urgent-send]');
    if (!btn || btn.disabled || !state.selected.length || state.sending) return;
    var message = messageText().slice(0, MAX_MESSAGE);
    if (!message) return;
    if (!window.FOMSNotificationWrite || typeof window.FOMSNotificationWrite.fetch !== 'function') {
      showError('긴급 호출을 보낼 수 없어요. 화면을 새로고침해 주세요.');
      return;
    }
    var body = { target_user_ids: state.selected.map(function (u) { return u.id; }), message: message };
    var sentLabel = targetLabel();
    var order = orderApi() ? orderApi().get() : null;
    if (order) body.order_id = Number(order.id);
    state.sending = true;
    renderSelected();
    syncSend();
    showError('');
    window.FOMSNotificationWrite.fetch('/erp/api/urgent-call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body)
    })
      .then(function (res) { return res.json().then(function (d) {
        if (!res.ok) throw new Error((d && (d.message || d.error)) || '긴급 호출을 보내지 못했어요.');
        return d;
      }); })
      .then(function (data) {
        if (!data || !data.success) throw new Error((data && data.message) || '긴급 호출을 보내지 못했어요.');
        var api = modalApi();
        if (api && root()) api.getOrCreateInstance(root()).hide();
        toast(data.message || (sentLabel + '에게 보냈어요.'));
      })
      .catch(function (err) {
        showError((err && err.message) || '긴급 호출을 보내지 못했어요.');
      })
      .then(function () {
        state.sending = false;
        renderSelected();
        syncSend();
      });
  }

  window.fomsUrgentCall = { open: open };

  document.addEventListener('input', function (e) {
    var t = e.target;
    if (!t || !t.closest || !t.closest('#' + MODAL_ID)) return;
    if (t.hasAttribute('data-foms-urgent-message')) { syncSend(); return; }
    if (t.hasAttribute('data-foms-urgent-order-q') && orderApi()) orderApi().onInput(t);
  });

  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return;

    var headerOpener = t.closest('[data-foms-urgent-open]');
    if (headerOpener) {
      e.preventDefault();
      var ctx = contextOrder();
      open(ctx ? { orderId: ctx.id, orderLabel: ctx.label } : {});
      return;
    }
    var orderOpener = t.closest('[data-foms-urgent-call]');
    if (orderOpener) {
      e.preventDefault();
      open({
        orderId: orderOpener.getAttribute('data-order-id'),
        orderLabel: orderOpener.getAttribute('data-urgent-order-label'),
        team: orderOpener.getAttribute('data-urgent-team'),
        message: orderOpener.getAttribute('data-urgent-message')
      });
      return;
    }

    var r = root();
    if (!r || !r.contains(t)) return;

    var teamBtn = t.closest('[data-foms-urgent-team]');
    if (teamBtn) { e.preventDefault(); state.team = teamBtn.getAttribute('data-foms-urgent-team'); renderTeams(); return; }

    var remove = t.closest('[data-foms-urgent-remove]');
    var person = remove || t.closest('[data-foms-urgent-target]');
    if (person) {
      e.preventDefault();
      if (state.sending) return;
      var id = Number(person.getAttribute(remove ? 'data-foms-urgent-remove' : 'data-foms-urgent-target'));
      var index = state.selected.findIndex(function (u) { return u.id === id; });
      if (index >= 0) state.selected.splice(index, 1);
      else if (!remove && Number.isInteger(id) && id > 0) state.selected.push({ id: id, name: person.getAttribute('data-target-name') || '' });
      renderTeams();
      syncSend();
      return;
    }

    var oa = orderApi();
    if (oa && t.closest('[data-foms-urgent-order-add]')) { e.preventDefault(); oa.openSearch(); return; }
    if (oa && t.closest('[data-foms-urgent-order-clear]')) { e.preventDefault(); oa.clear(); return; }
    var hit = t.closest('[data-foms-urgent-order-hit]');
    if (oa && hit) { e.preventDefault(); oa.pick(hit); return; }

    if (t.closest('[data-foms-urgent-send]')) { e.preventDefault(); send(); }
  });
})();
