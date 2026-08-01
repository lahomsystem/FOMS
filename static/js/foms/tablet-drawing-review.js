/**
 * FOMS 태블릿 도면 리뷰 (E2 배선 · E3 판정 · E5 연속 리뷰 · E6 딜라이트) — 태블릿 가로
 * 코호트에서 도면 썸네일 탭 시 전역 이미지 뷰어(GlobalImageViewer — 블러 배경·핀치 줌·
 * 스와이프)로 전체화면 열람하고, 그 위에서 수령 확정 / 수정 요청까지 끝낸다.
 *
 * 대상 = `[data-foms-drawing-viewer]` 마커 2종:
 *   1) 갤러리 카드 썸네일(.foms-drawing-gallery-card__thumb) — 서버가 내려준
 *      `data-foms-drawing-files`(JSON: [{key, view_url, download_url, filename}])를 그대로
 *      뷰어 파일 목록으로 사용한다. 이미지 도면이 0장인 카드는 서버가 마커를 안 붙인다.
 *   2) 관리 시트 스트립 썸네일(.foms-drawing-sheet__sheet-thumb) — 마법사 미전달 autosave
 *      PNG. 같은 스트립의 형제 img 들을 모아 클릭 인덱스로 연다(열람 전용, 판정 없음).
 *
 * 판정 UI(갤러리 카드 경로에서만) = append 패턴: 뷰어를 연 뒤 `[data-viewer-extra]` 노드를
 *   셸(컨텍스트 스트립)과 `#global-viewer-footer`(액션바)에 붙인다. 코어는 close() 에서
 *   같은 속성을 전수 제거하므로 다른 표면(AS·첨부 뷰어)으로 새지 않는다. 노드 내용 갱신
 *   책임은 이 파일에 있다(연속 전환은 close 없이 open 재호출).
 *   판정 대상 도면 key 는 열 때 인덱스가 아니라 GlobalImageViewer.getIndex() — 스와이프로
 *   다른 장을 보고 있으면 그 장에 수정 요청이 접수돼야 한다.
 *
 * 활성 게이트: MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse).
 *   비-코호트(PC·폰)에선 완전 무동작 → 카드 앵커의 기존 상세 이동 fallback 이 보존된다.
 *
 * 리스너: document 위임 클릭 1개. 시트 aside 는 tablet-side-sheet.js 가 런타임에 생성하므로
 *   컨테이너 바인딩이 불가하다(갤러리·시트 스트립을 한 리스너로 커버). 액션바 버튼은
 *   document 가 아니라 액션바 노드에 위임한다(신규 전역 리스너 금지).
 *   preventDefault + stopPropagation 은 필수 — 카드가 <a> 라 네비 차단 책임이 여기 있다
 *   (tablet-side-sheet.js 는 이 마커를 만나면 early-return 해 시트를 열지 않는다).
 * idempotent: window.__FOMS_DRAWING_REVIEW_BOUND 싱글턴 가드(perf 가드 G4 — fragment 재실행
 *   시 전역 listener 중복 방지).
 */
