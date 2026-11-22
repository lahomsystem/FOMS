/* Pointer-hint boot. SSOT copy of the pre-paint inline block in
   templates/partials/shared/layout_head.html (실행 코드는 두 곳이 글자 그대로 같아야 한다 —
   tests/domains/test_tablet_shell_t0_contract.py 가 대조한다).

   기록하는 것: 이 기기가 터치 기기(coarse)인지 마우스 PC(fine)인지 하나뿐. 서버가 "이 기기에 터치 전용
   표면(태블릿 작업 모드)을 렌더할 필요가 있는가" · "생산 쓰기 단추를 그리는가"를 다음 요청부터 알 수 있게 한다
   (서버 읽기는 foms/services/feature_flags.py pointer_hint 한 곳 — 쿠키 없음 = "모름").

   판정(2026-11-22 터치 감사): 주 포인터가 `(pointer: coarse)` 면 터치. 아니어도 `(any-pointer: coarse)`(터치 화면이 있음)
   이고 폰 · 태블릿이면 터치 — 키보드 커버 · 마우스를 단 태블릿은 주 포인터가 fine 이라 PC 보기 전용이 되던 것.
   폰 · 태블릿 = UA 의 Android · iPhone · iPad · iPod, 또는 터치 점 2개 이상인 Macintosh(데스크톱 UA 의 iPadOS) ·
   X11; Linux(데스크톱 사이트 모드의 안드로이드 태블릿). 터치 화면 Windows 노트북은 fine 그대로(PC 보기 전용이 맞다).

   왜 포인터인가 — 기기 특성이라 창 크기 조절·화면 회전으로 바뀌지 않는다. 뷰포트 폭 기반 표면(모바일 셸:
   max-width 991.98px)은 PC 창을 좁히면 필요해지므로 이 쿠키로 판단하면 안 된다.
   페이지마다 다시 재고(낡은 값이 남지 않게) 포인터 미디어 식이 바뀔 때도(키보드 커버를 떼고 붙임) 다시 쓴다.
   다시 재는 함수를 window.__fomsPointerHint 로 내놓는다(foms-wide-surface-recover.js 가 같은 판정을 쓴다).

   안전 폴백: 쿠키가 없거나 값이 이상하면 서버는 "모름"으로 본다(터치 표면은 그리고 · 생산 쓰기 단추는 표식만). */
(function () {
  var NAME = 'foms_ptr';
  try {
    if (!window.matchMedia) return;
    var primary = window.matchMedia('(pointer: coarse)');
    var any = window.matchMedia('(any-pointer: coarse)');
    var detect = function () {
      if (primary.matches) return 'coarse';
      if (!any.matches) return 'fine';
      var ua = navigator.userAgent || '';
      var touches = navigator.maxTouchPoints > 1;
      return /Android|iPhone|iPad|iPod/.test(ua) || (touches && /Macintosh|X11; Linux/.test(ua)) ? 'coarse' : 'fine';
    };
    var sync = function () {
      var value = detect();
      try {
        if (document.cookie.indexOf(NAME + '=' + value) === -1) {
          document.cookie =
            NAME + '=' + value + ';path=/;max-age=31536000;SameSite=Lax' +
            (location.protocol === 'https:' ? ';Secure' : '');
        }
      } catch (e) {
        console.warn('[foms-pointer-hint-boot] pointer hint write failed:', e);
      }
      return value;
    };
    sync();
    window.__fomsPointerHint = sync;
    [primary, any].forEach(function (m) {
      if (m.addEventListener) {
        m.addEventListener('change', sync);
      } else if (m.addListener) {
        m.addListener(sync);
      }
    });
  } catch (e) {
    console.warn('[foms-pointer-hint-boot] pointer hint unavailable:', e);
  }
})();
