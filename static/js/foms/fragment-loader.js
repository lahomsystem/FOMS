/**
 * FOMS 공용 fragment 로더 (W12 추출) — 사이드 시트(W10) · 실측 split(W12) 공유 SSOT.
 *
 * window.FomsFragmentLoader.load(container, url, options) 하나로:
 *   - 컨테이너에 로딩 스피너 주입 → url fetch(same-origin) → 성공 시 innerHTML 교체
 *     + <script> 재실행(activateScripts: type/id/nonce/src/async/defer/crossOrigin/
 *     integrity/textContent 보존 — application/json 프리로드 블록이 클래식 스크립트로
 *     실행돼 SyntaxError 나는 것 방지) → foms:main-content-swapped /
 *     foms:erp-shell-fragment-swapped 디스패치(호스트 재바인딩) → scrollTop=0.
 *   - 실패 시 console.error(무음 금지) + "다시 시도" 버튼(같은 인자로 load 재호출).
 *   - 컨테이너별 staleness 토큰(__fomsFragmentToken)으로 빠른 연속 로드 시 옛 응답 폐기.
 *
 * idempotent: 이미 정의돼 있으면 재정의하지 않는다. 전역 listener 없음(네임스페이스만),
 * 로드 시 side-effect 없음(perf G4).
 */
(function () {
  "use strict";

  if (window.FomsFragmentLoader) return;

  // runtime/erp-shell.js activateScripts 정책 모방: innerHTML 로 주입된 <script>는 실행되지
  // 않으므로 새 노드로 교체해 재실행한다. type 보존(application/json 데이터 블록 보호).
  function activateScripts(container) {
    var nodes = container.querySelectorAll("script");
    Array.prototype.forEach.call(nodes, function (old) {
      var s = document.createElement("script");
      if (old.id) s.id = old.id;
      if (old.type) s.type = old.type;
      if (old.nonce) s.nonce = old.nonce;
      if (old.src) {
        s.src = old.src;
        s.async = old.async;
        s.defer = old.defer;
        if (old.crossOrigin) s.crossOrigin = old.crossOrigin;
        if (old.integrity) s.integrity = old.integrity;
      } else {
        s.textContent = old.textContent;
      }
      old.parentNode.replaceChild(s, old);
    });
  }

  function renderLoading(container, text) {
    container.innerHTML =
      '<div class="foms-fragment-state" role="status">' +
      '<span class="foms-fragment-spinner foms-tablet-sheet__spinner" aria-hidden="true"></span>' +
      "<span>" +
      (text || "불러오는 중…") +
      "</span>" +
      "</div>";
  }

  function renderError(container, url, options) {
    container.innerHTML =
      '<div class="foms-fragment-state foms-fragment-state--error" role="alert">' +
      "<p>내용을 불러오지 못했습니다.</p>" +
      '<button type="button" class="foms-fragment-retry foms-tablet-sheet__retry">다시 시도</button>' +
      "</div>";
    var retry = container.querySelector(".foms-fragment-retry");
    if (retry) {
      retry.addEventListener("click", function () {
        load(container, url, options);
      });
    }
  }

  function load(container, url, options) {
    if (!container || !url) return;
    options = options || {};

    // 컨테이너별 staleness 토큰: 매 호출 증가 → resolve 시점에 바뀌었으면 옛 응답 폐기.
    var token = (container.__fomsFragmentToken || 0) + 1;
    container.__fomsFragmentToken = token;

    renderLoading(container, options.loadingText);

    fetch(url, {
      credentials: "same-origin",
      headers: {
        "X-Requested-With": options.requestedWith || "foms-fragment-loader",
      },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("fragment HTTP " + res.status);
        return res.text();
      })
      .then(function (html) {
        if (container.__fomsFragmentToken !== token) return; // 더 최신 로드가 있으면 폐기
        container.innerHTML = html;
        activateScripts(container);
        try {
          document.dispatchEvent(
            new CustomEvent("foms:main-content-swapped", {
              detail: { source: options.source, url: url },
            })
          );
          document.dispatchEvent(
            new CustomEvent("foms:erp-shell-fragment-swapped", {
              detail: { source: options.source, url: url },
            })
          );
        } catch (e) {
          /* CustomEvent 미지원 환경 무시 */
        }
        container.scrollTop = 0;
      })
      .catch(function (err) {
        if (container.__fomsFragmentToken !== token) return;
        console.error("[foms-fragment-loader] load failed:", err);
        renderError(container, url, options);
      });
  }

  window.FomsFragmentLoader = { load: load };
})();
