/**
 * 협력사 공지 창(사용자 2026-11-02) — "확인"을 눌러야만 닫힌다. 배경 누르기 · Esc 로는 안 닫힌다.
 *
 * 두 출처를 차례로 띄운다(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5): 서버가 정한 차례를
 * data-pp-notice-queue(JSON [{source, id, title, message, by, at}])로 받는다 — 기존 협력사 공지 먼저, 그다음 FOMS 공지사항.
 * 서버 계약(둘 다 {success, data:{pending:[...]}, error}):
 *   source=partner → POST /api/partner/notices/<id>/ack (data-pp-notice-url)
 *   source=notice  → POST /api/notices/<id>/ack          (data-pp-notice-new-url)
 * 확인하면 차례의 다음 공지를, 없으면 창을 닫는다. 첫 공지는 서버가 그린다(partials/notice_modal.html).
 */
(function () {
  'use strict';

  function parseQueue(raw) {
    var safe = window.ERPUtils && window.ERPUtils.safeJsonParse;
    var value;
    if (typeof safe === 'function') value = safe(raw, []);
    else { try { value = JSON.parse(raw || '[]'); } catch (e) { value = []; } }
    return Array.isArray(value) ? value : [];
  }

  function bind(root) {
    var urls = {
      partner: root.getAttribute('data-pp-notice-url') || '',
      notice: root.getAttribute('data-pp-notice-new-url') || '',
    };
    var title = root.querySelector('[data-pp-notice-title]');
    var body = root.querySelector('[data-pp-notice-body]');
    var meta = root.querySelector('[data-pp-notice-meta]');
    var count = root.querySelector('[data-pp-notice-count]');
    var status = root.querySelector('[data-pp-notice-status]');
    var ok = root.querySelector('[data-pp-notice-ok]');
    if (!ok) return;
    var queue = parseQueue(root.getAttribute('data-pp-notice-queue'));
    if (!queue.length) {
      queue = [{ source: ok.getAttribute('data-pp-notice-source') || 'partner', id: ok.getAttribute('data-pp-notice-id') }];
    }
    var total = queue.length;
    var index = 0;

    document.body.classList.add('pp-notice-open');
    ok.focus();
    // 창 밖으로 초점이 나가지 않게 — 단추가 하나뿐이라 Tab 도 그 단추에 머문다. Esc 는 무시한다.
    root.addEventListener('keydown', function (ev) {
      if (ev.key === 'Tab' || ev.key === 'Escape') {
        ev.preventDefault();
        ok.focus();
      }
    });

    function close() {
      root.remove();
      document.body.classList.remove('pp-notice-open');
    }

    function show(notice) {
      ok.setAttribute('data-pp-notice-id', String(notice.id));
      ok.setAttribute('data-pp-notice-source', notice.source === 'notice' ? 'notice' : 'partner');
      if (title) title.textContent = notice.title || '';
      if (body) body.textContent = notice.message || '';
      if (meta) meta.textContent = notice.by ? [notice.by, notice.at].filter(Boolean).join(' · ') : '';
      if (count) count.textContent = total > 1 ? (index + 1) + ' / ' + total : '';
      ok.focus();
    }

    ok.addEventListener('click', async function () {
      var id = ok.getAttribute('data-pp-notice-id');
      var source = ok.getAttribute('data-pp-notice-source') === 'notice' ? 'notice' : 'partner';
      ok.disabled = true;
      if (status) status.textContent = '';
      try {
        var resp = await fetch(urls[source].replace('/notices/0/', '/notices/' + encodeURIComponent(id) + '/'), {
          method: 'POST', credentials: 'same-origin',
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!data || !data.success) throw new Error((data && data.error) || '확인을 저장하지 못했습니다. 다시 눌러 주세요.');
        index += 1;
        if (index < queue.length) show(queue[index]);
        else close();
      } catch (err) {
        if (status) {
          status.textContent = err.message;
          status.classList.add('pp-status--error');
        }
      }
      ok.disabled = false;
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.querySelector('[data-pp-notice]');
    if (root) bind(root);
  });
})();
