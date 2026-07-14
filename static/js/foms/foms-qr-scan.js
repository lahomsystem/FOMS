/**
 * B4 QR 스캔 — v2 통합검색 오버레이 진입.
 *
 * 네이티브 BarcodeDetector 만 사용(외부 CDN 없음 → G2 정합). 스크립트는 defer 로
 * 로드되지만 카메라(getUserMedia)는 진입 버튼 클릭 시에만 시작한다(lazy).
 * BarcodeDetector 미지원 브라우저는 진입 버튼을 숨긴 채 즉시 종료한다.
 * 결과: same-origin /erp/* URL → 이동, 순수 숫자 → /erp/orders/<n>/mobile, 그 외 무시+안내.
 * G4: window.__FOMS_QR_SCAN_BOUND 싱글톤 가드 + document 위임(fragment 재실행 안전).
 */
(function () {
  'use strict';

  if (!('BarcodeDetector' in window) || !navigator.mediaDevices) {
    return; // 미지원: 진입 버튼은 [hidden] 상태로 유지.
  }
  if (window.__FOMS_QR_SCAN_BOUND) {
    return;
  }
  window.__FOMS_QR_SCAN_BOUND = true;

  var OVERLAY_ID = 'foms-qr-scan-overlay';
  var DEFAULT_HINT = 'QR 코드를 사각형 안에 맞춰 주세요.';
  var stream = null;
  var rafId = 0;
  var detector = null;
  var scanning = false;

  function revealTriggers() {
    var btns = document.querySelectorAll('[data-foms-qr-scan-open]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].hidden = false;
    }
  }

  function buildOverlay() {
    var overlay = document.getElementById(OVERLAY_ID);
    if (overlay) {
      return overlay;
    }
    overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.className = 'foms-qr-scan';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', 'QR 스캔');
    overlay.hidden = true;
    overlay.innerHTML =
      '<div class="foms-qr-scan__frame">' +
      '<video class="foms-qr-scan__video" playsinline muted></video>' +
      '<div class="foms-qr-scan__reticle" aria-hidden="true"></div>' +
      '<p class="foms-qr-scan__hint" data-foms-qr-scan-hint></p>' +
      '<button type="button" class="foms-qr-scan__close" data-foms-qr-scan-close aria-label="닫기">닫기</button>' +
      '</div>';
    document.body.appendChild(overlay);
    return overlay;
  }

  function setHint(text) {
    var hint = document.querySelector('#' + OVERLAY_ID + ' [data-foms-qr-scan-hint]');
    if (hint) {
      hint.textContent = text;
    }
  }

  function stopScan() {
    scanning = false;
    if (rafId) {
      window.cancelAnimationFrame(rafId);
      rafId = 0;
    }
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
    }
    var overlay = document.getElementById(OVERLAY_ID);
    if (overlay) {
      overlay.hidden = true;
      var video = overlay.querySelector('video');
      if (video) {
        video.srcObject = null;
      }
    }
  }

  function handleResult(raw) {
    var value = (raw || '').trim();
    if (!value) {
      return false;
    }
    if (/^\d+$/.test(value)) {
      stopScan();
      window.location.assign('/erp/orders/' + value + '/mobile');
      return true;
    }
    try {
      var url = new URL(value, window.location.origin);
      if (url.origin === window.location.origin && url.pathname.indexOf('/erp/') === 0) {
        stopScan();
        window.location.assign(url.pathname + url.search + url.hash);
        return true;
      }
    } catch (e) {
      /* URL 이 아니면 무시 안내로 폴백 */
    }
    setHint('이 시스템의 주문 코드가 아닙니다. 다른 QR 을 비춰 주세요.');
    return false;
  }

  function detectLoop(video) {
    if (!scanning) {
      return;
    }
    detector.detect(video).then(function (codes) {
      if (codes && codes.length && handleResult(codes[0].rawValue)) {
        return;
      }
      rafId = window.requestAnimationFrame(function () { detectLoop(video); });
    }).catch(function () {
      rafId = window.requestAnimationFrame(function () { detectLoop(video); });
    });
  }

  function startScan() {
    var overlay = buildOverlay();
    overlay.hidden = false;
    setHint(DEFAULT_HINT);
    if (!detector) {
      try {
        detector = new window.BarcodeDetector({ formats: ['qr_code'] });
      } catch (e) {
        detector = new window.BarcodeDetector();
      }
    }
    var video = overlay.querySelector('video');
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      .then(function (mediaStream) {
        stream = mediaStream;
        video.srcObject = mediaStream;
        return video.play();
      })
      .then(function () {
        scanning = true;
        detectLoop(video);
      })
      .catch(function () {
        setHint('카메라를 열 수 없습니다. 브라우저 카메라 권한을 확인해 주세요.');
      });
  }

  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-foms-qr-scan-open]')) {
      event.preventDefault();
      startScan();
      return;
    }
    if (event.target.closest('[data-foms-qr-scan-close]')) {
      event.preventDefault();
      stopScan();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && scanning) {
      stopScan();
    }
  });

  revealTriggers();
})();
