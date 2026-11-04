/**
 * 협력사 사진 줄이기 — 우리 직원 화면과 같은 규칙(사용자 11-04: 협력사 사진은 원본 그대로 올라가던 것).
 *
 * 규칙은 우리 공용 static/js/runtime/upload-progress.js 의 compressImageFile 그대로다: 800KB 넘는 jpg · png · webp 만
 * 긴 변 1920px · 품질 0.8(우리 주문 화면 erp-order-shared.js 와 같은 값)로 다시 그리고, 사진 방향(EXIF)은 지킨다.
 * 동영상 · PDF · 작은 사진은 그대로, 줄이다 실패하거나 10초가 넘으면 원본을 보낸다.
 * partner-portal.js 가 올리기 직전에 PartnerShrink.file(파일) · PartnerShrink.formData(폼)으로 부른다.
 */
(function () {
  'use strict';

  function file(f) {
    if (typeof window.compressImageFile !== 'function' || !f) return Promise.resolve(f);
    return window.compressImageFile(f, { quality: 0.8 }).catch(function () { return f; });
  }

  /** 폼 → FormData, 사진 칸 파일은 줄여서 넣는다(수정 요청 · AS 사진). */
  async function formData(form) {
    var source = new FormData(form);
    var out = new FormData();
    var entries = [];
    source.forEach(function (value, key) { entries.push([key, value]); });
    for (var i = 0; i < entries.length; i += 1) {
      var value = entries[i][1];
      if (value instanceof File && value.size) {
        var small = await file(value);
        out.append(entries[i][0], small, small.name);
      } else {
        out.append(entries[i][0], value);
      }
    }
    return out;
  }

  window.PartnerShrink = { file: file, formData: formData };
})();
