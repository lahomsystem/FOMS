/**
 * 작성 중인 주문(초안) 되찾기 줄 — 모바일 홈 대시보드 상단.
 *
 * 초안은 TTL 이 지나면 조용히 사라지는데(``new.*`` 7일) 목록이 없어 화면을 한 번 떠난
 * 사용자는 그것을 되찾을 방법이 아예 없었다. 실제로 2026-09-02·09-03·09-10 세 건이
 * 그렇게 유실됐다(09-10 건은 채널톡 발송까지 끝난 뒤였다).
 *
 * 서버가 이미 지원하는 진입 링크(`/add?key=<draft_key>&wizard=1&step=n`)를 그대로 쓴다.
 * 목록 조회는 **화면이 그려진 뒤** 한 번 더 부르는 별도 요청이다 — 대시보드 쿼리에 얹으면
 * 홈 응답시간에 그대로 붙는다(성능 가드).
 *
 * 초안 라우트는 마법사 코호트 게이트 뒤에 있다. 자격이 없으면 403 이 오고, 그때는 아무것도
 * 그리지 않는다(줄 자체가 없다).
 */
(function () {
  "use strict";

  var LIST_URL = "/api/erp/order-draft/list";
  var MAX_STEP = 4;

  /**
   * 텍스트 노드를 붙인 엘리먼트를 만든다(innerHTML 금지 — 고객명이 그대로 들어온다).
   * @param {string} tag 태그 이름.
   * @param {string} className 클래스.
   * @param {string} [text] 텍스트.
   * @returns {HTMLElement}
   */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text) {
      node.appendChild(document.createTextNode(text));
    }
    return node;
  }

  /**
   * 초안 1건을 카드 한 줄로 그린다.
   * @param {Object} draft 목록 API 의 한 행.
   * @returns {HTMLAnchorElement}
   */
  function renderRow(draft) {
    var step = parseInt(draft.step, 10);
    if (isNaN(step) || step < 1) {
      step = 1;
    }
    if (step > MAX_STEP) {
      step = MAX_STEP;
    }
    var row = el("a", "foms-draft-resume__row");
    row.href =
      "/add?key=" + encodeURIComponent(draft.draft_key) + "&wizard=1&step=" + step;

    var head = el("span", "foms-draft-resume__row-head");
    head.appendChild(
      el("span", "foms-draft-resume__name", draft.customer_name || "이름 아직 없음")
    );
    if (draft.has_send_history) {
      // 이 배지가 이 화면이 생긴 이유다 — 발송은 나갔는데 주문은 없는 상태.
      head.appendChild(el("span", "foms-draft-resume__badge", "발송함 · 등록 전"));
    }
    row.appendChild(head);

    var parts = ["단계 " + step + "/" + MAX_STEP];
    if (draft.updated_label) {
      parts.push(draft.updated_label + " 저장");
    }
    if (typeof draft.expires_in_days === "number") {
      parts.push(
        draft.expires_in_days > 0 ? "만료까지 " + draft.expires_in_days + "일" : "오늘 만료"
      );
    }
    row.appendChild(el("span", "foms-draft-resume__meta", parts.join(" · ")));

    if (draft.address) {
      row.appendChild(el("span", "foms-draft-resume__address", draft.address));
    }
    return row;
  }

  /**
   * 목록을 받아 줄과 시트를 채운다. 0건이면 아무것도 그리지 않는다.
   * @param {HTMLElement} root 컨테이너.
   * @param {Array<Object>} drafts 초안 목록.
   * @returns {void}
   */
  function render(root, drafts) {
    if (!drafts.length) {
      return;
    }
    var bar = root.querySelector("#foms-draft-resume-bar");
    var sheet = root.querySelector("#foms-draft-resume-sheet");
    var count = root.querySelector(".foms-draft-resume__count");
    if (!bar || !sheet || !count) {
      return;
    }
    count.textContent = "작성 중인 주문 " + drafts.length + "건";
    drafts.forEach(function (draft) {
      sheet.appendChild(renderRow(draft));
    });
    bar.addEventListener("click", function () {
      var open = sheet.hidden;
      sheet.hidden = !open;
      bar.setAttribute("aria-expanded", open ? "true" : "false");
    });
    root.hidden = false;
  }

  /**
   * 목록을 부른다. 실패(권한 없음·네트워크)면 조용히 물러난다 — 홈 화면을 막지 않는다.
   * @returns {void}
   */
  function init() {
    var root = document.getElementById("foms-draft-resume");
    if (!root || root.fomsDraftResumeBound) {
      return;
    }
    // ERP 셸은 본문만 조각으로 갈아끼운다(foms:erp-shell-fragment-swapped). 그때 placeholder
    // 는 **새 엘리먼트**라 다시 채워야 하고, 같은 엘리먼트를 두 번 채우면 목록이 겹친다.
    root.fomsDraftResumeBound = true;
    fetch(LIST_URL, { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) {
          return null;
        }
        return res.json();
      })
      .then(function (body) {
        if (!body || body.success !== true || !body.data) {
          return;
        }
        var drafts = body.data.drafts;
        render(root, Array.isArray(drafts) ? drafts : []);
      })
      .catch(function () {
        /* 초안 줄이 없다고 홈이 망가지면 안 된다 — 조용히 접는다. */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("foms:main-content-swapped", init);
  document.addEventListener("foms:erp-shell-fragment-swapped", init);
})();
