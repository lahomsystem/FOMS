/**
 * ERP shell: PRIMARY_NAV (9) + B5 subordinate fragment surfaces — EPT-B6 prefetch / warm nav.
 * Fetch + #main-content swap when server returns X-FOMS-ERP-FRAGMENT: 1 (view=fragment + shell header).
 * Python SSOT for 9-primary: foms.services.common.erp_navigation_contract
 * Opt-out: data-foms-erp-no-shell="1" on <a> or <form>.
 * Excluded from shell swap + prefetch: full-document map surface (B5 run record).
 */
(function () {
  'use strict';

  /** @type {string[]} 잠금판 9 primary — 문서/인벤토리와 동일 순서. */
  var PRIMARY_NAV_PATHS = [
    '/erp/dashboard',
    '/erp/measurement',
    '/erp/drawing-workbench',
    '/erp/production/dashboard',
    '/erp/shipment',
    '/erp/as',
    '/erp/construction/dashboard',
    '/erp/completion',
    '/erp/history/',
  ];

  /** @type {string[]} Server implements shell+view=fragment for these exact paths. */
  var FRAGMENT_READY_PATHS = [
    '/erp/dashboard',
    '/erp/measurement',
    '/erp/drawing-workbench',
    '/erp/production/dashboard',
    '/erp/shipment',
    '/erp/as',
    '/erp/construction/dashboard',
    '/erp/completion',
    '/erp/history/',
  ];

  var CACHE_MAX_ENTRIES = 28;
  var CACHE_TTL_MS = 5 * 60 * 1000;
  /**
   * Mutation-sensitive surfaces (other users/devices change them between visits).
   * 하트비트(HEARTBEAT_FRESH_MS=50s < 60s)가 만료 전에 항상 재프리페치하므로 사실상 영구 웜.
   * 신선도는 A2 복귀-재수혈(refreshFreshTtlSurfaces)+서버 티어 무효화가 담당. 전체 리로드는 이 캐시 우회.
   */
  var FRESH_TTL_MS = 60 * 1000;
  var FRESH_TTL_PATHS = [
    '/erp/dashboard',
    // 실측: 날짜 민감(타 사용자·기기가 행을 바꿈). 하트비트로 만료 전 갱신 + focus/bfcache 재수혈로 신선도 유지.
    // (과거엔 NO_FRAGMENT_CACHE 로 매 스왑 refetch → 5.8s. 이제 fragment 안에 마크업만 남아 warm-cache 가능.)
    '/erp/measurement',
    // 생산 보드: '도면 수정 중' 배지·[제작 시작] 막힘이 다른 사람의 수정요청·수령 확정으로 바뀐다(Q2).
    // 5분 primary 캐시면 수령 확정 뒤에도 배지가 남으므로 fresh(60s·하트비트 50s)+복귀 재수혈로 둔다.
    '/erp/production/dashboard',
  ];
  var IDLE_PREFETCH_MAX = 3;
  var HOVER_DEBOUNCE_MS = 180;
  var IDLE_DELAY_MS = 1600;
  /**
   * 하트비트 재프리페치: 캐시가 식기 전에 주기 갱신해 "일정 시간 후 첫 클릭 느림(싱가포르 왕복)→
   * 이후 빠름" 주기를 없앤다. primary 는 CACHE_TTL(5분)보다, fresh 는 FRESH_TTL(60s)보다 앞선다.
   * visible + 최근 활동(HEARTBEAT_IDLE_CUTOFF_MS 이내)일 때만 도므로 방치 탭은 자동 정지.
   */
  var HEARTBEAT_PRIMARY_MS = 240 * 1000;
  var HEARTBEAT_FRESH_MS = 50 * 1000;
  /**
   * 하트비트 스윕 스태거: primary 9발을 동시에 쏘면 각 fragment(640KB 급) 재검증이 겹쳐
   * 클라 주기 jank 를 만든다. 요청을 setTimeout 체인으로 순차 발사해 부하를 펼친다.
   * 대부분은 304(빈 바디)로 값싸게 끝나지만, 스태거는 200 이 섞일 때의 tail 을 흡수한다.
   */
  var HEARTBEAT_PRIMARY_STAGGER_MS = 600;
  var HEARTBEAT_FRESH_STAGGER_MS = 300;
  var HEARTBEAT_IDLE_CUTOFF_MS = 10 * 60 * 1000;
  /** 복귀(visibilitychange/pageshow) 재수혈 연타 방지 최소 간격. */
  var FOCUS_REFRESH_MIN_GAP_MS = 15 * 1000;
  // 셸 warm-cache 를 강제로 건너뛸 경로. 현재는 없음(실측은 FRESH_TTL_PATHS 로 이동).
  var NO_FRAGMENT_CACHE_PATHS = [];

  /** pathname+search cache key — sorted query keys, stable for warm hit / scroll memory. */
  var fragmentHtmlCache = Object.create(null);
  var fragmentCacheOrder = [];
  var inflightFetches = Object.create(null);
  /** scrollY remembered when leaving a shell URL (back/forward restore). */
  var scrollMemory = Object.create(null);
  var hoverTimer = null;

  /**
   * Rapid A→B nav race guard. Every real navigation bumps navGeneration and
   * aborts the previous nav's in-flight fetch (navAbortController). A late
   * response from a superseded nav carries a stale generation, so the commit
   * gate (isCurrent) skips its history/DOM mutation entirely — A commit 0, the
   * newer surface B is preserved. This only *tightens* commits (never adds a
   * listener/bind), so fragment re-exec stays idempotent (perf guard G4).
   */
  var navGeneration = 0;
  var navAbortController = null;
  /**
   * One-shot channel handing the current navigation's abort signal to the very
   * next fetchFragment() call, without widening its shared signature (prefetch/
   * heartbeat callers must NOT inherit a nav's abort lifecycle). Set right before
   * the nav fetch and consumed+cleared at the top of fetchFragment — both run in
   * the same synchronous tick, so no other caller can observe a stale value.
   */
  var navFetchSignal = null;

  /**
   * Wrap #main-content once so a loading overlay can sit above it without being
   * destroyed by innerHTML swaps.
   */
  function ensureShellMainWrap() {
    var main = document.getElementById('main-content');
    if (!main || main.getAttribute('data-foms-erp-shell-wrapped') === '1') {
      return main;
    }
    var parent = main.parentNode;
    if (!parent) {
      return main;
    }
    var wrap = document.createElement('div');
    wrap.className = 'foms-erp-shell-main-wrap';
    wrap.id = 'foms-erp-shell-main-wrap';
    parent.insertBefore(wrap, main);
    wrap.appendChild(main);
    var ov = document.createElement('div');
    ov.id = 'foms-erp-shell-loading-overlay';
    ov.className = 'foms-erp-shell-loading-overlay';
    ov.setAttribute('aria-hidden', 'true');
    ov.innerHTML =
      '<div class="spinner-border text-primary" role="status">' +
      '<span class="visually-hidden">로딩 중</span></div>';
    wrap.appendChild(ov);
    main.setAttribute('data-foms-erp-shell-wrapped', '1');
    return main;
  }

  /**
   * Cover #main-content before async shell navigation (e.g. mobile search result click)
   * so stale queue HTML is not visible under the overlay.
   */
  function beginShellNavigationPending() {
    ensureShellMainWrap();
    setShellFragmentLoading(true);
  }

  /** Show or hide full-fetch loading state (not used for instant cache hits). */
  function setShellFragmentLoading(on) {
    var main = ensureShellMainWrap();
    var ov = document.getElementById('foms-erp-shell-loading-overlay');
    if (!main || !ov) {
      return;
    }
    if (on) {
      ov.classList.add('is-active');
      ov.setAttribute('aria-hidden', 'false');
      main.setAttribute('aria-busy', 'true');
    } else {
      ov.classList.remove('is-active');
      ov.setAttribute('aria-hidden', 'true');
      main.removeAttribute('aria-busy');
    }
  }

  function pathOnly(url) {
    try {
      var u = new URL(url, window.location.origin);
      return u.pathname;
    } catch (e) {
      return '';
    }
  }

  function isFragmentReadyPath(url) {
    return FRAGMENT_READY_PATHS.indexOf(pathOnly(url)) >= 0;
  }

  /**
   * B5 subordinate surfaces that implement the same shell fragment contract (GET).
   * Not in FRAGMENT_READY_PATHS (non-canonical tab paths).
   */
  function isSubordinateShellFragmentPath(url) {
    var p = pathOnly(url);
    if (p === '/erp/shipment-settings') {
      return true;
    }
    if (/^\/erp\/drawing-workbench\/\d+$/.test(p)) {
      return true;
    }
    return false;
  }

  /** True when fetch+swap is allowed (9 primary + B5 subordinates). Full-document map surface excluded. */
  function isShellFragmentSwapUrl(url) {
    return isFragmentReadyPath(url) || isSubordinateShellFragmentPath(url);
  }

  function isFragmentCacheable(url) {
    return NO_FRAGMENT_CACHE_PATHS.indexOf(pathOnly(url)) === -1;
  }

  function getCacheKey(url) {
    var u = new URL(url, window.location.origin);
    var keys = [];
    u.searchParams.forEach(function (_, k) {
      if (keys.indexOf(k) === -1) {
        keys.push(k);
      }
    });
    keys.sort();
    var parts = [];
    keys.forEach(function (k) {
      var vals = u.searchParams.getAll(k);
      vals.sort();
      vals.forEach(function (v) {
        parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
      });
    });
    return u.pathname + (parts.length ? '?' + parts.join('&') : '');
  }

  function canonicalFromFetchResponse(responseUrl) {
    if (typeof responseUrl !== 'string' || !responseUrl) {
      return null;
    }
    var finalUrl;
    try {
      finalUrl = new URL(responseUrl, window.location.origin);
    } catch (e) {
      return null;
    }
    if (finalUrl.origin !== window.location.origin) {
      return null;
    }
    finalUrl.searchParams.delete('view');
    if (!isShellFragmentSwapUrl(finalUrl.href)) {
      return null;
    }
    return finalUrl;
  }

  /**
   * @param {string} key
   * @param {string} html
   * @param {string} [etag] 서버 fragment ETag — 다음 요청의 If-None-Match(조건부 304)로 재사용.
   */
  function cachePut(key, html, etag) {
    var now = Date.now();
    if (fragmentHtmlCache[key]) {
      var i = fragmentCacheOrder.indexOf(key);
      if (i >= 0) {
        fragmentCacheOrder.splice(i, 1);
      }
    }
    fragmentHtmlCache[key] = { html: html, ts: now, etag: etag || null };
    fragmentCacheOrder.push(key);
    while (fragmentCacheOrder.length > CACHE_MAX_ENTRIES) {
      var evict = fragmentCacheOrder.shift();
      delete fragmentHtmlCache[evict];
    }
  }

  /** Per-path warm-cache freshness: mutation-sensitive surfaces expire fast. */
  function cacheTtlForKey(key) {
    var path = key.split('?')[0];
    return FRESH_TTL_PATHS.indexOf(path) >= 0 ? FRESH_TTL_MS : CACHE_TTL_MS;
  }

  function cacheGet(key) {
    var row = fragmentHtmlCache[key];
    if (!row) {
      return null;
    }
    if (Date.now() - row.ts > cacheTtlForKey(key)) {
      delete fragmentHtmlCache[key];
      var ix = fragmentCacheOrder.indexOf(key);
      if (ix >= 0) {
        fragmentCacheOrder.splice(ix, 1);
      }
      return null;
    }
    return row.html;
  }

  /**
   * Drop warm fragment HTML after server-side mutations (quest approve, stage change).
   * @param {string|boolean|undefined} urlOrAll — omit or true to clear all; URL string to drop one entry.
   */
  function invalidateFragmentCache(urlOrAll) {
    if (!urlOrAll || urlOrAll === true) {
      fragmentHtmlCache = Object.create(null);
      fragmentCacheOrder.length = 0;
      return;
    }
    try {
      var canonical = new URL(String(urlOrAll), window.location.origin);
      var key = getCacheKey(canonical.href);
      delete fragmentHtmlCache[key];
      var ix = fragmentCacheOrder.indexOf(key);
      if (ix >= 0) {
        fragmentCacheOrder.splice(ix, 1);
      }
    } catch (e) {
      fragmentHtmlCache = Object.create(null);
      fragmentCacheOrder.length = 0;
    }
  }

  /** Clear cached HTML for all 9 primary ERP nav surfaces. */
  function invalidatePrimaryNavFragmentCache() {
    PRIMARY_NAV_PATHS.forEach(function (p) {
      invalidateFragmentCache(window.location.origin + p);
    });
  }

  /**
   * 셸 공용 스크립트(data-foms-run-once)는 문서당 한 번만 실행한다.
   * 9탭 조각마다 셸 머리·하단 탭·검색이 함께 들어 있어, 예전엔 탭을 바꿀 때마다 공용 스크립트
   * 19개(약 200KB)와 인라인 1개를 다시 실행했다. Alpine·htmx 는 다시 실행될 때마다 새 인스턴스를
   * 띄우고 옛 인스턴스의 문서 관찰자·리스너를 남긴다(2026-10-01 성능 검사 P2-3).
   * 이미 실행된 것은 건너뛰고, 새 DOM 연결은 각 스크립트의 foms:main-content-swapped 리스너·
   * processHtmxIn·Alpine 문서 관찰자가 맡는다.
   * 키: 외부 = 절대 src(?v= 포함 — 배포로 핀이 바뀌면 새 파일로 보고 한 번 실행),
   *     인라인 = 'inline:' + 속성 값.
   */
  var RUN_ONCE_ATTR = 'data-foms-run-once';
  /** @type {Object<string, boolean>|null} 첫 스왑 직전에 만든다. */
  var executedScriptKeys = null;

  function runOnceScriptKey(el) {
    if (el.src) {
      return el.src;
    }
    var tag = el.getAttribute(RUN_ONCE_ATTR);
    return tag ? 'inline:' + tag : '';
  }

  /** 첫 스왑 직전 한 번: 지금 문서에 있는(파서가 이미 실행했거나 곧 실행할) 스크립트를 등록한다. */
  function ensureExecutedScriptRegistry() {
    if (executedScriptKeys) {
      return;
    }
    executedScriptKeys = Object.create(null);
    document.querySelectorAll('script[src], script[' + RUN_ONCE_ATTR + ']').forEach(function (el) {
      var key = runOnceScriptKey(el);
      if (key) {
        executedScriptKeys[key] = true;
      }
    });
  }

  function activateScripts(container) {
    var nodes = container.querySelectorAll('script');
    nodes.forEach(function (old) {
      var runOnceKey = old.hasAttribute(RUN_ONCE_ATTR) ? runOnceScriptKey(old) : '';
      if (runOnceKey && executedScriptKeys && executedScriptKeys[runOnceKey]) {
        // innerHTML 로 들어온 <script> 는 실행되지 않는 빈 껍데기라 그대로 두어도 된다.
        return;
      }
      var s = document.createElement('script');
      if (runOnceKey) {
        s.setAttribute(RUN_ONCE_ATTR, old.getAttribute(RUN_ONCE_ATTR));
        if (executedScriptKeys) {
          executedScriptKeys[runOnceKey] = true;
          if (old.src) {
            // 받기 실패면 등록을 지워 다음 스왑에서 다시 시도한다.
            s.addEventListener('error', function () {
              delete executedScriptKeys[runOnceKey];
            });
          }
        }
      }
      if (old.id) {
        s.id = old.id;
      }
      // Preserve non-JS types (e.g. application/json preload tags). Without this, JSON
      // bodies execute as classic scripts and throw "Unexpected token ':'" at `{`.
      if (old.type) {
        s.type = old.type;
      }
      if (old.nonce) {
        s.nonce = old.nonce;
      }
      if (old.src) {
        s.src = old.src;
        s.async = old.async;
        s.defer = old.defer;
        if (old.crossOrigin) {
          s.crossOrigin = old.crossOrigin;
        }
        if (old.integrity) {
          s.integrity = old.integrity;
        }
      } else {
        s.textContent = old.textContent;
      }
      old.parentNode.replaceChild(s, old);
    });
  }

  function finishErpShellFragmentSwap(swapUrl) {
    try {
      document.dispatchEvent(
        new CustomEvent('foms:main-content-swapped', { detail: { url: swapUrl || '' } })
      );
    } catch (e) {
      /* ignore */
    }
    try {
      document.dispatchEvent(
        new CustomEvent('foms:erp-shell-fragment-swapped', { detail: { url: swapUrl || '' } })
      );
    } catch (e) {
      /* ignore */
    }
  }

  /**
   * Tear down any Bootstrap offcanvas/modal that is open inside the region about
   * to be replaced. Bootstrap keeps its overlay state (the backdrop element plus
   * the `<body>` scroll-lock) on `<body>`, which lives *outside* #main-content.
   * Replacing #main-content innerHTML removes the overlay element without running
   * Bootstrap's hide transition, so that body-level state is orphaned and the
   * page can no longer scroll. Disposing the instance and completing the cleanup
   * here keeps the fragment-swap navigation (e.g. the mobile filter sheet's GET
   * "적용") from freezing the page.
   * @param {HTMLElement} container
   */
  function teardownOpenOverlays(container) {
    if (!container || !window.bootstrap) {
      return;
    }
    [
      ['offcanvas', window.bootstrap.Offcanvas],
      ['modal', window.bootstrap.Modal],
    ].forEach(function (pair) {
      var kind = pair[0];
      var Ctor = pair[1];
      if (!Ctor) {
        return;
      }
      container.querySelectorAll('.' + kind + '.show').forEach(function (el) {
        var instance = Ctor.getInstance(el);
        if (instance) {
          try {
            instance.dispose();
          } catch (e) {
            /* ignore */
          }
        }
      });
    });
    document
      .querySelectorAll('.offcanvas-backdrop, .modal-backdrop')
      .forEach(function (backdrop) {
        backdrop.remove();
      });
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
  }

  /**
   * 바꿔 끼울 영역 안 요소에 붙은 Bootstrap 인스턴스를 열림 여부와 무관하게 모두 정리한다.
   * Bootstrap 은 인스턴스를 전역 Map(요소 → 인스턴스)에 강하게 쥔다. 정리하지 않으면 요소가 문서에서
   * 빠진 뒤에도 Map 이 그 요소를, 요소는 부모 사슬로 옛 화면 DOM 통째를 붙잡는다.
   * 실측(2026-10-02 힙 스냅샷): 셸 메뉴 서랍(#erp-mobile-menu-drawer — erp-mobile-shell.js 가 스왑마다
   * Offcanvas.getOrCreateInstance)이 탭을 바꿀 때마다 옛 화면 하나씩을 붙잡았다. 완료 탭은 사진 목록이
   * 커서 가장 크게 보였을 뿐 같은 경로다.
   */
  var BOOTSTRAP_DISPOSE_SELECTOR =
    '.modal, .offcanvas, .collapse, .collapsing, .toast, [data-bs-toggle="dropdown"], [data-bs-original-title]';
  var BOOTSTRAP_DISPOSE_COMPONENTS = ['Modal', 'Offcanvas', 'Collapse', 'Toast', 'Dropdown', 'Tooltip', 'Popover'];

  function disposeBootstrapInstances(container) {
    var bs = window.bootstrap;
    if (!container || !bs) {
      return;
    }
    var ctors = BOOTSTRAP_DISPOSE_COMPONENTS.map(function (name) {
      return bs[name];
    }).filter(function (Ctor) {
      return Ctor && typeof Ctor.getInstance === 'function';
    });
    container.querySelectorAll(BOOTSTRAP_DISPOSE_SELECTOR).forEach(function (el) {
      ctors.forEach(function (Ctor) {
        var instance = Ctor.getInstance(el);
        if (!instance) {
          return;
        }
        try {
          instance.dispose();
        } catch (e) {
          /* ignore */
        }
      });
    });
  }

  /**
   * 새 조각의 hx-* 속성(통합 검색 입력칸 hx-get 등)을 htmx 에 연결한다. 예전엔 htmx.min.js 가
   * 스왑마다 다시 실행되며 body 전체를 다시 훑었다 — 이제 한 번만 실행하므로 여기서 새 영역만 연결한다.
   * htmx 가 아직 없으면(셸 스크립트 첫 실행 중) htmx 자신의 시작 처리가 body 를 훑는다.
   */
  function processHtmxIn(container) {
    var htmx = window.htmx;
    if (!container || !htmx || typeof htmx.process !== 'function') {
      return;
    }
    try {
      htmx.process(container);
    } catch (e) {
      console.warn('[erp-shell] htmx.process 실패:', e);
    }
  }

  /**
   * 지금 #main-content 에 그려진 화면의 캐시 키. 겹층 기록(fomsShellKeep) 건너뛰기는 이 키가 지금 주소와
   * 같을 때만 한다 — 다른 화면으로 갔다가 뒤로 와서 그 기록에 닿으면 다시 그려야 하기 때문이다.
   * 화면 안에서 replaceState 로 주소만 바꾸는 쪽(실측 탭 ?mgr=)은 syncRenderedUrl() 로 알린다.
   */
  var lastRenderedKey = getCacheKey(window.location.href);

  function syncRenderedUrl() {
    lastRenderedKey = getCacheKey(window.location.href);
  }

  function shouldKeepOnPop(state) {
    return !!(state && state.fomsShellKeep) && getCacheKey(window.location.href) === lastRenderedKey;
  }

  function applyFragmentToMain(html, swapUrl) {
    var main = document.getElementById('main-content');
    if (!main) {
      return false;
    }
    teardownOpenOverlays(main);
    disposeBootstrapInstances(main);
    // innerHTML 이 옛 셸 <script> 를 지우기 전에 등록해야 첫 스왑에서도 건너뛸 수 있다.
    ensureExecutedScriptRegistry();
    main.innerHTML = html;
    if (typeof swapUrl === 'string' && swapUrl) {
      lastRenderedKey = getCacheKey(swapUrl);
    }
    activateScripts(main);
    processHtmxIn(main);
    if (typeof swapUrl === 'string' && swapUrl) {
      finishErpShellFragmentSwap(swapUrl);
    }
    return true;
  }

  /**
   * 전체 스타일 선로드 대기 상한(ms). 초과 시 그냥 swap 진행 — 네비게이션이 느린/
   * 죽은 CSS 요청에 무한 대기하지 않게 한다(가드 G3 정신: timeout+폴백).
   */
  var STYLE_PRELOAD_TIMEOUT_MS = 1500;
  /** <link ...> 태그 스캔 — 서버(Jinja) 생성 fragment 만 대상이라 정규식이 안전하고, 직후
   *  innerHTML 이 어차피 전체 파싱하므로 DOMParser 로 640KB 를 재파싱하는 비용을 피한다. */
  var LINK_TAG_RE = /<link\b[^>]*>/gi;

  /**
   * fragment HTML(아직 DOM 미삽입)에서 <link rel="stylesheet"> href 를 절대 URL 로 추출.
   * rel/ href 속성 순서·따옴표 종류 무관. 중복 href 는 1회만.
   * @param {string} html
   * @returns {string[]} 절대 href 목록
   */
  function extractStylesheetHrefs(html) {
    if (typeof html !== 'string' || html.indexOf('<link') === -1) {
      return [];
    }
    var hrefs = [];
    var m;
    LINK_TAG_RE.lastIndex = 0;
    while ((m = LINK_TAG_RE.exec(html)) !== null) {
      var tag = m[0];
      var relM = /\brel\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i.exec(tag);
      if (!relM) {
        continue;
      }
      var relVal = (relM[1] || relM[2] || relM[3] || '').toLowerCase();
      if (relVal.split(/\s+/).indexOf('stylesheet') === -1) {
        continue;
      }
      var hrefM = /\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i.exec(tag);
      if (!hrefM) {
        continue;
      }
      var raw = hrefM[1] || hrefM[2] || hrefM[3] || '';
      if (!raw) {
        continue;
      }
      var abs;
      try {
        abs = new URL(raw, window.location.href).href;
      } catch (e) {
        continue;
      }
      if (hrefs.indexOf(abs) === -1) {
        hrefs.push(abs);
      }
    }
    return hrefs;
  }

  /** document.head 에 동일 href(쿼리스트링 포함, 정확 비교) stylesheet link 가 이미 있는가. */
  function headHasStylesheetHref(absHref) {
    var links = document.head.querySelectorAll('link[rel~="stylesheet"][href]');
    for (var i = 0; i < links.length; i++) {
      if (links[i].href === absHref) {
        return true;
      }
    }
    return false;
  }

  /** head 에 stylesheet link 를 추가하고 load/error 를 1회 resolve 로 await. */
  function preloadStylesheetHref(absHref) {
    return new Promise(function (resolve) {
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = absHref;
      var settled = false;
      function settle() {
        if (settled) {
          return;
        }
        settled = true;
        resolve();
      }
      link.addEventListener('load', settle);
      link.addEventListener('error', settle);
      document.head.appendChild(link);
    });
  }

  /**
   * fragment 안의 stylesheet 를 innerHTML swap **전에** document.head 로 선로드해 콜드 캐시
   * FOUC(스타일 미적용 렌더)를 근본 차단한다. 이미 head 에 있는 href 는 skip(중복 바인딩
   * 방지 → 재실행 idempotent). 전체 대기는 STYLE_PRELOAD_TIMEOUT_MS 상한(Promise.race) —
   * 초과 시 그냥 진행한다. 모든 swap 진입점(cache-hit / network fetch / popstate 복원)이
   * 이 함수를 거친다.
   * @param {string} html
   * @returns {Promise<void>}
   */
  function preloadFragmentStylesheets(html) {
    var pending = extractStylesheetHrefs(html).filter(function (href) {
      return !headHasStylesheetHref(href);
    });
    if (!pending.length) {
      return Promise.resolve();
    }
    var loaded = Promise.all(pending.map(preloadStylesheetHref));
    var timeout = new Promise(function (resolve) {
      window.setTimeout(resolve, STYLE_PRELOAD_TIMEOUT_MS);
    });
    return Promise.race([loaded, timeout]);
  }

  function fetchFragment(canonical) {
    // Consume the one-shot nav abort signal set by navigateByShell (null for
    // prefetch/heartbeat callers). Read+clear before any early return so a reused
    // in-flight promise can't leak this signal to the next caller.
    var navSignal = navFetchSignal;
    navFetchSignal = null;
    var fetchUrl = new URL(canonical.toString());
    fetchUrl.searchParams.set('view', 'fragment');
    var key = getCacheKey(canonical.href);
    var cacheable = isFragmentCacheable(canonical.href);
    if (inflightFetches[key]) {
      return inflightFetches[key];
    }
    var reqHeaders = {
      'X-FOMS-ERP-SHELL': '1',
      'X-Requested-With': 'XMLHttpRequest',
    };
    // 조건부 재검증: 캐시에 ETag 가 있으면 If-None-Match 를 붙여 서버가 내용 무변경 시
    // 304(빈 바디)로 응답하게 한다. force(하트비트)든 네비든 동일 — 네비게이션도 304면
    // 캐시 html 을 그대로 재사용하는 것이 정답(640KB 재전송·재해압 회피). etag 없는 구캐시
    // 엔트리는 헤더 미첨부 → 정상 200 경로.
    var priorRow = fragmentHtmlCache[key];
    // 요청 비행 중 LRU evict/invalidate 경합에도 304 를 복원할 수 있게 html/etag 를
    // 클로저에 캡처해 둔다(문자열 참조만 유지 — 비행 동안만 생존).
    var priorHtml = priorRow && typeof priorRow.html === 'string' ? priorRow.html : null;
    var priorEtag = priorRow && priorRow.etag ? priorRow.etag : null;
    if (priorEtag && priorHtml !== null) {
      reqHeaders['If-None-Match'] = priorEtag;
    }
    var p = fetch(fetchUrl.toString(), {
      credentials: 'same-origin',
      headers: reqHeaders,
      signal: navSignal || undefined,
    })
      .then(function (r) {
        if (r.status === 304) {
          // 내용 무변경 → 캡처해 둔 html 재사용(비행 중 evict/invalidate 경합에도 안전 —
          // If-None-Match 는 priorHtml 이 있을 때만 보냈으므로 여기서 null 불가).
          // 304 엔 커스텀 헤더/바디가 없을 수 있어 X-FOMS-ERP-FRAGMENT 검사와 본문
          // 파싱을 건너뛴다. TTL 은 아래 cachePut 이 연장.
          if (priorHtml === null) {
            throw new Error('304 without cached fragment');
          }
          return { html: priorHtml, finalUrl: canonical, etag: priorEtag };
        }
        if (!r.ok) {
          throw new Error('fragment fetch failed');
        }
        if (r.headers.get('X-FOMS-ERP-FRAGMENT') !== '1') {
          throw new Error('not fragment');
        }
        var finalCanonical = canonicalFromFetchResponse(
          r.headers.get('X-FOMS-Canonical-URL') || r.url
        );
        if (!finalCanonical) {
          throw new Error('unsafe redirected fragment url');
        }
        var etag = r.headers.get('etag');
        return r.text().then(function (html) {
          return {
            html: html,
            finalUrl: finalCanonical,
            etag: etag,
          };
        });
      })
      .then(function (payload) {
        var finalKey = getCacheKey(payload.finalUrl.href);
        if (isFragmentCacheable(payload.finalUrl.href)) {
          // 200 → html+etag 저장, 304 → 동일 html+etag 로 ts 만 갱신(TTL 연장).
          cachePut(finalKey, payload.html, payload.etag);
        }
        if (cacheable && finalKey !== key) {
          delete fragmentHtmlCache[key];
        }
        return payload;
      })
      .finally(function () {
        delete inflightFetches[key];
      });
    inflightFetches[key] = p;
    return p;
  }

  /**
   * @param {string} url
   * @param {{ fromPopState?: boolean, bypassCache?: boolean, replaceHistory?: boolean }} [opts]
   *   replaceHistory=true 면 기록을 새로 쌓지 않고 지금 기록을 바꾼다(같은 화면 다시 받기용).
   */
  function navigateByShell(url, opts) {
    opts = opts || {};
    var canonical = new URL(url, window.location.origin);
    if (!isShellFragmentSwapUrl(canonical.href)) {
      window.location.href = url;
      return Promise.resolve();
    }

    // Rapid A→B nav race guard: this navigation supersedes any in-flight one.
    // Bumping the generation makes a late A response fail the commit gate below
    // (A commit 0); aborting tears down A's dead request so B does not queue
    // behind it. AbortController-less browsers still get correct gating.
    var myGeneration = ++navGeneration;
    if (navAbortController) {
      try {
        navAbortController.abort();
      } catch (e) {
        /* ignore */
      }
    }
    navAbortController =
      typeof AbortController !== 'undefined' ? new AbortController() : null;
    var mySignal = navAbortController ? navAbortController.signal : null;

    /** Only the newest navigation may mutate history/DOM/loading — else commit 0. */
    function isCurrent() {
      return myGeneration === navGeneration;
    }

    var fromKey = getCacheKey(window.location.href);
    if (!opts.fromPopState) {
      scrollMemory[fromKey] = window.scrollY;
    }

    var destKey = getCacheKey(canonical.href);

    function afterSwap() {
      if (opts.fromPopState) {
        window.scrollTo(0, scrollMemory[destKey] || 0);
      } else {
        window.scrollTo(0, 0);
      }
    }

    function commitShellHistory(finalUrl) {
      if (opts.fromPopState || !window.history || !window.history.pushState) {
        return;
      }
      var target = finalUrl.pathname + finalUrl.search + finalUrl.hash;
      if (opts.replaceHistory && window.history.replaceState) {
        window.history.replaceState(window.history.state, '', target);
        return;
      }
      window.history.pushState({ fomsErpShell: true }, '', target);
    }

    if (!opts.bypassCache && isFragmentCacheable(canonical.href)) {
      var cached = cacheGet(destKey);
      if (cached) {
        // 스타일 선로드 후 swap — 콜드 캐시라도 FOUC 없이 즉시 정상 렌더.
        return preloadFragmentStylesheets(cached).then(function () {
          // 선로드 도중 더 새 nav 가 시작됐으면 이 캐시 커밋을 버린다(commit 0).
          if (!isCurrent()) {
            return;
          }
          commitShellHistory(canonical);
          if (applyFragmentToMain(cached, canonical.href)) {
            afterSwap();
            // 앞선 network nav 가 켜 둔 오버레이가 남아 있을 수 있어 명시적으로 내린다.
            setShellFragmentLoading(false);
            return;
          }
          window.location.href = canonical.pathname + canonical.search + canonical.hash;
        });
      }
    }

    setShellFragmentLoading(true);
    navFetchSignal = mySignal;
    return fetchFragment(canonical)
      .then(function (payload) {
        // 응답 도착이 늦어 더 새 nav 에 밀렸으면 commit 0(B 화면 보존).
        if (!isCurrent()) {
          return;
        }
        var finalUrl = payload.finalUrl || canonical;
        // 스타일 선로드 후 swap(가드 G3 상한). commit 직전 generation 재확인 —
        // inline page 스크립트가 window.location.search 를 읽으므로 swap 전 history 확정.
        return preloadFragmentStylesheets(payload.html).then(function () {
          if (!isCurrent()) {
            return;
          }
          commitShellHistory(finalUrl);
          if (!applyFragmentToMain(payload.html, finalUrl.href)) {
            setShellFragmentLoading(false);
            window.location.href = canonical.pathname + canonical.search + canonical.hash;
            return;
          }
          afterSwap();
        });
      })
      .catch(function () {
        // 밀린 nav(abort 로 reject 되었거나 stale generation)는 하드 네비게이션 폴백을
        // 하지 않는다 — 사용자가 고른 새 화면 B 를 덮어쓰기 때문. 진짜 실패(현재 nav)만 폴백.
        if (!isCurrent()) {
          return;
        }
        setShellFragmentLoading(false);
        window.location.href = canonical.pathname + canonical.search + canonical.hash;
      })
      .then(function () {
        // 새 nav 가 켠 오버레이를 밀린 nav 가 끄지 않도록 현재 nav 만 정리한다.
        if (!isCurrent()) {
          return;
        }
        setShellFragmentLoading(false);
      });
  }

  /**
   * Prefetch only; fills warm cache (no DOM swap).
   * @param {string} url
   * @param {{ force?: boolean }} [opts] force=true 면 warm-hit skip 을 건너뛰고 refetch→cachePut 덮어쓰기
   *   (하트비트/복귀 재수혈용). inflight dedup 은 항상 유지해 중복 요청을 막는다.
   */
  function prefetchShellFragment(url, opts) {
    var canonical = new URL(url, window.location.origin);
    if (!isShellFragmentSwapUrl(canonical.href)) {
      return;
    }
    if (!isFragmentCacheable(canonical.href)) {
      return;
    }
    var key = getCacheKey(canonical.href);
    if (!(opts && opts.force) && cacheGet(key)) {
      return;
    }
    if (inflightFetches[key]) {
      return;
    }
    fetchFragment(canonical).catch(function () {
      /* ignore prefetch errors */
    });
  }

  /**
   * 초기 웜업: 로드 후 1회, 가까운 primary 몇 개(IDLE_PREFETCH_MAX)만 프리페치해 초기 로드 부담을 피한다.
   * 나머지 primary 와 이후 신선도 유지는 하트비트(runPrimaryHeartbeat/runFreshHeartbeat)가 곧 커버한다.
   */
  function scheduleIdlePrimaryPrefetch() {
    var cur = pathOnly(window.location.href);
    var candidates = PRIMARY_NAV_PATHS.filter(function (p) {
      return p !== cur;
    }).slice(0, IDLE_PREFETCH_MAX);
    var i = 0;
    function next() {
      if (i >= candidates.length) {
        return;
      }
      var base = window.location.origin + candidates[i];
      prefetchShellFragment(base);
      i += 1;
      window.setTimeout(next, 400);
    }
    window.setTimeout(next, IDLE_DELAY_MS);
  }

  function onAnchorHoverFocus(ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
    if (!a || a.hasAttribute('data-foms-erp-no-shell')) {
      return;
    }
    if (hoverTimer) {
      window.clearTimeout(hoverTimer);
      hoverTimer = null;
    }
    hoverTimer = window.setTimeout(function () {
      hoverTimer = null;
      var href = a.getAttribute('href');
      if (!href || href.charAt(0) === '#') {
        return;
      }
      try {
        var u = new URL(a.href);
        if (u.origin !== window.location.origin) {
          return;
        }
        if (!isShellFragmentSwapUrl(u.href)) {
          return;
        }
        prefetchShellFragment(u.pathname + u.search + u.hash);
      } catch (e) {
        /* ignore */
      }
    }, HOVER_DEBOUNCE_MS);
  }

  /**
   * pointerdown(누름) 즉시 prefetch — hover 디바운스(180ms)를 못 채운 빠른 클릭도
   * 누르는 순간 fragment fetch를 시작한다. 뒤이은 click→swap은 inflight/cache
   * 재사용(prefetchShellFragment의 dedup)으로 이미 시작된 요청을 그대로 쓴다 →
   * 탭 전환 체감 지연 감소. 캐시 불가 경로(measurement)는 prefetch가 자체 스킵.
   */
  function onAnchorPressPrefetch(ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
    if (!a || a.hasAttribute('data-foms-erp-no-shell')) {
      return;
    }
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#') {
      return;
    }
    try {
      var u = new URL(a.href);
      if (u.origin !== window.location.origin) {
        return;
      }
      if (!isShellFragmentSwapUrl(u.href)) {
        return;
      }
      prefetchShellFragment(u.pathname + u.search + u.hash);
    } catch (e) {
      /* ignore */
    }
  }

  function shellNavigateFromAnchor(a) {
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0) {
      return false;
    }
    if (a.hasAttribute('data-foms-erp-no-shell')) {
      return false;
    }
    if (a.getAttribute('download')) {
      return false;
    }
    var u;
    try {
      u = new URL(a.href);
    } catch (err) {
      return false;
    }
    if (u.origin !== window.location.origin) {
      return false;
    }
    if (!isShellFragmentSwapUrl(u.href)) {
      return false;
    }
    navigateByShell(a.href);
    return true;
  }

  document.addEventListener(
    'click',
    function (e) {
      var a = e.target.closest('a[href]');
      if (!a || a.target === '_blank' || e.metaKey || e.ctrlKey || e.shiftKey) {
        return;
      }
      if (shellNavigateFromAnchor(a)) {
        e.preventDefault();
      }
    },
    true
  );

  /* mouseover bubbles — mouseenter does not; needed for document-level delegation */
  document.addEventListener('mouseover', onAnchorHoverFocus, true);
  document.addEventListener('focusin', onAnchorHoverFocus, true);
  /* 누름 즉시 prefetch(빠른 클릭·터치 탭 대응) — 마우스/터치/펜 공통 pointerdown */
  document.addEventListener('pointerdown', onAnchorPressPrefetch, true);

  document.addEventListener(
    'submit',
    function (e) {
      var form = e.target;
      if (!form || form.nodeName !== 'FORM') {
        return;
      }
      if (form.hasAttribute('data-foms-erp-no-shell')) {
        return;
      }
      var method = (form.getAttribute('method') || 'get').toLowerCase();
      if (method !== 'get') {
        return;
      }
      var actionAttr = form.getAttribute('action');
      var u;
      if (actionAttr && String(actionAttr).trim() !== '') {
        u = new URL(actionAttr, window.location.href);
      } else {
        u = new URL(window.location.href);
      }
      if (u.origin !== window.location.origin) {
        return;
      }
      if (!isShellFragmentSwapUrl(u.href)) {
        return;
      }
      e.preventDefault();
      u.search = '';
      var sub = typeof SubmitEvent !== 'undefined' && e instanceof SubmitEvent ? e.submitter : null;
      var fd = sub ? new FormData(form, sub) : new FormData(form);
      fd.forEach(function (value, key) {
        u.searchParams.append(key, value);
      });
      navigateByShell(u.pathname + u.search + u.hash);
    },
    true
  );

  window.addEventListener('popstate', function (e) {
    // 화면 안 겹층(실측 모바일 바텀시트)이 쌓은 기록 사이의 뒤로·앞으로는 같은 화면이다 — 다시 읽지 않는다.
    // 표식은 그 겹층이 열 때 달고 닫은 뒤 지운다(mobile-glance-sheet.js). window 의 popstate 는 캡처로도
    // 먼저 받을 수 없어(등록 순서대로 호출) 겹층 쪽에서 이 리스너를 막을 방법이 없다.
    if (shouldKeepOnPop(e && e.state)) {
      return;
    }
    var url = window.location.href;
    if (!isShellFragmentSwapUrl(url)) {
      return;
    }
    navigateByShell(url, { fromPopState: true });
  });

  /**
   * (레거시, 외부 API 호환용으로 노출) fresh 경로 warm 캐시를 삭제. 복귀 처리는 이제 삭제 대신
   * refreshFreshTtlSurfaces(재수혈)를 쓴다 — 삭제하면 복귀 직후 첫 클릭이 싱가포르 왕복을 그대로 맞기 때문.
   */
  function invalidateFreshTtlSurfaces() {
    FRESH_TTL_PATHS.forEach(function (p) {
      invalidateFragmentCache(window.location.origin + p);
    });
  }

  var lastFocusRefreshTs = 0;

  /**
   * Revalidate-on-focus (stale-while-refresh): 탭이 숨은 사이 타 사용자/기기가 mutation-sensitive
   * 서페이스를 바꿨을 수 있다. 캐시를 **지우지 않고** fresh 경로를 force prefetch 로 백그라운드
   * 덮어쓴다 → 복귀 직후 클릭은 즉시(구 캐시), ~1초 내 신선본으로 교체. 실패 시 구 캐시 유지(fail-open).
   * 연타 방지: 마지막 재수혈로부터 FOCUS_REFRESH_MIN_GAP_MS 이내면 skip.
   */
  function refreshFreshTtlSurfaces() {
    var now = Date.now();
    if (now - lastFocusRefreshTs < FOCUS_REFRESH_MIN_GAP_MS) {
      return;
    }
    lastFocusRefreshTs = now;
    FRESH_TTL_PATHS.forEach(function (p) {
      prefetchShellFragment(window.location.origin + p, { force: true });
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      refreshFreshTtlSurfaces();
    }
  });

  /* bfcache restore brings back the in-memory cache wholesale → 구 캐시를 신선본으로 재수혈. */
  window.addEventListener('pageshow', function (e) {
    if (e && e.persisted) {
      refreshFreshTtlSurfaces();
    }
  });

  /**
   * 하트비트: 캐시가 만료되기 전에 주기적으로 재프리페치해 warm 캐시 "약효"를 유지한다.
   * visible + 최근 활동일 때만 도므로 방치 탭(HEARTBEAT_IDLE_CUTOFF_MS 무활동)은 자동 정지,
   * 활동 재개 시 다음 tick 에 재개(+ 재개 순간 캐시가 식었으면 즉시 1회 refresh).
   */
  var lastActivityTs = Date.now();
  var lastPrimaryHeartbeatTs = 0;
  var lastFreshHeartbeatTs = 0;
  /** 진행 중 스윕 재진입 방지(주기 >> 스윕 소요라 겹칠 일 없지만 안전 플래그). */
  var primaryHeartbeatSweeping = false;
  var freshHeartbeatSweeping = false;

  function heartbeatActive() {
    return (
      document.visibilityState === 'visible' &&
      Date.now() - lastActivityTs < HEARTBEAT_IDLE_CUTOFF_MS
    );
  }

  /**
   * primary 9 nav(현재 경로·fresh 경로 제외)을 순차(600ms 간격) force refresh — 만료 전 웜 유지.
   * fresh 경로는 50초 스윕(runFreshHeartbeat)이 이미 갱신하므로 여기서 다시 부르면 거의 늘 304 인
   * 중복 요청이 된다 — 경로마다 갱신 일정은 하나뿐이다.
   */
  function runPrimaryHeartbeat() {
    if (primaryHeartbeatSweeping) {
      return;
    }
    lastPrimaryHeartbeatTs = Date.now();
    var cur = pathOnly(window.location.href);
    var targets = PRIMARY_NAV_PATHS.filter(function (p) {
      return p !== cur && FRESH_TTL_PATHS.indexOf(p) === -1;
    });
    if (!targets.length) {
      return;
    }
    primaryHeartbeatSweeping = true;
    var i = 0;
    function step() {
      if (i >= targets.length) {
        primaryHeartbeatSweeping = false;
        return;
      }
      try {
        prefetchShellFragment(window.location.origin + targets[i], { force: true });
      } catch (e) {
        // sync throw 시 플래그가 영구 true 로 남아 하트비트가 죽는 leak 방지.
        primaryHeartbeatSweeping = false;
        return;
      }
      i += 1;
      window.setTimeout(step, HEARTBEAT_PRIMARY_STAGGER_MS);
    }
    step();
  }

  /** fresh 경로(3개)를 순차(300ms 간격) force refresh — FRESH_TTL(60s) 앞선 50s 주기로 항상 웜. */
  function runFreshHeartbeat() {
    if (freshHeartbeatSweeping) {
      return;
    }
    lastFreshHeartbeatTs = Date.now();
    if (!FRESH_TTL_PATHS.length) {
      return;
    }
    freshHeartbeatSweeping = true;
    var i = 0;
    function step() {
      if (i >= FRESH_TTL_PATHS.length) {
        freshHeartbeatSweeping = false;
        return;
      }
      try {
        prefetchShellFragment(window.location.origin + FRESH_TTL_PATHS[i], { force: true });
      } catch (e) {
        // sync throw 시 플래그 leak(하트비트 영구 정지) 방지.
        freshHeartbeatSweeping = false;
        return;
      }
      i += 1;
      window.setTimeout(step, HEARTBEAT_FRESH_STAGGER_MS);
    }
    step();
  }

  function onShellActivity() {
    var now = Date.now();
    var wasIdle = now - lastActivityTs >= HEARTBEAT_IDLE_CUTOFF_MS;
    lastActivityTs = now;
    // 방치 후 활동 재개: 캐시가 식어있으면(마지막 하트비트 경과 > 주기) 다음 tick 을 기다리지 않고 즉시 1회.
    if (!wasIdle || document.visibilityState !== 'visible') {
      return;
    }
    if (now - lastFreshHeartbeatTs >= HEARTBEAT_FRESH_MS) {
      runFreshHeartbeat();
    }
    if (now - lastPrimaryHeartbeatTs >= HEARTBEAT_PRIMARY_MS) {
      runPrimaryHeartbeat();
    }
  }

  ['pointerdown', 'keydown', 'wheel', 'touchstart'].forEach(function (evt) {
    document.addEventListener(evt, onShellActivity, { passive: true, capture: true });
  });

  window.setInterval(function () {
    if (heartbeatActive()) {
      runPrimaryHeartbeat();
    }
  }, HEARTBEAT_PRIMARY_MS);

  window.setInterval(function () {
    if (heartbeatActive()) {
      runFreshHeartbeat();
    }
  }, HEARTBEAT_FRESH_MS);

  if (typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(
      function () {
        scheduleIdlePrimaryPrefetch();
      },
      { timeout: 8000 }
    );
  } else {
    window.setTimeout(scheduleIdlePrimaryPrefetch, IDLE_DELAY_MS);
  }

  /*
   * 생략된 모바일 표면 되돌리기.
   * 서버는 광폭 마우스 PC(foms_ptr=fine + foms_vw=wide)에 모바일 v2 대시보드 표면을 빼고
   * [data-foms-mobile-surface-omitted] 표식만 남긴다(feature_flags.wants_mobile_width_surfaces).
   * 창 폭은 바뀐다 — 표면이 보여야 하는 상태(아래 은닉 식 불일치)인데 표식이 남아 있으면 지금
   * 화면을 다시 받는다. 은닉 식은 foms-mobile-v2-surfaces-hide.css 의 @media 와 같은 조건이다.
   * 되풀이 방지: 같은 주소에서 셸 다시 받기 1회 → 그래도 표식이 남으면 전체 새로고침 1회
   * (sessionStorage 표식, 60초) → 그래도 남으면 경고만 남기고 멈춘다(쿠키가 저장되지 않는 환경 등).
   * 새로고침은 포인터·폭 부트를 다시 돌리므로 셸 다시 받기로 못 고치는 경우(쿠키 낡음)까지 덮는다.
   */
  var MOBILE_SURFACE_HIDDEN_MQ =
    '((min-width: 992px) and (orientation: landscape)), ' +
    '((min-width: 992px) and (pointer: fine)), ' +
    '((min-width: 992px) and (pointer: none))';
  var MOBILE_SURFACE_OMITTED_SELECTOR = '[data-foms-mobile-surface-omitted]';
  var MOBILE_SURFACE_RELOAD_GUARD_KEY = 'foms_mobile_surface_reload';
  var MOBILE_SURFACE_RELOAD_GUARD_MS = 60 * 1000;
  var mobileSurfaceHiddenMql = window.matchMedia ? window.matchMedia(MOBILE_SURFACE_HIDDEN_MQ) : null;
  /** 이 문서에서 셸 다시 받기를 이미 한 주소(캐시 키). 성공하면 비운다. */
  var mobileSurfaceRefetchKey = null;
  var mobileSurfaceStorageWarned = false;

  /**
   * 새로고침 되풀이 표식 저장소. 실패하면 undefined(1회 경고) — 호출자는 새로고침을 하지 않는다.
   * @param {'get'|'set'|'remove'} op
   * @param {string} [value]
   */
  function mobileSurfaceReloadGuard(op, value) {
    try {
      var store = window.sessionStorage;
      if (op === 'get') {
        return store.getItem(MOBILE_SURFACE_RELOAD_GUARD_KEY);
      }
      if (op === 'set') {
        store.setItem(MOBILE_SURFACE_RELOAD_GUARD_KEY, value);
        return value;
      }
      store.removeItem(MOBILE_SURFACE_RELOAD_GUARD_KEY);
      return null;
    } catch (e) {
      if (!mobileSurfaceStorageWarned) {
        mobileSurfaceStorageWarned = true;
        console.warn('[erp-shell] sessionStorage 사용 불가 — 모바일 표면 새로고침 되돌림을 하지 않는다:', e);
      }
      return undefined;
    }
  }

  /** 같은 주소를 60초 안에 이미 새로고침했는가(그랬는데 표식이 남았으면 되풀이하지 않는다). */
  function mobileSurfaceReloadedRecently(guard, key) {
    if (!guard) {
      return false;
    }
    var cut = guard.lastIndexOf('|');
    return guard.slice(0, cut) === key && Date.now() - Number(guard.slice(cut + 1)) < MOBILE_SURFACE_RELOAD_GUARD_MS;
  }

  function recoverOmittedMobileSurface() {
    if (!mobileSurfaceHiddenMql) {
      return;
    }
    var here = window.location.href;
    var key = getCacheKey(here);
    if (mobileSurfaceHiddenMql.matches || !document.querySelector(MOBILE_SURFACE_OMITTED_SELECTOR)) {
      // 표면이 필요 없거나 이미 그려져 있다 = 되돌림 불필요·성공 → 되풀이 표식 정리.
      mobileSurfaceRefetchKey = null;
      if (mobileSurfaceReloadGuard('get')) {
        mobileSurfaceReloadGuard('remove');
      }
      return;
    }
    // 창 여러 개가 쿠키 하나를 나눠 쓴다 — 다시 받기 직전에 이 창의 폭 구간으로 맞춘다.
    if (typeof window.__fomsViewportHintSync === 'function') {
      window.__fomsViewportHintSync();
    }
    if (mobileSurfaceRefetchKey !== key && isShellFragmentSwapUrl(here) && document.getElementById('main-content')) {
      mobileSurfaceRefetchKey = key;
      invalidateFragmentCache(here);
      navigateByShell(here, { bypassCache: true, replaceHistory: true });
      return;
    }
    var guard = mobileSurfaceReloadGuard('get');
    if (guard === undefined) {
      return;
    }
    if (mobileSurfaceReloadedRecently(guard, key)) {
      console.warn('[erp-shell] 새로고침 뒤에도 모바일 표면이 빠져 있다(쿠키 저장 실패?) — 되풀이하지 않는다:', key);
      return;
    }
    if (mobileSurfaceReloadGuard('set', key + '|' + Date.now()) === undefined) {
      return;
    }
    window.location.reload();
  }

  if (mobileSurfaceHiddenMql) {
    var onMobileSurfaceVisibilityChange = function () {
      if (!mobileSurfaceHiddenMql.matches) {
        // 광폭일 때 받아 둔 warm 캐시에는 표면이 빠져 있을 수 있다 — 통째로 버린다.
        invalidateFragmentCache();
      }
      // 부트의 foms_vw 쿠키 갱신(먼저 등록된 리스너)이 끝난 뒤에 돈다.
      window.setTimeout(recoverOmittedMobileSurface, 0);
    };
    if (mobileSurfaceHiddenMql.addEventListener) {
      mobileSurfaceHiddenMql.addEventListener('change', onMobileSurfaceVisibilityChange);
    } else if (mobileSurfaceHiddenMql.addListener) {
      mobileSurfaceHiddenMql.addListener(onMobileSurfaceVisibilityChange);
    }
    document.addEventListener('foms:erp-shell-fragment-swapped', recoverOmittedMobileSurface);
    window.addEventListener('pageshow', function (e) {
      if (e && e.persisted) {
        recoverOmittedMobileSurface();
      }
    });
    // 전체 문서로 받은 첫 화면: 좁은 창인데 낡은 wide 쿠키로 받았을 수 있다.
    recoverOmittedMobileSurface();
  }

  if (typeof window !== 'undefined') {
    window.FOMS_ERP_SHELL = window.FOMS_ERP_SHELL || {};
    window.FOMS_ERP_SHELL.PRIMARY_NAV_PATHS = PRIMARY_NAV_PATHS;
    window.FOMS_ERP_SHELL.FRAGMENT_READY_PATHS = FRAGMENT_READY_PATHS;
    window.FOMS_ERP_SHELL.isShellFragmentSwapUrl = isShellFragmentSwapUrl;
    window.FOMS_ERP_SHELL.isFragmentCacheable = isFragmentCacheable;
    window.FOMS_ERP_SHELL.prefetchShellFragment = prefetchShellFragment;
    window.FOMS_ERP_SHELL.getCacheKey = getCacheKey;
    window.FOMS_ERP_SHELL.syncRenderedUrl = syncRenderedUrl;
    window.FOMS_ERP_SHELL.navigateByShell = navigateByShell;
    window.FOMS_ERP_SHELL.beginShellNavigationPending = beginShellNavigationPending;
    window.FOMS_ERP_SHELL.invalidateFragmentCache = invalidateFragmentCache;
    window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache = invalidatePrimaryNavFragmentCache;
    window.FOMS_ERP_SHELL.invalidateFreshTtlSurfaces = invalidateFreshTtlSurfaces;
    window.FOMS_ERP_SHELL.refreshFreshTtlSurfaces = refreshFreshTtlSurfaces;
  }
})();
