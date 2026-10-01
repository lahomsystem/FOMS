/**
 * 긴급 호출 공용 창의 주문 줄 — SPEC docs/specs/2026-10-01-urgent-call-global_SPEC.md §3.3 · §4.1.
 *
 * 골라진 주문 `#번호 고객명 ×` / 없으면 `+ 주문 추가 (안 해도 돼요)` → 검색 칸("이름, 전화, 주소 등 입력").
 * 검색은 통합 검색 GET /api/foms/search?group=all(이름·전화 일부·주소·주문번호), 2글자부터 200ms 디바운스,
 * customer·order·drawing 버킷을 합쳐 같은 주문은 한 번만, 최대 8줄. 늦게 온 옛 결과는 버린다.
 *
 * urgent-call.js 가 window.fomsUrgentOrder 로 부른다: set(order|null) · get() · openSearch() · onInput(input) ·
 * pick(hitEl) · clear(). 서버 문자열은 textContent 로만 넣는다. 이 파일은 리스너를 걸지 않는다(창 JS 가 위임).
 */
(function () {
  'use strict';
  if (window.fomsUrgentOrder) return;

  var MODAL_ID = 'fomsUrgentCallModal';
  var SEARCH_MIN = 2;
  var SEARCH_DEBOUNCE_MS = 200;
  var SEARCH_LIMIT = 8;
  var current = null; // { id, label } | null
  var searchSeq = 0;
  var searchTimer = null;

  function q(sel) { var r = document.getElementById(MODAL_ID); return r ? r.querySelector(sel) : null; }
  function toggle(el, on) { if (el) el.classList.toggle('d-none', !on); }

  function orderLabel(id, name) {
    var n = String(name || '').replace(/^#\d+\s*·\s*/, '').trim();
    return '#' + id + (n ? ' ' + n : '');
  }

  function render() {
    var picked = q('[data-foms-urgent-order-picked]');
    var add = q('[data-foms-urgent-order-add]');
    var search = q('[data-foms-urgent-order-search]');
    var label = q('[data-foms-urgent-order-label]');
    if (current) {
      if (label) label.textContent = current.label || ('#' + current.id);
      toggle(picked, true); toggle(add, false); toggle(search, false);
    } else {
      toggle(picked, false); toggle(add, true); toggle(search, false);
    }
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

  function searchUrl(query) {
    return '/api/foms/search?group=all&q=' + encodeURIComponent(String(query));
  }

  /** 미리 고른 주문의 고객명을 모르면 통합 검색으로 번호를 찾아 채운다(못 찾으면 #번호 그대로). */
  function resolveLabel(id) {
    fetch(searchUrl(id), { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var hits = collectHits(data);
        for (var i = 0; i < hits.length; i += 1) {
          if (String(hits[i].order_id) === String(id) && current && String(current.id) === String(id)) {
            current.label = orderLabel(id, hits[i].title);
            render();
            return;
          }
        }
      })
      .catch(function () { /* #번호 그대로 둔다 */ });
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

  function showSearchError() {
    var box = q('[data-foms-urgent-order-results]');
    if (!box) return;
    box.textContent = '';
    var err = document.createElement('div');
    err.className = 'list-group-item small text-danger';
    err.textContent = '주문을 찾지 못했어요. 잠시 뒤 다시 적어 주세요.';
    box.appendChild(err);
  }

  function runSearch(query) {
    var seq = ++searchSeq;
    fetch(searchUrl(query), { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (seq !== searchSeq) return; // 늦게 온 옛 결과는 버린다
        if (!data || data.success === false) throw new Error('search error');
        renderResults(collectHits(data), query);
      })
      .catch(function () {
        if (seq === searchSeq) showSearchError();
      });
  }

  window.fomsUrgentOrder = {
    /** @param {{id: (string|number), label: (string|undefined)}|null} order */
    set: function (order) {
      var id = order && order.id != null ? String(order.id) : '';
      current = /^\d+$/.test(id) ? { id: id, label: order.label ? String(order.label) : '' } : null;
      if (current && !current.label) {
        current.label = '#' + current.id;
        render();
        resolveLabel(current.id);
        return;
      }
      render();
    },
    get: function () { return current ? { id: current.id, label: current.label } : null; },
    clear: function () { current = null; render(); },
    openSearch: function () {
      toggle(q('[data-foms-urgent-order-add]'), false);
      toggle(q('[data-foms-urgent-order-search]'), true);
      var input = q('[data-foms-urgent-order-q]');
      if (input) { input.value = ''; if (typeof input.focus === 'function') input.focus(); }
      var box = q('[data-foms-urgent-order-results]');
      if (box) box.textContent = '';
    },
    onInput: function (input) {
      var query = String(input.value || '').trim();
      if (searchTimer) clearTimeout(searchTimer);
      if (query.length < SEARCH_MIN) {
        searchSeq += 1;
        var box = q('[data-foms-urgent-order-results]');
        if (box) box.textContent = '';
        return;
      }
      searchTimer = setTimeout(function () { runSearch(query); }, SEARCH_DEBOUNCE_MS);
    },
    pick: function (hit) {
      current = { id: hit.getAttribute('data-foms-urgent-order-hit'), label: hit.getAttribute('data-order-label') || '' };
      render();
    }
  };
})();
