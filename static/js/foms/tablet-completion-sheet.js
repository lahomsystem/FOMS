/**
 * FOMS 태블릿 시공 완료 정산 시트 — W17 (T2 / 목업 v8 P9).
 *
 * 로드: 완료 그리드 파샬(tablet_completion_grid_body.html) 끝의 <script defer>로 전역
 *   로드(perf 가드 G1 — defer 필수). 완료 대시보드 코호트에서만 파샬이 렌더되므로 사실상
 *   완료 페이지에서만 활성.
 *
 * 역할: 완료 정산 상세는 tablet-side-sheet.js 가 행의 data-foms-sheet-url 을 읽어 공용
 *   사이드 시트(.foms-tablet-sheet__body)에 fragment(tablet_completion_sheet.html)로 로드
 *   한다(그 배선은 side-sheet 소유 — 여기서 손대지 않음). 이 모듈은 시트 안의 정산 발행
 *   폼(form[data-foms-settlement-issue]) submit 만 document 위임으로 처리한다:
 *     POST /api/orders/<id>/settlement/issue  (기존 정산 API 재사용, 신규 엔드포인트 없음)
 *   성공 시 (a) 완료 그리드의 해당 행에 is-settled dim + 정산 배지를 "완료"로 갱신,
 *   (b) 시트 폼/푸터를 성공 노트로 교체(발행은 terminal — 재활성화 없음).
 *   현금영수증 발행 버튼(--receipt)은 API 미배선이라 여기서 처리하지 않는다(disabled).
 *
 * idempotent: window.__FOMS_COMPLETION_SHEET_BOUND 싱글턴 가드(perf 가드 G4 — fragment
 *   재실행/재로드 시 전역 listener 중복 바인딩 방지). document 위임이라 시트가 나중에
 *   <body>에 붙어도 재바인딩 불필요.
 */
