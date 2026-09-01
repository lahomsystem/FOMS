/**
 * 고객 공유 열람 페이지 (Phase A T2) — presigned 만료 표면화 + 도면 일괄 저장 상태 표시.
 *
 * presigned URL 은 5분 수명이라 체류가 길어지면 이미지 fetch 가 403 으로 죽는다.
 * 조용한 깨진 이미지 대신 "새로고침" 안내를 켠다(플랜 T2 zero-silent-failure).
 *
 * ZIP 일괄 저장(/s/<token>/drawings.zip)은 서버가 원본을 다 읽어 압축할 때까지
 * 몇 초가 걸린다. 그 사이 화면이 아무 반응도 안 하면 고객은 버튼을 연타하고,
 * 연타는 서버에서 같은 압축을 여러 번 돌린다 — 눌린 즉시 안내를 켜고 잠근다.
 *
 * 2026-08-31: 폰(카톡 인앱)은 ZIP 을 풀 수 없어 합본 사진(/s/<token>/drawings-sheet.png)
 * 버튼이 주 버튼이다. 그 버튼은 PNG 를 페이지에 띄워 **길게 눌러 저장**할 수 있게 하고
 * (인앱 웹뷰에서 유일하게 확실한 길), 동시에 <a download> 저장도 시도한다.
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
    // 합본 사진은 presign 이 아니라 우리 라우트다 — 실패 사유가 "주소 만료"가 아니라서
    // 여기서 제외하고 자기 안내(data-share-sheet-error)를 쓴다.
    var images = document.querySelectorAll('.foms-share-view img:not([data-share-sheet-img])');
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

  function bindSheetButton() {
    var btn = document.querySelector('[data-share-sheet]');
    if (!btn) return;
    var result = document.querySelector('[data-share-sheet-result]');
    var img = document.querySelector('[data-share-sheet-img]');
    var status = document.querySelector('[data-share-sheet-status]');
    var error = document.querySelector('[data-share-sheet-error]');
    // 마크업이 없으면 손대지 않는다 — 기본 이동(PNG 를 그대로 여는 것)이 폴백이다.
    if (!result || !img) return;
    var busy = false;

    function lock() {
      busy = true;
      btn.classList.add('is-busy');
      btn.setAttribute('aria-busy', 'true');
      btn.textContent = '사진 만드는 중…';
      if (status) status.hidden = false;
      if (error) error.hidden = true;
    }

    function unlock() {
      busy = false;
      btn.classList.remove('is-busy');
      btn.removeAttribute('aria-busy');
      btn.textContent = btn.getAttribute('data-share-sheet-label') || btn.textContent;
      if (status) status.hidden = true;
    }

    function trySaveFile(url) {
      // 되는 브라우저(사파리·크롬)에서는 이걸로 바로 파일이 저장된다. 카톡 인앱은
      // download 를 무시하는데, 그때는 위에 뜬 이미지를 길게 눌러 저장하면 된다.
      var link = document.createElement('a');
      link.href = url + (url.indexOf('?') === -1 ? '?' : '&') + 'download=1';
      link.setAttribute('download', '');
      link.rel = 'noreferrer';
      link.hidden = true;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    btn.setAttribute('data-share-sheet-label', btn.textContent.trim());

    btn.addEventListener('click', function (event) {
      if (busy) {
        event.preventDefault();
        return;
      }
      var url = btn.getAttribute('href');
      if (!url) return;
      event.preventDefault();
      lock();

      img.onload = function () {
        result.hidden = false;
        unlock();
        // 이미지가 확실히 만들어진 뒤에만 저장을 건다 — 503 을 파일로 저장시키지 않는다.
        trySaveFile(url);
        result.scrollIntoView({ behavior: 'smooth', block: 'start' });
      };
      img.onerror = function () {
        // 조용히 죽지 않는다 — 아래 '하나씩 저장'으로 안내한다.
        result.hidden = true;
        unlock();
        if (error) error.hidden = false;
      };
      img.src = url;
    });
  }

  function bindCardSaveIcons() {
    // 아이콘은 카드 <button> 의 **형제**라 지금 배선에서는 lightbox 로 이벤트가
    // 새지 않는다. 그래도 막아 둔다 — 나중에 그리드에 위임 핸들러가 붙으면
    // 저장 한 번에 확대창이 같이 뜨는 회귀가 조용히 생긴다.
    var icons = document.querySelectorAll('[data-share-card-save]');
    Array.prototype.forEach.call(icons, function (icon) {
      icon.addEventListener('click', function (event) {
        event.stopPropagation();
      });
    });
  }

  function bind() {
    bindImages();
    bindZipButton();
    bindSheetButton();
    bindCardSaveIcons();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
