/**
 * 파일 업로드 시 실제 업로드 %를 보여주기 위한 XHR 기반 업로드 유틸.
 * fetch()는 upload progress 이벤트를 지원하지 않으므로 XMLHttpRequest 사용.
 * 사용: uploadWithProgress(url, formData, { onProgress: (percent) => { ... } }).then(data => ...)
 */
(function () {
  'use strict';

  function uploadWithProgress(url, formData, options) {
    options = options || {};
    var onProgress = options.onProgress || function () { };
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

  /**
   * 브라우저 Canvas API를 활용한 클라이언트 사이드 이미지 압축.
   * 스마트폰 원본 사진(5MB+)을 약 1920px 크기로 리사이즈하고 품질을 낮추어(300~500KB) 물리적 업로드 대기 시간을 90% 없앱니다.
   */
  function compressImageFile(file, options) {
    options = options || {};
    var maxWidth = options.maxWidth || 1920;
    var quality = options.quality !== undefined ? options.quality : 0.8;
    // GIF, SVG 등은 압축 시 애니메이션이나 벡터 속성이 날아가므로 무시
    if (!file.type || !file.type.startsWith('image/') || file.type === 'image/gif' || file.type === 'image/svg+xml') {
      return Promise.resolve(file);
    }

    return new Promise(function (resolve) {
      var reader = new FileReader();
      reader.onload = function (event) {
        var img = new Image();
        img.onload = function () {
          var width = img.width;
          var height = img.height;

          // 원본이 이미 설정된 픽셀보다 작으면 리사이즈 패스
          if (width > maxWidth) {
            height = Math.round((height * maxWidth) / width);
            width = maxWidth;
          }

          var canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          var ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);

          var mimeType = file.type;
          // PNG는 Canvas 압축(quality) 패러미터가 지원되지 않고 용량이 커지는 경우가 있어, 최적화를 위해 JPEG로 변환 적용 가능.
          if (mimeType === 'image/png' && options.convertToJpeg) {
            mimeType = 'image/jpeg';
            ctx.fillStyle = "#fff";
            ctx.fillRect(0, 0, canvas.width, canvas.height); // 알파 채널 대비 백그라운드 화이트
            ctx.drawImage(img, 0, 0, width, height);
          }

          canvas.toBlob(function (blob) {
            if (!blob) return resolve(file);
            var newFile = new File([blob], file.name, {
              type: mimeType,
              lastModified: Date.now()
            });
            // 압축 파일이 어쩌다 원본보다 큰 경우 원본 사용
            if (newFile.size > file.size) resolve(file);
            else resolve(newFile);
          }, mimeType, quality);
        };
        img.onerror = function () { resolve(file); };
        img.src = event.target.result;
      };
      reader.onerror = function () { resolve(file); };
      reader.readAsDataURL(file);
    });
  }

  window.compressImageFile = compressImageFile;
})();
