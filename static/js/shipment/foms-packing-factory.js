/**
 * 출고 패킹 — 공장마다(설계서 2026-11-23 '승인 때 고친 것' 6). 2공장 장이 섞인 주문(공장 꼴)만 이 모듈이 그린다.
 * 카드 · 생산 작업 시트의 [data-foms-pf-trigger] → 같은 바텀시트([data-foms-packing-sheet], packing_sheet.html)를 열고
 * GET /api/erp/shipment/packing/<id> → 공장 묶음(도면 장 줄 · "철물 · 기타" 줄 · 더한 줄) + [N공장 상차 완료](두 번 눌러 확정 —
 * 지금 [상차 완료 → 출발 보고] 꼴). 두 공장이 다 상차 완료되면 서버가 출발 보고를 처리한다.
 * 여는 동안 시트에 .is-pf 를 붙여 옛 목록 칸(foms-packing.js)을 CSS 로 숨기고 이 모듈 칸(.foms-pf)만 보인다. 옛 단추
 * ([data-foms-packing-trigger])를 누르면(캡처 단계) 이 칸을 걷어 옛 목록으로 돌려준다. 옛 모듈 리스너와 겹치지 않게 data-pf-* 만 쓴다.
 * 1공장뿐인 주문은 이 파일이 실리지도 않는다(조각 바이트 그대로).
 */
