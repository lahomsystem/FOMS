/**
 * 태블릿 가로 출고 세부정보 서랍 보조 (설계서 2026-11-09-tablet-production-ui_SPEC §14.3 P14-4).
 *
 * 서랍 본문 = templates/shipment/partials/tablet_sheet.html. 저장(시간 · 메모)은
 * tablet-domain-sheets.js 의 shipment-save 가 맡고, 이 파일은 셋만 한다.
 *   1) 표 줄 누름 직전에 시트 주소에 고른 날짜(?date=)를 붙인다 — 서랍이 그날 품목만 보이게.
 *   2) 시간 단추(오전 8시 · 오후 1시 · 직접) → 시간 칸 채우기/포커스.
 *   3) AS 줄 서랍이 들어오면 AS 탭 읽기 조각(/erp/as/timeline/<id>?readonly=1)을 불러 붙인다.
 *      readonly=1 이 기록 추가 · 수정 · 삭제 · 판정 단추를 숨긴다. 비용(금액) 칸은 붙인 뒤 지운다(D7).
 *
 * 시트 조각은 공용 fragment-loader 가 넣고 foms:erp-shell-fragment-swapped(source=tablet-sheet)를
 * 쏜다 — 그 이벤트를 받는다. 문서 위임 싱글턴(perf G4), jQuery 없음.
 */
(function () {
  "use strict";

  if (window.__FOMS_SHIP_SHEET_BOUND) return;
  window.__FOMS_SHIP_SHEET_BOUND = true;

  function sheetBody() {
    return document.querySelector(".foms-tablet-sheet__body");
  }

  // 1) 줄 누름(캡처 단계 — 시트 여는 tablet-side-sheet.js 의 버블 리스너보다 먼저 돈다).
  document.addEventListener("click", function (ev) {
    var row = ev.target && ev.target.closest
      ? ev.target.closest(".foms-tablet-shipgrid-wrap tr[data-foms-sheet-url]")
      : null;
    if (!row) return;
    var cfg = document.getElementById("shipment-dashboard-config");
    var day = cfg ? (cfg.getAttribute("data-selected-date") || "") : "";
    var url = (row.getAttribute("data-foms-sheet-url") || "").split("?")[0];
    if (!url) return;
    row.setAttribute("data-foms-sheet-url", /^\d{4}-\d{2}-\d{2}$/.test(day) ? url + "?date=" + day : url);
  }, true);

  // 2) 시간 단추 · 4) 붙인 AS 기록 사진 누름.
  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!t || !t.closest || !t.closest(".foms-ship-sheet")) return;
    var sheet = t.closest(".foms-ship-sheet");
    var input = sheet.querySelector("input[data-tablet-assign-time]");
    var chip = t.closest("[data-tablet-time-chip]");
    if (chip && input) {
      input.value = chip.value || chip.textContent.trim();
      return;
    }
    if (t.closest("[data-tablet-time-custom-trigger]") && input) {
      input.value = "";
      input.focus();
      return;
    }
    // AS 탭이 한 번 열렸던 문서면 as-dashboard.js 위임이 이미 사진을 연다 — 겹치지 않게 비킨다.
    var file = t.closest(".as-rchart-file");
    if (!file || window.__FOMS_AS_TIMELINE_BOUND) return;
    var url = file.getAttribute("data-file-url");
    if (!url) return;
    if (file.getAttribute("data-file-image") === "1" && window.GlobalImageViewer) {
      window.GlobalImageViewer.open([{ url: url, name: file.getAttribute("data-file-name") || "", type: "image" }], 0);
    } else {
      window.open(url, "_blank", "noopener");
    }
  });

  // 3) AS 탭 읽기 조각 불러 붙이기.
  function setState(box, text, retry) {
    box.innerHTML = "";
    var p = document.createElement("p");
    p.className = "foms-ship-sheet__muted";
    p.textContent = text;
    box.appendChild(p);
    if (!retry) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "foms-ship-sheet__btn foms-ship-sheet__btn--wide";
    btn.textContent = "다시 불러오기";
    btn.addEventListener("click", function () { loadAsLog(box); });
    box.appendChild(btn);
  }

  async function loadAsLog(box) {
    var url = box.getAttribute("data-ship-as-log-url");
    if (!url) return;
    box.setAttribute("data-ship-as-log-state", "loading");
    setState(box, "AS 기록을 불러오는 중이에요…", false);
    try {
      var res = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "foms-ship-sheet" },
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      var html = await res.text();
      if (!box.isConnected) return; // 그사이 다른 줄 서랍으로 바뀜
      box.innerHTML = html;
      // 비용 칸(유상 금액이 실릴 수 있다)은 출고 서랍에 두지 않는다(D7 금액 없음).
      Array.prototype.forEach.call(
        box.querySelectorAll(".as-rchart-field--billing, .as-billing-state"),
        function (el) { el.remove(); }
      );
      if (!box.querySelector(".as-rchart")) setState(box, "AS 기록이 없어요", false);
      box.setAttribute("data-ship-as-log-state", "done");
    } catch (err) {
      console.error("[tablet-ship-sheet] AS 기록 불러오기 실패:", err);
      if (!box.isConnected) return;
      box.setAttribute("data-ship-as-log-state", "error");
      setState(box, "AS 기록을 못 불러왔어요", true);
    }
  }

  document.addEventListener("foms:erp-shell-fragment-swapped", function (ev) {
    if (!ev.detail || ev.detail.source !== "tablet-sheet") return;
    var body = sheetBody();
    var box = body ? body.querySelector("[data-ship-as-log-url]:not([data-ship-as-log-state])") : null;
    if (box) loadAsLog(box);
  });
})();
