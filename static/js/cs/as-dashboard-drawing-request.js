/**
 * AS 화면 'AS도면' 칸 [도면팀 부탁] — 완료 주문 AS 도면 설계서
 * docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §4.4.
 *
 * 단추를 누르면 작은 창(무엇을 그려야 하나요 · 부탁하기)이 뜬다.
 * POST /api/orders/<id>/drawing/as/request {memo} 가 열린 AS 접수에 부탁만 붙인다(접수는 다시 저장하지 않는다).
 * 성공하면(또는 이미 그리고 있으면) 응답 state({title, words})로 칸 글자를 "1차 대기중"처럼 바로 바꾼다.
 * 창 모양은 같은 화면의 방문 가능시간 창(.erp-as-avail-pop)을 그대로 쓴다.
 */
(function () {
  'use strict';
  if (window.__fomsAsDrawingRequestWired) return; // fragment 재실행 가드
  window.__fomsAsDrawingRequestWired = true;

  const MEMO_ID = 'erp-as-drawing-req-memo';
  let pop = null;

  function closePop() {
    if (pop) { pop.remove(); pop = null; }
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function orderIdOf(btn) {
    const row = btn.closest('[data-order-id]');
    return row ? row.getAttribute('data-order-id') || '' : '';
  }

  /** 서버 state 로 칸 글자를 만든다 — 템플릿의 상태 링크(as_dashboard_body.html)와 같은 모양. */
  function stateLink(orderId, state) {
    const a = el('a', 'd-block small lh-sm');
    a.href = '/edit/' + encodeURIComponent(orderId);
    a.title = state.title || '';
    (state.words || []).forEach(function (w, i) {
      if (i) a.appendChild(document.createTextNode(' '));
      a.appendChild(el('span', 'text-nowrap', String(w)));
    });
    return a;
  }

  function settle(btn, orderId, state) {
    if (state && Array.isArray(state.words) && state.words.length) btn.replaceWith(stateLink(orderId, state));
    else btn.remove();
  }

  /** 같은 화면의 저장 알림(#saveToast, as-dashboard.js 와 같은 모양) — 칸이 54px 라 칸 안에 글을 두지 않는다. */
  function feedback(text, isError) {
    const toastEl = document.getElementById('saveToast');
    const msgEl = document.getElementById('toastMessage');
    if (toastEl && msgEl && window.bootstrap && window.bootstrap.Toast) {
      msgEl.textContent = text;
      toastEl.classList.remove('bg-success', 'bg-danger');
      toastEl.classList.add(isError ? 'bg-danger' : 'bg-success');
      window.bootstrap.Toast.getOrCreateInstance(toastEl).show();
      return;
    }
    window.alert(text);
  }

  async function send(orderId, memo) {
    try {
      const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/drawing/as/request', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ memo: memo }),
      });
      let data = {};
      try { data = await res.json(); } catch (_) { data = {}; }
      return data || {};
    } catch (e) {
      return { success: false, error: '인터넷 연결을 확인해 주세요.' };
    }
  }

  function position(btn) {
    const rect = btn.getBoundingClientRect();
    // 화면 크기(--foms-ui-zoom)가 붙으면 rect · scroll · innerWidth 는 보이는 px, style 은 배율 전 px 다.
    const uiZoom = window.fomsUiZoom ? window.fomsUiZoom() : 1;
    const popW = (pop.offsetWidth || 280) * uiZoom;
    // 칸이 표 오른쪽에 있어 단추 오른쪽 끝에 맞춰 왼쪽으로 연다.
    const left = Math.max(8, Math.min(window.scrollX + rect.right - popW, window.scrollX + window.innerWidth - popW - 8));
    const popH = (pop.offsetHeight || 200) * uiZoom;
    // 아래 자리가 모자라면(표 아래쪽 줄) 단추 위로 연다 — [부탁하기]가 화면 밖으로 밀리지 않게.
    const below = rect.bottom + 4 + popH <= window.innerHeight || rect.top - 4 - popH < 0;
    const top = below ? window.scrollY + rect.bottom + 4 : window.scrollY + rect.top - 4 - popH;
    pop.style.top = (top / uiZoom) + 'px';
    pop.style.left = (left / uiZoom) + 'px';
  }

  function openPop(btn) {
    closePop();
    const orderId = orderIdOf(btn);
    const received = btn.getAttribute('data-as-received') || '';
    pop = el('div', 'erp-as-avail-pop erp-as-drawing-req-pop');
    pop.dataset.forOrder = orderId;
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', '도면팀에 정확한 도면 부탁');
    pop.appendChild(el('div', 'erp-as-drawing-req-pop__title', '도면팀에 정확한 도면 부탁'));
    pop.appendChild(el('div', 'erp-as-drawing-req-pop__hint',
      received ? 'AS 접수 ' + received + '에 묶어요.' : '지금 열린 AS 접수에 묶어요.'));
    pop.appendChild(el('div', 'erp-as-drawing-req-pop__hint', '받는 사람: 도면 담당 (없으면 도면팀 전체)'));
    const label = el('label', 'erp-as-drawing-req-pop__label', '무엇을 그려야 하나요 (비우면 AS 내용)');
    label.htmlFor = MEMO_ID;
    const input = el('input', 'erp-pro-input erp-as-avail-pop__note');
    input.id = MEMO_ID;
    input.type = 'text';
    input.maxLength = 500;
    input.placeholder = '예: 오른쪽 문짝 1짝, 원래 크기 그대로';
    const actions = el('div', 'erp-as-avail-pop__actions');
    const closeBtn = el('button', 'erp-pro-btn erp-pro-btn--ghost', '닫기');
    closeBtn.type = 'button';
    closeBtn.dataset.act = 'close';
    const sendBtn = el('button', 'erp-pro-btn erp-pro-btn--primary', '부탁하기');
    sendBtn.type = 'button';
    sendBtn.dataset.act = 'send';
    actions.append(closeBtn, sendBtn);
    pop.append(label, input, actions);
    document.body.appendChild(pop);
    position(btn);
    input.focus();

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); sendBtn.click(); }
    });
    pop.addEventListener('click', async function (e) {
      const act = e.target.closest('[data-act]');
      if (!act || act.disabled) return;
      if (act.dataset.act === 'close') { closePop(); btn.focus(); return; }
      sendBtn.disabled = true;
      const data = await send(orderId, input.value.trim());
      closePop();
      if (data.success) {
        settle(btn, orderId, data.data && data.data.state);
        feedback('도면팀에 부탁했어요. 도면 담당 폰에 알림이 가요.', false);
        return;
      }
      if (data.code === 'AS_DRAWING_OPEN') {
        // 다른 사람이 먼저 부탁했거나 도면팀이 시작했다 — 칸 글자를 지금 상태로 맞춘다.
        settle(btn, orderId, data.data && data.data.state);
      }
      feedback(data.error || '부탁하지 못했어요. 잠시 뒤 다시 해 주세요.', true);
    });
  }

  document.addEventListener('click', function (e) {
    const btn = e.target.closest ? e.target.closest('[data-as-drawing-request]') : null;
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      if (pop && pop.dataset.forOrder === orderIdOf(btn)) { closePop(); return; }
      openPop(btn);
      return;
    }
    if (pop && !pop.contains(e.target)) closePop();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePop(); });
})();
