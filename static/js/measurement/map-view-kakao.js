/*
 * FOMS 지도 보기(map_view) — 카카오 지도 JS SDK 클라이언트 렌더.
 * folium(서버 생성 HTML) 경로의 클라이언트 대체: /api/map_data points JSON으로
 * 마커 pill·팝업·범례·동선(route=1) 오버레이를 그린다. SDK 로드 실패 시
 * 호출부(map_view.html inline)가 기존 folium 경로로 자동 폴백한다.
 *
 * 색 SSOT:
 *  - 동선 순번 핀·연결선: foms-route-strip.css의 .foms-route-c0~c7 / --foms-route-line
 *    (동선 카드와 동일 팔레트 — map_view.html이 해당 CSS를 링크).
 *  - 상태색·중첩색: 서버 folium 정본(foms/services/common/map_generator.py의
 *    _get_status_color / OVERLAP_MARKER_COLOR)을 포팅. 변경 시 양쪽 동기 필수.
 *  - 실측 담당자색: 서버 페이로드(manager_bg_color 등)가 소유 — JS 하드코딩 없음.
 *
 * 전역 계약: window.FomsMapViewKakao = { isUsable, isActive, render, updateMarkers }
 * (map_view는 full-page 전용 표면 — fragment 재실행 없음, 싱글톤 가드 불필요하나
 *  이중 로드 방어로 유지.)
 */
