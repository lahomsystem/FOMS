(function () {
  /**
   * 같은 주문의 도면 전체 목록(서버 JSON) — data-* + 가드 파싱 패턴.
   * 인라인 JSON.parse('{{ x|tojson }}') 는 금지라 속성에서 읽는다.
   * @param {Element|null} root data-foms-drawing-handoff-files 보유 노드
   * @returns {Array<Object>} 파싱 실패·비배열이면 빈 배열
   */
  function handoffFiles(root) {
    const raw = root && root.getAttribute('data-foms-drawing-handoff-files');
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      console.warn('[drawing-handoff] 도면 목록 파싱 실패 — 단일 도면으로 열기', err);
      return [];
    }
  }

  function fileFromTrigger(trigger) {
    return {
      view_url: trigger.getAttribute('data-handoff-view-url') || '',
      download_url: trigger.getAttribute('data-handoff-download-url') || '',
      filename: trigger.getAttribute('data-handoff-filename') || 'drawing',
      key: trigger.getAttribute('data-handoff-key') || ''
    };
  }

  /**
   * 수정요청 말풍선 하나의 참고사진 묶음(서버가 key 로 만든 URL 만 data-* 에 있다).
   * @param {Element} group data-handoff-ref-group 노드
   * @returns {Array<Object>} view_url 이 있는 사진 목록
   */
  function refGroupFiles(group) {
    return Array.from(group.querySelectorAll('[data-drawing-handoff-open]'))
      .map(fileFromTrigger)
      .filter(function (f) { return Boolean(f.view_url); });
  }

  function openHandoffViewer(trigger) {
    if (!window.GlobalImageViewer || !trigger) return;
    const file = fileFromTrigger(trigger);
    if (!file.view_url) return;
    // 도면이 여러 장이면 전체를 넘겨 좌우 스와이프·화살표로 넘겨보게 한다(실측 이미지와 동일).
    // 수정요청 참고사진은 도면 목록과 섞지 않고 그 말풍선의 사진끼리만 넘긴다.
    const group = trigger.closest('[data-handoff-ref-group]');
    const files = group
      ? refGroupFiles(group)
      : handoffFiles(trigger.closest('[data-foms-drawing-handoff-files]'));
    const index = files.findIndex(function (f) {
      return (f.key && f.key === file.key) || f.view_url === file.view_url;
    });
    if (files.length && index >= 0) {
      window.GlobalImageViewer.open(files, index);
      return;
    }
    window.GlobalImageViewer.open([file], 0);
  }

  function setRevisionTarget(key) {
    if (!key) return;
    document.querySelectorAll('#dw-revision-target-cards .drawing-target-card').forEach((card) => {
      const checkbox = card.querySelector('.revision-target-checkbox');
      const matched = checkbox && checkbox.value === key;
      card.classList.toggle('selected', Boolean(matched));
      if (checkbox) checkbox.checked = Boolean(matched);
    });
  }

  // 대신 누르기 표 — 모바일 버튼은 같은 응답의 숨은 PC 버튼을 누른다(그 버튼의 확인창·API·토스트를 그대로 쓴다).
  // 도면방 보내기는 PC #dw-btn-drawing-room-push 의 pushDrawingRoom(workbench_detail_body.html) 을 탄다.
  function proxyLegacyAction(action) {
    const target = {
      confirm: 'btn-confirm-receipt',
      cancel: 'btn-cancel-transfer',
      'cancel-revision': 'btn-cancel-revision',
      'drawing-room-push': 'dw-btn-drawing-room-push'
    }[action];
    if (!target) return;
    document.getElementById(target)?.click();
  }

  function notify(message) {
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(message);
      return;
    }
    window.alert(message);
  }

  /**
   * 수정요청 반영 체크 토글 — PC 요청사항 칸(.js-revision-check)과 같은 API·같은 본문.
   * 성공하면 지금 주소를 다시 읽어 하단 바(전달 대기 → 수정본 전달)를 서버 판정으로 갱신한다.
   * @param {HTMLButtonElement} button data-request-at·data-by-user-id·data-next-checked 보유
   */
  async function toggleRevisionCheck(button) {
    if (button.disabled) return; // 이중 탭·스크립트 중복 실행 가드
    const orderId = button.getAttribute('data-order-id') || '';
    const requestAt = button.getAttribute('data-request-at') || '';
    if (!orderId || !requestAt) return;
    const byUserId = button.getAttribute('data-by-user-id') || '';
    button.disabled = true;
    try {
      const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/request-revision-check', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          request_at: requestAt,
          by_user_id: byUserId ? Number(byUserId) : null,
          checked: button.getAttribute('data-next-checked') === 'true'
        })
      });
      const data = await res.json();
      if (!data || !data.success) {
        notify((data && data.message) || '반영 체크 저장에 실패했습니다.');
        button.disabled = false;
        return;
      }
      window.location.reload();
    } catch (err) {
      console.error('[drawing-handoff] 반영 체크 저장 실패', err);
      notify('반영 체크 저장 중 오류가 발생했습니다. 잠시 후 다시 눌러 주세요.');
      button.disabled = false;
    }
  }

  document.addEventListener('click', function (event) {
    const viewer = event.target.closest('[data-drawing-handoff-open]');
    if (viewer) {
      event.preventDefault();
      openHandoffViewer(viewer);
      return;
    }

    const action = event.target.closest('[data-drawing-handoff-action]');
    if (!action) return;
    const actionName = action.getAttribute('data-drawing-handoff-action');
    if (actionName === 'revision') {
      setRevisionTarget(action.getAttribute('data-drawing-key') || '');
      return;
    }
    event.preventDefault();
    if (actionName === 'revision-check') {
      toggleRevisionCheck(action);
      return;
    }
    proxyLegacyAction(actionName);
  });
})();
