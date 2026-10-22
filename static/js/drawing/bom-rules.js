/**
 * 도면 마법사 — 자재표 계산 규칙 숫자 받기·고치기.
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.6
 * - GET/POST /api/orders/drawing-wizard/bom-rules (전역 SystemSetting). 고치기는 도면팀·관리자만.
 * - 저장할 때 version(If-Match)을 같이 보낸다. 다른 사람이 먼저 고쳤으면(409) 새 값을 다시 받는다.
 * - 모든 글자는 textContent 로만 넣는다(innerHTML 금지).
 *
 * window.FomsBomRules = { load() → Promise<info|null>, renderEditor(host, info, onSaved, toast) }
 *   info: { rules, defaults, label, version, can_edit }
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
  var detailsOpen = false;

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

  function renderEditor(host, info, onSaved, toast) {
    host.textContent = '';
    var details = el('details', 'dws-calc-rules');
    details.open = detailsOpen;
    details.addEventListener('toggle', function () { detailsOpen = details.open; });
    details.appendChild(el('summary', null, '계산 규칙 숫자 · 판 ' + info.label));
    var grid = el('div', 'dws-calc-rules-grid');
    var inputs = {};
    FIELDS.forEach(function (f) {
      var label = el('label', 'dws-calc-field');
      label.appendChild(el('span', null, f[1]));
      var inp = el('input');
      inp.type = 'text';
      inp.inputMode = 'numeric';
      inp.value = show(info.rules[f[0]]);
      inp.disabled = !info.can_edit;
      if (show(info.rules[f[0]]) !== show(info.defaults[f[0]])) {
        inp.classList.add('dws-calc-changed');
        inp.title = '기본값 ' + show(info.defaults[f[0]]);
      }
      inputs[f[0]] = inp;
      label.appendChild(inp);
      grid.appendChild(label);
    });
    details.appendChild(grid);
    host.appendChild(details);
    if (!info.can_edit) {
      details.appendChild(el('p', 'dws-calc-hint', '규칙 숫자는 도면팀·관리자만 고칠 수 있습니다.'));
      return;
    }

    var row = el('div', 'dws-calc-actions');
    var saveBtn = el('button', 'dws-btn dws-btn-primary', '규칙 저장');
    var resetBtn = el('button', 'dws-btn', '기본값으로');
    saveBtn.type = 'button';
    resetBtn.type = 'button';
    row.appendChild(saveBtn);
    row.appendChild(resetBtn);
    details.appendChild(row);

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
          toast('계산 규칙을 저장했습니다(판 ' + next.label + ').');
          onSaved(next);
          return;
        }
        if (r.data.code === 'REVISION_CONFLICT') {
          toast('다른 사람이 먼저 규칙을 고쳤습니다. 새 값을 불러왔으니 다시 확인해 주세요.');
          load().then(function (fresh) { if (fresh) { onSaved(fresh); } else { busy(false); } });
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
      submit(form.rules);
    });
    resetBtn.addEventListener('click', function () {
      if (window.confirm('계산 규칙 숫자를 모두 기본값으로 되돌릴까요?')) { submit({}); }
    });
  }

  window.FomsBomRules = { load: load, renderEditor: renderEditor };
})();
