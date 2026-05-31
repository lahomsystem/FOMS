/**
 * P1-07 KV copy buttons + clipboard toast.
 */
(function () {
  "use strict";

  function toast(msg) {
    if (window.fomsShowToast) {
      window.fomsShowToast(msg);
      return;
    }
    var el = document.getElementById("foms-kv-copy-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "foms-kv-copy-toast";
      el.className = "foms-inline-toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("is-visible");
    setTimeout(function () {
      el.classList.remove("is-visible");
    }, 1800);
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-copy-value]");
    if (!btn) return;
    var value = btn.getAttribute("data-copy-value") || "";
    if (!value) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(function () {
        toast((btn.getAttribute("data-copy-label") || "값") + " 복사됨");
      }).catch(function () {
        toast("복사 실패");
      });
    } else {
      toast("클립보드 미지원");
    }
  });
})();
