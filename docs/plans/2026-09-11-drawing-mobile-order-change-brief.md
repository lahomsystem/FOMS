# 모바일 도면 상세 — 주문 변경 배너 제거 + 페르소나 기반 UI 재설계 (목업 브리프, 초안)

작성 2026-09-11. 이 문서는 **초안**이다. CEO 에이전트는 계약과 워커 브리프를 확정하면서 필요한 부분을 고쳐도 된다.

## 1. 사용자 요청 (원문 취지)

모바일 > 도면 상세 화면 상단의 "주문 내용 변경" 분홍 배너는 필요 없다. 같은 변경 내용이 아래 타임라인에 이미
항목별로 표기되기 때문이다. 배너를 걷어내고, 사용자 페르소나 관점에서 이 화면을 다시 구상해 **목업**을 만든다.
이번 요청의 산출물은 목업과 설계 근거이며, 운영 코드 수정은 범위 밖이다.

## 2. 현재 구현 (앵커 — 경로:행)

- `templates/drawing/partials/workbench_mobile_handoff.html:25-38` — 배너 블록.
  `order_change_pending` 이 참일 때만 렌더. `latest_order_change_note`(= `summarize_changes` 한 줄 요약),
  버튼 2개(`data-dw-order-change-focus` = 타임라인으로 스크롤, `data-dw-order-change-ack` = 확인함 POST).
- `templates/drawing/partials/workbench_mobile_handoff.html:164-190` — 타임라인(`.foms-drawing-thread`).
  `ERP_ORDER_CHANGED` 이벤트는 `side='alert'` 로 분홍 말풍선이 되고, `event.changes` 를
  `<strong>라벨</strong> <s>이전</s> → <b>이후</b>` 목록으로 **전량** 보여준다. 배너의 한 줄 요약은 이 목록의 축약본이다 — 중복의 실체.
- `templates/drawing/partials/workbench_mobile_handoff.html:47-80` — **목록(list) 뷰**. 이 분기에는 타임라인이 없다.
  즉 목록 뷰에서는 지금 배너가 주문 변경을 알리는 **유일한** 신호다. 재설계는 이 구멍을 반드시 메운다.
- `templates/drawing/partials/workbench_mobile_handoff.html:1-23` — 상단 2블록: 상태 리본(`.foms-drawing-turn`)과 주문 요약(고객명/주소/담당).
- `templates/drawing/partials/workbench_mobile_handoff.html:191-226` — 하단 고정 액션바(전달/수정요청/수령확정/전달취소/긴급 호출).
- `static/js/drawing/order-change-banner.js` — 배너 동작 전부. `focusTimeline()`(타임라인 스크롤 + `?tab=timeline`),
  `ackBanner()`(POST 후 배너 제거·뱃지 제거·토스트). 문서 위임 + `window.__FOMS_DW_ORDER_CHANGE_BOUND` 싱글턴.
- `static/css/components/foms-drawing-mobile.css:451-462`(배너), `:463-469`(큐 카드 `is-order-change` 칩),
  `:470-482`(타임라인 alert 말풍선). 분홍 계열 토큰: 배경 `#fff0f6`, 테두리 `#f9a8d4`, 글자 `#9d174d`, 강조 `#831843`.
- `foms/web/drawing/workbench.py:937-962` — `order_change_pending`, `latest_order_change_note`, `order_change_events` 생성.
  최초 입력 줄은 `humanize_order_change_changes` 가 걷어내고, 남는 줄이 없는 이벤트는 통째로 제외된다.
- `foms/web/drawing/workbench.py:243` — 상태 리본 보조 문구가 `'… · 주문 단위 상태 1개'` **하드코딩**이다.
  실제 미확인 변경 건수와 무관한 상수 문구이므로, 재설계에서 살아 있는 숫자로 바꿀 후보다.
- 확인 API: `POST /api/orders/<order_id>/drawing/ack-order-change` (`foms/api/drawing/erp_orders_revision.py:498`).
- 참고 테스트(목업 단계에서 건드리지 않지만 구현 시 계약): `tests/visual/test_p1_mockup_structure.py:426-443`,
  `tests/visual/test_p1_mockup_png_gate.py:30-31`, `tests/visual/test_mobile_notification_center.py:264`,
  `tests/domains/test_drawing_workbench_mobile.py:540`.

## 3. 페르소나 (초안 — CEO 가 확정)

1. **도면 담당자 / 최상용** — 도면팀. 아이폰으로 이동 중·작업대 옆에서 본다. 알고 싶은 것은 "내가 지금 그려야 할
   치수가 무엇으로 바뀌었나". 변경의 **내용**(스펙 1170→1165*620*2311)이 중요하고, 요약 한 줄은 다시 아래로 스크롤하게 만든다.
