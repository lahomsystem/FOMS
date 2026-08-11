/* Pointer-hint boot. SSOT copy of the pre-paint inline block in
   templates/partials/shared/layout_head.html.

   기록하는 것: `(pointer: coarse)` 매치 여부 하나뿐. 서버가 "이 기기에 터치 전용
   표면(태블릿 작업 모드)을 렌더할 필요가 있는가"를 다음 요청부터 알 수 있게 한다.

   왜 pointer 인가 — 이 값은 기기 고정 특성이라 창 크기 조절·화면 회전으로 바뀌지
   않는다. 뷰포트 폭 기반 표면(모바일 셸: max-width 991.98px)은 PC 창을 좁히면
   필요해지므로 이 쿠키로 판단하면 안 된다. coarse 전용 표면만 대상이다.

   안전 폴백: 쿠키가 없거나 값이 이상하면 서버는 "coarse 일 수 있다"로 보고 지금처럼
   전부 렌더한다(느릴 뿐 화면이 비지 않는다). 첫 요청은 항상 폴백 경로다. */
(function () {
  var NAME = 'foms_ptr';
  try {
    if (!window.matchMedia) return;
    var value = window.matchMedia('(pointer: coarse)').matches ? 'coarse' : 'fine';
    // 값이 그대로면 재기록하지 않는다(매 페이지 document.cookie 쓰기 회피).
    if (document.cookie.indexOf(NAME + '=' + value) !== -1) return;
    document.cookie =
      NAME + '=' + value + ';path=/;max-age=31536000;SameSite=Lax' +
      (location.protocol === 'https:' ? ';Secure' : '');
  } catch (e) {
    console.warn('[foms-pointer-hint-boot] pointer hint unavailable:', e);
  }
})();
