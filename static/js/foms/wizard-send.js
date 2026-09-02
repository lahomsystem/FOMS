/**
 * 모바일 마법사 4단계 — 등록 전 발송 액션 (WIZ-SEND-01 / T4).
 *
 * 실측 PUSH(채널톡 실측방)와 알림톡(실측 예약 안내)을 **주문 등록 전** 초안 상태에서
 * 보낸다. 본문은 서버가 저장된 초안 payload 로 조립하므로(설계 D2 — 클라 텍스트 불신)
 * 화면값이 그대로 나가려면 발송 전에 초안이 서버에 굳어 있어야 한다. 순서를 고정한다.
 *
 *   클릭 → 초안 강제 flush(PUT) → 미리보기 GET → 읽기 전용 시트 확인 → 발송 POST
 *
 * 라우트가 아직 배포되지 않았거나(404) 서버 오류(500)여도 UI 는 상태 한 줄만 바꾸고
 * 계속 동작한다. 전역 안내에 `.alert` 를 쓰지 않는다 — 이 프로젝트의 `.alert` 는 5초 뒤
 * 스스로 사라져 상시 안내로 쓸 수 없다.
 */
(function () {
  "use strict";

  var ENDPOINTS = {
    alimtalk: {
      preview: "/api/erp/order-draft/alimtalk/preview",
      send: "/api/erp/order-draft/alimtalk/send",
      title: "알림톡 · 예약 내역",
    },
    channel: {
      preview: "/api/erp/order-draft/channel-push/preview",
      send: "/api/erp/order-draft/channel-push/send",
      title: "실측 PUSH",
    },
  };

  // 서버 사유 코드 → 사용자 문구. PC 표면(static/js/orders/erp-alimtalk-send.js)의
  // REASON_LABELS 와 미러 관계이며, 초안 전용 코드만 뒤에 덧붙였다.
  var REASON_LABELS = {
    order_not_found: "주문을 찾을 수 없습니다",
    not_configured: "알림톡 서버 설정이 없습니다",
    not_eligible: "실측 일정이 확정되지 않았습니다",
    no_valid_phone: "고객 연락처가 올바르지 않습니다",
    brand_profile_missing: "이 발주사의 알림톡 발신프로필이 아직 등록되지 않았습니다",
    auth: "알림톡 인증 정보가 올바르지 않습니다",
    balance: "알림톡 잔액이 부족합니다",
    template_mismatch: "승인된 템플릿과 본문이 일치하지 않습니다",
    invalid_phone: "수신 번호가 올바르지 않습니다",
    length_exceeded: "본문이 1,000자를 넘었습니다",
    network: "전송 중 네트워크 오류가 발생했습니다",
    draft_not_found: "초안을 찾을 수 없습니다. 새로고침 후 다시 시도해주세요",
    draft_flush_failed: "임시 저장에 실패했습니다. 잠시 후 다시 시도해주세요",
    not_found: "발송 기능이 아직 배포되지 않았습니다",
    server_error: "서버 오류가 발생했습니다",
    forbidden: "발송 권한이 없습니다",
  };

  var TRACE_PREFIX = { alimtalk: "알림톡", channel: "실측 PUSH" };

  var state = {
    kind: null,
    busy: false,
    sendable: false,
    resend: false,
  };

  /**
   * 사유 코드를 사용자 문구로 바꾼다.
   * @param {string} code 서버 사유 코드.
   * @returns {string} 사용자에게 보여줄 한 줄.
   */
  function reasonLabel(code) {
    return REASON_LABELS[code] || String(code || "알 수 없는 오류");
  }

  /**
   * 마법사 루트 엘리먼트.
   * @returns {HTMLElement|null}
   */
  function root() {
    return document.getElementById("foms-wizard-root");
  }

  /**
   * 현재 초안 키.
   * @returns {string} 없으면 빈 문자열.
   */
  function draftKey() {
    var el = root();
    return (el && el.getAttribute("data-draft-key")) || "";
  }

  /**
   * 버튼 아래 상태 한 줄을 갱신한다.
   * @param {string} text 표시 문구(빈 문자열이면 지움).
   * @param {boolean} [isError] 오류 색 적용 여부.
   * @returns {void}
   */
  function setStatus(text, isError) {
    var el = document.getElementById("foms-wizard-send-status");
    if (!el) {
      return;
    }
    el.textContent = text || "";
    el.classList.toggle("is-error", !!isError);
  }

  /**
   * ISO 타임스탬프를 `2026-09-02 14:30` 모양으로 자른다.
   * @param {string} value ISO 문자열.
   * @returns {string} 표시용 문자열.
   */
  function formatStamp(value) {
    return String(value || "").replace("T", " ").slice(0, 16);
  }

  /**
   * 마지막 발송 흔적 한 줄을 그린다.
   * @param {string} kind "alimtalk" | "channel".
   * @param {Object|null} last 발송 이력({sent_at, error}).
   * @returns {void}
   */
  function renderTrace(kind, last) {
    var el = document.querySelector('[data-wizard-send-trace="' + kind + '"]');
    if (!el) {
      return;
    }
    var text = "";
    if (last && last.error) {
      text = TRACE_PREFIX[kind] + " · 마지막 시도 실패 · " + reasonLabel(last.error);
    } else if (last && last.sent_at) {
      text = TRACE_PREFIX[kind] + " · " + formatStamp(last.sent_at) + " 발송됨";
    }
    el.textContent = text;
    el.hidden = !text;
  }

  /**
   * 확인 시트를 연다/닫는다.
   * @param {boolean} open 열림 여부.
   * @returns {void}
   */
  function toggleSheet(open) {
    var sheet = document.getElementById("foms-wizard-send-sheet");
    if (!sheet) {
      return;
    }
    sheet.classList.toggle("is-open", !!open);
    if (!open) {
      state.kind = null;
      state.sendable = false;
      state.resend = false;
    }
  }

  /**
   * 버튼 잠금 상태를 일괄 적용한다(중복 클릭·중복 발송 방지).
   * @param {boolean} locked 잠금 여부.
   * @returns {void}
   */
  function lockButtons(locked) {
    state.busy = !!locked;
    document.querySelectorAll("[data-wizard-send]").forEach(function (btn) {
      btn.disabled = !!locked;
    });
    var confirmBtn = document.getElementById("foms-wizard-send-confirm");
    if (confirmBtn) {
      confirmBtn.disabled = !!locked || !state.sendable;
    }
  }

  /**
   * 응답 규약 `{success, data, error}` 를 안전하게 읽는다.
   * @param {Response} res fetch 응답.
   * @returns {Promise<{status:number, body:Object|null}>}
   */
  function readBody(res) {
    return res
      .json()
      .then(function (body) {
        return { status: res.status, body: body };
      })
      .catch(function () {
        return { status: res.status, body: null };
      });
  }

  /**
   * HTTP 상태에서 사유 코드를 유도한다(라우트 미배포 404, 500 등).
   * @param {number} status HTTP 상태 코드.
   * @param {Object|null} body 응답 본문.
   * @returns {string} 사유 코드.
   */
  function errorCode(status, body) {
    if (body && body.error) {
      return String(body.error);
    }
    if (body && body.data && body.data.error) {
      return String(body.data.error);
    }
    if (status === 404) {
      return "not_found";
    }
    if (status === 403) {
      return "forbidden";
    }
    if (status >= 500) {
      return "server_error";
    }
    return "network";
  }

  /**
   * 현재 폼 상태를 초안 서버에 강제로 굳힌다(디바운스 대기분 포함).
   *
   * 본문은 서버가 저장본으로 조립하므로 flush 실패 시 발송을 진행하면 낡은 내용이
   * 고객에게 나간다 — 실패는 곧 중단이다.
   *
   * @returns {Promise<boolean>} 굳히기 성공 여부.
   */
  function flushDraft() {
    var client = window.fomsWizardDraftClient;
    if (!client || typeof client.flush !== "function") {
      return Promise.resolve(false);
    }
    return client.flush().then(
      function (ok) {
        return !!ok;
      },
      function () {
        return false;
      }
    );
  }

  /**
   * 미리보기 응답으로 시트를 채운다.
   * @param {string} kind "alimtalk" | "channel".
   * @param {Object} data 미리보기 `data` 객체.
   * @returns {void}
   */
  function fillSheet(kind, data) {
    var title = document.getElementById("foms-wizard-send-sheet-title");
    var preview = document.getElementById("foms-wizard-send-sheet-preview");
    var notice = document.getElementById("foms-wizard-send-sheet-notice");
    var meta = document.getElementById("foms-wizard-send-sheet-meta");
    var noteWrap = document.getElementById("foms-wizard-send-sheet-note-wrap");
    var noteInput = document.getElementById("foms-wizard-send-sheet-note");

    if (title) {
      title.textContent = ENDPOINTS[kind].title + " 발송 확인";
    }
    if (preview) {
      preview.textContent = data.text || "";
    }

    var blocked = "";
    if (data.configured === false) {
      blocked = "서버 미설정 — 관리자에게 발송 설정을 요청해주세요.";
    } else if (kind === "alimtalk" && data.eligible === false) {
      blocked = "발송 불가 — " + reasonLabel(data.ineligible_reason);
    } else if (!data.text) {
      blocked = "발송 불가 — 보낼 본문이 비어 있습니다.";
    }

    var last = data.last || null;
    renderTrace(kind, last);
    state.resend = !!(last && (last.sent_at || last.error));

    var metaParts = [];
    if (kind === "channel") {
      metaParts.push("첨부 " + (parseInt(data.files_count, 10) || 0) + "건");
    }
    if (!blocked && state.resend) {
      metaParts.push("이미 발송 이력이 있습니다. 확인하면 다시 발송됩니다.");
    }
    if (meta) {
      meta.textContent = metaParts.join(" · ");
      meta.hidden = metaParts.length === 0;
    }
    if (notice) {
      notice.textContent = blocked;
      notice.hidden = !blocked;
    }
    if (noteWrap) {
      noteWrap.hidden = !(kind === "channel" && state.resend && !blocked);
    }
    if (noteInput && noteWrap && noteWrap.hidden) {
      noteInput.value = "";
    }

    state.sendable = !blocked;
    var confirmBtn = document.getElementById("foms-wizard-send-confirm");
    if (confirmBtn) {
      confirmBtn.disabled = !state.sendable;
    }
  }

  /**
   * 버튼 진입점 — flush → 미리보기 → 시트.
   * @param {string} kind "alimtalk" | "channel".
   * @returns {Promise<void>}
   */
  function openPreview(kind) {
    var conf = ENDPOINTS[kind];
    var key = draftKey();
    if (!conf || !key) {
      setStatus(reasonLabel("draft_not_found"), true);
      return Promise.resolve();
    }
    lockButtons(true);
    setStatus("임시 저장 중…");
    return flushDraft()
      .then(function (ok) {
        if (!ok) {
          setStatus(reasonLabel("draft_flush_failed"), true);
          return null;
        }
        setStatus("미리보기 불러오는 중…");
        return fetch(conf.preview + "?draft_key=" + encodeURIComponent(key), {
          credentials: "same-origin",
        }).then(readBody);
      })
      .then(function (result) {
        if (!result) {
          return;
        }
        var body = result.body;
        if (!body || body.success !== true || !body.data) {
          setStatus("미리보기 실패 · " + reasonLabel(errorCode(result.status, body)), true);
          return;
        }
        setStatus("");
        state.kind = kind;
        fillSheet(kind, body.data);
        toggleSheet(true);
      })
      .catch(function () {
        setStatus("미리보기 실패 · " + reasonLabel("network"), true);
      })
      .then(function () {
        lockButtons(false);
      });
  }

  /**
   * 시트 확인 → 실제 발송 POST.
   * @returns {Promise<void>}
   */
  function confirmSend() {
    var kind = state.kind;
    var conf = kind ? ENDPOINTS[kind] : null;
    var key = draftKey();
    if (!conf || !key || !state.sendable) {
      return Promise.resolve();
    }
    var payload = { draft_key: key };
    var noteInput = document.getElementById("foms-wizard-send-sheet-note");
    var noteWrap = document.getElementById("foms-wizard-send-sheet-note-wrap");
    if (kind === "channel" && noteWrap && !noteWrap.hidden && noteInput && noteInput.value.trim()) {
      payload.change_note = noteInput.value.trim();
    }
    lockButtons(true);
    setStatus(conf.title + " 발송 중…");
    return fetch(conf.send, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(readBody)
      .then(function (result) {
        var body = result.body;
        var data = (body && body.data) || null;
        if (data && data.last) {
          renderTrace(kind, data.last);
        }
        if (body && body.success === true && data && data.sent) {
          if (!data.last) {
            renderTrace(kind, { sent_at: new Date().toISOString() });
          }
          setStatus(conf.title + " 발송 완료");
          toggleSheet(false);
          return;
        }
        var label = reasonLabel(errorCode(result.status, body));
        setStatus(conf.title + " 발송 실패 · " + label, true);
        var notice = document.getElementById("foms-wizard-send-sheet-notice");
        if (notice) {
          notice.textContent = "발송 실패 — " + label;
          notice.hidden = false;
        }
      })
      .catch(function () {
        var label = reasonLabel("network");
        setStatus(conf.title + " 발송 실패 · " + label, true);
      })
      .then(function () {
        lockButtons(false);
      });
  }

  /**
   * 클릭 위임 바인딩(싱글톤).
   * @returns {void}
   */
  function bind() {
    if (window.__FOMS_WIZARD_SEND_BOUND) {
      return;
    }
    window.__FOMS_WIZARD_SEND_BOUND = true;

    document.addEventListener("click", function (ev) {
      var target = ev.target;
      if (!target || typeof target.closest !== "function") {
        return;
      }
      var trigger = target.closest("[data-wizard-send]");
      if (trigger) {
        ev.preventDefault();
        if (state.busy) {
          return;
        }
        void openPreview(trigger.getAttribute("data-wizard-send"));
        return;
      }
      if (target.closest("[data-wizard-send-close]")) {
        ev.preventDefault();
        if (state.busy) {
          return;
        }
        toggleSheet(false);
        return;
      }
      if (target.closest("#foms-wizard-send-confirm")) {
        ev.preventDefault();
        if (state.busy) {
          return;
        }
        void confirmSend();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }

  window.FomsWizardSendReasonLabel = reasonLabel;
})();
