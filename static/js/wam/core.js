(function initWAMCore(window, document) {
  if (window.WAMCore) {
    return;
  }

  function parseBootstrap() {
    var node = document.getElementById("wam-bootstrap");
    if (!node) {
      return null;
    }

    try {
      return JSON.parse(node.textContent || "{}");
    } catch (error) {
      return null;
    }
  }

  function qs(root, selector) {
    return (root || document).querySelector(selector);
  }

  function qsa(root, selector) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function on(root, eventName, selector, handler) {
    root.addEventListener(eventName, function delegate(event) {
      var target = event.target.closest(selector);
      if (!target || !root.contains(target)) {
        return;
      }

      handler(event, target);
    });
  }

  function ensureLiveRegion() {
    var region = document.getElementById("wam-live-region");
    if (region) {
      return region;
    }

    region = document.createElement("div");
    region.id = "wam-live-region";
    region.className = "visually-hidden";
    region.setAttribute("aria-live", "polite");
    document.body.appendChild(region);
    return region;
  }

  function announce(message) {
    var region = ensureLiveRegion();
    region.textContent = "";

    window.setTimeout(function flushLiveRegion() {
      region.textContent = message;
    }, 10);
  }

  function fallbackCopy(text) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();

    var copied = false;

    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }

    document.body.removeChild(textarea);
    return copied;
  }

  function copyText(text) {
    if (!text) {
      return Promise.resolve(false);
    }

    if (window.navigator.clipboard && window.navigator.clipboard.writeText) {
      return window.navigator.clipboard.writeText(text).then(function success() {
        return true;
      }).catch(function failure() {
        return fallbackCopy(text);
      });
    }

    return Promise.resolve(fallbackCopy(text));
  }

  function updateToggleButton(button, expanded) {
    button.setAttribute("aria-expanded", expanded ? "true" : "false");

    var text = qs(button, ".wam-section__toggle-text");
    if (text) {
      text.textContent = expanded ? "접기" : "열기";
    }
  }

  function setSectionExpanded(section, expanded) {
    var toggle = qs(section, "[data-section-toggle]");
    var body = section ? document.getElementById(toggle && toggle.getAttribute("aria-controls")) : null;

    if (!toggle || !body) {
      return;
    }

    body.hidden = !expanded;
    body.classList.toggle("is-collapsed", !expanded);
    section.dataset.expanded = expanded ? "true" : "false";
    updateToggleButton(toggle, expanded);

    section.dispatchEvent(new CustomEvent("wam:section-toggled", {
      bubbles: true,
      detail: {
        key: section.dataset.sectionKey,
        expanded: expanded
      }
    }));
  }

  function bindSectionToggles(root, options) {
    var config = options || {};

    on(root, "click", "[data-section-toggle]", function handleToggle(event, button) {
      event.preventDefault();

      var section = button.closest("[data-section-key]");
      if (!section) {
        return;
      }

      var nextExpanded = button.getAttribute("aria-expanded") !== "true";
      var group = section.dataset.sectionGroup || config.oneOpenGroup;

      if (nextExpanded && group) {
        qsa(root, '[data-section-group="' + group + '"]').forEach(function collapse(peer) {
          if (peer !== section) {
            setSectionExpanded(peer, false);
          }
        });
      }

      setSectionExpanded(section, nextExpanded);
    });
  }

  function bindCopyButtons(root) {
    on(root, "click", "[data-copy-value]", function handleCopy(event, target) {
      if (target.tagName === "BUTTON" || !target.getAttribute("href")) {
        event.preventDefault();
      }

      var value = target.getAttribute("data-copy-value");
      var label = target.getAttribute("data-copy-label") || "정보";

      copyText(value).then(function complete(copied) {
        if (copied) {
          announce(label + "를 복사했습니다.");
        }
      });
    });
  }

  function openSection(root, key, shouldScroll) {
    var section = qs(root, '[data-section-key="' + key + '"]');
    if (!section) {
      return;
    }

    if (section.dataset.folded === "true") {
      setSectionExpanded(section, true);
    }

    if (shouldScroll) {
      section.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    }
  }

  window.WAMCore = {
    announce: announce,
    bindCopyButtons: bindCopyButtons,
    bindSectionToggles: bindSectionToggles,
    copyText: copyText,
    on: on,
    openSection: openSection,
    parseBootstrap: parseBootstrap,
    qs: qs,
    qsa: qsa,
    setSectionExpanded: setSectionExpanded
  };
})(window, document);
