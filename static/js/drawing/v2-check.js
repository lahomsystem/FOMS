/**
 * 도면 마법사 V2 — 왼쪽 칸 맨 위 '확인할 그림' 상자: 종류를 사람이 골라야 하는 그림만 모아 큰 미리보기와 종류 단추로 고르게 한다.
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 · 도면팀원 눈 사용성 평가(2026-10-27 큼 — 할 일(종류 확인)이
 *   카드 목록 맨 끝이라 작은 화면에선 안 보였고, 종류를 고치는 길이 다섯 갈래였다)
 * - 고를 그림 = 앱바 '미분류 N장 ›' 칩과 같은 셈: 이름표가 미분류(AI 칸 짐작 '?' 포함)이거나 이름표가 없는 그림(알아보는 중이면
 *   뺀다 — part-badges.js badgeInfo 'unsure' 와 같은 규칙). 종이 읽는 순서(위 줄부터, 줄 안은 왼쪽부터 — part-status.js 와 같은 80px 줄).
 * - 종류 단추 2~4개 = AI 첫 짐작(part.ai) → 칸 짐작(v2_ai) 또는 첫 짐작의 칸 식구 → 큰 그림 넷, 나머지는 '그 밖 ▾'.
 *   시트에는 AI 확률이 다 남지 않는다(첫 짐작 · 확신 · 칸 짐작만) — 이 순서가 'AI 확률 높은 순'에 가장 가깝다.
 * - 누르면 바로 바꾸고(FomsV2.relabel) 다음 그림 첫 단추로 초점을 옮긴다. 다시 그릴 때(배치 · 늦은 AI 이름표) 고를 것이 그대로면
 *   상자를 새로 만들지 않는다 — 누르는 사이에 단추가 바뀌면 눌림이 사라진다.
 * - 미리보기에 마우스를 올리거나 그 줄에 초점이 가면 종이에서 그 그림을 파란 테로 짚는다(스테이지 안 .dws-ui — PNG · 저장 그림에 안 찍힘).
 * - 앱바 '미분류 N장 ›' 칩 · 카드의 '?' 딱지는 이 상자로 데려온다. 칩은 상자에 그림이 있을 때만 받아 V1 처리(part-badges goNext —
 *   종이에서 다음 미분류 그림 고르기)를 건너뛴다(캡처 단계). 칩을 거듭 누르면 다음 그림으로.
 *
 * window.FomsV2Check = { init(api), render(view), show(id), point(id), pending(sheet, waiting), choices(o, g, kitchen) }
 *   (pending · choices 는 node 로 시험한다 — tests/domains/test_drawing_wizard_v2_left_ux.py)
 */
