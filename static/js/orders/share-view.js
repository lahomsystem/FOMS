/**
 * 고객 공유 열람 페이지 (Phase A T2) — presigned 만료 표면화 + 도면 일괄 저장 상태 표시.
 *
 * presigned URL 은 5분 수명이라 체류가 길어지면 이미지 fetch 가 403 으로 죽는다.
 * 조용한 깨진 이미지 대신 "새로고침" 안내를 켠다(플랜 T2 zero-silent-failure).
 *
 * ZIP 일괄 저장(/s/<token>/drawings.zip)은 서버가 원본을 다 읽어 압축할 때까지
 * 몇 초가 걸린다. 그 사이 화면이 아무 반응도 안 하면 고객은 버튼을 연타하고,
 * 연타는 서버에서 같은 압축을 여러 번 돌린다 — 눌린 즉시 안내를 켜고 잠근다.
 */
(function () {
  'use strict';

  /** ZIP 요청 잠금 해제까지(ms). 다운로드 시작 시점을 브라우저가 알려주지 않아 시간으로 푼다. */
  var ZIP_BUSY_MS = 8000;

  function showExpiryNote() {
    var note = document.querySelector('[data-share-expiry-note]');
    if (note) note.hidden = false;
  }

  function bindImages() {
    var images = document.querySelectorAll('.foms-share-view img');
    Array.prototype.forEach.call(images, function (img) {
      img.addEventListener('error', showExpiryNote);
      // 이미 실패해 캐시된 broken 상태(방문 복귀)도 잡는다.
      if (img.complete && img.naturalWidth === 0 && img.src) showExpiryNote();
    });
  }

  function bindZipButton() {
    var btn = document.querySelector('[data-share-zip]');
    if (!btn) return;
    var status = document.querySelector('[data-share-zip-status]');
    var busy = false;
    var timer = null;

    function release() {
      busy = false;
      timer = null;
      btn.classList.remove('is-busy');
      btn.removeAttribute('aria-busy');
      if (status) status.hidden = true;
    }

    btn.addEventListener('click', function (event) {
      if (busy) {
        // 중복 클릭 차단 — 같은 압축을 서버에서 두 번 돌리지 않는다.
        event.preventDefault();
        return;
      }
      busy = true;
      btn.classList.add('is-busy');
      btn.setAttribute('aria-busy', 'true');
      if (status) status.hidden = false;
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(release, ZIP_BUSY_MS);
    });

    // 다운로드가 시작되면 페이지는 그대로 남지만 탭이 잠깐 백그라운드가 되기도 한다.
    // 돌아왔을 때 "준비 중" 이 남아 있지 않게 정리한다.
    window.addEventListener('pageshow', function () {
      if (busy) release();
    });
  }

  function bind() {
    bindImages();
    bindZipButton();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