(function () {
  'use strict';
  if (window.FomsMapViewKakao) return;

  // 서버 정본 포팅: map_generator._get_status_color (변경 시 동기 필수)
  var STATUS_COLORS = {
    RECEIVED: '#007bff', MEASURE: '#28a745', MEASURED: '#28a745',
    DRAWING: '#6f42c1', CONFIRM: '#0d6efd', PRODUCTION: '#fd7e14',
    CONSTRUCTION: '#20c997', CS: '#dc3545', CONFIRMED: '#28a745',
    IN_PRODUCTION: '#ffc107', COMPLETED: '#6c757d', SHIPPED: '#17a2b8',
    DELIVERED: '#20c997', CANCELLED: '#dc3545', ON_HOLD: '#fd7e14'
  };
  var STATUS_FALLBACK_COLOR = '#6c757d';
  // 서버 정본 포팅: map_generator.OVERLAP_MARKER_COLOR / MAP_MARKER_NAME_MAX_LEN
  var OVERLAP_COLOR = '#f8c8d8';
  var NAME_MAX_LEN = 8;
  // 서버 정본 포팅: geocode_config.DEFAULT_CENTER (마커 0건일 때 중심)
  var DEFAULT_CENTER = { lat: 37.5665, lng: 126.9780 };
  var ROUTE_LINE_FALLBACK = '#6366f1'; // --foms-route-line 미해석 시(콜드 CSS) 동일값 폴백

  var SDK_IDLE = 0, SDK_LOADING = 1, SDK_READY = 2, SDK_FAILED = 3;
  var sdkState = SDK_IDLE;
  var sdkWaiters = [];

  // 렌더 상태(페이지당 지도 1개)
  var state = {
    map: null,
    mapEl: null,
    overlays: [],   // CustomOverlay + Polyline 정리 목록
    popup: null,
    active: false
  };

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

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

  // 사용 시점 lazy 주입(전역 로드 금지 · 가드 G2 정신). route-strip 로더와 동형.
  function loadSdk(jsKey, cb) {
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

  // ---------- 마커 테마 (서버 _get_marker_theme 포팅) ----------
  function markerTheme(m) {
    var managerBg = String(m.manager_bg_color || '').trim();
    var managerSource = String(m.manager_bg_source || '').trim();
    var managerText = String(m.manager_text_color || '#000000').trim() || '#000000';
    if (managerBg && managerSource === 'palette') {
      return { bg: managerBg, border: '#ffffff', text: managerText };
    }
    if (m.__dupSize > 1) {
      return { bg: OVERLAP_COLOR, border: '#e29ab7', text: '#6c2845' };
    }
    return {
      bg: STATUS_COLORS[String(m.status || '').toUpperCase()] || STATUS_FALLBACK_COLOR,
      border: '#ffffff', text: '#ffffff'
    };
  }

  // ---------- 중복 위치 그룹핑 (서버 _duplicate_group_key 포팅) ----------
  function duplicateKey(m) {
    // 서버 메타(measurement snapshot) 우선 — 없으면 주소/좌표로 유도(generic 모드).
    var meta = m.duplicate_location_group_key || m.duplicate_address_group_key || m.duplicate_group_key;
    if (meta) return 'meta:' + meta;
    var addr = String(m.address || '').trim();
    if (addr && addr !== '-' && addr !== '주소없음') {
      return 'addr:' + addr.split(/\s+/).join(' ').toLowerCase();
    }
    if (m.latitude == null || m.longitude == null) return null;
    return 'coord:' + Number(m.latitude).toFixed(6) + ':' + Number(m.longitude).toFixed(6);
  }

  function annotateDuplicates(markers) {
    var groups = {};
    markers.forEach(function (m) {
      var key = duplicateKey(m);
      m.__dupKey = key;
      if (key) (groups[key] = groups[key] || []).push(m);
    });
    Object.keys(groups).forEach(function (key) {
      var items = groups[key];
      items.forEach(function (m, i) {
        m.__dupSize = items.length;
        m.__dupIndex = i + 1;
      });
    });
    markers.forEach(function (m) {
      if (!m.__dupSize) { m.__dupSize = 1; m.__dupIndex = 1; }
    });
  }

  // ---------- 동선 정렬 (서버 _route_sort_key 포팅: 시간 오름차순→id) ----------
  function routeSortKey(m) {
    var t = String(m.measurement_time || '').trim();
    return [t ? 0 : 1, t, Number(m.id) || 0];
  }

  function sortForRoute(markers) {
    return markers.slice().sort(function (a, b) {
      var ka = routeSortKey(a), kb = routeSortKey(b);
      for (var i = 0; i < 3; i++) {
        if (ka[i] < kb[i]) return -1;
        if (ka[i] > kb[i]) return 1;
      }
      return 0;
    });
  }

  function isRouteCompleted(status) {
    var s = String(status || '').toUpperCase();
    return s === 'COMPLETED' || s === 'AS_COMPLETED';
  }

  // ---------- 팝업 (folium Popup 테이블 패리티 + 목록 연동) ----------
  function closePopup() {
    if (state.popup) { state.popup.setMap(null); state.popup = null; }
  }

  function openPopup(m, position) {
    closePopup();
    var statusColor = STATUS_COLORS[String(m.status || '').toUpperCase()] || STATUS_FALLBACK_COLOR;
    var dupRow = m.__dupSize > 1
      ? '<tr><th>중복</th><td>' + m.__dupSize + '건 같은 주소</td></tr>' : '';
    var el = document.createElement('div');
    el.className = 'foms-kmap-popup';
    el.innerHTML =
      '<div class="foms-kmap-popup__head">' +
      '<strong>주문 #' + escapeHtml(m.id) + '</strong>' +
      '<button type="button" class="foms-kmap-popup__close" aria-label="닫기">&times;</button>' +
      '</div>' +
      '<table class="foms-kmap-popup__table">' +
      '<tr><th>고객명</th><td>' + escapeHtml(m.customer_name || '-') + '</td></tr>' +
      '<tr><th>담당자</th><td>' + escapeHtml(m.manager_name || '-') + '</td></tr>' +
      '<tr><th>연락처</th><td>' + escapeHtml(m.phone || '-') + '</td></tr>' +
      '<tr><th>주소</th><td>' + escapeHtml(m.address || '-') + '</td></tr>' +
      '<tr><th>제품</th><td>' + escapeHtml(m.product || '-') + '</td></tr>' +
      '<tr><th>상태</th><td style="color:' + statusColor + '">' + escapeHtml(m.status || '-') + '</td></tr>' +
      '<tr><th>접수일</th><td>' + escapeHtml(m.received_date || '-') + '</td></tr>' +
      '<tr><th>좌표</th><td>' + Number(m.latitude).toFixed(6) + ', ' + Number(m.longitude).toFixed(6) + '</td></tr>' +
      dupRow +
      '</table>' +
      '<div class="foms-kmap-popup__actions">' +
      '<button type="button" class="btn btn-sm btn-primary foms-kmap-popup__detail">주문 상세 보기</button>' +
      '</div>';
    el.querySelector('.foms-kmap-popup__close').addEventListener('click', closePopup);
    el.querySelector('.foms-kmap-popup__detail').addEventListener('click', function () {
      // map_view inline의 selectOrder(우측 목록 선택 + 세부 정보 패널)와 연동.
      if (typeof window.selectOrder === 'function') window.selectOrder(Number(m.id));
    });
    state.popup = new window.kakao.maps.CustomOverlay({
      map: state.map, position: position, content: el,
      xAnchor: 0.5, yAnchor: 1.15, zIndex: 60
    });
  }

  // ---------- 범례 (folium legend 패리티: 상태색 + 동선 보조) ----------
  function renderLegend(container, opts) {
    var old = container.querySelector('.foms-kmap-legend');
    if (old) old.remove();
    var entries = [
      ['#007bff', '접수'], ['#28a745', '실측/확인'], ['#ffc107', '제작중'],
      ['#17a2b8', '배송'], ['#20c997', '배송완료'], ['#6c757d', '완료'],
      ['#dc3545', '취소/CS'], ['#fd7e14', '보류/생산'], [OVERLAP_COLOR, '동일 주소 중첩']
    ];
    var rows = entries.map(function (e) {
      return '<div class="foms-kmap-legend__row"><span class="foms-kmap-legend__dot" style="background:' + e[0] + '"></span>' + e[1] + '</div>';
    }).join('');
    var routeRows = '';
    if (opts.routeMode) {
      routeRows =
        '<div class="foms-kmap-legend__sep"></div>' +
        '<div class="foms-kmap-legend__row"><strong>방문 동선 (시간순)</strong></div>' +
        '<div class="foms-kmap-legend__row"><span class="foms-kmap-legend__line"></span>이동 순서</div>' +
        '<div class="foms-kmap-legend__row"><span class="foms-kmap-legend__dot" style="background:#adb5bd"></span>완료</div>' +
        (opts.routeSkipped ? '<div class="foms-kmap-legend__row foms-kmap-legend__row--warn">좌표 없음 ' + opts.routeSkipped + '건 제외</div>' : '');
    }
    var legend = document.createElement('div');
    legend.className = 'foms-kmap-legend';
    legend.innerHTML =
      '<button type="button" class="foms-kmap-legend__toggle" aria-expanded="true">범례 <i class="fas fa-chevron-down"></i></button>' +
      '<div class="foms-kmap-legend__body">' +
      '<div class="foms-kmap-legend__row"><strong>총 ' + opts.total + '개 주문</strong></div>' +
      rows + routeRows +
      '</div>';
    legend.querySelector('.foms-kmap-legend__toggle').addEventListener('click', function () {
      var body = legend.querySelector('.foms-kmap-legend__body');
      var hidden = body.style.display === 'none';
      body.style.display = hidden ? '' : 'none';
      this.setAttribute('aria-expanded', hidden ? 'true' : 'false');
    });
    container.appendChild(legend);
  }

  // ---------- 마커 렌더 ----------
  function clearOverlays() {
    closePopup();
    state.overlays.forEach(function (o) {
      try { o.setMap(null); } catch (e) { /* 정리 실패 무해 */ }
    });
    state.overlays = [];
  }

  function buildPill(m, opts) {
    var theme = markerTheme(m);
    var completedRoute = opts.routeMode && isRouteCompleted(m.status);
    var name = String(m.customer_name || '정보없음');
    var display = name.length > NAME_MAX_LEN ? name.slice(0, NAME_MAX_LEN) + '…' : name;

    var pill = document.createElement('div');
    pill.className = 'foms-kmap-pill' + (completedRoute ? ' foms-kmap-pill--done' : '');
    // 색은 데이터 주도(담당자색=서버·상태색=STATUS_COLORS) — 동적 스타일 불가피.
    pill.style.background = completedRoute ? '#adb5bd' : theme.bg;
    pill.style.borderColor = completedRoute ? '#ffffff' : theme.border;
    pill.style.color = completedRoute ? '#ffffff' : theme.text;
    pill.title = name + (m.__dupSize > 1 ? ' · 중복 위치 x' + m.__dupSize : '') + ' · ' + String(m.status || '');

    var htmlParts = '';
    if (opts.routeMode && m.__routeSeq) {
      // 동선 카드와 동일 팔레트 SSOT(foms-route-strip.css .foms-route-pin/.foms-route-c*)
      htmlParts += '<span class="foms-route-pin foms-route-c' + ((m.__routeSeq - 1) % 8) +
        (completedRoute ? ' foms-route-pin--done' : '') + '">' + m.__routeSeq + '</span>';
    }
    htmlParts += '<span class="foms-kmap-pill__name">' + escapeHtml(display) + '</span>';
    if (m.__dupSize > 1) {
      htmlParts += '<span class="foms-kmap-pill__dup">x' + m.__dupSize + '</span>';
    }
    pill.innerHTML = htmlParts;

    // 동일 좌표 중첩 완화: 그룹 내 순번별 수평 부채꼴 오프셋(folium 확장뷰의 경량 대체).
    if (m.__dupSize > 1) {
      var offset = (m.__dupIndex - (m.__dupSize + 1) / 2) * 14;
      pill.style.transform = 'translateX(' + offset + 'px)';
    }

    pill.addEventListener('click', function (e) {
      e.stopPropagation();
      openPopup(m, new window.kakao.maps.LatLng(m.latitude, m.longitude));
    });
    return pill;
  }

  function drawMarkers(markers, opts) {
    var maps = window.kakao.maps;
    clearOverlays();

    var routeMarkers = markers;
    if (opts.routeMode) {
      routeMarkers = sortForRoute(markers);
      routeMarkers.forEach(function (m, i) { m.__routeSeq = i + 1; });
    }

    annotateDuplicates(routeMarkers);

    var bounds = new maps.LatLngBounds();
    var routePath = [];
    routeMarkers.forEach(function (m) {
      var pos = new maps.LatLng(m.latitude, m.longitude);
      bounds.extend(pos);
      if (opts.routeMode) routePath.push(pos);
      var overlay = new maps.CustomOverlay({
        map: state.map, position: pos, content: buildPill(m, opts),
        xAnchor: 0.5, yAnchor: 1, zIndex: m.__dupSize > 1 ? 3 + (m.__dupSize - m.__dupIndex) : 2
      });
      state.overlays.push(overlay);
    });

    // 동선 폴리라인(점선) — 색 SSOT: --foms-route-line (동선 카드와 공유).
    if (opts.routeMode && routePath.length >= 2) {
      var lineColor = '';
      try {
        lineColor = getComputedStyle(state.mapEl.parentNode)
          .getPropertyValue('--foms-route-line').trim();
      } catch (e) { /* 미지원 무해 */ }
      var line = new maps.Polyline({
        map: state.map, path: routePath, strokeWeight: 4,
        strokeColor: lineColor || ROUTE_LINE_FALLBACK,
        strokeOpacity: 0.85, strokeStyle: 'dash'
      });
      state.overlays.push(line);
    }

    return { bounds: bounds, count: routeMarkers.length };
  }

  // 컨테이너 크기 변화(초기 표시 전환·창 resize·모바일 회전) 시 relayout+재fit.
  function bindAutoRelayout(mapEl, map) {
    if (typeof ResizeObserver !== 'function') return;
    var lastW = 0, lastH = 0;
    var ro = new ResizeObserver(function () {
      if (!mapEl.isConnected) { ro.disconnect(); return; }
      var w = mapEl.offsetWidth, h = mapEl.offsetHeight;
      if (w > 0 && h > 0 && (w !== lastW || h !== lastH)) {
        var first = lastW === 0 && lastH === 0;
        lastW = w; lastH = h;
        try {
          map.relayout();
          if (!first && state.lastBounds && !state.lastBounds.isEmpty()) {
            map.setBounds(state.lastBounds, 40, 40, 40, 40);
          }
        } catch (e) { /* relayout 실패 무해 */ }
      }
    });
    ro.observe(mapEl);
  }

  function ensureMap(container) {
    if (state.map && state.mapEl && state.mapEl.isConnected) return state.map;
    var maps = window.kakao.maps;
    container.textContent = '';
    var mapEl = document.createElement('div');
    mapEl.className = 'foms-kmap-canvas';
    container.appendChild(mapEl);
    var map = new maps.Map(mapEl, {
      center: new maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
      level: 8
    });
    map.addControl(new maps.ZoomControl(), maps.ControlPosition.RIGHT);
    bindAutoRelayout(mapEl, map);
    state.map = map;
    state.mapEl = mapEl;
    return map;
  }

  function renderInto(container, markers, opts) {
    ensureMap(container);
    var result = drawMarkers(markers || [], opts);
    renderLegend(container, {
      total: opts.totalOrders != null ? opts.totalOrders : result.count,
      routeMode: opts.routeMode,
      routeSkipped: opts.routeSkipped || 0
    });
    if (result.count > 0) {
      state.lastBounds = result.bounds;
      if (!opts.preserveView) {
        try { state.map.relayout(); } catch (e) { /* 무해 */ }
        state.map.setBounds(result.bounds, 40, 40, 40, 40);
      }
    }
    state.active = true;
  }

  window.FomsMapViewKakao = {
    /** SDK 실패 이력이 없고 키가 있으면 true — 호출부의 경로 선택 게이트. */
    isUsable: function (container) {
      if (sdkState === SDK_FAILED) return false;
      return !!(container && container.getAttribute('data-kakao-js-key'));
    },
    /** 카카오 렌더가 실제로 활성인지(폴링 갱신 배선용). */
    isActive: function () { return state.active && sdkState !== SDK_FAILED; },
    /**
     * 최초/필터 변경 렌더. resolve(false)면 호출부가 folium 폴백.
     * opts: { routeMode, totalOrders, routeSkipped }
     */
    render: function (container, markers, opts) {
      return new Promise(function (resolve) {
        var key = container.getAttribute('data-kakao-js-key') || '';
        loadSdk(key, function (ok) {
          if (!ok) { state.active = false; resolve(false); return; }
          try {
            renderInto(container, markers, opts || {});
            resolve(true);
          } catch (e) {
            console.warn('[map-view-kakao] 렌더 실패', e);
            state.active = false;
            resolve(false);
          }
        });
      });
    },
    /** 폴링 갱신: 뷰포트 유지한 채 마커·범례만 재구성. */
    updateMarkers: function (container, markers, opts) {
      if (!this.isActive() || !sdkReady()) return;
      try {
        renderInto(container, markers || [], Object.assign({}, opts || {}, { preserveView: true }));
      } catch (e) {
        console.warn('[map-view-kakao] 마커 갱신 실패', e);
      }
    }
  };
})();