(function () {
  "use strict";

  if (window.__FOMS_COMPLETION_SHEET_BOUND) return;
  window.__FOMS_COMPLETION_SHEET_BOUND = true;

  var ISSUE_FORM_SELECTOR = "form[data-foms-settlement-issue]";

  function focusField(el) {
    if (el && typeof el.focus === "function") el.focus();
  }

  // 완료 그리드의 대상 행(order id 는 숫자 → 이스케이프 불필요이나 방어적으로 CSS.escape).
  function findGridRow(orderId) {
    if (orderId == null || orderId === "") return null;
    var idSel =
      window.CSS && typeof CSS.escape === "function"
        ? CSS.escape(orderId)
        : String(orderId);
    return document.querySelector(
      '.foms-completion-grid tbody tr[data-order-id="' + idSel + '"]'
    );
  }

  // 발행 결과 노드(.foms-completion-sheet__issue-result) — 시트 안에 없으면 폼 뒤에 생성.
  function resultNode(form) {
    var sheet = form.closest(".foms-completion-sheet") || form.parentNode;
    var node = sheet
      ? sheet.querySelector(".foms-completion-sheet__issue-result")
      : null;
    if (!node && form.parentNode) {
      node = document.createElement("div");
      node.className = "foms-completion-sheet__issue-result";
      node.setAttribute("role", "status");
      node.hidden = true;
      form.parentNode.insertBefore(node, form.nextSibling);
    }
    return node;
  }

  function showResult(form, message, ok) {
    var node = resultNode(form);
    if (!node) return;
    node.textContent = message;
    node.classList.remove("is-success", "is-error");
    node.classList.add(ok ? "is-success" : "is-error");
    node.hidden = false;
  }

  function clearResult(form) {
    var sheet = form.closest(".foms-completion-sheet");
    var node = sheet
      ? sheet.querySelector(".foms-completion-sheet__issue-result")
      : null;
    if (node) {
      node.hidden = true;
      node.textContent = "";
      node.classList.remove("is-success", "is-error");
    }
  }

  function setPending(btn, pending) {
    if (!btn) return;
    btn.disabled = !!pending;
    if (pending) {
      if (!btn.hasAttribute("data-foms-label")) {
        btn.setAttribute("data-foms-label", btn.textContent || "");
      }
      btn.textContent = "발행 중…";
    } else {
      var label = btn.getAttribute("data-foms-label");
      if (label !== null) btn.textContent = label;
    }
  }

  // 성공 시: 발행은 terminal → 폼/푸터 숨기고 성공 노트 표시.
  function hideFormAndFooter(form) {
    form.hidden = true;
    var sheet = form.closest(".foms-completion-sheet");
    if (sheet) {
      var foot = sheet.querySelector(".foms-completion-sheet__m-foot");
      if (foot && !form.contains(foot)) foot.hidden = true;
    }
  }

  function markRowSettled(orderId) {
    var row = findGridRow(orderId);
    if (!row) return;
    row.classList.add("is-settled");
    var badge = row.querySelector(".foms-completion-grid__badge");
    if (badge) {
      badge.textContent = "완료";
      badge.classList.remove("is-pending");
      badge.classList.add("is-settled");
    }
  }

  function handleIssue(form) {
    var orderId = form.getAttribute("data-order-id");
    var deptEl = form.querySelector("select[name='department']");
    var amountEl = form.querySelector("input[name='amount']");
    var reasonEl = form.querySelector("textarea[name='reason']");
    var submitBtn = form.querySelector(
      "button[type='submit'], .foms-completion-sheet__btn--issue"
    );

    var department = deptEl ? deptEl.value.trim() : "";
    var amountRaw = amountEl ? amountEl.value.trim() : "";
    var reason = reasonEl ? reasonEl.value.trim() : "";

    // 기본 클라이언트 검증(누락 필드 focus + 가시 메시지).
    if (!department) {
      focusField(deptEl);
      showResult(form, "귀속 대상을 선택하세요.", false);
      return;
    }
    if (!amountRaw) {
      focusField(amountEl);
      showResult(form, "차감 금액을 입력하세요.", false);
      return;
    }
    if (!reason) {
      focusField(reasonEl);
      showResult(form, "사유를 입력하세요.", false);
      return;
    }
    var amount = Number(amountRaw);
    if (!isFinite(amount) || amount <= 0) {
      focusField(amountEl);
      showResult(form, "차감 금액은 0보다 큰 숫자여야 합니다.", false);
      return;
    }

    setPending(submitBtn, true);
    clearResult(form);

    fetch("/api/orders/" + encodeURIComponent(orderId) + "/settlement/issue", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify({
        department: department,
        amount: amount,
        reason: reason,
      }),
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            // 비-JSON 응답도 무음 금지 — 실패로 귀결시켜 아래 else 에서 로그+가시 메시지.
            return { success: false, message: "서버 응답 형식 오류" };
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        if (r.ok && r.data && r.data.success) {
          // (a) 그리드 행 dim + 배지 갱신, (b) 시트 성공 노트.
          markRowSettled(orderId);
          hideFormAndFooter(form);
          showResult(form, "정산이 발행되었습니다.", true);
        } else {
          var msg =
            (r.data && (r.data.message || r.data.error)) ||
            "정산 발행에 실패했습니다.";
          setPending(submitBtn, false);
          showResult(form, msg, false);
          console.error("[foms-completion-sheet] 정산 발행 실패:", msg, r.data);
        }
      })
      .catch(function (err) {
        setPending(submitBtn, false);
        showResult(form, "정산 발행 중 오류가 발생했습니다.", false);
        console.error("[foms-completion-sheet] 정산 발행 요청 오류:", err);
      });
  }

  // ---- 현금영수증 발행(발행 버튼) ------------------------------------------
  // 시트 현금영수증 섹션의 발행 버튼(button[data-foms-cash-receipt-issue]) 클릭 →
  // POST /api/orders/<id>/cash-receipt/issue (신규 완료 API). 발행은 terminal —
  // 성공 시 (a) 시트 배지를 "발행됨"으로 교체+버튼 제거, (b) 완료 그리드 해당 행의
  // 현금영수증 셀을 "발행됨" 칩으로 갱신한다. 응답 = {success, data:{cash_receipt}} / {success,error}.
  var CASH_ISSUE_BTN = "[data-foms-cash-receipt-issue]";

  function cashResultNode(scope) {
    return scope ? scope.querySelector("[data-foms-cash-receipt-result]") : null;
  }

  function showCashResult(scope, message, ok) {
    var node = cashResultNode(scope);
    if (!node) return;
    node.textContent = message;
    node.classList.remove("is-success", "is-error");
    node.classList.add(ok ? "is-success" : "is-error");
    node.hidden = false;
  }

  function markGridReceiptIssued(orderId) {
    var row = findGridRow(orderId);
    if (!row) return;
    var cell = row.querySelector(".foms-completion-grid__receipt-cell");
    if (!cell) return;
    cell.innerHTML =
      '<span class="foms-completion-grid__receipt-chip is-issued">발행됨</span>';
  }

  function handleCashIssue(btn) {
    if (btn.disabled) return;
    var orderId = btn.getAttribute("data-order-id");
    if (!orderId) return;
    var scope = btn.closest("[data-foms-cash-receipt]") || btn.parentNode;

    btn.disabled = true;
    var origLabel = btn.textContent;
    btn.textContent = "발행 중…";

    fetch("/api/orders/" + encodeURIComponent(orderId) + "/cash-receipt/issue", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: "{}",
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return { success: false, error: "서버 응답 형식 오류" };
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        if (r.ok && r.data && r.data.success) {
          // (a) 시트 배지 갱신 + 버튼 제거, (b) 그리드 셀 갱신.
          var badge = scope ? scope.querySelector("[data-foms-cash-receipt-badge]") : null;
          var line = scope ? scope.querySelector(".foms-completion-sheet__cash-line") : null;
          if (badge) {
            badge.textContent = "발행됨";
          } else if (line) {
            var span = document.createElement("span");
            span.className = "foms-completion-sheet__cash-issued";
            span.setAttribute("data-foms-cash-receipt-badge", "");
            span.textContent = "발행됨";
            // 기존 요청/없음 표시를 교체.
            var old = line.querySelector(
              ".foms-completion-sheet__cash-req, .foms-completion-sheet__cash-none"
            );
            if (old && old.parentNode) old.parentNode.replaceChild(span, old);
            else line.appendChild(span);
          }
          if (btn.parentNode) btn.parentNode.removeChild(btn);
          markGridReceiptIssued(orderId);
          showCashResult(scope, "현금영수증이 발행되었습니다.", true);
        } else {
          var msg = (r.data && (r.data.error || r.data.message)) || "현금영수증 발행에 실패했습니다.";
          btn.disabled = false;
          btn.textContent = origLabel;
          showCashResult(scope, msg, false);
          console.error("[foms-completion-sheet] 현금영수증 발행 실패:", msg, r.data);
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = origLabel;
        showCashResult(scope, "현금영수증 발행 중 오류가 발생했습니다.", false);
        console.error("[foms-completion-sheet] 현금영수증 발행 요청 오류:", err);
      });
  }

  // 단일 document 위임(bind once). 시트는 tablet-side-sheet.js 가 <body>에 나중에 붙이므로
  // capture 없이 bubble 단계 위임으로 충분(form 이 submit 을 버블링).
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form || typeof form.matches !== "function") return;
    if (!form.matches(ISSUE_FORM_SELECTOR)) return;
    ev.preventDefault();
    handleIssue(form);
  });

  document.addEventListener("click", function (ev) {
    if (!ev.target || !ev.target.closest) return;
    var btn = ev.target.closest(CASH_ISSUE_BTN);
    if (!btn) return;
    ev.preventDefault();
    handleCashIssue(btn);
  });
})();
