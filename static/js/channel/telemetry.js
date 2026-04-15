(function initWAMTelemetry(window, document) {
  if (window.WAMTelemetry) {
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

  function send(eventName, payload) {
    var bootstrap = parseBootstrap();
    var flags = (bootstrap && bootstrap.flags) || {};
    var api = (bootstrap && bootstrap.api) || {};
    if (!flags.telemetry_enabled || !api.telemetry_url) {
      return;
    }

    var body = JSON.stringify({
      event_name: eventName,
      view_key: (bootstrap && bootstrap.view_key) || "order-detail",
      page_state: bootstrap && bootstrap.page ? bootstrap.page.page_state : null,
      section_count: payload && payload.section_count,
      attachment_count: payload && payload.attachment_count,
      latency_ms: payload && payload.latency_ms,
      key: payload && payload.key
    });

    try {
      if (window.navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        window.navigator.sendBeacon(api.telemetry_url, blob);
        return;
      }
    } catch (error) {
      // Fail open: telemetry must never break the page.
    }

    try {
      fetch(api.telemetry_url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json"
        },
        body: body,
        keepalive: true
      }).catch(function noop() {});
    } catch (error) {
      // Fail open: ignore telemetry transport failures.
    }
  }

  function emit(eventName, payload) {
    try {
      window.dispatchEvent(new CustomEvent("wam:telemetry", {
        detail: {
          eventName: eventName,
          payload: payload || {},
          at: Date.now()
        }
      }));
    } catch (error) {
      return;
    }

    send(eventName, payload || {});
  }

  window.WAMTelemetry = {
    emit: emit
  };
})(window, document);
