/**
 * FOMS 태블릿 생산 칸반 — W13 (T2 / 목업 v8).
 *
 * 태블릿 가로 코호트의 생산 칸반(.foms-kanban) 열 이동 버튼(제작 시작 / 제작 완료)을
 * 처리한다. 신규 API 없이 기존 생산 워크플로 엔드포인트를 재사용한다:
 *   POST /api/orders/<id>/production/start    (제작대기 → 제작중)
 *   POST /api/orders/<id>/production/complete (제작중 → 제작완료/시공대기)
 * 성공 시 새로고침으로 read-model을 재조회한다(낙관 갱신은 비범위 — 간단·근본).
 *
 * 카드 본문 탭 → 상세는 tablet-side-sheet.js의 위임(위임 셀렉터에
 * `.foms-kanban-card[data-order-id]` 확장됨)이 처리한다. 여기서는 카드의 키보드 접근성
 * (Enter/Space, role=button 계약)만 보강한다.
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   AND CSS 마커 --foms-tablet-ui:ready(foms-tablet-side-sheet.css 정의, v2 셸 번들 로드
 *   여부에서 파생 — defect 1, 이중 정의 금지). 칸반 마크업은 서버가 v2 코호트에만 렌더하고
 *   CSS로 태블릿 가로에서만 표시하지만, 열 이동/키보드 핸들러도 동일 게이트로 방어한다.
 *
 * idempotent: window.__FOMS_KANBAN_BOUND 싱글턴 가드(perf 가드 G4 — fragment 재실행/
 *   재로드 시 전역 listener 중복 바인딩 방지). defer 로드(perf 가드 G1).
 */
(function () {
  "use strict";

  if (window.__FOMS_KANBAN_BOUND) return;
  window.__FOMS_KANBAN_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  // 코호트 게이트 = MQ AND CSS 마커(--foms-tablet-ui:ready). 마커는 시트 CSS가
  // body.erp-mobile-v2-layout 에 정의(v2 번들 로드 여부에서 파생 — defect 1, 이중 정의 금지).
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

  // data-kanban-action → { 엔드포인트 suffix, 확인 문구 }. 경로는 production/orders.py 실사.
  var ACTIONS = {
    start: {
      path: "/production/start",
      confirm: "제작을 시작하시겠습니까? (상태가 제작중으로 변경됩니다)",
    },
    complete: {
      path: "/production/complete",
      confirm: "제작을 완료하시겠습니까? (상태가 제작완료로 변경됩니다)",
    },
  };

  function moveOrder(orderId, action) {
    var spec = ACTIONS[action];
    if (!orderId || !spec) return;
    if (!window.confirm(spec.confirm)) return;

    fetch("/api/orders/" + encodeURIComponent(orderId) + spec.path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
    })
      .then(function (res) {
        return res.json().catch(function () {
          return { success: false, message: "서버 응답 형식 오류" };
        });
      })
      .then(function (data) {
        if (data && data.success) {
          window.location.reload();
        } else {
          window.alert("오류: " + ((data && data.message) || "처리에 실패했습니다."));
        }
      })
      .catch(function (err) {
        console.error("[foms-kanban] 열 이동 실패:", err);
        window.alert("처리 중 오류가 발생했습니다.");
      });
  }

  // 열 이동 버튼 위임(document). 버튼은 카드 안의 <button>이라 side-sheet INTERACTIVE
  // 제외 규칙에 걸려 시트를 열지 않는다(중복 동작 없음).
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;
    var btn = target.closest(".foms-kanban-move-btn[data-order-id]");
    if (!btn) return;
    ev.preventDefault();
    moveOrder(
      btn.getAttribute("data-order-id"),
      btn.getAttribute("data-kanban-action")
    );
  });

  // 카드 키보드 접근성: 포커스된 카드에서 Enter/Space → 클릭 합성 → side-sheet 오픈.
  document.addEventListener("keydown", function (ev) {
    if (!cohortActive()) return;
    if (ev.key !== "Enter" && ev.key !== " " && ev.key !== "Spacebar") return;
    var card = ev.target;
    if (!card || !card.classList || !card.classList.contains("foms-kanban-card")) return;
    ev.preventDefault();
    if (typeof card.click === "function") card.click();
  });
})();
