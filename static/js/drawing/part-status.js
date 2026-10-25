/**
 * 도면 마법사 — 앱바 그림 종류 칩 묶음(#dws-part-status): 분류 진행 칩 · '미분류 N장 ›' · 딱지 숨기기 단추.
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.1 · 사용성 평가(2026-10-25) 큼-7·큼-8
 * 사용성 재평가(2026-10-25 QA1·QA2·QA3):
 * - 진행 칩 'n/N' 이 한 번도 보이지 않았다 — 분류가 쉬지 않고 이어 돌아 화면을 그릴 틈이 없었다(part-ai.js 가 한 장씩
 *   사이사이 화면을 그리게 고침). 칩은 너무 빨리 끝나도 0.8초는 보여 준다(끝난 뒤에는 'N/N').
 * - 모델 단계에도 장수를 붙인다('모델 받는 중 0/8'). 모델이 이미 이 브라우저에 있으면 '모델 받는 중'을 띄우지 않는다
 *   (wizard.js partProgress 가 loading 을 고른다).
 * - 칩 폭 상한(wizard.css --dws-busy-max)에서 글이 '그림 종…'으로 잘리면 짧은 글('분류 중')로 바꾼다. 장수는 늘 보인다.
 *   칩·앱바 폭이 바뀌면 다시 맞춘다(ResizeObserver — V1). 모델이 있는지 아직 모르면 글 없이 장수만(loading null).
 * - 딱지가 그림을 가릴 때 한 번에 숨기는 단추(딱지 모양, 숨긴 동안은 빗금) — 숨김 기억은 part-badges.js.
 * 마지막 실화면 확인(2026-10-25 V1): 칩이 뜨고 질 때마다 앱바 단추가 옆으로 밀렸다 → 칩 묶음(#dws-part-status)은 템플릿에
 *   두고 wizard.css 가 폭을 늘 잡아 둔다('미분류'·딱지 단추). '알아보는 중' 칩은 앱바 아래에 떠서 보여 앱바 자리를 안 쓴다.
 *   그래서 묶음 안 순서는 [알아보는 중(떠 있음)] [미분류] [딱지 단추] 그대로 두고 보이고 숨기기만 한다.
 *
 * window.FomsPartStatus = { init(anchor, on), progress(done, total, opts), waiting(), paint(unsure, badges, off),
 *   progressParts(done, total, loading, keep), progressText(done, total, loading), unsureText(n),
 *   nextUnsorted(items, currentId), scrollShift(a, b, lo, hi) }
 *   on: { next() — '미분류' 칩을 누름, eye() — 딱지 숨기기 단추를 누름, changed() — 잠깐 보여 주기가 끝나 다시 그릴 때 }
 *   (node 로 시험한다 — tests/domains/test_drawing_part_badges.py)
 */
