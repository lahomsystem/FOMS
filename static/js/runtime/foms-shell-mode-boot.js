/* Early shell-mode boot (escape hatch). SSOT copy of the pre-paint inline block
   in templates/partials/shared/layout_head.html. Reads the manual shell override
   from localStorage and stamps html[data-foms-shell] before first paint so the
   CSS shell-selection matrix (foms-split-view.css / foms-shell.css) can be
   overridden without a flash. Mirrors the foms-theme-boot.js load pattern. */
(function () {
  var key = 'foms_shell_mode';
  try {
    var mode = localStorage.getItem(key);
    if (mode === 'desktop' || mode === 'split') {
      document.documentElement.setAttribute('data-foms-shell', mode);
    } else {
      // 'auto', absent, or any unexpected value → let the CSS matrix decide.
      document.documentElement.removeAttribute('data-foms-shell');
    }
  } catch (e) {
    console.warn('[foms-shell-mode-boot] shell mode preference unavailable:', e);
  }
})();
