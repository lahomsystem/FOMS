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

  function activateScripts(container) {
    var nodes = container.querySelectorAll('script');
    nodes.forEach(function (old) {
      var s = document.createElement('script');
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

  function applyFragmentToMain(html, swapUrl) {
    var main = document.getElementById('main-content');
    if (!main) {
      return false;
    }
    teardownOpenOverlays(main);
    main.innerHTML = html;
    activateScripts(main);
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
   * @param {{ fromPopState?: boolean, bypassCache?: boolean }} [opts]
   */
  function navigateByShell(url, opts) {
    opts = opts || {};
    var canonical = new URL(url, window.location.origin);
    if (!isShellFragmentSwapUrl(canonical.href)) {
      window.location.href = url;
      return Promise.resolve();
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
      window.history.pushState(
        { fomsErpShell: true },
        '',
        finalUrl.pathname + finalUrl.search + finalUrl.hash
      );
    }

    if (!opts.bypassCache && isFragmentCacheable(canonical.href)) {
      var cached = cacheGet(destKey);
      if (cached) {
        commitShellHistory(canonical);
        // 스타일 선로드 후 swap — 콜드 캐시라도 FOUC 없이 즉시 정상 렌더.
        return preloadFragmentStylesheets(cached).then(function () {
          if (applyFragmentToMain(cached, canonical.href)) {
            afterSwap();
            return;
          }
          window.location.href = canonical.pathname + canonical.search + canonical.hash;
        });
      }
    }

    setShellFragmentLoading(true);
    return fetchFragment(canonical)
      .then(function (payload) {
        var finalUrl = payload.finalUrl || canonical;
        commitShellHistory(finalUrl);
        // 스타일 선로드 후 swap(가드 G3 상한). commitShellHistory 는 위에서 이미 실행 —
        // inline page 스크립트가 window.location.search 를 읽으므로 swap 전 history 확정.
        return preloadFragmentStylesheets(payload.html).then(function () {
          if (!applyFragmentToMain(payload.html, finalUrl.href)) {
            setShellFragmentLoading(false);
            window.location.href = canonical.pathname + canonical.search + canonical.hash;
            return;
          }
          afterSwap();
        });
      })
      .catch(function () {
        setShellFragmentLoading(false);
        window.location.href = canonical.pathname + canonical.search + canonical.hash;
      })
      .then(function () {
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

  window.addEventListener('popstate', function () {
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
   * primary 9 nav(현재 경로 제외)을 순차(600ms 간격) force refresh — 만료 전 웜 유지.
   * 동시 9발 대신 setTimeout 체인 스태거로 주기 jank 를 없앤다(대부분 304, tail 만 200).
   */
  function runPrimaryHeartbeat() {
    if (primaryHeartbeatSweeping) {
      return;
    }
    lastPrimaryHeartbeatTs = Date.now();
    var cur = pathOnly(window.location.href);
    var targets = PRIMARY_NAV_PATHS.filter(function (p) {
      return p !== cur;
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

  /** fresh 경로(2개)를 순차(300ms 간격) force refresh — FRESH_TTL(60s) 앞선 50s 주기로 항상 웜. */
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

  if (typeof window !== 'undefined') {
    window.FOMS_ERP_SHELL = window.FOMS_ERP_SHELL || {};
    window.FOMS_ERP_SHELL.PRIMARY_NAV_PATHS = PRIMARY_NAV_PATHS;
    window.FOMS_ERP_SHELL.FRAGMENT_READY_PATHS = FRAGMENT_READY_PATHS;
    window.FOMS_ERP_SHELL.isShellFragmentSwapUrl = isShellFragmentSwapUrl;
    window.FOMS_ERP_SHELL.isFragmentCacheable = isFragmentCacheable;
    window.FOMS_ERP_SHELL.prefetchShellFragment = prefetchShellFragment;
    window.FOMS_ERP_SHELL.getCacheKey = getCacheKey;
    window.FOMS_ERP_SHELL.navigateByShell = navigateByShell;
    window.FOMS_ERP_SHELL.beginShellNavigationPending = beginShellNavigationPending;
    window.FOMS_ERP_SHELL.invalidateFragmentCache = invalidateFragmentCache;
    window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache = invalidatePrimaryNavFragmentCache;
    window.FOMS_ERP_SHELL.invalidateFreshTtlSurfaces = invalidateFreshTtlSurfaces;
    window.FOMS_ERP_SHELL.refreshFreshTtlSurfaces = refreshFreshTtlSurfaces;
  }
})();
