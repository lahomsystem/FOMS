/**
 * B2 CS '부재중' 페이지 내 필터 (클라이언트 전용, 서버 재조회 없음).
 * - 칩 [data-foms-lastcall-filter] 토글 → 스코프([data-foms-lastcall-scope]) 안의
 *   카드([data-foms-last-call]) 중 값이 'no_answer' 가 아니면 hidden 처리.
 * - 힌트 라벨([data-foms-lastcall-hint])은 활성 시에만 표시(페이지네이션 한계 고지).
 * - v2(.foms-v2h-chip 단독 토글)·v3(.fos-chips 단일 선택)를 스코프 단위로 동시 지원.
 *   v3 형제 칩(전체/보류/재확인) 클릭 시 필터를 해제해 단일 선택과 정합을 맞춘다.
 * - document 위임 + __FOMS_CALL_FILTER_BOUND 싱글톤 → 셸 프래그먼트 재실행에도 중복 없음(G4).
 */
(function () {
  'use strict';

  if (window.__FOMS_CALL_FILTER_BOUND) {
    return;
  }
  window.__FOMS_CALL_FILTER_BOUND = true;

  var NO_ANSWER = 'no_answer';

  function scopeOf(el) {
    return (el.closest && el.closest('[data-foms-lastcall-scope]')) || null;
  }

  function applyFilter(scope, on) {
    if (!scope) {
      return;
    }
    var cards = scope.querySelectorAll('[data-foms-last-call]');
    Array.prototype.forEach.call(cards, function (card) {
      card.hidden = on && card.getAttribute('data-foms-last-call') !== NO_ANSWER;
    });
    var hint = scope.querySelector('[data-foms-lastcall-hint]');
    if (hint) {
      hint.hidden = !on;
    }
  }

  function setChip(chip, on) {
    chip.classList.toggle('is-active', on);
    chip.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  document.addEventListener('click', function (ev) {
    if (!ev.target || !ev.target.closest) {
      return;
    }

    var chip = ev.target.closest('[data-foms-lastcall-filter]');
    if (chip) {
      ev.preventDefault();
      var willActivate = chip.getAttribute('aria-pressed') !== 'true';
      setChip(chip, willActivate);
      applyFilter(scopeOf(chip), willActivate);
      return;
    }

    // 형제 칩(필터 아님) 클릭 → 현재 스코프의 활성 필터 해제(v3 단일 선택 정합).
    var sibling = ev.target.closest('.fos-chips .fos-chip, .foms-v2h-chip');
    if (sibling && !sibling.hasAttribute('data-foms-lastcall-filter')) {
      var scope = scopeOf(sibling);
      var active = scope && scope.querySelector('[data-foms-lastcall-filter][aria-pressed="true"]');
      if (active) {
        setChip(active, false);
        applyFilter(scope, false);
      }
    }
  });
})();
