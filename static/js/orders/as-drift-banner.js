/**
 * 주문 상세 최상단 AS 기준 일정 드리프트 배너 배선 (재적용 / 무시 / 연결 해제).
 *
 * AS 대시보드의 같은 3액션은 static/js/cs/as-dashboard.js 에 있지만, 그 구현은 목록 전용
 * 헬퍼(saveDateField·getDateInputsForOrder = 행의 날짜 input)에 묶여 있어 주문 상세에는
 * 그대로 쓸 수 없다(상세엔 as_visit_date input 이 없다). 그래서 배너 전용으로 분리하되,
 * **엔드포인트는 두 개 그대로** 재사용한다 — 세 번째 API 도 새 날짜 포맷 경로도 만들지 않는다:
 *   1) POST /api/update_order_field  {order_id, field_name:'as_visit_date', value: Ds}
 *   2) POST /api/orders/<id>/as/schedule-link  {action: relink|ack|unlink}
 * Ds(기준 주문의 새 시공일)는 서버가 이미 'YYYY-MM-DD' 로 정규화해 data 속성에 실어 보낸
 * 값을 그대로 전달한다(클라 재포맷 금지).
 *
 * fragment 재실행 대비: document 위임 + 싱글톤 가드(perf G4). CSRF 헤더는 layout_head.html
 * 의 전역 fetch 인터셉터가 붙인다(여기서 수동 부착 금지 — 중복).
 */
(function () {
  'use strict';
  if (window.__FOMS_AS_DRIFT_BANNER_BOUND) return;
  window.__FOMS_AS_DRIFT_BANNER_BOUND = true;

  var HOOKS = '.js-as-banner-drift-relink, .js-as-banner-drift-ack, .js-as-banner-drift-unlink';

  /**
   * 응답 본문을 텍스트로 받아 방어적으로 JSON 파싱한다(선례: as-dashboard.js parseJsonResponse).
   * 세션 만료 리다이렉트는 HTML 을 200 으로 돌려준다 — res.json() 을 바로 쓰면 SyntaxError 로
   * 버튼이 아무 반응 없이 죽는다(무음 실패). 파싱 실패는 상태코드를 담은 실패 객체로 접는다.
   */
  function parseJsonResponse(r) {
    return r.text().then(function (text) {
      var data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (e) {
        data = null;
      }
      if (!data || typeof data !== 'object') {
        data = { success: false, message: '서버 응답 오류 (' + r.status + ')' };
      }
      return { ok: r.ok, status: r.status, data: data };
    });
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    }).then(parseJsonResponse);
  }

  /** 실패 사유를 사람이 읽을 문장으로. 없으면 fallback. */
  function errorText(res, fallback) {
    var d = (res && res.data) || {};
    return String(d.message || d.error || fallback);
  }

  function showMessage(banner, text) {
    var slot = banner ? banner.querySelector('[data-as-drift-banner-msg]') : null;
    if (slot) {
      slot.textContent = text;
      return;
    }
    window.alert(text);
  }

  /** 재적용 1단계 — 방문일 쓰기는 기존 SSOT(update_order_field)만 탄다. */
  function writeAsVisitDate(orderId, refCurrentDate) {
    return postJson('/api/update_order_field', {
      order_id: Number(orderId),
      field_name: 'as_visit_date',
      value: refCurrentDate,
    }).then(function (res) {
      if (!res.ok || res.data.success !== true) {
        throw new Error(errorText(res, 'AS 방문일 저장에 실패했습니다.'));
      }
      return res;
    });
  }

  function postScheduleLink(orderId, action) {
    return postJson(
      '/api/orders/' + encodeURIComponent(orderId) + '/as/schedule-link',
      { action: action }
    ).then(function (res) {
      if (!res.ok || res.data.success !== true) {
        throw new Error(errorText(res, '기준 일정 처리에 실패했습니다.'));
      }
      return res;
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest(HOOKS) : null;
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var banner = btn.closest('.foms-as-drift-banner');
    if (!banner) return;
    var orderId = banner.dataset.asOrderId;
    if (!orderId) return;
    var refCurrentDate = banner.dataset.refCurrentDate || '';
    var isRelink = btn.classList.contains('js-as-banner-drift-relink');
    var isUnlink = btn.classList.contains('js-as-banner-drift-unlink');

    if (isUnlink && !window.confirm('기준 일정 연결을 해제할까요? AS 방문일은 그대로 둡니다.')) return;
    // both_moved = 방문일도 따로 바뀐 상태 — 재적용은 그 값을 덮어쓴다(스펙 §4).
    if (isRelink && banner.dataset.driftState === 'both_moved'
      && !window.confirm('AS 방문일이 따로 변경돼 있습니다. 기준 주문의 새 일정('
        + refCurrentDate + ')으로 덮어쓸까요?')) return;

    var action = isRelink ? 'relink' : (isUnlink ? 'unlink' : 'ack');
    showMessage(banner, '');
    btn.disabled = true;

    var chain;
    if (isRelink) {
      chain = refCurrentDate
        ? writeAsVisitDate(orderId, refCurrentDate)
        : Promise.reject(new Error('기준 주문의 새 일정을 알 수 없습니다.'));
    } else {
      chain = Promise.resolve();
    }
    chain
      .then(function () {
        return postScheduleLink(orderId, action);
      })
      .then(function () {
        // 배너 문구·AS 탭 표시의 SSOT 는 서버다 — 클라에서 다시 조립하지 않고 다시 그린다.
        window.location.reload();
      })
      .catch(function (err) {
        btn.disabled = false;
        showMessage(banner, String((err && err.message) || err || '기준 일정 처리 중 오류가 발생했습니다.'));
      });
  });
})();
