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
          // nextPage 0(또는 NaN) = 더 이상 페이지 없음 → page=0 재요청(서버 1로 클램프 → 중복 append) 방지.
          if (!nextPage || nextPage > totalPages) {
            observer.disconnect();
            return;
          }
          loading = true;
          var url = new URL(window.location.href);
          url.searchParams.set('page', String(nextPage));
          url.searchParams.set('mobile_chunk', '1');
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
              if (!chunk && html.indexOf('data-foms-mobile-queue-chunk') !== -1) {
                var wrap = document.createElement('div');
                wrap.innerHTML = html.trim();
                chunk = wrap.querySelector('[data-foms-mobile-queue-chunk]');
              }
              var list = root.querySelector('[data-foms-mobile-queue-list]');
              if (chunk && list) {
                list.insertAdjacentHTML('beforeend', chunk.innerHTML);
                // append된 카드에 모듈별 per-card 핸들러 재배선 기회 제공 (예: AS 자동저장).
                document.dispatchEvent(new CustomEvent('foms:mobile-queue-appended', {
                  detail: { root: root, list: list },
                }));
              }
              var fresh = doc.querySelector('[data-foms-mobile-queue-scroll]');
              if (!fresh && chunk) {
                nextPage = parseInt(chunk.getAttribute('data-next-page') || '0', 10);
                totalPages = parseInt(chunk.getAttribute('data-total-pages') || String(totalPages), 10);
                root.dataset.nextPage = String(nextPage);
                root.dataset.totalPages = String(totalPages);
                var indicator = root.querySelector('[data-foms-mobile-queue-page]');
                if (indicator && chunk.getAttribute('data-page-label')) {
                  indicator.textContent = chunk.getAttribute('data-page-label');
                }
              } else if (!fresh && nextPage <= totalPages) {
                nextPage += 1;
                root.dataset.nextPage = String(Math.min(nextPage, totalPages + 1));
              } else if (fresh) {
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
