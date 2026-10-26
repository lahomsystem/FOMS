/**
 * 도면 마법사 V2 — 왼쪽 칸: [제품 N | 칸 N | 실측 사진 N] · 제품 종류 · 칸 카드 · 미분류 상자.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 (화면 시안 K2 왼쪽 316px)
 * - 제품 · 실측 사진 칸은 V1 목록 DOM(#dws-product-list · #dws-pending · #dws-photos)을 옮겨 담는다 — 눌러 넣기 · 끌어 넣기 그대로.
 * - 칸 카드의 작은 그림을 누르면 종이에서 그 그림을 고른다(V1 미니 막대 · 숫자키로 종류를 고친다).
 *   다른 카드로 끌어 놓으면 그 칸 종류로 바꾼다(사람이 고친 종류 = 다음 AI 학습 자료). 큰 그림 칸은 넷 중에서 고른다.
 * - 특이 사항 · 강조 문구 카드는 v2-notes.js 가 그린다.
 *
 * window.FomsV2Left = { init(api), render(view) }
 */
(function () {
  'use strict';
  if (window.FomsV2Left) { return; }

  var api = null, els = {}, tab = 'slots', DRAG = 'application/x-dws-v2-id';
  var FRONT_ISO = ['정면·내부', '정면·도어', '입체·내부', '입체·도어'];
  var ALL = ['정면·내부', '정면·도어', '입체·내부', '입체·도어', '평면·상판', '서랍 단면', '부품 상세', '사진', '그림 아님', '미분류'];

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  function setTab(t) {
    tab = t;
    Array.prototype.forEach.call(document.querySelectorAll('[data-v2-tab]'), function (b) {
      var on = b.getAttribute('data-v2-tab') === t;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.classList.toggle('dws-v2-tab-on', on);
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-v2-pane]'), function (p) { p.hidden = p.getAttribute('data-v2-pane') !== t; });
  }

  function init(a) {
    api = a;
    els.cards = $('dws-v2-cards');
    els.unsorted = $('dws-v2-unsorted');
    els.kind = $('dws-v2-kind');
    els.kindAuto = $('dws-v2-kind-auto');
    var prod = document.querySelector('[data-v2-pane="products"]'), photos = document.querySelector('[data-v2-pane="photos"]');
    ['dws-product-list', 'dws-pending'].forEach(function (id) { var n = $(id); if (n && prod) { prod.appendChild(n); } });
    var ph = $('dws-photos');
    if (ph && photos) { photos.appendChild(ph); }
    Array.prototype.forEach.call(document.querySelectorAll('[data-v2-tab]'), function (b) {
      b.addEventListener('click', function () { setTab(b.getAttribute('data-v2-tab')); });
    });
    if (els.kind) {
      els.kind.addEventListener('change', function () {
        var core = api.core, sh = core.sheet(), plan = api.plan();
        if (!sh || !plan || !core.canSave()) { return; }
        core.recordUndo();
        sh.form.v2_kind = els.kind.value === plan.kindAuto ? '' : els.kind.value;
        core.markDirty();
        if (api.mode() === 'auto' && plan.laid) { api.arrange('kind', {}); } else { api.refresh(); }
      });
    }
    setTab('slots');
  }

  function thumb(o, view) {
    var core = api.core, b = el('button', 'dws-v2-thumb' + (view.plan.g.fixed[o.id] ? ' dws-v2-thumb-fixed' : ''));
    b.type = 'button';
    b.title = (view.plan.g.labels[o.id] || '미분류') + ' — 눌러서 종이에서 고르기 · 다른 칸으로 끌어서 종류 바꾸기';
    var img = el('img', 'dws-v2-thumb-img');
    img.alt = view.plan.g.labels[o.id] || '그림';
    img.loading = 'lazy';
    img.src = core.viewUrl(o.key);
    b.appendChild(img);
    b.addEventListener('click', function () { api.selectIds([o.id]); });
    if (core.canSave()) {
      b.draggable = true;
      b.addEventListener('dragstart', function (e) {
        try { e.dataTransfer.setData(DRAG, o.id); e.dataTransfer.effectAllowed = 'move'; } catch (err) { /* 끌기 못 함 = 누르기만 */ }
      });
    }
    return b;
  }

  function chooser(card, id, labels) {
    var old = card.querySelector('.dws-v2-choose');
    if (old) { old.parentNode.removeChild(old); }
    var box = el('div', 'dws-v2-choose');
    box.appendChild(el('span', 'dws-v2-choose-text', '어느 종류인가요?'));
    labels.forEach(function (l) {
      var b = el('button', 'dws-v2-choose-btn', l);
      b.type = 'button';
      b.addEventListener('click', function () { box.parentNode.removeChild(box); api.relabel(id, l); });
      box.appendChild(b);
    });
    card.appendChild(box);
  }

  /** 카드에 끌어 놓은 그림 → 그 칸 종류. 큰 그림 · 입체 칸은 고르게 한다. */
  function dropTo(card, slot, id, view) {
    var cur = view.plan.g.labels[id];
    if (slot === 'photo') { api.relabel(id, '사진'); return; }
    if (slot === 'plan') { api.relabel(id, '평면·상판'); return; }
    if (slot === 'unsorted') { api.relabel(id, '미분류'); return; }
    if (slot === 'detail') { api.relabel(id, cur === '서랍 단면' || cur === '부품 상세' ? cur : '부품 상세'); return; }
    if (slot === 'main' || slot === 'iso') {
      var opts = view.plan.kitchen ? (slot === 'main' ? FRONT_ISO.slice(0, 2) : FRONT_ISO.slice(2)) : FRONT_ISO;
      if (opts.indexOf(cur) >= 0) { return; }
      chooser(card, id, opts);
    }
  }

  function acceptDrop(card, slot, view) {
    if (!api.core.canSave()) { return; }
    card.addEventListener('dragover', function (e) {
      if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], DRAG) >= 0) { e.preventDefault(); card.classList.add('dws-v2-card-drop'); }
    });
    card.addEventListener('dragleave', function () { card.classList.remove('dws-v2-card-drop'); });
    card.addEventListener('drop', function (e) {
      card.classList.remove('dws-v2-card-drop');
      var id = e.dataTransfer && e.dataTransfer.getData(DRAG);
      if (!id) { return; }
      e.preventDefault();
      dropTo(card, slot, id, view);
    });
  }

  function tags(list, view) {
    var wrap = el('div', 'dws-v2-tags'), th = api.core.threshold();
    list.forEach(function (o) {
      var p = o.part || {}, label = view.plan.g.labels[o.id] || '미분류';
      var sure = p.src === 'user' || (typeof p.conf === 'number' && p.conf >= th);
      var t = el('span', 'dws-v2-tag' + (sure ? ' dws-v2-tag-ok' : ' dws-v2-tag-ai'), (sure ? '✓ ' : '') + label.replace('·', ' · '));
      t.title = p.src === 'user' ? '사람이 고른 종류' : ('AI 짐작' + (typeof p.conf === 'number' ? ' · 확신 ' + Math.round(p.conf * 100) + '%' : '') +
        (sure ? '' : ' — 맞으면 그림을 고르고 Enter'));
      wrap.appendChild(t);
      if (view.plan.g.fixed[o.id]) { var f = el('span', 'dws-v2-tag dws-v2-tag-fixed', '고정'); f.title = '손으로 옮겼거나 잠근 그림 — 다시 배치해도 그대로'; wrap.appendChild(f); }
    });
    return wrap;
  }

  function card(slot, head, list, view, extra) {
    var c = el('div', 'dws-v2-card');
    c.setAttribute('data-slot', slot);
    var h = el('div', 'dws-v2-card-head');
    h.appendChild(el('span', 'dws-v2-card-badge' + (head.badge.length > 1 ? ' dws-v2-card-badge-word' : ''), head.badge));
    h.appendChild(el('span', 'dws-v2-card-title', head.title));
    if (head.chip) { h.appendChild(el('span', 'dws-v2-chip dws-v2-chip-' + head.tone, head.chip)); }
    c.appendChild(h);
    var body = el('div', 'dws-v2-card-body');
    list.slice(0, 4).forEach(function (o) { body.appendChild(thumb(o, view)); });
    var info = el('div', 'dws-v2-card-info');
    if (head.meta) { info.appendChild(el('span', 'dws-v2-card-meta', head.meta)); }
    if (list.length) { info.appendChild(tags(list, view)); }
    if (extra) { info.appendChild(extra); }
    body.appendChild(info);
    c.appendChild(body);
    acceptDrop(c, slot, view);
    return c;
  }

  function lowPct(list, view) {
    var ps = list.map(function (o) { return view.pct[o.id]; }).filter(function (v) { return v > 0; });
    return ps.length ? Math.min.apply(null, ps) : null;
  }

  function linkBtn(label, onClick) {
    var b = el('button', 'dws-v2-link', label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  function renderCards(view) {
    var plan = view.plan, g = plan.g, f = view.sheet.form || {}, L = plan.letters, out = [];
    var meta = [f.site_spec, f.color].map(function (v) { return String(v || '').trim(); }).filter(Boolean).join(' · ');
    function pctHead(list, key) {
      var p = lowPct(list, view), isMin = list.some(function (o) { return o.id === view.minId; });
      return p == null ? {} : { chip: Math.round(p * 100) + '%', tone: isMin ? 'orange' : (key === 'main' || key === 'iso' ? 'blue' : 'gray') };
    }
    var auto = g.photo.some(function (o) { return view.autoPhoto[o.id]; });
    out.push(card('photo', { badge: '사진', title: '실측 사진 ' + g.photo.length + '장', chip: auto ? '자동' : '', tone: 'green',
      meta: auto ? '실측 사진 중 방 전체가 잘 보이는 사진을 골랐어요' : (g.photo.length ? '' : '실측 사진 칸에서 눌러 넣어요') }, g.photo, view,
      linkBtn(g.photo.length ? '다른 사진' : '실측 사진 보기', function () { setTab('photos'); })));
    var heads = g.bom.map(function (o) { return String(o.text || '').split('\n')[0].trim(); }).join(' ');
    out.push(card('bom', { badge: '자재', title: '자재표 ' + g.bom.length + '열', chip: '직접 입력', tone: 'gray', meta: heads || '자재표 글자가 없어요' }, [], view,
      linkBtn('자재표 계산 열기', function () { var b = $('dws-btn-calc'); if (b) { b.click(); } })));
    [['main', L.main || 'A', plan.kitchen ? '정면' : (String(f.product_name || '').trim() || '큰 그림'), plan.kitchen ? '' : meta],
      ['iso', L.iso || 'B', '입체', ''], ['detail', L.detail || 'B', '상세', '작은 상세'], ['plan', L.plan || 'C', '평면 · 상판', '']]
      .forEach(function (k) {
        var list = g[k[0]] || [];
        if (!list.length && k[0] !== 'main') { return; }
        var ph = pctHead(list, k[0]);
        out.push(card(k[0], { badge: k[1], title: k[2], chip: ph.chip, tone: ph.tone, meta: list.length ? k[3] : '큰 그림을 여기로 끌어 놓아요' }, list, view));
      });
    if (window.FomsV2Notes) { out.push(window.FomsV2Notes.card(view, api)); }
    els.cards.textContent = '';
    out.forEach(function (c) { els.cards.appendChild(c); });
  }

  function renderUnsorted(view) {
    var box = els.unsorted, list = view.plan.g.unsorted;
    box.textContent = '';
    box.className = 'dws-v2-unsorted ' + (list.length ? 'dws-v2-unsorted-warn' : 'dws-v2-unsorted-ok');
    box.appendChild(el('strong', 'dws-v2-unsorted-title', '미분류 ' + list.length + '장'));
    if (!list.length) {
      box.appendChild(el('span', 'dws-v2-unsorted-text', '모든 그림이 칸을 찾았어요. 확신이 낮은 그림은 여기로 모여서 사람이 골라요.'));
      acceptDrop(box, 'unsorted', view);
      return;
    }
    box.appendChild(el('span', 'dws-v2-unsorted-text', '종류를 골라 주세요 — 고른 종류는 다음 AI 학습에 쓰여요.'));
    list.forEach(function (o) {
      var row = el('div', 'dws-v2-unsorted-row');
      row.appendChild(thumb(o, view));
      var sel = el('select', 'dws-v2-unsorted-select');
      sel.setAttribute('aria-label', '그림 종류');
      sel.disabled = !api.core.canSave();
      ALL.forEach(function (l) { var op = el('option', '', l); op.value = l; sel.appendChild(op); });
      sel.value = view.plan.g.labels[o.id] || '미분류';
      sel.addEventListener('change', function () { api.relabel(o.id, sel.value); });
      row.appendChild(sel);
      box.appendChild(row);
    });
  }

  function renderKind(view) {
    if (!els.kind) { return; }
    var plan = view.plan, n = plan.input.units.length, rest = plan.g.detail.length + plan.g.plan.length;
    els.kind.textContent = '';
    window.FomsV2Slots.KINDS.forEach(function (k) {
      var op = el('option', '', k.name + (k.key === plan.kind ? ' · 큰 그림 ' + n + (rest ? ' + 상세' : '') : ''));
      op.value = k.key;
      els.kind.appendChild(op);
    });
    els.kind.value = plan.kind;
    els.kind.disabled = !api.core.canSave();
    if (els.kindAuto) { els.kindAuto.hidden = !!(view.sheet.form && view.sheet.form.v2_kind); }
  }

  function render(view) {
    var core = api.core;
    var setCount = function (k, v) { var n = document.querySelector('[data-v2-count="' + k + '"]'); if (n) { n.textContent = String(v); } };
    setCount('products', (core.products() || []).length);
    setCount('photos', (core.photos() || []).filter(core.photoVisible).length);
    if (!els.cards || !view.sheet || !view.plan) {
      if (els.cards) { els.cards.textContent = ''; }
      if (els.unsorted) { els.unsorted.textContent = ''; }
      setCount('slots', 0);
      return;
    }
    var g = view.plan.g, act = document.activeElement;
    var refocus = !!(act && act.closest && act.closest('.dws-v2-note-add'));   // 더하기 칸은 다시 그린 뒤 커서를 돌려준다(이어 치기)
    if (refocus) { act = null; }
    setCount('slots', ['photo', 'main', 'iso', 'detail', 'plan', 'unsorted'].filter(function (k) { return g[k].length; }).length +
      (g.bom.length ? 1 : 0) + (g.notes.length || g.stamp ? 1 : 0));
    if (act && els.cards.contains(act) && /^(INPUT|TEXTAREA)$/.test(act.tagName)) {   // 특이 사항을 치는 중 — 칸을 다시 그리면 커서가 사라진다
      if (!els.waiting) {
        els.waiting = true;
        act.addEventListener('blur', function () { els.waiting = false; api.refresh(); }, { once: true });
      }
      return;
    }
    renderKind(view);
    renderCards(view);
    renderUnsorted(view);
    if (refocus) { var add = els.cards.querySelector('.dws-v2-note-add .dws-v2-note-input'); if (add) { add.focus(); } }
  }

  window.FomsV2Left = { init: init, render: render, setTab: setTab };
})();
