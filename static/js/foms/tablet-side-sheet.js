/**
 * FOMS 태블릿 사이드 시트 (W10 · T2) — 태블릿 가로(코호트)에서 legacy 그리드 행 탭 시
 * 우측 400px 시트에 주문 상세/edit fragment 로드. 페이지 이동/모달 대체.
 *
 * 활성 코호트: (min-width: 992px) and (orientation: landscape) and (pointer: coarse).
 *   미매치(폰/세로/데스크톱) 시 완전 무동작 → 기존 행 클릭·인라인 편집 동작 그대로 보존.
 *
 * 대상 행: #erp-grid tr.erp-main-row[data-order-id]
 *   (컨트롤타워 dashboard_grid / 시공 filters_grid / 생산 filters_grid 3그리드 공유 마크업).
 *   행 안의 a/button/input/select/label/textarea 클릭은 제외(closest로 무시) → 인라인
 *   실측일·시공일 편집, 액션 버튼, 첨부 미리보기, 상세 링크, 체크박스 동작 보존.
 *
 * 콘텐츠: 기존 fragment 인프라 재사용 — /api/foms/fragment/order/<id>/edit?open=erp-order
 *   (foms/services/foms_split_view.py build_split_master_cards.detail_href 와 동일 URL) fetch →
 *   시트 바디 주입 → 스크립트 재실행(runtime/erp-shell.js activateScripts 정책 모방: type 보존
 *   해 application/json 프리로드 블록이 클래식 스크립트로 실행돼 SyntaxError 나는 것 방지) →
 *   foms:main-content-swapped / foms:erp-shell-fragment-swapped 디스패치(호스트 재바인딩).
 *   로딩 스피너 + 실패 시 재시도 버튼(에러 무음 금지).
 *
 * 닫기: 시트 밖 탭 · X 버튼 · ESC. 스크림 없음(비차단 — aria-modal=false, 그리드 계속 보임).
 * idempotent: window.__FOMS_TABLET_SHEET_BOUND 싱글턴 가드(perf 가드 G4 — 전역 listener 중복 방지).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_SHEET_BOUND) return;
  window.__FOMS_TABLET_SHEET_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );
  var ROW_SELECTOR = "#erp-grid tr.erp-main-row[data-order-id]";
  var INTERACTIVE = "a, button, input, select, label, textarea";

  function fragmentUrl(orderId) {
    return "/api/foms/fragment/order/" + encodeURIComponent(orderId) + "/edit?open=erp-order";
  }

  var sheet = null;
  var headerTitle = null;
  var bodyEl = null;
  var lastFocus = null;
  var currentOrderId = null;
  var hideTimer = null;

  function ensureSheet() {
    if (sheet) return;
    sheet = document.createElement("aside");
    sheet.className = "foms-tablet-sheet";
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-modal", "false"); // 비차단 — 뒤 그리드 계속 조작 가능
    sheet.setAttribute("aria-label", "주문 상세");
    sheet.tabIndex = -1;
    sheet.hidden = true;
    sheet.innerHTML =
      '<div class="foms-tablet-sheet__head">' +
      '<span class="foms-tablet-sheet__title"></span>' +
      '<button type="button" class="foms-tablet-sheet__close" aria-label="닫기">✕</button>' +
      "</div>" +
      '<div class="foms-tablet-sheet__body"></div>';
    document.body.appendChild(sheet);
    headerTitle = sheet.querySelector(".foms-tablet-sheet__title");
    bodyEl = sheet.querySelector(".foms-tablet-sheet__body");
    sheet.querySelector(".foms-tablet-sheet__close").addEventListener("click", close);
  }

  // runtime/erp-shell.js activateScripts 정책 모방: innerHTML로 주입된 <script>는 실행되지
  // 않으므로 새 노드로 교체해 재실행한다. type 보존(application/json 데이터 블록 보호).
  function activateScripts(container) {
    var nodes = container.querySelectorAll("script");
    Array.prototype.forEach.call(nodes, function (old) {
      var s = document.createElement("script");
      if (old.id) s.id = old.id;
      if (old.type) s.type = old.type;
      if (old.nonce) s.nonce = old.nonce;
      if (old.src) {
        s.src = old.src;
        s.async = old.async;
        s.defer = old.defer;
        if (old.crossOrigin) s.crossOrigin = old.crossOrigin;
        if (old.integrity) s.integrity = old.integrity;
      } else {
        s.textContent = old.textContent;
      }
      old.parentNode.replaceChild(s, old);
    });
  }

  function setLoading() {
    bodyEl.innerHTML =
      '<div class="foms-tablet-sheet__state" role="status">' +
      '<span class="foms-tablet-sheet__spinner" aria-hidden="true"></span>' +
      "<span>주문 상세 로딩 중…</span>" +
      "</div>";
  }

  function setError(orderId) {
    bodyEl.innerHTML =
      '<div class="foms-tablet-sheet__state foms-tablet-sheet__state--error" role="alert">' +
      "<p>주문 상세를 불러오지 못했습니다.</p>" +
      '<button type="button" class="foms-tablet-sheet__retry">다시 시도</button>' +
      "</div>";
    var retry = bodyEl.querySelector(".foms-tablet-sheet__retry");
    if (retry) {
      retry.addEventListener("click", function () {
        load(orderId);
      });
    }
  }

  function load(orderId) {
    currentOrderId = orderId;
    setLoading();
    fetch(fragmentUrl(orderId), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "foms-tablet-sheet" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("fragment HTTP " + res.status);
        return res.text();
      })
      .then(function (html) {
        // 사이가 더 최신 주문으로 바뀌었으면(빠른 연속 탭) 이 응답은 폐기.
        if (currentOrderId !== orderId) return;
        bodyEl.innerHTML = html;
        activateScripts(bodyEl);
        try {
          document.dispatchEvent(
            new CustomEvent("foms:main-content-swapped", {
              detail: { source: "tablet-sheet", url: fragmentUrl(orderId) },
            })
          );
          document.dispatchEvent(
            new CustomEvent("foms:erp-shell-fragment-swapped", {
              detail: { url: fragmentUrl(orderId) },
            })
          );
        } catch (e) {
          /* CustomEvent 미지원 환경 무시 */
        }
        bodyEl.scrollTop = 0;
      })
      .catch(function (err) {
        if (currentOrderId !== orderId) return;
        console.error("[foms-tablet-sheet] fragment load failed:", err);
        setError(orderId);
      });
  }

  function markActiveRow(row) {
    var prev = document.querySelectorAll(".erp-main-row.foms-tablet-sheet-active");
    Array.prototype.forEach.call(prev, function (el) {
      el.classList.remove("foms-tablet-sheet-active");
    });
    if (row) row.classList.add("foms-tablet-sheet-active");
  }

  function open(orderId, row) {
    if (!orderId) return;
    ensureSheet();
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    // 시트가 이미 열린 상태에서 다른 행을 탭한 경우 lastFocus를 덮어쓰지 않는다.
    if (sheet.hidden || !sheet.classList.contains("is-open")) {
      lastFocus = document.activeElement;
    }
    headerTitle.textContent = "주문 상세";
    markActiveRow(row);
    sheet.hidden = false;
    // reflow 확보 후 클래스 부착 → transform 슬라이드 인.
    requestAnimationFrame(function () {
      sheet.classList.add("is-open");
    });
    load(orderId);
    try {
      sheet.focus({ preventScroll: true });
    } catch (e) {
      sheet.focus();
    }
  }

  function close() {
    if (!sheet || sheet.hidden) return;
    sheet.classList.remove("is-open");
    markActiveRow(null);
    currentOrderId = null;
    if (hideTimer) clearTimeout(hideTimer);
    // 슬라이드 아웃 트랜지션 후 완전히 숨김(reduced-motion이면 트랜지션 0 → 타이머만 사용).
    hideTimer = setTimeout(function () {
      if (sheet && !sheet.classList.contains("is-open")) {
        sheet.hidden = true;
        bodyEl.innerHTML = "";
      }
      hideTimer = null;
    }, 360);
    if (lastFocus && typeof lastFocus.focus === "function") {
      try {
        lastFocus.focus({ preventScroll: true });
      } catch (e) {
        /* focus 옵션 미지원 무시 */
      }
    }
    lastFocus = null;
  }

  // 단일 document 위임: 코호트에서만 동작. 행 탭 → 열기/전환, 시트 밖 탭 → 닫기.
  document.addEventListener("click", function (ev) {
    if (!MQ.matches) return;
    var target = ev.target;
    if (!target || !target.closest) return;

    var row = target.closest(ROW_SELECTOR);
    if (row) {
      var interactive = target.closest(INTERACTIVE);
      if (interactive && row.contains(interactive)) return; // 행 내 액션/링크/입력 보존
      ev.preventDefault();
      open(row.getAttribute("data-order-id"), row);
      return;
    }

    // 시트가 열려 있고, 클릭이 시트 내부가 아니면 닫기(시트 밖 탭).
    if (sheet && !sheet.hidden && !sheet.contains(target)) {
      close();
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && sheet && !sheet.hidden) close();
  });

  // 회전/포인터 변화로 코호트를 벗어나면 열린 시트를 정리.
  function onMqChange() {
    if (!MQ.matches) close();
  }
  if (typeof MQ.addEventListener === "function") {
    MQ.addEventListener("change", onMqChange);
  } else if (typeof MQ.addListener === "function") {
    MQ.addListener(onMqChange);
  }
})();
