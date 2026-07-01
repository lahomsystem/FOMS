(function () {
  var key = 'foms-theme';
      var pref = 'system';
      try {
        var stored = localStorage.getItem(key);
        if (stored === 'light' || stored === 'dark' || stored === 'system') {
          pref = stored;
        }
      } catch (e) { /* ignore */ }
      var mobileViewport = window.matchMedia && window.matchMedia('(max-width: 991.98px)').matches;
      var effective = mobileViewport
        ? (pref === 'system'
          ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
          : pref)
        : 'light';
      document.documentElement.setAttribute('data-theme', effective);
      document.documentElement.setAttribute('data-theme-preference', pref);
      document.documentElement.setAttribute('data-bs-theme', effective);
      var metaCs = document.querySelector('meta[name="color-scheme"]');
      if (metaCs) {
        metaCs.setAttribute('content', effective);
      }
      var themeColor = document.querySelector('meta[name="theme-color"]');
      if (themeColor) {
        themeColor.setAttribute('content', effective === 'dark' ? '#0a0c10' : '#0070f2');
      }
    })();