(function () {
  "use strict";

  if (window.__FOMS_DRAWING_REVIEW_BOUND) return;
  window.__FOMS_DRAWING_REVIEW_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  var VIEWER_SELECTOR = "[data-foms-drawing-viewer]";
  var STRIP_SELECTOR = ".foms-drawing-sheet__strip";
  var GALLERY_SELECTOR = ".foms-drawing-gallery";
  var CARD_SELECTOR = ".foms-drawing-gallery-card[data-order-id]";
  var EXTRA_SELECTOR = "[data-viewer-extra]";
  var HINT_KEY = "fomsDrawingLongpressHintSeen";
  // D5: 수정 요청 사유 프리셋(태블릿 타이핑 최소화). 문구 튜닝은 별도 과제.
  var REASON_CHIPS = ["치수 확인", "재실측 필요", "마감/색상 확인", "설치 간섭"];

  // 현재 리뷰 세션(카드 + 뷰어에 넘긴 파일 목록) — 판정 대상 key 해석의 근거.
  var session = { card: null, files: [] };
  // 액션바 하위 노드 1회 캐시(공유 컨테이너를 통째로 덮어쓰지 않는다 — 마크업 조립 금지 계약).
  var els = {};

  function cohortActive() {
    return MQ.matches;
  }

  /**
   * 뷰어 호출(단일 경로). 부재 시 무음 금지 — 경고 후 중단.
   * @param {Array<Object>} files {view_url, download_url, filename} 목록
   * @param {number} index 초기 표시 인덱스
   */
  function openViewer(files, index) {
    if (!window.GlobalImageViewer || typeof window.GlobalImageViewer.open !== "function") {
      console.warn("[foms-drawing-review] GlobalImageViewer 미로드 — 도면 뷰어 열기 중단");
      return;
    }
    if (!files || !files.length) return;
    var idx = index > 0 && index < files.length ? index : 0;
    window.GlobalImageViewer.open(files, idx);
  }

  /**
   * 갤러리 카드 썸네일 → 서버 JSON 파일 목록.
   * data-* + 가드 파싱 패턴(인라인 JSON.parse('{{ x|tojson }}') 금지).
   * @param {Element} marker
   * @returns {Array<Object>} 파싱 실패/비배열이면 빈 배열
   */
  function galleryFiles(marker) {
    var raw = marker.getAttribute("data-foms-drawing-files");
    if (!raw) return [];
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      console.warn("[foms-drawing-review] 도면 파일 목록 파싱 실패 — 뷰어 생략", e);
      return [];
    }
  }

  /**
   * 시트 스트립 썸네일 → 같은 스트립의 형제 img 전부를 뷰어 파일 목록으로 구성.
   * @param {Element} marker 클릭된 스트립 img
   * @returns {{files: Array<Object>, index: number}}
   */
  function stripFiles(marker) {
    var strip = marker.closest(STRIP_SELECTOR);
    var nodes = strip
      ? strip.querySelectorAll(VIEWER_SELECTOR + "[data-view-url]")
      : [marker];
    var files = [];
    var index = 0;
    Array.prototype.forEach.call(nodes, function (node) {
      var viewUrl = node.getAttribute("data-view-url") || "";
      if (!viewUrl) return;
      if (node === marker) index = files.length;
      files.push({
        view_url: viewUrl,
        download_url: viewUrl,
        filename: node.getAttribute("data-filename") || "도면",
      });
    });
    return { files: files, index: index };
  }

  // --- 연속 리뷰 대상 집합 ---------------------------------------------------

  /**
   * 현재 DOM 목록의 확정 대기(TRANSFERRED) 카드 — 카운터 모수이자 순회 대상.
   * 서버 stats 가 아니라 목록 기준(stats 는 필터 이전 + seed cap 이라 순회 집합과 불일치).
   * 이미지 도면이 없는 카드는 뷰어로 열 수 없으므로 순회에서 제외한다(막다른 길 방지).
   * @returns {Array<Element>}
   */
  function transferredCards() {
    var gallery = document.querySelector(GALLERY_SELECTOR);
    if (!gallery) return [];
    var all = gallery.querySelectorAll('[data-foms-drawing-status="TRANSFERRED"][data-order-id]');
    return Array.prototype.filter.call(all, function (card) {
      return !!card.querySelector("[data-foms-drawing-files]");
    });
  }

  /**
   * DOM 순서상 현재 카드 다음의 확정 대기 카드. 뒤에 없으면 목록 앞에서 다시 찾는다.
   * 반드시 카드 DOM 변경(제거·상태 갱신) **전에** 호출해야 순서 판정이 유효하다.
   * @param {Element} card
   * @returns {Element|null}
   */
  function nextTransferred(card) {
    var list = transferredCards();
    if (!list.length) return null;
    for (var i = 0; i < list.length; i += 1) {
      if (list[i] === card) continue;
      if (card && !(card.compareDocumentPosition(list[i]) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      return list[i];
    }
    return list[0] === card ? null : list[0];
  }

  // --- 액션바 구성 ------------------------------------------------------------

  /** 뷰어에 붙였던 주입 노드 전수 제거(연속 전환은 close 를 거치지 않는다). */
  function teardown() {
    Array.prototype.forEach.call(document.querySelectorAll(EXTRA_SELECTOR), function (node) {
      node.remove();
    });
    els = {};
  }

  /**
   * 버튼 생성 헬퍼 — 라벨은 정적 문자열이지만 일관되게 textContent 로만 넣는다.
   * @param {string} label
   * @param {string} attr 식별 속성명(data-act | data-chip)
   * @param {string} value
   * @param {string} extraClass
   */
  function button(label, attr, value, extraClass) {
    var el = document.createElement("button");
    el.type = "button";
    el.className = extraClass;
    el.setAttribute(attr, value);
    el.textContent = label;
    return el;
  }

  /**
   * 뷰어 상단 컨텍스트 스트립(고객명 · #주문번호 · D-day · 시공일 + 주문변경 경고).
   * 사용자 유래 문자열이라 전부 createElement + textContent (마크업 문자열 조립 금지).
   * @param {Element} card
   * @returns {Element}
   */
  function buildContext(card) {
    var strip = document.createElement("div");
    strip.className = "foms-viewer-context";
    strip.setAttribute("data-viewer-extra", "");
    [
      card.getAttribute("data-foms-customer"),
      "#" + (card.getAttribute("data-order-id") || ""),
      card.getAttribute("data-foms-dday"),
      card.getAttribute("data-foms-install"),
    ].forEach(function (text) {
      if (!text || text === "#") return;
      var item = document.createElement("span");
      item.className = "foms-viewer-context__item";
      item.textContent = text;
      strip.appendChild(item);
    });
    if (card.getAttribute("data-foms-order-change")) {
      var warn = document.createElement("span");
      warn.className = "foms-viewer-context__warn";
      warn.textContent = "⚠ 주문변경 미확인";
      strip.appendChild(warn);
    }
    return strip;
  }

  /** 카운터 문구 — "이 목록 확정 대기 M / N"(현재 카드가 대상 밖이면 총량만). */
  function counterText(card) {
    var list = transferredCards();
    var idx = list.indexOf(card);
    return "이 목록 확정 대기 " + (idx >= 0 ? idx + 1 + " / " + list.length : list.length + "건");
  }

  /**
   * 판정 액션바. 노출 가능한 버튼이 하나도 없으면 null → 열람 전용(도면팀·무권한자).
   * 클라이언트 조건은 편의일 뿐 실제 방어선은 서버(403/400).
   * @param {Element} card
   * @returns {Element|null}
   */
  function buildActions(card) {
    var status = card.getAttribute("data-foms-drawing-status") || "";
    var canConfirm = !!card.getAttribute("data-foms-can-confirm") && status === "TRANSFERRED";
    var canRevise =
      !!card.getAttribute("data-foms-can-revise") &&
      (status === "TRANSFERRED" || status === "CONFIRMED");
    if (!canConfirm && !canRevise) return null;

    var bar = document.createElement("div");
    bar.className = "foms-viewer-actions";
    bar.setAttribute("data-viewer-extra", "");

    var row = document.createElement("div");
    row.className = "foms-viewer-actions__row";
    var counter = document.createElement("span");
    counter.className = "foms-viewer-actions__counter";
    counter.textContent = counterText(card);
    row.appendChild(counter);
    if (canConfirm) {
      row.appendChild(button("수령 확정", "data-act", "confirm", "foms-viewer-actions__btn is-primary"));
    }
    if (canRevise) {
      row.appendChild(button("수정 요청", "data-act", "revise", "foms-viewer-actions__btn"));
    }
    row.appendChild(button("다음 ▸", "data-act", "skip", "foms-viewer-actions__btn"));
    bar.appendChild(row);

    // 수정 요청 입력 패널(사유 칩 + 자유 텍스트) — 기본 숨김, [수정 요청] 탭에서 전환.
    var panel = document.createElement("div");
    panel.className = "foms-viewer-actions__panel";
    panel.hidden = true;
    var chips = document.createElement("div");
    chips.className = "foms-viewer-actions__chips";
    REASON_CHIPS.forEach(function (label) {
      chips.appendChild(button(label, "data-chip", label, "foms-viewer-actions__chip"));
    });
    panel.appendChild(chips);
    var note = document.createElement("textarea");
    note.className = "foms-viewer-actions__note";
    note.rows = 2;
    note.placeholder = "수정 요청 사유(칩을 눌러 채우거나 직접 입력)";
    panel.appendChild(note);
    var panelRow = document.createElement("div");
    panelRow.className = "foms-viewer-actions__row";
    panelRow.appendChild(button("보내기", "data-act", "send", "foms-viewer-actions__btn is-primary"));
    panelRow.appendChild(button("취소", "data-act", "cancel", "foms-viewer-actions__btn"));
    panel.appendChild(panelRow);
    bar.appendChild(panel);

    var status_line = document.createElement("p");
    status_line.className = "foms-viewer-actions__status";
    status_line.setAttribute("role", "status");
    bar.appendChild(status_line);

    els = { bar: bar, row: row, panel: panel, note: note, status: status_line };
    // 액션바 내부 위임 — 신규 document 리스너 금지 계약.
    bar.addEventListener("click", function (ev) {
      onAction(ev, card);
    });
    return bar;
  }

  /**
   * 카드 → 뷰어 열기 + 판정 UI 부착. 최초 탭과 연속 전환의 단일 진입점.
   * @param {Element} card 갤러리 카드
   * @param {Array<Object>=} files 이미 파싱한 파일 목록(없으면 카드에서 읽는다)
   */
  function openCard(card, files) {
    var marker = card ? card.querySelector("[data-foms-drawing-files]") : null;
    var list = files || (marker ? galleryFiles(marker) : []);
    if (!list.length) return;
    openViewer(list, 0);
    teardown();
    session = { card: card, files: list };
    var root = document.getElementById("global-image-viewer");
    var footer = document.getElementById("global-viewer-footer");
    if (!card || !root || !footer) return;
    root.appendChild(buildContext(card));
    var bar = buildActions(card);
    if (bar) footer.appendChild(bar);
  }

  // --- 판정 ------------------------------------------------------------------

  /** 상태 라인 + (있으면) 전역 토스트. 뷰어가 전체화면이라 라인 표시가 1차 채널이다. */
  function notify(message) {
    if (els.status) els.status.textContent = message;
    if (typeof window.fomsShowToast === "function") window.fomsShowToast(message);
  }

  /** 전송 중 이중 탭 방지 — 액션바 버튼 전체 잠금. */
  function setBusy(busy) {
    if (!els.bar) return;
    Array.prototype.forEach.call(els.bar.querySelectorAll("button"), function (btn) {
      btn.disabled = busy;
    });
  }

  /**
   * 판정 API POST. 헤더는 실행판 기존 판정 fetch(workbench_detail_body.html) 패턴 그대로 —
   * 'Content-Type': 'application/json' + 동일 출처 세션 쿠키(앱에 CSRF 토큰 헤더 없음).
   * @param {string} url
   * @param {Object} payload
   * @returns {Promise<{status: number, data: Object}>}
   */
  async function postJson(url, payload) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    var data = await res.json();
    return { status: res.status, data: data || {} };
  }

  /** 실패 문구 — 서버 message 우선, 없으면 상태코드별 안내. */
  function errorText(status, data) {
    if (data && data.message) return data.message;
    if (status === 403) return "권한이 없습니다";
    if (status === 400) return "이미 처리된 도면입니다 — 목록을 새로고침하세요";
    return "전송 실패 — 다시 시도";
  }

  /**
   * 지금 보고 있는 도면의 storage key. 열 때 인덱스가 아니라 뷰어 현재 인덱스를 쓴다
   * (스와이프 후 엉뚱한 도면에 수정 요청이 접수되는 정합성 사고 방지).
   * @returns {string|null}
   */
  function currentKey() {
    var viewer = window.GlobalImageViewer;
    var idx = viewer && typeof viewer.getIndex === "function" ? viewer.getIndex() : 0;
    var file = session.files[idx];
    return (file && (file.key || file.storage_key)) || null;
  }

  /** 수정 요청 성공 카드는 목록에 남아 도면팀 할 일이 된다 — RETURNED + 칩 갱신. */
  function markReturned(card) {
    card.setAttribute("data-foms-drawing-status", "RETURNED");
    var top = card.querySelector(".foms-drawing-gallery-card__top");
    if (!top || top.querySelector(".foms-drawing-gallery-chip.is-urgent")) return;
    var chip = document.createElement("span");
    chip.className = "foms-drawing-gallery-chip is-urgent";
    chip.textContent = "수정 요청";
    top.insertBefore(chip, top.firstChild);
  }

  /** 다음 확정 대기 건으로 전환. 소진 시 안내 후 뷰어 종료(자동 페이지 fetch 없음). */
  function goNext(next) {
    if (next) {
      openCard(next);
      return;
    }
    if (window.GlobalImageViewer) window.GlobalImageViewer.close();
    notify("이 목록의 확정 대기 도면을 모두 검토했습니다 — 다음 페이지에서 계속하세요");
  }

  async function submitConfirm(card) {
    var orderId = card.getAttribute("data-order-id");
    var next = nextTransferred(card); // DOM 변경 전에 확정
    setBusy(true);
    try {
      var out = await postJson("/api/orders/" + orderId + "/confirm-drawing-receipt", {});
      if (!out.data.success) {
        notify(errorText(out.status, out.data));
        return;
      }
      card.remove(); // 확정 = CONFIRM 단계로 이탈 → 큐에서 제거
      goNext(next);
      notify(out.data.message || "수령 확정 완료");
    } catch (e) {
      notify("전송 실패 — 다시 시도");
      console.error("[foms-drawing-review]", orderId, e);
    } finally {
      setBusy(false);
    }
  }

  async function submitRevision(card) {
    var orderId = card.getAttribute("data-order-id");
    var note = ((els.note && els.note.value) || "").trim();
    if (!note) {
      notify("수정 요청 사유를 입력하세요");
      return;
    }
    var key = currentKey();
    if (!key) {
      notify("대상 도면을 확인할 수 없습니다 — 뷰어를 다시 열어 주세요");
      return;
    }
    var next = nextTransferred(card); // DOM 변경 전에 확정
    setBusy(true);
    try {
      var out = await postJson("/api/orders/" + orderId + "/request-revision", {
        note: note,
        target_drawing_keys: [key],
      });
      if (!out.data.success) {
        notify(errorText(out.status, out.data)); // 입력 보존(패널 유지)
        return;
      }
      markReturned(card);
      goNext(next);
      notify(out.data.message || "수정 요청 전송 완료");
    } catch (e) {
      notify("전송 실패 — 다시 시도");
      console.error("[foms-drawing-review]", orderId, e);
    } finally {
      setBusy(false);
    }
  }

  /** 사유 칩 → note 이어붙임(복수 선택, 중복 삽입 방지). */
  function appendNote(text) {
    if (!els.note) return;
    var current = els.note.value.trim();
    if (current.indexOf(text) >= 0) return;
    els.note.value = current ? current + ", " + text : text;
    els.note.focus();
  }

  /** 입력 모드 ↔ 버튼 모드. 취소해도 note 값은 그대로 둔다(재작성 강요 금지). */
  function showPanel(on) {
    if (!els.panel || !els.row) return;
    els.panel.hidden = !on;
    els.row.hidden = on;
  }

  /**
   * 액션바 내부 위임 핸들러. 모든 분기를 try/catch 로 감싼다 — throw 로 뷰어가 조용히
   * 먹통이 되는 것을 금지(async 액션은 각자 내부에서 처리).
   */
  function onAction(ev, card) {
    var btn = ev.target.closest ? ev.target.closest("button") : null;
    if (!btn) return;
    ev.preventDefault();
    try {
      var chip = btn.getAttribute("data-chip");
      if (chip) return appendNote(chip);
      var act = btn.getAttribute("data-act");
      if (act === "revise") return showPanel(true);
      if (act === "cancel") return showPanel(false);
      if (act === "skip") return goNext(nextTransferred(card));
      if (act === "confirm") return submitConfirm(card);
      if (act === "send") return submitRevision(card);
    } catch (e) {
      notify("처리 중 오류가 발생했습니다");
      console.error("[foms-drawing-review]", card.getAttribute("data-order-id"), e);
    }
  }

  // --- E6 ⑥ 롱프레스 다중선택 첫 사용 힌트(1회) ------------------------------

  function mountLongpressHint() {
    if (!cohortActive()) return;
    var gallery = document.querySelector(GALLERY_SELECTOR);
    if (!gallery || !gallery.querySelector(CARD_SELECTOR)) return;
    try {
      if (localStorage.getItem(HINT_KEY)) return;
    } catch (e) {
      return; // 저장소 차단(프라이빗 모드 등) — 매번 뜨는 힌트보다 미표시가 낫다.
    }
    var hint = document.createElement("div");
    hint.className = "foms-drawing-gallery-hint";
    var text = document.createElement("span");
    text.textContent = "카드를 길게 누르면 여러 건을 선택할 수 있습니다";
    var dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "foms-drawing-gallery-hint__close";
    dismiss.setAttribute("aria-label", "안내 닫기");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", function () {
      hint.remove();
      try {
        localStorage.setItem(HINT_KEY, "1");
      } catch (e) {
        console.warn("[foms-drawing-review] 힌트 확인 저장 실패 — 다음에 다시 표시됨", e);
      }
    });
    hint.appendChild(text);
    hint.appendChild(dismiss);
    gallery.parentNode.insertBefore(hint, gallery);
  }

  // 단일 document 위임: 코호트에서만 동작. 갤러리 카드 썸네일 + 시트 스트립 공통 진입점.
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;
    if (target.closest(EXTRA_SELECTOR)) return; // 액션바는 자체 위임이 처리
    var marker = target.closest(VIEWER_SELECTOR);
    if (!marker) return;

    // 카드 <a> 네비 차단 + 사이드 시트 열기 차단(책임이 side-sheet 에서 이관됨).
    ev.preventDefault();
    ev.stopPropagation();

    if (marker.hasAttribute("data-foms-drawing-files")) {
      openCard(marker.closest(CARD_SELECTOR), galleryFiles(marker));
      return;
    }
    var strip = stripFiles(marker);
    teardown(); // 시트 스트립은 열람 전용 — 이전 판정 UI 잔류 금지
    session = { card: null, files: strip.files };
    openViewer(strip.files, strip.index);
  });

  mountLongpressHint();
})();
