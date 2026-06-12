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
   * Mutation-sensitive surfaces (other users/devices change them between visits):
   * shorter warm-cache freshness + revalidate-on-focus so a tab-switch back never
   * serves a stale post-approve home. Full page reload already bypasses this cache.
   */
  var FRESH_TTL_MS = 30 * 1000;
  var FRESH_TTL_PATHS = [
    '/erp/dashboard',
  ];
  var IDLE_PREFETCH_MAX = 3;
  var HOVER_DEBOUNCE_MS = 180;
  var IDLE_DELAY_MS = 1600;
  var NO_FRAGMENT_CACHE_PATHS = [
    '/erp/measurement',
  ];

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

  function cachePut(key, html) {
    var now = Date.now();
    if (fragmentHtmlCache[key]) {
      var i = fragmentCacheOrder.indexOf(key);
      if (i >= 0) {
        fragmentCacheOrder.splice(i, 1);
      }
    }
    fragmentHtmlCache[key] = { html: html, ts: now };
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

  function fetchFragment(canonical) {
    var fetchUrl = new URL(canonical.toString());
    fetchUrl.searchParams.set('view', 'fragment');
    var key = getCacheKey(canonical.href);
    var cacheable = isFragmentCacheable(canonical.href);
    if (inflightFetches[key]) {
      return inflightFetches[key];
    }
    var p = fetch(fetchUrl.toString(), {
      credentials: 'same-origin',
      headers: {
        'X-FOMS-ERP-SHELL': '1',
        'X-Requested-With': 'XMLHttpRequest',
      },
    })
      .then(function (r) {
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
        return r.text().then(function (html) {
          return {
            html: html,
            finalUrl: finalCanonical,
          };
        });
      })
      .then(function (payload) {
        var finalKey = getCacheKey(payload.finalUrl.href);
        if (isFragmentCacheable(payload.finalUrl.href)) {
          cachePut(finalKey, payload.html);
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

    if (!opts.bypassCache && isFragmentCacheable(canonical.href)) {
      var cached = cacheGet(destKey);
      if (cached && applyFragmentToMain(cached, canonical.href)) {
        if (!opts.fromPopState && window.history && window.history.pushState) {
          window.history.pushState({ fomsErpShell: true }, '', canonical.pathname + canonical.search + canonical.hash);
        }
        afterSwap();
        return Promise.resolve();
      }
    }

    setShellFragmentLoading(true);
    return fetchFragment(canonical)
      .then(function (payload) {
        var finalUrl = payload.finalUrl || canonical;
        if (!applyFragmentToMain(payload.html, finalUrl.href)) {
          setShellFragmentLoading(false);
          window.location.href = canonical.pathname + canonical.search + canonical.hash;
          return;
        }
        if (!opts.fromPopState && window.history && window.history.pushState) {
          window.history.pushState({ fomsErpShell: true }, '', finalUrl.pathname + finalUrl.search + finalUrl.hash);
        }
        afterSwap();
      })
      .catch(function () {
        setShellFragmentLoading(false);
        window.location.href = canonical.pathname + canonical.search + canonical.hash;
      })
      .then(function () {
        setShellFragmentLoading(false);
      });
  }

  /** Prefetch only; fills warm cache (no DOM swap). */
  function prefetchShellFragment(url) {
    var canonical = new URL(url, window.location.origin);
    if (!isShellFragmentSwapUrl(canonical.href)) {
      return;
    }
    if (!isFragmentCacheable(canonical.href)) {
      return;
    }
    var key = getCacheKey(canonical.href);
    if (cacheGet(key)) {
      return;
    }
    if (inflightFetches[key]) {
      return;
    }
    fetchFragment(canonical).catch(function () {
      /* ignore prefetch errors */
    });
  }

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
   * Revalidate-on-focus: while this tab was hidden, another user/device may have
   * mutated a mutation-sensitive surface (quest approve → stage change). Drop its
   * warm cache so the next tab-switch back refetches instead of serving stale HTML.
   */
  function invalidateFreshTtlSurfaces() {
    FRESH_TTL_PATHS.forEach(function (p) {
      invalidateFragmentCache(window.location.origin + p);
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      invalidateFreshTtlSurfaces();
    }
  });

  /* bfcache restore brings back the in-memory cache wholesale → drop fresh surfaces too. */
  window.addEventListener('pageshow', function (e) {
    if (e && e.persisted) {
      invalidateFreshTtlSurfaces();
    }
  });

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
    window.FOMS_ERP_SHELL.invalidateFragmentCache = invalidateFragmentCache;
    window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache = invalidatePrimaryNavFragmentCache;
  }
})();
