/**
 * 긴급 호출 공용 창(#fomsUrgentCallModal) — SPEC docs/specs/2026-10-01-urgent-call-global_SPEC.md §4.
 *
 * 여는 곳:
 *  - 맨 위 줄 ⚡ [data-foms-urgent-open] (PC layout_nav · 모바일 셸 머리줄). 지금 보던 주문이 있으면 미리 고른다:
 *    페이지가 실은 [data-urgent-context-order-id] 또는 대시보드에서 펼쳐 둔 주문 상세.
 *  - 주문·도면 화면 버튼 [data-foms-urgent-call][data-order-id] (모바일 주문 상세·도면 모바일).
 *  - window.fomsUrgentCall.open({ orderId, orderLabel, team, message }) — 도면 작업실 PC 창·전달 취소 경고가 부른다.
 *
 * 창: 주문 한 줄(골라짐 `#번호 고객명 ×` / 없으면 `+ 주문 추가 (안 해도 돼요)` → 검색) · 팀 버튼 · 사람 이름 ·
 * 사유 · 맨 아래 버튼 하나(받을 사람을 골라 주세요 / 사유를 적어 주세요 / ○○에게 보내기).
 * 주문 검색은 통합 검색 GET /api/foms/search?group=all(이름·전화 일부·주소·주문번호).
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
  var SEARCH_MIN = 2;
  var SEARCH_DEBOUNCE_MS = 200;
  var SEARCH_LIMIT = 8;
  var TEAM_SHORT = {
    CS: 'CS', SALES: '영업', DRAWING: '도면', PRODUCTION: '생산',
    CONSTRUCTION: '시공', SHIPMENT: '출고', ACCOUNTING: '회계'
  };

  var state = {
    order: null,        // { id, label } | null
    team: '',
    targetId: null,
    targetName: '',
    targets: null,      // 서버 목록 캐시(창을 열 때마다 새로 받는다)
    searchSeq: 0,
    searchTimer: null,
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
  function teamKey(u) { return String((u && u.team) || '') || '_ETC'; }
  function teamText(key, label) {
    if (TEAM_SHORT[key]) return TEAM_SHORT[key];
    if (key === '_ETC') return '기타';
    return String(label || key).replace(/팀$/, '');
  }

  // ---- 보내기 버튼 ---------------------------------------------------------
  function syncSend() {
    var btn = q('[data-foms-urgent-send]');
    if (!btn) return;
    var label;
    var ready = false;
    if (state.targetId === null) label = '받을 사람을 골라 주세요';
    else if (!messageText()) label = '사유를 적어 주세요';
    else { label = state.targetName + '에게 보내기'; ready = true; }
    btn.textContent = label;
    btn.disabled = !ready || state.sending;
    btn.classList.toggle('btn-danger', ready);
    btn.classList.toggle('btn-secondary', !ready);
  }

  // ---- 주문 줄 -------------------------------------------------------------
  function renderOrder() {
    var picked = q('[data-foms-urgent-order-picked]');
    var add = q('[data-foms-urgent-order-add]');
    var search = q('[data-foms-urgent-order-search]');
    var label = q('[data-foms-urgent-order-label]');
    if (state.order) {
      if (label) label.textContent = state.order.label || ('#' + state.order.id);
      toggle(picked, true); toggle(add, false); toggle(search, false);
    } else {
      toggle(picked, false); toggle(add, true); toggle(search, false);
    }
  }

  function orderLabel(id, name) {
    var n = String(name || '').replace(/^#\d+\s*·\s*/, '').trim();
    return '#' + id + (n ? ' ' + n : '');
  }

  /** 미리 고른 주문의 고객명을 모르면 통합 검색으로 번호를 찾아 채운다(못 찾으면 #번호 그대로). */
  function resolveOrderLabel(id) {
    fetch('/api/foms/search?group=all&q=' + encodeURIComponent(String(id)), {
      headers: { Accept: 'application/json' }, credentials: 'same-origin'
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var hits = collectHits(data);
        for (var i = 0; i < hits.length; i += 1) {
          if (String(hits[i].order_id) === String(id) && state.order && String(state.order.id) === String(id)) {
            state.order.label = orderLabel(id, hits[i].title);
            renderOrder();
            return;
          }
        }
      })
      .catch(function () { /* #번호 그대로 둔다 */ });
  }

  function collectHits(data) {
    var groups = (data && data.data) || {};
    var all = [].concat(groups.customer || [], groups.order || [], groups.drawing || []);
    var seen = {};
    var out = [];
    all.forEach(function (h) {
      if (!h || h.order_id == null || seen[h.order_id]) return;
      seen[h.order_id] = true;
      out.push(h);
    });
    return out.slice(0, SEARCH_LIMIT);
  }

  function openSearch() {
    toggle(q('[data-foms-urgent-order-add]'), false);
    toggle(q('[data-foms-urgent-order-search]'), true);
    var input = q('[data-foms-urgent-order-q]');
    if (input) { input.value = ''; if (typeof input.focus === 'function') input.focus(); }
    var box = q('[data-foms-urgent-order-results]');
    if (box) box.textContent = '';
  }

  function renderResults(hits, query) {
    var box = q('[data-foms-urgent-order-results]');
    if (!box) return;
    box.textContent = '';
    if (!hits.length) {
      var empty = document.createElement('div');
      empty.className = 'list-group-item small text-muted';
      empty.textContent = '"' + query + '" 에 맞는 주문이 없어요.';
      box.appendChild(empty);
      return;
    }
    hits.forEach(function (h) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'list-group-item list-group-item-action foms-urgent-order__hit';
      b.setAttribute('data-foms-urgent-order-hit', String(Number(h.order_id)));
      b.setAttribute('data-order-label', orderLabel(h.order_id, h.title));
      var top = document.createElement('div');
      top.className = 'foms-urgent-order__hit-top';
      var name = document.createElement('span');
      name.className = 'foms-urgent-order__hit-name';
      name.textContent = String(h.title || '').replace(/^#\d+\s*·\s*/, '') || ('주문 #' + h.order_id);
      top.appendChild(name);
      if (h.stage_label) {
        var stage = document.createElement('span');
        stage.className = 'badge bg-light text-dark border';
        stage.textContent = String(h.stage_label);
        top.appendChild(stage);
      }
      var sub = document.createElement('div');
      sub.className = 'foms-urgent-order__hit-sub';
      sub.textContent = ['#' + h.order_id, h.phone, h.address].filter(Boolean).join(' · ');
      b.appendChild(top);
      b.appendChild(sub);
      box.appendChild(b);
    });
  }

  function runSearch(query) {
    var seq = ++state.searchSeq;
    fetch('/api/foms/search?group=all&q=' + encodeURIComponent(query), {
      headers: { Accept: 'application/json' }, credentials: 'same-origin'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (seq !== state.searchSeq) return; // 늦게 온 옛 결과는 버린다
        if (!data || data.success === false) throw new Error('search error');
        renderResults(collectHits(data), query);
      })
      .catch(function () {
        if (seq !== state.searchSeq) return;
        var box = q('[data-foms-urgent-order-results]');
        if (box) {
          box.textContent = '';
          var err = document.createElement('div');
          err.className = 'list-group-item small text-danger';
          err.textContent = '주문을 찾지 못했어요. 잠시 뒤 다시 적어 주세요.';
          box.appendChild(err);
        }
      });
  }

  function onSearchInput(input) {
    var query = String(input.value || '').trim();
    if (state.searchTimer) clearTimeout(state.searchTimer);
    if (query.length < SEARCH_MIN) {
      state.searchSeq += 1;
      var box = q('[data-foms-urgent-order-results]');
      if (box) box.textContent = '';
      return;
    }
    state.searchTimer = setTimeout(function () { runSearch(query); }, SEARCH_DEBOUNCE_MS);
  }

  // ---- 팀·사람 -------------------------------------------------------------
  function groups() {
    var order = [];
    var byKey = {};
    (state.targets || []).forEach(function (u) {
      if (!u || !Number.isInteger(Number(u.id))) return;
      var key = teamKey(u);
      if (!byKey[key]) { byKey[key] = { key: key, label: teamText(key, u.team_label), members: [] }; order.push(byKey[key]); }
      byKey[key].members.push(u);
    });
    return order;
  }

  function renderTeams() {
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
      var on = state.targetId === Number(u.id);
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

  // ---- 열기·보내기 ---------------------------------------------------------
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
    opts = opts || {};
    var oid = opts.orderId != null && String(opts.orderId) !== '' ? String(opts.orderId) : '';
    state.order = oid && /^\d+$/.test(oid) ? { id: oid, label: opts.orderLabel ? String(opts.orderLabel) : '' } : null;
    state.team = String(opts.team || '');
    state.targetId = null;
    state.targetName = '';
    state.sending = false;
    var msg = q('[data-foms-urgent-message]');
    if (msg) msg.value = String(opts.message || '').slice(0, MAX_MESSAGE);
    showError('');
    renderOrder();
    if (state.order && !state.order.label) {
      state.order.label = '#' + state.order.id;
      renderOrder();
      resolveOrderLabel(state.order.id);
    }
    syncSend();
    api.getOrCreateInstance(r).show();
    loadTargets();
    return true;
  }

  function send() {
    var btn = q('[data-foms-urgent-send]');
    if (!btn || btn.disabled || state.targetId === null || state.sending) return;
    var message = messageText().slice(0, MAX_MESSAGE);
    if (!message) return;
    if (!window.FOMSNotificationWrite || typeof window.FOMSNotificationWrite.fetch !== 'function') {
      showError('긴급 호출을 보낼 수 없어요. 화면을 새로고침해 주세요.');
      return;
    }
    var body = { target_user_id: state.targetId, message: message };
    if (state.order) body.order_id = Number(state.order.id);
    state.sending = true;
    syncSend();
    showError('');
    window.FOMSNotificationWrite.fetch('/erp/api/urgent-call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body)
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || !data.success) throw new Error((data && data.message) || '긴급 호출을 보내지 못했어요.');
        var api = modalApi();
        if (api && root()) api.getOrCreateInstance(root()).hide();
        toast(data.message || (state.targetName + '님에게 보냈어요.'));
      })
      .catch(function (err) {
        showError((err && err.message) || '긴급 호출을 보내지 못했어요.');
      })
      .then(function () {
        state.sending = false;
        syncSend();
      });
  }

  window.fomsUrgentCall = { open: open };

  document.addEventListener('input', function (e) {
    var t = e.target;
    if (!t || !t.closest || !t.closest('#' + MODAL_ID)) return;
    if (t.hasAttribute('data-foms-urgent-message')) { syncSend(); return; }
    if (t.hasAttribute('data-foms-urgent-order-q')) onSearchInput(t);
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

    var person = t.closest('[data-foms-urgent-target]');
    if (person) {
      e.preventDefault();
      var id = Number(person.getAttribute('data-foms-urgent-target'));
      state.targetId = Number.isInteger(id) ? id : null;
      state.targetName = state.targetId === null ? '' : (person.getAttribute('data-target-name') || '');
      renderTeams();
      syncSend();
      return;
    }

    if (t.closest('[data-foms-urgent-order-add]')) { e.preventDefault(); openSearch(); return; }
    if (t.closest('[data-foms-urgent-order-clear]')) { e.preventDefault(); state.order = null; renderOrder(); return; }

    var hit = t.closest('[data-foms-urgent-order-hit]');
    if (hit) {
      e.preventDefault();
      state.order = { id: hit.getAttribute('data-foms-urgent-order-hit'), label: hit.getAttribute('data-order-label') || '' };
      renderOrder();
      return;
    }

    if (t.closest('[data-foms-urgent-send]')) { e.preventDefault(); send(); }
  });
})();
