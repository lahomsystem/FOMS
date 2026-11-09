/**
 * 협력사 "도면 확인했어요" — 진행할 도면 고르기(설계서 docs/plans/2026-11-09-partner-receipt-pick-drawings-spec.md).
 * 도면이 2장 이상일 때만 이 파일이 실린다. 체크된 도면 key 를 final_drawing_keys 로 보낸다 —
 * 우리 영업 확정 창과 같이 체크를 푼 도면은 최종 도면에서 빠진다(서버 plan_partial_confirm).
 */
(function () {
  'use strict';

  function setStatus(text, isError) {
    var el = document.getElementById('ppStatus');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('pp-status--error', !!isError);
  }

  function picks() {
    var boxes = document.querySelectorAll('[data-pp-receive-pick] input[type="checkbox"]');
    var on = [], onNo = [], offNo = [];
    Array.prototype.forEach.call(boxes, function (box) {
      var no = box.getAttribute('data-pp-pick-no') || '';
      if (box.checked) { on.push(box.value); onNo.push(no + '번'); } else { offNo.push(no + '번'); }
    });
    return { keys: on, onNo: onNo, offNo: offNo };
  }

  function question(p) {
    var tail = '도면을 확인했다고 저희에게 알릴까요? 고객 확인 단계로 넘어갑니다.';
    if (!p.offNo.length) return tail;
    return p.onNo.join(', ') + ' 도면만 진행합니다. ' + p.offNo.join(', ') + ' 도면은 빠지고 만들지 않습니다.\n\n' + tail;
  }

  async function send(button) {
    var p = picks();
    if (!p.keys.length) { setStatus('진행할 도면을 하나 이상 골라 주세요.', true); return; }
    if (!window.confirm(question(p))) return;
    button.disabled = true;
    setStatus('보내는 중…');
    try {
      var resp = await fetch(button.getAttribute('data-pp-receive-url'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ final_drawing_keys: p.keys }),
        credentials: 'same-origin',
      });
      var data = null;
      try { data = await resp.json(); } catch (e) { data = null; }
      if (!data || !data.success) throw new Error((data && data.error) || '보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
      window.location.reload();
    } catch (err) {
      setStatus(err.message, true);
      button.disabled = false;
    }
  }

  document.addEventListener('click', function (ev) {
    var button = ev.target.closest && ev.target.closest('[data-pp-receive-url]');
    if (!button || button.disabled) return;
    send(button);
  });
})();
