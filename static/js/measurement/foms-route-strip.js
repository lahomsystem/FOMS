/*
 * FOMS 실측 "오늘 동선" — 히어로 방문 카운트다운 + 지도 동선 스트립.
 * v2(mobile_list.html)·v3(persona_home_sales.html) 공용. additive·vanilla·defer.
 * 지도는 Kakao Maps SDK(사용 시점 lazy 로드)로 실지도 위 방문 순서를 그린다.
 * SDK 부재/로드 실패 시 자체 SVG 렌더로 자동 폴백(색/획은 CSS 클래스가 소유).
 *
 * 재초기화 계약(셸 프래그먼트 스왑 대응):
 *   - boot(마운트 탐색→렌더)은 스크립트 실행마다 + foms:erp-shell-fragment-swapped 마다 호출.
 *   - 마운트별 dataset.fomsRouteStripInit 가드로 idempotent(중복 fetch/렌더 차단).
 *   - 전역 1회 대상(스왑 리스너·카운트다운 타이머)만 __FOMS_ROUTE_STRIP_BOUND 아래에서 1회 배선.
 */
(function () {
  'use strict';

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

  // 라이브 DOM 재조회 → 스왑 후 새 히어로도 즉시 반영(스크립트 실행마다 호출해도 안전).
  function paintAllCountdowns() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-foms-visit-time]'), paintCountdown);
  }

  // ---------- SVG 동선 렌더(폴백) ----------
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

  // ---------- Kakao Maps SDK lazy 로더 ----------
  var SDK_IDLE = 0, SDK_LOADING = 1, SDK_READY = 2, SDK_FAILED = 3;
  var sdkState = SDK_IDLE;
  var sdkWaiters = [];

  function sdkReady() {
    return !!(window.kakao && window.kakao.maps && window.kakao.maps.Map);
  }

  function flushSdkWaiters(ok) {
    var list = sdkWaiters.slice();
    sdkWaiters.length = 0;
    for (var i = 0; i < list.length; i++) {
      try { list[i](ok); } catch (e) { /* 개별 waiter 예외 격리 */ }
    }
  }

  // 마운트 존재 시에만 head 에 SDK script 1회 주입(전역 로드 금지 · 가드 G2 정신).
  function loadKakaoSdk(jsKey, cb) {
    if (sdkReady()) { cb(true); return; }
    if (sdkState === SDK_FAILED) { cb(false); return; }
    sdkWaiters.push(cb);
    if (sdkState === SDK_LOADING) return;
    if (!jsKey) { sdkState = SDK_FAILED; flushSdkWaiters(false); return; }
    sdkState = SDK_LOADING;
    var s = document.createElement('script');
    s.id = 'foms-kakao-maps-sdk';
    s.async = true;
    s.src = 'https://dapi.kakao.com/v2/maps/sdk.js?appkey=' +
      encodeURIComponent(jsKey) + '&autoload=false';
    s.onload = function () {
      if (!window.kakao || !window.kakao.maps || !window.kakao.maps.load) {
        sdkState = SDK_FAILED; flushSdkWaiters(false); return;
      }
      window.kakao.maps.load(function () {
        sdkState = sdkReady() ? SDK_READY : SDK_FAILED;
        flushSdkWaiters(sdkState === SDK_READY);
      });
    };
    s.onerror = function () { sdkState = SDK_FAILED; flushSdkWaiters(false); };
    document.head.appendChild(s);
  }

  // ---------- Kakao 지도 렌더(실지도 위 방문 순서) ----------
  function renderKakaoMap(slot, pts, currentIdx) {
    if (!sdkReady()) return false;
    try {
      var maps = window.kakao.maps;
      var mapEl = document.createElement('div');
      mapEl.className = 'foms-route-strip__map';
      slot.textContent = '';
      slot.appendChild(mapEl);

      var bounds = new maps.LatLngBounds();
      var path = [];
      var i;
      for (i = 0; i < pts.length; i++) {
        var ll = new maps.LatLng(pts[i].lat, pts[i].lng);
        path.push(ll);
        bounds.extend(ll);
      }
      var centerIdx = currentIdx !== -1 ? currentIdx : 0;
      // draggable/zoomable 기본값 유지 → 방문지 탐색 가능. 카드가 짧아(≈180px) 스크롤 하이잭 최소.
      var map = new maps.Map(mapEl, { center: path[centerIdx], level: 5 });

      // 방문 순서 폴리라인(점선, 스트립 색감 유지).
      new maps.Polyline({
        map: map, path: path, strokeWeight: 3,
        strokeColor: '#c9bea8', strokeOpacity: 0.95, strokeStyle: 'shortdash'
      });

      // 순번 오버레이(현재=강조, 완료=✓, 나머지=작게).
      for (i = 0; i < pts.length; i++) {
        var isCurrent = i === currentIdx;
        var done = !!pts[i].measurement_completed && !isCurrent;
        var mod = isCurrent ? 'is-current' : (done ? 'is-done' : 'is-upcoming');
        var pin = document.createElement('span');
        pin.className = 'foms-route-pin foms-route-pin--' + mod;
        pin.textContent = done ? '✓' : String(i + 1);
        new maps.CustomOverlay({
          map: map, position: path[i], content: pin,
          xAnchor: 0.5, yAnchor: 0.5, zIndex: isCurrent ? 10 : 1
        });
      }

      map.setBounds(bounds, 28, 28, 28, 28);
      // 슬롯이 방금 붙어 크기 계산이 늦을 수 있어 relayout 후 재fit(타이밍 방어).
      window.setTimeout(function () {
        try { map.relayout(); map.setBounds(bounds, 28, 28, 28, 28); } catch (e) { /* relayout 실패 무해 */ }
      }, 0);
      return true;
    } catch (e) {
      console.warn('[route-strip] Kakao 지도 렌더 실패 — SVG 폴백', e);
      return false;
    }
  }

  // 지도 우선, 실패/키부재 시 SVG 폴백. SDK 로드 대기 중엔 SVG 즉시 렌더(빈 화면 방지).
  function renderRouteVisual(slot, jsKey, pts, currentIdx) {
    function svgFallback(warnMsg) {
      if (warnMsg) console.warn('[route-strip] ' + warnMsg);
      slot.textContent = '';
      slot.appendChild(renderSvg(pts, normalize(pts), currentIdx));
    }
    if (sdkReady()) {
      if (!renderKakaoMap(slot, pts, currentIdx)) svgFallback('Kakao 지도 렌더 실패 — SVG 폴백');
      return;
    }
    if (!jsKey) { svgFallback('Kakao JS 키 없음 — SVG 폴백'); return; }
    svgFallback();  // 로드 전 플레이스홀더(실패 아님 → warn 없음)
    loadKakaoSdk(jsKey, function (ok) {
      if (!slot.isConnected) return;  // 그새 스왑 재초기화로 슬롯 교체 시 구식 콜백 무시
      if (!ok) { console.warn('[route-strip] Kakao SDK 로드 실패 — SVG 유지'); return; }
      if (!renderKakaoMap(slot, pts, currentIdx)) svgFallback('Kakao 지도 렌더 실패 — SVG 폴백');
    });
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

    var slot = document.createElement('div');
    slot.className = 'foms-route-strip__visual';
    strip.appendChild(slot);

    var foot = document.createElement('div');
    foot.className = 'foms-route-strip__foot';
    foot.textContent = footCaption(pts, currentIdx);
    strip.appendChild(foot);
    if (currentIdx !== -1) applyEta(foot, pts[currentIdx]);

    strip.hidden = false;  // 렌더 전 표시 → 지도 컨테이너가 실제 크기를 갖도록
    renderRouteVisual(slot, strip.getAttribute('data-kakao-js-key') || '', pts, currentIdx);
  }

  function initRouteStrip() {
    var strip = document.querySelector('[data-foms-route-strip]');
    if (!strip) return;
    if (strip.dataset.fomsRouteStripInit === '1') return;  // 마운트별 idempotent 가드
    strip.dataset.fomsRouteStripInit = '1';
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

  // 스크립트 실행마다 + 프래그먼트 스왑마다 실행(모두 idempotent).
  function boot() { paintAllCountdowns(); initRouteStrip(); }

  // 전역 1회 배선: 스왑 재init 리스너 + 카운트다운 단일 타이머(라이브 DOM 재조회).
  if (!window.__FOMS_ROUTE_STRIP_BOUND) {
    window.__FOMS_ROUTE_STRIP_BOUND = true;
    document.addEventListener('foms:erp-shell-fragment-swapped', boot);
    window.setInterval(paintAllCountdowns, 60000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
