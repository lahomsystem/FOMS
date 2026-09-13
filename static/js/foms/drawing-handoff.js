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

  function openHandoffViewer(trigger) {
    if (!window.GlobalImageViewer || !trigger) return;
    const file = {
      view_url: trigger.getAttribute('data-handoff-view-url') || '',
      download_url: trigger.getAttribute('data-handoff-download-url') || '',
      filename: trigger.getAttribute('data-handoff-filename') || 'drawing',
      key: trigger.getAttribute('data-handoff-key') || ''
    };
    if (!file.view_url) return;
    // 도면이 여러 장이면 전체를 넘겨 좌우 스와이프·화살표로 넘겨보게 한다(실측 이미지와 동일).
    const files = handoffFiles(trigger.closest('[data-foms-drawing-handoff-files]'));
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

  function proxyLegacyAction(action) {
    const target = {
      confirm: 'btn-confirm-receipt',
      cancel: 'btn-cancel-transfer',
      'cancel-revision': 'btn-cancel-revision'
    }[action];
    if (!target) return;
    document.getElementById(target)?.click();
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
    proxyLegacyAction(actionName);
  });
})();
