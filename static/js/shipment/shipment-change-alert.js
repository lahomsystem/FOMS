/**
 * 출고 대시보드 시공일 변경 알림 — [확인](ack) 클라이언트 (T4/T5).
 *
 * 마크업 SSOT = templates/shipment/partials/shipment_change_macros.html.
 * 하나의 문서 위임 핸들러가 **세 표면**(PC 테이블 행 · 태블릿 클린 그리드 행 · 태블릿 배정
 * 시트)의 [확인] 버튼을 모두 받는다. 시트는 fetch 로 같은 문서에 주입되므로 위임이면 시트가
 * 언제 생기든 배선이 살아 있다(표면별 init 불필요).
 *
 * 리로드하지 않는다(사용자 결정). 생산 선례(tablet-domain-sheets.js changeAck)는 성공 시
 * 페이지를 통째로 새로고침하지만, "확인하면 그 표시만 사라진다"가 요구사항이라 여기서는
 * ack 응답(remaining / banner_count_hint)으로 DOM 만 in-place 정리한다:
 *   1) 그 주문의 행 배지·시트 스트립 전부 제거([data-shipment-change][data-order-id])
 *   2) 배너의 그 주문 점프 칩 제거(PC용·태블릿용 2개)
 *   3) 배너 카운트를 banner_count_hint 만큼 증감, 0 이하가 되면 배너를 통째로 제거
 *
 * 실패는 절대 무음이 아니다(플랜 함정 #10): 응답 본문을 텍스트로 받아 방어적으로 파싱하고
 * (HTML 오류 페이지·빈 본문도 죽지 않는다), 실패하면 버튼을 되살린 뒤 배지 옆 메시지 슬롯에
 * 사유를 띄우고 console.error 로도 남긴다. 슬롯이 없으면 alert 로 폴백한다.
 *
 * fragment 스왑 안전(G4): 전역 리스너는 window.__FOMS_SHIPMENT_CHANGE_ALERT_BOUND 싱글턴
 * 가드로 1회만 등록한다. 탭을 오가며 HTML 이 바뀌어도 위임이라 재초기화가 필요 없다.
 */
(function () {
  'use strict';

  if (window.__FOMS_SHIPMENT_CHANGE_ALERT_BOUND) {
    return;
  }
  window.__FOMS_SHIPMENT_CHANGE_ALERT_BOUND = true;

  var ACK_BTN = '.js-shipment-change-ack';
  var MARKER = '[data-shipment-change]';
  var CHIP = '[data-shipment-change-chip]';
  var BANNER = '[data-shipment-change-banner]';
  var COUNT = '[data-shipment-change-count]';

  /** CSS 속성 셀렉터에 안전하게 넣기 위한 따옴표 이스케이프(주문 id 는 정수지만 방어). */
  function attrEq(name, value) {
    return '[' + name + '="' + String(value).replace(/"/g, '\\"') + '"]';
  }

  /** 실패 사유를 화면에 노출한다(배지 옆 슬롯 우선, 없으면 alert). */
  function showFailure(btn, message) {
    var wrap = btn ? btn.closest(MARKER) : null;
    var slot = wrap ? wrap.querySelector('.erp-ship-change__msg') : null;
    if (slot) {
      slot.textContent = message;
      return;
    }
    window.alert(message);
  }

  /** 응답을 텍스트로 받아 방어적으로 JSON 파싱한다(HTML 오류 페이지·빈 본문 내성). */
  function parseResponse(res) {
    return res.text().then(function (text) {
      var data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (err) {
        data = null;
      }
      if (data && typeof data === 'object') {
        return data;
      }
      return {
        success: false,
        error: res.ok ? '서버 응답 형식 오류' : 'HTTP ' + res.status
      };
    });
  }

  /** 그 주문의 행 배지·시트 스트립을 전 표면에서 제거한다. */
  function removeMarkers(orderId) {
    var nodes = document.querySelectorAll(MARKER + attrEq('data-order-id', orderId));
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].remove();
    }
  }

  /**
   * 배너를 갱신한다 — 그 주문 칩 제거 + 카운트 증감, 0 이하면 배너 제거.
   * delta 는 서버가 준 banner_count_hint(미확인이 있었으면 -1, replay 면 0)다.
   */
  function updateBanner(orderId, delta) {
    var banner = document.querySelector(BANNER);
    if (!banner) {
      return;
    }
    var chips = banner.querySelectorAll(CHIP + attrEq('data-order-id', orderId));
    for (var i = 0; i < chips.length; i++) {
      chips[i].remove();
    }
    var countEl = banner.querySelector(COUNT);
    var current = countEl ? parseInt(countEl.textContent, 10) : NaN;
    if (isNaN(current)) {
      current = 0;
    }
    var next = current + (typeof delta === 'number' ? delta : 0);
    if (next <= 0) {
      banner.remove();
      return;
    }
    if (countEl) {
      countEl.textContent = String(next);
    }
  }

  function onAckClick(btn) {
    var orderId = btn.getAttribute('data-order-id');
    if (!orderId || btn.disabled) {
      return;
    }
    var slot = btn.closest(MARKER);
    slot = slot ? slot.querySelector('.erp-ship-change__msg') : null;
    if (slot) {
      slot.textContent = '';
    }
    btn.disabled = true;

    fetch('/api/orders/' + encodeURIComponent(orderId) + '/shipment/change-ack', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    })
      .then(parseResponse)
      .then(function (data) {
        if (!data || !data.success) {
          btn.disabled = false;
          var reason = (data && (data.error || data.message)) || '확인 처리 실패';
          console.error('[shipment-change-alert] ack 실패:', reason);
          showFailure(btn, '확인 실패: ' + reason);
          return;
        }
        // 성공: 리로드 없이 그 표시만 지운다(사용자 결정).
        updateBanner(orderId, data.banner_count_hint);
        removeMarkers(orderId);
      })
      .catch(function (err) {
        btn.disabled = false;
        console.error('[shipment-change-alert] ack 요청 오류:', err);
        showFailure(btn, '확인 실패: 네트워크 오류');
      });
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }
    var btn = target.closest(ACK_BTN);
    if (!btn) {
      return;
    }
    // preventDefault/stopPropagation 을 쓰지 않는다: 버튼은 type="button" 이라 기본 동작이
    // 없고, 행 탭 → 배정 시트 위임(tablet-side-sheet.js)은 INTERACTIVE 셀렉터('button' 포함)
    // 로 이미 스스로 비켜난다. 같은 document 노드의 리스너끼리는 stopPropagation 이 무의미
    // 하기도 하다(막으려면 stopImmediatePropagation 이어야 하는데 그건 남의 배선을 끊는다).
    onAckClick(btn);
  });
})();
