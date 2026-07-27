/**
 * FOMS 태블릿 도면 리뷰 (E2 · 단계 2) — 태블릿 가로 코호트에서 도면 썸네일 탭 시
 * 전역 이미지 뷰어(GlobalImageViewer — 블러 배경·핀치 줌·스와이프)로 전체화면 열람.
 *
 * 대상 = `[data-foms-drawing-viewer]` 마커 2종:
 *   1) 갤러리 카드 썸네일(.foms-drawing-gallery-card__thumb) — 서버가 내려준
 *      `data-foms-drawing-files`(JSON: [{key, view_url, download_url, filename}])를 그대로
 *      뷰어 파일 목록으로 사용한다. 이미지 도면이 0장인 카드는 서버가 마커를 안 붙인다.
 *   2) 관리 시트 스트립 썸네일(.foms-drawing-sheet__sheet-thumb) — 마법사 미전달 autosave
 *      PNG. 같은 스트립의 형제 img 들을 모아 클릭 인덱스로 연다(열람 전용, 판정 없음).
 *
 * 활성 게이트: MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse).
 *   비-코호트(PC·폰)에선 완전 무동작 → 카드 앵커의 기존 상세 이동 fallback 이 보존된다.
 *
 * 리스너: document 위임 클릭 1개. 시트 aside 는 tablet-side-sheet.js 가 런타임에 생성하므로
 *   컨테이너 바인딩이 불가하다(갤러리·시트 스트립을 한 리스너로 커버).
 *   preventDefault + stopPropagation 은 필수 — 카드가 <a> 라 네비 차단 책임이 여기 있다
 *   (tablet-side-sheet.js 는 이 마커를 만나면 early-return 해 시트를 열지 않는다).
 * idempotent: window.__FOMS_DRAWING_REVIEW_BOUND 싱글턴 가드(perf 가드 G4 — fragment 재실행
 *   시 전역 listener 중복 방지).
 */
(function () {
  "use strict";

  if (window.__FOMS_DRAWING_REVIEW_BOUND) return;
  window.__FOMS_DRAWING_REVIEW_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  var VIEWER_SELECTOR = "[data-foms-drawing-viewer]";
  var STRIP_SELECTOR = ".foms-drawing-sheet__strip";

  function cohortActive() {
    return MQ.matches;
  }

  /**
   * 뷰어 호출(단일 경로). 부재 시 무음 금지 — 경고 후 중단.
   * @param {Array<Object>} files {view_url, download_url, filename} 목록
   * @param {number} index 초기 표시 인덱스
   */
  function openViewer(files, index) {
    if (!window.GlobalImageViewer || typeof window.GlobalImageViewer.open !== "function") {
      console.warn("[foms-drawing-review] GlobalImageViewer 미로드 — 도면 뷰어 열기 중단");
      return;
    }
    if (!files || !files.length) return;
    var idx = index > 0 && index < files.length ? index : 0;
    window.GlobalImageViewer.open(files, idx);
  }

  /**
   * 갤러리 카드 썸네일 → 서버 JSON 파일 목록.
   * data-* + 가드 파싱 패턴(인라인 JSON.parse('{{ x|tojson }}') 금지).
   * @param {Element} marker
   * @returns {Array<Object>} 파싱 실패/비배열이면 빈 배열
   */
  function galleryFiles(marker) {
    var raw = marker.getAttribute("data-foms-drawing-files");
    if (!raw) return [];
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      console.warn("[foms-drawing-review] 도면 파일 목록 파싱 실패 — 뷰어 생략", e);
      return [];
    }
  }

  /**
   * 시트 스트립 썸네일 → 같은 스트립의 형제 img 전부를 뷰어 파일 목록으로 구성.
   * @param {Element} marker 클릭된 스트립 img
   * @returns {{files: Array<Object>, index: number}}
   */
  function stripFiles(marker) {
    var strip = marker.closest(STRIP_SELECTOR);
    var nodes = strip
      ? strip.querySelectorAll(VIEWER_SELECTOR + "[data-view-url]")
      : [marker];
    var files = [];
    var index = 0;
    Array.prototype.forEach.call(nodes, function (node) {
      var viewUrl = node.getAttribute("data-view-url") || "";
      if (!viewUrl) return;
      if (node === marker) index = files.length;
      files.push({
        view_url: viewUrl,
        download_url: viewUrl,
        filename: node.getAttribute("data-filename") || "도면",
      });
    });
    return { files: files, index: index };
  }

  // 단일 document 위임: 코호트에서만 동작. 갤러리 카드 썸네일 + 시트 스트립 공통 진입점.
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;
    var marker = target.closest(VIEWER_SELECTOR);
    if (!marker) return;

    // 카드 <a> 네비 차단 + 사이드 시트 열기 차단(책임이 side-sheet 에서 이관됨).
    ev.preventDefault();
    ev.stopPropagation();

    if (marker.hasAttribute("data-foms-drawing-files")) {
      openViewer(galleryFiles(marker), 0);
      return;
    }
    var strip = stripFiles(marker);
    openViewer(strip.files, strip.index);
  });
})();
