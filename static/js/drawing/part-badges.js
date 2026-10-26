/**
 * 도면 마법사 — 그림 종류 이름 딱지 · 미분류 칩 · 분류 진행 칩 (화면에만, 내보내기·저장 그림에는 안 찍힌다).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.1 · 사용성 평가(2026-10-25) 큼-7·큼-8·보통-1
 * - 그림마다 딱지: AI 짐작 = 점선 'AI 72% · 정면·내부', 사람 확인 = 초록 '✓ 정면·도어'(짧게 — V1 확인 딱지가 숫자를 덮음),
 *   미분류 = 주황 '? 미분류', 주방 짝 규칙이 바꾼 이름 = 'AI 짝 규칙 · 정면·내부'.
 *   종류를 알아보는 중(이름표 없음)인 그림은 딱지 없이 앱바 칩만 보인다.
 * - 딱지 자리(재평가 QA1·QA3 — 그림 안 왼쪽 위에 얹으면 맨 위 치수·옆 자리표를 가리고 딱지끼리 겹쳤다):
 *   그림 틀 위 바깥·틀에 걸침·안쪽 위아래 중 덜 가리는 곳(part-badge-spot.js — 글자 같은 잉크·양식 칸·다른 딱지를 본다).
 *   그림 폭보다 길면 짧은 글(종류 이름만). 마우스를 올린 그림·하나만 고른 그림(손가락·펜슬엔 마우스 올리기가 없다) 위에
 *   걸친 딱지는 흐려지고, 하나만 고른 그림의 제 딱지는 숨는다(미니 막대가 같은 글). 앱바 딱지 단추로 모두 숨긴다(기억).
 * - 딱지 층(.dws-pbadges.dws-ui, 누름 통과)은 줌이 걸린 스테이지 안, 딱지 크기는 badgeScale(100% 아래는 80% 까지 준다).
 *   내보내기(.dws-exporting)에서는 통째로 숨는다. Konva 노드로 그리면 내보내기 그림에 찍히므로 DOM 으로 겹친다.
 * - 끌기·변형·화살표 이동·그림 불러옴·줌 바뀜은 다음 그림 틀에 자리만 다시 고른다.
 * - 앱바 칩 묶음('그림 종류 알아보는 중 3/8' · '미분류 N장 ›' · 딱지 숨기기 단추)은 part-status.js.
 *
 * window.FomsPartBadges = { init(opts), refresh(), progress(done, total, {loading}),
 *   badgeInfo, partHint, withRo, multiLabelPlan }
 *   (순수 함수와 딱지 자리는 node 로 시험한다 — tests/domains/test_drawing_part_badges.py)
 */