(function () {
  'use strict';
  if (window.FomsPartStatus) { return; }

  var MIN_SHOW = 800;   // 진행 칩을 적어도 이만큼(ms)은 보인다 — 0.3초 깜빡임은 읽을 수 없다
  var ROW = 80;         // 다음 미분류 고르기: 위쪽 끝이 80px 안이면 같은 줄로 본다
  var SVG_NS = 'http://www.w3.org/2000/svg';
  // 딱지 모양 그림(숨긴 동안은 빗금 — wizard.css .dws-part-eye-slash). 고정 그림이라 요소로 만든다(innerHTML 안 씀).
  var TAG = [['svg', { viewBox: '0 0 24 24', width: '15', height: '15', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7',
    'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' }],
    ['path', { d: 'M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z' }], ['circle', { cx: '7.5', cy: '7.5', r: '1.4' }],
    ['line', { 'class': 'dws-part-eye-slash', x1: '3', y1: '21', x2: '21', y2: '3' }]];
  var IDLE = { done: 0, total: 0, loading: false, keep: false, since: 0 };

  var chips = null, on = {}, timer = null, busy = IDLE;

  function count(v) { return (typeof v === 'number' && isFinite(v)) ? Math.max(0, Math.floor(v)) : 0; }

  /** 진행 칩 글 — 넓은 글 · 좁은 앱바용 짧은 글 · 장수('3/8') · 풍선 말. 다 알아봤으면 null(keep = 끝난 뒤 잠깐 'N/N').
      loading = true(모델 받는 중) | false(알아보는 중) | null(모델이 이 브라우저에 있는지 아직 모름 — 글 없이 장수만:
      V1 첫 올림에서 '그림 종류 알아보는 중 0/2' 가 0.1초 뒤 '모델 받는 중 0/5' 로 바뀌며 깜빡였다). */
  function progressParts(done, total, loading, keep) {
    if (!(total > 0) || (done >= total && !keep)) { return null; }
    var n = Math.min(done, total) + '/' + total;
    if (loading === null) { return { text: '', short: '', count: n, title: '그림 종류 ' + n }; }
    var text = loading ? '모델 받는 중' : '그림 종류 알아보는 중';
    return { text: text, short: loading ? '모델 받는 중' : '분류 중', count: n,
      title: text + ' ' + n + (loading ? ' — 처음 한 번만 받아요' : '') };
  }

  function progressText(done, total, loading) {
    var p = progressParts(done, total, loading, false);
    return p ? p.text + ' ' + p.count : '';
  }

  function unsureText(n) { return n > 0 ? '미분류 ' + n + '장 ›' : ''; }

  function num(v) { return (typeof v === 'number' && isFinite(v)) ? v : 0; }

  /** '미분류' 칩 — 다음에 볼 미분류 그림 id: 읽는 순서(위 줄부터, 줄 안에서는 왼쪽부터)로 지금 그림 다음, 끝이면 처음으로. */
  function nextUnsorted(items, currentId) {
    var list = (items || []).slice().sort(function (a, b) {
      var ra = Math.round(num(a.y) / ROW), rb = Math.round(num(b.y) / ROW);
      return (ra - rb) || (num(a.x) - num(b.x)) || (num(a.y) - num(b.y));
    });
    var start = -1;
    for (var i = 0; i < list.length; i++) { if (list[i].id === currentId) { start = i; break; } }
    for (var k = 1; k <= list.length; k++) {
      var it = list[(start + k) % list.length];
      if (it.unsure) { return it.id; }
    }
    return null;
  }

  /** 화면 칸 [lo, hi] 안에 [a, b] 가 들어오게 옮길 거리 — 이미 보이면 0, 칸보다 크면 앞쪽 끝을 맞춘다. */
  function scrollShift(a, b, lo, hi) {
    if (a >= lo && b <= hi) { return 0; }
    if (a < lo || b - a > hi - lo) { return a - lo; }
    return b - hi;
  }

  /** 알아보는 중인가(이름표 없는 그림을 '미분류'로 세지 않고 딱지 없이 둔다). */
  function waiting() { return busy.total > 0 && busy.done < busy.total; }

  /** 진행 상태를 바꾼다 — done >= total 이면 숨기되, 뜬 지 0.8초가 안 됐으면 'N/N' 으로 남은 시간만 더 둔다. 바뀌면 true. */
  function progress(done, total, opts) {
    var d = count(done), t = count(total), now = Date.now();
    if (t > 0 && d < t) {
      clearTimeout(timer);
      var ld = (opts && opts.loading === null) ? null : !!(opts && opts.loading);
      busy = { done: d, total: t, loading: ld, keep: false, since: busy.total > 0 ? busy.since : now };
      return true;
    }
    if (!(busy.total > 0) || busy.keep) { return false; }
    var left = MIN_SHOW - (now - busy.since);
    if (!(left > 0)) { busy = IDLE; return true; }
    busy = { done: busy.total, total: busy.total, loading: false, keep: true, since: busy.since };
    timer = setTimeout(function () {
      busy = IDLE;
      if (on.changed) { on.changed(); }
    }, left);
    return true;
  }

  function el(tag, cls) {
    var e = document.createElement(tag);
    e.className = cls;
    return e;
  }

  function set(node, text) { if (node.textContent !== text) { node.textContent = text; } }

  /** 딱지 숨기기 단추 그림 — 첫 칸이 svg, 나머지는 그 안의 선. */
  function tagIcon() {
    var svg = null;
    TAG.forEach(function (t) {
      var e = document.createElementNS(SVG_NS, t[0]);
      Object.keys(t[1]).forEach(function (k) { e.setAttribute(k, t[1][k]); });
      if (svg) { svg.appendChild(e); } else { svg = e; }
    });
    return svg;
  }

  /** 칩 묶음을 만든다(템플릿에 없으면 anchor 바로 앞에). on 은 매번 바꿀 수 있다. */
  function init(anchor, handlers) {
    on = handlers || {};
    if (chips) { return chips; }
    var box = document.getElementById('dws-part-status');
    if (!box) {
      if (!anchor || !anchor.parentNode) { return null; }
      box = el('span', 'dws-part-status');
      box.id = 'dws-part-status';
      anchor.parentNode.insertBefore(box, anchor);
    }
    var busyEl = el('span', 'dws-part-status-chip dws-part-status-busy');
    // 글과 '3/8' 을 따로 담는다 — 좁은 앱바에서 글만 말줄임(또는 짧은 글)되고 장수는 늘 보이게
    var text = busyEl.appendChild(el('span', 'dws-part-status-busy-text'));
    var num = busyEl.appendChild(el('span', 'dws-part-status-busy-count'));
    var unsure = el('button', 'dws-part-status-chip dws-part-status-unsure');
    unsure.type = 'button';
    unsure.title = '다음 미분류 그림으로 — 숫자키 1~9로 종류를 고르세요';
    unsure.addEventListener('click', function () { if (on.next) { on.next(); } });
    var eye = el('button', 'dws-part-status-chip dws-part-status-eye');
    eye.type = 'button';
    if (document.createElementNS) { eye.appendChild(tagIcon()); }
    eye.addEventListener('click', function () { if (on.eye) { on.eye(); } });
    [busyEl, unsure, eye].forEach(function (x) { x.hidden = true; box.appendChild(x); });
    box.hidden = true;
    chips = { box: box, busy: busyEl, text: text, count: num, unsure: unsure, eye: eye };
    watchWidth(busyEl, box.closest ? box.closest('.dws-appbar') : null);
    return chips;
  }

  /** 칩·앱바 폭이 바뀌면(창 크기·옆 칩) 다음 그림 틀에 칩 글을 다시 맞춘다 — V1: 넓은 글을 보이던 중 칩이 좁아지자
      다음 진행 칸까지 '그림 종… 0/4' 로 잘린 채 남았다(모델을 처음 받거나 분류가 느리면 오래). */
  function watchWidth(chip, bar) {
    var raf = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); }, queued = false;
    var again = function () {
      if (queued) { return; }
      queued = true;
      raf(function () { queued = false; fit(); });
    };
    if (window.ResizeObserver) {
      var ro = new window.ResizeObserver(again);
      ro.observe(chip);
      if (bar) { ro.observe(bar); }
    } else if (window.addEventListener) {
      window.addEventListener('resize', again);
    }
  }

  /** 칩 글 맞추기 — 넓은 글부터 대 보고 잘리면 짧은 글('분류 중'). 장수 칸은 이 묶음에서 가장 넓은 꼴('N/N')로 놓고 재
      (9/19 → 10/19 처럼 자리수가 늘 때 글이 중간에 바뀌지 않게) 진짜 장수로 돌린다. 장수만 보일 때(글 없음)는 그대로. */
  function fit() {
    var c = chips, p = c && !c.busy.hidden && progressParts(busy.done, busy.total, busy.loading, busy.keep);
    if (!p || !p.text) { return; }
    set(c.count, ' ' + busy.total + '/' + busy.total);
    set(c.text, p.text);
    if (c.text.scrollWidth > c.text.clientWidth + 1) { set(c.text, p.short); }
    set(c.count, ' ' + p.count);
  }

  /** 칩을 그린다 — unsure: 미분류 장수 · badges: 지금 보이는(숨기기 전) 딱지 수(0 이면 숨기기 단추도 숨김) · off: 딱지를 숨겼나. */
  function paint(unsureN, badges, off) {
    var c = chips;
    if (!c) { return; }
    var u = unsureText(unsureN), p = progressParts(busy.done, busy.total, busy.loading, busy.keep);
    var label = off ? '그림 종류 딱지 다시 보이기' : '그림 종류 딱지 숨기기 — 딱지가 치수를 가릴 때';
    set(c.unsure, u);
    c.unsure.hidden = !u;
    c.busy.hidden = !p;
    c.busy.title = p ? p.title : '';   // 말줄임·짧은 글이어도 마우스를 올리면 전체 글
    c.count.hidden = !p;
    c.eye.hidden = !(badges > 0);
    c.eye.title = label;
    c.eye.setAttribute('aria-label', label);
    c.eye.setAttribute('aria-pressed', off ? 'true' : 'false');
    c.box.hidden = !u && !p && c.eye.hidden;
    if (!p) { return; }
    c.text.hidden = !p.text;   // 모델이 있는지 아직 모르면 글 없이 장수만
    if (!p.text) { set(c.text, ''); set(c.count, p.count); return; }
    fit();   // 좁은 칩에서 글이 잘리면('그림 종…') 짧은 글로 — 칩이 보이게 한 뒤에 잰다
  }

  window.FomsPartStatus = {
    init: init, progress: progress, waiting: waiting, paint: paint,
    progressParts: progressParts, progressText: progressText, unsureText: unsureText,
    nextUnsorted: nextUnsorted, scrollShift: scrollShift
  };
})();
