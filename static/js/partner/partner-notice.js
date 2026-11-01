/**
 * 협력사 공지 창(사용자 2026-11-02) — "확인"을 눌러야만 닫힌다. 배경 누르기 · Esc 로는 안 닫힌다.
 *
 * 서버 계약: POST /api/partner/notices/<id>/ack → {success, data:{pending:[{id, title, message}]}, error}
 * 확인하면 남은 공지가 있으면 다음 공지를, 없으면 창을 닫는다. 첫 공지는 서버가 그린다(partials/notice_modal.html).
 */
(function () {
  'use strict';

  function bind(root) {
    var url = root.getAttribute('data-pp-notice-url') || '';
    var title = root.querySelector('[data-pp-notice-title]');
    var body = root.querySelector('[data-pp-notice-body]');
    var status = root.querySelector('[data-pp-notice-status]');
    var ok = root.querySelector('[data-pp-notice-ok]');
    if (!ok) return;

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
      if (title) title.textContent = notice.title || '';
      if (body) body.textContent = notice.message || '';
      ok.focus();
    }

    ok.addEventListener('click', async function () {
      var id = ok.getAttribute('data-pp-notice-id');
      ok.disabled = true;
      if (status) status.textContent = '';
      try {
        var resp = await fetch(url.replace('/notices/0/', '/notices/' + id + '/'), {
          method: 'POST', credentials: 'same-origin',
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!data || !data.success) throw new Error((data && data.error) || '확인을 저장하지 못했습니다. 다시 눌러 주세요.');
        var pending = (data.data && data.data.pending) || [];
        if (pending.length) show(pending[0]);
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
