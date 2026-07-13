/**
 * FOMS 태블릿 사이드 시트 (W10 · T2) — 태블릿 가로(코호트)에서 legacy 그리드 행 탭 시
 * 우측 400px 시트에 주문 상세/edit fragment 로드. 페이지 이동/모달 대체.
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   **AND** CSS 마커 --foms-tablet-ui:ready 존재. 마커는 foms-tablet-side-sheet.css 가
 *   body.erp-mobile-v2-layout 에 정의하며, 이 CSS 는 v2 셸 코호트에서만(layout_head 게이트)
 *   foms-mobile-surfaces.css 번들로 로드된다. 즉 **JS 활성 = CSS 로드 여부에서 파생**(이중
 *   정의 금지, defect 1). 비-v2(legacy/v3) coarse 태블릿에선 마커 부재 → 완전 무동작 →
 *   기존 행 클릭·인라인 편집 동작 그대로 보존(preventDefault·미스타일 시트 덤프 방지).
 *
 * 대상 행/카드: #erp-grid tr.erp-main-row[data-order-id](컨트롤타워/시공/생산 3그리드 공유),
 *   생산 칸반 카드(.foms-kanban-card), AS 대시보드 PC 테이블 본행(.erp-as-dashboard
 *   .erp-pro-table-wrapper tbody tr[data-order-id]), 이력 대시보드 본행(.erp-history-mobile-shell
 *   tr.history-main-row[data-order-id]) — B1/B2 융합 레이어 확장.
 *   행 안의 a/button/input/select/label/textarea/[role="button"]/.form-check 클릭은 제외
 *   (closest로 무시) → 인라인 날짜 편집, 액션 버튼, 첨부 미리보기, 상세 링크, 체크박스,
 *   이력 chevron(확장 토글, role="button") 동작 보존.
 *
 * 콘텐츠 URL(SSOT resolveSheetUrl): 탭한 행/카드에 data-foms-sheet-url 이 있으면 그 URL을,
 *   없으면 아래 기본 edit fragment URL을 시트 본문으로 로드한다(대시보드 목업 시트 등 페이지
 *   전용 상세가 opt-in). 파이프라인은 URL과 무관하게 행 data-stage 로만 렌더(기존 로직 불변).
 * 기본 콘텐츠: 기존 fragment 인프라 재사용 — /api/foms/fragment/order/<id>/edit?open=erp-order
 *   (foms/services/foms_split_view.py build_split_master_cards.detail_href 와 동일 URL) fetch →
 *   시트 바디 주입 → 스크립트 재실행(runtime/erp-shell.js activateScripts 정책 모방: type 보존
 *   해 application/json 프리로드 블록이 클래식 스크립트로 실행돼 SyntaxError 나는 것 방지) →
 *   foms:main-content-swapped / foms:erp-shell-fragment-swapped 디스패치(호스트 재바인딩).
 *   로딩 스피너 + 실패 시 재시도 버튼(에러 무음 금지).
 *
 * 닫기: X 버튼 · ESC 만(비차단 non-modal 패널 표준 — 외부 탭 자동 닫기는 "뒤 그리드 계속
 *   조작 가능"과 모순이라 제거, defect 6). 스크림 없음(aria-modal=false, 그리드 계속 보임).
 * idempotent: window.__FOMS_TABLET_SHEET_BOUND 싱글턴 가드(perf 가드 G4 — 전역 listener 중복 방지).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_SHEET_BOUND) return;
  window.__FOMS_TABLET_SHEET_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  // 코호트 게이트 = MQ 매치 AND CSS 마커(--foms-tablet-ui:ready). 마커는 시트 CSS가
  // body.erp-mobile-v2-layout 에 정의(defect 1 — JS 활성이 CSS 로드 여부에서 파생, 이중
  // 정의 금지). CSS 로드 상태는 페이지 수명 내 불변이라 positive 결과만 캐시한다.
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

  // W13: 생산 칸반 카드(#erp-grid 밖)도 시트 대상에 포함 — 카드 탭 → 동일 fragment 상세.
  // B1/B2(2026-07-12): AS(.erp-as-dashboard PC 테이블 본행) + 이력(.erp-history-mobile-shell
  // 본행)까지 융합 레이어 확장. 이력 확장행(.history-detail-row)은 클래스가 달라 미포함이고,
  // chevron 확장 토글은 아래 INTERACTIVE([role="button"])가 제외해 기존 확장 UX가 보존된다.
  var ROW_SELECTOR =
    "#erp-grid tr.erp-main-row[data-order-id], " +
    ".foms-kanban-card[data-order-id], " +
    ".foms-completion-grid tbody tr[data-order-id], " +
    ".erp-as-dashboard .erp-pro-table-wrapper tbody tr[data-order-id], " +
    ".erp-history-mobile-shell tr.history-main-row[data-order-id], " +
    // 도면 갤러리 카드(<a>): data-foms-erp-no-shell 로 erp-shell 인터셉트를 끊고
    // 여기서 시트를 연다(카드 자신이 anchor지만 INTERACTIVE 가드는 행 자신을 제외 안 함).
    ".foms-drawing-gallery-card[data-order-id]";
  // 행 내 인터랙티브 요소 클릭은 시트 대상에서 제외(closest 체인). AS 인라인 날짜/체크박스
  // (.form-check)·상세 링크·이력 chevron([role="button"])까지 커버.
  var INTERACTIVE =
    'a, button, input, select, label, textarea, [role="button"], .form-check';

  function fragmentUrl(orderId) {
    return "/api/foms/fragment/order/" + encodeURIComponent(orderId) + "/edit?open=erp-order";
  }

  // 시트 본문 URL 해석(SSOT). 탭한 행/카드에 data-foms-sheet-url 이 있으면 그 URL(페이지
  // 전용 상세 — 예: 컨트롤타워 목업 시트 /erp/dashboard/tablet-sheet/<id>)을 시트 본문으로
  // 로드하고, 없으면 기존 edit fragment URL 로 폴백한다. 열림/닫힘/active 행/파이프라인 등
  // 나머지 동작은 불변이며, 파이프라인은 여전히 행의 data-stage 로만 렌더된다(URL 무관).
  function resolveSheetUrl(orderId, row) {
    var explicit = row && row.getAttribute ? row.getAttribute("data-foms-sheet-url") : null;
    if (explicit && explicit.trim()) return explicit.trim();
    return fragmentUrl(orderId);
  }

  var sheet = null;
  var headerTitle = null;
  var pipeEl = null;
  var bodyEl = null;
  var lastFocus = null;
  var currentOrderId = null;
  var hideTimer = null;
  var _stageCatalog = null;

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
      '<div class="foms-tablet-sheet__pipe" hidden></div>' +
      '<div class="foms-tablet-sheet__body"></div>';
    document.body.appendChild(sheet);
    headerTitle = sheet.querySelector(".foms-tablet-sheet__title");
    pipeEl = sheet.querySelector(".foms-tablet-sheet__pipe");
    bodyEl = sheet.querySelector(".foms-tablet-sheet__body");
    sheet.querySelector(".foms-tablet-sheet__close").addEventListener("click", close);
  }

  // 진행 단계 파이프라인(시트 크롬 — 헤더 아래). 8단계 카탈로그(순서·표시명)는 서버가
  // STAGE_SEQUENCE(order_timeline_v3, SSOT)를 그리드 컨테이너의 data-foms-stage-catalog(JSON)로
  // 내려보내고, 현재 단계는 탭한 행의 data-stage(=erp_stage_code)에서 읽는다. JS에 단계 목록을
  // 하드코딩하지 않는다(카탈로그·순서·표시명 전부 서버 SSOT). 카탈로그는 페이지 수명 내 불변 → 캐시.
  function stageCatalog() {
    if (_stageCatalog) return _stageCatalog;
    var host = document.querySelector("[data-foms-stage-catalog]");
    if (!host) return null;
    var raw = host.getAttribute("data-foms-stage-catalog");
    if (!raw) return null;
    // safeJsonParse 패턴: data-* 속성 + 가드 파싱(인라인 JSON.parse('{{ x|tojson }}') 금지).
    try {
      var parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length) {
        _stageCatalog = parsed;
        return _stageCatalog;
      }
    } catch (e) {
      // 카탈로그 손상 → 파이프 생략(우아한 부재). 무음 금지 — 경고 로그.
      console.warn("[foms-tablet-sheet] 단계 카탈로그 파싱 실패 — 파이프 생략", e);
    }
    return null;
  }

  // 시트 열림마다 현재 단계로 파이프를 재구성한다(idempotent). 카탈로그 부재 또는 행의
  // data-stage 가 카탈로그 코드와 미매치(AS/이력/칸반 등 단계 파생 불가)면 hidden → 파이프 생략.
  function renderPipe(row) {
    if (!pipeEl) return;
    var stageCode = row && row.getAttribute ? row.getAttribute("data-stage") : null;
    var catalog = stageCode ? stageCatalog() : null;
    var curIdx = -1;
    if (stageCode && catalog) {
      for (var i = 0; i < catalog.length; i++) {
        if (catalog[i] && catalog[i].code === stageCode) {
          curIdx = i;
          break;
        }
      }
    }
    if (curIdx < 0) {
      pipeEl.hidden = true;
      pipeEl.innerHTML = "";
      return;
    }
    var html = ['<ol class="foms-tablet-pipe">'];
    for (var j = 0; j < catalog.length; j++) {
      var cls = "foms-tablet-pipe__step";
      var marker;
      if (j < curIdx) {
        cls += " is-done";
        marker = "✓"; // ✓
      } else if (j === curIdx) {
        cls += " is-now";
        marker = String(j + 1);
      } else {
        marker = String(j + 1);
      }
      html.push(
        '<li class="' + cls + '">' +
          '<span class="foms-tablet-pipe__marker">' + marker + "</span>" +
          '<span class="foms-tablet-pipe__label"></span>' +
          "</li>"
      );
    }
    html.push("</ol>");
    pipeEl.innerHTML = html.join("");
    // 라벨은 textContent 로 주입(카탈로그가 서버 SSOT이나 텍스트 노드 삽입으로 안전 확보).
    var labels = pipeEl.querySelectorAll(".foms-tablet-pipe__label");
    for (var k = 0; k < labels.length; k++) {
      labels[k].textContent = (catalog[k] && catalog[k].label) || "";
    }
    pipeEl.hidden = false;
  }

  // fragment fetch/주입/스크립트 재실행/staleness 는 공용 로더(fragment-loader.js) 소유.
  // 이 모듈은 컨테이너(bodyEl)와 URL 만 넘긴다. currentOrderId 는 행 하이라이트 staleness 용.
  function load(orderId, url) {
    currentOrderId = orderId;
    if (!window.FomsFragmentLoader || typeof window.FomsFragmentLoader.load !== "function") {
      console.error("[foms-tablet-sheet] FomsFragmentLoader 미로드 — 시트 로드 중단");
      return;
    }
    window.FomsFragmentLoader.load(bodyEl, url, {
      requestedWith: "foms-tablet-sheet",
      source: "tablet-sheet",
      loadingText: "주문 상세 로딩 중…",
    });
  }

  function markActiveRow(row) {
    // 정리 쿼리는 행 타입 무관(#erp-grid 행·AS/이력 본행·칸반 카드) — 클래스만으로 매치해
    // 다른 표면에 남은 stale 하이라이트까지 확실히 제거한다.
    var prev = document.querySelectorAll(".foms-tablet-sheet-active");
    Array.prototype.forEach.call(prev, function (el) {
      el.classList.remove("foms-tablet-sheet-active");
    });
    if (row) row.classList.add("foms-tablet-sheet-active");
  }

  function open(orderId, row) {
    if (!orderId) return;
    var sheetUrl = resolveSheetUrl(orderId, row);
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
    renderPipe(row);
    sheet.hidden = false;
    // reflow 확보 후 클래스 부착 → transform 슬라이드 인.
    requestAnimationFrame(function () {
      sheet.classList.add("is-open");
    });
    load(orderId, sheetUrl);
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
    if (pipeEl) {
      pipeEl.hidden = true;
      pipeEl.innerHTML = "";
    }
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

  // 단일 document 위임: 코호트에서만 동작. 행 탭 → 열기/전환.
  // (defect 6) 외부 탭 자동 닫기는 제거 — 비차단 non-modal 패널은 뒤 그리드를 계속 조작
  // 가능해야 하는데, 외부 탭 닫기는 그 조작(다른 행 클릭 등)마다 시트를 닫아 모순. X·ESC만 닫기.
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;

    var row = target.closest(ROW_SELECTOR);
    if (row) {
      var interactive = target.closest(INTERACTIVE);
      // 행 내 액션/링크/입력 보존. 단 행 자신이 인터랙티브 시맨틱(role="button" 등,
      // 완료 그리드 a11y 행)이어도 그건 시트 트리거 자체이므로 제외 대상이 아니다
      // (2026-07-12: 완료 행 role="button" ↔ [role="button"] 가드 자충돌 봉합).
      if (interactive && interactive !== row && row.contains(interactive)) return;
      ev.preventDefault();
      open(row.getAttribute("data-order-id"), row);
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && sheet && !sheet.hidden) close();
  });

  // 회전/포인터 변화로 코호트를 벗어나면 열린 시트를 정리.
  function onMqChange() {
    if (!cohortActive()) close();
  }
  if (typeof MQ.addEventListener === "function") {
    MQ.addEventListener("change", onMqChange);
  } else if (typeof MQ.addListener === "function") {
    MQ.addListener(onMqChange);
  }
})();
