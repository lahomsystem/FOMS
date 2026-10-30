/**
 * 이름 뱃지 입력 칸 (MULTI-MGR-01, 2026-10-30).
 *
 * 담당자·시공 담당자처럼 "여러 명"을 받는 칸을 뱃지 입력으로 바꾼다.
 * `data-name-chips` 가 붙은 원래 input/textarea 는 숨긴 **값 보관 칸**으로 남는다 —
 * 그 칸의 `.value` 를 읽고 쓰는 기존 코드(저장 조립·자동 저장 복원·변환 문구·지방주문
 * 확인 창·시공자 덮어쓰기 확인)가 그대로 돈다. 값은 이름을 구분자로 이은 문자열이다.
 *
 *   data-name-chips-sep="newline"  → 줄바꿈으로 잇는다(시공 담당자 정본 포맷).
 *   (없음)                          → ", " 로 잇는다(담당자).
 *   data-name-chips-primary         → 첫 뱃지에 "대표" 표시(담당자: 첫 사람 = 대표).
 *
 * 입력: Enter·쉼표·목록 고르기·칸 떠나기로 뱃지가 되고, 빈 칸에서 Backspace 는 마지막
 * 뱃지를 지운다. 바뀔 때마다 보관 칸에 input·change 이벤트를 쏜다(자동 저장·변경 감지).
 * 코드가 보관 칸 `.value` 를 바꾸면 뱃지를 다시 그린다(인스턴스 value 속성 가로채기).
 */
