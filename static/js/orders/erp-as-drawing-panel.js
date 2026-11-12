/**
 * 주문 화면 'AS 도면' 묶음(#erp-as-drawing-panel) — 완료 주문 AS 도면.
 * 설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §4.3-5.
 *
 * 원래 도면 갤러리와 따로 보인다. AS 도면 차수가 없으면 숨긴 채 둔다.
 * - GET  /api/orders/<id>/drawing/as                    지금 차수 · 지난 차수 · 확인할 수 있는지
 * - POST /api/orders/<id>/drawing/as/confirm            [확인했어요] (영업 · AS 담당 중 한 명이면 끝)
 * - POST /api/orders/<id>/drawing/as/request-revision   [고쳐 주세요] {reason}
 * 글자는 모두 textContent 로 넣는다(메모 · 파일 이름은 사람이 쓴 값).
 */
(function () {
  'use strict';
  if (window.__FOMS_ERP_AS_DRAWING_PANEL_BOUND) return;
  window.__FOMS_ERP_AS_DRAWING_PANEL_BOUND = true;

  var STATUS_LABELS = {
    WAITING: '도면팀 대기중', IN_PROGRESS: '도면팀 작업중', TRANSFERRED: '왔어요 · 확인해 주세요',
    RETURNED: '고쳐 달라고 함', CONFIRMED: '확인함', CANCELLED: '그만둠',
  };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  async function call(url, method, body) {
    var data = {};
    try {
      var res = await fetch(url, {
        method: method || 'GET',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      });
      try { data = await res.json(); } catch (_) { data = {}; }
    } catch (e) {
      data = { success: false, error: '인터넷 연결을 확인해 주세요.' };
    }
    if (!data || !data.success) {
      return { ok: false, message: (data && (data.error || data.message)) || '불러오지 못했어요.' };
    }
    return { ok: true, data: data.data || {} };
  }

  function filesList(files) {
    var ul = el('ul', 'dw-as-files list-unstyled mb-2');
    (files || []).forEach(function (f) {
      var li = el('li');
      var a = el('a');
      a.href = f.view_url;
      a.target = '_blank';
      a.rel = 'noopener';
      var img = el('img');
      img.loading = 'lazy';
      img.src = f.view_url;
      img.alt = f.name || 'AS 도면';
      a.appendChild(img);
      a.appendChild(el('span', null, f.name || 'AS 도면'));
      li.appendChild(a);
      ul.appendChild(li);
    });
    return ul;
  }

  function setStatus(panel, text, ok) {
    var s = panel.querySelector('[data-erp-as-status]');
    if (!s) return;
    s.textContent = text || '';
    s.classList.toggle('d-none', !text);
    s.classList.toggle('text-success', !!ok);
    s.classList.toggle('text-danger', !ok);
  }

  function render(panel, data) {
    var rounds = data.rounds || [];
    if (!rounds.length) { panel.classList.add('d-none'); return; }
    var cur = data.current || rounds[rounds.length - 1];
    panel.textContent = '';
    var head = el('div', 'dw-as-head');
    head.appendChild(el('span', 'dw-as-badge', 'AS'));
    head.appendChild(el('strong', null, 'AS 도면 ' + cur.no + '차'));
    head.appendChild(el('span', 'dw-as-status is-' + String(cur.status || '').toLowerCase(),
      STATUS_LABELS[cur.status] || cur.status || ''));
    panel.appendChild(head);
    if (cur.memo) panel.appendChild(el('p', 'dw-as-memo mb-1', cur.memo));
    panel.appendChild(el('p', 'small text-muted mb-1', '원래 최종 도면은 아래 도면 칸 그대로예요.'));
    if ((cur.files || []).length) panel.appendChild(filesList(cur.files));

    var actions = el('div', 'dw-as-actions');
    if (data.can_review) {
      var ok = el('button', 'btn btn-sm btn-success', '확인했어요');
      ok.type = 'button';
      ok.setAttribute('data-erp-as-act', 'confirm');
      var back = el('button', 'btn btn-sm btn-outline-danger', '고쳐 주세요');
      back.type = 'button';
      back.setAttribute('data-erp-as-act', 'revision-open');
      actions.appendChild(ok);
      actions.appendChild(back);
    }
    var link = el('a', 'btn btn-sm btn-outline-secondary', '도면 작업실에서 보기');
    link.href = data.workbench_url || '#';
    actions.appendChild(link);
    panel.appendChild(actions);

    if (data.can_review) {
      var form = el('div', 'dw-as-revision-form d-none');
      form.setAttribute('data-erp-as-revision-form', '');
      var label = el('label', 'small fw-semibold', '무엇을 고쳐야 하나요');
      label.htmlFor = 'erp-as-revision-reason';
      var ta = el('textarea', 'form-control form-control-sm');
      ta.id = 'erp-as-revision-reason';
      ta.rows = 2;
      ta.maxLength = 500;
      var send = el('button', 'btn btn-sm btn-danger mt-1', '고쳐 달라고 보내기');
      send.type = 'button';
      send.setAttribute('data-erp-as-act', 'revision');
      form.appendChild(label);
      form.appendChild(ta);
      form.appendChild(send);
      panel.appendChild(form);
    }
    var status = el('div', 'small mt-2 d-none');
    status.setAttribute('data-erp-as-status', '');
    status.setAttribute('role', 'status');
    panel.appendChild(status);
    panel.classList.remove('d-none');
  }

  async function load(panel) {
    var id = panel.getAttribute('data-order-id') || '';
    if (!id) return;
    var r = await call('/api/orders/' + encodeURIComponent(id) + '/drawing/as');
    if (!r.ok) return;   // 볼 수 없는 주문 · 오류는 조용히 숨긴다(원래 도면 칸은 그대로)
    render(panel, r.data);
  }

  async function act(panel, name, btn) {
    var id = panel.getAttribute('data-order-id') || '';
    var base = '/api/orders/' + encodeURIComponent(id) + '/drawing/as/';
    if (name === 'revision-open') {
      var f = panel.querySelector('[data-erp-as-revision-form]');
      if (f) { f.classList.remove('d-none'); var t = f.querySelector('textarea'); if (t) t.focus(); }
      return;
    }
    var r;
    if (name === 'confirm') {
      if (!window.confirm('이 AS 도면을 확인했어요. 도면팀에 알려요.')) return;
      btn.disabled = true;
      r = await call(base + 'confirm', 'POST', {});
    } else if (name === 'revision') {
      var ta = panel.querySelector('#erp-as-revision-reason');
      var reason = ta ? ta.value.trim() : '';
      if (!reason) { setStatus(panel, '무엇을 고쳐야 하는지 적어 주세요.', false); if (ta) ta.focus(); return; }
      btn.disabled = true;
      r = await call(base + 'request-revision', 'POST', { reason: reason });
    } else {
      return;
    }
    if (!r.ok) { btn.disabled = false; setStatus(panel, r.message, false); return; }
    await load(panel);
    setStatus(panel, name === 'confirm' ? '확인했어요.' : '고쳐 달라고 보냈어요.', true);
  }

  function init() {
    var panel = document.getElementById('erp-as-drawing-panel');
    if (!panel) return;
    panel.addEventListener('click', function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest('[data-erp-as-act]') : null;
      if (!btn) return;
      ev.preventDefault();
      act(panel, btn.getAttribute('data-erp-as-act'), btn);
    });
    load(panel);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
