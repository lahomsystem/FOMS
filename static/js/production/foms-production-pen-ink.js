/* 생산 도면 펜 기록 — 펜 입력 → 기록 · SVG 그리기 · 되돌리기 · 다시 하기 · 지우개 · 텍스트 · 화살표 · 투명 PNG 뽑기.
 * 설계서 docs/specs/2026-11-28-production-pen-record_SPEC.md §3-2 · §3-3(1번) · §6-3 · §7(Konva 안 씀 — 가벼운 SVG, 사장님 승인 시안과 같은 꼴).
 * 보기 JS(foms-production-parts-viewer.js)가 [기록 쓰기]를 처음 누를 때 받고, 쓰는 상태 JS(foms-production-pen.js)가 create() 로 한 판씩 만든다.
 * 펜 · 마우스 = 쓰기, 손가락(pointerType touch) = 움직이기 · 키우기(foms-production-parts-zoom.js 몫 — 14번 답 "펜으로만").
 * 좌표 = 가로 1478 기준(세로는 그림 비율). rect · clientX 는 보이는 px 라 쓰는 층 rect 와의 비로 바꾼다(화면 크기 배율 · 확대와 상관없다).
 * 층 자리 = 그림의 배치 크기(offset* — 배율 전 CSS px), 확대 transform 은 zoom 파일이 그림과 같이 붙인다. 지우개 = 댄 것 하나 통째로(굵은 투명 선).
 * 한 개의 꼴(서버 약속 §3-2): pen {type, points, stroke, strokeWidth, opacity?(형광펜 0.4)} · arrow {type, points 넷, stroke, strokeWidth} ·
 * text {type, x, y, text(40자), fill, fontSize}. 받는 값 한도를 여기서도 지킨다: 색 넷 · 굵기 넷 · 300개 · 한 선 값 2,000(넘으면 이어서 새 선).
 * PNG 는 화면 밖 캔버스에 펜 기록만 그린다(도면 그림을 안 그려 캔버스가 잠기지 않는다 — 서버가 원본 위에 얹는다). */
