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

  var COMPRESSIBLE_IMAGE_TYPES = {
    'image/jpeg': true,
    'image/png': true,
    'image/webp': true
  };

  function fomsIsCoarsePointer() {
    try {
      return !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
    } catch (_) {
      return false;
    }
  }

  function fomsGetUploadQueuePolicy(options) {
    options = options || {};
    var mobile = options.mobile != null ? !!options.mobile : fomsIsCoarsePointer();
    return {
      compressConcurrency: Number(options.compressConcurrency || (mobile ? 1 : 2)),
      uploadConcurrency: Number(options.uploadConcurrency || (mobile ? 3 : 5)),
      mobile: mobile
    };
  }

  function fomsShouldCompressImage(file, options) {
    options = options || {};
    var minSize = options.minSizeBytes || 800 * 1024;
    if (!file || !file.type || !COMPRESSIBLE_IMAGE_TYPES[file.type]) return false;
    if (file.size && file.size < minSize) return false;
    return true;
  }

  function fomsNextFrame() {
    return new Promise(function (resolve) {
      var raf = window.requestAnimationFrame || function (cb) { return window.setTimeout(cb, 0); };
      raf(function () { resolve(); });
    });
  }

  function fomsCreateFile(blob, sourceFile, mimeType) {
    if (typeof File === 'function') {
      return new File([blob], sourceFile.name, {
        type: mimeType,
        lastModified: Date.now()
      });
    }
    blob.name = sourceFile.name;
    blob.lastModified = Date.now();
    return blob;
  }

  function fomsDecodeImageFallback(file, registerObjectUrl) {
    return new Promise(function (resolve, reject) {
      if (!window.URL || typeof window.URL.createObjectURL !== 'function') {
        reject(new Error('object URL unsupported'));
        return;
      }
      var url = window.URL.createObjectURL(file);
      registerObjectUrl(url);
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { reject(new Error('image decode failed')); };
      img.src = url;
    });
  }

  function fomsCanvasToBlob(canvas, mimeType, quality) {
    return new Promise(function (resolve) {
      if (!canvas || typeof canvas.toBlob !== 'function') {
        resolve(null);
        return;
      }
      canvas.toBlob(function (blob) {
        resolve(blob || null);
      }, mimeType, quality);
    });
  }

  /**
   * 모바일 안전형 클라이언트 이미지 압축.
   * 실패·미지원·timeout·MIME 불일치 시 원본 파일로 안전 fallback.
   */
  function compressImageFile(file, options) {
    options = options || {};
    if (!fomsShouldCompressImage(file, options)) {
      return Promise.resolve(file);
    }

    var maxLongSide = options.maxLongSide || options.maxWidth || 1920;
    var quality = options.quality !== undefined ? options.quality : 0.82;
    var timeoutMs = options.timeoutMs || 10000;
    var mimeType = file.type;

    return new Promise(function (resolve) {
      var settled = false;
      var bitmap = null;
      var canvas = null;
      var objectUrl = null;
      var timer = null;

      function cleanup() {
        if (bitmap && typeof bitmap.close === 'function') {
          try { bitmap.close(); } catch (_) { }
        }
        bitmap = null;
        if (canvas) {
          try {
            canvas.width = 0;
            canvas.height = 0;
          } catch (_) { }
        }
        canvas = null;
        if (objectUrl && window.URL && typeof window.URL.revokeObjectURL === 'function') {
          try { window.URL.revokeObjectURL(objectUrl); } catch (_) { }
        }
        objectUrl = null;
      }

      function finish(result) {
        if (settled) {
          cleanup();
          return;
        }
        settled = true;
        if (timer) window.clearTimeout(timer);
        cleanup();
        resolve(result || file);
      }

      timer = window.setTimeout(function () {
        finish(file);
      }, timeoutMs);

      (async function () {
        try {
          await fomsNextFrame();
          if (settled) return;

          var source;
          if (typeof window.createImageBitmap === 'function') {
            bitmap = await window.createImageBitmap(file, { imageOrientation: 'from-image' });
            if (settled) {
              cleanup();
              return;
            }
            source = bitmap;
          } else {
            source = await fomsDecodeImageFallback(file, function (url) { objectUrl = url; });
            if (settled) {
              cleanup();
              return;
            }
          }

          var sourceWidth = source.width || source.naturalWidth || 0;
          var sourceHeight = source.height || source.naturalHeight || 0;
          if (!sourceWidth || !sourceHeight) {
            finish(file);
            return;
          }

          var scale = Math.min(maxLongSide / sourceWidth, maxLongSide / sourceHeight, 1);
          var width = Math.max(1, Math.round(sourceWidth * scale));
          var height = Math.max(1, Math.round(sourceHeight * scale));
          canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          var ctx = canvas.getContext('2d');
          if (!ctx) {
            finish(file);
            return;
          }
          ctx.drawImage(source, 0, 0, width, height);
          if (settled) {
            cleanup();
            return;
          }

          var blob = await fomsCanvasToBlob(canvas, mimeType, quality);
          if (settled) {
            cleanup();
            return;
          }
          if (!blob || (blob.type && blob.type !== mimeType)) {
            finish(file);
            return;
          }
          var newFile = fomsCreateFile(blob, file, mimeType);
          if (newFile.size > file.size) {
            finish(file);
            return;
          }
          finish(newFile);
        } catch (_) {
          finish(file);
        }
      })();
    });
  }

  function fomsRunLimitedQueue(items, concurrency, worker) {
    var list = Array.prototype.slice.call(items || []);
    var limit = Math.max(1, Math.min(Number(concurrency) || 1, list.length || 1));
    var results = new Array(list.length);
    var nextIndex = 0;
    var active = 0;
    var done = 0;
    var failed = false;

    return new Promise(function (resolve, reject) {
      if (list.length === 0) {
        resolve([]);
        return;
      }

      function pump() {
        if (failed) return;
        while (active < limit && nextIndex < list.length) {
          (function (index) {
            active += 1;
            Promise.resolve(worker(list[index], index))
              .then(function (result) {
                results[index] = result;
              }, function (err) {
                failed = true;
                reject(err);
              })
              .then(function () {
                if (failed) return;
                active -= 1;
                done += 1;
                if (done >= list.length) {
                  resolve(results);
                  return;
                }
                pump();
              });
          })(nextIndex);
          nextIndex += 1;
        }
      }

      pump();
    });
  }

  function fomsMakeUploadClientId(index) {
    return 'foms-upload-' + Date.now() + '-' + index + '-' + Math.random().toString(36).slice(2, 8);
  }

  async function fomsPrepareUploadFiles(files, options) {
    options = options || {};
    var policy = fomsGetUploadQueuePolicy(options);
    var entries = Array.prototype.slice.call(files || []).map(function (file, index) {
      return {
        clientId: fomsMakeUploadClientId(index),
        originalFile: file,
        file: file,
        compressed: false,
        skipped: !fomsShouldCompressImage(file, options),
        error: null
      };
    });
    var completed = 0;
    await fomsRunLimitedQueue(entries, policy.compressConcurrency, async function (entry, index) {
      if (typeof options.onPrepareProgress === 'function') {
        options.onPrepareProgress({
          index: index,
          done: completed,
          total: entries.length,
          entry: entry,
          phase: 'start'
        });
      }
      try {
        var preparedFile = await compressImageFile(entry.originalFile, options);
        entry.file = preparedFile || entry.originalFile;
        entry.compressed = entry.file !== entry.originalFile;
        entry.skipped = !entry.compressed;
      } catch (err) {
        entry.file = entry.originalFile;
        entry.error = err;
      }
      completed += 1;
      if (typeof options.onPrepareProgress === 'function') {
        options.onPrepareProgress({
          index: index,
          done: completed,
          total: entries.length,
          entry: entry,
          phase: 'done'
        });
      }
      return entry;
    });
    return entries;
  }

  async function fomsRequestUploadSessions(preparedFiles, options) {
    options = options || {};
    var response = await fetch('/api/upload/session/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        files: (preparedFiles || []).map(function (entry) {
          return {
            client_id: entry.clientId,
            filename: entry.file.name,
            size: entry.file.size
          };
        }),
        folder: options.folder,
        category: options.category
      })
    });
    var data = await response.json();
    var sessionMap = {};
    if (data && data.success && Array.isArray(data.sessions)) {
      data.sessions.forEach(function (session) {
        if (session && session.client_id) {
          session.success = true;
          sessionMap[session.client_id] = session;
        }
      });
    }
    return sessionMap;
  }

    async function fomsUploadOrderAttachmentsBatch(options) {
    options = options || {};
    var files = Array.prototype.slice.call(options.files || []);
    var orderId = options.orderId;
    var category = options.category || 'measurement';
    var itemIndex = options.itemIndex == null ? null : options.itemIndex;
    // AS-FRESH-01: 어느 AS 기록의 파일인지(선택). direct/fallback 두 경로에 같이 실어야
    // 업로드 경로에 따라 결합되기도 안 되기도 하는 갈림이 생기지 않는다.
    var asLogId = options.asLogId || null;
    // AS-SORT-01: 미리보기 순서. files 와 같은 길이여야 하며 0 도 유효값이다.
    var sortOrders = options.sortOrders;
    if (sortOrders != null && (!Array.isArray(sortOrders) || sortOrders.length !== files.length)) {
      return { ok: 0, total: files.length, results: [], preparedFiles: [], error: 'sortOrders 길이가 파일 수와 다릅니다.' };
    }
    var folder = options.folder || ('orders/' + orderId + '/attachments');
    var total = files.length;
    var ok = 0;
    var policy = fomsGetUploadQueuePolicy(options);
    var preparedFiles = await fomsPrepareUploadFiles(files, options);
    var sessionMap = {};

    async function fallbackFormUpload(entry, uploadIndex) {
      var formData = new FormData();
      formData.append('file', entry.file);
      formData.append('category', category);
      if (itemIndex != null) formData.append('item_index', String(itemIndex));
      if (asLogId) formData.append('as_log_id', asLogId);
      if (sortOrders) formData.append('sort_order', String(sortOrders[uploadIndex]));
      if (typeof uploadWithProgress !== 'undefined') {
        return uploadWithProgress('/api/orders/' + orderId + '/attachments', formData, {
          onProgress: function (p) {
            if (typeof options.onUploadProgress === 'function') {
              options.onUploadProgress({ done: uploadIndex + p / 100, total: total, entry: entry });
            }
          }
        });
      }
      var res = await fetch('/api/orders/' + orderId + '/attachments', { method: 'POST', body: formData });
      return res.json();
    }

    if (options.useDirectUpload) {
      try {
        sessionMap = await fomsRequestUploadSessions(preparedFiles, { folder: folder, category: category });
      } catch (_) {
        sessionMap = {};
      }
    }

    var completed = 0;
    var results = await fomsRunLimitedQueue(preparedFiles, options.useDirectUpload ? policy.uploadConcurrency : 1, async function (entry, index) {
      var result;
      if (options.useDirectUpload) {
        var session = sessionMap[entry.clientId];
        if (!session || !session.success || !session.upload_url) {
          try {
            var sessRes = await fetch('/api/upload/session', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ filename: entry.file.name, size: entry.file.size, folder: folder, category: category })
            });
            session = await sessRes.json();
          } catch (_) {
            session = null;
          }
        }

        if (session && session.upload_url) {
          try {
            var putRes = await fetch(session.upload_url, {
              method: 'PUT',
              headers: { 'Content-Type': entry.file.type || 'application/octet-stream' },
              body: entry.file
            });
            if (putRes.ok) {
              var completeRes = await fetch('/api/orders/' + orderId + '/attachments/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  key: session.key,
                  filename: entry.file.name,
                  category: category,
                  item_index: itemIndex,
                  as_log_id: asLogId,
                  sort_order: sortOrders ? sortOrders[index] : null,
                  size: entry.file.size
                })
              });
              result = await completeRes.json();
            }
          } catch (_) {
            result = null;
          }
        }
      }

      if (!result || !result.success) {
        try {
          result = await fallbackFormUpload(entry, index);
        } catch (err) {
          result = {
            success: false,
            message: err && err.message ? err.message : '업로드 실패'
          };
        }
      }

      completed += 1;
      if (result && result.success) ok += 1;
      if (typeof options.onFileDone === 'function') {
        options.onFileDone({ done: completed, total: total, entry: entry, result: result });
      }
      if (typeof options.onUploadProgress === 'function') {
        options.onUploadProgress({ done: completed, total: total, entry: entry, result: result });
      }
      entry.file = entry.originalFile;
      return result;
    });

    return { ok: ok, total: total, results: results, preparedFiles: preparedFiles };
  }

  window.compressImageFile = compressImageFile;
  window.fomsGetUploadQueuePolicy = fomsGetUploadQueuePolicy;
  window.fomsShouldCompressImage = fomsShouldCompressImage;
  window.fomsRunLimitedQueue = fomsRunLimitedQueue;
  window.fomsPrepareUploadFiles = fomsPrepareUploadFiles;
  window.fomsRequestUploadSessions = fomsRequestUploadSessions;
  window.fomsUploadOrderAttachmentsBatch = fomsUploadOrderAttachmentsBatch;
})();
