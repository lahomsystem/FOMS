/**
 * 새 주문 마법사 4단계 — 같은 고객의 진행 중 주문 한 줄.
 *
 * 설계서 2026-11-20 "한 주문 여러 시공일 1단계" 6.2 (M15 · M17).
 * 마지막 확인 단계에 들어올 때 서버에 물어 맨 위에 한 줄을 그린다. 알리기만 하고 등록은 막지 않는다.
 * wizard.js 는 고치지 않는다 — #foms-wizard-root 의 data-current-step 이 4 가 되는 것을 지켜본다.
 * 프리랜서는 서버가 403 을, 목록 밖 역할은 로그인 화면 HTML 을 준다 — 둘 다 막힘으로 보고 다시 묻지 않는다.
 * 고객 이름은 보내지 않는다(서버가 찾는 데 쓰지 않고, 주소창 기록 · 접속 로그에 남는다).
 * 화면 낭독기가 첫 안내를 읽도록 자리는 처음부터 접근성 트리에 두고, 비었을 때는 visually-hidden 으로 눈에만 숨긴다.
 * 글은 textContent 로만 넣는다(주소는 저장된 값이다).
 */
(function () {
  "use strict";

  var TITLE = "이 고객의 진행 중인 주문이 있습니다";
  var OPEN_LABEL = "그 주문 열기";
  var CONFIRM_STEP = "4";
  var EMPTY_CLASS = "visually-hidden";

  var root = document.getElementById("foms-wizard-root");
  var box = document.getElementById("foms-wizard-same-customer");
  if (!root || !box) return;
  var lookupUrl = box.getAttribute("data-lookup-url") || "";
  if (!lookupUrl) return;

  var lastKey = null;
  var requestSeq = 0;
  var denied = false;

  function fieldValue(id) {
    var el = document.getElementById(id);
    return el ? String(el.value || "").trim() : "";
  }

  /** '2026-11-17' → '11/17'. 꼴이 다르면 그대로 둔다. */
  function shortDate(value) {
    var match = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(value || ""));
    return match ? parseInt(match[2], 10) + "/" + parseInt(match[3], 10) : String(value || "");
  }

  /** 주문 한 줄 글: '주문 #5687 · 생산 단계 · 시공 11/5, 11/17 · 주소'. */
  function orderText(order) {
    var parts = ["주문 #" + order.order_id];
    if (order.stage_label) parts.push(order.stage_label + " 단계");
    var dates = Array.isArray(order.construction_dates) ? order.construction_dates : [];
    if (dates.length) parts.push("시공 " + dates.map(shortDate).join(", "));
    if (order.address) parts.push(order.address);
    return parts.join(" · ");
  }

  function hide() {
    box.classList.add(EMPTY_CLASS);
    box.replaceChildren();
  }

  /** JSON 이 아닌 응답(권한 밖 역할이 받는 로그인 화면 등)이면 null. */
  async function readJson(response) {
    var type = response.headers.get("Content-Type") || "";
    if (type.indexOf("application/json") === -1) return null;
    try {
      return await response.json();
    } catch (parseError) {
      return null;
    }
  }

  function render(data) {
    var orders = Array.isArray(data.orders) ? data.orders : [];
    if (!orders.length) {
      hide();
      return;
    }
    var title = document.createElement("strong");
    title.textContent = TITLE;
    var nodes = [title];
    orders.forEach(function (order) {
      var row = document.createElement("span");
      row.appendChild(document.createTextNode(orderText(order) + " "));
      var href = order.mobile_url || order.url;
      if (href) {
        var link = document.createElement("a");
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = OPEN_LABEL;
        link.setAttribute("aria-label", OPEN_LABEL + " (주문 #" + order.order_id + ")");
        row.appendChild(link);
      }
      nodes.push(row);
    });
    var more = parseInt(data.more, 10) || 0;
    if (more > 0) {
      var rest = document.createElement("span");
      rest.textContent = "외 " + more + "건";
      nodes.push(rest);
    }
    box.replaceChildren.apply(box, nodes);
    box.classList.remove(EMPTY_CLASS);
  }

  /** 4단계에 들어올 때 한 번 묻는다. 같은 입력이면 다시 묻지 않는다. */
  async function check() {
    if (denied) return;
    var phone = fieldValue("wiz-phone");
    var address = fieldValue("wiz-address");
    var key = phone + "|" + address;
    if (key === lastKey) return;
    lastKey = key;
    var mine = ++requestSeq;
    if (!phone && !address) {
      hide();
      return;
    }
    var params = new URLSearchParams({ phone: phone, address: address });
    try {
      var response = await fetch(lookupUrl + "?" + params.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      var data = response.status === 403 ? null : await readJson(response);
      if (response.status === 403 || data === null) {
        denied = true; // 막힌 역할 — 이 화면에서는 다시 묻지 않는다
        hide();
        return;
      }
      if (mine !== requestSeq) return; // 늦게 온 옛 응답은 버린다
      if (!response.ok || !data || !data.success) {
        hide();
        return;
      }
      render(data.data || {});
    } catch (error) {
      if (mine === requestSeq) hide();
      console.warn("[wizard-same-customer] 진행 중 주문 확인 실패", error);
    }
  }

  function onStepChange() {
    if (root.getAttribute("data-current-step") === CONFIRM_STEP) check();
  }

  new MutationObserver(onStepChange).observe(root, { attributes: true, attributeFilter: ["data-current-step"] });
  onStepChange();
})();
