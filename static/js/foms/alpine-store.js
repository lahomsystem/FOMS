/**
 * P2-02 Alpine store: toast + modal helpers for new FOMS surfaces.
 */
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
