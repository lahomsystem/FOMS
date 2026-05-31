/**
 * P2-02 Alpine store: toast + modal helpers for new FOMS surfaces.
 */
// #region agent log
fetch("http://127.0.0.1:7309/ingest/2d47bfab-a311-4a20-bcce-343e7171cc9a", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "f2330d" },
  body: JSON.stringify({
    sessionId: "f2330d",
    runId: "pre-fix",
    hypothesisId: "A",
    location: "alpine-store.js:load",
    message: "alpine-store.js parsed",
    data: { hasAlpine: !!window.Alpine },
    timestamp: Date.now(),
  }),
}).catch(function () {});
// #endregion
document.addEventListener("alpine:init", function () {
  // #region agent log
  fetch("http://127.0.0.1:7309/ingest/2d47bfab-a311-4a20-bcce-343e7171cc9a", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "f2330d" },
    body: JSON.stringify({
      sessionId: "f2330d",
      runId: "pre-fix",
      hypothesisId: "A",
      location: "alpine-store.js:alpine:init",
      message: "fomsToast store registering",
      data: {},
      timestamp: Date.now(),
    }),
  }).catch(function () {});
  // #endregion
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
