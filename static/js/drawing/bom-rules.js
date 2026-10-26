/**
 * 도면 마법사 — 자재표 계산 규칙 숫자 받기·고치기.
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.6
 * - GET/POST /api/orders/drawing-wizard/bom-rules (전역 SystemSetting). 고치기는 도면팀·관리자만.
 * - 저장할 때 version(If-Match)을 같이 보낸다. 다른 사람이 먼저 고쳤으면(409) 새 값을 다시 받는다.
 * - 저장은 도면팀 전체 계산에 바로 적용되므로 확인을 받는다(보고서 2026-10-25 보통-4).
 *   편집 칸은 계산 칸 밖 규칙 창(bom-rules-dialog.js)에 그린다.
 * - 모든 글자는 textContent 로만 넣는다(innerHTML 금지).
 *
 * window.FomsBomRules = { load() → Promise<info|null>, renderEditor(host, info, onSaved, toast), labelName(label), lastChange(info) }
 *   info: { rules, defaults, label, version, can_edit, changed_at, changed_by }
 *         changed_at·changed_by: 마지막으로 고친 시각(한국 시간 'YYYY-MM-DD HH:MM')·사람 이름(없으면 null).
 *   onSaved(next, conflict): 저장했으면 conflict 없이, 남이 먼저 고쳐 새 값을 다시 받았으면 conflict=true.
 */