(function () {
  'use strict';
  if (window.FomsPenInk) { return; }

  var NS = 'http://www.w3.org/2000/svg';
  var BASE_W = 1478;
  var COLORS = ['#e11d1d', '#1c62d6', '#000000'];
  var WIDTHS = [3, 5, 9];
  var MARKER = { stroke: '#ffd400', strokeWidth: 24, opacity: 0.4 };
  var TOOLS = ['pen', 'marker', 'text', 'arrow', 'erase'];
  var MAX_OBJS = 300;
  var MAX_NUMS = 2000; // 한 선의 points 값 개수 — 서버 한도(한 선 2,000점) 안에서 끊고 이어서 새 선
  var MAX_TEXT = 40;
  var FONT = 38;
  var FAMILY = 'sans-serif';
  var MAX_PNG = 2956;
  var HIST = 50;

  function r1(v) { return Math.round(v * 10) / 10; }
  function clone(v) { return JSON.parse(JSON.stringify(v)); }
  function uiZoom() { var z = typeof window.fomsUiZoom === 'function' ? Number(window.fomsUiZoom()) || 1 : 1; return z > 0 ? z : 1; }
  function svgEl(tag, attrs) {
    var n = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { n.setAttribute(k, String(attrs[k])); });
    return n;
  }
  function pairs(pts) {
    var out = [];
    for (var i = 0; i + 1 < pts.length; i += 2) { out.push(pts[i] + ',' + pts[i + 1]); }
    return out.join(' ');
  }
  function headPts(p, w) { // 화살촉 세 점(끝점 + 양 날개)
    var a = Math.atan2(p[3] - p[1], p[2] - p[0]);
    var n = 12 + w * 3;
    return [p[2], p[3], r1(p[2] - n * Math.cos(a - 0.45)), r1(p[3] - n * Math.sin(a - 0.45)), r1(p[2] - n * Math.cos(a + 0.45)), r1(p[3] - n * Math.sin(a + 0.45))];
  }
  function valid(o) { // 받은 기록(GET) 중 그릴 수 있는 꼴만(값 한도는 서버가 이미 본 것)
    if (!o || typeof o !== 'object') { return false; }
    if (o.type === 'text') { return typeof o.text === 'string' && isFinite(o.x) && isFinite(o.y); }
    return (o.type === 'pen' || o.type === 'arrow') && Array.isArray(o.points) && o.points.length >= 4;
  }
  function trace(g, pts, k) { // 캔버스 길 — 화면 SVG 와 같은 점
    g.beginPath();
    for (var i = 0; i + 1 < pts.length; i += 2) { g[i ? 'lineTo' : 'moveTo'](pts[i] * k, pts[i + 1] * k); }
  }
  function stroke2d(g, o, k) { // 투명 PNG 한 개
    g.save();
    g.globalAlpha = o.opacity || 1;
    if (o.type === 'text') {
      g.fillStyle = o.fill;
      g.font = '700 ' + (o.fontSize * k) + 'px ' + FAMILY;
      g.fillText(o.text, o.x * k, o.y * k);
    } else {
      g.strokeStyle = o.stroke;
      g.lineWidth = o.strokeWidth * k;
      g.lineCap = 'round';
      g.lineJoin = 'round';
      trace(g, o.points, k);
      g.stroke();
      if (o.type === 'arrow') { g.fillStyle = o.stroke; trace(g, headPts(o.points, o.strokeWidth), k); g.closePath(); g.fill(); }
    }
    g.restore();
  }

  function create(opts) {
    var stage = opts.stage;
    var img = opts.img;
    var text = opts.text || null;
    var s = { objs: [], saved: '[]', hist: [], redo: [], tool: 'pen', color: COLORS[0], width: 5, enabled: false, dead: false,
      active: null, svg: null, lastG: null, base: { w: BASE_W, h: Math.round(BASE_W * 0.7) }, natural: { w: BASE_W, h: 0 }, textAt: null };
    function changed() { if (opts.onChange) { opts.onChange(); } }

    // ── 그리기 ──
    function draw(o, i) {
      var g = svgEl('g', { 'data-pp-o': i });
      if (o.type === 'text') {
        var t = g.appendChild(svgEl('text', { x: o.x, y: o.y, fill: o.fill, 'font-size': o.fontSize, 'font-weight': 700, 'font-family': FAMILY }));
        t.textContent = o.text;
        return g;
      }
      var str = pairs(o.points);
      g.appendChild(svgEl('polyline', { points: str, fill: 'none', stroke: 'transparent', 'stroke-width': Math.max(30, o.strokeWidth + 16), 'pointer-events': 'stroke' }));
      var line = g.appendChild(svgEl('polyline', { points: str, fill: 'none', stroke: o.stroke, 'stroke-width': o.strokeWidth, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'pointer-events': 'none' }));
      if (o.opacity) { line.setAttribute('opacity', String(o.opacity)); }
      if (o.type === 'arrow') { g.appendChild(svgEl('polygon', { points: pairs(headPts(o.points, o.strokeWidth)), fill: o.stroke, 'pointer-events': 'none' })); }
      return g;
    }
    function paint() {
      if (!s.svg) { return; }
      s.svg.textContent = '';
      s.lastG = null;
      s.objs.forEach(function (o, i) { s.lastG = s.svg.appendChild(draw(o, i)); });
      changed();
    }
    function fit() { // 쓰는 층 = 그림과 같은 배치 자리 · 같은 확대
      if (!s.svg || !s.svg.style) { return; }
      var st = s.svg.style;
      st.left = img.offsetLeft + 'px';
      st.top = img.offsetTop + 'px';
      st.width = img.offsetWidth + 'px';
      st.height = img.offsetHeight + 'px';
      st.transform = (img.style && img.style.transform) || '';
    }
    function pt(e) {
      var r = s.svg.getBoundingClientRect();
      var x = (e.clientX - r.left) / (r.width || 1) * s.base.w;
      var y = (e.clientY - r.top) / (r.height || 1) * s.base.h;
      return [r1(Math.max(0, Math.min(s.base.w, x))), r1(Math.max(0, Math.min(s.base.h, y)))];
    }
    function push() { s.hist.push(JSON.stringify(s.objs)); if (s.hist.length > HIST) { s.hist.shift(); } s.redo = []; }
    function full() { if (s.objs.length < MAX_OBJS) { return false; } if (opts.onLimit) { opts.onLimit(); } return true; }

    // ── 텍스트 — 누른 자리에 글 칸(보기 창 안 자리 = 보이는 px ÷ 화면 크기 배율), Enter 로 놓는다(40자) ──
    function openText(a) {
      if (!text) { return; }
      s.textAt = a.at;
      text.value = '';
      text.hidden = false;
      text.style.left = Math.max(8, a.x / uiZoom() - 12) + 'px';
      text.style.top = Math.max(60, a.y / uiZoom() - 20) + 'px';
      text.style.color = s.color;
      text.focus();
    }
    function commitText() {
      if (!text || text.hidden) { return; }
      var v = String(text.value || '').trim().slice(0, MAX_TEXT);
      var at = s.textAt;
      text.hidden = true;
      text.value = '';
      s.textAt = null;
      if (!v || !at || full()) { return; }
      push();
      s.objs.push({ type: 'text', x: at[0], y: at[1], text: v, fill: s.color, fontSize: FONT });
      paint();
    }

    // ── 펜 입력 ──
    function erase(e) {
      var hit = typeof document.elementFromPoint === 'function' ? document.elementFromPoint(e.clientX, e.clientY) : null;
      var g = hit && typeof hit.closest === 'function' ? hit.closest('[data-pp-o]') : null;
      if (!g || !s.svg.contains(g)) { return; }
      if (!s.active.pushed) { push(); s.active.pushed = true; }
      s.objs.splice(Number(g.getAttribute('data-pp-o')), 1);
      paint();
    }
    function startObj(p) {
      if (s.tool === 'arrow') { return { type: 'arrow', points: [p[0], p[1], p[0], p[1]], stroke: s.color, strokeWidth: s.width }; }
      if (s.tool === 'marker') { return { type: 'pen', points: [p[0], p[1]], stroke: MARKER.stroke, strokeWidth: MARKER.strokeWidth, opacity: MARKER.opacity }; }
      return { type: 'pen', points: [p[0], p[1]], stroke: s.color, strokeWidth: s.width };
    }
    function down(e) {
      if (s.dead || !s.enabled || !s.svg || e.pointerType === 'touch' || s.active || e.button > 0) { return; } // 손가락은 zoom 파일 몫
      e.preventDefault(); // 호환 mouse 사건(확대 파일의 끌기) · 초점 옮김을 막는다
      commitText();
      try { if (stage.setPointerCapture) { stage.setPointerCapture(e.pointerId); } } catch (err) { /* 잡기를 못 해도 쓰기는 된다 */ }
      var p = pt(e);
      s.active = { id: e.pointerId, tool: s.tool, pushed: false, at: p, x: e.clientX, y: e.clientY };
      if (s.tool === 'text') { return; }
      if (s.tool === 'erase') { erase(e); return; }
      if (full()) { s.active = null; return; }
      push();
      s.active.obj = startObj(p);
      s.objs.push(s.active.obj);
      paint();
      s.active.g = s.lastG;
    }
    function addPoint(a, p) {
      var pts = a.obj.points;
      var n = pts.length;
      if (Math.abs(p[0] - pts[n - 2]) + Math.abs(p[1] - pts[n - 1]) < 2) { return false; }
      if (n + 2 > MAX_NUMS) { // 한 선 한도 — 마지막 점에서 이어 새 선(같은 모양), 300개면 멈춘다
        if (s.objs.length >= MAX_OBJS) { return false; }
        a.obj = clone(a.obj);
        a.obj.points = [pts[n - 2], pts[n - 1]];
        s.objs.push(a.obj);
        paint();
        a.g = s.lastG;
      }
      a.obj.points.push(p[0], p[1]);
      return true;
    }
    function move(e) {
      var a = s.active;
      if (!a || a.id !== e.pointerId) { return; }
      e.preventDefault();
      if (a.tool === 'erase') { erase(e); return; }
      if (!a.obj) { return; }
      if (a.obj.type === 'arrow') {
        var q = pt(e);
        a.obj.points[2] = q[0];
        a.obj.points[3] = q[1];
        paint();
        return;
      }
      var list = typeof e.getCoalescedEvents === 'function' ? e.getCoalescedEvents() : [];
      var grew = false;
      (list.length ? list : [e]).forEach(function (ev) { grew = addPoint(a, pt(ev)) || grew; });
      if (!grew || !a.g) { return; }
      var str = pairs(a.obj.points);
      [].slice.call(a.g.querySelectorAll('polyline')).forEach(function (l) { l.setAttribute('points', str); });
    }
    function up(e) {
      var a = s.active;
      if (!a || a.id !== e.pointerId) { return; }
      s.active = null;
      if (a.tool === 'text') { if (e.type === 'pointerup') { openText(a); } return; }
      var o = a.obj;
      if (o && o.type === 'pen' && o.points.length === 2) { o.points.push(r1(o.points[0] + 0.5), r1(o.points[1] + 0.5)); } // 콕 찍은 점
      if (o && o.type === 'arrow' && Math.abs(o.points[2] - o.points[0]) + Math.abs(o.points[3] - o.points[1]) < 16) {
        s.objs = JSON.parse(s.hist.pop() || '[]'); // 너무 짧은 화살표는 버린다
      }
      paint();
    }
    var handlers = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: up };
    Object.keys(handlers).forEach(function (k) { stage.addEventListener(k, handlers[k]); });

    // ── 밖으로 ──
    function whenLoaded(cb) {
      if (img.complete && img.naturalWidth) { cb(); return; }
      var once = false;
      img.addEventListener('load', function () { if (!once) { once = true; cb(); } });
    }
    // 받은 기록을 얹고 쓰는 층을 만든다(그림이 뜬 뒤). note = 서버 기록({base_w, base_h} — 없으면 가로 1478 · 그림 비율)
    function mount(list, note) {
      return new Promise(function (resolve) {
        whenLoaded(function () {
          if (s.dead) { resolve(false); return; }
          s.natural = { w: img.naturalWidth || BASE_W, h: img.naturalHeight || Math.round(BASE_W * 0.7) };
          var bw = note && Number(note.base_w);
          var bh = note && Number(note.base_h);
          s.base = bw > 0 && bh > 0 ? { w: bw, h: bh } : { w: BASE_W, h: Math.round(BASE_W * s.natural.h / s.natural.w) };
          s.objs = (Array.isArray(list) ? list : []).filter(valid).map(clone);
          s.saved = JSON.stringify(s.objs);
          s.hist = [];
          s.redo = [];
          s.svg = svgEl('svg', { 'class': 'pp-ink', 'data-pp-ink': '', viewBox: '0 0 ' + s.base.w + ' ' + s.base.h, preserveAspectRatio: 'none', 'aria-hidden': 'true', focusable: 'false' });
          stage.appendChild(s.svg);
          fit();
          paint();
          resolve(true);
        });
      });
    }
    // 긴 변 = 원본 긴 변(최대 2,956px), 비율 = 좌표 기준 크기. 못 만들면 null
    function toPng() {
      return new Promise(function (resolve) {
        var long = Math.min(Math.max(s.natural.w, s.natural.h), MAX_PNG);
        var wide = s.base.w >= s.base.h;
        var c = document.createElement('canvas');
        c.width = wide ? long : Math.round(long * s.base.w / s.base.h);
        c.height = wide ? Math.round(long * s.base.h / s.base.w) : long;
        var g = c.getContext ? c.getContext('2d') : null;
        if (!g || typeof c.toBlob !== 'function') { resolve(null); return; }
        s.objs.forEach(function (o) { stroke2d(g, o, c.width / s.base.w); });
        try { c.toBlob(function (blob) { resolve(blob || null); }, 'image/png'); } catch (err) { resolve(null); }
      });
    }
    function undo() { if (!s.hist.length || s.active) { return; } s.redo.push(JSON.stringify(s.objs)); s.objs = JSON.parse(s.hist.pop()); paint(); }
    function redo() { if (!s.redo.length || s.active) { return; } s.hist.push(JSON.stringify(s.objs)); s.objs = JSON.parse(s.redo.pop()); paint(); }
    function destroy() {
      s.dead = true;
      s.active = null;
      if (text) { text.hidden = true; text.value = ''; }
      Object.keys(handlers).forEach(function (k) { stage.removeEventListener(k, handlers[k]); });
      if (s.svg && s.svg.parentNode) { s.svg.parentNode.removeChild(s.svg); }
      s.svg = null;
    }
    return {
      mount: mount, fit: fit, toPng: toPng, undo: undo, redo: redo, destroy: destroy, commitText: commitText,
      dropText: function () { if (text) { text.value = ''; } commitText(); },
      enable: function (yes) { s.enabled = !!yes; },
      set: function (k, v) { if ((k === 'tool' && TOOLS.indexOf(v) >= 0) || (k === 'color' && COLORS.indexOf(v) >= 0) || (k === 'width' && WIDTHS.indexOf(v) >= 0)) { commitText(); s[k] = v; } },
      get: function (k) { return s[k]; },
      canUndo: function () { return s.hist.length > 0; },
      canRedo: function () { return s.redo.length > 0; },
      dirty: function () { return JSON.stringify(s.objs) !== s.saved; },
      objects: function () { return clone(s.objs); },
      base: function () { return { w: s.base.w, h: s.base.h }; },
      inking: function () { return !!s.active; }
    };
  }

  window.FomsPenInk = { create: create, COLORS: COLORS, WIDTHS: WIDTHS, BASE_W: BASE_W, MAX_OBJS: MAX_OBJS, MAX_NUMS: MAX_NUMS };
})();
