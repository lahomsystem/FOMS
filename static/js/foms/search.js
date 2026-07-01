/**
 * P1-02: ERP mobile fullscreen search overlay (HTMX + localStorage recent).
 * G4: document-level delegation + live DOM getters — survives fragment re-run without stale closures.
 */
(function () {
  'use strict';

  var RECENT_KEY = 'foms.search.recent.v1';
  var RECENT_MAX = 5;
  var activeIndex = -1;

  function getDialog() {
    return document.getElementById('foms-search-overlay');
  }

  function getInput() {
    return document.getElementById('foms-search-input');
  }

  function getGroupInput() {
    return document.getElementById('foms-search-group');
  }

  function getResultsWrap() {
    return document.getElementById('foms-search-results-wrap');
  }

  function getResultsRoot() {
    return document.getElementById('foms-search-results');
  }

  function getRecentList() {
    return document.getElementById('foms-search-recent-list');
  }

  function readRecent() {
    try {
      var raw = localStorage.getItem(RECENT_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.slice(0, RECENT_MAX) : [];
    } catch (e) {
      return [];
    }
  }

  function writeRecent(items) {
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, RECENT_MAX)));
    } catch (e) {
      /* ignore quota */
    }
  }

  function pushRecent(term) {
    var value = (term || '').trim();
    if (!value) {
      return;
    }
    var next = [value].concat(readRecent().filter(function (x) { return x !== value; }));
    writeRecent(next);
    renderRecent();
  }

  function renderRecent() {
    var recentList = getRecentList();
    if (!recentList) {
      return;
    }
    var items = readRecent();
    recentList.innerHTML = '';
    items.forEach(function (term) {
      var li = document.createElement('li');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'foms-search-overlay__link';
      btn.textContent = term;
      btn.setAttribute('data-foms-search-recent-term', term);
      li.appendChild(btn);
      recentList.appendChild(li);
    });
  }

  function setResultsVisible(show) {
    var resultsWrap = getResultsWrap();
    if (resultsWrap) {
      resultsWrap.hidden = !show;
    }
  }

  function openDialog() {
    var dialog = getDialog();
    if (!dialog) {
      return;
    }
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', 'open');
    }
    renderRecent();
    setResultsVisible(false);
    var input = getInput();
    if (input) {
      input.value = '';
      window.setTimeout(function () { input.focus(); }, 0);
    }
  }

  function closeDialog() {
    var dialog = getDialog();
    if (!dialog) {
      return;
    }
    if (typeof dialog.close === 'function') {
      dialog.close();
    } else {
      dialog.removeAttribute('open');
    }
    activeIndex = -1;
  }

  function setActiveTab(group) {
    var dialog = getDialog();
    if (!dialog) {
      return;
    }
    dialog.querySelectorAll('.foms-search-overlay__tab').forEach(function (tab) {
      var isActive = tab.getAttribute('data-group') === group;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    var groupInput = getGroupInput();
    if (groupInput) {
      groupInput.value = group;
    }
    var input = getInput();
    if (input && input.value.trim()) {
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function resultLinks() {
    var resultsRoot = getResultsRoot();
    if (!resultsRoot) {
      return [];
    }
    return Array.prototype.slice.call(
      resultsRoot.querySelectorAll('[data-search-result]')
    );
  }

  function clearSearchResults() {
    var resultsRoot = getResultsRoot();
    if (resultsRoot) {
      resultsRoot.innerHTML = '';
    }
    setResultsVisible(false);
    activeIndex = -1;
  }

  function navigateToResult(link) {
    if (!link) {
      return;
    }
    var href = (link.getAttribute('href') || '').trim();
    if (!href || href === '#') {
      return;
    }
    var input = getInput();
    if (input) {
      pushRecent(input.value);
    }
    clearSearchResults();

    var shell = window.FOMS_ERP_SHELL;
    try {
      var targetUrl = new URL(href, window.location.origin);
      if (
        targetUrl.origin === window.location.origin
        && shell
        && typeof shell.isShellFragmentSwapUrl === 'function'
        && shell.isShellFragmentSwapUrl(targetUrl.href)
        && typeof shell.navigateByShell === 'function'
      ) {
        if (typeof shell.beginShellNavigationPending === 'function') {
          shell.beginShellNavigationPending();
        }
        closeDialog();
        shell.navigateByShell(
          targetUrl.pathname + targetUrl.search + targetUrl.hash,
          { bypassCache: true }
        );
        return;
      }
    } catch (e) {
      /* fall through to full navigation */
    }

    closeDialog();
    window.location.assign(href);
  }

  function highlightIndex(index) {
    var links = resultLinks();
    links.forEach(function (link, i) {
      link.classList.toggle('is-active', i === index);
    });
    activeIndex = index;
    if (index >= 0 && links[index]) {
      links[index].scrollIntoView({ block: 'nearest' });
    }
  }

  if (!getDialog()) {
    return;
  }

  if (window.__FOMS_SEARCH_OVERLAY_BOUND) {
    return;
  }
  window.__FOMS_SEARCH_OVERLAY_BOUND = true;

  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-foms-search-open]')) {
      event.preventDefault();
      openDialog();
      return;
    }

    var dialog = getDialog();
    if (!dialog) {
      return;
    }

    if (event.target.closest('[data-foms-search-close]') && dialog.contains(event.target.closest('[data-foms-search-close]'))) {
      event.preventDefault();
      closeDialog();
      return;
    }

    if (event.target.closest('[data-foms-search-clear]') && dialog.contains(event.target.closest('[data-foms-search-clear]'))) {
      event.preventDefault();
      var input = getInput();
      if (input) {
        input.value = '';
        input.focus();
      }
      var resultsRoot = getResultsRoot();
      if (resultsRoot) {
        resultsRoot.innerHTML = '';
      }
      setResultsVisible(false);
      activeIndex = -1;
      return;
    }

    var tab = event.target.closest('.foms-search-overlay__tab');
    if (tab && dialog.contains(tab)) {
      event.preventDefault();
      setActiveTab(tab.getAttribute('data-group') || 'all');
      return;
    }

    var recentBtn = event.target.closest('.foms-search-overlay__link[data-foms-search-recent-term]');
    if (recentBtn && dialog.contains(recentBtn)) {
      event.preventDefault();
      var term = recentBtn.getAttribute('data-foms-search-recent-term') || '';
      var recentInput = getInput();
      if (recentInput && term) {
        recentInput.value = term;
        recentInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
      return;
    }

    var resultTarget = event.target.closest('[data-search-result]');
    if (resultTarget && dialog.contains(resultTarget)) {
      event.preventDefault();
      navigateToResult(resultTarget);
    }
  });

  document.addEventListener('input', function (event) {
    if (!event.target || event.target.id !== 'foms-search-input') {
      return;
    }
    setResultsVisible(Boolean(event.target.value.trim()));
    activeIndex = -1;
  });

  document.addEventListener('keydown', function (event) {
    if (!event.target || event.target.id !== 'foms-search-input') {
      return;
    }
    var input = getInput();
    if (!input) {
      return;
    }
    var links = resultLinks();
    if (event.key === 'Enter' && !links.length && input.value.trim()) {
      var resultsRoot = getResultsRoot();
      var historyFallback = resultsRoot
        ? resultsRoot.querySelector('[data-search-history-fallback]')
        : null;
      if (historyFallback) {
        event.preventDefault();
        pushRecent(input.value);
        closeDialog();
        window.location.assign(historyFallback.getAttribute('href') || '/erp/history/');
        return;
      }
    }
    if (!links.length) {
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      highlightIndex(Math.min(activeIndex + 1, links.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      highlightIndex(Math.max(activeIndex - 1, 0));
    } else if (event.key === 'Enter' && activeIndex >= 0 && links[activeIndex]) {
      event.preventDefault();
      navigateToResult(links[activeIndex]);
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    var resultsRoot = getResultsRoot();
    if (event.detail && event.detail.target === resultsRoot) {
      highlightIndex(-1);
    }
  });

  renderRecent();
})();