(function () {
  'use strict';
  if (window.FomsBomRules) { return; }

  var ENDPOINT = '/api/orders/drawing-wizard/bom-rules';
  var HEIGHTS = 'door_std_heights';
  // [키, 이름] — 키는 foms/services/drawing_wizard_bom_rules.py DEFAULT_RULES 와 같다.
  var FIELDS = [
    ['door_gap_phoenix_pair', '문 폭 · 피닉스바 쌍문에서 빼기'],
    ['door_gap_phoenix_single', '문 폭 · 피닉스바 외짝에서 빼기'],
    ['door_gap_other_pair', '문 폭 · 그 밖 손잡이 쌍문에서 빼기'],
    ['door_gap_other_single', '문 폭 · 그 밖 손잡이 외짝에서 빼기'],
    [HEIGHTS, '표준 문 높이(쉼표로 나눔)'],
    ['door_ceiling_margin', '표준 문 · 천장에서 띄울 높이'],
    ['nomold_cut', '무몰딩 문 · 천장에서 빼기'],
    ['nomold_step', '무몰딩 문 · 내림 단위'],
    ['rod_cut', '옷봉 · 모듈에서 빼기'],
    ['maida_w_cut', '마이다 폭 · 모듈에서 빼기'],
    ['maida_h_cut', '마이다 높이 · 나눈 칸에서 빼기'],
    ['drawer_zone', '서랍 칸 높이 기본값'],
    ['sr_small_gap', 'SR 위 · 작은 틈 기준'],
    ['sr_small_value', 'SR 위 · 작은 틈일 때 값'],
    ['sr_minus', 'SR 위 · 틈에서 빼기'],
    ['sr_step', 'SR 위 · 올림 단위'],
    ['sheet_len', 'SR·EP 판 길이'],
    ['ep_plus_hinged', 'EP · 여닫이 깊이에 더하기']
  ];

  /** 판 이름 → 화면 글: 'd1' → '기본 규칙', 's2' → '규칙 2판'(개발 말 '판 s2' 를 보이지 않는다). */
  function labelName(label) {
    var m = /^s(\d+)$/.exec(String(label || ''));
    if (m) { return '규칙 ' + m[1] + '판'; }
    return /^d\d+$/.test(String(label || '')) ? '기본 규칙' : String(label || '');
  }
  /** 저장 확인 글 — '도면팀 전체 계산에 바로 적용됩니다(규칙 2판 → 3판). 저장할까요?' */
  function confirmText(info, lead) {
    var from = labelName(info.label), to = (Number(info.version) || 0) + 1 + '판';
    return lead + '도면팀 전체 계산에 바로 적용됩니다(' + from + ' → ' + (/^규칙 /.test(from) ? to : '규칙 ' + to) + '). 저장할까요?';
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }

  function request(opts) {
    opts.credentials = 'same-origin';
    return fetch(ENDPOINT, opts).then(function (resp) {
      return resp.json().then(
        function (data) { return { status: resp.status, data: data || {} }; },
        function () { return { status: resp.status, data: {} }; }
      );
    });
  }

  /** 현재 규칙. 못 받으면 null(계산 칸이 안내 글을 보여 준다). */
  function load() {
    return request({ headers: { 'Accept': 'application/json' } }).then(function (r) {
      return (r.status === 200 && r.data.success && r.data.data) ? r.data.data : null;
    }).catch(function () { return null; });
  }

  function show(v) { return Array.isArray(v) ? v.join(', ') : String(v); }
  function tidy(text) { return String(text).split(/[,\s]+/).filter(Boolean).join(', '); }

  /** 입력 칸 → 규칙 dict. 정수가 아닌 칸이 있으면 bad 에 그 칸 이름. */
  function readForm(inputs) {
    var rules = {}, bad = null;
    FIELDS.forEach(function (f) {
      var raw = inputs[f[0]].value.trim();
      var nums = raw.split(/[,\s]+/).filter(Boolean).map(Number);
      var ok = nums.length > 0 && nums.every(function (n) { return isFinite(n) && Math.floor(n) === n; });
      if (f[0] !== HEIGHTS && nums.length !== 1) { ok = false; }
      if (!ok && !bad) { bad = f[1]; }
      rules[f[0]] = f[0] === HEIGHTS ? nums : nums[0];
    });
    return { rules: rules, bad: bad };
  }

  /** 규칙 칸 하나 — 이름(낱말 단위 줄바꿈) · 값 · mm. 기본값과 다르면 진한 주황 테두리 + '기본 34'. */
  function field(grid, f, info) {
    var label = el('label', 'dws-calc-field dws-calc-rule' + (f[0] === HEIGHTS ? ' dws-calc-rule-wide' : ''));
    label.appendChild(el('span', 'dws-calc-rule-name', f[1]));
    var line = label.appendChild(el('span', 'dws-calc-rule-input'));
    var inp = line.appendChild(el('input'));
    inp.type = 'text';
    inp.inputMode = 'numeric';
    inp.value = show(info.rules[f[0]]);
    inp.disabled = !info.can_edit;
    line.appendChild(el('span', 'dws-calc-unit', 'mm'));
    var def = show((info.defaults || {})[f[0]]);
    var base = label.appendChild(el('span', 'dws-calc-rule-base', '기본 ' + def));
    function mark() {
      var changed = tidy(inp.value) !== def;
      label.classList.toggle('dws-calc-changed', changed);
      base.hidden = !changed;
    }
    inp.addEventListener('input', mark);
    mark();
    grid.appendChild(label);
    return inp;
  }

  /** '마지막 고침: 홍길동 · 2026-10-25 14:03' — 서버가 감사 기록에서 읽어 준다(아직 아무도 안 고쳤으면 ''). */
  function lastChange(info) {
    if (!info || !info.changed_at) { return ''; }
    return '마지막 고침: ' + (info.changed_by ? info.changed_by + ' · ' : '') + info.changed_at;
  }

  /** 규칙 편집 칸을 host 에 그리고 단추 줄을 돌려준다(규칙 창이 [닫기]를 덧붙인다). */
  function renderEditor(host, info, onSaved, toast) {
    host.textContent = '';
    var last = lastChange(info);   // 도면팀 전체에 바로 적용되는 숫자라 누가 언제 바꿨는지 보인다(보고서 보통-4)
    if (last) { host.appendChild(el('p', 'dws-calc-rules-meta', last)); }
    host.appendChild(el('p', 'dws-calc-hint dws-calc-rules-intro', '자재표 계산 칸이 쓰는 숫자입니다(단위 mm). 기본값과 다른 칸은 주황 테두리와 기본값을 함께 보여 줍니다.'));
    var grid = el('div', 'dws-calc-rules-grid');
    var inputs = {};
    FIELDS.forEach(function (f) { inputs[f[0]] = field(grid, f, info); });
    host.appendChild(grid);
    var row = el('div', 'dws-dialog-actions dws-calc-rules-actions');
    if (!info.can_edit) {
      host.appendChild(el('p', 'dws-calc-hint', '규칙 숫자는 도면팀·관리자만 고칠 수 있습니다.'));
      host.appendChild(row);
      return row;
    }
    var resetBtn = el('button', 'dws-btn', '기본값으로');
    var saveBtn = el('button', 'dws-btn dws-btn-primary', '규칙 저장');
    saveBtn.type = 'button';
    resetBtn.type = 'button';
    row.appendChild(resetBtn);
    row.appendChild(saveBtn);
    host.appendChild(row);

    function busy(on) { saveBtn.disabled = on; resetBtn.disabled = on; }
    function submit(rules) {
      busy(true);
      request({
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ rules: rules, settings_version: info.version })
      }).then(function (r) {
        if (r.status === 200 && r.data.success && r.data.data) {
          var next = r.data.data;
          next.can_edit = info.can_edit;
          toast('계산 규칙을 저장했습니다(' + labelName(next.label) + ').');
          onSaved(next, false);
          return;
        }
        if (r.data.code === 'REVISION_CONFLICT') {
          toast('다른 사람이 먼저 규칙을 고쳤습니다. 새 값을 불러왔으니 다시 확인해 주세요.');
          load().then(function (fresh) { if (fresh) { onSaved(fresh, true); } else { busy(false); } });
          return;
        }
        toast(r.data.message || r.data.error || '계산 규칙을 저장하지 못했습니다.');
        busy(false);
      }).catch(function () {
        toast('계산 규칙을 저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.');
        busy(false);
      });
    }
    saveBtn.addEventListener('click', function () {
      var form = readForm(inputs);
      if (form.bad) { toast('\'' + form.bad + '\' 칸에 정수를 넣어 주세요.'); return; }
      if (window.confirm(confirmText(info, ''))) { submit(form.rules); }
    });
    resetBtn.addEventListener('click', function () {
      if (window.confirm(confirmText(info, '계산 규칙 숫자를 모두 기본값으로 되돌립니다. '))) { submit({}); }
    });
    return row;
  }

  window.FomsBomRules = { load: load, renderEditor: renderEditor, labelName: labelName, lastChange: lastChange };
})();
