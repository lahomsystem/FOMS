/*
 * FOMS 실측 "오늘 동선" — 히어로 방문 카운트다운 + 지도 동선 스트립.
 * v2(mobile_list.html)·v3(persona_home_sales.html) 공용. additive·vanilla·defer.
 * 지도는 Kakao Maps SDK(사용 시점 lazy 로드)로 실지도 위 방문 순서를 그린다.
 * SDK 부재/로드 실패 시 자체 SVG 렌더로 자동 폴백(색/획은 CSS 클래스가 소유).
 * 데이터는 서버 인라인(data-route-inline, 뷰가 route API와 동일 빌더로 주입) 우선
 * — API 왕복 없이 즉시 첫 페인트. 미주입 표면(v3 등)은 route API fetch 폴백.
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
    // 표시는 항상 원문 라벨("4시") 우선 — data-foms-visit-time 은 서버가 정규화한
    // HH:MM 정렬/계산용 값이라 그대로 보여주면 사용자가 쓰는 표현과 달라진다.
    var label = el.getAttribute('data-foms-visit-label') || el.getAttribute('data-foms-visit-time');
    if (diff < 0) { el.textContent = '방문 시간 지남'; el.classList.add('is-passed'); }
    else if (diff === 0) { el.textContent = '지금 출발'; el.classList.add('is-soon'); }
    else if (diff < 60) { el.textContent = diff + '분 후 출발'; el.classList.add('is-soon'); }
    else { el.textContent = label + ' 방문'; }
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

  // ---------- 핀 → 실측 큐 카드 스크롤 ----------
  // 실측 모바일 대시보드(mobile_list.html)에서만 카드가 존재한다. 카드 없는 표면
  // (v3 persona 홈 등)은 배선 자체를 생략해 no-op 유지. 존재 판정은 렌더 시점,
  // 카드 재탐색은 클릭 시점(?focus_order= 딥링크와 동일 selector·하이라이트 계약).
  function findQueueCard(orderId) {
    if (orderId == null) return null;
    return document.querySelector(
      '.erp-measurement-mobile-card[data-measurement-mobile-order-id="' + orderId + '"]'
    );
  }

  function focusQueueCard(orderId) {
    var card = findQueueCard(orderId);
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('is-focused');
    window.setTimeout(function () { card.classList.remove('is-focused'); }, 2400);
  }

  function bindPinToCard(node, point, seq) {
    if (!point || point.id == null || !findQueueCard(point.id)) return;
    node.classList.add('is-linkable');
    node.setAttribute('role', 'button');
    node.setAttribute('tabindex', '0');
    node.setAttribute('aria-label', seq + '번 ' + (point.customer_name || '방문지') + ' 주문 카드로 이동');
    node.addEventListener('click', function () { focusQueueCard(point.id); });
    node.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); focusQueueCard(point.id); }
    });
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
      // 순번별 팔레트(.foms-route-c0~c7, CSS SSOT) — 상태 강조는 링/크기/✓가 담당.
      var g = el('g', { class: 'foms-route-node foms-route-node' + mod + ' foms-route-c' + (i % 8) });
      if (isCurrent) {
        g.appendChild(el('circle', {
          cx: coords[i].x, cy: coords[i].y, r: 15, class: 'foms-route-node__ring'
        }));
      }
      g.appendChild(el('circle', {
        cx: coords[i].x, cy: coords[i].y, r: isCurrent ? 11 : 8, class: 'foms-route-node__dot'
      }));
      var glyph = (done && !isCurrent) ? '✓' : String(i + 1);
      g.appendChild(el('text', {
        x: coords[i].x, y: coords[i].y, class: 'foms-route-node__label',
        'text-anchor': 'middle', 'dominant-baseline': 'central'
      }, glyph));
      bindPinToCard(g, pts[i], i + 1);
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

  // 컨테이너 크기 변화(콜드 로드 CSS 늦은 도착·창 회전/resize·시트 개폐) 시
  // relayout + bounds 재fit. 카카오 지도는 0-사이즈로 init 되면 자동 복구가 없어
  // 관측 기반으로 결정론화한다(첫 observe 콜백이 초기 보정 1회를 겸함).
  function bindMapAutoRelayout(mapEl, map, bounds) {
    function refit() {
      try { map.relayout(); map.setBounds(bounds, 28, 28, 28, 28); } catch (e) { /* relayout 실패 무해 */ }
    }
    if (typeof ResizeObserver === 'function') {
      var lastW = 0, lastH = 0;
      var ro = new ResizeObserver(function () {
        if (!mapEl.isConnected) { ro.disconnect(); return; }  // 스왑으로 분리된 옛 지도 정리
        var w = mapEl.offsetWidth, h = mapEl.offsetHeight;
        if (w > 0 && h > 0 && (w !== lastW || h !== lastH)) { lastW = w; lastH = h; refit(); }
      });
      ro.observe(mapEl);
      return;
    }
    // 구형 브라우저 폴백: rAF 2프레임 보정(레이아웃 확정 후 재fit).
    var tries = 0;
    (function poll() {
      if (!mapEl.isConnected || tries >= 2) return;
      tries += 1;
      window.requestAnimationFrame(function () { refit(); poll(); });
    })();
  }

  // ---------- Kakao 지도 렌더(실지도 위 방문 순서) ----------
  function renderKakaoMap(slot, pts, currentIdx) {
    if (!sdkReady()) return false;
    try {
      var maps = window.kakao.maps;
      var mapEl = document.createElement('div');
      mapEl.className = 'foms-route-strip__map';
      // 콜드 로드에서 route-strip.css(높이 180px)보다 JS가 먼저 돌면 0-사이즈 init
      // → 타일 미렌더 공백. init 전 JS 동적 스타일로 높이를 결정론화(CSS와 중복 무해).
      mapEl.style.height = '180px';
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

      // 방문 순서 폴리라인(점선) — 색 SSOT는 CSS 변수 --foms-route-line(strip에서 상속).
      var lineColor = '';
      try { lineColor = getComputedStyle(slot).getPropertyValue('--foms-route-line').trim(); } catch (e) { /* 미지원 무해 */ }
      new maps.Polyline({
        map: map, path: path, strokeWeight: 3,
        strokeColor: lineColor || '#6366f1', strokeOpacity: 0.95, strokeStyle: 'shortdash'
      });

      // 순번 오버레이 — 순번별 팔레트(.foms-route-c*), 현재=이중 링+확대, 완료=✓+저채도.
      for (i = 0; i < pts.length; i++) {
        var isCurrent = i === currentIdx;
        var done = !!pts[i].measurement_completed && !isCurrent;
        var mod = isCurrent ? 'current' : (done ? 'done' : 'upcoming');
        var pin = document.createElement('span');
        pin.className = 'foms-route-pin foms-route-pin--' + mod + ' foms-route-c' + (i % 8);
        pin.textContent = done ? '✓' : String(i + 1);
        bindPinToCard(pin, pts[i], i + 1);
        // clickable: 핀 탭이 지도 pan/클릭으로 새지 않게 — 배선된 핀에만 적용.
        new maps.CustomOverlay({
          map: map, position: path[i], content: pin,
          xAnchor: 0.5, yAnchor: 0.5, zIndex: isCurrent ? 10 : 1,
          clickable: pin.classList.contains('is-linkable')
        });
      }

      map.setBounds(bounds, 28, 28, 28, 28);
      bindMapAutoRelayout(mapEl, map, bounds);
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

  // 지도에서 빠진 건수는 반드시 캡션에 남긴다 — 조용히 사라지면 "실측 10곳"과
  // "동선 4곳"의 차이를 사용자가 설명할 수 없다(좌표 미변환/상한 절단).
  function excludedNote(data) {
    var missing = (data && data.missing_coords) || 0;
    var truncated = (data && data.truncated) || 0;
    var parts = [];
    if (missing > 0) parts.push('좌표 없는 ' + missing + '곳');
    if (truncated > 0) parts.push(truncated + '곳 더');
    return parts.length ? '(' + parts.join(' · ') + ' 제외)' : '';
  }

  function headCaption(pts, data) {
    var first = regionOf(pts[0].address), last = regionOf(pts[pts.length - 1].address);
    var route = (first && last && first !== last) ? (first + ' → ' + last) : (first || last || '');
    return '오늘 동선 · ' + pts.length + '곳' + excludedNote(data) + (route ? ' · ' + route : '');
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
    head.textContent = headCaption(pts, data);
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

  // 서버 인라인 동선(data-route-inline) 안전 파싱 — 실패 시 null(fetch 폴백).
  function parseInlineRoute(strip) {
    var raw = strip.getAttribute('data-route-inline');
    if (!raw) return null;
    try {
      var data = JSON.parse(raw);
      return (data && Array.isArray(data.route)) ? data : null;
    } catch (e) {
      console.warn('[route-strip] 인라인 동선 파싱 실패 — fetch 폴백', e);
      return null;
    }
  }

  function initRouteStrip() {
    var strip = document.querySelector('[data-foms-route-strip]');
    if (!strip) return;
    if (strip.dataset.fomsRouteStripInit === '1') return;  // 마운트별 idempotent 가드
    strip.dataset.fomsRouteStripInit = '1';
    // SDK 선로드(워밍): 데이터 확정 전에 다운로드를 시작해 fetch 왕복(지오코딩 ~0.7s) 뒤에 숨긴다.
    // 이전엔 fetch → buildStrip → renderRouteVisual 순으로만 SDK 로드가 시작돼 직렬이었다.
    // loadKakaoSdk 는 상태머신+waiter 큐라 재호출이 안전하다(READY 면 즉시, LOADING 이면 합류).
    var warmKey = strip.getAttribute('data-kakao-js-key') || '';
    if (warmKey) loadKakaoSdk(warmKey, function () { /* 워밍 전용 — 렌더는 renderRouteVisual 담당 */ });
    // 서버 인라인이 2점 이상(좌표가 이미 캐시된 날)이면 route API 왕복 없이 즉시 렌더.
    // 좌표 미캐시로 2점 미만이면 여기서 숨기지 말고 fetch 폴백으로 넘어간다 —
    // build_inline_route_strip_payload 는 저장 좌표만 써서 아직 지오코딩 안 된 날짜엔
    // 빈 route 를 주지만, route API(build_measurement_route_payload)는 즉시 지오코딩하므로
    // 오늘 외 날짜(미지오코딩)도 지도가 뜬다. 미주입 표면(v3 등)도 이 fetch 경로를 탄다.
    var inline = parseInlineRoute(strip);
    if (inline && Array.isArray(inline.route) && inline.route.length >= 2) {
      buildStrip(strip, inline);
      return;
    }
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
