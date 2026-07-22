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

  // 생산 보류 토글 — 표시 전용 플래그(워크플로 전이 없음). 버튼의 data-hold-active 로
  // 현재 상태를 읽어 반대로 토글한다. 활성화 시 사유를 prompt 로 받는다(취소 시 중단).
  // 성공 시 시트를 닫고 새로고침해 카드/시트 배지를 재조회한다. 에러 키 = error(생산 API).
  function productionHold(orderId, btn) {
    if (!orderId) return;
    var isActive = btn && btn.getAttribute("data-hold-active") === "1";
    var nextActive = !isActive;
    var reason = "";
    if (nextActive) {
      reason = window.prompt("보류 사유를 입력하세요. (선택)", "") || "";
      reason = reason.trim();
    }
    fetch("/api/orders/" + encodeURIComponent(orderId) + "/production/hold", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: nextActive, reason: reason }),
    })
      .then(function (res) {
        return res.json().catch(function () {
          return { success: false, error: "서버 응답 형식 오류" };
        });
      })
      .then(function (data) {
        if (data && data.success) {
          closeSheet();
          window.location.reload();
        } else {
          window.alert("오류: " + ((data && (data.error || data.message)) || "처리 실패"));
        }
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 생산 보류 토글 실패:", err);
        window.alert("처리 중 오류가 발생했습니다.");
      });
  }

  // 변경 확인(ack) — 묘비 카드/시트의 [변경 확인] 버튼. 생산 진입 후 감지된 변경/취소를
  // 팀 확인으로 해제한다. 성공 시 새로고침으로 read-model(카드 스트립/묘비/카운트)을 재조회.
  // 삭제 주문(묘비)에도 허용되는 전용 엔드포인트. 에러 키 = error(생산 API 패턴).
  function changeAck(orderId) {
    if (!orderId) return;
    fetch("/api/orders/" + encodeURIComponent(orderId) + "/production/change-ack", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then(function (res) {
        return res.json().catch(function () {
          return { success: false, error: "서버 응답 형식 오류" };
        });
      })
      .then(function (data) {
        if (data && data.success) {
          window.location.reload();
        } else {
          window.alert("오류: " + ((data && (data.error || data.message)) || "처리 실패"));
        }
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 변경 확인 실패:", err);
        window.alert("처리 중 오류가 발생했습니다.");
      });
  }

  // ---- 변경 브리핑 모달 (R4) -------------------------------------------------
  // 대시보드 진입 시 changed_count>0 이면 서버가 #foms-prod-change-modal 을 렌더한다. 각 행의
  // [확인] 버튼이 기존 change-ack 를 단건 호출하고, 성공 시 리로드 없이 해당 행·카드 강조·카운트를
  // in-place 정리한다. 닫기/Esc/딤 = 이번 화면에서만 닫힘(영구 억제 없음 — 다음 로드/스왑 시
  // 미확인 변경 있으면 무조건 재표시).

  // 단건 ack 요청 — 성공 여부 bool 로만 resolve(reject 없음).
  function ackOrderRequest(orderId) {
    return fetch("/api/orders/" + encodeURIComponent(orderId) + "/production/change-ack", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then(function (res) {
        return res.json().catch(function () {
          return { success: false };
        });
      })
      .then(function (data) {
        return !!(data && data.success);
      })
      .catch(function () {
        return false;
      });
  }

  function openChangeModal(modal) {
    if (!modal || modal.classList.contains("is-open")) return; // 중복 오픈(스왑) 방지.
    modal.removeAttribute("hidden");
    modal.classList.add("is-open");
    var firstBtn = modal.querySelector("[data-prod-change-row-ack]") ||
      modal.querySelector("[data-prod-change-close]");
    if (firstBtn) {
      try {
        firstBtn.focus();
      } catch (e) {
        /* focus 실패 무해 */
      }
    }
  }

  // 닫기(ack 없이) — 이번 화면에서만. 영구 억제 없음(fingerprint 제거): 다음 로드/스왑 시 재표시.
  function closeChangeModal(modal) {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("hidden", "");
  }

  // 자동 표시 — 코호트+모달 존재면 무조건 연다(미확인 변경 잔존 = changed_count>0 = 서버가 렌더).
  function maybeShowChangeModal() {
    if (!cohortActive()) return;
    openChangeModal(document.getElementById("foms-prod-change-modal"));
  }

  // "변경 N" 필터 칩 카운트 = 변경 카드(data-changed=1) + 묘비 카드 수로 재계산. 0 이면 has-changes 해제.
  function refreshChangedCount() {
    var n =
      document.querySelectorAll('.foms-kanban-card[data-changed="1"]').length +
      document.querySelectorAll(".foms-kanban-card--tomb").length;
    var btn = document.querySelector("button[data-tablet-prod-changed]");
    if (btn) {
      var span = btn.querySelector("span");
      if (span) span.textContent = "변경 " + n;
      if (n > 0) btn.classList.add("has-changes");
      else btn.classList.remove("has-changes");
    }
    return n;
  }

  // 뱃지열에 조용한 "변경됨" 칩 주입(중복 가드). 확인 후 상설 표시(이력 보유 신호).
  function injectQuietBadge(card) {
    var cluster = card.querySelector(".foms-kanban-card__top-right");
    if (!cluster) return;
    if (cluster.querySelector(".foms-kanban-card__changed-quiet")) return; // 중복 주입 방지.
    var badge = document.createElement("span");
    badge.className = "foms-kanban-card__changed-quiet";
    badge.setAttribute("title", "변경 이력 있음(확인됨)");
    badge.textContent = "변경됨";
    cluster.appendChild(badge);
  }

  // 보드 in-place 정리: 카드 변경이면 시끄러운 상태(스트립·is-changed·펄스)를 조용한 상태로
  // 전환(data-changed=0·data-change-history=1·조용한 칩 주입). 묘비면 묘비 카드 제거(현행 유지).
  // 묘비 카드는 article 에 data-order-id 가 없고(시트 오픈 방지) ack 버튼에만 있으므로 그 경유로 찾는다.
  function cleanupBoardForOrder(orderId, isTomb) {
    if (isTomb) {
      var tombBtn = document.querySelector(
        '.foms-kanban-card--tomb .foms-kanban-ack-btn[data-order-id="' + orderId + '"]'
      );
      var tombCard = tombBtn ? tombBtn.closest(".foms-kanban-card--tomb") : null;
      if (tombCard) tombCard.remove();
      return;
    }
    var card = document.querySelector(
      '.foms-kanban-card[data-order-id="' + orderId + '"]'
    );
    if (!card) return;
    var strip = card.querySelector(".foms-kanban-card__alert");
    if (strip) strip.remove();
    card.classList.remove("is-changed"); // 3px 보더·펄스 제거.
    card.setAttribute("data-changed", "0");
    card.setAttribute("data-change-history", "1"); // 이력 보유로 전환.
    injectQuietBadge(card);
  }

  function showRowError(row) {
    if (!row) return;
    var err = row.querySelector(".foms-prod-change-modal__row-error");
    if (!err) {
      err = document.createElement("span");
      err.className = "foms-prod-change-modal__row-error";
      var body = row.querySelector(".foms-prod-change-modal__item-body") || row;
      body.appendChild(err);
    }
    err.textContent = "확인 실패 — 다시 시도";
  }

  // 행별 [확인] — 단건 ack. 성공: 리로드 없이 (a)모달 행 제거 (b)카드 강조/묘비 제거 (c)카운트 감소
  // (d)마지막 행이면 모달 닫기. 실패: 행에 오류 표시+버튼 재활성. 연타 방지(진행 중 disabled).
  function ackModalRow(btn) {
    if (!btn || btn.disabled) return;
    var orderId = btn.getAttribute("data-order-id");
    if (!orderId) return;
    var row = btn.closest(".foms-prod-change-modal__item");
    var isTomb = !!(row && row.classList.contains("foms-prod-change-modal__item--tomb"));
    btn.disabled = true;
    ackOrderRequest(orderId).then(function (ok) {
      if (!ok) {
        btn.disabled = false;
        showRowError(row);
        return;
      }
      cleanupBoardForOrder(orderId, isTomb);
      if (row) row.remove();
      refreshChangedCount();
      applyProdFilter(); // 변경만/KPI 필터 활성 시 보드 정합 유지.
      var modal = document.getElementById("foms-prod-change-modal");
      if (modal) {
        var list = modal.querySelector(".foms-prod-change-modal__list");
        if (list && !list.querySelector(".foms-prod-change-modal__item")) {
          closeChangeModal(modal);
        }
      }
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
    var changedEl = document.querySelector("button[data-tablet-prod-changed]");
    var changedOnly = !!(changedEl && changedEl.classList.contains("is-on"));
    // KPI 탭(상호 배타, 하나만 is-on): line=제작중 열(열 레벨) / load=dday 0 / delayed=dday<0(카드 레벨).
    var kpiEl = document.querySelector("[data-tablet-prod-kpi].is-on");
    var kpi = kpiEl ? kpiEl.getAttribute("data-tablet-prod-kpi") : "";

    var cols = document.querySelectorAll(".foms-kanban-col[data-kanban-bucket]");
    Array.prototype.forEach.call(cols, function (col) {
      var bucket = col.getAttribute("data-kanban-bucket");
      // 상태 필터: 미선택('')이면 전부 표시, 선택 시 해당 버킷 열만 표시.
      // KPI line = 제작중 열만(status predicate 재사용, 교집합).
      var colVisible =
        (status === "" || bucket === status) &&
        (kpi !== "line" || bucket === "제작중");
      col.style.display = colVisible ? "" : "none";
      if (!colVisible) return; // 숨긴 열의 카드는 재평가 불필요(열이 다시 보일 때 재계산).

      var cards = col.querySelectorAll(".foms-kanban-card");
      Array.prototype.forEach.call(cards, function (card) {
        // 묘비(취소) 카드는 모든 클라 필터에서 항상 표시(취소 알림은 필터로 숨기지 않는다).
        if (card.getAttribute("data-tomb") === "1") {
          card.style.display = "";
          return;
        }
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

        // 변경 모아보기(반장 리뷰): 토글 ON 이면 미확인(data-changed=1) 또는 확인된 이력
        // (data-change-history=1) 카드 표시.
        var changedOK =
          !changedOnly ||
          card.getAttribute("data-changed") === "1" ||
          card.getAttribute("data-change-history") === "1";

        // KPI 카드 레벨 조건: load=D-DAY(dday 0), delayed=지연(dday<0). line 은 열 레벨에서 처리.
        var kpiOK = true;
        if (kpi === "load" || kpi === "delayed") {
          var dday = card.getAttribute("data-dday");
          if (dday === "" || dday === null) {
            kpiOK = false; // 무일정 카드는 시공일 기반 KPI 필터에서 제외.
          } else if (kpi === "load") {
            kpiOK = dday === "0";
          } else {
            kpiOK = parseInt(dday, 10) < 0;
          }
        }

        card.style.display = searchOK && factoryOK && changedOK && kpiOK ? "" : "none";
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
    var changedEl = document.querySelector("button[data-tablet-prod-changed]");
    if (changedEl) {
      changedEl.classList.remove("is-on");
      changedEl.setAttribute("aria-pressed", "false");
    }
    clearKpiTabs();
    applyProdFilter();
  }

  // KPI 탭 전체 해제(상호 배타 헬퍼 — 토글 시·리셋 시 공용).
  function clearKpiTabs() {
    var els = document.querySelectorAll("[data-tablet-prod-kpi]");
    Array.prototype.forEach.call(els, function (el) {
      el.classList.remove("is-on");
      el.setAttribute("aria-pressed", "false");
    });
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

    // 변경 모아보기 토글 — is-on 클래스/aria-pressed 토글 후 재필터.
    var changedBtn = target.closest("button[data-tablet-prod-changed]");
    if (changedBtn) {
      ev.preventDefault();
      var on = changedBtn.classList.toggle("is-on");
      changedBtn.setAttribute("aria-pressed", on ? "true" : "false");
      applyProdFilter();
      return;
    }

    // 변경 확인(ack) 버튼 — 묘비 카드 + 시트 공용(data-kanban-action="change-ack").
    var ackBtn = target.closest("[data-kanban-action='change-ack']");
    if (ackBtn) {
      ev.preventDefault();
      changeAck(ackBtn.getAttribute("data-order-id"));
      return;
    }

    // 변경 브리핑 모달: 행별 [확인] / [닫기] / 딤 클릭.
    var rowAckBtn = target.closest("[data-prod-change-row-ack]");
    if (rowAckBtn) {
      ev.preventDefault();
      ackModalRow(rowAckBtn);
      return;
    }
    var closeModalBtn = target.closest("[data-prod-change-close]");
    if (closeModalBtn) {
      ev.preventDefault();
      closeChangeModal(document.getElementById("foms-prod-change-modal"));
      return;
    }
    // 딤(오버레이) 직접 클릭만 닫기(다이얼로그 내부 클릭 제외 = target === 딤).
    var dim = target.closest("[data-prod-change-dim]");
    if (dim && target === dim) {
      ev.preventDefault();
      closeChangeModal(dim);
      return;
    }

    // KPI 타일 탭 필터 — 상호 배타(하나만 is-on), 재탭=해제.
    var kpiTile = target.closest("[data-tablet-prod-kpi]");
    if (kpiTile) {
      ev.preventDefault();
      var wasOn = kpiTile.classList.contains("is-on");
      clearKpiTabs();
      if (!wasOn) {
        kpiTile.classList.add("is-on");
        kpiTile.setAttribute("aria-pressed", "true");
      }
      applyProdFilter();
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
    if (action === "production-hold") {
      ev.preventDefault();
      productionHold(orderId, actionBtn);
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

  // KPI 타일(role="button" div)은 네이티브 버튼이 아니라 Enter/Space 활성화를 배선한다(a11y).
  // 위 click 위임이 실제 토글을 처리하므로 여기선 click 합성만.
  document.addEventListener("keydown", function (ev) {
    if (!cohortActive()) return;
    // Esc = 변경 모달 닫기(닫기 버튼과 동일 — 이번 화면만, 다음 로드 시 재표시).
    if (ev.key === "Escape" || ev.key === "Esc") {
      var openModal = document.querySelector("#foms-prod-change-modal.is-open");
      if (openModal) {
        ev.preventDefault();
        closeChangeModal(openModal);
      }
      return;
    }
    if (ev.key !== "Enter" && ev.key !== " " && ev.key !== "Spacebar") return;
    var target = ev.target;
    if (!target || !target.closest) return;
    var kpiTile = target.closest("[data-tablet-prod-kpi]");
    if (kpiTile) {
      ev.preventDefault();
      kpiTile.click();
    }
  });

  // ---- 변경 모달 자동 표시: 초기 로드 + erp-shell fragment 스왑 도착 (R3) ------
  // 정본 패턴(tablet-measurement.js): 싱글턴 IIFE 안에서 스왑 이벤트를 once-only 로 바인딩하고,
  // 핸들러 안에서 매 시점 요소를 새로 조회한다(per-swap 재바인딩 금지). openChangeModal 은
  // is-open 중복 가드가 있어 재진입 안전.
  maybeShowChangeModal();
  document.addEventListener("foms:erp-shell-fragment-swapped", maybeShowChangeModal);
})();
