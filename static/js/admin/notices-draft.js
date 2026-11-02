/**
 * FOMS 공지 쓰기 · 고치기 — 쓰던 글 잠깐 맡아 두기.
 * 휴대폰은 사진을 고르러 갤러리 · 카메라 앱에 다녀오는 사이 브라우저가 이 화면을 지웠다가 다시 읽는 일이 잦다
 * (폼이 autocomplete="off" 라 브라우저도 글을 되살리지 않는다). 그래서 화면을 떠나기 직전마다
 * 제목 · 내용 · 받는 쪽 · 사진 · 설정을 sessionStorage(이 탭에만)에 적어 두고, 다시 열리면 data-notice 에 겹쳐
 * notices-images.js · notices-form.js 가 고치기 화면처럼 미리 채우게 한다. 이 파일은 두 파일보다 먼저 실린다.
 * 저장에 성공하면 notices-form.js 가 FomsNoticeDraft.clear() 로 지운다. 30분 지난 맡김은 버린다.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-notice-form]');
  if (!root) return;
  var TTL_MS = 30 * 60 * 1000;
  var current = {};
  try {
    current = JSON.parse(root.getAttribute('data-notice') || '{}') || {};
  } catch (err) {
    current = {};
  }
  var key = 'foms-notice-draft:' + (root.getAttribute('data-mode') === 'edit' ? String(current.id || '') : 'new');
  var done = false;

  function read() {
    try {
      var saved = JSON.parse(window.sessionStorage.getItem(key) || 'null');
      if (saved && saved.data && Date.now() - Number(saved.at) < TTL_MS) return saved.data;
      window.sessionStorage.removeItem(key);
    } catch (err) { /* sessionStorage 막힘 — 맡기지 않는다 */ }
    return null;
  }

  function save() {
    if (done || !window.FomsNoticeForm) return;
    var data = window.FomsNoticeForm.snapshot();
    if (window.FomsNoticeImages) data.images = window.FomsNoticeImages.items();
    var aud = data.audience || {};
    var chosen = aud.staff_all || aud.partner_all || (aud.staff_teams || []).length || (aud.partner_org_ids || []).length;
    try {
      if (!data.title && !String(data.body || '').trim() && !(data.images || []).length && !chosen) {
        window.sessionStorage.removeItem(key); // 다 비웠으면 맡긴 것도 버린다
        return;
      }
      window.sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), data: data }));
    } catch (err) { /* 꽉 참 · 막힘 — 맡기지 못해도 쓰기는 그대로 된다 */ }
  }

  var draft = read();
  if (draft) {
    var merged = Object.assign({}, current, draft, { draft: true });
    root.setAttribute('data-notice', JSON.stringify(merged));
    var box = root.querySelector('[data-notice-message]');
    if (box) {
      box.className = 'alert foms-notice-admin__message alert-info';
      box.textContent = '쓰던 내용을 되살렸어요. 확인한 뒤 저장해 주세요.';
    }
  }

  window.FomsNoticeDraft = {
    clear: function () {
      done = true;
      try { window.sessionStorage.removeItem(key); } catch (err) { /* 막힘 */ }
    }
  };
  // 사진 칸을 누르는 순간(앱으로 넘어가기 전) · 화면이 가려질 때 · 떠날 때마다 적어 둔다.
  root.addEventListener('click', function (event) {
    if (event.target.closest('a[href]')) window.FomsNoticeDraft.clear(); // [공지 목록] — 일부러 떠난다
    else window.setTimeout(save, 0);
  }, true);
  root.addEventListener('change', save);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') save();
  });
  window.addEventListener('pagehide', save);
})();
