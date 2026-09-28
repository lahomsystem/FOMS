/* Viewport-hint boot. SSOT copy of the pre-paint inline block in
   templates/partials/shared/layout_head.html (실행 코드는 두 곳이 글자 그대로 같아야 한다 —
   tests/domains/test_mobile_width_surfaces.py 가 대조한다).

   기록하는 것: 지금 창이 모바일 셸 경계(992px) 이상인지 한 비트 — 쿠키 `foms_vw` 에
   `wide` / `narrow`. 서버는 이것과 `foms_ptr=fine` 이 **둘 다** 맞을 때만(광폭 마우스 PC)
   광폭에서 CSS 가 끄는 모바일 v2 대시보드 표면을 렌더에서 뺀다
   (foms/services/feature_flags.py wants_mobile_width_surfaces).

   왜 matchMedia 인가 — CSS 은닉 규칙과 같은 식 `(min-width: 992px)` 을 그대로 물어야 확대·
   스크롤바 폭까지 CSS 판정과 어긋나지 않는다. change 이벤트는 경계를 넘을 때만 한 번 오므로
   리사이즈 디바운스가 필요 없다.

   창 폭은 기기 고정 특성이 아니다(foms_ptr·foms_scr 와 다르다). 그래서 1) 세션 쿠키로 두어
   다음 방문에 낡은 값이 남지 않게 하고, 2) 창이 경계를 넘으면 즉시 다시 쓰며, 3) 그래도
   이미 받은 화면에서 표면이 빠져 있으면 erp-shell.js 가 화면을 다시 받는다. 그때 쓰라고
   다시 쓰기 함수를 window.__fomsViewportHintSync 로 내놓는다(창 여러 개가 쿠키 하나를
   나눠 쓰므로, 다시 받기 직전에 이 창 값으로 맞춘다).

   안전 폴백: 쿠키가 없거나 값이 이상하면 서버는 전부 렌더한다(느릴 뿐 화면이 비지 않는다). */
(function () {
  var NAME = 'foms_vw';
  try {
    if (!window.matchMedia) return;
    var mq = window.matchMedia('(min-width: 992px)');
    var sync = function () {
      try {
        var value = mq.matches ? 'wide' : 'narrow';
        if (document.cookie.indexOf(NAME + '=' + value) !== -1) return;
        document.cookie =
          NAME + '=' + value + ';path=/;SameSite=Lax' +
          (location.protocol === 'https:' ? ';Secure' : '');
      } catch (e) {
        console.warn('[foms-viewport-hint-boot] viewport hint write failed:', e);
      }
    };
    sync();
    window.__fomsViewportHintSync = sync;
    if (mq.addEventListener) {
      mq.addEventListener('change', sync);
    } else if (mq.addListener) {
      mq.addListener(sync);
    }
  } catch (e) {
    console.warn('[foms-viewport-hint-boot] viewport hint unavailable:', e);
  }
})();
