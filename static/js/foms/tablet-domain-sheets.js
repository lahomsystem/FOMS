/**
 * FOMS 태블릿 도메인 시트 액션 + 생산 칸반 필터 (T2 · 목업 v8 마감).
 *
 * 태블릿 가로(코호트)에서 우측 사이드 시트 본문에 로드되는 도메인 전용 액션 버튼과,
 * 생산 칸반 상단 필터 바를 처리한다. 신규 API 없이 기존 워크플로 엔드포인트를 재사용한다:
 *   - 생산 완료: POST /api/orders/<id>/production/complete   (에러 키 = message)
 *   - 출고 배정: POST /api/erp/shipment/update/<id>          (권한 실패 = 403)
 * 성공 시 시트를 닫고 새로고침으로 read-model 을 재조회한다(낙관 갱신은 비범위 — 간단·근본).
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   AND CSS 마커 --foms-tablet-ui:ready(foms-tablet-side-sheet.css 가 body.erp-mobile-v2-layout
 *   에 정의 — v2 셸 번들 로드 여부에서 파생, 이중 정의 금지). 비-코호트에서 완전 무동작.
 *
 * 위임: 시트 액션은 document 단일 'click' 위임, 생산 필터는 document 'input'/'change' 위임.
 *   시트 본문은 fragment 로 교체되므로 요소별 바인딩 대신 document 위임으로 swap 을 견딘다
 *   (foms:erp-shell-fragment-swapped 후에도 핸들러 유지 — 재바인딩 불필요).
 *
 * idempotent: window.__FOMS_DOMAIN_SHEETS_BOUND 싱글턴 가드(perf 가드 G4 — 전역 listener
 *   중복 바인딩 방지). defer 로드(perf 가드 G1).
 */
