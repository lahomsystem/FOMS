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
    DELIVERED: '#20c997', CANCELLED: '#dc3545', ON_HOLD: '#fd7e14',
    AS_RECEIVED: '#dc3545', AS: '#fd7e14', AS_COMPLETED: '#6c757d'
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
  // 팝업 zIndex 서열 정본: 개별 핀 2 < 겹침 그룹 대표 300대 < 스크린 클러스터 대표 400 < 팝업.
  // (구값 60은 클러스터 xN 뱃지(400)가 팝업을 가리는 결함 — 항상 마커류 위여야 한다)
  var POPUP_ZINDEX = 500;

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
    onOpenDetail: null,  // 팝업 [상세] 호출부 주입 핸들러(AS 지도 등) — 미주입 시 기존 폴백 체인
    screenClusters: [],  // 스크린 겹침 클러스터 [{repMarker, markers[]}] — applyScreenClusters 소유
    // 주문↔주문 경로 계산(folium 파리티): 출발/도착 선택 + 실도로 폴리라인 + 결과 패널.
    // line/panel 은 마커 재렌더(clearOverlays)와 독립 수명 — 폴링에도 결과 유지.
    routeCalc: { start: null, end: null, line: null, panel: null }
  };

  // 모바일 게이트 — SSOT(foms-shell.css:11 / map-mobile.css)와 바이트 동일.
  var MOBILE_GATE = '(max-width: 991.98px), ((min-width: 992px) and (pointer: coarse) and (orientation: portrait))';

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function isMobileView() {
    return !!(window.matchMedia && window.matchMedia(MOBILE_GATE).matches);
  }

  // 팝업 [주문 상세 보기]: 호출부 주입 핸들러(onOpenDetail, AS 지도 등) 최우선,
  // 없으면 모바일 시트 훅, 마지막으로 기존 selectOrder 폴백.
  function openOrderDetailFromPopup(orderId) {
    if (typeof state.onOpenDetail === 'function') {
      state.onOpenDetail(Number(orderId));
      return;
    }
    var sheet = window.FomsMapMobileSheet;
    if (sheet && typeof sheet.openDetail === 'function') {
      sheet.openDetail(Number(orderId));
      return;
    }
    if (typeof window.selectOrder === 'function') window.selectOrder(Number(orderId));
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

  // ---------- AS 지도 v3: as 모드 표시 분기 ----------
  // 판정: 서버 as 페이로드에만 as_bucket 존재(foms/services/map_snapshot.py
  // apply_as_map_display_fields) — 전역 플래그 불필요, folium 폴백 무영향.
  // 버킷 색은 map_view.html 카드 .as-bucket-badge 팔레트와 동기(변경 시 양쪽).
  var AS_BUCKET_COLORS = {
    visit_confirmed: '#2b8a3e', pending: '#d9480f',
    unassigned: '#495057', paid_unconfirmed: '#7048e8'
  };

  // as 모드 핀(pill) 테마 — 버킷별 파스텔 배경 + 동계열 진한 글자/테두리(사용자 확정:
  // 파스텔톤·상호 확실히 구별). 필터 select(#as-bucket-filter) 옵션과 1:1.
  // 흰 테두리 대신 동계열 중간톤 — 밝은 지도 타일 위에서 파스텔끼리 뭉개지지 않게.
  var AS_BUCKET_PILL_THEME = {
    visit_confirmed: { bg: '#b2f2bb', border: '#69db7c', text: '#2b8a3e' },   // 초록
    pending: { bg: '#ffd8a8', border: '#ffa94d', text: '#d9480f' },          // 주황
    unassigned: { bg: '#a5d8ff', border: '#4dabf7', text: '#1971c2' },       // 파랑(회색은 지도 타일에 묻힘 — 사용자 피드백)
    paid_unconfirmed: { bg: '#d0bfff', border: '#9775fa', text: '#5f3dc4' }  // 보라
  };

  function isAsPoint(m) {
    return !!m && m.as_bucket != null;
  }

  function asBucketColor(m) {
    return AS_BUCKET_COLORS[String(m.as_bucket || '')] || '#495057';
  }

  // 방문일 표기(카드와 동일 규칙): 미정=주황, 지남=빨강 "N일 지남", D-3 이내=빨강 강조.
  function asVisitHtml(m) {
    if (!m.as_visit_date) return '<span class="foms-kmap-as-undecided">미정</span>';
    var dateText = escapeHtml(m.as_visit_date);
    var dday = m.as_visit_dday;
    if (dday == null) return dateText;
    if (dday < 0) return dateText + ' <span class="foms-kmap-as-danger">' + (-dday) + '일 지남</span>';
    var label = dday === 0 ? 'D-DAY' : 'D-' + dday;
    return dateText + ' <span class="' + (dday <= 3 ? 'foms-kmap-as-danger' : 'foms-kmap-as-dday') + '">' + label + '</span>';
  }

  // 그룹/클러스터 행용 축약: 'M/D' 또는 '미정'.
  function asVisitShort(m) {
    var parts = String(m.as_visit_date || '').slice(0, 10).split('-');
    if (parts.length === 3 && parts[0].length === 4) {
      return Number(parts[1]) + '/' + Number(parts[2]);
    }
    return m.as_visit_date ? String(m.as_visit_date) : '미정';
  }

  // ---------- 마커 테마 (서버 _get_marker_theme 포팅) ----------
  function markerTheme(m) {
    // as 모드: 버킷 파스텔색 최우선 — 중복 핑크보다 앞(같은 주소 묶임은 xN 뱃지가
    // 이미 표시하므로 색 채널은 버킷 분류에 양보. 사용자 확정 2026-08-06).
    if (isAsPoint(m)) {
      var asTheme = AS_BUCKET_PILL_THEME[String(m.as_bucket || '')];
      if (asTheme) return asTheme;
    }
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

  // 팝업 DOM 이벤트가 지도 제스처로 새는 것 차단 — 휠은 리스트 스크롤 대신 줌,
  // 드래그는 팬으로 먹히던 결함의 근본 수정. preventDefault는 하지 않는다
  // (팝업 내부 네이티브 스크롤·클릭·버튼은 살아야 함).
  function guardPopupEvents(el) {
    ['wheel', 'mousedown', 'touchstart', 'dblclick'].forEach(function (type) {
      el.addEventListener(type, function (e) { e.stopPropagation(); });
    });
  }

  // 팝업이 지도 컨테이너 밖으로 잘리면 잘린 픽셀만큼만 팬(카카오 autopan 부재 보완).
  // PC 전용 — 모바일 컴팩트 카드는 뷰포트 기준 스킨이라 보정 대상 아님.
  function panPopupIntoView(el) {
    if (isMobileView()) return;
    if (!state.popup || !state.map || !state.mapEl || !el.isConnected) return;
    try {
      var p = el.getBoundingClientRect();
      var c = state.mapEl.getBoundingClientRect();
      var PAD = 8, dx = 0, dy = 0;
      if (p.left < c.left + PAD) dx = p.left - (c.left + PAD);
      else if (p.right > c.right - PAD) dx = p.right - (c.right - PAD);
      if (p.top < c.top + PAD) dy = p.top - (c.top + PAD);
      else if (p.bottom > c.bottom - PAD) dy = p.bottom - (c.bottom - PAD);
      if (dx || dy) state.map.panBy(dx, dy);
    } catch (e) { /* 팬 보정 실패 무해 */ }
  }

  // 팝업 공통 마운트: 이벤트 가드 + 오버레이 생성 + 화면 밖 잘림 보정.
  function mountPopup(el, position) {
    guardPopupEvents(el);
    state.popup = new window.kakao.maps.CustomOverlay({
      map: state.map, position: position, content: el,
      xAnchor: 0.5, yAnchor: 1.15, zIndex: POPUP_ZINDEX
    });
    setTimeout(function () { panPopupIntoView(el); }, 0);
  }

  function openPopup(m, position) {
    closePopup();
    var statusColor = STATUS_COLORS[String(m.status || '').toUpperCase()] || STATUS_FALLBACK_COLOR;
    var dupRow = m.__dupSize > 1
      ? '<tr><th>중복</th><td>' + m.__dupSize + '건 같은 주소</td></tr>' : '';
    var mobile = isMobileView();
    var asMode = isAsPoint(m);
    // 칩(모바일 헤더): as=버킷 분류(색 동기), measurement=상태 — 색은 데이터 주도라 동적.
    var chipColor = asMode ? asBucketColor(m) : statusColor;
    var chipText = asMode ? (m.as_bucket_label || '-') : (m.status || '-');
    var metaLine = asMode
      ? '방문일 ' + asVisitHtml(m)
      : escapeHtml(m.measurement_time || '실측 시간 미정');
    // PC 테이블: as 모드는 AS 정보 중심(스펙 F3) — 담당자·제품·상태·좌표 행 없음,
    // 분류·방문일 D-day·AS 내용·유무상·AS 접수일 추가. measurement는 기존 그대로.
    var tableRows = asMode
      ? '<tr><th>고객명</th><td>' + escapeHtml(m.customer_name || '-') + '</td></tr>' +
        '<tr><th>연락처</th><td>' + escapeHtml(m.phone || '-') + '</td></tr>' +
        '<tr><th>주소</th><td>' + escapeHtml(m.address || '-') + '</td></tr>' +
        '<tr><th>분류</th><td><span style="color:' + asBucketColor(m) + ';font-weight:700">' +
        escapeHtml(m.as_bucket_label || '-') + '</span></td></tr>' +
        '<tr><th>방문일</th><td>' + asVisitHtml(m) + '</td></tr>' +
        (m.as_content_preview
          ? '<tr><th>AS 내용</th><td>' + escapeHtml(m.as_content_preview) + '</td></tr>' : '') +
        (m.as_recent_log_preview
          ? '<tr><th>최근 기록</th><td>' + escapeHtml(m.as_recent_log_preview) + '</td></tr>' : '') +
        '<tr><th>유무상</th><td>' + escapeHtml(m.as_billing_text || '-') + '</td></tr>' +
        (m.as_availability_label
          ? '<tr><th>가능시간</th><td>' + escapeHtml(m.as_availability_label) + '</td></tr>' : '') +
        '<tr><th>AS 접수일</th><td>' + escapeHtml(m.as_received_date || '-') + '</td></tr>' +
        dupRow
      : '<tr><th>고객명</th><td>' + escapeHtml(m.customer_name || '-') + '</td></tr>' +
        '<tr><th>담당자</th><td>' + escapeHtml(m.manager_name || '-') + '</td></tr>' +
        '<tr><th>연락처</th><td>' + escapeHtml(m.phone || '-') + '</td></tr>' +
        '<tr><th>주소</th><td>' + escapeHtml(m.address || '-') + '</td></tr>' +
        '<tr><th>제품</th><td>' + escapeHtml(m.product || '-') + '</td></tr>' +
        '<tr><th>상태</th><td style="color:' + statusColor + '">' + escapeHtml(m.status || '-') + '</td></tr>' +
        (m.as_availability_label
          ? '<tr><th>가능시간</th><td>' + escapeHtml(m.as_availability_label) + '</td></tr>' : '') +
        '<tr><th>접수일</th><td>' + escapeHtml(m.received_date || '-') + '</td></tr>' +
        '<tr><th>좌표</th><td>' + Number(m.latitude).toFixed(6) + ', ' + Number(m.longitude).toFixed(6) + '</td></tr>' +
        dupRow;
    // 모바일: 컴팩트 카드(상세는 시트에서). PC: 테이블.
    var body = mobile
      ? '<div class="foms-kmap-popup__m-body">' +
        '<div class="foms-kmap-popup__m-name">' +
        '<span class="foms-kmap-popup__m-cust">' + escapeHtml(m.customer_name || '-') + '</span>' +
        '<span class="foms-kmap-popup__m-chip" style="color:' + chipColor + '">' + escapeHtml(chipText) + '</span>' +
        '</div>' +
        '<div class="foms-kmap-popup__m-meta">' + metaLine +
        (m.__dupSize > 1 ? ' · 같은 주소 ' + m.__dupSize + '건' : '') + '</div>' +
        '<div class="foms-kmap-popup__m-addr" title="' + escapeHtml(m.address || '-') + '">' +
        escapeHtml(m.address || '-') + '</div>' +
        '</div>'
      : '<table class="foms-kmap-popup__table">' + tableRows + '</table>';
    var el = document.createElement('div');
    el.className = 'foms-kmap-popup';
    el.innerHTML =
      '<div class="foms-kmap-popup__head">' +
      '<strong>주문 #' + escapeHtml(m.id) + '</strong>' +
      '<button type="button" class="foms-kmap-popup__close" aria-label="닫기">&times;</button>' +
      '</div>' +
      body +
      '<div class="foms-kmap-popup__actions' + (mobile ? ' foms-kmap-popup__actions--m' : '') + '">' +
      '<button type="button" class="btn btn-sm btn-outline-danger foms-kmap-popup__route">' + routeCalcBtnLabel(m) + '</button>' +
      '<button type="button" class="btn btn-sm btn-primary foms-kmap-popup__detail">주문 상세 보기</button>' +
      '</div>';
    el.querySelector('.foms-kmap-popup__close').addEventListener('click', closePopup);
    el.querySelector('.foms-kmap-popup__detail').addEventListener('click', function () {
      // 모바일은 상세가 풀시트로 덮으므로 팝업을 먼저 닫는다(PC 동작 무변경).
      if (isMobileView()) closePopup();
      openOrderDetailFromPopup(m.id);
    });
    // 주문↔주문 경로 계산: 출발/도착 선택(route 모드 순번 핀 팝업에서도 동일 동작).
    el.querySelector('.foms-kmap-popup__route').addEventListener('click', function () {
      closePopup();
      onRouteCalcAction(m);
    });
    mountPopup(el, position);
  }

  // 접힌 대표 마커/스크린 클러스터 클릭 팝업: 그룹 내 주문 목록(+각 상세 보기).
  // opts: { title, fitBounds } — fitBounds=스크린 클러스터(주소 상이)용, 펼치면 bounds 줌인.
  function openGroupPopup(markersInGroup, position, opts) {
    opts = opts || {};
    closePopup();
    var rows = markersInGroup.map(function (m) {
      var statusColor = STATUS_COLORS[String(m.status || '').toUpperCase()] || STATUS_FALLBACK_COLOR;
      // as 모드: 실측시간 자리에 방문일 M/D(미정 포함) — 동선 판단 1차 정보(스펙 F3).
      var timePart = isAsPoint(m)
        ? ' · ' + escapeHtml(asVisitShort(m))
        : (m.measurement_time ? ' · ' + escapeHtml(m.measurement_time) : '');
      return '<div class="foms-kmap-popup__group-row">' +
        '<span class="foms-kmap-popup__group-main">' +
        '<span class="foms-kmap-popup__status-dot" style="background:' + statusColor + '"></span>' +
        '<strong>#' + escapeHtml(m.id) + '</strong> ' + escapeHtml(m.customer_name || '-') +
        timePart +
        '</span>' +
        '<button type="button" class="btn btn-sm btn-outline-primary" data-order-id="' + escapeHtml(m.id) + '">상세</button>' +
        '</div>';
    }).join('');
    var el = document.createElement('div');
    el.className = 'foms-kmap-popup';
    el.innerHTML =
      '<div class="foms-kmap-popup__head">' +
      '<strong>' + escapeHtml(opts.title || ('같은 위치 ' + markersInGroup.length + '건')) + '</strong>' +
      '<button type="button" class="foms-kmap-popup__close" aria-label="닫기">&times;</button>' +
      '</div>' +
      '<div class="foms-kmap-popup__group">' +
      (opts.fitBounds ? '' :
        '<div class="foms-kmap-popup__group-addr">' + escapeHtml(markersInGroup[0].address || '-') + '</div>') +
      rows +
      '</div>' +
      '<div class="foms-kmap-popup__actions' + (isMobileView() ? ' foms-kmap-popup__actions--m' : '') + '">' +
      '<button type="button" class="btn btn-sm btn-outline-danger foms-kmap-popup__route">' + routeCalcBtnLabel(markersInGroup[0]) + '</button>' +
      '<button type="button" class="btn btn-sm btn-primary foms-kmap-popup__expand">펼쳐 보기</button>' +
      '</div>';
    el.querySelector('.foms-kmap-popup__close').addEventListener('click', closePopup);
    // 그룹 중심 확대: 임계 통과(격자 펼침)로 직행 — 중심 고정 줌으로 그룹이
    // 화면 밖으로 흘러나가는 문제를 앵커 지정으로 원천 회피.
    // 스크린 클러스터(fitBounds)는 좌표가 서로 달라 bounds 줌인이 정본 —
    // 단 좌표 스팬이 사실상 0이면(전원 같은 지점) 기존 앵커 줌으로 폴백.
    el.querySelector('.foms-kmap-popup__expand').addEventListener('click', function () {
      closePopup();
      try {
        if (opts.fitBounds) {
          var minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
          markersInGroup.forEach(function (m) {
            minLat = Math.min(minLat, m.latitude); maxLat = Math.max(maxLat, m.latitude);
            minLng = Math.min(minLng, m.longitude); maxLng = Math.max(maxLng, m.longitude);
          });
          if ((maxLat - minLat) > 1e-6 || (maxLng - minLng) > 1e-6) {
            var b = new window.kakao.maps.LatLngBounds(
              new window.kakao.maps.LatLng(minLat, minLng),
              new window.kakao.maps.LatLng(maxLat, maxLng));
            state.map.setBounds(b, 60, 60, 60, 60);
            return;
          }
        }
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
        if (isMobileView()) closePopup();
        openOrderDetailFromPopup(btn.getAttribute('data-order-id'));
      });
    });
    mountPopup(el, position);
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

  // ---------- 스크린 겹침 클러스터 (원거리 pill 잘림 대응, 2026-08-06) ----------
  // 같은 주소 그룹(x2 접기)과 별개로, 주소가 달라도 화면(px)상 pill이 겹치면
  // 대표 1개 + xN 뱃지(동일 룩 재사용)로 묶는다. 접힘 뷰(level>=6)에서만 동작,
  // route 모드 제외. 팬은 같은 줌에서 상대 위치를 바꾸지 않으므로 줌/재렌더 시에만 재계산.
  // 그리드 셀 방식: AABB 겹침 union은 밀집 지역에서 사슬 병합(transitive chain)으로
  // 전국 뷰가 클러스터 1개로 뭉개진다(스테이징 실측: 55건 → x53). 셀 경계가 사슬을
  // 끊어 지역 단위 묶음을 보존한다. 셀 크기 ≈ pill 1개 박스.
  var CLUSTER_CELL_W = 112;
  var CLUSTER_CELL_H = 44;

  function resetScreenClusters() {
    state.screenClusters = [];
    state.markerItems.forEach(function (item) {
      var badge = item.pill.querySelector('[data-cluster-badge]');
      if (badge) badge.remove();
      var dupBadge = item.pill.querySelector('.foms-kmap-pill__dup');
      if (dupBadge) dupBadge.style.display = '';
    });
  }

  function findScreenCluster(marker) {
    for (var i = 0; i < state.screenClusters.length; i++) {
      if (state.screenClusters[i].repMarker === marker) return state.screenClusters[i];
    }
    return null;
  }

  function setClusterBadge(item, total) {
    var dupBadge = item.pill.querySelector('.foms-kmap-pill__dup');
    if (dupBadge) dupBadge.style.display = 'none';
    var badge = document.createElement('span');
    badge.className = 'foms-kmap-pill__dup';
    badge.setAttribute('data-cluster-badge', '1');
    badge.textContent = 'x' + total;
    item.pill.appendChild(badge);
    item.pill.title = item.pill.title + ' · 주변 ' + total + '건';
  }

  function applyScreenClusters() {
    resetScreenClusters();
    if (!state.map || !state.markerItems.length) return;
    if (state.routeMode || isExpandedView()) return;
    var projection;
    try { projection = state.map.getProjection(); } catch (e) { return; }
    if (!projection || typeof projection.containerPointFromCoords !== 'function') return;

    // 보이는 대표 pill들을 그리드 셀에 버킷팅 (CustomOverlay 앵커 기준)
    var clusters = {};
    var seen = 0;
    state.markerItems.forEach(function (item) {
      if (!item.overlay.getMap()) return; // 동일주소 접기로 숨은 비대표 제외
      var pt;
      try {
        pt = projection.containerPointFromCoords(
          new window.kakao.maps.LatLng(item.marker.latitude, item.marker.longitude));
      } catch (e) { return; }
      seen++;
      var key = Math.floor(pt.x / CLUSTER_CELL_W) + ':' + Math.floor(pt.y / CLUSTER_CELL_H);
      (clusters[key] = clusters[key] || []).push(item);
    });
    if (seen < 2) return;

    Object.keys(clusters).forEach(function (cellKey) {
      var items = clusters[cellKey];
      if (items.length <= 1) return;
      // 대표 = 최신 주문(id 큰 것) — 줌 변화에도 안정적인 명시 기준
      items.sort(function (a, b) { return Number(b.marker.id) - Number(a.marker.id); });
      var markers = [];
      items.forEach(function (item) {
        groupMarkersOf(item.marker).forEach(function (m) {
          if (markers.indexOf(m) === -1) markers.push(m);
        });
      });
      items.forEach(function (item, position) {
        if (position === 0) { item.overlay.setZIndex(400); return; }
        item.overlay.setMap(null);
      });
      setClusterBadge(items[0], markers.length);
      state.screenClusters.push({ repMarker: items[0].marker, markers: markers });
    });
  }

  // 접기/펼치기 + 스크린 클러스터 한 패스 — 호출부 공용 진입점
  function applyMarkerLayout() {
    applyDuplicateLayout();
    applyScreenClusters();
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
    // AS 지도: 주말 가능 건 표식(필터 안 켜도 훑어보며 인지) — 데이터 있을 때만
    if (m.as_availability && m.as_availability.days === 'weekend') {
      htmlParts += '<span class="foms-kmap-pill__wknd" title="주말 가능">주</span>';
    }
    // AS 지도 v3(F4): 방문일 미정 건은 테두리 점선 — 색 추가 없이 과밀 회피.
    if (isAsPoint(m) && !m.as_visit_date) {
      pill.classList.add('foms-kmap-pill--as-undecided');
      pill.title += ' · 방문일 미정';
    }
    if (m.__dupSize > 1) {
      htmlParts += '<span class="foms-kmap-pill__dup">x' + m.__dupSize + '</span>';
    }
    pill.innerHTML = htmlParts;

    // 오프셋/표시 여부는 applyDuplicateLayout(줌 임계 그룹 레이아웃)이 소유.
    pill.addEventListener('click', function (e) {
      e.stopPropagation();
      var pos = new window.kakao.maps.LatLng(m.latitude, m.longitude);
      // 스크린 클러스터 대표: 주변 건 목록 팝업(펼치면 클러스터 bounds로 줌인).
      var cluster = findScreenCluster(m);
      if (cluster && !state.routeMode) {
        openGroupPopup(cluster.markers, pos, {
          title: '주변 ' + cluster.markers.length + '건',
          fitBounds: true
        });
        return;
      }
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

    // 현재 줌 기준 그룹 접기/펼치기 + 스크린 클러스터 즉시 적용(폴링 재렌더 시 상태 보존).
    applyMarkerLayout();

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
      applyMarkerLayout();
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
    // 팝업 상세 핸들러 주입(옵션 미지정 시 기존 폴백 체인 유지)
    if (typeof opts.onOpenDetail === 'function') state.onOpenDetail = opts.onOpenDetail;
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
     * SDK 선로드(워밍): /api/map_data fetch 시작 전에 SDK 다운로드부터 먼저 시작해
     * 데이터 fetch 와 병렬화한다(기존엔 fetch 완료 후에야 SDK 다운로드가 시작되는 직렬 워터폴이었다).
     * loadSdk 는 상태머신(SDK_IDLE/LOADING/READY/FAILED)+waiter 큐라 재호출이 안전하다
     * (READY 면 즉시, LOADING 이면 합류). 키가 없으면 아무것도 하지 않는다. 렌더는 기존 render() 담당.
     */
    warm: function (key) {
      if (!key) return;
      loadSdk(key, function () { /* 워밍 전용 — 렌더는 render() 가 담당 */ });
    },
    /**
     * 최초/필터 변경 렌더. resolve(false)면 호출부가 folium 폴백.
     * opts: { routeMode, onOpenDetail }
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
