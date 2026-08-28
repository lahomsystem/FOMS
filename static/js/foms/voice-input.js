/**
 * P2-05 Web Speech API — search + wizard memo fields (ko-KR).
 *
 * mode:
 *   "append"          검색 오버레이 등: 기존 값 뒤에 인식 결과를 덧붙임(무확인).
 *   "confirm-replace" wizard 입력칸: 인식 결과를 확인받은 뒤 기존 값('상담' 등)을
 *                     모두 지우고 덮어씀. 마이크는 입력칸 우측 내부에 배치.
 */
(function () {
  "use strict";

  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  function resolveWrap(input, mode) {
    if (mode === "confirm-replace") {
      // wizard: 입력칸만 감싸 우측 내부에 마이크를 배치(필드 grid에 별도 줄로 빠지지 않도록).
      var existing = input.closest(".foms-voice-wrap");
      if (existing) return existing;
      var wrap = document.createElement("span");
      wrap.className = "foms-voice-wrap";
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);
      input.classList.add("foms-voice-has-btn");
      return wrap;
    }
    return input.closest(".foms-search-overlay__input-wrap") || input.parentElement;
  }

  function attachMic(input, mode) {
    if (!input || input.dataset.fomsVoiceBound) return;
    input.dataset.fomsVoiceBound = "1";
    var wrap = resolveWrap(input, mode);
    if (!wrap) return;
    wrap.style.position = "relative";

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "foms-voice-btn";
    btn.setAttribute("aria-label", "음성 입력");
    btn.innerHTML = '<i class="fas fa-microphone" aria-hidden="true"></i>';
    wrap.appendChild(btn);

    var rec = new SpeechRecognition();
    rec.lang = "ko-KR";
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    btn.addEventListener("click", function () {
      try {
        rec.start();
        btn.classList.add("is-active");
        if (window.fomsHapticTap) window.fomsHapticTap();
      } catch (e) {
        if (window.fomsShowToast) window.fomsShowToast("음성 입력을 시작할 수 없습니다");
      }
    });

    rec.addEventListener("result", function (ev) {
      var text = ev.results[0] && ev.results[0][0] ? ev.results[0][0].transcript : "";
      text = (text || "").trim();
      if (!text) return;
      if (mode === "confirm-replace") {
        // 인식 결과를 확인받은 뒤에만 입력. 확인 시 기존 값('상담' 등)을 모두 지우고 덮어쓴다.
        var ok = window.confirm('"' + text + '"\n\n이 내용을 입력할까요?\n(기존 입력 내용은 지워집니다)');
        if (!ok) return;
        input.value = text;
      } else {
        input.value = (input.value ? input.value + " " : "") + text;
      }
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    rec.addEventListener("end", function () {
      btn.classList.remove("is-active");
    });

    rec.addEventListener("error", function () {
      btn.classList.remove("is-active");
      if (window.fomsShowToast) window.fomsShowToast("음성 인식 실패");
    });
  }

  // wizard 입력칸(메모류 textarea + text input)에 확인-덮어쓰기 마이크 부착.
  // 동적으로 추가된 제품 카드(scope=클론)에도 재호출 가능.
  function isWizardVoiceTarget(el) {
    if (!el) return false;
    // 명시적 opt-out(금액칸 등 숫자 전용): data-foms-no-voice.
    if (el.hasAttribute("data-foms-no-voice")) return false;
    if (el.tagName === "TEXTAREA") return true;
    if (el.tagName !== "INPUT") return false;
    // 숨김 입력(콤보 '직접입력' custom 등) 제외 — 숨겨진 칸에 마이크만 떠다니는 것 방지.
    if (el.hidden) return false;
    // 자유 입력칸 전체(텍스트 + 숫자 inputmode 포함; type 미지정 input은 'text').
    // date/tel/checkbox 등 네이티브 컨트롤은 제외.
    var type = (el.getAttribute("type") || "text").toLowerCase();
    return type === "text" || type === "search";
  }

  function attachWizard(scope) {
    if (!scope) return;
    scope.querySelectorAll("textarea, input").forEach(function (el) {
      if (isWizardVoiceTarget(el)) attachMic(el, "confirm-replace");
    });
  }

  function init() {
    attachMic(document.getElementById("foms-search-input"), "append");
    attachWizard(document.getElementById("foms-wizard-root"));
  }

  window.FomsVoiceInput = { attachWizard: attachWizard };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