(function () {
  "use strict";

  if (window.__FOMS_DOMAIN_SHEETS_BOUND) return;
  window.__FOMS_DOMAIN_SHEETS_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  // 코호트 게이트 = MQ AND CSS 마커(--foms-tablet-ui:ready). 마커는 시트 CSS 가
  // body.erp-mobile-v2-layout 에 정의(v2 번들 로드 여부에서 파생 — 이중 정의 금지).
  // CSS 로드 상태는 페이지 수명 내 불변이라 positive 결과만 캐시한다.
  var _uiReady = false;
  function tabletUiReady() {
    if (_uiReady) return true;
    var body = document.body;
    if (!body) return false;
    var v = window.getComputedStyle(body).getPropertyValue("--foms-tablet-ui");
    if (v && v.trim() === "ready") _uiReady = true;
    return _uiReady;
  }
  function cohortActive() {
    return MQ.matches && tabletUiReady();
  }

  // 시트 닫기 = 시트 크롬의 X 버튼(.foms-tablet-sheet__close) 클릭 합성.
  // 시트 자체는 tablet-side-sheet.js 소유 — 여기서는 표준 닫기 경로만 재사용(중복 구현 금지).
  function closeSheet() {
    var closeBtn = document.querySelector(".foms-tablet-sheet__close");
    if (closeBtn) closeBtn.click();
  }

  // 생산 완료 — 기존 생산 워크플로 엔드포인트 재사용. 에러는 message 키(error 아님).
  function productionComplete(orderId) {
    if (!orderId) return;
    fetch("/api/orders/" + encodeURIComponent(orderId) + "/production/complete", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then(function (res) {
        return res.json().catch(function () {
          return { success: false, message: "서버 응답 형식 오류" };
        });
      })
      .then(function (data) {
        if (data && data.success) {
          closeSheet();
          window.location.reload();
        } else {
          window.alert("오류: " + ((data && data.message) || "처리 실패"));
        }
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 생산 완료 실패:", err);
        window.alert("처리 중 오류가 발생했습니다.");
      });
  }

  // 출고 배정 — 시공팀/시공시간/현장 메모를 기존 출고 update 엔드포인트로 저장.
  // 입력은 시트 본문(.foms-tablet-sheet__body) 범위에서 조회, 없으면 document 폴백.
  function shipmentAssign(orderId) {
    if (!orderId) return;
    var scope = document.querySelector(".foms-tablet-sheet__body") || document;

    var teamInput = scope.querySelector('input[name="tablet-assign-team"]:checked');
    var team = teamInput ? teamInput.value : null;
    var constructionWorkers = team ? [team] : [];

    var timeInput = scope.querySelector("input[data-tablet-assign-time]");
    var constructionTime = timeInput ? timeInput.value.trim() : "";

    var memoInput = scope.querySelector("input[data-tablet-assign-memo]");
    var memo = memoInput ? memoInput.value.trim() : "";
    var siteExtra = memo ? [{ text: memo, color: "#334155" }] : [];

    fetch("/api/erp/shipment/update/" + encodeURIComponent(orderId), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        construction_workers: constructionWorkers,
        construction_time: constructionTime,
        site_extra: siteExtra,
      }),
    })
      .then(function (res) {
        var status = res.status;
        return res
          .json()
          .catch(function () {
            return { success: false, message: "서버 응답 형식 오류" };
          })
          .then(function (data) {
            return { status: status, data: data || {} };
          });
      })
      .then(function (result) {
        var data = result.data;
        if (result.status === 403) {
          window.alert(data.message || "권한이 없습니다.");
          return;
        }
        if (data.success) {
          closeSheet();
          window.location.reload();
        } else {
          window.alert("오류: " + (data.message || "저장 실패"));
        }
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 출고 배정 실패:", err);
        window.alert("처리 중 오류가 발생했습니다.");
      });
  }

  // ---- 생산 칸반 필터(클라이언트 사이드) --------------------------------------
  // 컨트롤: 검색어 input, 상태 select(''|제작대기|제작중|제작완료), 공장 select(''|1|2),
  // 리셋 button. 세 값을 읽어 열 표시(상태)와 카드 표시(검색+공장)를 재계산한다.

  function applyProdFilter() {
    if (!cohortActive()) return;
    var searchEl = document.querySelector("input[data-tablet-prod-search]");
    var statusEl = document.querySelector("select[data-tablet-prod-status]");
    var factoryEl = document.querySelector("select[data-tablet-prod-factory]");
    var search = searchEl ? searchEl.value : "";
    var status = statusEl ? statusEl.value : "";
    var factory = factoryEl ? factoryEl.value : "";
    var searchLower = search.toLowerCase();

    var cols = document.querySelectorAll(".foms-kanban-col[data-kanban-bucket]");
    Array.prototype.forEach.call(cols, function (col) {
      var bucket = col.getAttribute("data-kanban-bucket");
      // 상태 필터: 미선택('')이면 전부 표시, 선택 시 해당 버킷 열만 표시.
      var colVisible = status === "" || bucket === status;
      col.style.display = colVisible ? "" : "none";
      if (!colVisible) return; // 숨긴 열의 카드는 재평가 불필요(열이 다시 보일 때 재계산).

      var cards = col.querySelectorAll(".foms-kanban-card");
      Array.prototype.forEach.call(cards, function (card) {
        var searchOK =
          search === "" ||
          card.textContent.toLowerCase().indexOf(searchLower) !== -1;

        var factoryOK;
        if (factory === "") {
          factoryOK = true;
        } else {
          var isFactory2 =
            card.querySelector(".foms-kanban-card__factory") !== null ||
            card.getAttribute("data-factory2") === "1";
          factoryOK = factory === "2" ? isFactory2 : !isFactory2;
        }

        card.style.display = searchOK && factoryOK ? "" : "none";
      });
    });
  }

  function resetProdFilter() {
    var searchEl = document.querySelector("input[data-tablet-prod-search]");
    var statusEl = document.querySelector("select[data-tablet-prod-status]");
    var factoryEl = document.querySelector("select[data-tablet-prod-factory]");
    if (searchEl) searchEl.value = "";
    if (statusEl) statusEl.value = "";
    if (factoryEl) factoryEl.value = "";
    applyProdFilter();
  }

  // ---- 단일 document 'click' 위임 --------------------------------------------
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;

    // 생산 필터 리셋 버튼.
    var resetBtn = target.closest("button[data-tablet-prod-reset]");
    if (resetBtn) {
      ev.preventDefault();
      resetProdFilter();
      return;
    }

    // 시트 도메인 액션 버튼.
    var actionBtn = target.closest("[data-tablet-sheet-action]");
    if (!actionBtn) return;
    var action = actionBtn.getAttribute("data-tablet-sheet-action");
    var orderId = actionBtn.getAttribute("data-order-id");

    if (action === "sheet-cancel") {
      ev.preventDefault();
      closeSheet();
      return;
    }
    if (action === "production-complete") {
      ev.preventDefault();
      productionComplete(orderId);
      return;
    }
    if (action === "shipment-assign") {
      ev.preventDefault();
      shipmentAssign(orderId);
      return;
    }
  });

  // ---- 생산 필터 'input'/'change' 위임 ---------------------------------------
  function onFilterEvent(ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;
    if (
      target.closest(
        "input[data-tablet-prod-search], select[data-tablet-prod-status], select[data-tablet-prod-factory]"
      )
    ) {
      applyProdFilter();
    }
  }
  document.addEventListener("input", onFilterEvent);
  document.addEventListener("change", onFilterEvent);
})();
