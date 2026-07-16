/**
 * 도면 작업실 — ERP 주문 변경 배너 (타임라인 포커스 + ack).
 * fragment 재실행 대비 document 위임 + singleton 가드 (perf G4).
 */
(function () {
  'use strict';
  if (window.__FOMS_DW_ORDER_CHANGE_BOUND) return;
  window.__FOMS_DW_ORDER_CHANGE_BOUND = true;

  function toast(msg) {
    if (typeof window.showToast === 'function') {
      window.showToast(msg);
      return;
    }
    try {
      console.info(msg);
    } catch (e) { /* ignore */ }
  }

  function focusTimeline() {
    var feed = document.getElementById('dwOrderChangeFeed');
    if (feed && typeof feed.scrollIntoView === 'function') {
      feed.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    var detailsList = document.querySelectorAll('details.dw-secondary-collapse');
    if (detailsList && detailsList.length) {
      detailsList[0].open = true;
    }
    var target =
      document.querySelector('.dw-order-change-card.is-pending') ||
      document.querySelector('.foms-drawing-thread__msg--alert') ||
      document.querySelector('.dw-order-change-badge');
    if (target && typeof target.scrollIntoView === 'function') {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    try {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', 'timeline');
      window.history.replaceState({}, '', url.toString());
    } catch (e) { /* ignore */ }
  }

  function ackBanner(btn) {
    var banner = btn.closest('#dwOrderChangeBanner, .dw-order-change-banner');
    if (!banner) return;
    var url = banner.getAttribute('data-ack-url');
    if (!url) return;
    btn.disabled = true;
    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: '{}',
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data || !result.data.success) {
          throw new Error(
            (result.data && result.data.message) || '확인 처리 실패'
          );
        }
        banner.remove();
        document.querySelectorAll('.dw-order-change-badge, .is-order-change').forEach(function (el) {
          el.remove();
        });
        document.querySelectorAll('.dw-order-change-card.is-pending').forEach(function (card) {
          card.classList.remove('is-pending');
          var badge = card.querySelector('.dw-order-change-badge, .badge.bg-warning');
          if (badge) {
            badge.className = 'badge bg-light text-dark border ms-1';
            badge.textContent = '확인됨';
          }
        });
        var feedHead = document.querySelector(
          '.dw-order-change-feed__head .dw-order-change-badge, .dw-order-change-feed__head .badge.bg-warning'
        );
        if (feedHead) feedHead.remove();
        toast('주문 변경을 확인했습니다.');
      })
      .catch(function (err) {
        btn.disabled = false;
        toast(err.message || '확인 처리 실패');
      });
  }

  document.addEventListener('click', function (e) {
    var focusBtn = e.target.closest('[data-dw-order-change-focus]');
    if (focusBtn) {
      e.preventDefault();
      focusTimeline();
      return;
    }
    var ackBtn = e.target.closest('[data-dw-order-change-ack]');
    if (ackBtn) {
      e.preventDefault();
      ackBanner(ackBtn);
    }
  });
})();
