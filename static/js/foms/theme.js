/**
 * P0-07: Light/dark theme preference (localStorage + prefers-color-scheme).
 */
(function (global) {
  'use strict';

  var STORAGE_KEY = 'foms-theme';
  var ALLOWED = { light: true, dark: true, system: true };

  function systemTheme() {
    if (!global.matchMedia) {
      return 'light';
    }
    return global.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
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

  function effectiveTheme(preference) {
    return preference === 'system' ? systemTheme() : preference;
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
    var effective = effectiveTheme(pref);
    var root = document.documentElement;
    root.setAttribute('data-theme', effective);
    root.setAttribute('data-theme-preference', pref);
    var meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) {
      meta.setAttribute('content', effective === 'dark' ? 'dark' : 'light');
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

  function bindToggles() {
    document.querySelectorAll('[data-foms-theme-option]').forEach(function (btn) {
      if (btn.dataset.fomsThemeBound === '1') {
        return;
      }
      btn.dataset.fomsThemeBound = '1';
      btn.addEventListener('click', function () {
        setTheme(btn.getAttribute('data-foms-theme-option'));
      });
    });
  }

  function init() {
    applyTheme(readStoredPreference());
    bindToggles();
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
    readStoredPreference: readStoredPreference,
    set: setTheme,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
