/**
 * Global top nav — G1-A warm fragment swap + G2 weak prefetch (GNV runbook).
 *
 * - G1-A (orders listing + trash, same-origin): hover/focus warms fetch(nav-fragment),
 *   click swaps #main-content; pushState/popstate + scroll memory; miss/fail → full navigation.
 * - G2/other: same-origin <link rel="prefetch"> hint only (no click interception).
 * - Progressive enhancement: broken fetch or JS off → normal navigation.
 */
(function () {
  'use strict';

  var prefetched = Object.create(null);
  var warmCache = Object.create(null);
  var scrollMem = Object.create(null);
  var hoverTimer = null;
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
      if (old.src) {
        s.src = old.src;
        s.async = old.async;
        s.defer = old.defer;
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
    nav.addEventListener('click', onNavClick, true);
    nav.addEventListener('mouseover', warmTarget, true);
    nav.addEventListener('focusin', warmTarget, true);
    window.addEventListener('popstate', onPopState);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
