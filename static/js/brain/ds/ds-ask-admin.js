/**
 * 새 물어보기 화면 관리 칸(ADMIN 만 — 설계서 10절 · 12절 '비용 · 남용' · 10.3, 옛 brain-ask-admin.js 와 같은 일을 새 꼴로) —
 * [data-ds-ask-admin] 설정 · [data-ds-ask-gaps-box] 빈 지식 · 왼쪽 길잡이 '관리'(빈 지식 수 · 틀림 신고 수).
 *
 * ds-ask.js 가 GET /api/brain/chat/state 를 읽으면 'ds:ask-state' 로 받는다(같은 값 — 다시 읽지 않는다). 칸은 서버 설정 표
 * (스위치 · 여는 단계 · 모델 · 생각 깊이 · 최대 출력 · 시간 상한 · 하루 돈 상한 · 사람마다 질문 수 · 빈 지식 묶기 · 부딪침 판정 ·
 * 보조 모델)대로 그리고, 바뀐 칸만 POST /api/brain/chat/settings {changes, version}. 값 꼴 맞추기 · 바뀐 칸 고르기 · 빈 지식 줄은
 * 옛 화면과 한 벌인 brain-ask-view.js. 글은 textContent 만 · 전역 듣개는 한 번만(window.__FOMS_DS_ASK_ADMIN_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_ASK_VIEW;
  var dv = window.FOMS_DS_ASK_VIEW;
  var root = document.querySelector('[data-ds-ask]');
  var admin = root && root.querySelector('[data-ds-ask-admin]');
  if (!admin || !dom || !view || !dv || window.__FOMS_DS_ASK_ADMIN_BOUND) return;
  window.__FOMS_DS_ASK_ADMIN_BOUND = true;

  var el = dom.el;
  var display = dom.safeJsonParse(root.getAttribute('data-display'), {});
  var url = root.getAttribute('data-settings-url');
  var form = admin.querySelector('[data-ds-ask-settings]');
  var grid = admin.querySelector('[data-ds-ask-fields]');
  var status = admin.querySelector('[data-ds-ask-settings-status]');
  var gapsBox = root.querySelector('[data-ds-ask-gaps-box]');
  var gaps = gapsBox && gapsBox.querySelector('[data-ds-ask-gaps]');
  var gapsStatus = gapsBox && gapsBox.querySelector('[data-ds-ask-gaps-status]');
  var side = document.querySelector('[data-ds-ask-side]');
  var current = { version: 0, fields: [] };

  function inputFor(field) {
    var id = 'ds-ask-set-' + field.name;
    if (field.kind === 'bool') {
      return el('input', { attrs: { id: id, type: 'checkbox', name: field.name, checked: field.value ? 'checked' : null } });
    }
    if (field.kind === 'choice') {
      var select = el('select', { cls: 'f-select', attrs: { id: id, name: field.name } });
      field.choices.forEach(function (c) {
        select.appendChild(el('option', { text: c.label, attrs: { value: String(c.value),
                                                                 selected: c.value === field.value ? 'selected' : null } }));
      });
      return select;
    }
    return el('input', { cls: 'f-input', attrs: {
      id: id, name: field.name, type: field.kind === 'int' ? 'number' : 'text', inputmode: 'decimal',
      min: field.low, max: field.high, value: field.value === null ? '' : String(field.value),
      placeholder: field.kind === 'money' ? '비우면 부르지 않아요' : null } });
  }

  function fieldNode(field) {
    var label = field.label + (field.unit ? '(' + field.unit + ')' : '');
    var box;
    if (field.kind === 'bool') {
      box = el('div', { cls: 'f-field', children: [el('label', { cls: 'f-check', children: [
        inputFor(field), document.createTextNode(label)] })] });
    } else {
      box = el('div', { cls: 'f-field', children: [
        el('label', { cls: 'f-label', text: label, attrs: { for: 'ds-ask-set-' + field.name } }), inputFor(field)] });
    }
    if (field.help) box.appendChild(el('span', { cls: 'f-help', text: field.help }));
    return box;
  }

  function renderFields(settings) {
    current = settings;
    dom.clear(grid);
    settings.fields.forEach(function (field) { grid.appendChild(fieldNode(field)); });
  }

  function setCount(sel, n) {
    var node = side && side.querySelector(sel);
    if (!node) return;
    node.textContent = String(n);
    node.hidden = !n;
  }

  function renderGaps(data) {
    if (!gaps) return;
    dom.clear(gaps);
    dom.setStatus(gapsStatus, data ? data.week + ' 주 · 질문 ' + data.questions + '건'
                                   : '아직 없어요. "빈 지식 묶기"를 켜면 주 1회 만들어요.');
    view.gapRows(data, display).forEach(function (row) {
      gaps.appendChild(el('li', { cls: 'f-row-nw', children: [
        el('span', { cls: 'f-i i-issue f-i-warning', attrs: { 'aria-hidden': 'true' } }),
        el('span', { cls: 'f-small f-grow', text: row.text })] }));
    });
    var n = dv.gapCounts(data);
    setCount('[data-ds-ask-gap-count]', n.gaps);
    setCount('[data-ds-ask-wrong-count]', n.wrong);
  }

  /** 칸 이름(영어) → 화면 이름. */
  function labelOf(name) {
    var hit = current.fields.filter(function (f) { return f.name === name; })[0];
    return hit ? hit.label : name;
  }

  function formValues() {
    var raw = {};
    current.fields.forEach(function (field) {
      var node = form.querySelector('[name="' + field.name + '"]');
      if (node) raw[field.name] = field.kind === 'bool' ? node.checked : node.value;
    });
    return raw;
  }

  root.addEventListener('ds:ask-state', function (event) {
    if (event.detail.settings) renderFields(event.detail.settings);
    renderGaps(event.detail.gaps || null);
  });

  if (side) {
    side.addEventListener('click', function (event) {
      var link = event.target.closest('[data-ds-ask-admin-link]');
      if (link && link.getAttribute('data-ds-ask-admin-link') === 'settings') admin.open = true;
    });
  }
  if (window.location && window.location.hash === '#ds-ask-settings') admin.open = true;

  if (form) {
    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      var picked = view.settingsChanges(current.fields, formValues());
      if (picked.bad.length) {
        dom.setStatus(status, '값이 맞지 않는 칸: ' + picked.bad.map(labelOf).join(', '), 'error');
        return;
      }
      if (!Object.keys(picked.changes).length) {
        dom.setStatus(status, '바뀐 칸이 없어요.');
        return;
      }
      dom.setStatus(status, '저장하는 중…');
      var res = await dom.postJson(url, { changes: picked.changes, version: current.version });
      if (!res.ok) {
        dom.setStatus(status, res.error, 'error');
        return;
      }
      renderFields(res.data.settings);
      dom.setStatus(status, '저장했어요 — 다음 질문부터 써요.' + (res.data.cap_ready ? '' : ' 하루 돈 상한이 비어 있어 아직 답하지 않아요.'));
    });
  }
})();
