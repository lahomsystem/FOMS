/**
 * 고객 공유 열람 페이지 (Phase A T2) — presigned 만료 표면화.
 *
 * presigned URL 은 5분 수명이라 체류가 길어지면 이미지 fetch 가 403 으로 죽는다.
 * 조용한 깨진 이미지 대신 "새로고침" 안내를 켠다(플랜 T2 zero-silent-failure).
 */
(function () {
  'use strict';

  function showExpiryNote() {
    var note = document.querySelector('[data-share-expiry-note]');
    if (note) note.hidden = false;
  }

  function bind() {
    var images = document.querySelectorAll('.foms-share-view img');
    Array.prototype.forEach.call(images, function (img) {
      img.addEventListener('error', showExpiryNote);
      // 이미 실패해 캐시된 broken 상태(방문 복귀)도 잡는다.
      if (img.complete && img.naturalWidth === 0 && img.src) showExpiryNote();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
