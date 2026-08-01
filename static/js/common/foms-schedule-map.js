/**
 * FOMS 공용 일정 지도 모듈 — 기준 지점 ↔ 대상 시공지 경로를 카카오 지도로 그린다.
 *
 * 왜 공용인가: AS 대시보드의 "가까운 일정 찾기"와 출고 대시보드의 "AS 일정 추천"이
 * 같은 `#scheduleMapModal` 마크업 + 같은 `/api/calculate_route` 를 쓰는데도 렌더러가
 * 두 종류(카카오 지도 / OpenStreetMap 타일)로 갈라져 있었다. 지도 스택·레이스 가드·경로 캐시·폴백
 * 문구를 한 곳에 두어 두 표면이 항상 같이 움직이게 한다.
 *
 * 호출부:
 *  - static/js/cs/as-dashboard.js       (`.schedule-map-btn` 위임)
 *  - static/js/shipment/shipment-dashboard.js (`.js-shipment-as-rec-map` 위임)
 *
 * 모듈이 소유하는 것: 카카오 SDK 1회 주입, generation 토큰(모달 연속 오픈 레이스),
 * 경로 응답 캐시, 컨테이너 초기화, `hidden.bs.modal` 정리, SDK 차단/경로 실패 폴백.
 *
 * 엘리먼트는 **호출자가 넘긴다**. 출고 대시보드는 프래그먼트 스왑 대비로
 * `#scheduleMapModal` 을 body 로 재부모화하므로 모듈이 document.getElementById 로
 * 찾으면 옛 노드를 잡을 수 있다.
 *
 * 지도 컨테이너·핀·경로정보 CSS 는 전역
 * static/css/foundation/erp-pro/09-mobile-erp-optimization.css 소관.
 */
