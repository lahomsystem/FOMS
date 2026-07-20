/*
 * FOMS 지도 보기(map_view) — 카카오 지도 JS SDK 클라이언트 렌더.
 * folium(서버 생성 HTML) 경로의 클라이언트 대체: /api/map_data points JSON으로
 * 마커 pill·팝업·동선(route=1) 오버레이를 그린다. SDK 로드 실패 시
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
    everRendered: false, // 세션 내 카카오 성공 렌더 이력 — folium 강등 금지 가드
    // 주문↔주문 경로 계산(folium 파리티): 출발/도착 선택 + 실도로 폴리라인 + 결과 패널.
    // line/panel 은 마커 재렌더(clearOverlays)와 독립 수명 — 폴링에도 결과 유지.
    routeCalc: { start: null, end: null, line: null, panel: null }
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

  // ---------- 주문↔주문 경로 계산 (folium 파리티: 2건 선택 → 거리·시간·통행료) ----------
  // 서버 프록시 /api/calculate_route(카카오모빌리티 directions) 경유 — REST 키 비노출.
  // folium UX(1클릭 출발→2클릭 도착→결과 카드+실도로 폴리라인+초기화)를 팝업 액션
  // 버튼 시퀀스로 이식(카카오 팝업 구조에 자연스럽게 — 단순 클릭 하이잭 대신).
  function routeCalcContainer() {
    // 패널은 카카오 컨테이너(mapEl) 안에 부착 — 카카오가 컨테이너를 position:relative로
    // 관리하므로 absolute(top/left 14px)가 지도 좌상단에 정확히 앵커된다. parentNode
    // (#map-content 등)는 비-positioned라 데스크톱에서 패널이 화면 밖으로 흘렀던 실사고.
    return state.mapEl || document.getElementById('map-content');
  }

  function ensureRouteCalcPanel() {
    if (state.routeCalc.panel && state.routeCalc.panel.isConnected) return state.routeCalc.panel;
    var panel = document.createElement('div');
    panel.className = 'foms-kmap-routecalc';
    routeCalcContainer().appendChild(panel);
    state.routeCalc.panel = panel;
    return panel;
  }

  function setRouteCalcPanel(bodyHtml, withReset) {
    var panel = ensureRouteCalcPanel();
    panel.innerHTML =
      '<div class="foms-kmap-routecalc__head">🚗 경로 계산</div>' + bodyHtml +
      (withReset ? '<button type="button" class="btn btn-sm btn-secondary foms-kmap-routecalc__reset">초기화</button>' : '');
    var reset = panel.querySelector('.foms-kmap-routecalc__reset');
    if (reset) reset.addEventListener('click', resetRouteCalc);
  }

  // 재렌더 후에도 출발/도착 강조를 pill 에 재적용(마커 id 기준).
  function applyRouteCalcHighlight() {
    state.markerItems.forEach(function (item) {
      var id = String(item.marker.id);
      item.pill.classList.toggle('foms-kmap-pill--route-start',
        !!(state.routeCalc.start && String(state.routeCalc.start.id) === id));
      item.pill.classList.toggle('foms-kmap-pill--route-end',
        !!(state.routeCalc.end && String(state.routeCalc.end.id) === id));
    });
  }

  function resetRouteCalc() {
    state.routeCalc.start = null;
    state.routeCalc.end = null;
    if (state.routeCalc.line) {
      try { state.routeCalc.line.setMap(null); } catch (e) { /* 정리 실패 무해 */ }
      state.routeCalc.line = null;
    }
    if (state.routeCalc.panel) {
      state.routeCalc.panel.remove();
      state.routeCalc.panel = null;
    }
    applyRouteCalcHighlight();
  }

  // 팝업 경로 버튼 라벨(선택 상태 머신 반영). 시작→도착→결과 후에는 새 시작.
  function routeCalcBtnLabel(m) {
    if (state.routeCalc.start && !state.routeCalc.end) {
      return String(state.routeCalc.start.id) === String(m.id) ? '출발 해제' : '도착 지정';
    }
    return '경로 시작';
  }

  function onRouteCalcAction(m) {
    // 결과 표시 중 3번째 선택 = folium 파리티(리셋 후 새 출발로 시작).
    if (state.routeCalc.start && state.routeCalc.end) resetRouteCalc();
    else if (state.routeCalc.start && String(state.routeCalc.start.id) === String(m.id)) {
      // folium 은 같은 주문 재선택에 alert — 여기선 '출발 해제'로 개선(팝업 라벨과 일치).
      resetRouteCalc();
      return;
    }
    var sel = { id: m.id, name: m.customer_name || '-', lat: m.latitude, lng: m.longitude };
    if (!state.routeCalc.start) {
      state.routeCalc.start = sel;
      applyRouteCalcHighlight();
      setRouteCalcPanel(
        '<div><strong>출발:</strong> ' + escapeHtml(sel.name) + '</div>' +
        '<div class="foms-kmap-routecalc__hint">도착 주문의 팝업에서 \'도착 지정\'을 눌러주세요.</div>',
        true
      );
      return;
    }
    state.routeCalc.end = sel;
    applyRouteCalcHighlight();
    runRouteCalc(state.routeCalc.start, sel);
  }

  function runRouteCalc(start, end) {
    var maps = window.kakao.maps;
    setRouteCalcPanel('<div>경로 계산 중... 잠시만 기다려주세요.</div>', false);
    var qs = 'start_lat=' + encodeURIComponent(start.lat) + '&start_lng=' + encodeURIComponent(start.lng) +
      '&end_lat=' + encodeURIComponent(end.lat) + '&end_lng=' + encodeURIComponent(end.lng);
    fetch('/api/calculate_route?' + qs)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success || !data.data) {
          console.warn('[map-view-kakao] 경로 계산 실패', data && data.error);
          setRouteCalcPanel(
            '<div class="foms-kmap-routecalc__error">오류: ' + escapeHtml((data && data.error) || '경로를 계산할 수 없습니다.') + '</div>',
            true
          );
          return;
        }
        var rd = data.data;
        if (state.routeCalc.line) {
          try { state.routeCalc.line.setMap(null); } catch (e) { /* 무해 */ }
        }
        // 실도로 경로(vertexes) 있으면 그대로, 없으면 직선을 점선으로 구분 표기.
        var path, straightFallback = false;
        if (Array.isArray(rd.route_coords) && rd.route_coords.length > 1) {
          path = rd.route_coords.map(function (c) { return new maps.LatLng(c[0], c[1]); });
        } else {
          path = [new maps.LatLng(start.lat, start.lng), new maps.LatLng(end.lat, end.lng)];
          straightFallback = true;
        }
        state.routeCalc.line = new maps.Polyline({
          map: state.map, path: path, strokeWeight: 5,
          strokeColor: '#ff4757',
          strokeOpacity: straightFallback ? 0.6 : 0.8,
          strokeStyle: straightFallback ? 'shortdash' : 'solid'
        });
        var b = new maps.LatLngBounds();
        b.extend(new maps.LatLng(start.lat, start.lng));
        b.extend(new maps.LatLng(end.lat, end.lng));
        try { state.map.setBounds(b, 50, 50, 50, 50); } catch (e) { /* fit 실패 무해 */ }
        var s = rd.summary || {};
        setRouteCalcPanel(
          '<div><strong>출발:</strong> ' + escapeHtml(start.name) + '</div>' +
          '<div><strong>도착:</strong> ' + escapeHtml(end.name) + '</div>' +
          '<div><strong>거리:</strong> ' + escapeHtml(s.distance_text || ((rd.distance_km != null ? rd.distance_km : '-') + 'km')) + '</div>' +
          '<div><strong>소요시간:</strong> ' + escapeHtml(s.duration_text || ((rd.duration_min != null ? rd.duration_min : '-') + '분')) + '</div>' +
          '<div><strong>통행료:</strong> ' + escapeHtml(s.toll_text || ((rd.toll || 0) + '원')) + '</div>' +
          (straightFallback ? '<div class="foms-kmap-routecalc__hint">실도로 경로 정보가 없어 직선(점선)으로 표시했습니다.</div>' : ''),
          true
        );
      })
      .catch(function (err) {
        console.warn('[map-view-kakao] 경로 계산 오류', err);
        setRouteCalcPanel('<div class="foms-kmap-routecalc__error">오류: 경로 계산에 실패했습니다.</div>', true);
      });
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
      '<button type="button" class="btn btn-sm btn-outline-danger foms-kmap-popup__route">' + routeCalcBtnLabel(m) + '</button>' +
      '<button type="button" class="btn btn-sm btn-primary foms-kmap-popup__detail">주문 상세 보기</button>' +
      '</div>';
    el.querySelector('.foms-kmap-popup__close').addEventListener('click', closePopup);
    el.querySelector('.foms-kmap-popup__detail').addEventListener('click', function () {
      // map_view inline의 selectOrder(우측 목록 선택 + 세부 정보 패널)와 연동.
      if (typeof window.selectOrder === 'function') window.selectOrder(Number(m.id));
    });
    // 주문↔주문 경로 계산: 출발/도착 선택(route 모드 순번 핀 팝업에서도 동일 동작).
    el.querySelector('.foms-kmap-popup__route').addEventListener('click', function () {
      closePopup();
      onRouteCalcAction(m);
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
      '<button type="button" class="btn btn-sm btn-outline-danger foms-kmap-popup__route">' + routeCalcBtnLabel(markersInGroup[0]) + '</button>' +
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
    // 그룹 경로 계산: 그룹원은 좌표가 동일해 경로 결과도 동일 — 대표(첫 행) 기준으로
    // 단순화(행별 시작/도착 버튼은 모바일 행 밀도상 과밀). 이름만 대표 주문으로 표기.
    el.querySelector('.foms-kmap-popup__route').addEventListener('click', function () {
      closePopup();
      onRouteCalcAction(markersInGroup[0]);
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
    try {
      var bounds = state.map.getBounds();
      var center = state.map.getCenter();
      // SDK 표기 방어: LatLngBounds 판정 함수 기능 탐지(contain 정본, contains 대비).
      var containFn = bounds.contain || bounds.contains;
      if (typeof containFn !== 'function') {
        console.debug('[kmap] bounds contain API 미탐지 — 팬 보정 생략');
        return;
      }
      var nearest = null, nearestD = Infinity, anyVisible = false, mapped = 0;
      state.markerItems.forEach(function (item) {
        if (!item.overlay.getMap()) return; // 접힘으로 숨긴 비대표 제외
        mapped++;
        var pos = item.overlay.getPosition();
        if (containFn.call(bounds, pos)) { anyVisible = true; return; }
        var dLat = pos.getLat() - center.getLat();
        var dLng = pos.getLng() - center.getLng();
        var d = dLat * dLat + dLng * dLng;
        if (d < nearestD) { nearestD = d; nearest = pos; }
      });
      console.debug('[kmap] keepMarkersInView mapped=' + mapped +
        ' anyVisible=' + anyVisible + ' panTo=' + (!anyVisible && !!nearest));
      if (!anyVisible && nearest) state.map.panTo(nearest);
    } catch (e) {
      // 카카오 이벤트 디스패처가 예외를 삼키면 무증상 미보정이 된다 — 반드시 기록.
      console.warn('[map-view-kakao] 팬 보정 실패', e);
    }
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

    // 경로 계산 선택 보존: 재렌더 후 대상 주문이 사라졌으면 해제, 남았으면 강조 재적용.
    if (state.routeCalc.start) {
      var liveIds = {};
      routeMarkers.forEach(function (m) { liveIds[String(m.id)] = true; });
      var startGone = !liveIds[String(state.routeCalc.start.id)];
      var endGone = state.routeCalc.end && !liveIds[String(state.routeCalc.end.id)];
      if (startGone || endGone) resetRouteCalc();
      else applyRouteCalcHighlight();
    }

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
    });
    // 팬 보정 이중화(Z8): idle(줌/팬 애니메이션 정착 후 1회)이 정본이나, 스테이징
    // 실측에서 idle 단독 배선이 미보정으로 남는 사례가 있어 bounds_changed
    // 디바운스(250ms)를 병행 배선한다. keepMarkersInView 는 멱등(보정 후 재진입
    // 시 anyVisible=true → no-op)이라 이중 발화 부작용이 없고, panTo 가 유발하는
    // bounds_changed/idle 재발화도 같은 이유로 루프가 되지 않는다.
    maps.event.addListener(map, 'idle', function () {
      console.debug('[kmap] idle fired');
      keepMarkersInView();
    });
    var boundsDebounce = null;
    maps.event.addListener(map, 'bounds_changed', function () {
      if (boundsDebounce) window.clearTimeout(boundsDebounce);
      boundsDebounce = window.setTimeout(keepMarkersInView, 250);
    });
    state.map = map;
    state.mapEl = mapEl;
    return map;
  }

  function renderInto(container, markers, opts) {
    ensureMap(container);
    var result = drawMarkers(markers || [], opts);
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
     * opts: { routeMode }
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
    /** 폴링 갱신: 뷰포트 유지한 채 마커만 재구성. */
    updateMarkers: function (container, markers, opts) {
      if (!this.isActive() || !sdkReady()) return;
      try {
        renderInto(container, markers || [], Object.assign({}, opts || {}, { preserveView: true }));
      } catch (e) {
        console.warn('[map-view-kakao] 마커 갱신 실패', e);
      }
    },
    /**
     * QA 진단 훅(read-only, 운영 무해): 헤드리스 검증이 IIFE 은닉 상태를 볼 수
     * 있게 지도 레벨·중심·마커 매핑/가시 수를 노출한다. DOM/지도 상태 무변경.
     */
    _debug: function () {
      var out = {
        level: null, center: null,
        markerCount: state.markerItems.length,
        mappedCount: 0, visibleInBounds: 0,
        routeCalc: {
          start: state.routeCalc.start ? state.routeCalc.start.id : null,
          end: state.routeCalc.end ? state.routeCalc.end.id : null,
          hasLine: !!state.routeCalc.line
        }
      };
      if (!state.map) return out;
      try {
        out.level = state.map.getLevel();
        var c = state.map.getCenter();
        out.center = { lat: c.getLat(), lng: c.getLng() };
        var bounds = state.map.getBounds();
        var containFn = bounds.contain || bounds.contains;
        state.markerItems.forEach(function (item) {
          if (!item.overlay.getMap()) return;
          out.mappedCount++;
          if (typeof containFn === 'function' && containFn.call(bounds, item.overlay.getPosition())) {
            out.visibleInBounds++;
          }
        });
      } catch (e) {
        out.error = String(e);
      }
      return out;
    }
  };
})();
