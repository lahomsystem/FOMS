/**
 * P2-05 Web Speech API — search + wizard memo fields (ko-KR).
 */
(function () {
  "use strict";

  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  function attachMic(input) {
    if (!input || input.dataset.fomsVoiceBound) return;
    input.dataset.fomsVoiceBound = "1";
    var wrap = input.closest(".foms-search-overlay__input-wrap") || input.parentElement;
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
      if (text) {
        input.value = (input.value ? input.value + " " : "") + text.trim();
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });

    rec.addEventListener("end", function () {
      btn.classList.remove("is-active");
    });

    rec.addEventListener("error", function () {
      btn.classList.remove("is-active");
      if (window.fomsShowToast) window.fomsShowToast("음성 인식 실패");
    });
  }

  function init() {
    attachMic(document.getElementById("foms-search-input"));
    document.querySelectorAll("#foms-wizard-root textarea, #foms-wizard-root input[type='text']").forEach(attachMic);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
