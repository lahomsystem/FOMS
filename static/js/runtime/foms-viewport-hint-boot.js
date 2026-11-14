/* Viewport-hint boot. SSOT copy of the pre-paint inline block in
   templates/partials/shared/layout_head.html (실행 코드는 두 곳이 글자 그대로 같아야 한다 —
   tests/domains/test_mobile_width_surfaces.py 가 대조한다).

   기록하는 것: 지금 창이 모바일 셸 경계(992px) 이상인지와, 이상이면 방향 — 쿠키 `foms_vw` 에
   `narrow`(992 미만) / `wide`(992 이상 가로) / `tall`(992 이상 세로). 서버는 이것과 `foms_ptr`
   로 광폭 마우스 PC(fine + wide/tall)와 태블릿 가로(coarse + wide)를 가려, 그 화면에서 CSS 가
   끄는 모바일 v2 대시보드 표면과(태블릿 가로면) PC 작업 큐를 렌더에서 뺀다
   (foms/services/feature_flags.py wants_mobile_width_surfaces · wants_desktop_queue_surfaces).
   값 이름은 서로 앞부분이 겹치지 않게 고른다 — 아래 indexOf 검사가 앞부분 일치로도 참이 된다.

   왜 matchMedia 인가 — CSS 은닉 규칙과 같은 식 `(min-width: 992px)` 을 그대로 물어야 확대·
   스크롤바 폭까지 CSS 판정과 어긋나지 않는다. 방향도 CSS 은닉 식의 `orientation` 과 같은 식으로
   묻는다(큰 태블릿은 세로도 992 이상이라 폭만으로는 가로·세로를 못 가른다). change 이벤트는
   경계를 넘거나 방향이 바뀔 때만 한 번 오므로 리사이즈 디바운스가 필요 없다.

   창 폭·방향은 기기 고정 특성이 아니다(foms_ptr·foms_scr 와 다르다). 그래서 1) 세션 쿠키로 두어
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
    var portrait = window.matchMedia('(orientation: portrait)');
    var sync = function () {
      try {
        var value = !mq.matches ? 'narrow' : portrait.matches ? 'tall' : 'wide';
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
    [mq, portrait].forEach(function (m) {
      if (m.addEventListener) {
        m.addEventListener('change', sync);
      } else if (m.addListener) {
        m.addListener(sync);
      }
    });
  } catch (e) {
    console.warn('[foms-viewport-hint-boot] viewport hint unavailable:', e);
  }
})();
