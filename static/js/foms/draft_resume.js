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
  var DELETE_URL = "/api/erp/order-draft";
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
   * 실패 알림 한 줄.
   *
   * 공용 토스트(``window.fomsShowToast``)를 쓰지 않는다 — 그 토스트의 CSS 는
   * ``foms-inline-edit.css`` 에만 있고 주문 대시보드에는 실리지 않아, 스타일 없는 div 가
   * 문서 끝에 붙을 뿐 스크롤된 모바일 화면에서는 사실상 안 보인다. 초안 삭제는 되돌릴 수
   * 없어서 "실패했는데 못 봤다"가 가장 나쁜 결과라, 확실히 보이는 alert 으로 간다.
   *
   * 성공은 따로 알리지 않는다 — 행이 사라지고 건수가 줄어드는 것이 곧 결과다.
   * @param {string} message 보여 줄 문구.
   * @returns {void}
   */
  function notify(message) {
    window.alert(message);
  }

  /**
   * 삭제 확인 문구. 어느 초안인지(고객명)를 못박아 옆줄을 잘못 지우는 일을 막는다.
   * @param {Object} draft 목록 API 의 한 행.
   * @returns {string}
   */
  function confirmText(draft) {
    var text =
      "\u201c" + draftName(draft) + "\u201d 작성 중인 주문을 지웁니다.\n\n" +
      "지우면 되돌릴 수 없습니다. 올려둔 사진도 함께 사라집니다.";
    if (draft.has_send_history) {
      text += "\n\n이 초안은 고객에게 이미 발송이 나갔습니다.";
    }
    return text;
  }

  /**
   * 행이 이미 보여 주는 이름. 비어 있을 수 있어 같은 기본값을 한 곳에서 만든다.
   * @param {Object} draft 목록 API 의 한 행.
   * @returns {string}
   */
  function draftName(draft) {
    return draft.customer_name || "이름 아직 없음";
  }

  /**
   * 남은 초안 수로 띠 문구를 다시 쓴다. 0건이 되면 띠 자체를 접는다(빈 띠 금지).
   * @param {Object} ctx 띠의 엘리먼트 묶음.
   * @returns {void}
   */
  function syncCount(ctx) {
    var left = ctx.sheet.children.length;
    if (!left) {
      ctx.sheet.hidden = true;
      ctx.bar.setAttribute("aria-expanded", "false");
      ctx.count.textContent = "";
      ctx.root.hidden = true;
      return;
    }
    ctx.count.textContent = "작성 중인 주문 " + left + "건";
  }

  /**
   * 초안 1건을 지운다. 성공하면 그 행만 DOM 에서 덜어낸다.
   *
   * 목록을 다시 부르지 않는 이유: bar 의 토글 리스너를 render() 안에서 붙이므로 render 를
   * 다시 돌리면 리스너가 겹쳐 시트가 열리자마자 닫힌다. 서버 변화가 "그 행 하나 사라짐"
   * 으로 결정적이라 낙관적 제거로 충분하고, 화면을 떠났다 오면 조각 교체가 다시 부른다.
   *
   * @param {Object} ctx 띠의 엘리먼트 묶음.
   * @param {Object} draft 목록 API 의 한 행.
   * @param {HTMLElement} item 행 래퍼.
   * @param {HTMLElement} btn 지우기 버튼.
   * @returns {void}
   */
  function deleteDraft(ctx, draft, item, btn) {
    if (btn.disabled) {
      return;
    }
    if (!window.confirm(confirmText(draft))) {
      return;
    }
    // 연타로 DELETE 가 두 번 나가지 않게 **요청 전에** 잠근다.
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    // CSRF 토큰은 csrf_bootstrap.html 의 fetch 래퍼가 자동으로 얹는다(직접 주입 금지).
    fetch(DELETE_URL + "?key=" + encodeURIComponent(draft.draft_key), {
      method: "DELETE",
      credentials: "same-origin"
    })
      .then(function (res) {
        return res.json();
      })
      .then(
        function (data) {
          if (!data || data.success !== true) {
            // 서버가 안 지웠다 — 버튼을 되돌려 다시 누를 수 있게 한다.
            btn.disabled = false;
            btn.removeAttribute("aria-busy");
            notify("지우지 못했습니다. 잠시 뒤 다시 해 주세요.");
            return;
          }
          // 여기서부터는 **서버가 이미 지웠다**(되돌릴 수 없다). 화면 정리가 실패하더라도
          // "지우지 못했습니다" 라고 말하면 거짓말이 된다 — 실패 경로와 반드시 갈라 둔다.
          // 조각 교체(foms:erp-shell-fragment-swapped)로 이 띠가 통째로 갈린 뒤에 응답이
          // 오면, 떨어져 나간 옛 DOM 을 손대 봐야 화면에 반영되지 않는다. 그때는 건너뛴다
          // (새 띠는 자기 목록을 다시 받아 그린다).
          try {
            // isConnected 가 false 일 때만 건너뛴다(구형 브라우저는 이 속성이 없다).
            if (ctx.root && ctx.root.isConnected !== false) {
              ctx.sheet.removeChild(item);
              syncCount(ctx);
            }
          } catch (domError) {
            /* 화면 정리 실패는 삭제 결과를 뒤집지 않는다 */
          }
        },
        function () {
          // 요청 자체가 실패했다(회선 끊김·JSON 아닌 응답). 무음 실패 금지.
          btn.disabled = false;
          btn.removeAttribute("aria-busy");
          notify("지우지 못했습니다. 잠시 뒤 다시 해 주세요.");
        }
      );
  }

  /**
   * 초안 1건을 카드 한 줄로 그린다.
   *
   * 행 자체가 이어쓰기 링크(<a>)라 지우기 버튼을 그 안에 넣을 수 없다(중첩 인터랙티브 —
   * 모바일에서 탭이 링크로 새어 마법사가 열린다). 래퍼로 감싸 형제로 세운다.
   *
   * @param {Object} ctx 띠의 엘리먼트 묶음.
   * @param {Object} draft 목록 API 의 한 행.
   * @returns {HTMLElement}
   */
  function renderRow(ctx, draft) {
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

    var item = el("div", "foms-draft-resume__item");
    item.setAttribute("data-draft-key", draft.draft_key || "");
    item.appendChild(row);
    if (draft.draft_key) {
      var del = el("button", "foms-draft-resume__delete", "\u2715");
      del.type = "button";
      del.setAttribute("aria-label", draftName(draft) + " 작성 중인 주문 지우기");
      del.setAttribute("title", "지우기");
      del.addEventListener("click", function (ev) {
        // 이어쓰기로 새는 것이 이 버튼의 가장 흔한 버그다 — 링크 이동과 띠 토글을 모두 막는다.
        if (ev && ev.preventDefault) {
          ev.preventDefault();
        }
        if (ev && ev.stopPropagation) {
          ev.stopPropagation();
        }
        deleteDraft(ctx, draft, item, del);
      });
      item.appendChild(del);
    }
    return item;
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
    var ctx = { root: root, bar: bar, sheet: sheet, count: count };
    drafts.forEach(function (draft) {
      sheet.appendChild(renderRow(ctx, draft));
    });
    syncCount(ctx);
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
