/* 협력사 단가표 — 오른쪽 칸: 고른 줄의 계산 정보(설계서 2026-11-03-partner-statement §3.1 · §5.1).
 *
 * partner-price-list.js 가 줄 이름을 누르면 FomsPriceListPanel.show(item, ctx) 를 부른다. 고친 값은 item 객체에
 * 바로 넣고 ctx.changed() 로 알린다(저장은 본 화면의 "저장 (새 판)"). 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var KINDS = [
    ['ja', '자 단가', '가로 ÷ 300으로 자 수를 구해 단가를 곱합니다. 자 수는 소수 한 자리까지 반올림합니다(12.35 → 12.4).'],
    ['meter', 'm 단가', '가로 ÷ 1,000으로 m 수를 구해 단가를 곱합니다(주방처럼 m로 파는 것). 옵션이면 고른 m 수 × 단가.'],
    ['band', '크기 구간', '가로(또는 깊이)가 어느 구간에 드는지 보고 같은 묶음에서 한 줄을 고릅니다. 가장 큰 구간보다 크면 "넘치면 이 줄"을 더합니다.'],
    ['over', '넘친 만큼', '가장 큰 구간을 넘은 길이를 정한 mm로 나눠 올림한 수 × 단가. 예: 250mm 넘침, 100mm마다 → 3'],
    ['count', '고른 수', '협력사가 고른 수 × 단가. 예: 서랍 · 거울 도어 · 피닉스바 손잡이 · 조명'],
    ['fixed', '정해진 값', '고르기만 하면 값이 정해지는 제품. 예: 서랍장 3단']
  ];
  var UNITS = ['자', 'm', '개', '짝', '통', '단', '식'];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function field(label, control, help) {
    var wrap = el('label', 'foms-pl-f');
    wrap.appendChild(el('span', 'foms-pl-f__label', label));
    wrap.appendChild(control);
    if (help) wrap.appendChild(el('span', 'foms-pl-f__help', help));
    return wrap;
  }

  function select(options, value) {
    var node = el('select', 'form-select form-select-sm');
    options.forEach(function (opt) {
      var o = el('option', null, opt[1]);
      o.value = opt[0];
      if (String(opt[0]) === String(value)) o.selected = true;
      node.appendChild(o);
    });
    return node;
  }

  function input(value, type) {
    var node = el('input', 'form-control form-control-sm');
    node.type = type || 'text';
    node.value = value == null ? '' : String(value);
    return node;
  }

  function lines(values) {
    var node = el('textarea', 'form-control form-control-sm');
    node.rows = 3;
    node.value = (values || []).join('\n');
    return node;
  }

  function splitLines(text) {
    var out = [];
    String(text || '').split(/\n|,/).forEach(function (part) {
      var name = part.trim();
      if (name && out.indexOf(name) < 0) out.push(name);
    });
    return out;
  }

  function kindHelp(kind) {
    var row = KINDS.filter(function (k) { return k[0] === kind; })[0];
    return row ? row[2] : '';
  }

  function condFields(item, ctx, box) {
    var cond = item.cond || (item.cond = {});
    if (item.kind === 'band') {
      var dim = select([['width', '가로'], ['depth', '깊이']], cond.dim || 'width');
      dim.addEventListener('change', function () { cond.dim = dim.value; ctx.changed(); });
      box.appendChild(field('기준 치수', dim));
      ['min', 'max'].forEach(function (bound) {
        var node = input(cond[bound], 'number');
        node.min = '0';
        node.addEventListener('input', function () {
          if (node.value === '') delete cond[bound]; else cond[bound] = parseInt(node.value, 10);
          ctx.changed();
        });
        box.appendChild(field(bound === 'min' ? '최소 mm (비우면 0)' : '최대 mm (비우면 제한 없음)', node));
      });
      var group = input(cond.group);
      group.addEventListener('input', function () { cond.group = group.value.trim(); ctx.changed(); });
      box.appendChild(field('구간 묶음 이름', group, '이름이 같은 줄끼리 한 묶음입니다. 치수에 맞는 줄 하나를 고릅니다.'));
      var overs = [['', '(없음)']].concat(ctx.overItems().map(function (o) { return [o.key, o.name]; }));
      var over = select(overs, cond.over_key || '');
      over.addEventListener('change', function () {
        if (over.value) cond.over_key = over.value; else delete cond.over_key;
        ctx.changed();
      });
      box.appendChild(field('넘치면 이 줄', over, '이 줄이 묶음에서 가장 큰 구간일 때만 씁니다. 넘은 길이만큼 더할 줄을 고르세요.'));
    } else if (item.kind === 'over') {
      var per = input(cond.per || 100, 'number');
      per.min = '1';
      per.addEventListener('input', function () { cond.per = parseInt(per.value, 10) || 100; ctx.changed(); });
      box.appendChild(field('몇 mm마다', per));
    }
  }

  /** 제품 분류 — 대분류 · 중분류(설계서 2026-11-04-partner-product-tree §2.1). 협력사 고르기 창이 이 3단으로 묶는다.
      이름이 여럿인 줄(같은 단가)은 이름마다 다르게 둘 수 있다(tree_by_name — 비우면 줄 분류를 따른다). */
  function treePair(path, onSave, holder) {
    var big = input((path || [])[0] || '');
    var mid = input((path || [])[1] || '');
    big.placeholder = (holder || [])[0] || '예: 붙박이장';
    mid.placeholder = (holder || [])[1] || '예: 여닫이';
    function save() { var b = big.value.trim(); onSave(b ? [b, mid.value.trim() || b] : null); }
    big.addEventListener('input', save);
    mid.addEventListener('input', save);
    return [big, mid];
  }

  function treeFields(item, ctx, body) {
    var pair = treePair(item.tree, function (path) { if (path) item.tree = path; else delete item.tree; ctx.changed(); });
    body.appendChild(field('분류 — 대분류', pair[0], '비우면 협력사 고르기 창의 "기타"에 보입니다.'));
    body.appendChild(field('분류 — 중분류', pair[1], '비우면 대분류 이름을 그대로 씁니다.'));
    var names = item.pick_names || [];
    if (names.length < 2) return;
    names.forEach(function (name) {
      var own = (item.tree_by_name || {})[name];
      var p = treePair(own, function (path) {
        var map = Object.assign({}, item.tree_by_name || {});
        if (path) map[name] = path; else delete map[name];
        if (Object.keys(map).length) item.tree_by_name = map; else delete item.tree_by_name;
        ctx.changed();
      }, item.tree);
      var row = el('div', 'foms-pl-tree-pair');
      row.appendChild(p[0]);
      row.appendChild(p[1]);
      body.appendChild(field('"' + name + '"만 다른 분류', row, '비우면 위 분류를 따릅니다.'));
    });
  }

  function render(item, ctx) {
    var body = document.querySelector('[data-pl-panel-body]');
    var empty = document.querySelector('[data-pl-panel-empty]');
    if (!body) return;
    body.replaceChildren();
    body.hidden = false;
    if (empty) empty.hidden = true;
    var info = ctx.describe(item);
    body.appendChild(el('h2', 'h6 mb-0', info.name || '(이름 없음)'));
    body.appendChild(el('div', 'text-muted small mb-2', info.priceText));
    var editable = ctx.editable();

    var role = select([['product', '제품 — 제품명 목록에 보임'], ['option', '옵션 — 옵션 목록에 보임']], item.role);
    role.addEventListener('change', function () { item.role = role.value; ctx.changed(); });
    body.appendChild(field('보이는 곳', role));

    var unit = select(UNITS.map(function (u) { return [u, u]; }), item.unit);
    unit.addEventListener('change', function () { item.unit = unit.value; ctx.changed(); });
    body.appendChild(field('단위', unit));

    var kind = select(KINDS.map(function (k) { return [k[0], k[1]]; }), item.kind);
    var help = el('p', 'foms-pl-f__help', kindHelp(item.kind));
    var condBox = el('div', 'foms-pl-cond');
    kind.addEventListener('change', function () {
      item.kind = kind.value;
      item.cond = {};
      help.textContent = kindHelp(item.kind);
      condBox.replaceChildren();
      condFields(item, ctx, condBox);
      ctx.changed();
    });
    body.appendChild(field('계산 방법', kind));
    body.appendChild(help);
    condFields(item, ctx, condBox);
    body.appendChild(condBox);
    if (info.included) body.appendChild(el('p', 'foms-pl-f__note', '금액이 없어 기본 포함입니다. 명세서에 따로 줄을 만들지 않고 제품 줄 비고에 이름만 적습니다.'));

    var label = input(item.partner_label);
    label.placeholder = info.name || '';
    label.addEventListener('input', function () { item.partner_label = label.value.trim(); ctx.changed(); });
    body.appendChild(field('협력사에게 보일 이름', label, '비우면 단가표 이름을 씁니다.'));

    var picks = lines(item.pick_names);
    picks.addEventListener('input', function () { item.pick_names = splitLines(picks.value); ctx.changed(); });
    body.appendChild(field('협력사가 고르는 이름 (한 줄에 하나)', picks, '예: 몰딩 여닫이, 무몰딩 여닫이 — 모두 이 줄 단가로 계산합니다.'));

    if (item.role === 'product') treeFields(item, ctx, body);

    if (item.role === 'option') {
      var only = lines(item.for_products);
      only.addEventListener('input', function () { item.for_products = splitLines(only.value); ctx.changed(); });
      body.appendChild(field('이 제품일 때만 보임 (한 줄에 하나)', only, '비우면 모든 제품. 예: 침대 붙박이장.'));
    }

    var vis = el('input', 'form-check-input');
    vis.type = 'checkbox';
    vis.checked = item.pickable !== false;
    vis.addEventListener('change', function () { item.pickable = vis.checked; ctx.changed(); });
    var visWrap = el('label', 'form-check foms-pl-f');
    visWrap.appendChild(vis);
    visWrap.appendChild(el('span', 'form-check-label', '협력사 목록에 보임 (끄면 명세서에서 우리 CS만 넣을 수 있음)'));
    body.appendChild(visWrap);

    body.querySelectorAll('select, input, textarea').forEach(function (node) { node.disabled = !editable; });
    if (!editable) body.appendChild(el('p', 'foms-pl-f__note', '옛 판은 볼 수만 있습니다. 지금 쓰는 판에서 고쳐 주세요.'));
  }

  function clear() {
    var body = document.querySelector('[data-pl-panel-body]');
    var empty = document.querySelector('[data-pl-panel-empty]');
    if (body) { body.replaceChildren(); body.hidden = true; }
    if (empty) empty.hidden = false;
  }

  window.FomsPriceListPanel = { show: render, clear: clear, kinds: KINDS };
})();
