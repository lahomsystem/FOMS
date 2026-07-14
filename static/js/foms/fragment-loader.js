/**
 * FOMS 공용 fragment 로더 (W12 추출) — 사이드 시트(W10) · 실측 split(W12) 공유 SSOT.
 *
 * window.FomsFragmentLoader.load(container, url, options) 하나로:
 *   - 컨테이너에 로딩 스피너 주입 → url fetch(same-origin) → 성공 시 innerHTML 교체
 *     + <script> 재실행(activateScripts: type/id/nonce/src/async/defer/crossOrigin/
 *     integrity/textContent 보존 — application/json 프리로드 블록이 클래식 스크립트로
 *     실행돼 SyntaxError 나는 것 방지).
 *   - src 스크립트는 **1회만 실행(dedupe)**: erp-order 모듈(~12 src)은 singleton 가드 +
 *     foms:main-content-swapped 이벤트로 재init 하므로, 매 fragment 로드마다 재로딩할
 *     필요가 없다(defect 4 — src 누적 방지). 인라인 스크립트는 매 로드 재실행(주문별 데이터
 *     주입 + swap 이벤트 발화).
 *   - foms:main-content-swapped 는 **fragment 인라인 <script>가 SSOT**로 발화한다
 *     (HTMX split flow에도 그 인라인이 필요 — activateScripts 재실행으로 로더 경유도 커버).
 *     로더는 이를 중복 발화하지 않고(defect 5), 인라인이 발화하지 않는
 *     foms:erp-shell-fragment-swapped 만 발화한다(호스트 재바인딩) → scrollTop=0.
 *   - 실패 시 console.error(무음 금지) + "다시 시도" 버튼(같은 인자로 load 재호출).
 *   - 컨테이너별 staleness 토큰(__fomsFragmentToken)으로 빠른 연속 로드 시 옛 응답 폐기.
 *
 * idempotent: 이미 정의돼 있으면 재정의하지 않는다. 전역 listener 없음(네임스페이스만),
 * 로드 시 side-effect 없음(perf G4).
 */
(function () {
  "use strict";

  if (window.FomsFragmentLoader) return;

  // src 기준 1회 실행 레지스트리(페이지 수명 유지). 컨테이너 innerHTML 교체로 옛 <script>
  // 노드가 사라져도 여기 기록은 남아 재로딩을 막는다(defect 4).
  var activatedFragmentSrc = Object.create(null);

  // 동일 src 스크립트가 이미 살아있는지(=1회 실행됨). 레지스트리 우선, 없으면 컨테이너 밖
  // document 를 확인(베이스 페이지가 전역 로드한 경우). 컨테이너 내부의 inert(innerHTML로
  // 삽입돼 미실행) 노드는 자기 자신을 오탐하지 않도록 제외한다.
  function srcAlreadyLive(src, container) {
    if (activatedFragmentSrc[src]) return true;
    var scripts = document.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      var node = scripts[i];
      if (node.src === src && !container.contains(node)) return true;
    }
    return false;
  }

  // runtime/erp-shell.js activateScripts 정책 모방: innerHTML 로 주입된 <script>는 실행되지
  // 않으므로 새 노드로 교체해 재실행한다. type 보존(application/json 데이터 블록 보호).
  //   - src 스크립트: 1회만 실행(dedupe). 이미 실행됐으면 inert 노드만 제거하고 skip.
  //     erp-order 모듈은 singleton 가드 + main-content-swapped 재init 이라 재로딩=낭비(defect 4).
  //   - 인라인 스크립트(no src): 매 로드 재실행 — (1) 주문별 데이터 주입,
  //     (2) main-content-swapped 발화로 로드된 모듈 재init. application/json 등 비실행
  //     데이터 블록은 type 보존 → 브라우저가 실행하지 않으므로 재생성해도 무해.
  function activateScripts(container) {
    var nodes = container.querySelectorAll("script");
    Array.prototype.forEach.call(nodes, function (old) {
      if (old.src) {
        var src = old.src; // resolved absolute URL(?v 포함) — 버전 다르면 별개 취급.
        if (srcAlreadyLive(src, container)) {
          if (old.parentNode) old.parentNode.removeChild(old);
          return;
        }
        activatedFragmentSrc[src] = true;
        var s = document.createElement("script");
        if (old.id) s.id = old.id;
        if (old.type) s.type = old.type;
        if (old.nonce) s.nonce = old.nonce;
        s.src = src;
        s.async = old.async;
        s.defer = old.defer;
        if (old.crossOrigin) s.crossOrigin = old.crossOrigin;
        if (old.integrity) s.integrity = old.integrity;
        old.parentNode.replaceChild(s, old);
        return;
      }
      var inline = document.createElement("script");
      if (old.id) inline.id = old.id;
      if (old.type) inline.type = old.type;
      if (old.nonce) inline.nonce = old.nonce;
      inline.textContent = old.textContent;
      old.parentNode.replaceChild(inline, old);
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
        // activateScripts 가 fragment 인라인 <script>를 재실행하며, 그 안에서
        // foms:main-content-swapped 가 발화된다(SSOT — 로더는 중복 발화하지 않음, defect 5).
        activateScripts(container);
        try {
          // 인라인이 발화하지 않는 erp-shell 재바인딩 이벤트만 로더가 발화한다.
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
