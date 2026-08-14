/* Screen-hint boot. SSOT copy of the pre-paint inline block in
   templates/partials/shared/layout_head.html.

   기록하는 것: 물리 화면의 긴 변(CSS px) 하나뿐 — `max(screen.width, screen.height)`.
   서버가 "이 기기가 광폭(≥992) 표면에 도달할 수 있는가"를 다음 요청부터 알 수 있게 한다.

   왜 screen 인가 — 이 값은 기기 고정 특성이다. 창 크기 조절로 바뀌지 않고, 회전하면
   width/height 가 서로 바뀔 뿐 최댓값은 그대로다. 반면 innerWidth(뷰포트)는 사용자가
   실시간으로 바꾸므로 서버 판정에 쓰면 안 된다 — PC 창을 좁히는 순간 값이 낡는다.
   [[foms-pointer-hint-boot.js]] 의 pointer 힌트와 같은 계열(기기 고정 특성만 기록).

   쓰임: 긴 변이 992 미만인 기기(=폰)는 어떤 방향으로도 ≥992 미디어쿼리에 도달할 수
   없다. 그런 기기에 광폭 전용 표면(데스크톱 작업 큐)을 보내는 것은 순수 낭비다.
   ※ 768 기준 표면(AS 데스크톱 표: d-md-block)은 대상 아님 — 폰 가로(예: 844)가
   768 을 넘으므로 실제로 표시된다. 992 기준 표면만 안전하다.

   안전 폴백: 쿠키가 없거나 숫자로 파싱되지 않으면 서버는 "광폭일 수 있다"로 보고
   지금처럼 전부 렌더한다(느릴 뿐 화면이 비지 않는다). 첫 요청은 항상 폴백 경로다. */
(function () {
  var NAME = 'foms_scr';
  try {
    if (!window.screen || !window.screen.width || !window.screen.height) return;
    var value = String(Math.max(window.screen.width, window.screen.height));
    // 값이 그대로면 재기록하지 않는다(매 페이지 document.cookie 쓰기 회피).
    if (document.cookie.indexOf(NAME + '=' + value) !== -1) return;
    document.cookie =
      NAME + '=' + value + ';path=/;max-age=31536000;SameSite=Lax' +
      (location.protocol === 'https:' ? ';Secure' : '');
  } catch (e) {
    console.warn('[foms-screen-hint-boot] screen hint unavailable:', e);
  }
})();
