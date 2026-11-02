/**
 * 회사 지식 물어보기 설정 · 빈 지식 목록(ADMIN — 설계서 10절 · 12절 '비용 · 남용' · 10.3) — [data-brain-ask-admin].
 *
 * brain-ask.js 가 GET /api/brain/chat/state 를 읽으면 'brain:ask-state' 로 받는다(같은 값 — 다시 읽지 않는다). 칸은 서버 설정 표
 * (스위치 · 여는 단계 · 모델 · 생각 깊이 · 최대 출력 · 시간 상한 · 하루 돈 상한 · 사람마다 질문 수 · 빈 지식 묶기 · 부딪침 판정 ·
 * 보조 모델)대로 그리고, 바뀐 칸만 POST /api/brain/chat/settings {changes, version}. 글은 textContent 만.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-brain-ask]');
  var admin = root && root.querySelector('[data-brain-ask-admin]');
  if (!admin || window.__FOMS_BRAIN_ASK_ADMIN_BOUND) return;
  window.__FOMS_BRAIN_ASK_ADMIN_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_ASK_VIEW;
  var display = dom.safeJsonParse(root.getAttribute('data-display'), {});
  var url = root.getAttribute('data-settings-url');
  var form = admin.querySelector('[data-brain-ask-settings]');
  var grid = admin.querySelector('[data-brain-ask-fields]');
  var status = admin.querySelector('[data-brain-ask-settings-status]');
  var gaps = admin.querySelector('[data-brain-ask-gaps]');
  var gapsStatus = admin.querySelector('[data-brain-ask-gaps-status]');
  var current = { version: 0, fields: [] };

  function inputFor(field) {
    var id = 'brain-ask-set-' + field.name;
    if (field.kind === 'bool') {
      return dom.el('input', { cls: 'form-check-input', attrs: { id: id, type: 'checkbox', name: field.name,
                                                                checked: field.value ? 'checked' : null } });
    }
    if (field.kind === 'choice') {
      var select = dom.el('select', { cls: 'form-select form-select-sm', attrs: { id: id, name: field.name } });
      field.choices.forEach(function (c) {
        select.appendChild(dom.el('option', { text: c.label, attrs: { value: String(c.value),
                                                                     selected: c.value === field.value ? 'selected' : null } }));
      });
      return select;
    }
    return dom.el('input', { cls: 'form-control form-control-sm', attrs: {
      id: id, name: field.name, type: field.kind === 'int' ? 'number' : 'text', inputmode: 'decimal',
      min: field.low, max: field.high, value: field.value === null ? '' : String(field.value),
      placeholder: field.kind === 'money' ? '비움 = 부르지 않음' : null } });
  }

  function renderFields(settings) {
    current = settings;
    dom.clear(grid);
    settings.fields.forEach(function (field) {
      var box = dom.el('div', { cls: 'brain-ask-admin__field' });
      box.appendChild(dom.el('label', { text: field.label + (field.unit ? '(' + field.unit + ')' : ''),
                                        attrs: { for: 'brain-ask-set-' + field.name } }));
      box.appendChild(inputFor(field));
      if (field.help) box.appendChild(dom.el('span', { cls: 'brain-ask-admin__help', text: field.help }));
      grid.appendChild(box);
    });
  }

  function renderGaps(data) {
    dom.clear(gaps);
    var rows = view.gapRows(data, display);
    dom.setStatus(gapsStatus, data ? '주(월요일 시작) ' + data.week + ' · 질문 ' + data.questions + '건'
                                   : '아직 목록이 없어요(설정 "빈 지식 묶기"를 켜면 밤 단계가 주 1회 만들어요).');
    rows.forEach(function (row) { gaps.appendChild(dom.el('li', { cls: 'brain-ask-gaps__row', text: row.text })); });
  }

  function formValues() {
    var raw = {};
    current.fields.forEach(function (field) {
      var node = form.querySelector('[name="' + field.name + '"]');
      if (node) raw[field.name] = field.kind === 'bool' ? node.checked : node.value;
    });
    return raw;
  }

  root.addEventListener('brain:ask-state', function (event) {
    if (event.detail.settings) renderFields(event.detail.settings);
    renderGaps(event.detail.gaps || null);
  });

  if (form) {
    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      var picked = view.settingsChanges(current.fields, formValues());
      if (picked.bad.length) {
        dom.setStatus(status, '값이 맞지 않는 칸: ' + picked.bad.join(', '), 'error');
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
      dom.setStatus(status, '저장했어요 — 다음 질문부터 써요.' + (res.data.cap_ready ? '' : ' 하루 돈 상한이 비어 있어 아직 부르지 않아요.'));
    });
  }
})();
