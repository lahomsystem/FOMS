/**
 * 주문 등록 빠른 시작 시트 — 아이폰 전용.
 *
 * 아이폰 사파리는 **사용자 제스처 안에서 일어난 진짜 포커스 변화**에만 소프트 자판을
 * 올린다. 마법사는 `/add?open=erp-order&wizard=1` 로 **새 문서를 여는 이동**이라 진입
 * 시점에 제스처가 없고(＋ 버튼을 탭한 활성화는 이전 문서에 속한다), 그래서 안드로이드와
 * 달리 들어가자마자 타이핑을 시작할 수 없었다. 스크립트가 부르는 `focus()`·`click()`
 * 에는 그 활성화 표식이 없어서 "한 줄 추가"로는 뚫리지 않는다(2026-09-15, 세 번 실패).
 *
 * 그래서 전제를 바꾼다. 마법사로 **넘어가기 전에**, ＋ 버튼을 탭한 그 제스처 안에서
 * 지금 화면 위에 고객명 한 칸짜리 시트를 열고 거기에 포커스를 준다. 제스처 안이므로
 * 자판이 곧바로 올라온다 — 원리상 보장된다. 사용자가 이름을 치고 "다음"을 누르면 그
 * 값을 들고 마법사로 넘어가고, 마법사는 고객명이 채워진 채로 열린다.
 *
 * 안드로이드는 진입 즉시 커서·자판이 이미 되므로 이 시트를 끼우지 않는다(한 단계가
 * 늘어나기만 한다).
 */
(function () {
  "use strict";

  var STORE_KEY = "foms-wizard-quickstart-name";
  var SHEET_ID = "foms-quickstart";
  var bound = false;
  var els = null;
  var targetHref = "";

  /**
   * iOS(아이폰·아이패드) 사파리 계열 여부.
   * iPadOS 13+ 는 UA 가 Mac 으로 위장하므로 maxTouchPoints 로 보강한다
   * (같은 판별이 estimate-preview.js·mobile-push.js·wizard.js 에도 있다).
   * @returns {boolean}
   */
  function isIosLike() {
    var ua = navigator.userAgent || "";
    if (/iPad|iPhone|iPod/.test(ua)) return true;
    return navigator.platform === "MacIntel"
      && typeof navigator.maxTouchPoints === "number"
      && navigator.maxTouchPoints > 1;
  }

  /**
   * 요소 하나 만들기(innerHTML 금지 — 사용자 입력이 섞이는 자리다).
   * @param {string} tag 태그명.
   * @param {string} className 클래스.
   * @param {string=} text 텍스트.
   * @returns {HTMLElement}
   */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.appendChild(document.createTextNode(text));
    return node;
  }

  /**
   * 시트를 **미리** 만들어 둔다.
   *
   * 탭 순간에 DOM 을 만들면 그 사이 브라우저가 한숨 돌리게 되어 제스처 안 동기 포커스가
   * 흔들린다. 그래서 만들기는 로드 때 끝내고, 탭에서는 보여 주기와 포커스만 한다.
   * @returns {{root: HTMLElement, input: HTMLInputElement, submit: HTMLElement}}
   */
  function buildSheet() {
    var root = el("div", "foms-quickstart");
    root.id = SHEET_ID;
    root.hidden = true;

    var backdrop = el("div", "foms-quickstart__backdrop");
    backdrop.setAttribute("data-quickstart-close", "");

    var panel = el("div", "foms-quickstart__panel");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", "새 주문 — 고객명 입력");

    var label = el("label", "foms-quickstart__label", "고객명");
    var input = document.createElement("input");
    input.type = "text";
    input.className = "foms-input foms-quickstart__input";
    input.id = "foms-quickstart-name";
    input.setAttribute("autocomplete", "name");
    input.setAttribute("enterkeyhint", "next");
    input.placeholder = "예: 고명옥";
    label.setAttribute("for", input.id);

    var hint = el("p", "foms-quickstart__hint", "이름을 적고 다음으로 넘어가세요. 나중에 고칠 수 있어요.");

    var actions = el("div", "foms-quickstart__actions");
    var cancel = el("button", "foms-btn foms-btn--secondary foms-quickstart__cancel", "취소");
    cancel.type = "button";
    cancel.setAttribute("data-quickstart-close", "");
    var submit = el("button", "foms-btn foms-btn--primary foms-quickstart__submit", "다음 →");
    submit.type = "button";

    actions.appendChild(cancel);
    actions.appendChild(submit);
    panel.appendChild(label);
    panel.appendChild(input);
    panel.appendChild(hint);
    panel.appendChild(actions);
    root.appendChild(backdrop);
    root.appendChild(panel);
    document.body.appendChild(root);

    return { root: root, input: input, submit: submit };
  }

  /**
   * 마법사로 넘어간다. 적어 둔 이름은 세션 저장소로 건네고(주소창에 고객명을 남기지
   * 않는다), 마법사가 열리면서 그 값을 채운다.
   * @returns {void}
   */
  function go() {
    var name = String(els.input.value || "").trim();
    try {
      if (name) {
        window.sessionStorage.setItem(STORE_KEY, name);
      } else {
        window.sessionStorage.removeItem(STORE_KEY);
      }
    } catch (e) {
      /* 사파리 사생활 보호 모드 등 — 이름만 못 넘길 뿐 이동은 한다 */
    }
    if (targetHref) window.location.href = targetHref;
  }

  /**
   * 시트를 닫는다(이동하지 않는다).
   * @returns {void}
   */
  function close() {
    if (!els) return;
    els.root.hidden = true;
    els.input.value = "";
  }

  /**
   * 시트를 연다. **탭 핸들러 안에서 동기로** 불려야 자판이 올라온다.
   * @param {string} href 마법사 주소.
   * @returns {void}
   */
  function open(href) {
    targetHref = href;
    els.root.hidden = false;
    // 레이아웃을 한 번 확정시켜 방금 보이게 된 칸에 포커스가 확실히 들어가게 한다.
    void els.input.offsetHeight;
    els.input.focus();
  }

  function onDocumentClick(ev) {
    if (!els) return;
    var closer = ev.target && ev.target.closest ? ev.target.closest("[data-quickstart-close]") : null;
    if (closer && els.root.contains(closer)) {
      ev.preventDefault();
      close();
      return;
    }
    if (ev.target && els.submit === ev.target.closest(".foms-quickstart__submit")) {
      ev.preventDefault();
      go();
      return;
    }
    var link = ev.target && ev.target.closest ? ev.target.closest('a[href*="wizard=1"]') : null;
    if (!link) return;
    // 초안 이어쓰기(`key=`)는 이미 쓰던 주문을 여는 것이라 고객명을 새로 묻지 않는다.
    if (String(link.getAttribute("href") || "").indexOf("key=") !== -1) return;
    if (!els.root.hidden) return;
    ev.preventDefault();
    open(link.href);
  }

  function onKeydown(ev) {
    if (!els || els.root.hidden) return;
    if (ev.key === "Escape") {
      close();
      return;
    }
    if (ev.key === "Enter" && ev.target === els.input) {
      ev.preventDefault();
      go();
    }
  }

  function init() {
    if (bound || !isIosLike() || !document.body) return;
    bound = true;
    els = buildSheet();
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKeydown);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
