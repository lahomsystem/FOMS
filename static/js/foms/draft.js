/**
 * OrderDraft autosave client (P1-03).
 * debounce 1000ms + blur + sendBeacon on unload + 5min idle safety.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 1000;
  var IDLE_MS = 5 * 60 * 1000;
  var API_BASE = "/api/erp/order-draft";

  function emptyPayload(step) {
    return {
      schema_version: 1,
      step: step || 1,
      data: {},
    };
  }

  function FomsDraftClient(root, options) {
    this.root = root;
    this.draftKey = root.getAttribute("data-draft-key") || "";
    this.getPayload = options.getPayload;
    this.getStep = options.getStep;
    this.onConflict = options.onConflict;
    this.onRecovered = options.onRecovered;
    this.updatedAt = null;
    this._debounceTimer = null;
    this._idleTimer = null;
    this._pendingPayload = null;
    this._boundFlush = this.flush.bind(this);
  }

  FomsDraftClient.prototype._headers = function (json) {
    var headers = { "Content-Type": "application/json" };
    if (this.updatedAt) {
      headers["X-If-Match"] = this.updatedAt;
    }
    return headers;
  };

  FomsDraftClient.prototype.load = function () {
    var self = this;
    if (!self.draftKey) {
      return Promise.resolve(null);
    }
    return fetch(API_BASE + "?key=" + encodeURIComponent(self.draftKey), {
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        if (!body || !body.success) {
          return null;
        }
        if (!body.draft) {
          return null;
        }
        self.updatedAt = body.draft.updated_at || null;
        return body.draft;
      })
      .catch(function () {
        return null;
      });
  };

  FomsDraftClient.prototype._body = function () {
    return {
      draft_key: this.draftKey,
      step: this.getStep(),
      payload: this.getPayload(),
    };
  };

  FomsDraftClient.prototype.flush = function () {
    var self = this;
    if (!self.draftKey) {
      return Promise.resolve(false);
    }
    var body = self._body();
    self._pendingPayload = null;
    return fetch(API_BASE, {
      method: "PUT",
      credentials: "same-origin",
      headers: self._headers(true),
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { status: res.status, data: data };
        });
      })
      .then(function (result) {
        if (result.status === 409 && self.onConflict) {
          self.onConflict(result.data.current);
          return false;
        }
        if (result.data && result.data.success) {
          self.updatedAt = result.data.updated_at || self.updatedAt;
          self._showAutosave();
          return true;
        }
        return false;
      })
      .catch(function () {
        return false;
      });
  };

  FomsDraftClient.prototype.scheduleSave = function () {
    var self = this;
    self._pendingPayload = self._body();
    if (self._debounceTimer) {
      clearTimeout(self._debounceTimer);
    }
    self._debounceTimer = setTimeout(function () {
      self.flush();
    }, DEBOUNCE_MS);
    self._resetIdle();
  };

  FomsDraftClient.prototype._resetIdle = function () {
    var self = this;
    if (self._idleTimer) {
      clearTimeout(self._idleTimer);
    }
    self._idleTimer = setTimeout(function () {
      self.flush();
    }, IDLE_MS);
  };

  FomsDraftClient.prototype._showAutosave = function () {
    var el = document.getElementById("foms-wizard-autosave");
    if (!el) {
      return;
    }
    el.classList.add("is-visible");
    setTimeout(function () {
      el.classList.remove("is-visible");
    }, 2500);
  };

  FomsDraftClient.prototype.bindAutosave = function () {
    var self = this;
    var fields = self.root.querySelectorAll("[data-wizard-field]");
    fields.forEach(function (field) {
      field.addEventListener("input", function () {
        self.scheduleSave();
      });
      field.addEventListener("blur", function () {
        if (self._debounceTimer) {
          clearTimeout(self._debounceTimer);
        }
        self.flush();
      });
    });
    window.addEventListener("beforeunload", function () {
      if (!self.draftKey) {
        return;
      }
      try {
        fetch(API_BASE, {
          method: "PUT",
          credentials: "same-origin",
          headers: self._headers(true),
          body: JSON.stringify(self._body()),
          keepalive: true,
        });
      } catch (_e) {
        /* keepalive optional */
      }
    });
  };

  FomsDraftClient.prototype.deleteDraft = function () {
    if (!this.draftKey) {
      return Promise.resolve(true);
    }
    return fetch(API_BASE + "?key=" + encodeURIComponent(this.draftKey), {
      method: "DELETE",
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        return !!(body && body.success);
      })
      .catch(function () {
        return false;
      });
  };

  FomsDraftClient.prototype.submitOrder = function () {
    return fetch(API_BASE + "/submit", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_key: this.draftKey, payload: this.getPayload() }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { status: res.status, data: data };
        });
      });
  };

  FomsDraftClient.prototype.applyRemote = function (remote) {
    if (!remote) {
      return;
    }
    this.updatedAt = remote.updated_at || null;
    if (this.onRecovered) {
      this.onRecovered(remote);
    }
  };

  window.FomsDraftClient = FomsDraftClient;
  window.FomsDraftEmptyPayload = emptyPayload;
})();
