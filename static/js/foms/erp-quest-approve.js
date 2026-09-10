/**
 * ERP 퀘스트 승인 CTA — 확인 → 승인 API → 화면 갱신.
 *
 * 모바일 주문 상세(order_detail_mobile_v2.html)와 큐 카드(erp_mobile_queue_card_v2.html)가
 * 같은 handler 를 쓴다. 버튼이 확인 문구(data-confirm)와 대상(data-order-id)을 들고 오고,
 * 이 파일은 그 문구를 그대로 보여 준 뒤 POST 한다 — 단계별 문구는 서버(erp_quest_display)가 SSOT.
 *
 * 갱신 규칙(회귀 주의): 예전 코드는 `location.href = pathname + search + '#foms-detail-quest'`
 * 로 새로고침을 시도했다. 브라우저는 해시만 다른(또는 완전히 같은) URL 로는 문서를 다시
 * 읽지 않으므로 승인은 성공했는데 화면이 그대로였고, 버튼은 disabled 로 굳었다.
 * 그래서 여기서는 해시를 replaceState 로 먼저 심고 location.reload() 를 부른다.
 *
 * 목록에서 승인했을 때 카드를 지우지 않는 이유: 승인해도 그 주문은 목록에서 빠지지 않는다.
 * 실측 큐는 실측일 기준이라 승인 뒤에도 '실측 완료' 배지를 달고 남고(measurement/dashboard.py
 * measurement_completed), 메인 대시보드는 단계별 섹션이라 다음 단계 섹션으로 옮겨 갈 뿐이다.
 * 카드를 지우면 '사라졌다'는 거짓을 보여 준다. 대신 스크롤 위치를 기억해 두고 문서를 다시
 * 읽은 뒤 그 자리로 돌려놓고, 방금 처리한 카드를 잠깐 강조한다 — 바뀐 카드만 눈에 띈다.
 */
(function () {
  'use strict';

  var SELECTOR = '.erp-mobile-quest-approve-assignee, .erp-mobile-quest-approve-team, .erp-queue-card__quest-approve';
  var RESTORE_KEY = 'foms:quest-approve:restore';
  var RESTORE_TTL_MS = 30 * 1000;
  var HIGHLIGHT_MS = 2400;

  function toast(message) {
    if (!message) return;
    if (window.fomsFlashToast) {
      window.fomsFlashToast(message);
    } else {
      alert(message);
    }
  }

  function invalidateShellCache() {
    var shell = window.FOMS_ERP_SHELL;
    if (!shell) return;
    if (typeof shell.invalidatePrimaryNavFragmentCache === 'function') {
      shell.invalidatePrimaryNavFragmentCache();
    } else if (typeof shell.invalidateFragmentCache === 'function') {
      shell.invalidateFragmentCache(true);
    }
  }

  /** 승인 후 결과 문장 — 단계가 옮겨졌는지 서버 응답으로만 말한다(추정 금지). */
  function resultMessage(data, btn) {
    if (data.auto_transitioned && data.next_stage) {
      return '승인 완료 — ' + data.next_stage + ' 단계로 넘어갔습니다.';
    }
    var label = btn.getAttribute('data-approve-label') || '승인';
    if (data.all_approved) {
      return label + ' 기록 완료.';
    }
    var missing = (data.missing_teams || []).join(', ');
    return missing ? '승인 완료 — 남은 팀: ' + missing : '승인 완료.';
  }

  /**
   * 다시 읽은 뒤 돌아올 자리를 적어 둔다(sessionStorage 실패는 무시 — 복원만 못 할 뿐).
   * 같은 경로에서만, 그리고 방금 것만 복원한다(TTL).
   */
  function rememberPlace(orderId) {
    try {
      window.sessionStorage.setItem(
        RESTORE_KEY,
        JSON.stringify({
          path: window.location.pathname + window.location.search,
          y: window.scrollY || window.pageYOffset || 0,
          orderId: String(orderId || ''),
          at: Date.now()
        })
      );
    } catch (e) {
      /* private 모드·저장 차단: 복원 없이 진행 */
    }
  }

  function takeRememberedPlace() {
    var raw = null;
    try {
      raw = window.sessionStorage.getItem(RESTORE_KEY);
      window.sessionStorage.removeItem(RESTORE_KEY);
    } catch (e) {
      return null;
    }
    if (!raw) return null;
    var saved;
    try {
      saved = JSON.parse(raw);
    } catch (e) {
      return null;
    }
    if (!saved || typeof saved !== 'object') return null;
    if (saved.path !== window.location.pathname + window.location.search) return null;
    if (!saved.at || Date.now() - saved.at > RESTORE_TTL_MS) return null;
    return saved;
  }

  /** 방금 처리한 카드를 잠깐 강조한다(클래스만 — 스타일은 foms-queue-card-v2.css). */
  function highlightCard(card) {
    card.classList.add('is-foms-just-approved');
    window.setTimeout(function () {
      card.classList.remove('is-foms-just-approved');
    }, HIGHLIGHT_MS);
  }

  function restorePlace() {
    var saved = takeRememberedPlace();
    if (!saved) return;
    var card = saved.orderId
      ? document.querySelector('article.queue-card[data-order-id="' + saved.orderId + '"]')
      : null;
    if (card) {
      // 위쪽 내용이 줄거나 늘었을 수 있어 좌표보다 카드 자체가 정확하다.
      card.scrollIntoView({ block: 'center' });
      highlightCard(card);
      return;
    }
    if (typeof saved.y === 'number' && saved.y > 0) {
      window.scrollTo(0, saved.y);
    }
  }

  /**
   * 현재 화면을 실제로 다시 읽는다.
   * @param {string} anchor 상세 화면의 퀘스트 섹션 앵커(목록에서는 빈 문자열).
   */
  function refreshAfterApprove(anchor) {
    if (anchor && window.location.hash !== anchor && window.history && window.history.replaceState) {
      window.history.replaceState(
        null,
        '',
        window.location.pathname + window.location.search + anchor
      );
    }
    window.location.reload();
  }

  async function approve(btn) {
    var orderId = btn.getAttribute('data-order-id');
    if (!orderId) return;
    var team = btn.getAttribute('data-team');
    var confirmText = btn.getAttribute('data-confirm');
    if (confirmText && !window.confirm(confirmText)) return;

    var anchor = btn.getAttribute('data-refresh-anchor') || '';
    btn.disabled = true;
    try {
      var res = await fetch('/api/orders/' + orderId + '/quest/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(team ? { team: team } : {})
      });
      var data = await res.json();
      if (!data.success) {
        // 서버 code(COMMAND_REQUIRED·QUEST_INCOMPLETE·전이 충돌)까지 노출해야 원인 파악이 된다.
        var detail = data.code ? ' (' + data.code + ')' : '';
        throw new Error((data.message || data.error || '승인 실패') + detail);
      }
      invalidateShellCache();
      toast(resultMessage(data, btn));
      // 목록(앵커 없음)에서만 자리 복원 — 상세는 앵커가 자리를 잡는다.
      if (!anchor) rememberPlace(orderId);
      refreshAfterApprove(anchor);
    } catch (error) {
      btn.disabled = false;
      alert(String((error && error.message) || error || '승인 중 오류가 발생했습니다.'));
    }
  }

  document.addEventListener('click', function (event) {
    var btn = event.target.closest(SELECTOR);
    if (!btn) return;
    // 링크형 CTA(전용 command 단계·상세로 보내는 경우)는 가로채지 않는다.
    if (btn.tagName === 'A') return;
    event.preventDefault();
    approve(btn);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', restorePlace);
  } else {
    restorePlace();
  }
})();
