/**
 * FOMS Field OS v3 — 모바일 셸 행동 (읽기/표시 전용, v3.0).
 *
 * 목업 IIFE(scratchpad/mockup/foms-mobile-mockup.html)에서 v3.0에 필요한
 * 행동만 이식한다: 바텀시트 열기/닫기(+스크림), 세그먼트 컨트롤, 가로 필터 칩,
 * 접기/펼치기(주문360° 타임라인). 페르소나 스위처·스텝퍼(쓰기)·swipe·서명·QR
 * 데모 코드는 v3.1 쓰기 플로우 소관이라 제외한다.
 *
 * 예외 1건(v3.0 쓰기): 영업 홈 '오늘 동선'의 동행 전달 완료
 * (POST /api/orders/<id>/sales-delivery, 스펙 §6.3). 새 <script> 태그를 늘리지
 * 않으려고 셸 JS 안에 둔다 — layout_head.html 은 공유 핫파일이다.
 *
 * 성능 가드(G4): 전역 listener는 IIFE 안에서 document에 1회만 위임 바인딩하고,
 * `window.__FOS_SHELL_BOUND` singleton 가드로 fragment 재실행 시 중복 바인딩을
 * 막는다. DOM 스캔형 초기화는 없다(위임만 사용) → idempotent.
 */
