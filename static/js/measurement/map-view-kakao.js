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
  // 줌 임계 그룹 접기/펼치기 — folium 파리티: duplicateMarkerZoomThreshold=14
  // (Leaflet, getZoom()>=14 = 펼침). 카카오 level은 작을수록 확대이고
  // level 3 ≈ Leaflet z16(≈100m 축척) 앵커 → Leaflet z14 ≈ 카카오 level 5.
  // 즉 level<=5 = 펼침(개별 분리), level>=6 = 접힘(대표 1개 + xN 뱃지).
  var DUPLICATE_EXPAND_MAX_LEVEL = 5;

  var SDK_IDLE = 0, SDK_LOADING = 1, SDK_READY = 2, SDK_FAILED = 3;
  var sdkState = SDK_IDLE;
  var sdkWaiters = [];

  // 렌더 상태(페이지당 지도 1개)
  var state = {
    map: null,
    mapEl: null,
    overlays: [],    // CustomOverlay + Polyline 정리 목록
    markerItems: [], // {overlay, pill, marker} — 줌 임계 그룹 레이아웃 대상
    routeMode: false,
    popup: null,
    active: false,
    everRendered: false // 세션 내 카카오 성공 렌더 이력 — folium 강등 금지 가드
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

  // 접힌 대표 마커 클릭 팝업: 그룹 내 주문 목록(+각 상세 보기) — folium 팝업 행 파리티 확장.
  function openGroupPopup(markersInGroup, position) {
    closePopup();
    var rows = markersInGroup.map(function (m) {
      return '<div class="foms-kmap-popup__group-row">' +
        '<span class="foms-kmap-popup__group-main">' +
        '<strong>#' + escapeHtml(m.id) + '</strong> ' + escapeHtml(m.customer_name || '-') +
        (m.measurement_time ? ' · ' + escapeHtml(m.measurement_time) : '') +
        '</span>' +
        '<button type="button" class="btn btn-sm btn-outline-primary" data-order-id="' + escapeHtml(m.id) + '">상세</button>' +
        '</div>';
    }).join('');
    var el = document.createElement('div');
    el.className = 'foms-kmap-popup';
    el.innerHTML =
      '<div class="foms-kmap-popup__head">' +
      '<strong>같은 위치 ' + markersInGroup.length + '건</strong>' +
      '<button type="button" class="foms-kmap-popup__close" aria-label="닫기">&times;</button>' +
      '</div>' +
      '<div class="foms-kmap-popup__group">' +
      '<div class="foms-kmap-popup__group-addr">' + escapeHtml(markersInGroup[0].address || '-') + '</div>' +
      rows +
      '</div>' +
      '<div class="foms-kmap-popup__actions">' +
      '<button type="button" class="btn btn-sm btn-primary foms-kmap-popup__expand">펼쳐 보기</button>' +
      '</div>';
    el.querySelector('.foms-kmap-popup__close').addEventListener('click', closePopup);
    // 그룹 중심 확대: 임계 통과(격자 펼침)로 직행 — 중심 고정 줌으로 그룹이
    // 화면 밖으로 흘러나가는 문제를 앵커 지정으로 원천 회피.
    el.querySelector('.foms-kmap-popup__expand').addEventListener('click', function () {
      closePopup();
      try {
        state.map.setLevel(DUPLICATE_EXPAND_MAX_LEVEL, { anchor: position });
        state.map.panTo(position);
      } catch (e) { /* 지도 조작 실패 무해 */ }
    });
    Array.prototype.forEach.call(el.querySelectorAll('button[data-order-id]'), function (btn) {
      btn.addEventListener('click', function () {
        if (typeof window.selectOrder === 'function') {
          window.selectOrder(Number(btn.getAttribute('data-order-id')));
        }
      });
    });
    state.popup = new window.kakao.maps.CustomOverlay({
      map: state.map, position: position, content: el,
      xAnchor: 0.5, yAnchor: 1.15, zIndex: 60
    });
  }

  // ---------- 줌 임계 그룹 접기/펼치기 (folium applyDuplicateMarkerLayout 포팅) ----------
  function isExpandedView() {
    if (!state.map || typeof state.map.getLevel !== 'function') return true;
    return state.map.getLevel() <= DUPLICATE_EXPAND_MAX_LEVEL;
  }

  function groupMarkersOf(m) {
    if (!m.__dupKey || m.__dupSize <= 1) return [m];
    return state.markerItems
      .filter(function (item) { return item.marker.__dupKey === m.__dupKey; })
      .map(function (item) { return item.marker; });
  }

  // 오버레이는 재생성하지 않고 setMap/transform 토글만 수행(줌마다 DOM 재생성 금지).
  // 접힘: 대표 1개(+xN 뱃지) — route 모드 순번 핀은 방문 순서가 정체성이라 항상 표시
  // (folium의 routeState forceVisible 파리티). 펼침: folium 격자 지오메트리 그대로.
  function applyDuplicateLayout() {
    if (!state.map || !state.markerItems.length) return;
    var groups = {};
    state.markerItems.forEach(function (item) {
      // 리셋: 전원 표시 + 오프셋 제거 (folium 파리티)
      item.pill.style.transform = '';
      item.overlay.setZIndex(2);
      if (!item.overlay.getMap()) item.overlay.setMap(state.map);
      var key = item.marker.__dupKey;
      if (key && item.marker.__dupSize > 1) (groups[key] = groups[key] || []).push(item);
    });
    var expanded = isExpandedView();
    Object.keys(groups).forEach(function (key) {
      var items = groups[key];
      if (items.length <= 1) return;
      items.sort(function (a, b) { return a.marker.__dupIndex - b.marker.__dupIndex; });

      if (!expanded) {
        items.forEach(function (item, position) {
          var forceVisible = state.routeMode;
          var isRepresentative = position === 0;
          if (isRepresentative || forceVisible) {
            item.overlay.setZIndex(300 + items.length - position);
          } else {
            item.overlay.setMap(null);
          }
        });
        return;
      }

      // 펼침: columns=size<=4?size:3 · spacingX=clamp(88, w*1.1, 240) ·
      // spacingY=max(52, h*1.35) · dy는 역-Y 계단(+|dx|*0.16) — folium 그대로.
      var maxWidth = 0, maxHeight = 0;
      items.forEach(function (item) {
        var rect = item.pill.getBoundingClientRect();
        maxWidth = Math.max(maxWidth, rect.width || 0);
        maxHeight = Math.max(maxHeight, rect.height || 0);
      });
      if (!maxWidth) maxWidth = 120;
      if (!maxHeight) maxHeight = 36;
      var columns = items.length <= 4 ? items.length : 3;
      var spacingX = Math.min(240, Math.max(88, Math.round(maxWidth * 1.1)));
      var spacingY = Math.max(52, Math.round(maxHeight * 1.35));
      items.forEach(function (item, position) {
        var row = Math.floor(position / columns);
        var rowStart = row * columns;
        var rowCount = Math.min(columns, items.length - rowStart);
        var column = position % columns;
        var rowCenter = (rowCount - 1) / 2;
        var dx = Math.round((column - rowCenter) * spacingX);
        var dy = -Math.round((row * spacingY) + (Math.abs(dx) * 0.16));
        item.pill.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
        item.overlay.setZIndex(300 + position);
      });
    });
  }

  // 줌 후 보이는 마커가 0개면 최근접 마커로 팬 보정 — 근본 원인 대응:
  // 확대(중심 고정 줌)로 모든 마커가 뷰포트 밖으로 나가면 카카오는 화면 밖
  // CustomOverlay DOM을 분리해 사용자에게 "마커 전부 소실"로 보인다(스테이징
  // 실증: 소실 순간 render/updateMarkers 호출 0 + 축소만으로 대칭 복구).
  // 이 지도의 목적은 주문 탐색이므로 줌 결과 전멸 시에만 개입한다(팬 조작 불간섭).
  // panTo는 zoom_changed를 재발화하지 않아 루프가 없다.
  function keepMarkersInView() {
    if (!state.map || !state.markerItems.length) return;
    var bounds, center;
    try { bounds = state.map.getBounds(); center = state.map.getCenter(); } catch (e) { return; }
    var nearest = null, nearestD = Infinity, anyVisible = false;
    state.markerItems.forEach(function (item) {
      if (!item.overlay.getMap()) return; // 접힘으로 숨긴 비대표 제외
      var pos = item.overlay.getPosition();
      if (bounds.contain(pos)) { anyVisible = true; return; }
      var dLat = pos.getLat() - center.getLat();
      var dLng = pos.getLng() - center.getLng();
      var d = dLat * dLat + dLng * dLng;
      if (d < nearestD) { nearestD = d; nearest = pos; }
    });
    if (!anyVisible && nearest) state.map.panTo(nearest);
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
    state.markerItems = [];
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

    // 오프셋/표시 여부는 applyDuplicateLayout(줌 임계 그룹 레이아웃)이 소유.
    pill.addEventListener('click', function (e) {
      e.stopPropagation();
      var pos = new window.kakao.maps.LatLng(m.latitude, m.longitude);
      var group = groupMarkersOf(m);
      // 접힌 대표 마커: 그룹 내 주문 목록 팝업. 펼침/route 모드: 개별 팝업.
      if (group.length > 1 && !isExpandedView() && !state.routeMode) {
        openGroupPopup(group, pos);
      } else {
        openPopup(m, pos);
      }
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
    state.routeMode = !!opts.routeMode;

    var bounds = new maps.LatLngBounds();
    var routePath = [];
    routeMarkers.forEach(function (m) {
      var pos = new maps.LatLng(m.latitude, m.longitude);
      bounds.extend(pos);
      if (opts.routeMode) routePath.push(pos);
      var pill = buildPill(m, opts);
      var overlay = new maps.CustomOverlay({
        map: state.map, position: pos, content: pill,
        xAnchor: 0.5, yAnchor: 1, zIndex: 2
      });
      state.overlays.push(overlay);
      state.markerItems.push({ overlay: overlay, pill: pill, marker: m });
    });

    // 현재 줌 기준 그룹 접기/펼치기 즉시 적용(폴링 재렌더 시 상태 보존).
    applyDuplicateLayout();

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
    // 줌 임계 그룹 접기/펼치기 + 마커 전멸 팬 보정 — 리스너는 지도 인스턴스당
    // 1회(이 생성 분기에서만 부착). ensureMap 은 기존 인스턴스를 재사용하므로
    // 재렌더/폴링에서 누적되지 않는다.
    maps.event.addListener(map, 'zoom_changed', function () {
      applyDuplicateLayout();
      keepMarkersInView();
    });
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
            state.everRendered = true;
            resolve(true);
          } catch (e) {
            console.warn('[map-view-kakao] 렌더 실패', e);
            if (state.everRendered) {
              // 세션 내 folium 강등 금지(사용자 확정 지시): 카카오 지도를 유지하고
              // 다음 갱신(폴링/필터 변경 재렌더)에서 복구를 시도한다.
              resolve(true);
              return;
            }
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
