/**
 * 프리랜서 수수료 설정 화면(설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §2.3).
 * GET data-api-url → 목록 · 추가할 계정 · 요율 이력을 그린다. 저장 = POST {user_id, match_name, start_month, tax_type,
 * active, rate?, version}, 요율 = POST <url>/<user_id>/rates {effective_month, lahom_bp, haud_bp, personal_bp, version}.
 * 화면에는 % 로 보이고 서버에는 bp(100bp = 1%)로 보낸다. 고치기 칸은 서버가 관리자에게만 내보낸다(data-can-edit).
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-sf-root]');
  if (!root) return;
  var url = root.getAttribute('data-api-url');
  var canEdit = root.getAttribute('data-can-edit') === '1';
  var TAX_LABELS = { WITHHOLD_3_3: '3.3% 떼고 지급', VAT_10: '부가세 10% 더해 지급', NONE: '세금 없음' };
  var state = { version: 0, freelancers: [], candidates: [], taxTypes: [] };
  var selectedId = null;
  var editingId = null;

  function $(sel) { return root.querySelector(sel); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function status(text, isError) {
    var box = $('[data-sf-status]');
    box.textContent = text || '';
    box.classList.toggle('is-error', !!isError);
  }

  /** bp(정수) → 화면 % 글자. 소수 둘째 자리까지, 끝 0 은 지운다. */
  function bpToPercent(bp) {
    if (bp == null) return '';
    return String(Number((bp / 100).toFixed(2)));
  }

  /** 화면 % 글자 → bp. 소수 둘째 자리까지만 받는다. 잘못되면 null. */
  function percentToBp(text) {
    var value = String(text || '').trim();
    if (!/^\d{1,3}(\.\d{1,2})?$/.test(value)) return null;
    var bp = Math.round(parseFloat(value) * 100);
    return bp >= 0 && bp <= 10000 ? bp : null;
  }

  function readRate(form, prefix) {
    var out = {};
    var names = [['lahom', '라홈'], ['haud', '하우드'], ['personal', '개인영업']];
    for (var i = 0; i < names.length; i++) {
      var bp = percentToBp(form.elements[names[i][0]].value);
      if (bp === null) return { error: names[i][1] + ' 요율을 0 에서 100 사이 숫자로 적어 주세요(소수 둘째 자리까지).' };
      out[names[i][0] + '_bp'] = bp;
    }
    if (prefix) out.effective_month = prefix;
    return { rate: out };
  }

  async function call(path, body) {
    var res;
    try {
      res = await fetch(path, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined
      });
    } catch (_) {
      return { ok: false, error: '서버에 닿지 못했어요. 인터넷 연결을 확인해 주세요.' };
    }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!data || !data.success) {
      var msg = (data && data.error) || '처리하지 못했어요. 잠시 뒤 다시 해 주세요.';
      if (res.status === 409) msg = msg + ' (새로 고침하면 지금 값이 보여요)';
      return { ok: false, error: msg, conflict: res.status === 409 };
    }
    return { ok: true, data: data.data || {} };
  }

  function find(uid) {
    for (var i = 0; i < state.freelancers.length; i++) if (state.freelancers[i].user_id === uid) return state.freelancers[i];
    return null;
  }

  function drawList() {
    var body = $('[data-sf-list]');
    body.replaceChildren();
    $('[data-sf-empty]').hidden = state.freelancers.length > 0;
    state.freelancers.forEach(function (f) {
      var tr = body.appendChild(el('tr'));
      if (f.user_id === selectedId) tr.classList.add('is-selected');
      var nameCell = tr.appendChild(el('td'));
      var pick = nameCell.appendChild(el('button', 'btn btn-link btn-sm p-0', f.match_name));
      pick.type = 'button';
      pick.title = '요율 이력 보기';
      pick.addEventListener('click', function () { select(f.user_id); });
      tr.appendChild(el('td', '', (f.name || '') + (f.username ? ' (' + f.username + ')' : '') + (f.user_active ? '' : ' · 꺼진 계정')));
      tr.appendChild(el('td', '', f.start_month));
      var cur = f.current_rate;
      ['lahom_bp', 'haud_bp', 'personal_bp'].forEach(function (k) {
        tr.appendChild(el('td', 'foms-sf__num', cur ? bpToPercent(cur[k]) + '%' : '없음'));
      });
      tr.appendChild(el('td', '', TAX_LABELS[f.tax_type] || f.tax_type));
      tr.appendChild(el('td', '', f.active ? '켜짐' : '꺼짐'));
      if (canEdit) {
        var tools = tr.appendChild(el('td'));
        var edit = tools.appendChild(el('button', 'btn btn-outline-secondary btn-sm', '고치기'));
        edit.type = 'button';
        edit.addEventListener('click', function () { startEdit(f.user_id); });
      }
    });
  }

  function drawHistory() {
    var box = $('[data-sf-detail]');
    var f = selectedId != null ? find(selectedId) : null;
    box.hidden = !f;
    if (!f) return;
    $('[data-sf-detail-name]').textContent = f.match_name;
    var body = $('[data-sf-history]');
    body.replaceChildren();
    if (!f.rates.length) {
      var empty = body.appendChild(el('tr'));
      var td = empty.appendChild(el('td', 'text-muted', '아직 요율이 없어요.'));
      td.colSpan = 5;
    }
    f.rates.slice().reverse().forEach(function (r) {
      var tr = body.appendChild(el('tr'));
      tr.appendChild(el('td', '', r.effective_month + '부터'));
      ['lahom_bp', 'haud_bp', 'personal_bp'].forEach(function (k) { tr.appendChild(el('td', 'foms-sf__num', bpToPercent(r[k]) + '%')); });
      tr.appendChild(el('td', '', (r.at || '').slice(0, 16).replace('T', ' ')));
    });
  }

  function fillSelect(select, items) {
    select.replaceChildren();
    items.forEach(function (it) {
      var opt = select.appendChild(el('option', '', it[1]));
      opt.value = it[0];
    });
  }

  function resetForm() {
    var form = $('[data-sf-form]');
    if (!form) return;
    editingId = null;
    form.reset();
    $('[data-sf-form-title]').textContent = '프리랜서 추가';
    $('[data-sf-pick-wrap]').hidden = false;
    $('[data-sf-first-rate]').hidden = false;
    $('[data-sf-cancel]').hidden = true;
    var opts = state.candidates.map(function (c) { return [c.user_id, c.name + ' (' + c.username + ')']; });
    fillSelect($('[data-sf-pick]'), [['', opts.length ? '계정을 골라 주세요' : '추가할 수 있는 영업팀 직원이 없어요']].concat(opts));
    fillSelect($('[data-sf-tax]'), [['', '골라 주세요']].concat(state.taxTypes.map(function (t) { return [t, TAX_LABELS[t] || t]; })));
  }

  function startEdit(uid) {
    var f = find(uid);
    var form = $('[data-sf-form]');
    if (!f || !form) return;
    resetForm();
    editingId = uid;
    $('[data-sf-form-title]').textContent = f.match_name + ' 고치기';
    $('[data-sf-pick-wrap]').hidden = true;
    $('[data-sf-first-rate]').hidden = true;
    $('[data-sf-cancel]').hidden = false;
    form.elements.match_name.value = f.match_name;
    form.elements.start_month.value = f.start_month;
    form.elements.tax_type.value = f.tax_type;
    form.elements.active.checked = !!f.active;
    select(uid);
    form.scrollIntoView({ block: 'nearest' });
  }

  function select(uid) {
    selectedId = uid;
    drawList();
    drawHistory();
  }

  function draw(data) {
    state.version = data.version;
    state.freelancers = data.freelancers || [];
    state.candidates = data.candidates || [];
    state.taxTypes = data.tax_types || [];
    if (selectedId != null && !find(selectedId)) selectedId = null;
    drawList();
    drawHistory();
  }

  /** 다시 읽기. ``fresh`` 면 추가 폼도 비운다(처음 열 때) — 충돌 뒤 다시 읽기는 적던 칸을 그대로 둔다. */
  async function reload(fresh) {
    var res = await call(url);
    if (!res.ok) { status(res.error, true); return; }
    draw(res.data);
    if (fresh && canEdit) resetForm();
  }

  async function submitProfile(ev) {
    ev.preventDefault();
    var form = ev.target;
    var uid = editingId != null ? editingId : parseInt(form.elements.user_id.value, 10);
    if (!uid) { status('계정을 골라 주세요.', true); return; }
    var body = {
      user_id: uid, match_name: form.elements.match_name.value, start_month: form.elements.start_month.value,
      tax_type: form.elements.tax_type.value, active: form.elements.active.checked, version: state.version
    };
    if (editingId == null) {
      var first = readRate(form, form.elements.start_month.value);
      if (first.error) { status(first.error, true); return; }
      body.rate = first.rate;
    }
    status('저장하는 중…');
    var res = await call(url, body);
    if (!res.ok) { status(res.error, true); if (res.conflict) reload(); return; }
    selectedId = uid;
    draw(res.data);
    resetForm();
    status('저장했어요.');
  }

  async function submitRate(ev) {
    ev.preventDefault();
    var form = ev.target;
    if (selectedId == null) return;
    var month = form.elements.effective_month.value;
    if (!month) { status('적용 달을 골라 주세요.', true); return; }
    var read = readRate(form, month);
    if (read.error) { status(read.error, true); return; }
    status('저장하는 중…');
    var res = await call(url + '/' + selectedId + '/rates', Object.assign(read.rate, { version: state.version }));
    if (!res.ok) { status(res.error, true); if (res.conflict) reload(); return; }
    form.reset();
    draw(res.data);
    status('요율을 바꿨어요. ' + month + '부터 적용돼요.');
  }

  if (canEdit) {
    var profileForm = $('[data-sf-form]');
    var rateForm = $('[data-sf-rate-form]');
    if (profileForm) profileForm.addEventListener('submit', submitProfile);
    if (rateForm) rateForm.addEventListener('submit', submitRate);
    var cancel = $('[data-sf-cancel]');
    if (cancel) cancel.addEventListener('click', function () { resetForm(); });
  }

  reload(true);
})();
