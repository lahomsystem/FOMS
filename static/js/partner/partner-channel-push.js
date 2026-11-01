/**
 * 협력사 주문 화면 영발 · 발주 PUSH(사용자 결정 2026-10-29) — 변환(보낼 글 미리 보기) · 보내기.
 * 영발은 실측을 마친 주문만(2026-11-01): 실측 예정이면 "실측 끝 · 도면 요청"(POST .../request-drawing →
 * {success, data:{push_note} | {missing}, error})이 도면 단계로 넘기며 서버가 한 번 보낸다. 새 주문을 "마쳤어요"로
 * 저장해 바로 도면 단계가 되면 사진을 올린 뒤 여기서 한 번 보낸다(묻지 않는다).
 *
 * 서버 계약: GET  /api/partner/orders/<id>/channel-push → {success, data:{text, state}, error}
 *            POST /api/partner/orders/<id>/channel-push {kind, change_note?} → {success, data:{state}, error}
 * state = {measurement|drawing: {pushed, sent_label, open, reason}}. 글은 서버가 만든다.
 * 보낸 적 있으면 다시 보낼 때 바뀐 내용을 묻는다(서버가 재전송 메모를 요구한다 — ERP 와 같은 규칙).
 */
(function () {
  'use strict';

  var LABELS = { measurement: '영발', drawing: '발주' };
  var WAITING = { measurement: '도면 요청 뒤', drawing: '승인 뒤' };

  // 서버 오류는 문자열 또는 {code, message}(본문 크기 · 내부 오류 공통 봉투) — 둘 다 글로 보인다.
  function errorText(data) {
    var err = data && data.error;
    if (err && typeof err === 'object') return err.message || '';
    return err || '';
  }

  async function request(url, method, body) {
    var opts = { method: method, credentials: 'same-origin' };
    if (body) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    var resp = await fetch(url, opts);
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) {
      var missing = data && data.data && data.data.missing;
      var msg = errorText(data) || '보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
      throw new Error(missing && missing.length ? msg + '\n- ' + missing.join('\n- ') : msg);
    }
    return data.data;
  }

  /** 보내기 한 번. 보낸 적 있으면 바뀐 내용을 묻는다(취소하면 null). */
  async function send(url, kind, pushed) {
    var body = { kind: kind };
    if (pushed) {
      var note = window.prompt(LABELS[kind] + '방에 다시 보냅니다. 무엇이 바뀌었는지 적어 주세요.');
      if (note === null) return null;
      if (!note.trim()) throw new Error('바뀐 내용을 적어야 다시 보낼 수 있습니다.');
      body.change_note = note.trim();
    } else if (!window.confirm('본사 ' + LABELS[kind] + '방으로 보낼까요?')) {
      return null;
    }
    return request(url, 'POST', body);
  }

  function noteText(state) {
    return ['measurement', 'drawing'].map(function (kind) {
      var s = state[kind] || {};
      return LABELS[kind] + ' ' + (s.pushed ? '보냄 ' + s.sent_label : (s.open ? '아직 안 보냄' : WAITING[kind]));
    }).join(' · ');
  }

  function bindPanel(panel) {
    var url = panel.getAttribute('data-pp-push-url');
    var textBox = panel.querySelector('[data-pp-push-text]');
    var note = panel.querySelector('[data-pp-push-note]');
    var status = panel.querySelector('[data-pp-push-status]');
    var buttons = panel.querySelectorAll('[data-pp-push]');
    var busy = false;

    function show(text, isError) {
      if (!status) return;
      status.textContent = text || '';
      status.classList.toggle('pp-status--error', !!isError);
    }

    function apply(state) {
      if (note) note.textContent = noteText(state);
      Array.prototype.forEach.call(buttons, function (btn) {
        var s = state[btn.getAttribute('data-pp-push')] || {};
        btn.setAttribute('data-pp-pushed', s.pushed ? '1' : '0');
        btn.disabled = !s.open;
        if (!s.open && s.reason) btn.title = s.reason;
      });
    }

    var preview = panel.querySelector('[data-pp-push-preview]');
    if (preview) {
      preview.addEventListener('click', async function () {
        show('글을 만드는 중…');
        try {
          var data = await request(url, 'GET');
          if (textBox) textBox.value = data.text || '';
          apply(data.state || {});
          show('');
        } catch (err) {
          show(err.message, true);
        }
      });
    }

    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener('click', async function () {
        if (busy) return;
        var kind = btn.getAttribute('data-pp-push');
        busy = true;
        btn.disabled = true;
        var result = null;
        try {
          show('보내는 중…');
          result = await send(url, kind, btn.getAttribute('data-pp-pushed') === '1');
          show(result ? LABELS[kind] + '방에 보냈습니다.' : '');
        } catch (err) {
          show(err.message, true);
        }
        busy = false;
        // 보냈으면 서버 상태대로, 취소 · 실패면 누르기 전처럼(눌렀다는 건 열려 있었다는 뜻).
        if (result) apply(result.state || {});
        else btn.disabled = false;
      });
    });
  }

  /** 새 주문 저장 · 사진 올린 뒤. 도면 단계면 영발방으로 한 번(묻지 않는다), 실측 예정이면 다음 할 일을 알린다. */
  async function afterCreate(url, created, measuredDone) {
    if (created.stage !== 'DRAWING') {
      var missing = created.missing || [];
      window.alert(measuredDone && missing.length
        ? '실측 예정으로 저장했습니다. 도면을 요청하려면 더 넣어 주세요.\n- ' + missing.join('\n- ') + '\n\n다 넣은 뒤 주문 화면에서 "실측 끝 · 도면 요청"을 눌러 주세요.'
        : '실측 예정으로 저장했습니다. 실측을 마치면 주문 화면에서 "실측 끝 · 도면 요청"을 눌러 주세요.');
      return;
    }
    if (!url) return;
    try {
      await request(url, 'POST', { kind: 'measurement' });
    } catch (err) {
      window.alert('영발방에 보내지 못했습니다: ' + err.message + '\n주문 화면의 "영발 PUSH"로 다시 보내 주세요.');
    }
  }

  /** "실측 끝 · 도면 요청" — 서버가 조건을 다시 보고, 넘기면 영발방으로 한 번 보낸다. */
  function bindDrawingRequest(panel) {
    var btn = panel.querySelector('[data-pp-request-drawing]');
    if (!btn) return;
    btn.addEventListener('click', async function () {
      if (!window.confirm('실측을 마쳤나요? 도면 단계로 넘기고 본사 영발방으로 보냅니다.')) return;
      btn.disabled = true;
      try {
        var data = await request(panel.getAttribute('data-pp-request-url'), 'POST', {});
        window.alert('도면을 요청했습니다.' + (data && data.push_note ? '\n' + data.push_note : ''));
        window.location.reload();
      } catch (err) {
        window.alert(err.message);
        btn.disabled = false;
      }
    });
  }

  window.PartnerChannelPush = { afterCreate: afterCreate };

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('[data-pp-channel-push]'), function (panel) {
      bindPanel(panel);
      bindDrawingRequest(panel);
    });
  });
})();
