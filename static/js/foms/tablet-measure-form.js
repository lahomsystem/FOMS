/**
 * FOMS 태블릿 전용 실측 폼 (W-MEASURE-FORM) — 태블릿 가로(코호트) 실측 split view 우측 패널.
 *
 * 목업 frame02의 "실측 전용 터치 폼"을 구현한다. 기존 PC ERP Order edit fragment 주입을
 * 대체하되, 데이터는 100% 기존 구조화 API로 읽고 쓴다(신규 백엔드 없음):
 *   - 읽기: GET  /api/orders/<id>/structured           (전사 공용 구조화 조회)
 *   - 쓰기: PUT  /api/orders/<id>/structured           (전사 공용 구조화 저장 = PC "저장"과 동일 경로)
 *   - 사진: GET  /api/orders/<id>/attachments?category=measurement (읽기전용 표시만; 업로드=phase-2)
 *
 * 데이터 무결성(핵심):
 *   - read-merge-write: GET 전체 payload 를 메모리에 보관하고 실측 관련 키만 변형한 뒤
 *     "전체 shape 그대로" PUT 한다 → 폼이 렌더하지 않는 필드(도면/결제/채널톡/quests 등)를
 *     절대 덮어쓰지 않는다(서버 _preserve_operational_structured_state 와 이중 방어).
 *   - 규격 W/H/D 는 items[].spec_rows(=출고 W·자수 SSOT)에 직접 기록(목업 주석 #3 "별도 전기 단계
 *     제거"). 파생값(자수=W/300)은 표시만 클라이언트 계산, 저장하지 않는다(서버 eval_spec_width_mm SSOT).
 *   - PC 폼이 함께 보내는 raw_order_text/received_date/received_time/is_regional/construction_type/
 *     is_self_measurement 는 이 폼이 편집하지 않으므로 PUT payload 에서 생략한다(키 부재=서버 보존).
 *     이 필드들을 보내면 서버가 값을 덮어써 지방주문·자가실측 플래그가 유실된다(clobber).
 *
 * 동시성:
 *   - 명시 저장/실측완료 직전 GET 으로 structured_updated_at 을 baseline 과 비교 → 다른 곳에서
 *     수정됐으면 배너를 띄우고 PUT 을 중단한다(silent overwrite 금지). PUT 경로는 버전 토큰/409 를
 *     제공하지 않으므로(백엔드 무변경 제약) 이 클라이언트 가드가 충돌 감지의 SSOT다.
 *   - 자동저장은 last-write-wins(전체 merge payload 라 무관 필드 clobber 없음). 저장 성공 때마다
 *     경량 GET 으로 baseline 을 갱신해 다음 명시 저장의 오탐(내 저장을 충돌로 오인)을 막는다.
 *
 * 재실행 안전(perf G4): window.__FOMS_TABLET_MEASURE_FORM_BOUND 싱글턴 가드 + 위임 이벤트.
 * 이 모듈은 스스로 활성화하지 않는다 — 코호트 게이트를 통과한 tablet-measurement.js 가
 * load()/requestSave()/requestComplete() 로 구동한다(중복 게이트 정의 금지).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_MEASURE_FORM_BOUND) return;
  window.__FOMS_TABLET_MEASURE_FORM_BOUND = true;

  var AUTOSAVE_DEBOUNCE_MS = 1500;
  var DETAIL_SELECTOR = ".foms-tablet-measure-detail";
  var INJECT_SELECTOR = "[data-foms-tablet-measure-detail]";
  var STATUS_SELECTOR = "[data-foms-tablet-measure-status]";
  // 실측 완료 → 도면 단계(목업 "실측 완료 → 도면 전달"; PC 단계 select 의 "D. 도면" = DRAWING).
  // 서버 _handle_stage_transition 이 workflow.stage 변경을 감지해 order.status/OrderEvent/Quest 를 처리한다.
  var NEXT_STAGE_ON_COMPLETE = "DRAWING";

  // 활성 주문 1건의 편집 상태. 카드 전환 시 통째로 교체된다.
  var state = null;

  function structuredUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/structured";
  }
  function attachmentsUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/attachments?category=measurement";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function deepClone(obj) {
    try {
      return obj == null ? {} : JSON.parse(JSON.stringify(obj));
    } catch (e) {
      return {};
    }
  }

  // 복합 규격 W(가로) → 총 폭(mm). Python foms.services.erp_template_filters.eval_spec_width_mm 미러.
  // 괄호 안 세부치수 무시, 최상위 '+'/',' 가산항의 첫 숫자 토큰 합산.
  function evalSpecWidthMm(value) {
    if (value == null) return 0;
    var s = String(value).trim();
    if (!s) return 0;
    s = s.replace(/\([^)]*\)/g, "");
    var total = 0;
    var matched = false;
    s.split(/[+,]/).forEach(function (term) {
      var m = term.match(/[\d.]+/);
      if (!m) return;
      var n = parseFloat(m[0]);
      if (!isNaN(n)) {
        total += n;
        matched = true;
      }
    });
    return matched ? total : 0;
  }

  // 항목 자수(W/300) 표시값. spec_rows 각 행 W 합산 후 /300, 소수 1자리. 표시 전용(저장 안 함).
  function itemJasuDisplay(item) {
    if (!item || typeof item !== "object") return "";
    var rows = Array.isArray(item.spec_rows) ? item.spec_rows : [];
    var totalW = 0;
    rows.forEach(function (row) {
      if (row && typeof row === "object") {
        totalW += evalSpecWidthMm(row.spec_width != null ? row.spec_width : row.w);
      }
    });
    if (!totalW) return "";
    return String(Math.round((totalW / 300) * 10) / 10);
  }

  // ── DOM 헬퍼 ───────────────────────────────────────────────────────
  function detailEl() {
    return document.querySelector(DETAIL_SELECTOR);
  }
  function injectEl() {
    return document.querySelector(INJECT_SELECTOR);
  }
  function statusEl() {
    var d = detailEl();
    return d ? d.querySelector(STATUS_SELECTOR) : null;
  }
  function formEl() {
    var inj = injectEl();
    return inj ? inj.querySelector("[data-foms-tmf]") : null;
  }

  function setStatus(text, kind) {
    var el = statusEl();
    if (!el) return;
    el.textContent = text || "";
    el.className = "foms-tmf-status" + (kind ? " foms-tmf-status--" + kind : "");
    el.hidden = !text;
  }

  // ── 구조화 접근자(방어적) ───────────────────────────────────────────
  function ensureMeasurementSchedule() {
    if (!state.structured.schedule || typeof state.structured.schedule !== "object") {
      state.structured.schedule = {};
    }
    if (
      !state.structured.schedule.measurement ||
      typeof state.structured.schedule.measurement !== "object"
    ) {
      state.structured.schedule.measurement = {};
    }
    return state.structured.schedule.measurement;
  }

  function itemsList() {
    return Array.isArray(state.structured.items) ? state.structured.items : [];
  }

  function isEditable() {
    // ERP 원장(구조화 데이터)이 있는 주문만 실측 폼으로 편집 가능. 레거시 비-ERP 주문은
    // structured PUT 필수값(고객/전화/주소/제품)이 없어 400 이 나므로 편집을 막고 안내한다.
    var sd = state && state.structured;
    if (!sd || typeof sd !== "object") return false;
    var hasItems = Array.isArray(sd.items) && sd.items.length > 0;
    var hasParties = sd.parties && typeof sd.parties === "object";
    return hasItems || hasParties;
  }

  // ── 렌더 ────────────────────────────────────────────────────────────
  function scheduleValue(key) {
    var m = state.structured.schedule && state.structured.schedule.measurement;
    return m && typeof m === "object" ? m[key] || "" : "";
  }

  function renderItemChips() {
    var list = itemsList();
    if (!list.length) {
      return '<div class="foms-tmf__empty-note">제품 항목이 없습니다. ERP 편집에서 항목을 추가하세요.</div>';
    }
    var chips = list
      .map(function (item, idx) {
        var name = (item && (item.product_name || item.name)) || "제품 " + (idx + 1);
        var active = idx === state.activeItem ? " is-active" : "";
        return (
          '<button type="button" class="foms-tmf__chip' +
          active +
          '" data-tmf-item="' +
          idx +
          '">' +
          (idx + 1) +
          ". " +
          escapeHtml(name) +
          "</button>"
        );
      })
      .join("");
    return '<div class="foms-tmf__chips" role="group" aria-label="제품 항목 선택">' + chips + "</div>";
  }

  // 규격 행의 한 차원 값(spec_width|spec_depth|spec_height, 레거시 w|d|h 폴백)을 문자열로.
  function specDim(row, primary, legacy) {
    if (!row || typeof row !== "object") return "";
    var v = row[primary];
    if (v == null) v = row[legacy];
    return v == null ? "" : String(v);
  }

  function renderSpecRow(itemIdx, rowIdx, row, rowCount) {
    var w = escapeHtml(specDim(row, "spec_width", "w"));
    var d = escapeHtml(specDim(row, "spec_depth", "d"));
    var h = escapeHtml(specDim(row, "spec_height", "h"));
    var rowLabel = rowCount > 1 ? '<div class="foms-tmf__spec-rowlabel">규격 ' + (rowIdx + 1) + "</div>" : "";
    function box(dim, label, value) {
      return (
        '<div class="foms-tmf__numfield">' +
        '<label class="foms-tmf__numlabel">' +
        label +
        "</label>" +
        '<div class="foms-tmf__numwrap">' +
        '<input class="foms-tmf__num" type="text" inputmode="numeric" autocomplete="off" ' +
        'data-tmf-spec="' +
        dim +
        '" data-item-index="' +
        itemIdx +
        '" data-row-index="' +
        rowIdx +
        '" value="' +
        value +
        '" aria-label="' +
        label +
        '">' +
        '<span class="foms-tmf__unit">mm</span>' +
        "</div>" +
        "</div>"
      );
    }
    return (
      '<div class="foms-tmf__spec-row">' +
      rowLabel +
      '<div class="foms-tmf__numgrid">' +
      box("width", "W (가로)", w) +
      box("depth", "D (깊이)", d) +
      box("height", "H (높이)", h) +
      "</div>" +
      "</div>"
    );
  }

  function renderItemSpec() {
    var list = itemsList();
    var item = list[state.activeItem];
    if (!item) return "";
    var rows = Array.isArray(item.spec_rows) && item.spec_rows.length ? item.spec_rows : [{}];
    var rowsHtml = rows
      .map(function (row, rIdx) {
        return renderSpecRow(state.activeItem, rIdx, row, rows.length);
      })
      .join("");
    var jasu = itemJasuDisplay(item);
    // 자수 요소는 항상 렌더(빈 값이면 hidden) — 규격 입력 중 요소 생성/재렌더로 포커스를 잃지 않게.
    var jasuHtml =
      '<div class="foms-tmf__jasu"' +
      (jasu ? "" : " hidden") +
      '>자수 (W/300) <strong>' +
      escapeHtml(jasu) +
      "</strong></div>";
    return rowsHtml + jasuHtml;
  }

  function renderForm() {
    var inj = injectEl();
    if (!inj) return;

    if (!isEditable()) {
      var editHref = state.ctx && state.ctx.editUrl ? escapeHtml(state.ctx.editUrl) : "";
      inj.innerHTML =
        '<div class="foms-tmf" data-foms-tmf>' +
        '<div class="foms-tmf__notice">' +
        "<p>이 주문은 ERP 원장(구조화 데이터)이 없어 실측 폼으로 편집할 수 없습니다.</p>" +
        (editHref
          ? '<a class="foms-btn foms-btn--secondary" href="' + editHref + '">ERP 편집 열기</a>'
          : "") +
        "</div></div>";
      return;
    }

    var measDate = escapeHtml(scheduleValue("date"));
    var measTime = escapeHtml(scheduleValue("time"));
    var notesVal = escapeHtml(state.notes || "");
    var editHref2 = state.ctx && state.ctx.editUrl ? escapeHtml(state.ctx.editUrl) : "";

    inj.innerHTML =
      '<div class="foms-tmf" data-foms-tmf data-order-id="' +
      escapeHtml(state.orderId) +
      '">' +
      // 충돌 배너(기본 숨김)
      '<div class="foms-tmf__banner" data-tmf-banner hidden role="alert">' +
      '<span>다른 곳에서 이 주문이 수정되었습니다. 최신 내용을 불러오세요.</span>' +
      '<button type="button" class="foms-btn foms-btn--sm foms-btn--secondary" data-tmf-refresh>새로고침</button>' +
      "</div>" +
      // 섹션 1: 일정
      '<section class="foms-tmf__section">' +
      '<h3 class="foms-tmf__title">일정</h3>' +
      '<div class="foms-tmf__field">' +
      '<label class="foms-tmf__label" for="foms-tmf-meas-date">실측일</label>' +
      '<input class="foms-tmf__input" id="foms-tmf-meas-date" type="text" inputmode="text" autocomplete="off" ' +
      'data-tmf-field="measurement_date" value="' +
      measDate +
      '" placeholder="예: 2026-07-11 (여러 날짜는 쉼표로)">' +
      "</div>" +
      '<div class="foms-tmf__field">' +
      '<label class="foms-tmf__label" for="foms-tmf-meas-time">실측시간</label>' +
      '<input class="foms-tmf__input" id="foms-tmf-meas-time" type="text" inputmode="text" autocomplete="off" ' +
      'data-tmf-field="measurement_time" value="' +
      measTime +
      '" placeholder="예: 오전 / 오후 / 09:30">' +
      "</div>" +
      "</section>" +
      // 섹션 2: 제품 항목(규격 W/H/D)
      '<section class="foms-tmf__section">' +
      '<h3 class="foms-tmf__title">제품 항목 — 실측 치수</h3>' +
      renderItemChips() +
      '<div class="foms-tmf__spec" data-tmf-spec-panel>' +
      renderItemSpec() +
      "</div>" +
      "</section>" +
      // 섹션 3: 현장 메모(notes)
      '<section class="foms-tmf__section">' +
      '<h3 class="foms-tmf__title">현장 메모</h3>' +
      '<textarea class="foms-tmf__textarea" data-tmf-field="notes" rows="4" ' +
      'placeholder="현장 특이사항 · 시공 참고 메모">' +
      notesVal +
      "</textarea>" +
      "</section>" +
      // 섹션 4: 사진(읽기전용 + ERP 편집 링크; 업로드=phase-2)
      '<section class="foms-tmf__section">' +
      '<h3 class="foms-tmf__title">실측 사진</h3>' +
      '<div class="foms-tmf__photos" data-tmf-photos><div class="foms-tmf__photo-loading">사진 불러오는 중…</div></div>' +
      (editHref2
        ? '<a class="foms-tmf__photo-add foms-btn foms-btn--secondary foms-btn--sm" href="' +
          editHref2 +
          '"><i class="fas fa-camera" aria-hidden="true"></i><span>ERP 편집에서 첨부</span></a>'
        : "") +
      "</section>" +
      "</div>";

    renderPhotos();
  }

  function refreshSpecPanel() {
    var panel = formEl() ? formEl().querySelector("[data-tmf-spec-panel]") : null;
    if (panel) panel.innerHTML = renderItemSpec();
  }

  function refreshJasuOnly() {
    // 규격 입력 중 포커스를 잃지 않게 자수 표시만 갱신(패널/요소 재생성 없이 text+hidden 토글).
    var form = formEl();
    if (!form) return;
    var item = itemsList()[state.activeItem];
    var wrap = form.querySelector(".foms-tmf__jasu");
    if (!wrap) return;
    var strong = wrap.querySelector("strong");
    var jasu = itemJasuDisplay(item);
    if (strong) strong.textContent = jasu;
    wrap.hidden = !jasu;
  }

  // ── 사진(읽기전용) ──────────────────────────────────────────────────
  function renderPhotos() {
    var host = formEl() ? formEl().querySelector("[data-tmf-photos]") : null;
    if (!host) return;
    var orderId = state.orderId;
    fetch(attachmentsUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        // 응답 도착 시 다른 주문으로 전환됐으면 무시(stale).
        if (!state || state.orderId !== orderId) return;
        var host2 = formEl() ? formEl().querySelector("[data-tmf-photos]") : null;
        if (!host2) return;
        var list = data && data.success && Array.isArray(data.attachments) ? data.attachments : [];
        state.photos = list;
        if (!list.length) {
          host2.innerHTML = '<div class="foms-tmf__photo-empty">등록된 실측 사진이 없습니다.</div>';
          return;
        }
        host2.innerHTML = list
          .map(function (att, idx) {
            var url = att.view_url || att.url || "";
            var name = att.filename || "사진";
            var isVideo = /\.(mp4|webm|ogg|mov)$/i.test(url) || /\.(mp4|webm|ogg|mov)$/i.test(name);
            var inner = isVideo
              ? '<span class="foms-tmf__photo-video"><i class="fas fa-play" aria-hidden="true"></i></span>'
              : '<img src="' + escapeHtml(url) + '" alt="' + escapeHtml(name) + '" loading="lazy">';
            return (
              '<button type="button" class="foms-tmf__photo" data-tmf-photo="' +
              idx +
              '" title="' +
              escapeHtml(name) +
              '">' +
              inner +
              "</button>"
            );
          })
          .join("");
      })
      .catch(function () {
        if (!state || state.orderId !== orderId) return;
        var host3 = formEl() ? formEl().querySelector("[data-tmf-photos]") : null;
        if (host3) host3.innerHTML = '<div class="foms-tmf__photo-empty">사진을 불러오지 못했습니다.</div>';
      });
  }

  function openPhoto(idx) {
    var list = state && Array.isArray(state.photos) ? state.photos : [];
    if (!list.length) return;
    if (window.GlobalImageViewer && typeof window.GlobalImageViewer.open === "function") {
      var files = list.map(function (att) {
        return {
          url: att.view_url || att.url || "",
          view_url: att.view_url || att.url || "",
          download_url: att.download_url || "",
          filename: att.filename || "사진",
          key: att.key || att.storage_key || null,
        };
      });
      window.GlobalImageViewer.open(files, idx);
      return;
    }
    var one = list[idx];
    if (one && (one.view_url || one.url)) window.open(one.view_url || one.url, "_blank", "noopener");
  }

  // ── 저장(PUT read-merge-write) ──────────────────────────────────────
  function buildPayload() {
    // 이 폼이 편집하는 키만 담고, 나머지(raw_order_text/received_*/is_regional/construction_type/
    // is_self_measurement)는 생략한다 → 서버가 키 부재를 보존으로 처리(clobber 방지).
    var payload = {
      structured_data: state.structured,
      structured_schema_version: state.schemaVersion || 1,
      // 비고(order.notes): 빈 문자열도 반드시 전송(키 생략 시 서버가 갱신 안 함).
      notes: state.notes != null ? state.notes : "",
    };
    if (state.confidence != null) payload.structured_confidence = state.confidence;
    return payload;
  }

  function scheduleAutosave() {
    if (!state) return;
    state.dirty = true;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(function () {
      saveNow({ explicit: false });
    }, AUTOSAVE_DEBOUNCE_MS);
    setStatus("변경됨", "");
  }

  function checkConflict(orderId) {
    // 명시 저장 직전 최신 structured_updated_at 을 baseline 과 비교. 다르면 충돌.
    return fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) return false; // 조회 실패는 충돌로 보지 않음(저장 시도 계속)
        if (state.baselineUpdatedAt == null) return false;
        return data.structured_updated_at !== state.baselineUpdatedAt;
      })
      .catch(function () {
        return false;
      });
  }

  function refreshBaseline(orderId) {
    // 저장 성공 후 baseline 갱신(내 저장으로 서버 updated_at 이 전진했으므로 다음 명시 저장의 오탐 방지).
    // DOM 은 다시 채우지 않는다(입력 clobber 방지) — updated_at 만 읽는다.
    return fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data && data.success && state && state.orderId === orderId) {
          state.baselineUpdatedAt = data.structured_updated_at;
        }
      })
      .catch(function () {});
  }

  function putStructured(orderId, payload) {
    return fetch(structuredUrl(orderId), {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (res) {
      return res.json().then(function (data) {
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }

  function showConflictBanner() {
    var form = formEl();
    var banner = form ? form.querySelector("[data-tmf-banner]") : null;
    if (banner) banner.hidden = false;
    setStatus("충돌 — 저장 중단", "conflict");
  }

  function saveNow(opts) {
    opts = opts || {};
    if (!state || !isEditable()) return;
    if (state.saving) {
      state.pendingSave = true; // 진행 중이면 종료 후 1회 재저장(single-flight).
      return;
    }
    window.clearTimeout(state.saveTimer);
    var orderId = state.orderId;
    var explicit = !!opts.explicit;
    var isComplete = !!opts.complete;

    // 실측 완료: workflow.stage=DRAWING 을 이 PUT 에만 실어 서버가 단계 전환하게 한다.
    // 저장이 성공해야만 로컬 상태에 유지되도록, 충돌/실패 시 원래 stage 로 되돌린다
    // (그러지 않으면 이후 자동저장이 의도치 않게 단계 전환을 재시도할 수 있다).
    var stageApplied = false;
    var prevStage;
    if (isComplete) {
      if (!state.structured.workflow || typeof state.structured.workflow !== "object") {
        state.structured.workflow = {};
      }
      prevStage = state.structured.workflow.stage;
      state.structured.workflow.stage = NEXT_STAGE_ON_COMPLETE;
      stageApplied = true;
    }
    function revertStage() {
      if (stageApplied && state && state.structured && state.structured.workflow) {
        state.structured.workflow.stage = prevStage;
      }
    }

    state.saving = true;
    setStatus("저장 중…", "saving");

    var pre = explicit ? checkConflict(orderId) : Promise.resolve(false);
    pre
      .then(function (conflict) {
        if (conflict) {
          revertStage();
          state.saving = false;
          showConflictBanner();
          return null;
        }
        return putStructured(orderId, buildPayload());
      })
      .then(function (result) {
        if (result == null) return; // 충돌로 중단됨
        if (!state || state.orderId !== orderId) {
          return;
        }
        if (result.data && result.data.success) {
          state.dirty = false;
          setStatus(isComplete ? "도면 전달 완료" : "저장됨", "saved");
          if (isComplete) onCompleteSaved();
          refreshBaseline(orderId);
        } else {
          revertStage();
          var msg = (result.data && result.data.message) || "저장 실패";
          setStatus(msg, "error");
        }
      })
      .catch(function () {
        revertStage();
        setStatus("네트워크 오류 — 저장 실패", "error");
      })
      .then(function () {
        // finally: 진행 중 예약된 재저장 처리.
        if (state && state.orderId === orderId) {
          state.saving = false;
          if (state.pendingSave) {
            state.pendingSave = false;
            saveNow({ explicit: false });
          }
        }
      });
  }

  function onCompleteSaved() {
    // 실측 완료(→도면) 후: 좌측 활성 카드를 완료 처리(dim)해 피드백. 목록은 서버 렌더라 자동 갱신 안 됨.
    var card = document.querySelector(".foms-tablet-measure-card.is-active");
    if (card) card.classList.add("is-completed");
  }

  function flushPending() {
    if (state && state.dirty && !state.saving && isEditable()) {
      saveNow({ explicit: false });
    }
  }

  // ── 공개 API(tablet-measurement.js 가 구동) ────────────────────────
  function load(orderId, ctx) {
    // 이전 주문의 미저장 편집을 새 주문 로드 전에 flush(카드 전환 시 유실 방지).
    flushPending();

    var inj = injectEl();
    if (inj) {
      inj.innerHTML = '<div class="foms-tmf__loading">주문 원장 불러오는 중…</div>';
    }
    setStatus("", "");

    fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          if (inj) inj.innerHTML = '<div class="foms-tmf__loading">주문 원장을 불러오지 못했습니다.</div>';
          return;
        }
        state = {
          orderId: orderId,
          ctx: ctx || {},
          structured: deepClone(data.structured_data),
          notes: data.notes || "",
          schemaVersion: data.structured_schema_version || 1,
          confidence: data.structured_confidence != null ? data.structured_confidence : null,
          baselineUpdatedAt: data.structured_updated_at || null,
          activeItem: 0,
          photos: [],
          saving: false,
          pendingSave: false,
          dirty: false,
          saveTimer: null,
        };
        renderForm();
      })
      .catch(function () {
        if (inj) inj.innerHTML = '<div class="foms-tmf__loading">주문 원장을 불러오지 못했습니다.</div>';
      });
  }

  function requestSave() {
    if (!state) return;
    saveNow({ explicit: true });
  }

  function requestComplete() {
    if (!state) return;
    if (!isEditable()) {
      setStatus("이 주문은 실측 폼으로 완료할 수 없습니다.", "error");
      return;
    }
    // 2-tap 확인. stage 전환(→DRAWING)은 saveNow 가 PUT 성공 시에만 로컬에 유지한다.
    if (!window.confirm("실측을 완료하고 도면 단계로 전달하시겠습니까?")) return;
    saveNow({ explicit: true, complete: true });
  }

  window.FomsTabletMeasureForm = {
    load: load,
    requestSave: requestSave,
    requestComplete: requestComplete,
  };

  // ── 위임 이벤트(싱글턴 가드 하 1회 바인딩) ─────────────────────────
  function withinForm(target) {
    return target && target.closest && target.closest("[data-foms-tmf]");
  }

  document.addEventListener("input", function (ev) {
    if (!state) return;
    var t = ev.target;
    if (!withinForm(t)) return;

    var field = t.getAttribute("data-tmf-field");
    if (field) {
      if (field === "measurement_date") {
        ensureMeasurementSchedule().date = t.value;
      } else if (field === "measurement_time") {
        ensureMeasurementSchedule().time = t.value;
      } else if (field === "notes") {
        state.notes = t.value;
      }
      scheduleAutosave();
      return;
    }

    var spec = t.getAttribute("data-tmf-spec");
    if (spec) {
      applySpecEdit(t, spec);
      refreshJasuOnly();
      scheduleAutosave();
    }
  });

  function applySpecEdit(input, dim) {
    var itemIdx = parseInt(input.getAttribute("data-item-index") || "-1", 10);
    var rowIdx = parseInt(input.getAttribute("data-row-index") || "-1", 10);
    var list = itemsList();
    var item = list[itemIdx];
    if (!item || typeof item !== "object") return;
    if (!Array.isArray(item.spec_rows)) item.spec_rows = [];
    while (item.spec_rows.length <= rowIdx) item.spec_rows.push({});
    var row = item.spec_rows[rowIdx];
    if (!row || typeof row !== "object") {
      row = {};
      item.spec_rows[rowIdx] = row;
    }
    var key = dim === "width" ? "spec_width" : dim === "depth" ? "spec_depth" : "spec_height";
    row[key] = input.value;
    // erpCollectStructured 파생 미러링: 첫 행을 spec_width/depth/height 로, spec 원문(WxDxH, 행은 ', ') 재생성.
    var first = item.spec_rows[0] || {};
    item.spec_width = first.spec_width || "";
    item.spec_depth = first.spec_depth || "";
    item.spec_height = first.spec_height || "";
    var lines = item.spec_rows
      .map(function (r) {
        return [r.spec_width, r.spec_depth, r.spec_height]
          .filter(function (v) {
            return v != null && String(v).trim() !== "";
          })
          .join("x");
      })
      .filter(Boolean);
    item.spec = lines.join(", ");
  }

  document.addEventListener("click", function (ev) {
    if (!state) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    if (!withinForm(t)) return;

    var chip = t.closest("[data-tmf-item]");
    if (chip) {
      ev.preventDefault();
      var idx = parseInt(chip.getAttribute("data-tmf-item") || "0", 10);
      if (idx !== state.activeItem) {
        state.activeItem = idx;
        var chips = formEl().querySelectorAll("[data-tmf-item]");
        Array.prototype.forEach.call(chips, function (c) {
          c.classList.toggle("is-active", parseInt(c.getAttribute("data-tmf-item"), 10) === idx);
        });
        refreshSpecPanel();
      }
      return;
    }

    var photo = t.closest("[data-tmf-photo]");
    if (photo) {
      ev.preventDefault();
      openPhoto(parseInt(photo.getAttribute("data-tmf-photo") || "0", 10));
      return;
    }

    var refresh = t.closest("[data-tmf-refresh]");
    if (refresh) {
      ev.preventDefault();
      // 사용자가 서버 최신을 택함 → 재조회(로컬 미저장 편집은 서버 값으로 대체됨).
      load(state.orderId, state.ctx);
      return;
    }
  });

  // 백그라운드 전환/이탈 시 미저장분 flush(field 태블릿 앱 전환 대비).
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flushPending();
  });
  window.addEventListener("pagehide", flushPending);
})();