(function () {
  "use strict";

  if (window.__FOS_SHELL_BOUND) return;
  window.__FOS_SHELL_BOUND = true;

  /* ---- 바텀시트 열기/닫기 -------------------------------------------- */
  function openSheet(id) {
    var sheet = document.querySelector('.fos-sheet[data-sheet="' + id + '"]');
    if (!sheet) return;
    sheet.classList.add("is-open");
    var scrim = sheet.parentNode
      ? sheet.parentNode.querySelector(".fos-scrim")
      : null;
    if (scrim) scrim.classList.add("is-open");
  }

  function closeSheet(fromEl) {
    var host =
      (fromEl && fromEl.closest && fromEl.closest(".fos-shell-v3")) ||
      (fromEl && fromEl.closest && fromEl.closest(".fos-screen")) ||
      document;
    host.querySelectorAll(".fos-sheet.is-open").forEach(function (s) {
      s.classList.remove("is-open");
    });
    host.querySelectorAll(".fos-scrim.is-open").forEach(function (s) {
      s.classList.remove("is-open");
    });
  }

  /* ---- 세그먼트 컨트롤 ------------------------------------------------ */
  function segSwitch(btn) {
    var seg = btn.closest(".fos-seg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.remove("is-active");
    });
    btn.classList.add("is-active");
    var target = btn.getAttribute("data-seg");
    var scope = seg.closest(".fos-screen") || seg.closest(".fos-shell-v3") || document;
    if (target) {
      scope.querySelectorAll("[data-seg-panel]").forEach(function (p) {
        p.classList.toggle("is-active", p.getAttribute("data-seg-panel") === target);
      });
    }
  }

  /* ---- 로딩 스켈레톤 (createElement — 텍스트 폴백 유지) -------------- */
  function buildSkeleton(rows) {
    var wrap = document.createElement("div");
    wrap.className = "fos-skeleton-wrap";
    wrap.setAttribute("role", "status");
    wrap.setAttribute("aria-label", "불러오는 중");
    for (var i = 0; i < rows; i++) {
      var sk = document.createElement("div");
      sk.className = "fos-skeleton";
      var dot = document.createElement("span");
      dot.className = "fos-skeleton__dot";
      var lines = document.createElement("span");
      lines.className = "fos-skeleton__lines";
      var a = document.createElement("span");
      a.className = "sk sk--a";
      var b = document.createElement("span");
      b.className = "sk sk--b";
      lines.appendChild(a);
      lines.appendChild(b);
      sk.appendChild(dot);
      sk.appendChild(lines);
      wrap.appendChild(sk);
    }
    var fb = document.createElement("span");
    fb.className = "fos-skeleton-text";
    fb.textContent = "불러오는 중…";
    wrap.appendChild(fb);
    return wrap;
  }

  /* ---- 주문 360° 타임라인 (읽기 전용 fragment fetch) ----------------- */
  function openTimeline(orderId) {
    if (!orderId) return;
    var body = document.querySelector("[data-fos-timeline-body]");
    openSheet("order360");
    if (!body) return;
    body.textContent = "";
    body.appendChild(buildSkeleton(3));
    fetch("/api/foms/fragment/order/" + encodeURIComponent(orderId) + "/timeline", {
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (html) {
        body.innerHTML = html;
      })
      .catch(function () {
        body.innerHTML =
          '<div class="fos-empty"><span class="fos-empty__ic">' +
          '<i class="fas fa-triangle-exclamation" aria-hidden="true"></i></span>' +
          '<span class="fos-empty__title">타임라인을 불러오지 못했습니다</span>' +
          '<span class="fos-empty__sub">잠시 후 다시 시도하거나 기존 화면에서 확인하세요.</span></div>';
      });
  }

  /* ---- 오늘 동선: 동행 전달 (스펙 §6.3) ------------------------------ */
  /* 유일한 쓰기: POST /api/orders/<id>/sales-delivery {"action":"deliver"}.
     CSRF 헤더는 전역 인터셉터(csrf_bootstrap.html)가 붙인다 — 수동 주입 금지.
     실패를 .alert 로 알리지 않는다(5초 자동 닫힘 = 무음 실패). 카드 안 인라인
     텍스트(data-sales-delivery-msg)에 남겨 사용자가 놓치지 않게 한다. */
  function deliveryMsg(card, text, isError) {
    if (!card) return;
    var slot = card.querySelector("[data-sales-delivery-msg]");
    if (!slot) return;
    slot.textContent = text || "";
    slot.classList.toggle("is-error", !!isError);
    slot.hidden = !text;
  }

  function markDelivered(btn) {
    var card = btn.closest("[data-sales-delivery-card]");
    var orderId = btn.getAttribute("data-order-id");
    if (!orderId || btn.disabled) return;
    btn.disabled = true;
    deliveryMsg(card, "전달 완료를 저장하는 중…", false);
    try {
      fetch("/api/orders/" + encodeURIComponent(orderId) + "/sales-delivery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ action: "deliver" }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (out) {
          if (!out.ok || !out.data || out.data.success !== true) {
            throw new Error((out.data && out.data.error) || "save_failed");
          }
          if (card) {
            card.classList.add("is-done");
            card.setAttribute("data-state", out.data.display_state || "delivered");
            var badge = card.querySelector("[data-deliv-state]");
            if (badge) {
              badge.textContent = "전달 완료됨";
              badge.setAttribute("data-st", "completed");
            }
          }
          deliveryMsg(card, "전달 완료로 기록했습니다.", false);
        })
        .catch(function () {
          btn.disabled = false;
          deliveryMsg(card, "저장하지 못했습니다. 통신 상태를 확인하고 다시 눌러주세요.", true);
        });
    } catch (err) {
      btn.disabled = false;
      deliveryMsg(card, "저장하지 못했습니다. 통신 상태를 확인하고 다시 눌러주세요.", true);
    }
  }

  /* 보조 동작: 서버 액션 없음 — 아무 것도 저장하지 않고 안내만 남긴다. */
  function skipDelivery(btn) {
    var card = btn.closest("[data-sales-delivery-card]");
    deliveryMsg(
      card,
      "전달을 건너뛰었습니다. 저장된 건 없습니다 — AS 화면에서 재배정하거나 택배로 전환하세요.",
      false
    );
  }

  /* ---- 필터 칩 (가로 스크롤, 단일 선택) ------------------------------ */
  function chipSelect(chip) {
    var row = chip.parentNode;
    if (!row) return;
    row.querySelectorAll(".fos-chip").forEach(function (c) {
      c.classList.remove("is-active");
    });
    chip.classList.add("is-active");
  }

  /* ---- 옥외 고대비 모드 (localStorage 유지, 직사광 가독) ------------- */
  var CONTRAST_KEY = "foms_contrast";
  function readContrast() {
    try {
      return window.localStorage.getItem(CONTRAST_KEY) === "high";
    } catch (err) {
      return false;
    }
  }
  function applyContrast(on) {
    var root = document.documentElement;
    if (on) root.setAttribute("data-foms-contrast", "high");
    else root.removeAttribute("data-foms-contrast");
    document.querySelectorAll("[data-foms-contrast-toggle]").forEach(function (b) {
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function toggleContrast() {
    var next = !readContrast();
    try {
      window.localStorage.setItem(CONTRAST_KEY, next ? "high" : "off");
    } catch (err) {
      /* 스토리지 불가(사생활 모드 등) — 세션 내 토글만 반영 */
    }
    applyContrast(next);
  }

  /* ---- 이벤트 위임 (document 1회) ----------------------------------- */
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var el;
    if ((el = t.closest("[data-foms-contrast-toggle]"))) {
      toggleContrast();
      return;
    }
    if ((el = t.closest("[data-fos-timeline]"))) {
      // 카드(<a>) 내부의 표시 전용 트리거 — 기본 링크 이동을 막고 시트만 연다.
      e.preventDefault();
      e.stopPropagation();
      openTimeline(el.getAttribute("data-order-id"));
      return;
    }
    if ((el = t.closest("[data-sales-delivery-done]"))) {
      e.preventDefault();
      markDelivered(el);
      return;
    }
    if ((el = t.closest("[data-sales-delivery-skip]"))) {
      e.preventDefault();
      skipDelivery(el);
      return;
    }
    if ((el = t.closest("[data-open-sheet]"))) {
      openSheet(el.getAttribute("data-open-sheet"));
      return;
    }
    if ((el = t.closest("[data-close-sheet]"))) {
      closeSheet(el);
      return;
    }
    if ((el = t.closest(".fos-scrim"))) {
      closeSheet(el);
      return;
    }
    if ((el = t.closest("[data-tl-toggle]"))) {
      var card = el.closest(".fos-tl-card");
      if (card) card.classList.toggle("is-open");
      return;
    }
    if ((el = t.closest("[data-seg]"))) {
      segSwitch(el);
      return;
    }
    if ((el = t.closest(".fos-chips .fos-chip"))) {
      chipSelect(el);
      return;
    }
  });

  // 부팅 복원: 저장된 고대비 선호를 html·토글 버튼에 반영(defer라 DOM 준비 완료).
  applyContrast(readContrast());

  window.FOMS_SHELL_V3 = {
    openSheet: openSheet,
    closeSheet: closeSheet,
    openTimeline: openTimeline,
    toggleContrast: toggleContrast,
    markDelivered: markDelivered,
    skipDelivery: skipDelivery,
  };
})();
