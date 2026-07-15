/**
 * FOMS 태블릿 시공 워크모드 — 카드 탭 / 기간 칩 / 시공 불가.
 *
 * 태블릿 가로 코호트의 시공 워크모드(.foms-construction-workmode)에서
 * 좌측 카드 목록과 우측 상세 패널을 연동한다. 신규 엔드포인트는 만들지 않고
 * 기존 시공 불가 API를 재사용한다:
 *   POST /api/orders/<id>/construction/fail   (사유 4종 + 상세)
 *
 * 이 파일이 소유하는 상호작용은 3가지뿐이다:
 *   1) 카드 탭      → 활성 카드 전환 + 대응 패널/확인 노출
 *   2) 기간 칩      → today/tomorrow/week 필터로 카드 노출 토글
 *   3) 시공 불가    → 사유 선택 프롬프트 → fail API 호출
 * `.erp-construction-action`(제작 시작/완료 게이트 등)은
 *   templates/construction/partials/scripts.html 의 기존 위임이 처리하므로
 *   여기서는 절대 바인딩·간섭하지 않는다.
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   AND CSS 마커 --foms-tablet-ui:ready (foms-tablet-side-sheet.css 정의, v2 셸 번들
 *   로드 여부에서 파생 — 이중 정의 금지). tablet-production-kanban.js 와 동일 패턴.
 *
 * idempotent: window.__FOMS_CWORK_BOUND 싱글턴 가드(perf 가드 G4 — fragment 재실행/
 *   재로드 시 전역 listener 중복 바인딩 방지). defer 로드(perf 가드 G1).
 */
