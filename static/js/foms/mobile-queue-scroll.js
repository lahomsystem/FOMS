/**
 * P1 §6.2: Infinite scroll for mobile v2 dashboard queue (IntersectionObserver).
 */
(function () {
  'use strict';

  function initMobileQueueScroll() {
    var root = document.querySelector('[data-foms-mobile-queue-scroll]');
    if (!root || root.dataset.fomsScrollBound === '1') {
      return;
    }
    var sentinel = root.querySelector('[data-foms-mobile-queue-sentinel]');
    if (!sentinel) {
      return;
    }
    var nextPage = parseInt(root.dataset.nextPage || '0', 10);
    var totalPages = parseInt(root.dataset.totalPages || '0', 10);
    if (!nextPage || nextPage > totalPages) {
      return;
    }

    root.dataset.fomsScrollBound = '1';
    var loading = false;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || loading) {
            return;
          }
          if (nextPage > totalPages) {
            observer.disconnect();
            return;
          }
          loading = true;
          var url = new URL(window.location.href);
          url.searchParams.set('page', String(nextPage));
          fetch(url.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
          })
            .then(function (res) {
              return res.text();
            })
            .then(function (html) {
              var parser = new DOMParser();
              var doc = parser.parseFromString(html, 'text/html');
              var chunk = doc.querySelector('[data-foms-mobile-queue-chunk]');
              var list = root.querySelector('[data-foms-mobile-queue-list]');
              if (chunk && list) {
                list.insertAdjacentHTML('beforeend', chunk.innerHTML);
              }
              var fresh = doc.querySelector('[data-foms-mobile-queue-scroll]');
              if (fresh) {
                nextPage = parseInt(fresh.dataset.nextPage || '0', 10);
                totalPages = parseInt(fresh.dataset.totalPages || '0', 10);
                root.dataset.nextPage = String(nextPage);
                root.dataset.totalPages = String(totalPages);
              } else {
                nextPage = totalPages + 1;
              }
              var indicator = root.querySelector('[data-foms-mobile-queue-page]');
              if (indicator && fresh) {
                indicator.textContent = fresh.dataset.pageLabel || indicator.textContent;
              }
            })
            .catch(function (err) {
              console.error('[foms-mobile-queue-scroll]', err);
            })
            .finally(function () {
              loading = false;
            });
        });
      },
      { rootMargin: '120px' }
    );
    observer.observe(sentinel);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMobileQueueScroll);
  } else {
    initMobileQueueScroll();
  }
  document.addEventListener('foms:main-content-swapped', initMobileQueueScroll);
})();
