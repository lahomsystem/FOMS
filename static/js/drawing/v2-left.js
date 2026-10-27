/**
 * 도면 마법사 V2 — 왼쪽 칸: [제품 N | 그림 N | 실측 사진 N] · 확인할 그림(v2-check.js) · 제품 종류 · 칸 카드.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 (화면 시안 K2 왼쪽 316px)
 * - 제품 · 실측 사진 칸은 V1 목록 DOM(#dws-product-list · #dws-pending · #dws-photos)을 옮겨 담는다 — 눌러 넣기 · 끌어 넣기 그대로.
 * - 칸 카드의 작은 그림마다 바로 밑에 그 그림의 종류 딱지를 붙인다(예전엔 딱지가 옆에 세로로 쌓여 어느 그림 것인지 몰랐다 —
 *   2026-10-27 사용성 평가). 작은 그림을 누르면 종이에서 그 그림을 고르고(V1 미니 막대 · 숫자키로 종류를 고친다), 다른 카드로
 *   끌어 놓으면 그 칸 종류로 바꾼다(사람이 고친 종류 = 다음 AI 학습 자료). 큰 그림 칸은 넷 중에서 고른다.
 *   '?'(AI 칸 짐작) · 미분류 딱지를 누르면 맨 위 '확인할 그림' 상자의 그 그림으로 간다.
 * - 탭 '그림 N' = 종이에 놓인 그림 수(실측 사진 빼고 — 사람은 칸이 아니라 그림을 센다).
 * - 제품 종류는 제품 이름 · 시트 이름 글자로 고른다(v2-slots detectKind) — 화면 글도 그대로 말한다. 자동으로 고른 종류에 '(자동)'.
 * - 자재 카드: 자재표 글자가 없으면 [자재표 칸 넣기](엔진 addPresets — 자리표 다섯, 되돌리기 한 번, 칸으로 정리한 시트면 자재 칸에
 *   놓는다) · 늘 '계산해 보기 (참고용)'(자재표 계산 칸 — 결과를 시트에 넣지 않는다).
 * - 특이 사항 · 강조 문구 카드는 v2-notes.js 가 그린다.
 *
 * window.FomsV2Left = { init(api), render(view), setTab(t) }
 */
