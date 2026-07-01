/**
 * P2-02 Alpine store: toast + modal helpers for new FOMS surfaces.
 * G4: singleton guard — fragment re-run must not duplicate global listeners.
 */
if (!window.__FOMS_ALPINE_STORE_BOUND) {
  window.__FOMS_ALPINE_STORE_BOUND = true;
  document.addEventListener("alpine:init", function () {
  Alpine.store("fomsToast", {
    message: "",
    visible: false,
    _timer: null,
    show: function (msg) {
      var text = String(msg || "").trim();
      if (!text) return;
      this.message = text;
      this.visible = true;
      if (this._timer) clearTimeout(this._timer);
      var self = this;
      this._timer = setTimeout(function () {
        self.visible = false;
      }, 2200);
    },
  });

  Alpine.data("fomsWizardValidation", function () {
    return {
      errors: {},
      clear: function (field) {
        if (this.errors[field]) delete this.errors[field];
      },
      set: function (field, message) {
        this.errors[field] = message;
      },
      has: function (field) {
        return Boolean(this.errors[field]);
      },
    };
  });
  });
}

window.fomsShowToast = function (message) {
  if (window.Alpine && Alpine.store("fomsToast")) {
    Alpine.store("fomsToast").show(message);
    return;
  }
  var el = document.getElementById("foms-kv-copy-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "foms-kv-copy-toast";
    el.className = "foms-inline-toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add("is-visible");
  setTimeout(function () {
    el.classList.remove("is-visible");
  }, 1800);
};

/**
 * Flash toast across a reload: stash now, show on the next page load. Used by flows
 * that mutate then `window.location.reload()` (e.g. quest approve → stage change),
 * where a normal toast would be wiped by the reload.
 */
window.fomsFlashToast = function (message) {
  var text = String(message || "").trim();
  if (!text) return;
  try {
    sessionStorage.setItem("foms_flash_toast", JSON.stringify({ m: text, t: Date.now() }));
  } catch (e) {
    /* sessionStorage unavailable → best-effort, drop. */
  }
};

function fomsConsumeFlashToast() {
  var raw;
  try {
    raw = sessionStorage.getItem("foms_flash_toast");
    if (!raw) return;
    sessionStorage.removeItem("foms_flash_toast");
  } catch (e) {
    return;
  }
  var data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return;
  }
  // Only show flashes from the immediately preceding action (not a much-later restore).
  if (!data || !data.m || Date.now() - (data.t || 0) > 15000) return;
  setTimeout(function () {
    window.fomsShowToast(data.m);
  }, 150);
}

if (!window.__FOMS_ALPINE_FLASH_BOUND) {
  window.__FOMS_ALPINE_FLASH_BOUND = true;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", fomsConsumeFlashToast);
  } else {
    fomsConsumeFlashToast();
  }
}
