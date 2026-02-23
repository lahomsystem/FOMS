/**
 * 파일 업로드 시 실제 업로드 %를 보여주기 위한 XHR 기반 업로드 유틸.
 * fetch()는 upload progress 이벤트를 지원하지 않으므로 XMLHttpRequest 사용.
 * 사용: uploadWithProgress(url, formData, { onProgress: (percent) => { ... } }).then(data => ...)
 */
(function () {
  'use strict';

  function uploadWithProgress(url, formData, options) {
    options = options || {};
    var onProgress = options.onProgress || function () {};
    var timeout = options.timeout != null ? options.timeout : 300000;

    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.timeout = timeout;

      xhr.upload.addEventListener('progress', function (e) {
        if (e.lengthComputable) {
          var percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent);
        }
      });

      xhr.addEventListener('load', function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            var data = JSON.parse(xhr.responseText);
            resolve(data);
          } catch (err) {
            reject(new Error('응답 파싱 실패'));
          }
        } else {
          reject(new Error('HTTP ' + xhr.status));
        }
      });

      xhr.addEventListener('error', function () {
        reject(new Error('네트워크 오류'));
      });

      xhr.addEventListener('timeout', function () {
        reject(new Error('업로드 시간 초과'));
      });

      xhr.open('POST', url);
      xhr.send(formData);
    });
  }

  window.uploadWithProgress = uploadWithProgress;
})();
