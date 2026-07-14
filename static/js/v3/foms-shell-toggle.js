/**
 * FOMS v3 셸 토글 — `foms_shell_pref` 쿠키 SSOT (v2 <-> v3 즉시 전환).
 *
 * 검증된 erp-mine-only.js 패턴(쿠키 set + 페이지 갱신)을 복제한다. 자격
 * 게이트는 서버(env 코호트, feature_flags.resolve_shell_variant)가 통제하므로
 * 쿠키를 위조해도 v3 코호트 밖이면 서버가 컷한다(권한 상승 불가).
 *
 * 트리거: `[data-foms-shell-toggle]` 요소 클릭. 속성값(`v2`|`v3`)이 목표
 * variant다. 쿠키를 1년간 set하고 현재 페이지를 리로드해 서버가 새 셸을
 * 렌더하게 한다.
 *
 * 성능 가드(G4): document에 1회만 위임 바인딩하고 `window.__FOS_TOGGLE_BOUND`
 * singleton 가드로 fragment 재실행 시 중복 바인딩을 막는다.
 */
(function () {
  "use strict";

  if (window.__FOS_TOGGLE_BOUND) return;
  window.__FOS_TOGGLE_BOUND = true;

  var COOKIE_NAME = "foms_shell_pref";
  var ONE_YEAR_SEC = 60 * 60 * 24 * 365;

  /**
   * `foms_shell_pref` 쿠키를 지정 variant로 set한다.
   * @param {string} variant "v2" 또는 "v3"
   */
  function setShellPref(variant) {
    document.cookie =
      COOKIE_NAME +
      "=" +
      encodeURIComponent(variant) +
      "; path=/; max-age=" +
      ONE_YEAR_SEC +
      "; SameSite=Lax";
  }

  function onToggleClick(ev) {
    var el =
      ev.target && ev.target.closest
        ? ev.target.closest("[data-foms-shell-toggle]")
        : null;
    if (!el) return;
    ev.preventDefault();
    var target = (el.getAttribute("data-foms-shell-toggle") || "").trim();
    if (target !== "v2" && target !== "v3") return;
    setShellPref(target);
    window.location.reload();
  }

  document.addEventListener("click", onToggleClick, true);

  window.FOMS_SHELL_TOGGLE = {
    COOKIE_NAME: COOKIE_NAME,
    setShellPref: setShellPref,
  };
})();
