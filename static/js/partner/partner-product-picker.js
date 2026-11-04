/**
 * 협력사 제품 고르기 창 — 대분류 › 중분류 › 제품 3단 + 찾기 + "목록에 없는 제품"
 * (설계서 docs/specs/2026-11-04-partner-product-tree_SPEC.md §2.2).
 *
 * - PC 는 세 칸을 나란히, 휴대폰(600px 이하)은 한 칸씩 들어가고 "뒤로".
 * - 찾기는 띄어쓰기를 무시하고 대분류 · 중분류 · 제품 이름을 함께 본다.
 * - "목록에 없는 제품"은 이름을 직접 적는다. 금액은 명세서 때 우리 CS 가 넣는다(커스텀 제품 줄).
 * - 이름만 다룬다(금액 없음). 글은 textContent 로만 넣는다.
 *
 * 쓰기: window.PartnerProductPicker.open({ tree: [{label, groups: [{label, items: [이름]}]}], current, onPick(name),
 *       title?, allowCustom? })  — 우리 CS 옵션 채우기는 allowCustom:false(단가표 제품만, 설계서 2026-11-03 결정 12).
 */
(function () {
  'use strict';

  var CUSTOM_HINT = '사진 꼭 첨부해 주세요! 없으면 안 하셔도 됩니다.';
  var state = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function norm(text) { return String(text || '').toLowerCase().replace(/\s+/g, ''); }

  function narrow() { return window.matchMedia('(max-width: 600px)').matches; }

  function close() {
    if (!state) return;
    var back = state.focusBack;
    state.root.remove();
    document.removeEventListener('keydown', state.onKey);
    document.documentElement.classList.remove('ppp-open');
    state = null;
    if (back && back.focus) back.focus();
  }

  function pick(name) {
    var done = state.onPick;
    close();
    done(name);
  }

  function button(list, text, sub, opts) {
    var b = list.appendChild(el('button', 'ppp-item' + (opts.on ? ' is-on' : '') + (opts.custom ? ' ppp-item--custom' : '')));
    b.type = 'button';
    b.appendChild(el('span', 'ppp-item__name', text));
    if (sub) b.appendChild(el('span', 'ppp-item__sub', sub));
    b.addEventListener('click', opts.click);
    return b;
  }

  /** 지금 이름이 목록 어디에 있는지 — [대분류, 중분류] 번호, 없으면 null. */
  function locate(tree, name) {
    for (var b = 0; b < tree.length; b++) {
      for (var m = 0; m < tree[b].groups.length; m++) {
        if (tree[b].groups[m].items.indexOf(name) >= 0) return [b, m];
      }
    }
    return null;
  }

  function drawCustom(col) {
    var box = col.appendChild(el('div', 'ppp-custom'));
    box.appendChild(el('p', 'ppp-custom__title', '목록에 없는 제품 — 제품 이름을 적어 주세요.'));
    var input = box.appendChild(el('input', 'form-control'));
    input.type = 'text';
    input.maxLength = 100;
    input.placeholder = '예: 드레스룸 ㄷ자';
    input.setAttribute('aria-label', '목록에 없는 제품 이름');
    input.value = state.customText;
    box.appendChild(el('p', 'ppp-custom__hint', CUSTOM_HINT));
    box.appendChild(el('p', 'ppp-custom__note', '금액은 명세서를 낼 때 저희가 넣습니다.'));
    var ok = box.appendChild(el('button', 'btn btn-primary btn-sm', '이 이름으로 넣기'));
    ok.type = 'button';
    ok.disabled = !input.value.trim();
    input.addEventListener('input', function () { state.customText = input.value; ok.disabled = !input.value.trim(); });
    input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' && input.value.trim()) { ev.preventDefault(); pick(input.value.trim()); } });
    ok.addEventListener('click', function () { pick(input.value.trim()); });
    if (!narrow()) input.focus();
  }

  function drawSearch(cols, q) {
    var list = cols[2];
    state.tree.forEach(function (big) {
      big.groups.forEach(function (mid) {
        mid.items.forEach(function (name) {
          if (norm(big.label + mid.label + name).indexOf(q) < 0) return;
          button(list, name, big.label + ' › ' + mid.label, { on: name === state.current, click: function () { pick(name); } });
        });
      });
    });
    if (list.children.length) return;
    if (!state.allowCustom) { list.appendChild(el('p', 'ppp-custom__note ppp-empty', '찾는 제품이 없습니다.')); return; }
    button(list, '찾는 제품이 없으면 "목록에 없는 제품"', null, { custom: true, click: function () {
      state.customText = state.search.value.trim();
      state.search.value = '';
      state.big = -1;
      draw();
    } });
  }

  function draw() {
    var cols = state.cols;
    cols.forEach(function (c) { c.replaceChildren(); });
    var q = norm(state.search.value);
    var level = q ? 'search' : state.big < 0 ? (state.level > 1 ? 'custom' : 1) : state.level;
    state.root.setAttribute('data-level', String(level));
    state.backBtn.hidden = !narrow() || q || state.level < 2;
    if (q) { drawSearch(cols, q); return; }
    state.tree.forEach(function (big, i) {
      button(cols[0], big.label, null, { on: i === state.big, click: function () { state.big = i; state.mid = 0; state.level = 2; draw(); } });
    });
    if (state.allowCustom) button(cols[0], '목록에 없는 제품', '이름 직접 적기', { on: state.big < 0, custom: true, click: function () { state.big = -1; state.level = 2; draw(); } });
    if (state.big < 0) { drawCustom(cols[1]); return; }
    var groups = state.tree[state.big].groups;
    groups.forEach(function (mid, i) {
      button(cols[1], mid.label, mid.items.length + '개', { on: i === state.mid, click: function () { state.mid = i; state.level = 3; draw(); } });
    });
    (groups[state.mid] || { items: [] }).items.forEach(function (name) {
      button(cols[2], name, null, { on: name === state.current, click: function () { pick(name); } });
    });
  }

  function build(title) {
    var root = el('div', 'ppp');
    root.appendChild(el('div', 'ppp__backdrop')).addEventListener('click', close);
    var panel = root.appendChild(el('div', 'ppp__panel'));
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', title);
    var head = panel.appendChild(el('div', 'ppp__head'));
    var back = head.appendChild(el('button', 'ppp__back', '‹ 뒤로'));
    back.type = 'button';
    back.addEventListener('click', function () { state.level = Math.max(1, state.level - 1); if (state.level === 1 && state.big < 0) state.big = 0; draw(); });
    head.appendChild(el('h2', 'ppp__title', title));
    var x = head.appendChild(el('button', 'ppp__close', '×'));
    x.type = 'button';
    x.setAttribute('aria-label', '닫기');
    x.addEventListener('click', close);
    var search = panel.appendChild(el('input', 'form-control ppp__search'));
    search.type = 'search';
    search.placeholder = '제품 찾기 — 예: 아라, 냉장고, 파우더';
    search.setAttribute('aria-label', '제품 찾기');
    search.addEventListener('input', draw);
    var grid = panel.appendChild(el('div', 'ppp__cols'));
    var cols = [1, 2, 3].map(function (n) {
      var c = grid.appendChild(el('div', 'ppp__col'));
      c.setAttribute('data-col', String(n));
      return c;
    });
    return { root: root, cols: cols, search: search, backBtn: back };
  }

  function open(opts) {
    close();
    var tree = (opts && opts.tree) || [];
    var current = String((opts && opts.current) || '').trim();
    var allowCustom = !(opts && opts.allowCustom === false);
    var at = current ? locate(tree, current) : null;
    if (!at && !allowCustom) current = '';
    var parts = build((opts && opts.title) || '제품 선택');
    state = {
      root: parts.root, cols: parts.cols, search: parts.search, backBtn: parts.backBtn,
      tree: tree, current: current, onPick: opts.onPick || function () {},
      big: at ? at[0] : (current ? -1 : 0), mid: at ? at[1] : 0, level: at || current ? (at ? 3 : 2) : 1,
      customText: at ? '' : current, focusBack: document.activeElement, allowCustom: allowCustom
    };
    if (!tree.length && allowCustom) state.big = -1;
    state.onKey = function (ev) { if (ev.key === 'Escape') close(); };
    document.addEventListener('keydown', state.onKey);
    document.documentElement.classList.add('ppp-open');
    document.body.appendChild(state.root);
    draw();
    if (!narrow() && state.big >= 0) state.search.focus();
  }

  window.PartnerProductPicker = { open: open, close: close };
})();