(function () {
  'use strict';
  if (window.FomsV2Left) { return; }

  var api = null, els = {}, tab = 'slots', DRAG = 'application/x-dws-v2-id';
  var FRONT_ISO = ['정면·내부', '정면·도어', '입체·내부', '입체·도어'];

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
    if (window.FomsV2Check) { window.FomsV2Check.init(a); }
  }

  function thumb(o, view) {
    var core = api.core, fixed = !!view.plan.g.fixed[o.id], b = el('button', 'dws-v2-thumb' + (fixed ? ' dws-v2-thumb-fixed' : ''));
    b.type = 'button';
    b.title = (view.plan.g.labels[o.id] || '미분류') + ' — 눌러서 종이에서 고르기 · 다른 칸으로 끌어서 종류 바꾸기' +
      (fixed ? ' · 고정(손으로 옮겼거나 잠근 그림 — 다시 배치해도 그대로)' : '');
    var img = el('img', 'dws-v2-thumb-img');
    img.alt = view.plan.g.labels[o.id] || '그림';
    img.loading = 'lazy';
    img.src = core.viewUrl(o.key);
    b.appendChild(img);
    if (fixed) { b.appendChild(el('span', 'dws-v2-thumb-pin', '고정')); }
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

  /** 그림 한 장의 종류 딱지(작은 그림 바로 밑) — ✓ 사람 · 확신 넘은 AI / 점선 AI 짐작 / 주황 '?' 칸만 짐작 · 미분류(누르면 확인할 그림으로). */
  function tag(o, view) {
    var p = o.part || {}, g = view.plan.g, label = g.labels[o.id] || '미분류', gs = g.guess[o.id], ask = !!gs || label === '미분류';
    var sure = !ask && (p.src === 'user' || (typeof p.conf === 'number' && p.conf >= api.core.threshold()));
    var t = el(ask ? 'button' : 'span', 'dws-v2-tag ' + (sure ? 'dws-v2-tag-ok' : (ask ? 'dws-v2-tag-guess' : 'dws-v2-tag-ai')),
      (sure ? '✓ ' : '') + (gs ? g.lay[o.id] + '?' : label));
    t.title = gs ? 'AI 가 칸만 짐작했어요(칸 확신 ' + Math.round(gs.conf * 100) + '%) — 눌러서 종류 고르기'
      : ask ? '종류를 몰라요 — 눌러서 종류 고르기' : p.src === 'user' ? '사람이 고른 종류'
        : ('AI 짐작' + (typeof p.conf === 'number' ? ' · 확신 ' + Math.round(p.conf * 100) + '%' : '') + (sure ? '' : ' — 맞으면 그림을 고르고 Enter'));
    if (ask) {
      t.type = 'button';
      t.disabled = !api.core.canSave();
      t.addEventListener('click', function () { if (window.FomsV2Check) { window.FomsV2Check.show(o.id); } });
    }
    return t;
  }

  function card(slot, head, list, view, extra) {
    var c = el('div', 'dws-v2-card');
    c.setAttribute('data-slot', slot);
    var h = el('div', 'dws-v2-card-head');
    h.appendChild(el('span', 'dws-v2-card-badge' + (head.badge.length > 1 ? ' dws-v2-card-badge-word' : ''), head.badge));
    h.appendChild(el('span', 'dws-v2-card-title', head.title));
    if (head.chip) { h.appendChild(el('span', 'dws-v2-chip dws-v2-chip-' + head.tone, head.chip)); }
    c.appendChild(h);
    if (list.length) {
      var figs = el('div', 'dws-v2-figs');
      list.forEach(function (o) {
        var f = el('div', 'dws-v2-fig');
        f.appendChild(thumb(o, view));
        f.appendChild(tag(o, view));
        figs.appendChild(f);
      });
      c.appendChild(figs);
    }
    if (head.meta) { c.appendChild(el('span', 'dws-v2-card-meta', head.meta)); }
    if (extra) { c.appendChild(extra); }
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

  /** [자재표 칸 넣기] — 자리표 다섯을 넣고(되돌리기 한 번) 칸으로 정리한 자동 배치 시트면 자재 칸에 놓는다. */
  function addBom() {
    var core = api.core, ids = core.addPresets ? core.addPresets() : [], sh = core.sheet();
    if (!ids.length) { return; }
    if (api.mode() === 'auto' && sh && sh.form && sh.form.v2_layout) { api.arrange('bom', {}); } else { api.refresh(); }
    core.toast('자재표 칸 ' + ids.length + '개를 넣었어요 — 머리글을 눌러 내용을 써요 · 되돌리기 Ctrl+Z');
  }

  function bomTools(n) {
    var box = el('div', 'dws-v2-card-tools');
    if (!n) {
      var add = el('button', 'dws-v2-bom-add', '자재표 칸 넣기');
      add.type = 'button';
      add.title = '[SR] [EP] [DOOR] [옷봉] [마이다] 빈 칸을 넣어 자재 칸에 놓아요 · 되돌리기 Ctrl+Z';
      add.disabled = !api.core.canSave() || !api.core.addPresets;
      add.addEventListener('click', addBom);
      box.appendChild(add);
    }
    box.appendChild(linkBtn('계산해 보기 (참고용)', function () { var b = $('dws-btn-calc'); if (b) { b.click(); } }));
    return box;
  }

  function renderCards(view) {
    var plan = view.plan, g = plan.g, f = view.sheet.form || {}, L = plan.letters, out = [];
    var meta = [['현장규격', f.site_spec], ['색상', f.color]].map(function (p) {   // 아래 띠 칸 이름을 붙인다(1500 이 무슨 숫자인지)
      var v = String(p[1] || '').trim();
      return v ? p[0] + ' ' + v : '';
    }).filter(Boolean).join(' · ');
    function pctHead(list, key) {
      var p = lowPct(list, view), isMin = list.some(function (o) { return o.id === view.minId; });
      return p == null ? {} : { chip: Math.round(p * 100) + '%', tone: isMin ? 'orange' : (key === 'main' || key === 'iso' ? 'blue' : 'gray') };
    }
    var auto = g.photo.some(function (o) { return view.autoPhoto[o.id]; });
    out.push(card('photo', { badge: '사진', title: '실측 사진 ' + g.photo.length + '장', chip: auto ? '자동' : '', tone: 'green',
      meta: auto ? '실측 사진 중 방 전체가 잘 보이는 사진을 골랐어요' : (g.photo.length ? '' : '실측 사진 탭에서 눌러 넣어요') }, g.photo, view,
      linkBtn(g.photo.length ? '다른 사진' : '실측 사진 보기', function () { setTab('photos'); })));
    var heads = g.bom.map(function (o) { return String(o.text || '').split('\n')[0].trim(); }).join(' ');
    out.push(card('bom', { badge: '자재', title: '자재표 ' + g.bom.length + '열', meta: heads || '자재표 글자가 없어요' }, [], view,
      bomTools(g.bom.length)));
    var T = function (k) { return window.FomsV2Slots.title(k, g, plan.kitchen); };   // 칸 이름 = 든 그림 종류(종이 머리와 같다)
    var slots = [['main', L.main || 'A', T('main'), plan.kitchen ? '' : meta], ['iso', L.iso || 'B', T('iso'), ''],
      ['detail', L.detail || 'B', T('detail'), '작은 상세'], ['plan', L.plan || 'C', T('plan'), ''], ['unsorted', L.unsorted || '?', T('unsorted'), '']]
      .filter(function (k) { return (g[k[0]] || []).length || k[0] === 'main'; });
    // 카드는 칸 글자 순서로(종이 머리 글자와 같은 차례 — 글자를 종이 읽는 순서로 붙이면 카드도 그 순서). 빈 큰 그림 칸(끌어 놓는 곳)은 맨 앞
    var at = function (k) { return L[k[0]] || (k[0] === 'main' ? '' : '~'); };
    slots.sort(function (a, b) { return at(a) < at(b) ? -1 : (at(a) > at(b) ? 1 : 0); }).forEach(function (k) {
      var list = g[k[0]] || [], ph = pctHead(list, k[0]);
      out.push(card(k[0], { badge: k[1], title: k[2], chip: ph.chip, tone: ph.tone, meta: list.length ? k[3] : '큰 그림을 여기로 끌어 놓아요' }, list, view));
    });
    if (window.FomsV2Notes) { out.push(window.FomsV2Notes.card(view, api)); }
    els.cards.textContent = '';
    out.forEach(function (c) { els.cards.appendChild(c); });
  }

  function renderKind(view) {
    if (!els.kind) { return; }
    var plan = view.plan;
    els.kind.textContent = '';
    window.FomsV2Slots.KINDS.forEach(function (k) {
      var op = el('option', '', k.name + (k.key === plan.kindAuto ? ' (자동)' : ''));
      op.value = k.key;
      els.kind.appendChild(op);
    });
    els.kind.value = plan.kind;
    els.kind.disabled = !api.core.canSave();
    if (els.kindAuto) { els.kindAuto.hidden = !!(view.sheet.form && view.sheet.form.v2_kind); }
  }

  function render(view) {
    var core = api.core, check = window.FomsV2Check;
    var setCount = function (k, v) { var n = document.querySelector('[data-v2-count="' + k + '"]'); if (n) { n.textContent = String(v); } };
    setCount('products', (core.products() || []).length);
    setCount('photos', (core.photos() || []).filter(core.photoVisible).length);
    if (!els.cards || !view.sheet || !view.plan) {
      if (els.cards) { els.cards.textContent = ''; }
      if (check) { check.render(view); }
      setCount('slots', 0);
      return;
    }
    var g = view.plan.g, act = document.activeElement;
    var refocus = !!(act && act.closest && act.closest('.dws-v2-note-add'));   // 더하기 칸은 다시 그린 뒤 커서를 돌려준다(이어 치기)
    if (refocus) { act = null; }
    setCount('slots', g.main.length + g.iso.length + g.detail.length + g.plan.length + g.unsorted.length);   // 종이에 놓인 그림(실측 사진 빼고)
    if (act && els.cards.contains(act) && /^(INPUT|TEXTAREA)$/.test(act.tagName)) {   // 특이 사항을 치는 중 — 칸을 다시 그리면 커서가 사라진다
      if (!els.waiting) {
        els.waiting = true;
        act.addEventListener('blur', function () { els.waiting = false; api.refresh(); }, { once: true });
      }
      return;
    }
    renderKind(view);
    renderCards(view);
    if (check) { check.render(view); }
    if (refocus) { var add = els.cards.querySelector('.dws-v2-note-add .dws-v2-note-input'); if (add) { add.focus(); } }
  }

  window.FomsV2Left = { init: init, render: render, setTab: setTab };
})();
