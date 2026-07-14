/*
 * FOMS 실측 "오늘 동선" — 히어로 방문 카운트다운 + 지도 동선 스트립.
 * v2(mobile_list.html)·v3(persona_home_sales.html) 공용. additive·vanilla·defer.
 * SVG는 JS 렌더(서버 마크업 = 빈 컨테이너 1개). 색/획은 CSS 클래스가 소유.
 */
(function () {
  'use strict';
  if (window.__FOMS_ROUTE_STRIP_BOUND) return;
  window.__FOMS_ROUTE_STRIP_BOUND = true;

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var VIEW_W = 320, VIEW_H = 140, PAD = 20;

  // ---------- 방문 카운트다운 ----------
  function minutesOfDay(hm) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(String(hm || '').trim());
    if (!m) return null;
    var h = parseInt(m[1], 10), mm = parseInt(m[2], 10);
    if (h > 23 || mm > 59) return null;
    return h * 60 + mm;
  }

  function paintCountdown(el) {
    var target = minutesOfDay(el.getAttribute('data-foms-visit-time'));
    if (target === null) return;
    var now = new Date();
    var diff = target - (now.getHours() * 60 + now.getMinutes());
    el.classList.remove('is-soon', 'is-passed');
    if (diff < 0) { el.textContent = '방문 시간 지남'; el.classList.add('is-passed'); }
    else if (diff === 0) { el.textContent = '지금 출발'; el.classList.add('is-soon'); }
    else if (diff < 60) { el.textContent = diff + '분 후 출발'; el.classList.add('is-soon'); }
    else { el.textContent = el.getAttribute('data-foms-visit-time') + ' 방문'; }
  }

  function initCountdowns() {
    var els = document.querySelectorAll('[data-foms-visit-time]');
    if (!els.length) return;
    var tick = function () { Array.prototype.forEach.call(els, paintCountdown); };
    tick();
    setInterval(tick, 60000);
  }

  // ---------- 지도 동선 스트립 ----------
  function el(tag, attrs, text) {
    var node = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) { if (attrs.hasOwnProperty(k)) node.setAttribute(k, attrs[k]); }
    if (text != null) node.textContent = text;
    return node;
  }

  function normalize(points) {
    var lats = points.map(function (p) { return p.lat; });
    var lngs = points.map(function (p) { return p.lng; });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats);
    var minLng = Math.min.apply(null, lngs), maxLng = Math.max.apply(null, lngs);
    var spanLat = maxLat - minLat, spanLng = maxLng - minLng;
    var w = VIEW_W - PAD * 2, h = VIEW_H - PAD * 2;
    return points.map(function (p) {
      var fx = spanLng ? (p.lng - minLng) / spanLng : 0.5;
      var fy = spanLat ? (p.lat - minLat) / spanLat : 0.5;
      return { x: PAD + fx * w, y: PAD + (1 - fy) * h };  // 위도 반전(북쪽=위)
    });
  }

  function regionOf(addr) {
    var tokens = String(addr || '').trim().split(/\s+/);
    var head = tokens.slice(0, 3);
    var i;
    for (i = 0; i < head.length; i++) {
      if (/(구|군)$/.test(head[i]) && head[i].length > 1) return head[i].replace(/(구|군)$/, '');
    }
    for (i = 0; i < head.length; i++) {
      if (/시$/.test(head[i]) && !/(특별시|광역시)$/.test(head[i]) && head[i].length > 1) {
        return head[i].replace(/시$/, '');
      }
    }
    return tokens.slice(0, 2).join(' ');
  }

  function renderSvg(pts, coords, currentIdx) {
    var svg = el('svg', {
      viewBox: '0 0 ' + VIEW_W + ' ' + VIEW_H,
      class: 'foms-route-strip__svg', role: 'img',
      'aria-label': '오늘 실측 방문 순서 지도'
    });
    var i;
    for (i = 0; i < coords.length - 1; i++) {
      var dashed = currentIdx !== -1 && i >= currentIdx;
      svg.appendChild(el('line', {
        x1: coords[i].x, y1: coords[i].y, x2: coords[i + 1].x, y2: coords[i + 1].y,
        class: 'foms-route-seg' + (dashed ? ' foms-route-seg--dashed' : '')
      }));
    }
    for (i = 0; i < coords.length; i++) {
      var isCurrent = i === currentIdx;
      var done = !!pts[i].measurement_completed;
      var mod = isCurrent ? '--current' : (done ? '--done' : '--upcoming');
      var g = el('g', { class: 'foms-route-node foms-route-node' + mod });
      g.appendChild(el('circle', {
        cx: coords[i].x, cy: coords[i].y, r: isCurrent ? 11 : 8, class: 'foms-route-node__dot'
      }));
      var glyph = (done && !isCurrent) ? '✓' : String(i + 1);
      g.appendChild(el('text', {
        x: coords[i].x, y: coords[i].y, class: 'foms-route-node__label',
        'text-anchor': 'middle', 'dominant-baseline': 'central'
      }, glyph));
      svg.appendChild(g);
    }
    return svg;
  }

  function headCaption(pts) {
    var first = regionOf(pts[0].address), last = regionOf(pts[pts.length - 1].address);
    var route = (first && last && first !== last) ? (first + ' → ' + last) : (first || last || '');
    return '오늘 동선 · ' + pts.length + '곳' + (route ? ' · ' + route : '');
  }

  function footCaption(pts, currentIdx) {
    if (currentIdx === -1) return '오늘 실측 모두 완료';
    var cur = pts[currentIdx];
    return (currentIdx + 1) + '번 ' + (cur.customer_name || '-') + ' · 다음 방문';
  }

  function applyEta(footEl, cur) {
    if (!navigator.geolocation || !cur || cur.id == null) return;
    navigator.geolocation.getCurrentPosition(function (pos) {
      var qs = 'order_id=' + encodeURIComponent(cur.id) +
        '&from_lat=' + pos.coords.latitude + '&from_lng=' + pos.coords.longitude;
      fetch('/api/erp/measurement/route-eta?' + qs)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.success || !d.data) return;
          var span = document.createElement('span');
          span.className = 'foms-route-strip__dist';
          span.textContent = ' — 지금 위치에서 ' + d.data.distance_km + 'km · ' + d.data.duration_min + '분';
          footEl.appendChild(span);
        })
        .catch(function (err) { console.debug('[route-strip] eta fail', err); });
    }, function (err) { console.debug('[route-strip] geo denied', err && err.code); },
      { timeout: 8000, maximumAge: 300000 });
  }

  function buildStrip(strip, data) {
    var pts = (data && data.route) || [];
    if (!Array.isArray(pts) || pts.length < 2) { strip.hidden = true; return; }
    var currentIdx = -1, i;
    for (i = 0; i < pts.length; i++) { if (!pts[i].measurement_completed) { currentIdx = i; break; } }
    strip.textContent = '';
    var head = document.createElement('div');
    head.className = 'foms-route-strip__head';
    head.textContent = headCaption(pts);
    strip.appendChild(head);
    strip.appendChild(renderSvg(pts, normalize(pts), currentIdx));
    var foot = document.createElement('div');
    foot.className = 'foms-route-strip__foot';
    foot.textContent = footCaption(pts, currentIdx);
    strip.appendChild(foot);
    if (currentIdx !== -1) applyEta(foot, pts[currentIdx]);
    strip.hidden = false;
  }

  function initRouteStrip() {
    var strip = document.querySelector('[data-foms-route-strip]');
    if (!strip) return;
    var date = strip.getAttribute('data-route-date') || '';
    var url = '/api/erp/measurement/route?date=' + encodeURIComponent(date);
    // '내 주문' 보기가 켜져 있으면 스트립도 내 건만 그린다(대시보드와 동일 predicate).
    // data-mine 미지정 표면(v3 등)은 기존 동작 유지.
    var mine = strip.getAttribute('data-mine');
    if (mine === '1' || mine === '0') url += '&mine=' + mine;
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) { buildStrip(strip, data); })
      .catch(function (err) { strip.hidden = true; console.debug('[route-strip] fetch fail', err); });
  }

  function boot() { initCountdowns(); initRouteStrip(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
