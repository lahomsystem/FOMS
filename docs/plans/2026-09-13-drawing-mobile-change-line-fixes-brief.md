# 모바일 도면 화면 — 운영 제보 3건 수정 브리프 (초안)

작성 2026-09-13. **초안**이다. CEO 에이전트는 계약과 워커 브리프를 확정하며 고쳐도 된다.
선행 작업: 2026-09-12 배너 제거·리본 한 줄(production `0d67f76f3`). 이번은 그 후속 결함 수정이다.

## 1. 사용자 제보 (운영 안드로이드 실기기, 주문 #5082)

1. **리본 변경 줄에 CSS 가 안 붙는다.** 화면에는 `미확인` 칩도, 분홍 세로바도, 카드 테두리도 없이
   파란 글자만 나온다. 같은 화면의 다른 블록(주문 카드·뷰어·제작 자료)은 정상 스타일이다.
2. **`변경 보기` 버튼이 아무 반응이 없다.**
3. **뒤로가기 아이콘이 없다.** 이 상세 화면에서 이전 ERP 도면 탭(도면 작업실 목록)으로 나갈 길을 만들어야 한다.

제보 DOM (그대로):

```html
<div class="foms-drawing-turn__change" id="dwOrderChangeLine" data-order-id="5082" data-order-change-lines="10">
  <span class="foms-drawing-turn__change-chip">미확인</span>
  <span class="foms-drawing-turn__change-text">주문이 바뀌었습니다 · 색상, 자유입력 금액 외 1개 10줄</span>
  <button type="button" class="foms-drawing-turn__change-act" data-dw-order-change-focus="">변경 보기</button>
</div>
```

마크업은 새 것(서버는 새 코드)인데 **CSS 와 JS 만 옛 것**으로 보인다 — 아래 2절이 그 가설의 근거다.

## 2. 앵커와 유력 원인 (검증 대상이지 결론이 아니다)

- `static/css/foundation/foms-mobile-surfaces.css:24` — `@import url("../components/foms-drawing-mobile.css?v=20260716b");`
  2026-09-12 변경에서 `foms-drawing-mobile.css` 본문만 고치고 **이 핀을 안 올렸다**.
  스테이징 실측: 이 자산 응답 헤더가 `cache-control: public, max-age=86400`(24시간).
  → 이미 그 URL 을 받아 둔 기기는 24시간 동안 **옛 CSS** 를 쓴다. 새 클래스가 통째로 없으니 제보 ①과 정확히 맞는다.
- `templates/drawing/partials/workbench_detail_body.html:3021` —
  `<script src=".../js/drawing/order-change-banner.js') }}?v=20260716a" defer></script>`
  같은 이유로 **옛 JS** 가 돌 수 있다. 옛 `ackBanner` 는 `closest('#dwOrderChangeBanner, .dw-order-change-banner')`
  로 조상을 찾으므로 새 확인 버튼에서도 죽고, 옛 `focusTimeline` 도 새 마크업을 모른다. 제보 ②와 맞는다.
- `static/js/drawing/order-change-banner.js:20-42` `focusTimeline()` — **핀 문제가 아니어도 남는 결함**:
  맨 먼저 `document.getElementById('dwOrderChangeFeed')` 로 스크롤한다. 이 요소는 **데스크톱 본문**의 것이고
  모바일에서도 같은 응답 안에 렌더돼 있으나 CSS 로 숨겨져 있다. 숨은 요소에 `scrollIntoView` 는 아무 일도 안 한다
  → 버튼이 죽은 것처럼 보인다. 보이는 요소를 골라야 한다(`offsetParent === null` 이면 건너뛰기 등).
- 모바일 타임라인 도착지는 `.foms-drawing-thread__msg--alert`(최신 미확인 건). 목록 뷰에는 타임라인이 없어
  그 화면의 줄은 버튼이 아니라 상세로 가는 링크다(2026-09-12 계약).
- 뒤로가기 앵커: 모바일 상세 화면 = `templates/drawing/partials/workbench_mobile_handoff.html`.
  상단 블록 순서는 상태 리본 → 주문 요약 → (목록 | 뷰어…). 셸은 `partials/shared/erp_mobile_shell.html`(하단 탭바·드로어)이고
  **상단 바나 뒤로가기 개념이 없다**. 목적지는 도면 작업실 목록
  `url_for('erp_drawing_workbench.erp_drawing_workbench_dashboard')`.
  선례: `templates/orders/partials/risk_frame.html:4` 의 `<a class="foms-risk-frame__back" href="...">← 위험 레이더</a>`.
