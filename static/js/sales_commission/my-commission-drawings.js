/**
 * "내 수수료" 명세서 — 줄을 펼쳐 보이는 확정 도면 작은 그림을 누르면 FOMS 전역 모달(GlobalImageViewer:
 * 바깥 흐림 · 두 손가락 확대 · 축소)로 크게 본다. 같은 줄의 그림을 함께 넘겨 옆으로 밀면 다음 장이다.
 * 설계서 2026-11-06-freelancer-sales-commission §6.6 D31.
 *
 * 그림은 <a href=보기 주소 target=_blank> 라서 모달이 없거나 이 파일이 늦게 와도 새 탭으로 열린다.
 * 문서에 한 번만 건다(아래 탭 조각 바꾸기로 다시 실행돼도 겹치지 않게).
 */
(function () {
  "use strict";

  if (window.__FOMS_MC_DRAWINGS_BOUND === "1") return;
  window.__FOMS_MC_DRAWINGS_BOUND = "1";

  function fileOf(link) {
    return {
      view_url: link.getAttribute("data-view-url") || link.getAttribute("href") || "",
      download_url: link.getAttribute("data-download-url") || "",
      filename: link.getAttribute("data-filename") || "도면",
      key: link.getAttribute("data-key") || "",
    };
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    var link = target && target.closest ? target.closest("[data-foms-mc-drawing]") : null;
    if (!link) return;
    var viewer = window.GlobalImageViewer;
    if (!viewer || typeof viewer.open !== "function") return; // 새 탭으로 열리게 둔다
    var group = link.closest("[data-foms-mc-drawings]") || link.parentNode;
    var links = Array.prototype.slice.call(group.querySelectorAll("[data-foms-mc-drawing]"));
    var files = links.map(fileOf).filter(function (file) { return !!file.view_url; });
    if (!files.length) return;
    event.preventDefault();
    viewer.open(files, Math.max(0, links.indexOf(link)));
  });
})();
