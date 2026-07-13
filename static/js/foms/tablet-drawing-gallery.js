/**
 * FOMS 태블릿 도면 작업실 갤러리 컨트롤 (목업 v8 프레임 03, 2026-07-13 · W-DRAWING).
 *
 * 세 가지 최소 배선을 document 위임 싱글턴으로 담당한다(신규 전역 listener 중복 방지 —
 * perf 가드 G4). 카드 탭 → 시트 로드는 공용 tablet-side-sheet.js(data-foms-sheet-url)가
 * 소유하므로 여기서 재구현하지 않는다.
 *
 *   1) 갤러리 카드 크기 토글(작게 220 / 보통 260 / 크게 320) — .foms-drawing-gallery 에
 *      is-size-sm|md|lg 클래스 적용 + localStorage 지속(fragment swap 시 재적용).
 *   2) "도면공 일괄 배정" 버튼 → 기존 벌크 UI(window.openBatchAssignModal, workbench-dashboard.js).
 *   3) 관리 시트 "시트 전달" 버튼 → 기존 transfer-pending API(신규 엔드포인트 없음).
 *
 * defer 로드(perf G1). 코호트 DOM 에만 요소가 존재하므로 MQ 게이트는 불필요(off-cohort 무해).
 */
(function () {
  "use strict";

  if (window.__FOMS_DRAWING_GALLERY_BOUND) return;
  window.__FOMS_DRAWING_GALLERY_BOUND = true;

  var SIZE_KEY = "foms:drawing-gallery-size";
  var SIZES = ["sm", "md", "lg"];

  function readSize() {
    var v = null;
    try {
      v = window.localStorage.getItem(SIZE_KEY);
    } catch (e) {
      v = null;
    }
    return SIZES.indexOf(v) >= 0 ? v : "md";
  }

  function writeSize(size) {
    try {
      window.localStorage.setItem(SIZE_KEY, size);
    } catch (e) {
      /* private mode 등 localStorage 불가 — 세션 내 적용만, 무음 금지 아님(치명 아님) */
    }
  }

  function applySize(size) {
    var gallery = document.querySelector(".foms-drawing-gallery");
    if (gallery) {
      SIZES.forEach(function (s) {
        gallery.classList.toggle("is-size-" + s, s === size);
      });
    }
    document.querySelectorAll("[data-foms-gallery-size]").forEach(function (btn) {
      var on = btn.getAttribute("data-foms-gallery-size") === size;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function syncSize() {
    applySize(readSize());
  }

  function submitFilterForm(el) {
    var form = el.closest("form");
    if (form) form.submit();
  }

  async function transferPending(orderId, btn) {
    if (!orderId) return;
    if (!window.confirm("전달 대기 중인 저장 시트를 담당자에게 전달할까요?")) return;
    btn.disabled = true;
    try {
      var res = await fetch(
        "/api/orders/" + encodeURIComponent(orderId) + "/drawing-wizard/transfer-pending",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: "", mode: "APPEND" }),
        }
      );
      var data = await res.json();
      if (data && data.success) {
        window.alert((data.data && data.data.message) || "전달되었습니다.");
        window.location.reload();
      } else {
        btn.disabled = false;
        window.alert("오류: " + ((data && data.message) || "전달 실패"));
      }
    } catch (err) {
      btn.disabled = false;
      console.error("[tablet-drawing-gallery] 시트 전달 실패", err);
      window.alert("전달 중 오류가 발생했습니다.");
    }
  }

  document.addEventListener("click", function (ev) {
    var target = ev.target;
    if (!target || !target.closest) return;

    var sizeBtn = target.closest("[data-foms-gallery-size]");
    if (sizeBtn) {
      ev.preventDefault();
      var size = sizeBtn.getAttribute("data-foms-gallery-size");
      if (SIZES.indexOf(size) < 0) size = "md";
      writeSize(size);
      applySize(size);
      return;
    }

    var bulkBtn = target.closest("[data-foms-drawing-bulk-assign]");
    if (bulkBtn) {
      ev.preventDefault();
      if (typeof window.openBatchAssignModal === "function") {
        window.openBatchAssignModal();
      } else {
        window.alert("일괄 배정을 사용할 수 없습니다. 페이지를 새로고침해 주세요.");
      }
      return;
    }

    var transferBtn = target.closest("[data-foms-drawing-transfer]");
    if (transferBtn && !transferBtn.disabled) {
      ev.preventDefault();
      transferPending(transferBtn.getAttribute("data-order-id"), transferBtn);
      return;
    }
  });

  // 정렬 셀렉트 / 체크박스 변경 = 필터 폼 즉시 제출(GET).
  document.addEventListener("change", function (ev) {
    var target = ev.target;
    if (target && target.closest && target.closest(".foms-drawing-workshop__autofilter")) {
      submitFilterForm(target);
    }
  });

  function init() {
    syncSize();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // ERP 셸 fragment swap 시 갤러리 DOM 교체 → 저장된 크기 재적용.
  document.addEventListener("foms:erp-shell-fragment-swapped", syncSize);
})();