(function () {
  "use strict";

  var SELECTOR = "[data-name-chips]";

  // 괄호 밖 쉼표·줄바꿈에서만 나눈다 — "백재현(2번, 3번)" 은 한 사람(운영 #5579).
  function splitOutsideParens(text) {
    var parts = [];
    var buf = "";
    var depth = 0;
    String(text == null ? "" : text).split("").forEach(function (ch) {
      if (ch === "(") depth += 1;
      else if (ch === ")" && depth > 0) depth -= 1;
      if (depth === 0 && (ch === "," || ch === "\n")) {
        parts.push(buf);
        buf = "";
      } else {
        buf += ch;
      }
    });
    parts.push(buf);
    return parts;
  }

  function insideParens(text) {
    return (String(text).match(/\(/g) || []).length > (String(text).match(/\)/g) || []).length;
  }

  function splitNames(value) {
    var raw = Array.isArray(value) ? value : splitOutsideParens(value);
    var names = [];
    raw.forEach(function (item) {
      var name = String(item == null ? "" : item).trim();
      if (name && names.indexOf(name) === -1) names.push(name);
    });
    return names;
  }

  function valueDescriptor(el) {
    var proto = Object.getPrototypeOf(el);
    while (proto) {
      var desc = Object.getOwnPropertyDescriptor(proto, "value");
      if (desc && desc.get && desc.set) return desc;
      proto = Object.getPrototypeOf(proto);
    }
    return null;
  }

  function fire(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function enhance(source) {
    if (!source || source.__fomsNameChips) return source && source.__fomsNameChips;
    var desc = valueDescriptor(source);
    if (!desc) return null;
    // 한 줄 input 은 값의 줄바꿈을 지워 이름이 붙어 버린다 — 줄바꿈 구분자는 textarea 만.
    var sep = source.getAttribute("data-name-chips-sep") === "newline" && source.tagName === "TEXTAREA" ? "\n" : ", ";
    var markPrimary = source.hasAttribute("data-name-chips-primary");

    var box = document.createElement("div");
    box.className = "foms-name-chips " + source.className.replace(/\berp-autosize-textarea\b|\berp-flex-textarea\b|\bd-none\b/g, "");
    var chips = document.createElement("span");
    chips.className = "foms-name-chips__list";
    var entry = document.createElement("input");
    entry.type = "text";
    entry.className = "foms-name-chips__entry";
    entry.id = source.id ? source.id + "-entry" : "";
    entry.autocomplete = "off";
    entry.setAttribute("lang", source.getAttribute("lang") || "ko");
    entry.placeholder = source.getAttribute("placeholder") || "";
    if (source.getAttribute("list")) entry.setAttribute("list", source.getAttribute("list"));
    box.appendChild(chips);
    box.appendChild(entry);

    if (source.id) {
      document.querySelectorAll('label[for="' + source.id + '"]').forEach(function (label) {
        label.htmlFor = entry.id;
      });
    }
    source.classList.add("foms-name-chips__source");
    source.setAttribute("aria-hidden", "true");
    source.tabIndex = -1;
    source.parentNode.insertBefore(box, source.nextSibling);

    function current() {
      return splitNames(desc.get.call(source));
    }

    function locked() {
      return source.disabled || source.readOnly;
    }

    function render() {
      var names = current();
      chips.textContent = "";
      names.forEach(function (name, index) {
        var chip = document.createElement("span");
        chip.className = "foms-name-chips__chip";
        if (markPrimary && index === 0 && names.length > 1) {
          chip.classList.add("is-primary");
          chip.title = "대표 담당자";
        }
        var text = document.createElement("span");
        text.className = "foms-name-chips__text";
        text.textContent = name;
        chip.appendChild(text);
        if (!locked()) {
          var remove = document.createElement("button");
          remove.type = "button";
          remove.className = "foms-name-chips__remove";
          remove.setAttribute("aria-label", name + " 빼기");
          remove.textContent = "×";
          remove.addEventListener("click", function (event) {
            event.stopPropagation();
            write(current().filter(function (n) { return n !== name; }));
            entry.focus();
          });
          chip.appendChild(remove);
        }
        chips.appendChild(chip);
      });
      entry.disabled = !!source.disabled;
      entry.readOnly = !!source.readOnly;
      entry.placeholder = names.length ? "" : source.getAttribute("placeholder") || "";
      box.classList.toggle("is-locked", locked());
    }

    function write(names) {
      desc.set.call(source, splitNames(names).join(sep));
      render();
      fire(source);
    }

    function commit() {
      var typed = splitNames(entry.value);
      entry.value = "";
      if (!typed.length) return;
      write(current().concat(typed));
    }

    function isListOption(value) {
      var listId = entry.getAttribute("list");
      var list = listId && document.getElementById(listId);
      if (!list) return false;
      return Array.prototype.some.call(list.options, function (opt) { return opt.value === value; });
    }

    Object.defineProperty(source, "value", {
      configurable: true,
      get: function () { return desc.get.call(source); },
      set: function (v) {
        desc.set.call(source, splitNames(v).join(sep));
        render();
      },
    });

    entry.addEventListener("keydown", function (event) {
      if (event.isComposing) return;
      if (event.key === "Enter" || (event.key === "," && !insideParens(entry.value))) {
        event.preventDefault();
        commit();
      } else if (event.key === "Backspace" && !entry.value) {
        var names = current();
        if (names.length) write(names.slice(0, -1));
      }
    });
    entry.addEventListener("input", function (event) {
      if (splitOutsideParens(entry.value).length > 1) {
        commit();
      } else if (event.inputType === "insertReplacementText" || (!event.inputType && isListOption(entry.value))) {
        commit(); // 목록(datalist)에서 고른 이름
      }
    });
    entry.addEventListener("blur", commit);
    box.addEventListener("click", function (event) {
      if (event.target === box || event.target === chips) entry.focus();
    });
    new MutationObserver(render).observe(source, { attributes: true, attributeFilter: ["disabled", "readonly"] });

    render();
    source.__fomsNameChips = { box: box, entry: entry, render: render, names: current };
    return source.__fomsNameChips;
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll(SELECTOR).forEach(enhance);
  }

  window.FomsNameChips = { enhance: enhance, enhanceAll: enhanceAll, splitNames: splitNames };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { enhanceAll(document); });
  } else {
    enhanceAll(document);
  }
})();
