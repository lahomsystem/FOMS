/**
 * 주문 변경 사유 입력 (ORDER-REASON-00).
 *
 * **저장은 이미 끝났다.** 서버가 "금액·일정·단계가 바뀌었다"고 응답에 표시하면
 * (``change_reason_required`` + ``change_set``) 저장 성공 **뒤에** 사유를 받는다.
 * 저장 전에 묻지 않는 이유: 판정 목록이 서버·클라 2벌이 되고, 사유 창이 저장을 막으면
 * 사유 때문에 주문 저장이 실패한다.
 *
 * 두 가지 표면:
 * - ``full``(전체 저장 버튼) — 시트형 모달. 고르지 않으면 닫히지만 "나중에"를 눌러야 한다.
 * - ``inline``(칸 벗어나면 자동 저장) — 화면 아래 배너. blur 흐름을 모달로 끊지 않는다.
 *
 * 사유 목록은 서버(``/api/orders/change-reason-codes``)가 SSOT 다 — 여기에 복사하지 않는다.
 */
(function () {
  'use strict';

  // 전역 레이아웃(태블릿·모바일)과 ERP 편집 번들 양쪽에서 실릴 수 있다. 두 번 실행되면
  // 리스너가 둘이 되어 시트가 두 장 뜬다.
  if (window.FomsChangeReason) return;

  var CODES_ENDPOINT = '/api/orders/change-reason-codes';
  var codesPromise = null;
  var activeHost = null;
  //: 표면이 닫힐 때(사유 입력·건너뛰기) 호출한다. 저장 후 화면 이동을 여기까지 붙잡아 두는
  //: 쪽이 전체 저장 경로다 — 이동해 버리면 시트가 뜨자마자 사라진다(2026-08-13 스테이징에서
  //: 실제로 그렇게 사라졌다).
  var pendingResolve = null;

  function settle() {
    var resolve = pendingResolve;
    pendingResolve = null;
    if (resolve) resolve();
  }

  /** 사유 목록을 한 번만 받아 캐시한다(정적 상수라 세션 내 재조회 불필요). */
  function loadCodes() {
    if (codesPromise) return codesPromise;
    codesPromise = fetch(CODES_ENDPOINT, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (res) { return res.json(); })
      .then(function (payload) {
        if (!payload || payload.success !== true) throw new Error('사유 목록을 불러오지 못했습니다.');
        return payload.data.codes || [];
      })
      .catch(function (error) {
        codesPromise = null;   // 다음 저장에서 다시 시도한다.
        throw error;
      });
    return codesPromise;
  }

  /** 열려 있던 사유 표면을 치운다(저장이 연달아 일어나도 하나만 남게). */
  function dismiss() {
    if (activeHost && activeHost.parentNode) activeHost.parentNode.removeChild(activeHost);
    activeHost = null;
    settle();
  }

  /**
   * 사유를 서버에 붙인다.
   * @returns {Promise<boolean>} 성공 여부(거절 사유는 화면에 그대로 보여준다).
   */
  function submit(detail, code, note, statusEl) {
    return fetch('/api/orders/' + encodeURIComponent(detail.orderId) + '/change-reason', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ change_set: detail.changeSet, code: code, note: note })
    })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (result) {
        if (!result.ok || !result.data || result.data.success !== true) {
          var message = (result.data && result.data.error) || '사유를 기록하지 못했습니다.';
          if (statusEl) statusEl.textContent = message;
          return false;
        }
        dismiss();   // settle() 로 저장 경로의 대기를 푼다.
        return true;
      })
      .catch(function (error) {
        if (statusEl) statusEl.textContent = '사유를 기록하지 못했습니다: ' + error.message;
        return false;
      });
  }

  /** 사유 버튼 묶음(두 표면 공용) — 값은 서버가 준 목록 그대로. */
  function buildChoices(codes, onPick) {
    var wrap = document.createElement('div');
    wrap.className = 'foms-reason-choices';
    codes.forEach(function (entry) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'foms-reason-choice';
      button.textContent = entry.label;
      button.addEventListener('click', function () { onPick(entry); });
      wrap.appendChild(button);
    });
    return wrap;
  }

  /** 고른 값을 그대로 돌려주고 닫는다(collect 모드 — 아직 서버 요청 전인 행위). */
  function resolveCollected(detail, code, note) {
    var resolve = pendingResolve;
    pendingResolve = null;
    if (activeHost && activeHost.parentNode) activeHost.parentNode.removeChild(activeHost);
    activeHost = null;
    if (resolve) resolve({ code: code, note: note || '' });
  }

  /** 전체 저장용 시트 모달. */
  function openModal(detail, codes) {
    dismiss();
    var host = document.createElement('div');
    host.className = 'foms-reason-modal';
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-modal', 'true');

    var card = document.createElement('div');
    card.className = 'foms-reason-card';

    var title = document.createElement('div');
    title.className = 'foms-reason-title';
    title.textContent = detail.title || '이 변경을 한 이유를 골라주세요';
    card.appendChild(title);

    var hint = document.createElement('div');
    hint.className = 'foms-reason-hint';
    hint.textContent = detail.hint
      || '금액·일정·단계가 바뀐 저장입니다. 나중에 분쟁이 생기면 이 기록이 근거가 됩니다.';
    card.appendChild(hint);

    var status = document.createElement('div');
    status.className = 'foms-reason-status';

    var noteBox = document.createElement('input');
    noteBox.type = 'text';
    noteBox.className = 'foms-reason-note';
    noteBox.maxLength = 200;
    noteBox.placeholder = '기타 사유를 적어주세요';
    noteBox.hidden = true;

    card.appendChild(buildChoices(codes, function (entry) {
      if (detail.collect && !entry.note_required) {
        resolveCollected(detail, entry.code, '');
        return;
      }
      if (entry.note_required && noteBox.hidden) {
        // 기타는 메모가 있어야 집계에서 "그 밖"이 뭉개지지 않는다.
        noteBox.hidden = false;
        noteBox.focus();
        status.textContent = '기타 사유를 적고 Enter 를 눌러주세요.';
        noteBox.onkeydown = function (event) {
          if (event.key !== 'Enter') return;
          if (detail.collect) resolveCollected(detail, entry.code, noteBox.value);
          else submit(detail, entry.code, noteBox.value, status);
        };
        return;
      }
      submit(detail, entry.code, entry.note_required ? noteBox.value : '', status);
    }));
    card.appendChild(noteBox);
    card.appendChild(status);

    var later = document.createElement('button');
    later.type = 'button';
    later.className = 'foms-reason-later';
    later.textContent = detail.collect ? '취소' : '나중에 입력';
    later.addEventListener('click', dismiss);
    card.appendChild(later);

    host.appendChild(card);
    document.body.appendChild(host);
    activeHost = host;
  }

  /** 인라인 저장용 배너(입력 흐름을 끊지 않는다). */
  function openBanner(detail, codes) {
    dismiss();
    var host = document.createElement('div');
    host.className = 'foms-reason-banner';

    var label = document.createElement('span');
    label.className = 'foms-reason-banner-label';
    label.textContent = '변경 사유:';
    host.appendChild(label);

    var status = document.createElement('span');
    status.className = 'foms-reason-status';

    host.appendChild(buildChoices(codes, function (entry) {
      if (entry.note_required) {
        var note = window.prompt('기타 사유를 적어주세요(200자 이내)');
        if (!note) return;
        submit(detail, entry.code, note, status);
        return;
      }
      submit(detail, entry.code, '', status);
    }));
    host.appendChild(status);

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'foms-reason-later';
    close.textContent = '닫기';
    close.addEventListener('click', dismiss);
    host.appendChild(close);

    document.body.appendChild(host);
    activeHost = host;
  }

  /**
   * 사유 표면을 열고, 닫힐 때까지의 약속을 돌려준다.
   *
   * 저장 경로가 이 약속을 기다렸다가 화면을 이동한다(전체 저장은 저장 직후 대시보드로
   * 이동한다 — 기다리지 않으면 시트가 뜨자마자 사라진다).
   *
   * @param {{orderId:(number|string), changeSet:string, mode:(string|undefined)}} detail
   * ``detail.collect`` 가 참이면 서버로 보내지 않고 고른 값
   * (``{code, note}``)을 돌려준다 — 삭제처럼 **요청 전에** 사유를 받아 함께 실어야 하는 행위용.
   *
   * @returns {Promise<void|{code:string,note:string}>} 사유를 남겼거나 사용자가 닫으면 resolve.
   */
  function prompt(detail) {
    // collect 모드는 아직 change set 이 없다(삭제처럼 요청 자체가 아직 안 나갔다).
    if (!detail || !detail.orderId || (!detail.collect && !detail.changeSet)) {
      return Promise.resolve();
    }
    return loadCodes()
      .then(function (codes) {
        if (!codes.length) return;
        return new Promise(function (resolve) {
          // 여는 함수가 먼저 dismiss() 로 이전 표면을 치운다 — 그 dismiss 가 settle() 을
          // 부르므로, 대기 약속은 **연 뒤에** 걸어야 한다(먼저 걸면 즉시 풀린다).
          if (detail.mode === 'inline') openBanner(detail, codes);
          else openModal(detail, codes);
          pendingResolve = resolve;
        });
      })
      .catch(function () {
        // 목록을 못 받으면 조용히 지나간다 — 저장은 이미 성공했고, 사유는 감사 화면에서
        // 나중에 채울 수 있다. 여기서 alert 를 띄우면 저장 실패로 오해된다.
      });
  }

  document.addEventListener('foms:change-reason-required', function (event) {
    prompt((event && event.detail) || {});
  });

  window.FomsChangeReason = { prompt: prompt };
})();
