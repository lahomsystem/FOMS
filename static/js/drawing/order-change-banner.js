/**
 * 도면 작업실 — ERP 주문 변경 확인(ack) + 변경 이력 포커스.
 * 옛 상단 배너를 걷어낸 뒤로 확인 버튼은 변경 값 바로 아래(모바일 타임라인/데스크톱 카드)에 산다.
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
      document.querySelector('.foms-drawing-thread__msg--alert:not(.is-acked)') ||
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

  /** 확인 직후 화면 교체 — 버튼 줄은 걷고, 모바일 리본 한 줄은 '확인됨'으로 바꾼다. */
  function markAcked(data) {
    document.querySelectorAll('.foms-drawing-thread__ack, .dw-order-change-ack-row').forEach(function (el) {
      el.remove();
    });
    var line = document.getElementById('dwOrderChangeLine');
    if (!line) return;
    var lines = line.getAttribute('data-order-change-lines') || '';
    line.classList.add('foms-drawing-turn__change--done');
    var chip = line.querySelector('.foms-drawing-turn__change-chip');
    if (chip) chip.textContent = '확인함';
    var act = line.querySelector('.foms-drawing-turn__change-act');
    if (act) act.remove();
    var text = line.querySelector('.foms-drawing-turn__change-text');
    if (text) {
      var who = (data && data.acked_by_name) || '';
      var at = (data && data.acked_at) || '';
      text.textContent =
        '주문 변경' + (lines ? ' ' + lines + '줄' : '') +
        (who ? ' · ' + who : '') + (at ? ' ' + at : '');
    }
  }

  function ackBanner(btn) {
    // 확인 버튼이 자기 주소를 직접 싣는다(옛 배너는 조상에서 읽었고, 그 배너는 사라졌다).
    var holder = btn.closest('[data-ack-url]');
    if (!holder) return;
    var url = holder.getAttribute('data-ack-url');
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
        markAcked(result.data);
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
