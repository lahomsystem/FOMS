(function () {
  if (window.__erpWdcSplitBound) {
    return;
  }
  window.__erpWdcSplitBound = true;

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  function getCustomerName() {
    var erpCustomer = document.getElementById("erp-customer-name");
    if (erpCustomer && erpCustomer.value) {
      return erpCustomer.value.trim();
    }
    var legacyCustomer = document.getElementById("customer_name");
    return legacyCustomer && legacyCustomer.value ? legacyCustomer.value.trim() : "";
  }

  function buildFrameSrc(frame) {
    var base = frame.getAttribute("data-src") || "/wdcalculator?embedded=1";
    var url = new URL(base, window.location.origin);
    url.searchParams.set("embedded", "1");
    var customerName = getCustomerName();
    if (customerName) {
      url.searchParams.set("customer_name", customerName);
    }
    return url.pathname + url.search + url.hash;
  }

  function postCustomerName(frame) {
    if (!frame || !frame.contentWindow) {
      return;
    }
    frame.contentWindow.postMessage(
      {
        type: "foms:wdc:set-customer-name",
        customerName: getCustomerName(),
      },
      window.location.origin
    );
  }

  ready(function () {
    var shell = document.getElementById("erpEditShell");
    var pane = document.getElementById("erpWdcSplitPane");
    var frame = document.getElementById("erpWdcSplitFrame");
    var toggle = document.getElementById("erpWdcSplitToggle");
    var closeBtn = document.getElementById("erpWdcSplitClose");
    var loadingWrap = document.getElementById("erpWdcSplitLoading");
    var customerInput = document.getElementById("erp-customer-name");

    if (!shell || !pane || !frame || !toggle) {
      return;
    }

    function setOpen(nextOpen) {
      shell.classList.toggle("is-wdc-split-open", nextOpen);
      pane.classList.toggle("d-none", !nextOpen);
      toggle.setAttribute("aria-expanded", nextOpen ? "true" : "false");
      toggle.querySelector("span").textContent = nextOpen ? "계산기 닫기" : "계산기 같이 보기";

      if (nextOpen && !frame.getAttribute("src")) {
        frame.setAttribute("src", buildFrameSrc(frame));
      } else if (nextOpen) {
        postCustomerName(frame);
      }
    }

    toggle.addEventListener("click", function () {
      setOpen(!shell.classList.contains("is-wdc-split-open"));
    });

    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        setOpen(false);
      });
    }

    frame.addEventListener("load", function () {
      var frameWrap = frame.closest(".erp-wdc-split-frame-wrap");
      if (frameWrap) {
        frameWrap.classList.add("is-loaded");
      }
      if (loadingWrap) {
        loadingWrap.setAttribute("aria-hidden", "true");
      }
      postCustomerName(frame);
    });

    if (customerInput) {
      customerInput.addEventListener("input", function () {
        if (shell.classList.contains("is-wdc-split-open")) {
          postCustomerName(frame);
        }
      });
    }

    if (window.matchMedia && window.matchMedia("(min-width: 992px)").matches) {
      setOpen(true);
    }
  });
})();