- 모바일 CSS 정본: `static/css/components/foms-drawing-mobile.css`(리본·타임라인·액션바). 인라인 스타일 금지(ratchet).

## 3. 이번 수정이 지켜야 할 것

- **A. 핀 규율**: 자산 본문을 고치면 그 자산을 가리키는 `?v=` 핀을 **모두** 올린다. 올리기 전
  `grep -rn "<옛 핀>" tests/ templates/ static/` 으로 복제된 자리를 전수로 찾고, 계약 테스트가 그 핀을 박고 있으면 함께 고친다.
- **B. 핀 회귀 방지**: 이번 사고를 고정하는 테스트를 남긴다 — `foms-drawing-mobile.css` 가 새 클래스를 담고 있고,
  그 파일을 가리키는 핀이 2026-09-12 이전 값이 아님을 검사하는 식(문구는 워커가 정한다).
- **C. `변경 보기` 는 눌리면 반드시 보이는 곳으로 간다**: 모바일에서는 모바일 타임라인의 미확인 변경 말풍선,
  데스크톱에서는 변경 이력 피드. 숨은 요소로 스크롤해 조용히 끝나지 않는다. 도착지가 없으면 아무 일도 안 하는 대신
  최소한 로그/토스트로 티가 나야 한다(문구는 워커가 정한다).
- **D. 뒤로가기는 화면을 밀지 않는다**: 상단 블록 수를 늘리지 말고(2026-09-12 계약 E), 리본 안이나 셸 헤더처럼
  이미 있는 자리에 아이콘 하나로 넣는다. 하단 고정 액션바·긴급 호출과 겹치지 않는다. 접근성 라벨 필수.
- **E. 목록 뷰에서도 뒤로가기가 있어야 한다**(도면 2장 이상이면 목록 뷰로 열린다).
- **F. 회귀 금지**: 2026-09-12 계약(값은 한 곳·확인 버튼 1개·무권한 미렌더·목록 뷰 신호)을 깨지 않는다.
  기존 테스트 `tests/domains/test_drawing_mobile_order_change_line.py` 13건이 계속 통과해야 한다.

## 4. 워커 소유권 표 (초안 — CEO 가 확정)

| 워커 | 편집 허용 파일 | 금지 |
|---|---|---|
| W1 핀 | `static/css/foundation/foms-mobile-surfaces.css`, `templates/drawing/partials/workbench_detail_body.html`(스크립트 핀 줄만), 핀 계약 테스트 | JS 본문·모바일 템플릿 |
| W2 버튼 | `static/js/drawing/order-change-banner.js`, 그 계약 테스트(신규 파일) | CSS·템플릿 |
| W3 뒤로가기 | `templates/drawing/partials/workbench_mobile_handoff.html`, `static/css/components/foms-drawing-mobile.css`, 그 계약 테스트(신규 파일) | 위 두 워커 파일 |

세 워커 모두: 저장소 루트는 **`c:/tmp/foms-s-s0913-144546`**(세션 worktree). CRLF 줄끝 보존(`newline='\r\n'` 로 쓴다).
git 명령 금지. 응답은 한국어(한자 금지). 새 파일도 CRLF.

## 5. 검증 명령

- `python -c "import app; print('APP_OK')"`
- `python -m pytest tests/domains/test_drawing_mobile_order_change_line.py tests/domains/test_drawing_workbench_mobile.py -q`
- `python -m pytest tests/visual/test_p1_mockup_structure.py tests/visual/test_p1_mockup_png_gate.py -q`
- `node --check static/js/drawing/order-change-banner.js`
- 핀 전수: `grep -rn "20260716b\|20260716a" tests/ templates/ static/`

## 6. 함정

- 데스크톱 본문과 모바일 partial 은 **같은 응답 안에 함께** 있다. 셀 때는 구간을 갈라서 센다(기존 테스트의 `_render` 참고).
- `pre_push_smoke` 는 정적 JS 구문 검사를 안 한다 — `node --check` 를 따로 돌린다.
- 핀을 올리면 그 핀을 복제한 계약 테스트가 깨진다. 올리기 전에 grep 으로 전수 확인한다.
- 뒤로가기를 `history.back()` 으로 만들면 알림·딥링크로 들어온 사람이 앱 밖으로 나간다. 목적지 URL 을 명시한다.