(function () {
  'use strict';
  if (window.FomsPartBadges) { return; }

  var UNSURE = '미분류';
  var OFF_KEY = 'foms.drawingWizard.partBadgesOff';
  var EVENTS = ['x', 'y', 'width', 'height', 'rotation', 'scaleX', 'scaleY', 'image']
    .map(function (a) { return a + 'Change.dwspb'; }).join(' ');

  var opt = null;      // init 옵션
  var layer = null;    // 딱지 층(스테이지 안)
  var badges = {};     // 그림 id → 딱지 요소(_pre · _label · 잰 폭 _fw/_sw/_bh · 놓은 자리 _r)
  var hover = null;    // 마우스가 올라간 그림 id
  var off = false;     // 앱바 단추로 딱지를 모두 숨겼나
  var size = null;     // 스테이지 크기(한 번만 잰다)
  var queued = { all: false, raf: false };

  function pct(conf) { return (typeof conf === 'number' && isFinite(conf)) ? Math.round(conf * 100) + '%' : ''; }
  function pairChanged(part, th) {
    var P = window.FomsPartPair;
    return !!(P && P.pairChanged && P.pairChanged(part, th));
  }

  /* ---- 순수 함수(글 고르기) ------------------------------------------------ */

  /** 딱지 글과 모양. kind = ai(점선) | user(초록) | unsure(주황) | wait(알아보는 중 — 딱지 없음).
      text = pre + label — 좁은 자리에서는 앞 글(pre: 'AI 72% · ' 등)을 빼고 종류 이름(label)만 보인다. */
  function badgeInfo(part, th, waiting) {
    var unsure = { kind: 'unsure', text: '? ' + UNSURE, pre: '', label: '? ' + UNSURE };
    if (!part || !part.label) { return waiting ? { kind: 'wait', text: '', pre: '', label: '' } : unsure; }
    if (part.label === UNSURE) { return unsure; }
    var out = { kind: 'ai', pre: '' };
    if (part.src === 'user') { out = { kind: 'user', pre: '✓ ' }; }
    else if (pairChanged(part, th)) { out = { kind: 'ai', pre: 'AI 짝 규칙 · ', pair: true }; }
    else { out.pre = 'AI ' + (pct(part.conf) ? pct(part.conf) + ' · ' : '· '); }
    out.label = part.label;
    out.text = out.pre + part.label;
    return out;
  }

  /** 미니 막대 종류 칸 옆 짧은 글(note)·풍선 말(title)·[맞음] 단추 보임(ok). */
  function partHint(part, th) {
    if (!part || !part.label) {
      return { kind: 'none', note: '', ok: false, title: '그림 종류 — 숫자키 1~9로 고르고 0은 미분류' };
    }
    var p = pct(part.conf);
    if (part.label === UNSURE) {
      var why = (part.src === 'ai' && p) ? 'AI가 잘 모르는 그림(확신 ' + p + ')' : '미분류';
      return { kind: 'unsure', note: '골라 주세요', ok: false, title: why + ' — 숫자키 1~9로 골라 주세요' };
    }
    if (part.src === 'user') {
      return { kind: 'user', note: '확인', ok: false, title: '사람이 확인한 종류 — 다음 AI 학습에 씁니다 · 바꾸려면 숫자키 1~9' };
    }
    var memo = '사람이 고른 비슷한 그림을 따랐어요 — 틀리면 숫자키 1~9, 맞으면 Enter';   // 그림 종류 기억(head '.m')
    if (/\.m$/.test(String(part.head || ''))) { return { kind: 'ai', note: 'AI 기억', ok: true, title: memo }; }
    var pair = pairChanged(part, th);
    var title = 'AI 짐작' + (pair && part.ai ? ' ' + part.ai : '') + (p ? '(확신 ' + p + ')' : '') +
      ' — 틀리면 숫자키 1~9, 맞으면 Enter';
    if (pair) { title += ' · 주방 짝 규칙: 빗금 많은 쪽 = 내부'; }
    return { kind: 'ai', note: pair ? 'AI 짝 규칙' : ('AI ' + p).trim(), ok: true, title: title };
  }

  /** 받침에 맞춘 '로/으로' (ㄹ 받침은 '로'). */
  function withRo(word) {
    var s = String(word || ''), c = s.charCodeAt(s.length - 1) - 0xAC00;
    if (!(c >= 0 && c <= 11171)) { return s + '(으)로'; }
    var fin = c % 28;
    return s + (fin === 0 || fin === 8 ? '로' : '으로');
  }

  /** 여러 장 숫자키 — 고른 객체 중 그림만, 이미 사람이 같은 이름으로 정한 그림은 빼고 바꾼다. */
  function multiLabelPlan(objs, label) {
    var imgs = (objs || []).filter(function (x) { return x && x.type === 'image'; });
    var change = imgs.filter(function (x) {
      return !(x.part && x.part.src === 'user' && x.part.label === label);
    }).map(function (x) { return x.id; });
    return { count: imgs.length, change: change,
      text: imgs.length ? '고른 그림 ' + imgs.length + '장을 ' + withRo(label) + ' 정했어요' : '' };
  }

  /* ---- 화면 ---------------------------------------------------------------- */
  function threshold() { return (opt && opt.threshold) ? opt.threshold() : 0.5; }
  function active() { return !!(opt && layer && (!opt.canSave || opt.canSave())); }
  function waiting() { var St = window.FomsPartStatus; return !!(St && St.waiting()); }
  function objects() { var s = opt.getSheet(); return ((s && s.objects) || []).filter(Boolean); }
  function images() { return objects().filter(function (x) { return x.type === 'image'; }); }
  function rectOf(node) {
    try { return node.getClientRect({ skipShadow: true, skipStroke: true }); } catch (e) { return null; }
  }
  function box(r) { return { x: r.x, y: r.y, w: r.width, h: r.height }; }
  function hit(a, b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }

  /** 다음 그림 틀에 한 번만 다시 그린다(all = 글까지, 아니면 자리만). */
  function schedule(all) {
    if (all) { queued.all = true; }
    if (queued.raf) { return; }
    queued.raf = true;
    var raf = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };
    raf(function () {
      var full = queued.all;
      queued.raf = false;
      queued.all = false;
      if (full) { render(); } else { placeAll(); }
    });
  }

  /** 딱지 자리 고르기 — 그림(잉크)·양식 칸·글자 객체·먼저 놓은 딱지를 덜 가리는 곳(part-badge-spot.js). 없으면 그림 안 왼쪽 위. */
  function placeAll() {
    if (!active() || off) { return; }
    var S = window.FomsPartBadgeSpot, z = (opt.zoom && opt.zoom()) || 1, pics = [], items = [], byId = {};
    var k = (S && S.badgeScale ? S.badgeScale(z) : 1) / z;   // 딱지 화면 px → 스테이지 좌표(100% 아래에서는 딱지도 80% 까지 준다)
    var blocks = ((opt.zones && opt.zones()) || []).slice();
    var todo = Object.keys(badges).filter(function (id) { return !badges[id]._fw; });   // 글이 바뀐(아직 못 잰) 딱지만
    todo.forEach(function (id) { badges[id].className = 'dws-pbadge dws-pbadge-' + badges[id]._kind; });   // 긴 글 모양으로
    todo.forEach(function (id) {   // 읽기를 한데 모아 화면 다시 계산은 한 번
      var el = badges[id];
      el._fw = el.offsetWidth || 0;
      el._sw = el._fw - (el._pre.offsetWidth || 0);
      el._bh = el.offsetHeight || 0;
    });
    var budget = 8, more = false;   // 처음 보는 그림의 잉크는 한 그림 틀에 8장까지만 잰다(큰 시트에서 화면이 굳지 않게)
    objects().forEach(function (o) {
      var node = opt.nodeFor(o.id), r = node ? rectOf(node) : null;
      if (!r) { return; }
      if (o.type === 'text') { blocks.push(box(r)); return; }
      if (o.type !== 'image') { return; }
      var src = (S && node.image && !(node.rotation && node.rotation() % 360)) ? node.image() : null, ink = null;
      if (src && (src._dwsInk !== undefined || budget-- > 0)) { ink = S.inkGrid(src); } else if (src) { more = true; }
      byId[o.id] = { id: o.id, r: box(r), ink: ink };
      pics.push(byId[o.id]);
      var el = badges[o.id], photo = !!(o.part && o.part.label === '사진');   // 사진 딱지는 제 사진 위에 앉아도 된다(치수 없음)
      if (el && el._fw) { items.push({ id: o.id, fw: el._fw * k, sw: el._sw * k, bh: el._bh * k, g: 6 * k, photo: photo }); }
    });
    items.sort(function (a, b) {   // 읽는 순서(위 줄부터, 줄 안에서는 왼쪽부터)로 놓는다 — 먼저 놓은 딱지가 좋은 자리를 갖는다
      var ra = byId[a.id].r, rb = byId[b.id].r;
      return (Math.round(ra.y / 40) - Math.round(rb.y / 40)) || (ra.x - rb.x);
    });
    if (!size) { size = { w: layer.offsetWidth || 1478, h: layer.offsetHeight || 1040 }; }
    var spots = S ? S.place(pics, items, blocks, size) : {}, solo = opt.soloId ? opt.soloId() : null;
    items.forEach(function (it) {
      var el = badges[it.id], r = byId[it.id].r;
      var s = spots[it.id] || { x: Math.round(r.x + it.g), y: Math.round(r.y + it.g), w: it.fw, h: it.bh, short: false };
      el.style.left = s.x + 'px';
      el.style.top = s.y + 'px';
      el._r = s;
      el._sel = it.id === solo;
    });
    dim();
    if (more) { schedule(false); }   // 못 잰 잉크는 다음 그림 틀에
  }

  /** 딱지 모양 줄 — 짧은 글 · 고른 그림 하나(숨김) · 마우스를 올린 그림·하나만 고른 그림(손가락·펜슬) 위에 걸친 딱지(흐림). */
  function dim() {
    var focus = [hover, opt.soloId ? opt.soloId() : null].map(function (id) { return id && opt.nodeFor(id); })
      .map(function (n) { return n && rectOf(n); }).filter(Boolean).map(box);
    Object.keys(badges).forEach(function (id) {
      var el = badges[id], r = el._r, over = !!r && focus.some(function (h) { return hit(r, h); });
      var cls = 'dws-pbadge dws-pbadge-' + el._kind + (r && r.short ? ' dws-pbadge-short' : '') +
        (el._sel ? ' dws-pbadge-sel' : '') + (over ? ' dws-pbadge-dim' : '');
      if (el.className !== cls) { el.className = cls; }
    });
  }

  /** 노드가 움직이거나(끌기·변형·화살표) 그림을 다 불러오면 자리를 다시, 마우스가 오르내리면 흐림만 다시. */
  function watch(node, id) {
    if (node._dwsPb === true) { return; }
    node._dwsPb = true;
    node.on(EVENTS, function () { schedule(false); });
    node.on('mouseenter.dwspb', function () { hover = id; dim(); });
    node.on('mouseleave.dwspb', function () { if (hover === id) { hover = null; dim(); } });
  }

  function makeBadge() {
    var el = layer.appendChild(document.createElement('span'));
    el._pre = el.appendChild(document.createElement('span'));
    el._pre.className = 'dws-pbadge-pre';
    el._label = el.appendChild(document.createElement('span'));
    return el;
  }

  function render() {
    if (!opt || !layer) { return; }
    var show = active(), list = show ? images() : [], th = threshold(), wait = waiting(), keep = {}, n = 0, shown = 0;
    list.forEach(function (obj) {
      var info = badgeInfo(obj.part, th, wait);
      if (info.kind === 'unsure') { n += 1; }
      var node = opt.nodeFor(obj.id);
      if (!node || info.kind === 'wait') { return; }
      var el = badges[obj.id] || (badges[obj.id] = makeBadge());
      if (el._text !== info.text || el._kind !== info.kind) {   // 글이 바뀌면 다시 잰다(placeAll)
        el._pre.textContent = info.pre;
        el._label.textContent = info.label;
        el._text = info.text;
        el._kind = info.kind;
        el._fw = 0;
      }
      watch(node, obj.id);
      keep[obj.id] = true;
      shown += 1;
    });
    Object.keys(badges).forEach(function (id) {
      if (keep[id]) { return; }
      if (badges[id].parentNode) { badges[id].parentNode.removeChild(badges[id]); }
      delete badges[id];
    });
    if (window.FomsPartStatus) { window.FomsPartStatus.paint(n, shown, off); }
    placeAll();
  }

  /** 앱바 딱지 단추 — 딱지를 모두 숨기거나 다시 보인다(이 브라우저에 기억, 저장 못 하면 이 창에서만). */
  function toggleOff() {
    off = !off;
    try { window.localStorage.setItem(OFF_KEY, off ? '1' : '0'); } catch (e) { /* 사생활 보호 모드 등 */ }
    if (layer) { layer.className = 'dws-pbadges dws-ui' + (off ? ' dws-pbadges-off' : ''); }
    schedule(true);
  }

  /** 그림이 캔버스 칸 안에 보이게 스크롤한다(위쪽은 미니 막대 자리를 남긴다). */
  function reveal(node, St) {
    var sc = opt.scroller, r = rectOf(node);
    if (!sc || !r) { return; }
    var hr = opt.host.getBoundingClientRect(), cr = sc.getBoundingClientRect();   // 딱지 층은 숨겨져 있을 수 있다
    var z = (opt.zoom && opt.zoom()) || (hr.width / (opt.host.offsetWidth || 1)) || 1;
    var x0 = hr.left + r.x * z, y0 = hr.top + r.y * z;
    sc.scrollLeft += St.scrollShift(x0, x0 + r.width * z, cr.left + 24, cr.right - 24);
    sc.scrollTop += St.scrollShift(y0, y0 + r.height * z, cr.top + 64, cr.bottom - 24);
  }

  /** '미분류 N장 ›' 칩 — 읽는 순서로 다음 미분류 그림을 고르고 화면에 보이게(part-status.js nextUnsorted). */
  function goNext() {
    var St = window.FomsPartStatus;
    if (!active() || !St) { return; }
    var th = threshold(), wait = waiting(), items = [];
    images().forEach(function (obj) {
      var node = opt.nodeFor(obj.id), r = node ? rectOf(node) : null;
      if (r) { items.push({ id: obj.id, x: r.x, y: r.y, node: node, unsure: badgeInfo(obj.part, th, wait).kind === 'unsure' }); }
    });
    var id = St.nextUnsorted(items, opt.selectedId ? opt.selectedId() : null);
    if (!id) { schedule(true); return; }
    items.forEach(function (it) { if (it.id === id) { reveal(it.node, St); } });
    if (opt.select) { opt.select(id); }
  }

  /**
   * opts: host(줌 배율이 걸린 스테이지) · scroller(캔버스 스크롤 칸) · anchor(칩 묶음을 앞에 둘 요소) ·
   *       getSheet() · nodeFor(id) · threshold() · canSave() · select(id) · selectedId() ·
   *       zoom() · soloId()(하나만 고른 id) · zones()(딱지가 덮지 않을 양식 칸, 스테이지 좌표)
   */
  function init(opts) {
    if (opt) { return true; }
    if (!opts || !opts.host || typeof opts.getSheet !== 'function' || typeof opts.nodeFor !== 'function') { return false; }
    opt = opts;
    try { off = window.localStorage.getItem(OFF_KEY) === '1'; } catch (e) { off = false; }
    layer = document.createElement('div');
    layer.className = 'dws-pbadges dws-ui' + (off ? ' dws-pbadges-off' : '');
    layer.setAttribute('aria-hidden', 'true');
    opts.host.appendChild(layer);
    if (window.FomsPartStatus) {
      window.FomsPartStatus.init(opts.anchor || document.getElementById('dws-save-status'),
        { next: goNext, eye: toggleOff, changed: function () { schedule(true); } });
    }
    if (window.ResizeObserver && opts.host.parentNode) {   // 줌이 바뀌면(스테이지 감싼 칸 크기) 딱지의 스테이지 좌표 크기도 바뀐다
      new window.ResizeObserver(function () { schedule(false); }).observe(opts.host.parentNode);
    }
    schedule(true);
    return true;
  }

  /** 분류 진행 칩(part-status.js) — done >= total 이면 숨긴다(너무 빨리 끝나면 잠깐 'N/N'). opts.loading = 모델을 받는 중. */
  function progress(done, total, opts) {
    var St = window.FomsPartStatus;
    if (St && St.progress(done, total, opts)) { schedule(true); }
  }

  window.FomsPartBadges = {
    init: init, refresh: function () { schedule(true); }, progress: progress,
    badgeInfo: badgeInfo, partHint: partHint, withRo: withRo, multiLabelPlan: multiLabelPlan
  };
})();
