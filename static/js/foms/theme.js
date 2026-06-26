/**
 * P0-07: Light/dark theme preference (localStorage + prefers-color-scheme).
 * Dark applies on mobile viewport only (max-width 991.98px); PC stays light.
 * Bootstrap 5.3 data-bs-theme stays in sync with html[data-theme].
 */
(function (global) {
  'use strict';

  var STORAGE_KEY = 'foms-theme';
  var MOBILE_THEME_MQ = '(max-width: 991.98px)';
  var ALLOWED = { light: true, dark: true, system: true };

  function systemTheme() {
    if (!global.matchMedia) {
      return 'light';
    }
    return global.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function isMobileThemeViewport() {
    if (!global.matchMedia) {
      return false;
    }
    return global.matchMedia(MOBILE_THEME_MQ).matches;
  }

  function readStoredPreference() {
    try {
      var stored = global.localStorage.getItem(STORAGE_KEY);
      if (stored && ALLOWED[stored]) {
        return stored;
      }
    } catch (err) {
      /* localStorage blocked */
    }
    return 'system';
  }

  function preferenceToTheme(preference) {
    return preference === 'system' ? systemTheme() : preference;
  }

  function resolveAppliedTheme(preference) {
    if (!isMobileThemeViewport()) {
      return 'light';
    }
    return preferenceToTheme(preference);
  }

  function syncToggleUi(preference) {
    var buttons = document.querySelectorAll('[data-foms-theme-option]');
    buttons.forEach(function (btn) {
      var option = btn.getAttribute('data-foms-theme-option');
      var active = option === preference;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function applyTheme(preference) {
    var pref = preference || readStoredPreference();
    var effective = resolveAppliedTheme(pref);
    var root = document.documentElement;
    root.setAttribute('data-theme', effective);
    root.setAttribute('data-theme-preference', pref);
    root.setAttribute('data-bs-theme', effective);
    var meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) {
      meta.setAttribute('content', effective === 'dark' ? 'dark' : 'light');
    }
    var themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) {
      themeColor.setAttribute('content', effective === 'dark' ? '#0a0c10' : '#0070f2');
    }
    syncToggleUi(pref);
  }

  function setTheme(preference) {
    if (!ALLOWED[preference]) {
      return;
    }
    try {
      global.localStorage.setItem(STORAGE_KEY, preference);
    } catch (err) {
      /* ignore */
    }
    applyTheme(preference);
  }

  /** Single document listener — survives HTMX #main-content swap (G4 idempotent). */
  function bindThemeClickDelegation() {
    if (global.__FOMS_THEME_CLICK_BOUND) {
      return;
    }
    global.__FOMS_THEME_CLICK_BOUND = true;
    document.addEventListener('click', function (event) {
      var btn = event.target.closest('[data-foms-theme-option]');
      if (!btn) {
        return;
      }
      event.preventDefault();
      setTheme(btn.getAttribute('data-foms-theme-option'));
    });
  }

  function bindOffcanvasResync() {
    if (global.__FOMS_THEME_OFFCANVAS_BOUND) {
      return;
    }
    global.__FOMS_THEME_OFFCANVAS_BOUND = true;
    document.addEventListener('shown.bs.offcanvas', function (event) {
      if (!event.target || event.target.id !== 'erp-mobile-menu-drawer') {
        return;
      }
      applyTheme(readStoredPreference());
    });
  }

  function bindMainContentResync() {
    if (global.__FOMS_THEME_SWAP_BOUND) {
      return;
    }
    global.__FOMS_THEME_SWAP_BOUND = true;
    document.addEventListener('foms:main-content-swapped', function () {
      applyTheme(readStoredPreference());
    });
  }

  function bindViewportThemeListener() {
    if (global.__FOMS_THEME_VIEWPORT_BOUND || !global.matchMedia) {
      return;
    }
    global.__FOMS_THEME_VIEWPORT_BOUND = true;
    global.matchMedia(MOBILE_THEME_MQ).addEventListener('change', function () {
      applyTheme(readStoredPreference());
    });
  }

  function init() {
    applyTheme(readStoredPreference());
    bindThemeClickDelegation();
    bindOffcanvasResync();
    bindMainContentResync();
    bindViewportThemeListener();
    if (global.matchMedia) {
      global.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        if (readStoredPreference() === 'system') {
          applyTheme('system');
        }
      });
    }
  }

  global.FomsTheme = {
    apply: applyTheme,
    init: init,
    isMobileThemeViewport: isMobileThemeViewport,
    readStoredPreference: readStoredPreference,
    resolveAppliedTheme: resolveAppliedTheme,
    set: setTheme,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
