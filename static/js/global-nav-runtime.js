/**
 * Global top nav — G1-A warm fragment swap + G2 weak prefetch (GNV runbook).
 *
 * - G1-A (orders listing + trash, same-origin): hover/focus warms fetch(nav-fragment),
 *   click swaps #main-content; pushState/popstate + scroll memory; miss/fail → full navigation.
 * - G2/other: same-origin <link rel="prefetch"> hint only (no click interception).
 * - Shared UX: any same-origin top-nav click gets immediate loading feedback.
 * - Progressive enhancement: broken fetch or JS off → normal navigation.
 */
(function () {
  'use strict';

  var prefetched = Object.create(null);
  var warmCache = Object.create(null);
  // 이 런타임이 #main-content 를 갈아 끼운 적이 있는가(popstate 폴백 판정용).
  var didSwapMain = false;
  var scrollMem = Object.create(null);
  var hoverTimer = null;
  var activeNavLink = null;
  var HOVER_MS = 180;

  function normalizePathname(pathname) {
    if (!pathname || pathname === '') {
      return '/';
    }
    return pathname;
  }

  /** G1-A: shared-layout orders index + trash only (taxonomy freeze). */
  function isG1APath(pathname) {
    var p = normalizePathname(pathname);
    return p === '/' || p === '/trash';
  }

  function isG1A(href) {
    try {
      var u = new URL(href, window.location.href);
      if (u.origin !== window.location.origin) {
        return false;
      }
      return isG1APath(u.pathname);
    } catch (e) {
      return false;
    }
  }

  function cacheKeyForUrl(href) {
    var u = new URL(href, window.location.href);
    u.hash = '';
    var path = normalizePathname(u.pathname);
    var params = new URLSearchParams(u.search);
    params.delete('view');
    var keys = Array.from(params.keys()).sort();
    var parts = keys.map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(params.get(k) || '');
    });
    var qs = parts.join('&');
    return path + (qs ? '?' + qs : '');
  }

  function buildFragmentFetchUrl(href) {
    var u = new URL(href, window.location.href);
    u.searchParams.set('view', 'nav-fragment');
    return u.toString();
  }

  function stripTitleTags(html) {
    return html.replace(/<title\b[^>]*>[\s\S]*?<\/title>/gi, '');
  }

  function normalizePath(href) {
    try {
      var u = new URL(href, window.location.href);
      if (u.origin !== window.location.origin) {
        return null;
      }
      return u.pathname + u.search + u.hash;
    } catch (e) {
      return null;
    }
  }

  function isSameOriginDocumentHref(href) {
    try {
      var u = new URL(href, window.location.href);
      if (u.origin !== window.location.origin) {
        return false;
      }
      return u.protocol === 'http:' || u.protocol === 'https:';
    } catch (e) {
      return false;
    }
  }

  function setNavLoadingStatus(message) {
    var live = document.getElementById('layout-nav-loading-status');
    if (!live) {
      return;
    }
    live.textContent = '';
    window.setTimeout(function () {
      if (live.isConnected) {
        live.textContent = message || '';
      }
    }, 0);
  }

  function clearActiveNavLink() {
    if (!activeNavLink || !activeNavLink.classList) {
      activeNavLink = null;
      return;
    }
    activeNavLink.classList.remove('is-nav-loading-target');
    activeNavLink.removeAttribute('aria-disabled');
    activeNavLink = null;
  }

  function beginNavLoading(a) {
    var nav = document.querySelector('nav.layout-global-nav');
    var main = document.getElementById('main-content');
    clearActiveNavLink();
    if (a && a.classList) {
      activeNavLink = a;
      activeNavLink.classList.add('is-nav-loading-target');
      activeNavLink.setAttribute('aria-disabled', 'true');
    }
    document.body.classList.add('is-nav-loading');
    if (nav) {
      nav.setAttribute('data-nav-loading', '1');
    }
    if (main) {
      main.setAttribute('aria-busy', 'true');
    }
    setNavLoadingStatus('페이지 이동 중...');
  }

  function endNavLoading() {
    var nav = document.querySelector('nav.layout-global-nav');
    var main = document.getElementById('main-content');
    document.body.classList.remove('is-nav-loading');
    if (nav) {
      nav.removeAttribute('data-nav-loading');
    }
    if (main) {
      main.removeAttribute('aria-busy');
    }
    clearActiveNavLink();
    setNavLoadingStatus('');
  }

  function prefetchOnce(absPath) {
    if (!absPath || prefetched[absPath]) {
      return;
    }
    prefetched[absPath] = true;
    var link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = absPath;
    document.head.appendChild(link);
  }

  function warmFragmentFetch(href) {
    if (!isG1A(href)) {
      return;
    }
    var key = cacheKeyForUrl(href);
    if (warmCache[key]) {
      return;
    }
    var url = buildFragmentFetchUrl(href);
    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-FOMS-GNAV': '1' },
    })
      .then(function (res) {
        if (!res.ok) {
          return;
        }
        if (res.headers.get('X-FOMS-GNAV-FRAGMENT') !== '1') {
          return;
        }
        return res.text();
      })
      .then(function (text) {
        if (text) {
          warmCache[key] = text;
        }
      })
      .catch(function () {
        /* warm failure is OK */
      });
  }

  function scheduleWarm(href) {
    if (hoverTimer) {
      clearTimeout(hoverTimer);
    }
    hoverTimer = setTimeout(function () {
      hoverTimer = null;
      warmFragmentFetch(href);
    }, HOVER_MS);
  }

  function activateScriptsIn(container) {
    if (!container) {
      return;
    }
    var scripts = container.querySelectorAll('script');
    for (var i = 0; i < scripts.length; i++) {
      var old = scripts[i];
      var s = document.createElement('script');
      if (old.id) {
        s.id = old.id;
      }
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
    }
  }

  function swapMainFromHtml(html) {
    var main = document.querySelector('#main-content');
    if (!main) {
      throw new Error('missing #main-content');
    }
    // 이 런타임이 실제로 본문을 갈아 끼웠는지 기억한다 — popstate 폴백이 이걸 본다.
    didSwapMain = true;
    main.innerHTML = stripTitleTags(html);
    activateScriptsIn(main);
  }

  function navigateG1A(href, a) {
    var key = cacheKeyForUrl(href);
    var fromKey = cacheKeyForUrl(window.location.href);
    scrollMem[fromKey] = window.scrollY;

    var cached = warmCache[key];
    var p = cached
      ? Promise.resolve(cached)
      : fetch(buildFragmentFetchUrl(href), {
          credentials: 'same-origin',
          headers: { 'X-FOMS-GNAV': '1' },
        }).then(function (res) {
          if (!res.ok) {
            throw new Error('fragment HTTP ' + res.status);
          }
          if (res.headers.get('X-FOMS-GNAV-FRAGMENT') !== '1') {
            throw new Error('not a gnav fragment');
          }
          return res.text();
        });

    p.then(function (html) {
      if (html) {
        warmCache[key] = html;
      }
      swapMainFromHtml(html);
      if (history && history.pushState) {
        history.pushState({ gnav: true, gnavKey: key }, '', href);
      } else {
        window.location.href = href;
        return;
      }
      var y = scrollMem[key];
      if (typeof y === 'number') {
        window.requestAnimationFrame(function () {
          window.scrollTo(0, y);
        });
      } else {
        window.scrollTo(0, 0);
      }
      window.requestAnimationFrame(endNavLoading);
    }).catch(function () {
      window.location.href = a.href;
    });
  }

  function shouldHandleClick(a, ev) {
    if (!a || a.getAttribute('data-gnav-ignore') === '1') {
      return false;
    }
    if (ev.defaultPrevented) {
      return false;
    }
    if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) {
      return false;
    }
    if (a.target === '_blank') {
      return false;
    }
    if (a.hasAttribute('download')) {
      return false;
    }
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#') {
      return false;
    }
    return true;
  }

  function onNavClick(ev) {
    var nav = ev.currentTarget;
    if (!nav || !nav.matches || !nav.matches('nav.layout-global-nav')) {
      return;
    }
    var t = ev.target;
    if (!t || !t.closest) {
      return;
    }
    var a = t.closest('a[href]');
    if (!a || !nav.contains(a)) {
      return;
    }
    if (!shouldHandleClick(a, ev)) {
      return;
    }
    if (isSameOriginDocumentHref(a.href)) {
      beginNavLoading(a);
    }
    if (!isG1A(a.href)) {
      return;
    }
    ev.preventDefault();
    navigateG1A(a.href, a);
  }

  function applyFragmentAndScroll(key) {
    var html = warmCache[key];
    if (!html) {
      return false;
    }
    swapMainFromHtml(html);
    var y = scrollMem[key];
    if (typeof y === 'number') {
      window.requestAnimationFrame(function () {
        window.scrollTo(0, y);
      });
    } else {
      window.scrollTo(0, 0);
    }
    return true;
  }

  function onPopState(ev) {
    var st = ev.state;
    if (!st || !st.gnav || !st.gnavKey) {
      // 리로드는 **이 런타임이 본문을 갈아 끼운 뒤** 원래 항목으로 돌아왔을 때만 옳다.
      // 한 번도 스왑한 적이 없으면 DOM 은 서버가 준 그대로이고, 그 히스토리 항목은
      // 다른 화면이 만든 것이다(예: 네이버 워크벤치의 `{wbLinkId}` 부분 갱신).
      // 그때 리로드하면 남의 부분 갱신 UI 를 전체 재요청으로 되돌린다 —
      // 워크벤치 뒤로가기가 정확히 그렇게 깨졌다(2026-08-23 QA #2).
      if (!didSwapMain) {
        return;
      }
      window.location.reload();
      return;
    }
    var key = st.gnavKey;
    if (applyFragmentAndScroll(key)) {
      return;
    }
    fetch(buildFragmentFetchUrl(window.location.href), {
      credentials: 'same-origin',
      headers: { 'X-FOMS-GNAV': '1' },
    })
      .then(function (res) {
        if (!res.ok) {
          throw new Error('fragment HTTP ' + res.status);
        }
        if (res.headers.get('X-FOMS-GNAV-FRAGMENT') !== '1') {
          throw new Error('not fragment');
        }
        return res.text();
      })
      .then(function (text) {
        warmCache[key] = text;
        applyFragmentAndScroll(key);
      })
      .catch(function () {
        window.location.reload();
      });
  }

  function warmTarget(ev) {
    var nav = ev.currentTarget;
    if (!nav || !nav.matches || !nav.matches('nav.layout-global-nav')) {
      return;
    }
    var t = ev.target;
    if (!t || !t.closest) {
      return;
    }
    var a = t.closest('a[href]');
    if (!a || !nav.contains(a)) {
      return;
    }
    var path = normalizePath(a.getAttribute('href') || '');
    if (!path) {
      return;
    }
    prefetchOnce(path);
    if (isG1A(a.href)) {
      scheduleWarm(a.href);
    }
  }

  function boot() {
    var nav = document.querySelector('nav.layout-global-nav');
    if (!nav) {
      return;
    }
    endNavLoading();
    nav.addEventListener('click', onNavClick, true);
    nav.addEventListener('mouseover', warmTarget, true);
    nav.addEventListener('focusin', warmTarget, true);
    window.addEventListener('popstate', onPopState);
    window.addEventListener('pageshow', endNavLoading);
    window.addEventListener('load', endNavLoading);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
