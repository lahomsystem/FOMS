/**
 * P1-02: ERP mobile fullscreen search overlay (HTMX + localStorage recent).
 */
(function () {
  'use strict';

  var RECENT_KEY = 'foms.search.recent.v1';
  var RECENT_MAX = 5;
  var dialog = document.getElementById('foms-search-overlay');
  if (!dialog) {
    return;
  }

  var input = document.getElementById('foms-search-input');
  var groupInput = document.getElementById('foms-search-group');
  var resultsWrap = document.getElementById('foms-search-results-wrap');
  var resultsRoot = document.getElementById('foms-search-results');
  var recentList = document.getElementById('foms-search-recent-list');
  var openButtons = document.querySelectorAll('[data-foms-search-open]');
  var closeButtons = dialog.querySelectorAll('[data-foms-search-close]');
  var clearButtons = dialog.querySelectorAll('[data-foms-search-clear]');
  var tabs = dialog.querySelectorAll('.foms-search-overlay__tab');
  var activeIndex = -1;

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
      btn.addEventListener('click', function () {
        if (input) {
          input.value = term;
          input.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
      li.appendChild(btn);
      recentList.appendChild(li);
    });
  }

  function setResultsVisible(show) {
    if (resultsWrap) {
      resultsWrap.hidden = !show;
    }
  }

  function openDialog() {
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', 'open');
    }
    renderRecent();
    setResultsVisible(false);
    if (input) {
      input.value = '';
      window.setTimeout(function () { input.focus(); }, 0);
    }
  }

  function closeDialog() {
    if (typeof dialog.close === 'function') {
      dialog.close();
    } else {
      dialog.removeAttribute('open');
    }
    activeIndex = -1;
  }

  function setActiveTab(group) {
    tabs.forEach(function (tab) {
      var isActive = tab.getAttribute('data-group') === group;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    if (groupInput) {
      groupInput.value = group;
    }
    if (input && input.value.trim()) {
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function resultLinks() {
    if (!resultsRoot) {
      return [];
    }
    return Array.prototype.slice.call(
      resultsRoot.querySelectorAll('[data-search-result]')
    );
  }

  function navigateToResult(link) {
    if (!link) {
      return;
    }
    var href = (link.getAttribute('href') || '').trim();
    if (!href || href === '#') {
      return;
    }
    if (input) {
      pushRecent(input.value);
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

  openButtons.forEach(function (btn) {
    btn.addEventListener('click', openDialog);
  });
  closeButtons.forEach(function (btn) {
    btn.addEventListener('click', closeDialog);
  });
  clearButtons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (input) {
        input.value = '';
        input.focus();
      }
      if (resultsRoot) {
        resultsRoot.innerHTML = '';
      }
      setResultsVisible(false);
      activeIndex = -1;
    });
  });
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      setActiveTab(tab.getAttribute('data-group') || 'all');
    });
  });

  if (input) {
    input.addEventListener('input', function () {
      setResultsVisible(Boolean(input.value.trim()));
      activeIndex = -1;
    });
    input.addEventListener('keydown', function (event) {
      var links = resultLinks();
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
  }

  document.body.addEventListener('click', function (event) {
    var target = event.target.closest('[data-search-result]');
    if (!target || !dialog.contains(target)) {
      return;
    }
    event.preventDefault();
    navigateToResult(target);
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail && event.detail.target === resultsRoot) {
      highlightIndex(-1);
    }
  });

  renderRecent();
})();
