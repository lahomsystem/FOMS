/**
 * FOMS 도메인 시트 액션 — 생산 쓰기 단추 · 보류 · 사유 창 · [확인했어요](change-ack) · 출고 서랍 저장.
 *
 * 싣는 곳 셋: 생산 첫 화면(home_body.html — [확인했어요] · '내 공정' 판 [보류]) · 전체 화면 작업 시트(sheet.html) ·
 * 출고 태블릿 서랍(shipment-entry.js CHAIN). 옛 생산 칸반 보드(필터 바 · 숫자 타일 · 전체 화면 · 변경 브리핑 창)는
 * 2026-11-27 보드와 함께 지웠다(설계서 2026-11-27-production-legacy-board-removal §6-4). 기존 워크플로 엔드포인트를 쓴다:
 *   - 생산 시작/완료/수정 제작: POST /api/orders/<id>/production/start|complete|rework (에러 키 = message)
 *   - 출고 서랍 저장(시간 · 메모): POST /api/erp/shipment/update/<id> (권한 실패 = 403)
 * 성공 시 시트를 닫고 새로고침으로 read-model 을 재조회한다(낙관 갱신은 비범위 — 간단·근본).
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   AND CSS 마커 --foms-tablet-ui:ready(foms-tablet-side-sheet.css 가 body.erp-mobile-v2-layout
 *   에 정의 — v2 셸 번들 로드 여부에서 파생, 이중 정의 금지). 비-코호트에서 완전 무동작.
 *
 * 위임: 시트 액션은 document 단일 'click' 위임.
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

  // 묻기 — 작업 시트(section.foms-prod-page) · 생산 첫 화면([data-foms-prod-home]) 단추는 앱 창(작업 시트 공정 칸과 같은 창 ·
  // foms-production-sheet-parts.js confirm, 사장님 2026-11-27 "앱 창으로 바꾸기"): 제목 = q.title, 본문 = q.note, [닫기] [q.yes].
  // 그 밖(출고 서랍)과 창 조각이 없는 화면은 지금 기본 창(q.plain — 지금 글 그대로). [닫기] · Esc · 바깥 = 아무 것도 안 함.
  // 앱 창: 떠 있는 창 위 누름 · 저장 중 누름은 버리고, 저장하는 동안 단추를 잠근다(go 가 돌려준 약속이 끝나면 푼다).
  var APP_CONFIRM_SCOPE = "section.foms-prod-page, [data-foms-prod-home]";
  function ask(btn, q, go) {
    var sp = window.FomsSheetParts;
    var box = document.querySelector("[data-foms-sheet-confirm]");
    var app = !!(btn && btn.closest && btn.closest(APP_CONFIRM_SCOPE) && box && sp && typeof sp.confirm === "function");
    if (!app) {
      if (window.confirm(q.plain)) go();
      return;
    }
    if ((btn.disabled && !q.again) || !box.hidden) return; // again = 저장 응답 뒤 다시 묻기(보류 중) — 그때는 단추가 아직 잠겨 있다
    sp.confirm({
      title: q.title,
      body: q.note || "",
      yes: q.yes,
      no: "닫기",
      opener: btn,
      go: function () {
        btn.disabled = true;
        var unlock = function () {
          btn.disabled = false;
        };
        Promise.resolve(go()).then(unlock, unlock);
      },
    });
  }

  // HOLD_ACTIVE 재시도 confirm 문구(사유 있으면 병기).
  function holdConfirmText(hold) {
    var msg = "보류 중인 주문이에요";
    if (hold && hold.reason) msg += " (사유: " + hold.reason + ")";
    return msg + "\n보류를 해제하고 진행할까요?";
  }

  // 같은 글의 앱 창 꼴 — 제목 = 묻는 글, 본문 = "보류 중인 주문이에요 (사유: …)".
  function holdAsk(hold) {
    var note = "보류 중인 주문이에요";
    if (hold && hold.reason) note += " (사유: " + hold.reason + ")";
    return { title: "보류를 해제하고 진행할까요?", note: note, yes: "보류 해제하고 진행", plain: holdConfirmText(hold), again: true };
  }

  // 생산 전이(시작/완료) 공용 — 묻고(ask) 나서 POST. 서버가 stage 전제조건을 강제
  // (409 INVALID_STAGE). 에러는 message 키(error 아님). 성공 시 시트 닫고 새로고침.
  function productionTransition(orderId, path, q, btn) {
    if (!orderId) return;
    ask(btn, q, function () {
      return submitTransition(orderId, path, {}, btn);
    });
  }

  // 전이 POST. 409 HOLD_ACTIVE(보류 중) 면 해제를 묻고(ask) {release_hold:true} 로 1회 재시도.
  function submitTransition(orderId, path, body, btn) {
    return fetch("/api/orders/" + encodeURIComponent(orderId) + path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
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
        if (result.status === 409 && data.code === "HOLD_ACTIVE" && !body.release_hold) {
          ask(btn, holdAsk(data.hold), function () {
            // 재시도 시 기존 body(예: rework reason) 유지 + release_hold 부가.
            var retry = {};
            for (var k in body) if (body.hasOwnProperty(k)) retry[k] = body[k];
            retry.release_hold = true;
            return submitTransition(orderId, path, retry, btn);
          });
          return;
        }
        if (data.success) {
          closeSheet();
          window.location.reload();
          return;
        }
        // 관리자가 업무 게이트(단계 전제·승인)에 막혔으면 사유를 받아 한 번만 다시 보낸다.
        // 보류는 위에서 자기해제 경로로 빠지므로 여기 오지 않는다.
        var ctl = window.FomsAdminOverride;
        if (!ctl || typeof ctl.retry !== "function") {
          window.alert(data.message || "처리하지 못했어요");
          return;
        }
        return ctl
          .retry({
            url: "/api/orders/" + encodeURIComponent(orderId) + path,
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: body || {},
            code: data.code || "",
            message: data.message || data.error || "",
          })
          .then(function (again) {
            if (again && again.ok) {
              closeSheet();
              window.location.reload();
              return;
            }
            var failed = (again && again.data) || data;
            window.alert(failed.message || failed.error || "처리하지 못했어요");
          });
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 생산 전이 실패:", err);
        window.alert("연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.");
      });
  }

  // 생산 시작 — 제작대기(고객컨펌) → 제작중 전이.
  function productionStart(orderId, btn) {
    productionTransition(
      orderId,
      "/production/start",
      { title: "제작을 시작할까요?", yes: "제작 시작", plain: "제작을 시작할까요?" },
      btn
    );
  }

  // 시공일이 둘 이상인 주문만 서버가 작업 시트 뿌리에 한 줄(data-production-split-note)을 실어 준다.
  // 앱 창은 그 한 줄을 본문에, 기본 창은 지금처럼 빈 줄 하나 띄워 붙인다.
  function productionSplitNote(orderId) {
    var src = document.querySelector('[data-production-split-note][data-order-id="' + orderId + '"]');
    return src ? (src.getAttribute("data-production-split-note") || "") : "";
  }

  // 생산 완료 — 제작중 → 제작완료/시공대기 전이(기존 워크플로 엔드포인트 재사용).
  function productionComplete(orderId, btn) {
    var note = productionSplitNote(orderId);
    productionTransition(
      orderId,
      "/production/complete",
      { title: "제작을 완료할까요?", note: note, yes: "제작 완료", plain: "제작을 완료할까요?" + (note ? "\n\n" + note : "") },
      btn
    );
  }

  // 사유 입력 공용 바텀시트(static/js/foms/foms-reason-sheet.js)로 사유를 받아 전이한다.
  // window.prompt 는 쓰지 않는다 — 모바일·태블릿·v3 세 화면이 같은 시트를 쓴다.
  function openReasonSheetAndSubmit(orderId, path, opts, btn) {
    if (!orderId) return;
    if (!window.FomsReasonSheet) {
      window.alert("사유 입력 창을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.");
      return;
    }
    window.FomsReasonSheet.open({
      title: opts.title,
      actionLabel: opts.actionLabel,
      reasons: null,
      detailLabel: opts.detailLabel,
      onSubmit: function (reason, detail) {
        submitTransition(orderId, path, { reason: detail }, btn);
      },
    });
    setReasonCloseText(opts.cancelLabel);
  }

  // 사유 시트 왼쪽 단추 글 — 기본 "취소". 실행 단추에 '취소'가 드는 [제작 시작 취소]만 "닫기"(사장님 2026-11-26 — '취소'가 둘).
  // 공용 시트(foms-reason-sheet.js)는 안 바꾸고, 이 파일이 열 때마다 다시 정한다.
  function setReasonCloseText(text) {
    var btn = document.querySelector("[data-foms-reason-close].foms-btn");
    if (btn) btn.textContent = text || "취소";
  }

  // 수정 제작 — 제작완료 → 제작중 되돌림. 사유는 공용 시트에서 받는다(빈 값 허용).
  // HOLD_ACTIVE 재시도는 submitTransition 이 body(reason)를 유지한 채 처리한다.
  function productionRework(orderId, btn) {
    openReasonSheetAndSubmit(orderId, "/production/rework", {
      title: "수정 제작으로 되돌리기",
      actionLabel: "수정 제작",
      detailLabel: "수정 제작 사유 (선택)",
    }, btn);
  }

  // 제작 취소 — 제작중 → 제작대기 되돌림(시트 전용, 의도적 마찰). 사유는 공용 시트에서 받는다.
  // 후진 전이라 서버 보류 게이트 없음(HOLD_ACTIVE 분기 무발동, 무해).
  function productionCancel(orderId, btn) {
    openReasonSheetAndSubmit(orderId, "/production/cancel", {
      title: "제작을 취소하고 제작 대기로 되돌릴까요?",
      actionLabel: "제작 시작 취소",
      cancelLabel: "닫기",
      detailLabel: "제작 취소 사유 (선택)",
    }, btn);
  }

  // 완료 취소 — 제작완료 → 제작중 되돌림(시트 전용, 의도적 마찰). 묻기만(사유 없음).
  // 재제작 완료였으면 서버가 rework 를 다시 활성으로 복원한다. 후진 전이라 보류 게이트 없음.
  function productionUncomplete(orderId, btn) {
    if (!orderId) return;
    var text = "완료를 취소하고 제작 중으로 되돌릴까요?";
    ask(btn, { title: text, yes: "완료 취소", plain: text }, function () {
      return submitTransition(orderId, "/production/uncomplete", {}, btn);
    });
  }

  // 생산 보류 토글 — canonical HOLD_ORDER/RELEASE_HOLD 전이(STATE-OVERLAY-01). 버튼의
  // data-hold-active 로 현재 상태를 읽어 반대로 토글하며, 서버는 workflow.hold 축을 전이하고
  // production.hold 배지를 같은 tx 로 미러한다(응답 {success, data:{hold}} 형태 불변).
  // 활성화 시 사유를 prompt 로 받는다(취소 시 중단). 해제 경로는 오조작 방지 confirm 을 거치며,
  // 사유는 버튼 인접 DOM 이 아니라 서버 렌더 data-hold-reason 에서 읽어 병기한다. 성공 시 시트를
  // 닫고 새로고침해 카드/시트 배지를 재조회한다. 에러 키 = error/message(전이 409 는 message).
  function productionHold(orderId, btn) {
    if (!orderId) return;
    var isActive = btn && btn.getAttribute("data-hold-active") === "1";
    if (!isActive) {
      // 보류 사유도 공용 시트에서 받는다(window.prompt 금지). 시트는 비동기라 제출
      // 콜백에서 같은 요청을 이어 보낸다.
      if (!window.FomsReasonSheet) {
        window.alert("사유 입력 창을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.");
        return;
      }
      window.FomsReasonSheet.open({
        title: "생산 보류",
        actionLabel: "보류",
        reasons: null,
        detailLabel: "보류 사유 (선택)",
        onSubmit: function (_reason, detail) {
          submitProductionHold(orderId, true, detail);
        },
      });
      setReasonCloseText();
      return;
    }
    // 해제 묻기 — 서버 렌더 사유(data-hold-reason)를 병기(있을 때만 — 앱 창은 본문 줄).
    var heldReason = btn ? (btn.getAttribute("data-hold-reason") || "").trim() : "";
    var why = heldReason ? "(사유: " + heldReason + ")" : "";
    var releaseMsg = "보류를 해제할까요?";
    if (heldReason) releaseMsg += " " + why;
    ask(btn, { title: "보류를 해제할까요?", note: why, yes: "보류 해제", plain: releaseMsg }, function () {
      return submitProductionHold(orderId, false, "");
    });
  }

  // 보류 토글 요청 본체. 성공 시 시트를 닫고 새로고침해 카드/시트 배지를 재조회한다.
  // 에러 키 = error/message(전이 409 는 message).
  function submitProductionHold(orderId, active, reason) {
    return fetch("/api/orders/" + encodeURIComponent(orderId) + "/production/hold", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: active, reason: (reason || "").trim() }),
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
          window.alert((data && (data.error || data.message)) || "처리하지 못했어요");
        }
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 생산 보류 토글 실패:", err);
        window.alert("연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.");
      });
  }

  // [바뀐 것] 탭(home_changes.html) 한 줄 지우기 — 줄 제거, 탭 · 머리 숫자 1 감소(0 이면 is-hot 빼고 is-zero),
  // 미확인 줄이 다 비면 서버가 그리는 빈 글을 같은 자리에 둔다. 처리했으면 true.
  function removeInboxRow(row) {
    if (!row || !row.parentNode) return false;
    var box = row.closest(".fph-inbox");
    if (!box) return false;
    row.parentNode.removeChild(row);
    var headRow = box.querySelector(".fph-inbox__h");
    var head = headRow ? headRow.querySelector("b") : null;
    var navTab = document.querySelector(".foms-prod-home__navtab[aria-current='page']");
    var tab = navTab ? navTab.querySelector("small") : null;
    var left = box.querySelectorAll("[data-foms-home-inbox]").length;
    [head, tab].forEach(function (el) {
      if (!el) return;
      el.textContent = String(left);
      if (el === head) el.classList.toggle("is-zero", left === 0);
      else el.classList.toggle("is-hot", left > 0);
    });
    if (!left && !box.querySelector(".foms-prod-home__empty")) {
      var empty = document.createElement("p");
      empty.className = "foms-prod-home__empty";
      empty.textContent = "새로 바뀐 것이 없어요.";
      box.insertBefore(empty, box.querySelector("[data-foms-home-done], .fph-inbox__more"));
    }
    return true;
  }

  // 변경 확인(ack) — [바뀐 것] 탭 줄 · 작업 시트의 [확인했어요] 버튼. 생산 진입 후 감지된 변경/취소를
  // 팀 확인으로 해제한다. 성공 시 새로고침으로 read-model(줄 · 묘비 · 숫자)을 재조회.
  // 삭제 주문(묘비)에도 허용되는 전용 엔드포인트. 에러 키 = error(생산 API 패턴).
  function changeAck(orderId, inboxRow) {
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
          // [바뀐 것] 탭 줄만 그 줄을 지우고 숫자를 줄인다(보던 자리 유지, 사장님 결정 2026-11-26).
          // 그 밖 화면(작업 시트 · 날짜 탭 줄)은 지금처럼 다시 읽는다.
          if (!removeInboxRow(inboxRow)) window.location.reload();
        } else {
          window.alert((data && (data.error || data.message)) || "처리하지 못했어요");
        }
      })
      .catch(function (err) {
        console.error("[foms-domain-sheets] 변경 확인 실패:", err);
        window.alert("연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.");
      });
  }

  // 출고 서랍 저장 — 시공시간 · 현장 메모만 기존 출고 update 엔드포인트로 보낸다.
  // construction_workers 는 보내지 않는다: 시공자는 표의 이름판이 바로 저장하므로, 여기서 보내면
  // 이름판에서 방금 고친 값을 옛 값/빈 값으로 덮는다(API 는 없는 키를 그대로 둔다).
  // 메모는 바뀌었을 때만 보낸다 — 여러 줄 · 색 메모를 한 줄로 합쳐 덮지 않게(defaultValue = 처음 값).
  function shipmentSave(orderId) {
    if (!orderId) return;
    var scope = document.querySelector(".foms-tablet-sheet__body") || document;
    var payload = {};
    var timeInput = scope.querySelector("input[data-tablet-assign-time]");
    if (timeInput) payload.construction_time = timeInput.value.trim();
    var memoInput = scope.querySelector("input[data-tablet-assign-memo]");
    var memo = memoInput ? memoInput.value.trim() : "";
    if (memoInput && memo !== memoInput.defaultValue.trim()) {
      payload.site_extra = memo ? [{ text: memo, color: "#334155" }] : [];
    }

    fetch("/api/erp/shipment/update/" + encodeURIComponent(orderId), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
        console.error("[foms-domain-sheets] 출고 서랍 저장 실패:", err);
        window.alert("연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.");
      });
  }

  // ---- 단일 document 'click' 위임 --------------------------------------------
  document.addEventListener("click", function (ev) {
    var target = ev.target;
    if (!target || !target.closest) return;
    // 생산팀 첫 화면·전체 화면 작업 시트(설계서 §12)는 기기 무관 — 코호트 게이트를 타지 않는다.
    if (!cohortActive() && !target.closest("[data-foms-prod-sheet-page], [data-foms-prod-home]")) return;

    // 변경 확인(ack) 버튼 — [바뀐 것] 탭 줄 + 작업 시트 공용(data-kanban-action="change-ack" — 이름은 옛 칸반에서 온 계약).
    var ackBtn = target.closest("[data-kanban-action='change-ack']");
    if (ackBtn) {
      ev.preventDefault();
      changeAck(ackBtn.getAttribute("data-order-id"), ackBtn.closest("[data-foms-home-inbox]"));
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
    if (action === "production-start") {
      ev.preventDefault();
      productionStart(orderId, actionBtn);
      return;
    }
    if (action === "production-complete") {
      ev.preventDefault();
      productionComplete(orderId, actionBtn);
      return;
    }
    if (action === "production-rework") {
      ev.preventDefault();
      productionRework(orderId, actionBtn);
      return;
    }
    if (action === "production-cancel") {
      ev.preventDefault();
      productionCancel(orderId, actionBtn);
      return;
    }
    if (action === "production-uncomplete") {
      ev.preventDefault();
      productionUncomplete(orderId, actionBtn);
      return;
    }
    if (action === "production-hold") {
      ev.preventDefault();
      productionHold(orderId, actionBtn);
      return;
    }
    if (action === "shipment-save") {
      ev.preventDefault();
      shipmentSave(orderId);
      return;
    }
  });
})();
