/**
 * 도면 확정 창 ①제품 ②최종 생산 도면 (DRAWING-PARTIAL-CONFIRM).
 * 설계서 docs/specs/2026-10-12-drawing-confirm-partial-cancel_SPEC.md §4·§5.
 *
 * - 서버 값은 #dwCustomerOkModal 안 [data-ok-scope] 의 JSON(build_ok_scope)뿐이다.
 * - drawing-customer-ok.js 가 창을 열 때 reset(root), 확정 때 collect(root) 를 부른다.
 *   collect 는 {error} 또는 {body: {final_drawing_keys, cancel_items}} 를 돌려준다.
 * - 제품을 [취소]하면 그 제품에만 묶인 도면은 체크가 꺼지고 잠긴다(서버도 같은 규칙으로 거부).
 * - 줄은 textContent 로만 그린다(파일 이름·제품 이름은 사용자 입력).
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_OK_SCOPE_BOUND) return;
  window.__FOMS_DRAWING_OK_SCOPE_BOUND = true;

  var state = null; // {data, status: {uid: 'make'|'cancel'}, reason: {uid}, note: {uid}, final: {key: bool}}

  function safeJsonParse(val, fb) {
    try { var o = JSON.parse(String(val || '')); return o && typeof o === 'object' ? o : fb; } catch (_) { return fb; }
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function box(root) { return root ? root.querySelector('[data-ok-scope]') : null; }

  function onlyCancelled(d) {
    return d.item_uids.length > 0 && d.item_uids.every(function (u) { return state.status[u] === 'cancel'; });
  }

  function summary() {
    var items = state.data.items, drawings = state.data.drawings;
    var make = items.filter(function (it) { return state.status[it.uid] !== 'cancel'; }).length;
    var cancel = items.length - make;
    var finals = drawings.filter(function (d) { return state.final[d.key]; }).length;
    var missReason = items.some(function (it) {
      if (state.status[it.uid] !== 'cancel') return false;
      var r = state.reason[it.uid];
      return !r || (r === 'other' && !String(state.note[it.uid] || '').trim());
    });
    var text = '생산 ' + make + '개 · 최종 생산 도면 ' + finals + '장';
    var error = '';
    if (!make) error = '생산할 제품이 없어요. 전부 취소라면 주문 취소로 처리해 주세요.';
    else if (drawings.length && !finals) error = '공장으로 갈 도면을 하나 이상 골라 주세요.';
    else if (missReason) error = '취소 사유를 골라 주세요. 기타는 메모도 적어 주세요.';
    if (error) text += ' — ' + error;
    else if (cancel) text += ' · 취소 ' + cancel + '개 → 견적·금액은 주문 화면에서 따로 고쳐 주세요.';
    return { text: text, error: error, warn: !!(error || cancel), cancel: cancel };
  }

  function itemRow(it) {
    var cancelled = state.status[it.uid] === 'cancel';
    var row = el('div', 'dw-ok-item' + (cancelled ? ' is-cancel' : ''));
    var head = el('div', 'dw-ok-item__row');
    var text = el('div');
    text.appendChild(el('div', 'dw-ok-item__name', it.name));
    if (it.spec) text.appendChild(el('div', 'dw-ok-item__spec', it.spec));
    var seg = el('div', 'dw-ok-seg');
    seg.setAttribute('role', 'group');
    seg.setAttribute('aria-label', it.name + ' 생산 여부');
    [['make', '생산', 'is-make'], ['cancel', '취소', 'is-cancel']].forEach(function (b) {
      var btn = el('button', b[2], b[1]);
      btn.type = 'button';
      btn.setAttribute('aria-pressed', String((cancelled ? 'cancel' : 'make') === b[0]));
      btn.setAttribute('data-ok-set', b[0]);
      btn.setAttribute('data-uid', it.uid);
      if (b[0] === 'cancel' && !it.cancellable) btn.disabled = true;
      seg.appendChild(btn);
    });
    head.appendChild(text);
    head.appendChild(seg);
    row.appendChild(head);
    if (cancelled) {
      var reasons = el('div', 'dw-ok-reason');
      state.data.reasons.forEach(function (r) {
        var chip = el('button', 'dw-ok-reason__chip', r.label);
        chip.type = 'button';
        chip.setAttribute('aria-pressed', String(state.reason[it.uid] === r.value));
        chip.setAttribute('data-ok-reason', r.value);
        chip.setAttribute('data-uid', it.uid);
        reasons.appendChild(chip);
      });
      if (state.reason[it.uid] === 'other') {
        var note = el('input', 'form-control form-control-sm dw-ok-reason__note');
        note.type = 'text';
        note.maxLength = 200;
        note.id = 'dw-ok-cancel-note-' + it.uid;
        note.placeholder = '취소 이유를 적어 주세요';
        note.setAttribute('aria-label', it.name + ' 취소 메모');
        note.setAttribute('data-ok-note', it.uid);
        note.value = state.note[it.uid] || '';
        reasons.appendChild(note);
      }
      row.appendChild(reasons);
    }
    return row;
  }

  function drawingRow(d) {
    var locked = onlyCancelled(d), on = !!state.final[d.key];
    var label = el('label', 'dw-ok-dw ' + (on ? 'is-final' : 'is-off'));
    var cb = el('input');
    cb.type = 'checkbox';
    cb.id = 'dw-ok-final-' + d.no;
    cb.checked = on;
    cb.disabled = locked;
    cb.setAttribute('data-ok-final', d.key);
    var img = el('img', 'dw-ok-dw__thumb');
    img.src = d.view_url;
    img.alt = d.no + '번 도면';
    img.loading = 'lazy';
    var body = el('span', 'dw-ok-dw__body');
    var chips = el('span', 'dw-ok-dw__chips');
    chips.appendChild(el('span', 'dw-ok-dw__chip', d.no + '번'));
    chips.appendChild(el('span', 'dw-ok-dw__chip ' + (on ? 'is-final' : 'is-off'),
      locked ? '취소 제품 — 자동 제외' : (on ? '최종 생산' : '제외')));
    body.appendChild(chips);
    body.appendChild(el('span', 'dw-ok-dw__name', d.filename));
    body.appendChild(el('span', 'dw-ok-dw__meta', d.item_names.length ? d.item_names.join(' · ') : '제품 연결 없음'));
    label.appendChild(cb);
    label.appendChild(img);
    label.appendChild(body);
    return label;
  }

  function render(root) {
    var b = box(root);
    if (!b || !state) return;
    var items = b.querySelector('[data-ok-items]'), drawings = b.querySelector('[data-ok-drawings]');
    items.replaceChildren.apply(items, state.data.items.map(itemRow));
    drawings.replaceChildren.apply(drawings, state.data.drawings.map(drawingRow));
    var s = summary(), sum = b.querySelector('[data-ok-sum]');
    sum.textContent = s.text;
    sum.classList.toggle('is-warn', s.warn);
    var submit = root.querySelector('[data-ok-submit]');
    if (submit) submit.disabled = !!s.error;
  }

  function reset(root) {
    var b = box(root);
    if (!b) { state = null; return; }
    var data = safeJsonParse(b.getAttribute('data-ok-scope'), null);
    if (!data || !Array.isArray(data.items) || !Array.isArray(data.drawings)) { state = null; return; }
    state = { data: data, status: {}, reason: {}, note: {}, final: {} };
    data.drawings.forEach(function (d) { state.final[d.key] = true; });
    render(root);
  }

  function collect(root) {
    if (!state || !box(root)) return null;
    var s = summary();
    if (s.error) return { error: s.error };
    var cancels = state.data.items.filter(function (it) { return it.uid && state.status[it.uid] === 'cancel'; })
      .map(function (it) {
        return { uid: it.uid, reason: state.reason[it.uid], note: String(state.note[it.uid] || '').trim() || null };
      });
    var finals = state.data.drawings.filter(function (d) { return state.final[d.key]; }).map(function (d) { return d.key; });
    return { body: { final_drawing_keys: finals, cancel_items: cancels } };
  }

  function rootOf(t) { return t.closest ? t.closest('#dwCustomerOkModal') : null; }

  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-ok-set],[data-ok-reason]') : null;
    var root = t ? rootOf(t) : null;
    if (!t || !root || !state) return;
    var uid = t.getAttribute('data-uid');
    if (t.hasAttribute('data-ok-set')) {
      var v = t.getAttribute('data-ok-set');
      state.status[uid] = v;
      state.data.drawings.forEach(function (d) {
        if (d.item_uids.indexOf(uid) !== -1) state.final[d.key] = v === 'make' || !onlyCancelled(d);
      });
    } else {
      state.reason[uid] = t.getAttribute('data-ok-reason');
    }
    render(root);
  });
  document.addEventListener('change', function (e) {
    var t = e.target, root = t ? rootOf(t) : null;
    if (!root || !state || !t.hasAttribute('data-ok-final')) return;
    state.final[t.getAttribute('data-ok-final')] = t.checked;
    render(root);
  });
  document.addEventListener('input', function (e) {
    var t = e.target, root = t ? rootOf(t) : null;
    if (!root || !state || !t.hasAttribute('data-ok-note')) return;
    state.note[t.getAttribute('data-ok-note')] = t.value;
    var s = summary(), b = box(root), sum = b && b.querySelector('[data-ok-sum]');
    if (sum) { sum.textContent = s.text; sum.classList.toggle('is-warn', s.warn); }
    var submit = root.querySelector('[data-ok-submit]');
    if (submit) submit.disabled = !!s.error;
  });

  window.fomsDrawingOkScope = { reset: reset, collect: collect };
})();
