(function () {
  function openHandoffViewer(trigger) {
    if (!window.GlobalImageViewer || !trigger) return;
    const file = {
      view_url: trigger.getAttribute('data-handoff-view-url') || '',
      download_url: trigger.getAttribute('data-handoff-download-url') || '',
      filename: trigger.getAttribute('data-handoff-filename') || 'drawing',
      key: trigger.getAttribute('data-handoff-key') || ''
    };
    if (!file.view_url) return;
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
