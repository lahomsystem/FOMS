/**
 * 주문 변경 이력 탭 (ORDER-DIFF-02).
 *
 * 서버는 빈 껍데기만 내려주고, 이 스크립트가 **탭을 처음 열 때 한 번만** 원장을 부른다.
 * 주문 페이지는 이미 무거운 화면이라 초기 페인트에 감사 조회를 얹지 않는다.
 *
 * 렌더 규칙:
 * - 라벨/문장은 서버(표시 SSOT)가 만든 것을 그대로 쓴다 — 클라이언트가 두 번째 사전을 갖지 않는다.
 * - 값은 textContent 로만 넣는다(고객 입력이 섞이는 자리라 innerHTML 금지).
 */
(function () {
  'use strict';

  var pane = document.getElementById('change-history');
  if (!pane) return;

  var container = pane.querySelector('[data-role="container"]');
  var endpoint = pane.dataset.endpoint;
  var loaded = false;

  /** 안내 문구 1줄로 화면을 비운다. */
  function showMessage(text) {
    container.textContent = '';
    var line = document.createElement('div');
    line.className = 'text-muted small';
    line.textContent = text;
    container.appendChild(line);
  }

  /** 저장 묶음 1건을 카드로 그린다. */
  function renderChangeSet(entry) {
    var card = document.createElement('div');
    card.className = 'foms-change-set';

    var head = document.createElement('div');
    head.className = 'foms-change-set-head';
    var actor = entry.actor ? (entry.actor.name || entry.actor.username) : '시스템';
    head.textContent = (entry.at || '') + ' · ' + actor + ' · ' + entry.changes.length + '건';
    card.appendChild(head);

    // ORDER-REASON-00: "왜" 는 변경 목록보다 위에 온다 — 분쟁 조회에서 먼저 읽는 값이다.
    if (entry.reason) {
      var reason = document.createElement('div');
      reason.className = 'foms-change-set-reason';
      reason.textContent = '사유: ' + entry.reason.label
        + (entry.reason.note ? ' — ' + entry.reason.note : '');
      card.appendChild(reason);
    }

    var list = document.createElement('ul');
    list.className = 'foms-change-set-list';
    // 같은 품목이 연달아 나오면 이름표는 첫 줄에만 붙인다 — 한 품목의 5개 필드를 고치면
    // 같은 이름이 5번 반복돼 정작 바뀐 값이 눈에 안 들어온다(2026-08-14 운영 실측).
    var lastItem = null;
    entry.changes.forEach(function (change) {
      var item = document.createElement('li');
      item.textContent = change.text;
      if (change.item && change.item !== lastItem) {
        var tag = document.createElement('span');
        tag.className = 'foms-change-item-tag';
        tag.textContent = ' — ' + change.item;
        item.appendChild(tag);
      }
      lastItem = change.item || null;
      list.appendChild(item);
    });
    card.appendChild(list);

    if (entry.truncated) {
      var more = document.createElement('div');
      more.className = 'text-muted small';
      more.textContent = '이 저장의 나머지 ' + entry.truncated + '건은 감사 화면에서 볼 수 있습니다.';
      card.appendChild(more);
    }
    return card;
  }

  /** 응답 전체를 그린다(빈 이력·상한 안내 포함). */
  function render(data) {
    var sets = (data && data.change_sets) || [];
    if (!sets.length) {
      showMessage('기록된 변경 이력이 없습니다.');
      return;
    }
    container.textContent = '';
    sets.forEach(function (entry) {
      container.appendChild(renderChangeSet(entry));
    });
    if (data.truncated) {
      var note = document.createElement('div');
      note.className = 'text-muted small';
      note.textContent = '최근 저장 ' + sets.length + '건만 표시합니다. 그 이전 이력은 감사 화면에서 조회하세요.';
      container.appendChild(note);
    }
  }

  /** 원장을 한 번만 불러온다(실패는 화면에 그대로 알린다 — 조용한 빈 화면 금지). */
  function load() {
    if (loaded || !endpoint) return;
    loaded = true;
    showMessage('변경 이력을 불러오는 중...');

    fetch(endpoint, { headers: { 'Accept': 'application/json' } })
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (!payload || payload.success !== true) {
          throw new Error((payload && payload.error) || '불러오지 못했습니다.');
        }
        render(payload.data);
      })
      .catch(function (error) {
        loaded = false;  // 다음에 탭을 다시 열면 재시도한다.
        showMessage('변경 이력을 불러오지 못했습니다: ' + error.message);
      });
  }

  var trigger = document.getElementById('change-history-tab');
  if (trigger) {
    trigger.addEventListener('shown.bs.tab', load);
    // 딥링크 등으로 이미 열린 채 들어오는 경우.
    if (trigger.classList.contains('active')) load();
  }
})();