(function () {
  'use strict';

  if (window.__FOMS_PF_BOUND) return;
  window.__FOMS_PF_BOUND = true;

  var ARM_MS = 3200;
  var st = { id: null, trigger: null, data: null, timer: null };

  // 그리기(DOM)는 foms-packing-factory-view.js — 셸이 두 파일을 어떤 차례로 실어도 되게 쓸 때 찾는다.
  function V() { return window.FomsPackingFactoryView; }
  function sheet() { return document.querySelector('[data-foms-packing-sheet]'); }
  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function root(sh) {
    var body = q(sh, '.offcanvas-body');
    var r = q(body, '.foms-pf');
    if (!r && body) {
      r = document.createElement('div');
      r.className = 'foms-pf';
      body.insertBefore(r, body.firstChild);
    }
    return r;
  }

  function leave() {
    var sh = sheet();
    disarm();
    if (sh) {
      sh.classList.remove('is-pf');
      var r = q(sh, '.foms-pf');
      if (r) r.remove();
    }
    st.id = null; st.trigger = null; st.data = null;
  }

  async function call(method, body) {
    var write = method !== 'GET';
    var doFetch = (write && window.fomsWriteFetch) ? window.fomsWriteFetch : fetch;
    var opts = { method: method, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } };
    if (write) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body || {});
    }
    var res = await doFetch('/api/erp/shipment/packing/' + encodeURIComponent(st.id), opts);
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok || !data.success) throw new Error(data.error || data.message || '요청에 실패했습니다.');
    return data.data || {};
  }

  function showError(message) {
    var box = q(sheet(), '[data-pf-error]');
    if (!box) return;
    box.textContent = message || '';
    box.hidden = !message;
  }

  async function post(body) {
    showError('');
    try {
      st.data = await call('POST', body);
      render();
      return true;
    } catch (err) {
      showError(String((err && err.message) || err));
      return false;
    }
  }

  function badge() {
    var d = st.data;
    var lab = st.trigger && st.trigger.querySelector('[data-pf-label]');
    if (!lab || !d) return;
    if (d.departed_at) {
      lab.textContent = '출발 보고됨';
      lab.classList.add('foms-packing-departed-label');
      return;
    }
    // 생산 작업 시트 단추(data-pf-own)는 칸이 좁아 내 공장 몫만 — "패킹 2공장 2/3"
    var own = st.trigger.hasAttribute('data-pf-own');
    var gs = (d.groups || []).filter(function (g) { return !own || g.can_check; });
    lab.textContent = '패킹 ' + (gs.length > 1 || own
      ? gs.map(function (g) { return g.label + ' ' + g.checked + '/' + g.total; }).join(' · ')
      : d.checked_count + '/' + d.total);
  }

  function render() {
    var sh = sheet();
    var r = root(sh);
    var v = V();
    var d = st.data || {};
    if (!r || !v) return;
    disarm();
    r.textContent = '';
    var status = q(sh, '[data-foms-packing-departed]');
    if (status) {
      status.textContent = d.departed_at ? '출발 보고됨 · ' + v.when(d.departed_at) + (d.departed_by_name ? ' · ' + d.departed_by_name : '') : '';
      status.hidden = !d.departed_at;
    }
    if (d.legacy_count) r.appendChild(v.el('p', 'foms-pf__legacy', '2공장 도면이 생기기 전에 체크한 ' + d.legacy_count + '줄은 공장마다 다시 체크해 주세요.'));
    var err = v.attr(v.attr(v.attr(v.el('div', 'alert alert-danger foms-pf__err'), 'role', 'alert'), 'data-pf-error'), 'data-foms-no-autodismiss');
    err.hidden = true;
    r.appendChild(err);
    (d.groups || []).forEach(function (g) {
      r.appendChild(v.group(g, (d.items || []).filter(function (it) { return it.factory === g.factory; })));
    });
    if ((d.can_check || []).length) r.appendChild(v.addForm(d));
    r.appendChild(v.actions(d));
    badge();
  }

  function disarm() {
    if (st.timer) { clearTimeout(st.timer); st.timer = null; }
    document.querySelectorAll('[data-pf-load][data-armed="true"]').forEach(function (b) {
      b.setAttribute('data-armed', 'false');
      b.classList.remove('foms-packing-depart--armed');
      b.textContent = b.getAttribute('data-pf-text') || b.textContent;
    });
  }

  function arm(btn) {
    if (btn.disabled) return;
    if (btn.getAttribute('data-armed') === 'true') {
      disarm();
      btn.disabled = true;
      btn.textContent = '처리 중...';
      post({ loaded: Number(btn.getAttribute('data-pf-load')) }).then(function (ok) { if (!ok) render(); });
      return;
    }
    disarm();
    btn.setAttribute('data-pf-text', btn.textContent);
    btn.setAttribute('data-armed', 'true');
    btn.classList.add('foms-packing-depart--armed');
    btn.textContent = '한 번 더 탭해 확정';
    st.timer = setTimeout(disarm, ARM_MS);
  }

  async function open(trigger) {
    var sh = sheet();
    if (!sh || !trigger.getAttribute('data-order-id')) return;
    disarm();
    st.id = trigger.getAttribute('data-order-id');
    st.trigger = trigger;
    st.data = null;
    sh.classList.add('is-pf');
    var sub = q(sh, '[data-foms-packing-subtitle]');
    if (sub) sub.textContent = '주문 #' + st.id + ' · 공장마다 패킹 항목을 체크하세요.';
    var status = q(sh, '[data-foms-packing-departed]');
    if (status) { status.textContent = ''; status.hidden = true; }
    var r = root(sh);
    var loading = document.createElement('p');
    loading.className = 'foms-packing-loading';
    loading.setAttribute('role', 'status');
    loading.textContent = '불러오는 중...';
    r.textContent = '';
    r.appendChild(loading);
    if (window.bootstrap && window.bootstrap.Offcanvas) window.bootstrap.Offcanvas.getOrCreateInstance(sh).show();
    var id = st.id;
    try {
      var data = await call('GET');
      if (id !== st.id) return;
      if (data.layout !== 'factory') throw new Error('공장마다 상차하는 주문이 아니에요. 화면을 다시 열어 주세요.');
      st.data = data;
      render();
    } catch (err) {
      if (id !== st.id) return;
      var box = document.createElement('div');
      box.className = 'alert alert-danger foms-pf__err';
      box.setAttribute('role', 'alert');
      box.textContent = String((err && err.message) || err);
      r.textContent = '';
      r.appendChild(box);
    }
  }

  // 캡처 단계 — 옛 단추는 막지 않고 이 모듈 칸만 걷는다(옛 모듈이 문서 bubble 에서 이어서 연다).
  document.addEventListener('click', function (event) {
    var t = event.target;
    if (!t || !t.closest) return;
    if (t.closest('[data-foms-packing-trigger]')) { leave(); return; }
    var trigger = t.closest('[data-foms-pf-trigger]');
    if (trigger) { event.preventDefault(); open(trigger); return; }
    if (!st.id) return;
    var load = t.closest('[data-pf-load]');
    if (load) { event.preventDefault(); arm(load); return; }
    var toggle = t.closest('[data-pf-issue-toggle]');
    if (toggle) {
      event.preventDefault();
      var chips = toggle.parentNode && toggle.parentNode.querySelector('.foms-packing-issue-chips');
      if (chips) {
        chips.hidden = !chips.hidden;
        toggle.setAttribute('aria-expanded', chips.hidden ? 'false' : 'true');
      }
      return;
    }
    var chip = t.closest('[data-pf-issue]');
    if (chip) {
      event.preventDefault();
      var li = chip.closest('[data-pf-key]');
      var active = chip.classList.contains('foms-packing-issue-chip--active');
      if (li) post({ updates: [{ key: li.getAttribute('data-pf-key'), issue: active ? null : chip.getAttribute('data-pf-issue') }] });
    }
  }, true);

  document.addEventListener('change', function (event) {
    var cb = event.target && event.target.closest && event.target.closest('[data-pf-check]');
    if (!cb || !st.id) return;
    var li = cb.closest('[data-pf-key]');
    var on = cb.checked;
    li.classList.toggle('foms-packing-row--checked', on);
    post({ updates: [{ key: li.getAttribute('data-pf-key'), checked: on }] }).then(function (ok) {
      if (!ok) { cb.checked = !on; li.classList.toggle('foms-packing-row--checked', !on); }
    });
  });

  document.addEventListener('submit', function (event) {
    var form = event.target && event.target.closest && event.target.closest('[data-pf-add]');
    if (!form) return;
    event.preventDefault();
    if (form.dataset.submitting === '1') return;  // submit 1회 = POST 1
    var label = form.elements.label.value.trim();
    if (!label) { form.elements.label.focus(); return; }
    var qty = parseInt(form.elements.qty.value, 10);
    var add = { label: label, qty: qty > 0 ? qty : 1 };
    if (form.elements.factory) add.factory = Number(form.elements.factory.value);
    var btn = form.querySelector('[type="submit"]');
    form.dataset.submitting = '1';
    if (btn) btn.disabled = true;
    post({ add: add }).then(function () {
      form.dataset.submitting = '';
      if (btn) btn.disabled = false;
    });
  });
})();
