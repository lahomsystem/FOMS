/* 생산 PC [고치기] — 설계서 docs/specs/2026-11-21-production-pc-viewer_SPEC.md §7 (관리자 · 생산팀, §13 결정 1).
 * [고치기] = 쿠키 foms_prod_edit=<켠 시각(epoch 초)> 를 Path=/erp/production 세션 쿠키(만료 없음 = 브라우저를 닫으면 사라짐)로
 * 심고 다시 받는다. [고치는 중] · [그만 고치기] = 쿠키를 지우고 다시 받는다. 새 API 없음.
 * 켠 시각 = 그 단추에 서버가 준 시각(data-foms-prod-edit-now) + **그 단추가 화면에 온 뒤** 흐른 시간 — 기기 시계가 틀려도 서버의
 * 2시간 판정(foms/services/production/pc_view.edit_cookie_fresh)이 어긋나지 않는다. 단추를 그릴지 · 켬으로 볼지는 서버가 정한다.
 * 2026-11-22: 흐른 시간을 문서를 연 때부터 셌더니 위 탭을 바꿔(셸 조각 교체) 새 단추가 오면 새 서버 시각에 옛 시간이 더해져
 * 켠 시각이 앞날이 되고 서버가 거절해 첫 누름이 아무 일도 안 했다. 단추마다 처음 본 때를 적는다(처음 실행 · 셸 교체 때).
 * 적어 둔 때가 없는 단추는 흐른 시간 0(값이 서버 시각보다 앞서지 않는다).
 * 셸 조각 교체로 다시 실행돼도 문서 리스너는 한 번만(window.__FOMS_PROD_EDIT). */
(function () {
  'use strict';

  if (window.__FOMS_PROD_EDIT) { return; }
  window.__FOMS_PROD_EDIT = true;

  var NAME = 'foms_prod_edit';
  var PATH = '/erp/production';
  var seenAt = typeof WeakMap === 'function' ? new WeakMap() : null; // 단추 → 화면에 온 때(Date.now)

  function stampButtons() {
    if (!seenAt) { return; }
    var now = Date.now();
    [].slice.call(document.querySelectorAll('[data-foms-prod-edit]')).forEach(function (btn) {
      if (!seenAt.has(btn)) { seenAt.set(btn, now); }
    });
  }

  function issuedAt(btn) {
    var base = parseInt(btn.getAttribute('data-foms-prod-edit-now') || '', 10);
    var since = seenAt && seenAt.get(btn);
    var elapsed = since ? Math.max(0, Math.floor((Date.now() - since) / 1000)) : 0;
    return isNaN(base) ? Math.floor(Date.now() / 1000) : base + elapsed;
  }

  function writeCookie(on, btn) {
    var tail = ';path=' + PATH + ';SameSite=Lax' + (window.location.protocol === 'https:' ? ';Secure' : '');
    document.cookie = on ? (NAME + '=' + issuedAt(btn) + tail) : (NAME + '=;max-age=0' + tail);
  }

  stampButtons();
  document.addEventListener('foms:erp-shell-fragment-swapped', stampButtons);
  document.addEventListener('foms:main-content-swapped', stampButtons);

  document.addEventListener('click', function (e) {
    var t = e.target;
    var btn = t && typeof t.closest === 'function' ? t.closest('[data-foms-prod-edit]') : null;
    if (!btn || btn.disabled) { return; }
    e.preventDefault();
    btn.disabled = true;
    try {
      writeCookie(btn.getAttribute('data-foms-prod-edit') === 'on', btn);
    } catch (err) {
      btn.disabled = false; // 쿠키를 못 쓰는 브라우저 — 화면은 그대로(보기 전용)
      return;
    }
    window.location.reload();
  });
})();
