/**
 * FOMS 태블릿 가로 AS 전/후 대조 — 카드 CTA(일정 변경 · AS 완료) 배선. (frame08 / T2)
 *
 * 대조 카드 그리드는 자족형이라 tablet-side-sheet.js(주문 edit fragment 전용)를 쓰지 않는다.
 * 두 CTA 만 담당한다:
 *   - .foms-as-compare-reschedule → 카드의 방문일 date input
 *     (.editable-date-as[data-field="as_visit_date"]) picker 를 연다. 실제 저장은
 *     as-dashboard.js 의 기존 editable-date-as change 배선이 담당(중복 배선 없음).
 *   - .foms-as-compare-complete → /api/update_order_field 로 as_completed_date=오늘(KST) 저장.
 *     field_update.py SSOT 가 이때 status=AS_COMPLETED 로 전이한다(대시보드 '완료' 탭 정합).
 *     성공 시 카드 배지/버튼을 낙관적으로 완료 표시 + 공용 토스트(#saveToast) 피드백.
 *
 * 표시 게이트는 CSS(coarse landscape 코호트)가 소유한다 — JS 는 코호트 판정 없이 document
 * 위임만 한다(코호트 밖 PC/폰에선 버튼이 은닉/미렌더라 클릭 자체가 발생하지 않음). fragment
 * 스왑(fast-tab)으로 카드가 재삽입돼도 document 위임이라 재바인딩이 불필요하다.
 *
 * idempotent: window.__FOMS_TABLET_AS_COMPARE_BOUND 싱글턴 가드(perf 가드 G4 — 전역 listener
 * 중복 바인딩 방지). defer 로드(perf 가드 G1).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_AS_COMPARE_BOUND) return;
  window.__FOMS_TABLET_AS_COMPARE_BOUND = true;

  // 서버 get_today_kst 와 정합하는 KST(UTC+9) 오늘 YYYY-MM-DD.
  function todayKstIso() {
    var now = new Date();
    var kstMs = now.getTime() + now.getTimezoneOffset() * 60000 + 9 * 3600000;
    var kst = new Date(kstMs);
    var m = String(kst.getMonth() + 1);
    var d = String(kst.getDate());
    if (m.length < 2) m = "0" + m;
    if (d.length < 2) d = "0" + d;
    return kst.getFullYear() + "-" + m + "-" + d;
  }

  // 공용 토스트(#saveToast) 재사용. 없거나 bootstrap 미로드면 콘솔로 폴백(무음 금지).
  function showToast(message, isError) {
    var toastEl = document.getElementById("saveToast");
    if (!toastEl || !window.bootstrap || !window.bootstrap.Toast) {
      if (isError) console.warn("[tablet-as-compare]", message);
      return;
    }
    var msgEl = document.getElementById("toastMessage");
    if (msgEl) msgEl.textContent = message;
    toastEl.classList.toggle("bg-danger", !!isError);
    toastEl.classList.toggle("bg-success", !isError);
    window.bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 2000 }).show();
  }

  function findCard(el) {
    return el && el.closest ? el.closest(".foms-as-compare-card") : null;
  }

  // 일정 변경: 카드의 방문일 date input picker 를 연다(저장은 기존 as-dashboard.js 배선).
  function openReschedule(btn) {
    var card = findCard(btn);
    if (!card) return;
    var input = card.querySelector('.editable-date-as[data-field="as_visit_date"]');
    if (!input) {
      showToast("방문일 입력을 찾지 못했습니다.", true);
      return;
    }
    input.focus();
    if (typeof input.showPicker === "function") {
      try {
        input.showPicker();
      } catch (e) {
        /* user-gesture 밖/미지원 — focus 폴백으로 충분(무음 아님: 입력 자체가 보임). */
      }
    }
  }

  // 낙관적 완료 표시: 배지 → AS완료, 버튼 → 완료됨(비활성).
  function markCardComplete(btn) {
    var card = findCard(btn);
    if (card) {
      card.classList.remove("is-pending");
      var badge = card.querySelector(".foms-as-compare-card__status");
      if (badge) {
        badge.textContent = "AS완료";
        badge.classList.remove("foms-stage-badge--cs");
        badge.classList.add("foms-stage-badge--completed");
      }
    }
    var done = document.createElement("span");
    done.className = "foms-as-compare-btn foms-as-compare-btn--done";
    done.setAttribute("aria-disabled", "true");
    done.title = "AS 완료됨";
    done.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i><span>완료됨</span>';
    if (btn.parentNode) btn.parentNode.replaceChild(done, btn);
  }

  // AS 완료: as_completed_date=오늘 저장(field_update SSOT → AS_COMPLETED 전이).
  function completeAs(btn) {
    var orderId = btn.dataset.orderId;
    if (!orderId || btn.disabled) return;
    btn.disabled = true;
    fetch("/api/update_order_field", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        order_id: orderId,
        field_name: "as_completed_date",
        new_value: todayKstIso(),
      }),
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          throw new Error((data && data.message) || "AS 완료 저장에 실패했습니다.");
        }
        markCardComplete(btn);
        showToast("AS 완료로 처리했습니다.");
      })
      .catch(function (err) {
        btn.disabled = false;
        showToast("저장 실패: " + String((err && err.message) || err || ""), true);
      });
  }

  // 방문일 오버레이 표시 텍스트 갱신: date input(.foms-as-compare-visit__date) change 시
  // 겹쳐진 표시 텍스트를 새 값으로 반영한다(저장은 as-dashboard.js .editable-date-as change
  // 계약이 별도 담당 — 두 리스너는 독립, 충돌 없음). 코호트 밖에선 오버레이 마크업이 CSS 로
  // 미표시라 무해.
  function syncVisitDateText(input) {
    var wrap = input.closest(".foms-as-compare-visit__datewrap");
    if (!wrap) return;
    var textEl = wrap.querySelector(".foms-as-compare-visit__datetext-value");
    if (textEl) textEl.textContent = input.value || "미정";
  }

  // 단일 document 위임(fragment 스왑 무관 · 코호트 밖 무동작).
  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var reschedule = t.closest(".foms-as-compare-reschedule");
    if (reschedule) {
      ev.preventDefault();
      openReschedule(reschedule);
      return;
    }
    var complete = t.closest(".foms-as-compare-complete");
    if (complete) {
      ev.preventDefault();
      completeAs(complete);
    }
  });

  document.addEventListener("change", function (ev) {
    var t = ev.target;
    if (!t || !t.classList || !t.classList.contains("foms-as-compare-visit__date")) return;
    syncVisitDateText(t);
  });
})();
