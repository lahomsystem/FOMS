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
    this._saving = false;
    this._flushPromise = null;
    this._queuedFlush = false;
    this._lastKeepaliveAt = 0;
    // 제출 성공 뒤에는 서버에서 초안 행이 지워진다. 그런데 이탈 시점 keepalive 저장은
    // 리스너로 계속 걸려 있어서, 등록 직후 페이지 이동의 pagehide 가 PUT 을 한 번 더
    // 쏘고 upsert 가 그 초안을 되살린다(등록될 때마다 유령 초안 1건). 제출 성공을
    // 표시해 이후 저장 경로를 전부 닫는다.
    this._submitted = false;
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

  FomsDraftClient.prototype.flush = function (options) {
    var self = this;
    var opts = options || {};
    if (!self.draftKey || self._submitted) {
      return Promise.resolve(false);
    }
    if (self._saving) {
      self._queuedFlush = true;
      return self._flushPromise || Promise.resolve(false);
    }
    self._saving = true;
    var body = self._body();
    self._pendingPayload = null;
    function release(ok) {
      self._saving = false;
      var again = self._queuedFlush;
      self._queuedFlush = false;
      self._flushPromise = null;
      if (again) {
        return self.flush(opts);
      }
      return ok;
    }
    self._flushPromise = fetch(API_BASE, {
      method: "PUT",
      credentials: "same-origin",
      keepalive: !!opts.keepalive,
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
        if (window.fomsOfflineEnqueueRequest) {
          return window.fomsOfflineEnqueueRequest(API_BASE, {
            method: "PUT",
            headers: self._headers(true),
            body: JSON.stringify(body),
          }).then(function () {
            self._showAutosave();
            return true;
          });
        }
        return false;
      })
      .then(release, function (err) {
        return release(false).then(function () {
          throw err;
        });
      });
    return self._flushPromise;
  };

  FomsDraftClient.prototype.scheduleSave = function () {
    var self = this;
    if (self._submitted) {
      return;
    }
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
    // iOS Safari 는 앱 전환·홈버튼 이탈에서 beforeunload 를 신뢰성 있게 쏘지 않는다.
    // pagehide + visibilitychange(hidden) 를 함께 걸어 디바운스 대기 중인 입력을 지킨다.
    function keepaliveSave() {
      var now = Date.now();
      if (self._lastKeepaliveAt && now - self._lastKeepaliveAt < 250) {
        return;
      }
      self._lastKeepaliveAt = now;
      if (!self.draftKey || self._submitted) {
        return;
      }
      if (self._debounceTimer) {
        clearTimeout(self._debounceTimer);
        self._debounceTimer = null;
      }
      var payload = JSON.stringify(self._body());
      var req = {
        method: "PUT",
        credentials: "same-origin",
        headers: self._headers(true),
        body: payload,
      };
      if (!navigator.onLine && window.fomsOfflineEnqueueRequest) {
        window.fomsOfflineEnqueueRequest(API_BASE, req);
        return;
      }
      if (self._saving) {
        // In-flight PUT may be aborted on iOS hide — one extra keepalive.
        // Server UniqueViolation path absorbs the overlap.
        try {
          fetch(API_BASE, Object.assign({ keepalive: true }, req));
        } catch (_e) {
          /* keepalive optional */
        }
        return;
      }
      self.flush({ keepalive: true });
    }
    window.addEventListener("beforeunload", keepaliveSave);
    window.addEventListener("pagehide", keepaliveSave);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        keepaliveSave();
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

  /** 제출 성공 뒤 남은 저장 예약을 끄고 이후 저장 경로를 닫는다(유령 초안 방지). */
  FomsDraftClient.prototype._markSubmitted = function () {
    this._submitted = true;
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
      this._debounceTimer = null;
    }
    if (this._idleTimer) {
      clearTimeout(this._idleTimer);
      this._idleTimer = null;
    }
    this._pendingPayload = null;
    this._queuedFlush = false;
  };

  FomsDraftClient.prototype.submitOrder = function () {
    var self = this;
    return fetch(API_BASE + "/submit", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_key: this.draftKey, payload: this.getPayload() }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          // 성공하면 서버가 초안 행을 지운 상태다. 여기서 저장을 끄지 않으면 이어지는
          // 페이지 이동의 pagehide keepalive 가 같은 키로 PUT 을 쏴 초안을 되살린다.
          if (res.ok && data && data.success) {
            self._markSubmitted();
          }
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
