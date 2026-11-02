/**
 * 회사 지식 '뇌 보기' 이름표(설계서 7.6) — WebGL 글자가 아니라 **SVG 겹침**(한글 깨짐 없음), 고른 항목과 이웃만.
 *
 * 자리는 매 장면 바뀌는 3D 투영이라 CSS 만으로는 줄 수 없다. 요소의 인라인 스타일을 만지지 않고(인라인 스타일 규칙 — 화면
 * 시험이 스타일 속성 쓰기를 막는다) SVG 묶음(g)의 transform **속성**을 setAttribute 로 바꾼다. 색은 CSS 클래스(.brain-type--<유형>).
 * 글은 textContent 만. 겹치면 오른쪽 → 왼쪽 → 위 → 아래 → 한 줄씩 비켜 첫 빈자리, 없으면 흐리게 겹쳐 둔다(숨기지 않음).
 * classic 스크립트 — import() 로 읽혀 window.FOMS_BRAIN3D_LABELS.create(svg).
 */
(function (root) {
  'use strict';

  var SVG = 'http://www.w3.org/2000/svg';
  var MAX_LABELS = 40;
  var PAD_X = 6;
  var HEIGHT = 20;

  function create(svg) {
    var entries = [];

    function node(tag, cls) {
      var el = document.createElementNS(SVG, tag);
      if (cls) el.setAttribute('class', cls);
      return el;
    }

    function make(item, main) {
      var g = node('g', 'brain3d-label brain-type--' + item.type + (main ? ' is-main' : ''));
      var box = node('rect', 'brain3d-label__box');
      var dot = node('circle', 'brain3d-label__dot');
      var text = node('text', 'brain3d-label__text');
      text.textContent = item.name;
      text.setAttribute('x', String(PAD_X + 10));
      text.setAttribute('y', '14');
      dot.setAttribute('cx', String(PAD_X + 3));
      dot.setAttribute('cy', '10');
      dot.setAttribute('r', '3.5');
      box.setAttribute('height', String(HEIGHT));
      box.setAttribute('rx', '5');
      g.appendChild(box);
      g.appendChild(dot);
      g.appendChild(text);
      svg.appendChild(g);
      var width = Math.ceil((text.getComputedTextLength ? text.getComputedTextLength() : item.name.length * 12) + PAD_X * 2 + 10);
      box.setAttribute('width', String(width));
      return { idx: item.idx, g: g, main: main, w: width, h: HEIGHT };
    }

    function clear() {
      entries.forEach(function (e) { e.g.remove(); });
      entries = [];
    }

    function spotsFor(e, p) {
      var spots = [[p.x + 9, p.y - e.h / 2], [p.x - 9 - e.w, p.y - e.h / 2], [p.x - e.w / 2, p.y - e.h - 8],
                   [p.x - e.w / 2, p.y + 8]];
      for (var k = 1; k <= 3; k++) {
        var dy = k * (e.h + 3);
        spots.push([p.x + 9, p.y - e.h / 2 + dy], [p.x + 9, p.y - e.h / 2 - dy],
                   [p.x - 9 - e.w, p.y - e.h / 2 + dy], [p.x - 9 - e.w, p.y - e.h / 2 - dy]);
      }
      return e.main ? spots.slice(0, 1) : spots;
    }

    return {
      /** sel = {idx, name, type}, neighbours = 같은 꼴 배열(중복 없이). */
      set: function (sel, neighbours) {
        clear();
        if (!sel) return;
        entries.push(make(sel, true));
        neighbours.slice(0, MAX_LABELS - 1).forEach(function (it) { entries.push(make(it, false)); });
      },
      /** 매 장면 자리 맞추기 — project(idx) → {x, y, depth} | null(카메라 뒤). 가까운 것 · 고른 항목이 먼저 자리를 잡는다. */
      update: function (project) {
        if (!entries.length) return;
        var placed = [];
        var ordered = entries.map(function (e) { return { e: e, p: project(e.idx) }; }).sort(function (a, b) {
          return (b.e.main - a.e.main) || ((a.p ? a.p.depth : 9) - (b.p ? b.p.depth : 9));
        });
        ordered.forEach(function (o) {
          var e = o.e;
          if (!o.p) { e.g.classList.add('is-hidden'); return; }
          var pick = null;
          spotsFor(e, o.p).some(function (s) {
            var box = { x0: s[0], y0: s[1], x1: s[0] + e.w, y1: s[1] + e.h };
            var free = e.main || !placed.some(function (b) {
              return box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0;
            });
            if (free) pick = box;
            return free;
          });
          e.g.classList.toggle('is-crowded', !pick);
          e.g.classList.remove('is-hidden');
          if (pick) placed.push(pick);
          else pick = { x0: o.p.x + 9, y0: o.p.y - e.h / 2 };
          e.g.setAttribute('transform', 'translate(' + Math.round(pick.x0) + ' ' + Math.round(pick.y0) + ')');
        });
      },
      clear: clear,
      count: function () { return entries.length; }
    };
  }

  root.FOMS_BRAIN3D_LABELS = { create: create };
})(typeof window !== 'undefined' ? window : globalThis);
