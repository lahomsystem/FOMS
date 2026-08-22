/**
 * 주문 취소(휴지통 이동) 사유 (ORDER-REASON-00).
 *
 * 저장과 달리 삭제는 **요청 전에** 사유를 받는다 — 삭제는 되돌리기가 비싸고, 요청이 나간
 * 뒤에는 사용자가 화면을 떠나 사유를 못 붙인다. 그래서 사유 시트를 collect 모드로 열고,
 * 고른 값을 폼의 hidden 필드에 실어 그대로 제출한다.
 *
 * 사유를 고르지 않고 닫으면 삭제 자체를 하지 않는다(사용자가 취소한 것으로 본다).
 */
(function () {
  'use strict';

  document.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('[data-foms-delete-reason]') : null;
    if (!button) return;
    if (button.dataset.fomsReasonPicked === '1') return;   // 두 번째 클릭(실제 제출)은 통과.

    var form = document.getElementById(button.getAttribute('form'));
    if (!form || !window.FomsChangeReason) return;         // 자산이 없으면 기존 흐름 그대로.

    event.preventDefault();
    var orderId = button.dataset.fomsDeleteReason;

    window.FomsChangeReason.prompt({
      orderId: orderId,
      collect: true,
      title: '이 주문을 취소하는 이유를 골라주세요',
      hint: '휴지통으로 이동합니다. 나중에 "왜 취소했나"를 묻는 자리에서 이 기록이 근거가 됩니다.',
    }).then(function (picked) {
      if (!picked || !picked.code) return;                 // 닫으면 삭제하지 않는다.
      setHidden(form, 'reason_code', picked.code);
      setHidden(form, 'reason_note', picked.note || '');
      button.dataset.fomsReasonPicked = '1';
      button.click();
    });
  });

  /** 폼에 hidden 값을 넣는다(이미 있으면 값만 바꾼다). */
  function setHidden(form, name, value) {
    var input = form.querySelector('input[type="hidden"][name="' + name + '"]');
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      form.appendChild(input);
    }
    input.value = value;
  }
})();