(function () {
  'use strict';

  // 프래그먼트 스왑으로 이 파일이 재실행돼도 상태(gen·캐시)를 유지한다(가드 G4).
  if (window.FOMS_SCHEDULE_MAP) return;

  var routeCache = new Map();
  var gen = 0;
  var activeMap = null;

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function truncateAddr(s, maxLen) {
    var t = String(s || '').trim();
    if (t.length <= maxLen) return t;
    return t.slice(0, maxLen) + '…';
  }

  function routeCacheKey(lat1, lng1, lat2, lng2) {
    return [lat1, lng1, lat2, lng2].map(function (v) {
      return Number(v).toFixed(6);
    }).join(',');
  }

  /**
   * 카카오 지도 JS SDK를 사용 시점에 1회만 주입한다(전역 로드 금지 · 가드 G2).
   * @param {string} jsKey 카카오 JS 앱 키(geocode_config SSOT → data-kakao-js-key).
   * @returns {Promise<boolean>} SDK 사용 가능 여부(미등록 도메인·네트워크 차단 시 false).
   */
  function loadKakaoSdk(jsKey) {
    if (window.kakao && window.kakao.maps && window.kakao.maps.Map) return Promise.resolve(true);
    if (window.__fomsKakaoSdkPromise) return window.__fomsKakaoSdkPromise;
    if (!jsKey) return Promise.resolve(false);
    window.__fomsKakaoSdkPromise = new Promise(function (resolve) {
      var s = document.createElement('script');
      s.id = 'foms-kakao-maps-sdk';
      s.async = true;
      s.src = 'https://dapi.kakao.com/v2/maps/sdk.js?appkey=' +
        encodeURIComponent(jsKey) + '&autoload=false';
      s.onload = function () {
        if (!window.kakao || !window.kakao.maps || !window.kakao.maps.load) { resolve(false); return; }
        window.kakao.maps.load(function () {
          resolve(!!(window.kakao.maps && window.kakao.maps.Map));
        });
      };
      // 카카오 콘솔 미등록 도메인은 sdk.js 가 401 → onerror. 지도만 포기하고 경로 정보는 살린다.
      s.onerror = function () { resolve(false); };
      document.head.appendChild(s);
    });
    return window.__fomsKakaoSdkPromise;
  }

  /**
   * 지도 위 라벨 핀 1개를 올린다(카카오 기본 마커는 색 구분이 안 되므로 CustomOverlay 사용).
   * @param {object} map 카카오 지도 인스턴스.
   * @param {number} lat 위도.
   * @param {number} lng 경도.
   * @param {string} modifierClass 색 구분 클래스(schedule-map-pin--from|--to).
   * @param {string} label 핀에 표시할 짧은 라벨.
   * @param {string} title 네이티브 툴팁으로 보여줄 전체 주소.
   * @returns {void}
   */
  function addPin(map, lat, lng, modifierClass, label, title) {
    var el = document.createElement('span');
    el.className = 'schedule-map-pin ' + modifierClass;
    el.textContent = label;
    el.title = title || '';
    new window.kakao.maps.CustomOverlay({
      map: map,
      position: new window.kakao.maps.LatLng(lat, lng),
      content: el,
      yAnchor: 1.2
    });
  }

  /**
   * 기준↔대상 두 지점을 카카오 지도에 그린다.
   * @param {HTMLElement} container 지도 컨테이너(비워진 상태여야 한다).
   * @param {{lat: number, lng: number, address: string}} ref 기준 지점.
   * @param {{lat: number, lng: number, address: string, name: string}} target 대상 지점.
   * @returns {object} 생성된 카카오 지도 인스턴스(폴리라인 추가용).
   */
  function renderMap(container, ref, target) {
    var maps = window.kakao.maps;
    var map = new maps.Map(container, { center: new maps.LatLng(ref.lat, ref.lng), level: 8 });
    activeMap = map;
    addPin(map, ref.lat, ref.lng, 'schedule-map-pin--from', '기준', truncateAddr(ref.address, 80));
    addPin(map, target.lat, target.lng, 'schedule-map-pin--to', target.name || '시공지', target.address);
    var bounds = new maps.LatLngBounds();
    bounds.extend(new maps.LatLng(ref.lat, ref.lng));
    bounds.extend(new maps.LatLng(target.lat, target.lng));
    function fit() {
      try { map.setBounds(bounds, 40, 40, 40, 40); } catch (e) { /* fit 실패 시 center/level 유지 */ }
    }
    fit();
    // 모달 전환 직후 컨테이너 크기가 늦게 확정되는 경우 0-사이즈 init 방어(카카오는 자동 복구 없음).
    requestAnimationFrame(function () {
      if (activeMap !== map) return;
      try { map.relayout(); } catch (e) { /* relayout 실패 무해 */ }
      fit();
    });
    return map;
  }

  /**
   * 경로정보 패널을 그리고 폴리라인 좌표를 돌려준다.
   * @returns {Promise<Array|null>} route_coords 또는 실패 시 null.
   */
  function loadRoute(routeInfoEl, ref, target, scoreText, myGen) {
    var cacheKey = routeCacheKey(ref.lat, ref.lng, target.lat, target.lng);
    var cached = routeCache.get(cacheKey);
    var fetched = cached
      ? Promise.resolve(cached)
      : fetch(
        '/api/calculate_route?start_lat=' + encodeURIComponent(ref.lat) +
        '&start_lng=' + encodeURIComponent(ref.lng) +
        '&end_lat=' + encodeURIComponent(target.lat) +
        '&end_lng=' + encodeURIComponent(target.lng)
      ).then(function (res) {
        if (res.status === 429) throw new Error('RATE_LIMIT');
        return res.json();
      }).then(function (json) {
        if (json && json.success) routeCache.set(cacheKey, json);
        return json;
      });

    return fetched.then(function (routeJson) {
      if (myGen !== gen) return null;
      if (routeJson && routeJson.success && routeJson.data &&
          routeJson.data.route_coords && routeJson.data.route_coords.length > 0) {
        var routeData = routeJson.data;
        var summ = routeData.summary || {};
        var distT = summ.distance_text != null ? summ.distance_text : (routeData.distance_km + 'km');
        var durT = summ.duration_text != null ? summ.duration_text : ((routeData.duration_min || 0) + '분');
        var tollT = summ.toll_text != null ? summ.toll_text : '—';
        routeInfoEl.innerHTML =
          '<div class="schedule-map-route-info">' +
          '<h6><i class="fas fa-car-side me-1"></i> 경로 정보</h6>' +
          '<div class="mb-1"><strong>출발:</strong> ' + esc(ref.address) + '</div>' +
          '<div class="mb-1"><strong>도착:</strong> ' + esc(target.address) + '</div>' +
          '<div class="mb-1"><strong>거리:</strong> ' + esc(distT) + '</div>' +
          '<div class="mb-1"><strong>소요시간:</strong> ' + esc(durT) + '</div>' +
          '<div><strong>통행료:</strong> ' + esc(tollT) + '</div>' +
          '</div>';
        return routeData.route_coords;
      }
      throw new Error((routeJson && routeJson.error) ? String(routeJson.error) : 'ROUTE_FAIL');
    }).catch(function (err) {
      // 서버 원인(예: KAKAO_REST_API_KEY 미설정)은 콘솔에 남긴다 — 사용자 문구는 그대로.
      console.warn('[foms-schedule-map] 경로 계산 실패', err);
      if (myGen !== gen) return null;
      var msg = (err && err.message === 'RATE_LIMIT')
        ? '요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.'
        : '자동차 경로를 계산하지 못했습니다. 직선거리를 참고해 주세요.';
      var hint = scoreText
        ? ('<p class="mb-0 small mt-2">직선거리 참고: ' + esc(scoreText) + '</p>')
        : '';
      routeInfoEl.innerHTML =
        '<div class="alert alert-warning mb-0" role="alert">' +
        '<strong>경로 계산 실패</strong>' +
        '<p class="mb-0 small">' + esc(msg) + '</p>' +
        hint +
        '</div>';
      return null;
    });
  }

  /**
   * 지도 모달을 열고 기준↔대상 경로를 그린다.
   *
   * @param {object} opts
   * @param {HTMLElement} opts.modalEl 부트스트랩 모달 루트(`#scheduleMapModal`). 필수.
   * @param {HTMLElement} [opts.containerEl] 지도 컨테이너. 생략 시 modalEl 안의 `#scheduleMapContainer`.
   * @param {HTMLElement} [opts.routeInfoEl] 경로정보 패널. 생략 시 modalEl 안의 `#scheduleMapRouteInfo`.
   * @param {string} [opts.kakaoJsKey] 카카오 JS 키. 생략 시 containerEl.dataset.kakaoJsKey.
   * @param {{lat: number, lng: number, address: string}} opts.ref 기준 지점(출발).
   * @param {{lat: number, lng: number, address: string, name: string}} opts.target 대상 지점(도착).
   * @param {string} [opts.scoreText] 경로 실패 시 보여줄 직선거리 힌트.
   * @returns {void}
   */
  function open(opts) {
    var o = opts || {};
    var modalEl = o.modalEl;
    var ref = o.ref || {};
    var target = o.target || {};
    if (!modalEl || typeof bootstrap === 'undefined') return;
    if (!Number.isFinite(Number(ref.lat)) || !Number.isFinite(Number(ref.lng))) return;
    if (!Number.isFinite(Number(target.lat)) || !Number.isFinite(Number(target.lng))) return;

    var routeInfoEl = o.routeInfoEl || modalEl.querySelector('#scheduleMapRouteInfo');
    if (!routeInfoEl) return;

    var myGen = ++gen;
    var scoreText = o.scoreText || '';
    routeInfoEl.innerHTML = '<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm me-2" role="status"></div>경로 계산 중...</div>';

    var onShown = function () {
      if (myGen !== gen) return;

      var container = o.containerEl || modalEl.querySelector('#scheduleMapContainer');
      if (!container) return;
      container.replaceChildren();
      activeMap = null;

      // 카카오 지도는 destroy API 가 없다 — 닫을 때 컨테이너를 비워 타일·오버레이 DOM 을 놓아준다.
      modalEl.addEventListener('hidden.bs.modal', function () {
        activeMap = null;
        container.replaceChildren();
      }, { once: true });

      // 지도 렌더와 경로 조회는 독립 — SDK 가 막힌 환경(카카오 콘솔 미등록 도메인)에서도
      // 거리·소요시간 텍스트는 그대로 나온다. 폴리라인만 둘 다 준비됐을 때 그린다.
      var mapReady = loadKakaoSdk(o.kakaoJsKey || container.dataset.kakaoJsKey || '').then(function (ok) {
        if (myGen !== gen || !container.isConnected) return null;
        if (!ok) {
          var warn = document.createElement('div');
          warn.className = 'schedule-map-unavailable';
          warn.textContent = '지도를 불러오지 못했습니다. 아래 경로 정보를 확인해 주세요.';
          container.replaceChildren(warn);
          return null;
        }
        return renderMap(container, ref, target);
      });

      Promise.all([mapReady, loadRoute(routeInfoEl, ref, target, scoreText, myGen)]).then(function (results) {
        var map = results[0];
        var coords = results[1];
        if (!map || !coords || myGen !== gen || activeMap !== map) return;
        var maps = window.kakao.maps;
        var path = coords.map(function (c) { return new maps.LatLng(c[0], c[1]); });
        new maps.Polyline({
          map: map, path: path, strokeWeight: 5, strokeColor: '#ff4757', strokeOpacity: 0.8
        });
        var bounds = new maps.LatLngBounds();
        path.forEach(function (p) { bounds.extend(p); });
        try { map.setBounds(bounds, 40, 40, 40, 40); } catch (e) { /* fit 실패 시 두 지점 bounds 유지 */ }
      });
    };

    modalEl.addEventListener('shown.bs.modal', onShown, { once: true });
    // getOrCreateInstance: 프래그먼트 스왑으로 modalEl 이 교체돼도 새 엘리먼트 인스턴스를 얻는다.
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  window.FOMS_SCHEDULE_MAP = { open: open };
})();