(function () {
  'use strict';
  if (window.FomsV2Check) { return; }

  var FRONT = ['정면·내부', '정면·도어'], ISO = ['입체·내부', '입체·도어'];
  var ALL = FRONT.concat(['사이드뷰'], ISO, ['평면·상판', '탑뷰', '서랍 단면', '부품 상세', '사진', '그림 아님']);   // 사이드뷰 · 탑뷰 2026-10-28
  var ROW = 80, PAD = 6;   // 읽는 순서 한 줄 높이(part-status.js 와 같다) · 짚는 테가 그림 밖으로 나오는 여백(스테이지 px)
  var CHIP_TITLE = '왼쪽 \'확인할 그림\' 상자로 — 그림을 보고 종류를 골라요';
  var api = null, els = { ids: [] }, sig = null, want = null, pointed = null, lastShown = null;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }
  function nice(label) { return String(label).replace('·', ' · '); }
  function isWaiting() { var St = window.FomsPartStatus; return !!(St && St.waiting && St.waiting()); }

  /** 확인할 그림(종이 읽는 순서) — 이름표가 미분류, 또는 이름표가 없고 알아보는 중이 아닌 그림. */
  function pending(sheet, waiting) {
    return ((sheet && sheet.objects) || []).filter(function (o) {
      var p = (o && o.part) || {};
      return !!o && o.type === 'image' && (p.label ? p.label === '미분류' : !waiting);
    }).sort(function (a, b) {
      return (Math.round((a.y || 0) / ROW) - Math.round((b.y || 0) / ROW)) || ((a.x || 0) - (b.x || 0));
    });
  }

  /** 종류 단추 — { quick: 2~4개(AI 첫 짐작 → 칸 식구 → 큰 그림 넷), rest: 나머지('그 밖 ▾') }. 주방이면 짐작 칸의 둘만 더한다. */
  function choices(o, g, kitchen) {
    var p = (o && o.part) || {}, gs = g && g.guess ? g.guess[o.id] : null, out = [];
    var famOf = (window.FomsV2Slots && window.FomsV2Slots.FAM_OF) || {}, fam = gs ? gs.fam : famOf[p.ai];
    function add(l) { if (ALL.indexOf(l) >= 0 && out.indexOf(l) < 0) { out.push(l); } }
    add(p.ai);
    if (p.ai === '평면·상판') { add('탑뷰'); }   // 위에서 본 그림 — AI 는 아직 탑뷰를 몰라 평면·상판으로 짐작한다
    if (fam === 'd') { add('서랍 단면'); add('부품 상세'); }
    if (fam === 'f' || fam === 'i') {
      (fam === 'f' ? FRONT : ISO).forEach(add);
      if (!kitchen) { (fam === 'f' ? ISO : FRONT).forEach(add); }
    }
    if (out.length < 2) { FRONT.concat(ISO).forEach(add); }
    var quick = out.slice(0, 4);
    return { quick: quick, rest: ALL.filter(function (l) { return quick.indexOf(l) < 0; }) };
  }

  function findImage(id) {
    var sh = api && api.core.sheet();
    return id && sh ? (sh.objects || []).filter(function (x) { return x.id === id && x.type === 'image'; })[0] || null : null;
  }

  /** 종이에서 그 그림을 파란 테로 짚는다(id 없음 = 걷기). 스테이지 안 층이라 줌을 따라가고, .dws-ui 라 내보내기 때 숨는다. */
  function point(id) {
    var o = findImage(id), host = document.getElementById('dws-stage');
    pointed = o && host ? id : null;
    if (!pointed) { if (els.point) { els.point.hidden = true; } return; }
    if (!els.point || els.point.parentNode !== host) {
      els.point = el('div', 'dws-v2-point dws-ui');
      els.point.setAttribute('aria-hidden', 'true');
      host.appendChild(els.point);
    }
    var s = els.point.style;
    s.left = Math.round((o.x || 0) - PAD) + 'px';
    s.top = Math.round((o.y || 0) - PAD) + 'px';
    s.width = Math.round((o.w || 0) + PAD * 2) + 'px';
    s.height = Math.round((o.h || 0) + PAD * 2) + 'px';
    s.transformOrigin = PAD + 'px ' + PAD + 'px';   // Konva 그림은 (x, y)를 축으로 돈다(offset 0)
    s.transform = o.rotation ? 'rotate(' + o.rotation + 'deg)' : '';
    els.point.hidden = false;
  }

  function rowOf(node) { return node && node.closest ? node.closest('.dws-v2-check-row') : null; }
  function focusedId() {
    var r = rowOf(document.activeElement);
    return r && els.box.contains(r) ? r.getAttribute('data-id') : null;
  }

  /** 그 그림 줄로 초점(label = 같은 단추, 없으면 첫 단추). 줄이 없으면 첫 줄. reveal = 줄이 보이게 왼쪽 칸을 굴린다. */
  function focusRow(id, label, reveal) {
    var rows = els.box.querySelectorAll('.dws-v2-check-row'), r = null;
    Array.prototype.forEach.call(rows, function (x) { if (x.getAttribute('data-id') === id) { r = x; } });
    r = r || rows[0];
    if (!r) { return; }
    var t = label != null ? r.querySelector('[data-label="' + label + '"]') : null;
    t = t || r.querySelector('.dws-v2-check-btn') || r.querySelector('.dws-v2-check-more');
    if (t) { t.focus({ preventScroll: true }); }
    if (reveal && r.scrollIntoView) { r.scrollIntoView({ block: 'nearest' }); }
  }

  /** 종류를 고른다 — 바로 바꾸고, 다시 그린 뒤 다음 그림(마지막이면 남은 첫 그림)의 첫 단추로 초점. */
  function pick(id, label) {
    var ids = els.ids, at = ids.indexOf(id), rest = ids.filter(function (x) { return x !== id; });
    want = rest.length ? (ids[at + 1] || rest[0]) : null;
    api.relabel(id, label);
  }

  function row(o, n, plan) {
    var c = choices(o, plan.g, plan.kitchen), ai = (o.part || {}).ai, r = el('div', 'dws-v2-check-row');
    r.setAttribute('data-id', o.id);
    var pic = el('button', 'dws-v2-check-pic'), img = el('img', 'dws-v2-check-img');
    pic.type = 'button';
    pic.title = '종이에서 이 그림 고르기';
    pic.setAttribute('aria-label', n + '번째 확인할 그림 — 종이에서 고르기');
    img.alt = '';
    img.src = api.core.viewUrl(o.key);
    pic.appendChild(img);
    pic.addEventListener('click', function () { api.selectIds([o.id]); });
    pic.addEventListener('mouseenter', function () { point(o.id); });
    pic.addEventListener('mouseleave', function () { point(focusedId()); });
    r.appendChild(pic);
    var picks = el('div', 'dws-v2-check-picks');
    c.quick.forEach(function (l) {
      var b = el('button', 'dws-v2-check-btn' + (l === ai ? ' dws-v2-check-btn-ai' : ''), nice(l));
      b.type = 'button';
      b.setAttribute('data-label', l);
      if (l === ai) { b.title = 'AI 첫 짐작'; }
      b.addEventListener('click', function () { pick(o.id, l); });
      picks.appendChild(b);
    });
    var more = el('select', 'dws-v2-check-more');
    more.setAttribute('aria-label', '그 밖 종류');
    more.setAttribute('data-label', '');
    [''].concat(c.rest).forEach(function (l) { var op = el('option', '', l ? nice(l) : '그 밖 ▾'); op.value = l; more.appendChild(op); });
    more.addEventListener('change', function () { if (more.value) { pick(o.id, more.value); } });
    picks.appendChild(more);
    r.appendChild(picks);
    r.addEventListener('focusin', function () { point(o.id); });
    return r;
  }

  function draw(items, plan) {
    var box = els.box;
    box.textContent = '';
    box.hidden = !items.length;
    els.ids = items.map(function (o) { return o.id; });
    if (!items.length) { return; }
    var head = el('div', 'dws-v2-check-head');
    head.appendChild(el('strong', 'dws-v2-check-title', '확인할 그림 ' + items.length + '장'));
    head.appendChild(el('span', 'dws-v2-check-text', '그림을 보고 종류를 골라 주세요'));
    box.appendChild(head);
    items.forEach(function (o, i) { box.appendChild(row(o, i + 1, plan)); });
  }

  function render(view) {
    var box = els.box;
    if (!box) { return; }
    var plan = view && view.sheet ? view.plan : null;
    var items = plan && api.core.canSave() ? pending(view.sheet, isWaiting()) : [];
    var s = items.map(function (o) { return [o.id, o.key, choices(o, plan.g, plan.kitchen).quick.join(',')].join(':'); }).join('|');
    if (s !== sig) {   // 고를 것이 바뀔 때만 새로 만든다 — 초점은 같은 그림 · 같은 단추로 돌려준다
      var act = document.activeElement, r = box.contains(act) ? rowOf(act) : null, keep = box.contains(act);
      var label = act && act.getAttribute ? act.getAttribute('data-label') : null;
      sig = s;
      draw(items, plan);
      if (want == null && keep && items.length) { focusRow(r ? r.getAttribute('data-id') : '', label, false); }
    }
    if (want != null) { var w = want; want = null; if (items.length) { focusRow(w, null, true); } }
    var chip = items.length ? document.querySelector('.dws-part-status-unsure') : null;
    if (chip && chip.title !== CHIP_TITLE) { chip.title = CHIP_TITLE; }
    point(els.ids.indexOf(pointed) >= 0 ? pointed : null);   // 배치로 그림이 옮겨졌으면 테도 따라간다
  }

  /** 이 상자로 데려온다(칩 · 카드 '?' 딱지). id 없음 = 지난번 다음 그림(칩을 거듭 누르면 차례로). */
  function show(id) {
    var ids = els.ids;
    if (!els.box || !ids.length) { return; }
    if (window.FomsV2Left && window.FomsV2Left.setTab) { window.FomsV2Left.setTab('slots'); }
    var at = id ? ids.indexOf(id) : (ids.indexOf(lastShown) + 1) % ids.length;
    lastShown = ids[at < 0 ? 0 : at];
    if (els.box.scrollIntoView) { els.box.scrollIntoView({ block: 'nearest' }); }
    focusRow(lastShown, null, true);
    point(lastShown);
  }

  function onChip(e) {
    var chip = e.target && e.target.closest ? e.target.closest('.dws-part-status-unsure') : null;
    if (!chip || !els.box || els.box.hidden) { return; }   // 상자에 그림이 없으면 V1 처리 그대로
    // 막지 않고 표시만 한다 — 문서 클릭(⋯ 메뉴 · V1 메뉴 닫기)은 그대로 돌고, V1 칩 처리는 part-status 가 건너뛴다.
    // 예전엔 stopPropagation 이라 ⋯ 메뉴를 연 채 칩을 누르면 메뉴가 남았다(운영 점검 2026-10-27).
    e.preventDefault();
    show(null);
  }

  function init(a) {
    api = a;
    els.box = document.getElementById('dws-v2-unsorted');
    if (!els.box) { return; }
    els.box.addEventListener('focusout', function (e) {
      if (!e.relatedTarget || !els.box.contains(e.relatedTarget)) { point(null); }
    });
    document.addEventListener('click', onChip, true);
  }

  window.FomsV2Check = { init: init, render: render, show: show, point: point, pending: pending, choices: choices };
})();
