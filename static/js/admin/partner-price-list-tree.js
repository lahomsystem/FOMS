/**
 * 협력사 단가표 — 제품 분류로 보기(설계서 docs/specs/2026-11-04-partner-product-tree_SPEC.md §2.1).
 *
 * partner-price-list.js 가 표를 다시 그릴 때마다 render(sheet, ctx) 를 부른다. 고르는 이름마다 대분류 › 중분류로 묶어
 * 협력사 고르기 창과 같은 차례로 보인다(분류는 표에서 제품 이름을 눌러 오른쪽 칸에서 고친다). 대분류 ▲ ▼ 는 판의
 * tree_order(대분류 차례)를 바꾼다(편집할 수 있는 판만). 분류가 없는 이름은 맨 뒤 "기타"에 표 제목으로 묶인다.
 * 협력사 목록에서 끈 줄(pickable=false)은 빠진다.
 */
(function () {
  'use strict';

  var KINDS = {};
  ((window.FomsPriceListPanel && window.FomsPriceListPanel.kinds) || []).forEach(function (k) { KINDS[k[0]] = k[1]; });

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  /** {대분류: {중분류: [{name, item}]}} — 판의 tree_order 차례(없으면 처음 나온 차례), "기타"는 맨 뒤. */
  function group(sheet, ctx) {
    var tree = {};
    var order = [];
    sheet.categories.forEach(function (cat) {
      cat.rows.forEach(function (row) {
        row.items.forEach(function (item) {
          if (item.role !== 'product' || item.pickable === false) return;
          var names = (item.pick_names || []).length ? item.pick_names : [item.partner_label || ctx.describe(item).name];
          names.forEach(function (name) {
            var own = (item.tree_by_name || {})[name];
            var path = own && own[0] ? own : (Array.isArray(item.tree) && item.tree[0] ? item.tree : ['기타', cat.title || '제품']);
            var big = path[0];
            var mid = path[1] || big;
            if (!tree[big]) { tree[big] = {}; order.push(big); }
            if (!tree[big][mid]) tree[big][mid] = [];
            tree[big][mid].push({ name: name, item: item });
          });
        });
      });
    });
    var rank = sheet.tree_order || [];
    function at(big) { var i = rank.indexOf(big); return big === '기타' ? 1e6 : (i < 0 ? 1e3 + order.indexOf(big) : i); }
    order.sort(function (a, b) { return at(a) - at(b); });
    return { tree: tree, order: order };
  }

  function move(sheet, ctx, order, i, step) {
    var list = order.filter(function (b) { return b !== '기타'; });
    var j = i + step;
    if (j < 0 || j >= list.length) return;
    var t = list[i]; list[i] = list[j]; list[j] = t;
    sheet.tree_order = list;
    ctx.changed();
  }

  function render(sheet, ctx) {
    var box = document.querySelector('[data-pl-tree]');
    if (!box) return;
    box.replaceChildren();
    box.hidden = !sheet;
    if (!sheet) return;
    var g = group(sheet, ctx);
    var head = box.appendChild(el('div', 'foms-pl-tree__head'));
    head.appendChild(el('h2', null, '제품 분류'));
    head.appendChild(el('span', 'small text-muted', '협력사 고르기 창에 이 차례로 보입니다. 분류는 표에서 제품 이름을 눌러 오른쪽에서 고칩니다.'));
    var canMove = ctx.editable();
    g.order.forEach(function (big, i) {
      var mids = g.tree[big];
      var count = Object.keys(mids).reduce(function (n, m) { return n + mids[m].length; }, 0);
      var card = box.appendChild(el('details', 'foms-pl-tree__big' + (big === '기타' ? ' foms-pl-tree__big--etc' : '')));
      card.open = true;
      var sum = card.appendChild(el('summary', null, big));
      sum.appendChild(el('span', 'foms-pl-tree__count', count + '개'));
      if (canMove && big !== '기타') {
        [['▲', -1, '위로'], ['▼', 1, '아래로']].forEach(function (m) {
          var b = sum.appendChild(el('button', 'foms-pl-tree__move', m[0]));
          b.type = 'button';
          b.setAttribute('aria-label', big + ' ' + m[2]);
          b.disabled = (m[1] < 0 && i === 0) || (m[1] > 0 && g.order[i + 1] == null) || (m[1] > 0 && g.order[i + 1] === '기타');
          b.addEventListener('click', function (ev) { ev.preventDefault(); move(sheet, ctx, g.order, i, m[1]); });
        });
      }
      Object.keys(mids).forEach(function (mid) {
        card.appendChild(el('h3', 'foms-pl-tree__mid', mid));
        mids[mid].forEach(function (r) {
          var line = card.appendChild(el('div', 'foms-pl-tree__row'));
          line.appendChild(el('span', 'foms-pl-tree__name', r.name));
          line.appendChild(el('span', 'foms-pl-kb foms-pl-kb--' + r.item.kind, KINDS[r.item.kind] || r.item.kind));
          line.appendChild(el('span', 'foms-pl-tree__price', ctx.describe(r.item).priceText));
        });
      });
    });
  }

  window.FomsPriceListTree = { render: render };
})();