2. **영업 담당자 / 최진호** — 주문을 바꾼 쪽. 모바일에서 "도면팀이 내 변경을 봤나"를 확인한다. 확인 상태(ack)가 보여야 한다.
3. **관리자** — 두 화면 모두 본다. 미확인 변경이 몇 건인지, 언제 확인됐는지를 목록에서 알고 싶다.

## 4. 재설계가 반드시 지켜야 할 것 (기능 보존 계약)

- **A. 중복 제거**: 같은 변경 내용을 상단 요약과 하단 목록에서 두 번 읽게 하지 않는다.
- **B. 확인(ack) 동작 보존**: `POST …/ack-order-change` 를 부를 수 있는 자리가 모바일 화면에 반드시 남는다(한 곳).
- **C. 목록 뷰 신호 보존**: `mobile_handoff_view == 'list'` 에서도 미확인 주문 변경이 있다는 사실을 알 수 있어야 한다.
- **D. 상태 가시성**: 미확인 / 확인됨 두 상태가 시각적으로 구분된다. 확인 시각·확인한 사람은 있으면 좋다.
- **E. 임계경로 비용**: 상단에 새 네트워크 호출·큰 이미지를 얹지 않는다. 렌더 비용은 지금과 같거나 낮다.
- **F. 스타일 규약**: 인라인 스타일 금지가 실제 구현 규약이다. 목업에서도 클래스 기반으로 쓰고, 색은 위 분홍 토큰과
  기존 모바일 카드(흰 배경·12~16px 라운드·연회색 테두리) 어휘 안에서 고른다. 아이콘은 Font Awesome 클래스명으로 표기한다.

## 5. 목업 산출물 규격 (워커 공통)

- 형식: **단일 파일 HTML**(외부 자산·CDN 금지, `<style>` 은 파일 안 `<head>` 나 상단에 둔다). 화면 폭 390px 기준 iPhone 프레임.
- 한 파일에 **상태 3컷**을 가로로 나란히 렌더한다: ① 상세 뷰 · 변경 미확인, ② 상세 뷰 · 확인 후, ③ 목록 뷰 · 미확인 신호.
- 각 컷 아래에 2~4줄 캡션(무엇이 바뀌었나 / 어느 계약을 어떻게 지키나 / 페르소나 중 누구를 위한 것인가).
- 더미 데이터는 실제 화면과 같은 값을 쓴다: 주문 #4985 · 최승희 · 송파구 충민로4길 19 송파파인타운 705동106호 ·
  주문 담당 최진호 · 도면 담당 최상용, 김한비 · 도면 0장 · 변경 2줄
  (`항목1 스펙 1170 → 1165*620*2311`, `항목1 제품명 여닫이 붙박이장 → 몰딩여닫이`).
- 파일 맨 위 주석에 그 안(案)의 이름·한 줄 요지·계약 A~F 를 각각 어디서 지켰는지 표기한다.
- 출력 경로는 CEO 가 배정한다. 워커는 **자기 파일 하나만** 쓴다. 저장소 파일(`templates/`, `static/`, `foms/`)은 읽기만 한다.

## 6. 함정

- 배너를 지우면 목록 뷰가 침묵한다(계약 C). "타임라인에 있으니 됐다"는 상세 뷰에서만 참이다.
- ack 를 타임라인 카드 안으로 옮기면, 변경 이벤트가 여러 건일 때 어느 건을 확인하는지 모호해진다.
  현재 API 는 **주문 단위 확인**(건별 아님)이다. 목업의 문구도 주문 단위로 읽히게 쓴다.
- `주문 단위 상태 1개` 는 하드코딩 상수다. 이 문구를 그대로 목업에 옮기면 거짓 숫자를 설계에 고정하게 된다.
- 타임라인은 최신이 위(newest-first)다. "아래에 있다"는 안내 문구는 정렬과 맞아야 한다.
- 상세 뷰 상단은 이미 3블록(상태 리본·주문 요약·뷰어)이다. 새 블록을 더하면 도면 이미지가 화면 밖으로 밀린다.
  도면을 보러 온 화면이라는 점을 잊지 않는다.

## 7. 검증 (통합 검증자)

- 각 목업 파일이 존재하고, 단독으로 열렸을 때 빈 화면이 아니며, 상태 3컷과 캡션이 모두 있다.
- 계약 A~F 를 안별로 표로 판정한다(지킴/못 지킴/해당 없음 + 근거 한 줄).
- 워커가 자기 파일 밖(다른 안의 파일, 저장소 파일)을 고치지 않았다.