(function () {
  "use strict";

  if (window.__FOMS_CWORK_BOUND) return;
  window.__FOMS_CWORK_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  // 코호트 게이트 = MQ AND CSS 마커(--foms-tablet-ui:ready). 마커는 시트 CSS가
  // body.erp-mobile-v2-layout 에 정의(v2 번들 로드 여부에서 파생 — 이중 정의 금지).
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

  // ---- 카드 활성화 (탭 / 필터 공용) ----------------------------------------

  // 지정 attr 값이 id 인 요소만 노출, 나머지는 hidden.
  function toggleById(selector, attr, id) {
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) {
      els[i].hidden = els[i].getAttribute(attr) !== id;
    }
  }

  // 해당 id 카드를 활성화하고 대응 패널/확인만 노출한다.
  function activateCard(id) {
    if (!id) return;
    var cards = document.querySelectorAll(".foms-cwork-card");
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.toggle(
        "is-active",
        cards[i].getAttribute("data-order-id") === id
      );
    }
    toggleById("[data-cwork-panel]", "data-cwork-panel", id);
    toggleById("[data-cwork-confirm]", "data-cwork-confirm", id);
  }

  // 카드 탭 → 활성 전환. 시공 불가 버튼/기존 시공 액션 버튼 클릭은 각자 핸들러가
  // 처리하므로 활성 전환을 건너뛴다(중복 동작 방지).
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-cwork-fail]") || t.closest(".erp-construction-action")) return;
    var card = t.closest(".foms-cwork-card[data-order-id]");
    if (!card) return;
    activateCard(card.getAttribute("data-order-id"));
  });

  // ---- 기간 칩 필터 ---------------------------------------------------------

  // "YYYY-MM-DD" → 일수(day count). Date.UTC 는 DST 영향이 없어 날짜 단위
  // 비교에서 TZ drift 가 없다. 형식 불일치/빈 값이면 null.
  function dayCountFromStr(s) {
    if (!s) return null;
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s.trim());
    if (!m) return null;
    var y = parseInt(m[1], 10);
    var mo = parseInt(m[2], 10);
    var d = parseInt(m[3], 10);
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    return Math.floor(Date.UTC(y, mo - 1, d) / 86400000);
  }

  // 카드 날짜가 선택 범위에 드는지. "all"은 무조건 노출(과거/미정 포함) — 어제 시공처럼
  // 미래 범위에 안 걸리는 건까지 볼 수 있는 탈출구. 그 외 범위에서 빈/파싱불가 날짜는 숨김.
  function matchesRange(dateStr, range, todayDC) {
    if (range === "all") return true;
    if (todayDC === null) return false;
    var dc = dayCountFromStr(dateStr);
    if (dc === null) return false;
    if (range === "today") return dc === todayDC;
    if (range === "tomorrow") return dc === todayDC + 1;
    if (range === "week") return dc >= todayDC && dc <= todayDC + 6;
    return false;
  }

  // 전체 카드에서 today/tomorrow/week/미정 건수를 집계(빈 상태 힌트용).
  function computeRangeCounts(cards, todayDC) {
    var c = { today: 0, tomorrow: 0, week: 0, undated: 0 };
    if (todayDC === null) return c;
    for (var i = 0; i < cards.length; i++) {
      var dc = dayCountFromStr(cards[i].getAttribute("data-cwork-date"));
      if (dc === null) {
        c.undated++;
        continue;
      }
      if (dc === todayDC) c.today++;
      if (dc === todayDC + 1) c.tomorrow++;
      if (dc >= todayDC && dc <= todayDC + 6) c.week++;
    }
    return c;
  }

  var EMPTY_TITLES = {
    today: "오늘 시공 일정이 없습니다",
    tomorrow: "내일 시공 일정이 없습니다",
    week: "이번 주 시공 일정이 없습니다",
    all: "표시할 시공 건이 없습니다",
  };

  // 현재 범위 외에서 잡히는 건수를 "· "로 이어 힌트 문자열 생성.
  function buildEmptyHint(counts, range) {
    var parts = [];
    if (range !== "today" && counts.today > 0) parts.push("오늘 " + counts.today + "건");
    if (range !== "tomorrow" && counts.tomorrow > 0) parts.push("내일 " + counts.tomorrow + "건");
    if (range !== "week" && counts.week > 0) parts.push("주간 " + counts.week + "건");
    if (counts.undated > 0) parts.push("일정 미정 " + counts.undated + "건");
    return parts.join(" · ");
  }

  // 뷰어/확인 패널 전부 은닉 + 중앙 placeholder 노출(활성 카드 0건일 때).
  function clearActivePanels(root) {
    var panels = document.querySelectorAll("[data-cwork-panel]");
    for (var i = 0; i < panels.length; i++) panels[i].hidden = true;
    var confs = document.querySelectorAll("[data-cwork-confirm]");
    for (var j = 0; j < confs.length; j++) confs[j].hidden = true;
    var vEmpty = root.querySelector("[data-cwork-viewer-empty]");
    if (vEmpty) vEmpty.hidden = false;
  }

  // 칩 클릭/초기화 → 활성 칩 전환 + 카드 노출 토글 + 활성 카드 재선정 + 건수/빈상태 동기화.
  function applyRangeFilter(chip) {
    var root = document.querySelector(".foms-construction-workmode");
    if (!root || !chip) return; // 워크모드 미존재 페이지에서 no-op.
    var range = chip.getAttribute("data-cwork-range");
    var chips = document.querySelectorAll(".foms-cwork-chip");
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle("is-active", chips[i] === chip);
    }
    // 기준 "오늘"은 서버가 루트에 심은 값(하드코딩 금지).
    var todayDC = dayCountFromStr(root.getAttribute("data-cwork-today"));

    var cards = document.querySelectorAll(".foms-cwork-card");
    var firstVisible = null;
    var activeVisible = null;
    var visibleCount = 0;
    for (var j = 0; j < cards.length; j++) {
      var card = cards[j];
      var visible = matchesRange(card.getAttribute("data-cwork-date"), range, todayDC);
      card.hidden = !visible;
      if (visible) {
        visibleCount++;
        if (!firstVisible) firstVisible = card;
        if (!activeVisible && card.classList.contains("is-active")) activeVisible = card;
      }
    }

    // 건수 배지 = 현재 범위의 노출 건수(서버 orders|length 아님 — "오늘 시공 · N건" 정직화).
    var countEl = root.querySelector("[data-cwork-count]");
    if (countEl) countEl.textContent = String(visibleCount);

    var tEmpty = root.querySelector("[data-cwork-empty]");
    var vEmpty = root.querySelector("[data-cwork-viewer-empty]");
    if (visibleCount === 0) {
      // 빈 범위 → 좌 타임라인 빈상태(제목·힌트) + 중앙 placeholder, 모든 패널 은닉.
      if (tEmpty) {
        var counts = computeRangeCounts(cards, todayDC);
        var titleEl = tEmpty.querySelector("[data-cwork-empty-title]");
        var hintEl = tEmpty.querySelector("[data-cwork-empty-hint]");
        if (titleEl) titleEl.textContent = EMPTY_TITLES[range] || EMPTY_TITLES.all;
        if (hintEl) hintEl.textContent = buildEmptyHint(counts, range);
        tEmpty.hidden = false;
      }
      clearActivePanels(root);
    } else {
      if (tEmpty) tEmpty.hidden = true;
      if (vEmpty) vEmpty.hidden = true;
      // 활성 카드가 여전히 보이면 그 카드를, 아니면 첫 노출 카드를 활성화.
      // 항상 activateCard 호출 → 직전 0건 상태에서 은닉된 패널도 확실히 복원(idempotent).
      var target = activeVisible || firstVisible;
      activateCard(target.getAttribute("data-order-id"));
    }
  }

  // 초기/컨텐츠 스왑 시 활성 칩(기본 "오늘")의 필터를 적용 — "오늘 시공" 라벨을 정직하게
  // 반영(로드 시 전 날짜 노출 방지)하고 건수/빈상태를 서버 렌더 직후 즉시 동기화한다.
  function initRangeFilter() {
    var root = document.querySelector(".foms-construction-workmode");
    if (!root) return;
    var active =
      root.querySelector(".foms-cwork-chip.is-active[data-cwork-range]") ||
      root.querySelector(".foms-cwork-chip[data-cwork-range]");
    if (active) applyRangeFilter(active);
  }

  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var chip = t.closest(".foms-cwork-chip[data-cwork-range]");
    if (!chip) return;
    ev.preventDefault();
    applyRangeFilter(chip);
  });

  // ---- 시공 불가 ------------------------------------------------------------

  // 서버와 일치하는 정본 사유 4종(순서 = 프롬프트 번호).
  var FAIL_REASONS = [
    { code: "drawing_error", label: "도면 오류" },
    { code: "measurement_error", label: "실측 오류" },
    { code: "product_defect", label: "제품 불량" },
    { code: "site_issue", label: "현장 문제" },
  ];

  // 사유 번호 프롬프트. 취소/무효 입력이면 null → 조용히 중단.
  function promptFailReason() {
    var lines = ["시공 불가 사유를 선택하세요:"];
    for (var i = 0; i < FAIL_REASONS.length; i++) {
      lines.push(i + 1 + ". " + FAIL_REASONS[i].label);
    }
    var raw = window.prompt(lines.join("\n"));
    if (raw === null) return null;
    var n = parseInt(raw.trim(), 10);
    if (isNaN(n) || n < 1 || n > FAIL_REASONS.length) return null;
    return FAIL_REASONS[n - 1].code;
  }

  // 시공 불가 요청 → 성공 시 새로고침, 실패/오류 시 alert.
  function submitFail(id) {
    if (!id) return;
    var reason = promptFailReason();
    if (!reason) return; // 취소 / 무효 번호 → 조용히 중단
    var detailRaw = window.prompt("상세 사유(선택)를 입력하세요:");
    var detail = detailRaw === null ? "" : detailRaw.trim();
    try {
      fetch("/api/orders/" + encodeURIComponent(id) + "/construction/fail", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason, detail: detail }),
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
            window.alert(
              (data && (data.error || data.message)) || "시공 불가 처리 실패"
            );
          }
        })
        .catch(function (err) {
          console.error("[foms-cwork] 시공 불가 처리 실패:", err);
          window.alert("시공 불가 처리 중 오류가 발생했습니다.");
        });
    } catch (e) {
      console.error("[foms-cwork] 시공 불가 요청 실패:", e);
      window.alert("시공 불가 처리 중 오류가 발생했습니다.");
    }
  }

  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var btn = t.closest("[data-cwork-fail][data-order-id]");
    if (!btn) return;
    ev.preventDefault();
    submitFail(btn.getAttribute("data-order-id"));
  });

  // ---- 대형 스테이지 + 시트 전환 (목업 07 중앙 대형 뷰어) --------------------
  // 새 뷰어를 만들지 않는다. 숨긴 갤러리 소스(.foms-cwork-drawings)를 재사용한다:
  //   · 스테이지 탭  → 활성 시트 idx 의 갤러리 이미지를 프로그램 클릭 → erp-attachment-
  //     preview-open.js → GlobalImageViewer(핀치줌/더블탭/스와이프). (display:none 요소도
  //     .click() 은 바인딩된 핸들러를 실행한다.)
  //   · 시트 칩     → 스테이지 이미지를 인플레이스 교체 + 활성 idx 갱신(풀스크린 아님).

  // 패널 내부의 숨긴 갤러리 이미지(시트 원본) 목록.
  function panelSheetImgs(panel) {
    return panel
      ? panel.querySelectorAll(
          ".foms-cwork-drawings [data-foms-erp-attachment-view-url]"
        )
      : [];
  }

  // 스테이지 → 활성 idx 로 뷰어 오픈(기존 갤러리 바인딩에 위임).
  function openStageViewer(stage) {
    var panel = stage.closest(".foms-cwork-viewer__panel");
    if (!panel) return;
    var imgs = panelSheetImgs(panel);
    if (!imgs.length) return;
    var idx = parseInt(stage.getAttribute("data-cwork-active-idx") || "0", 10);
    if (isNaN(idx) || idx < 0 || idx >= imgs.length) idx = 0;
    imgs[idx].click();
  }

  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var stage = t.closest("[data-cwork-stage-img]");
    if (!stage) return;
    ev.preventDefault();
    openStageViewer(stage);
  });

  // 스테이지 키보드 접근성(Enter/Space) — role=button 이미지.
  document.addEventListener("keydown", function (ev) {
    if (!cohortActive()) return;
    if (ev.key !== "Enter" && ev.key !== " ") return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var stage = t.closest("[data-cwork-stage-img]");
    if (!stage) return;
    ev.preventDefault();
    openStageViewer(stage);
  });

  // 시트 칩 → 스테이지 이미지 인플레이스 교체 + 활성 idx 갱신.
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var chip = t.closest(".foms-cwork-sheet-chip[data-cwork-sheet-idx]");
    if (!chip) return;
    ev.preventDefault();
    var panel = chip.closest(".foms-cwork-viewer__panel");
    if (!panel) return;
    // 같은 패널 안에서만 활성 칩 전환(클릭 칩만 is-active, 형제 칩은 해제).
    var siblings = panel.querySelectorAll(".foms-cwork-sheet-chip");
    for (var i = 0; i < siblings.length; i++) {
      siblings[i].classList.toggle("is-active", siblings[i] === chip);
    }
    var idx = parseInt(chip.getAttribute("data-cwork-sheet-idx"), 10);
    var imgs = panelSheetImgs(panel);
    if (isNaN(idx) || idx < 0 || idx >= imgs.length) return;
    var stage = panel.querySelector("[data-cwork-stage-img]");
    if (!stage) return;
    var src =
      imgs[idx].getAttribute("src") ||
      imgs[idx].getAttribute("data-foms-erp-attachment-view-url") ||
      "";
    if (src) stage.setAttribute("src", src);
    stage.setAttribute("data-cwork-active-idx", String(idx));
    stage.setAttribute(
      "alt",
      imgs[idx].getAttribute("data-foms-erp-attachment-label") || "도면"
    );
  });

  // ---- 도면 첨부 프리뷰 갤러리 마운트 --------------------------------------
  // idempotent 마운트 헬퍼가 있으면 호출한다. DOM 준비 + 컨텐츠 스왑 양쪽에서
  // 재실행해 갤러리 바인딩을 보장한다(코호트 게이트와 무관하게 항상 마운트).
  function mountGalleries() {
    if (window.fomsMountErpAttachmentPreviewGalleries) {
      window.fomsMountErpAttachmentPreviewGalleries(document);
    }
  }
  // 갤러리 마운트 + 기본 범위 필터 적용을 DOM 준비/스왑 양쪽에서 재실행.
  function onReadyOrSwap() {
    mountGalleries();
    initRangeFilter();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReadyOrSwap);
  } else {
    onReadyOrSwap();
  }
  document.addEventListener("foms:main-content-swapped", onReadyOrSwap);
})();
