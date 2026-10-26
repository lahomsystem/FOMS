/**
 * 도면 마법사 — 시트 사이 그림 id 겹침 떼기(순수 계산). 설계서 docs/plans/2026-10-26-drawing-wizard-sheet-integrity-spec.md §1.2-2.
 *
 * 복제·붙여넣기·버전 복원은 늘 새 id 를 만든다. 그래도 버그 길로 같은 객체 id 가 두 시트(또는 한 시트 안 두 곳)에 생기면
 * 한쪽을 지우거나 옮길 때 헷갈린다. 불러올 때와 저장할 때 앞에서부터 보며 이미 나온 id 를 다시 만나면 새 id 로 바꾼다.
 * 그림은 지우지 않는다 — 무엇을 지울지는 사람이 정한다.
 *
 * window.FomsSheetIds = { splitDupIds(sheets, makeId) }
 */
(function () {
  'use strict';
  if (window.FomsSheetIds) { return; }

  /** 시트들의 객체 id 를 앞에서부터 보며 겹친 것을 makeId() 로 바꾼다(sheets 를 고친다). 바꾼 수를 돌려준다. */
  function splitDupIds(sheets, makeId) {
    var seen = Object.create(null), n = 0;
    (sheets || []).forEach(function (s) {
      ((s && s.objects) || []).forEach(function (o) {
        if (!o || !o.id) { return; }
        if (seen[o.id]) {
          var id;
          do { id = makeId(); } while (seen[id]);
          o.id = id;
          n += 1;
        }
        seen[o.id] = true;
      });
    });
    return n;
  }

  window.FomsSheetIds = { splitDupIds: splitDupIds };
})();
