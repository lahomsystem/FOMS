# 실측 모바일 — 체크리스트·주문 카드 통합 화면 SPEC (2026-09-23)

> 상태: **승인(2026-09-23)** · 구현 중 보강 2건은 §7
> 목업(사용자 확정본): `docs/plans/2026-09-23-measurement-mobile-unified-mockup.html`
> 선행 작업: 오늘 체크리스트(visit check), 색 A안, 담당자 묶음 안 시간순, 저장 시트 — 모두 deploy·일부 production 반영.

## 1. 문제

모바일 실측 화면(v2 셸, 390px)은 "오늘 실측" 체크리스트 한 벌과, 같은 주문의 큰 카드 한 벌을 위아래로 두 번 보여 준다. 16곳이면 세로 약 6,200~7,300px(추정)이다. 사용자 요청: "리스트 섹션과 주문 카드 섹션이 너무 길어져 — 깔끔하게 통합".

## 2. 사용자 결정 (2026-09-23)

1. 머리: 담당자 탭 줄(안5). `전체 n/m` + 담당자마다 `n/m` + 작은 진행 막대. 좌우로 밀 수 있다.
2. 담당자 묶음 접기와 "모두 펼치기 / 모두 접기"(안3).
3. 메인: 짧은 목록 + 줄을 누르면 바텀시트로 상세(안2).
4. 실측 사진: **ERP 주문에 등록된 사진만** 보여 준다. 사진이 없으면 사진 칸을 **아예 그리지 않는다**. "사진 추가"는 없다. 크게 보기는 **지금 쓰는 미리보기 모달**(GlobalImageViewer)을 그대로 쓴다.
5. 목록을 좌우로 밀면 옆 담당자 탭으로 넘어간다.
6. CSS·색·글꼴은 지금 운영 체크리스트 CSS(`measurement-mobile-glance.css`)와 토큰·Pretendard 를 그대로 쓴다. 새 규칙은 그 뒤에 덧붙이기만 한다.

기존 원칙(변경 없음):
- 체크 칸 = "실측만 완료". 카드의 "실측 완료" = 도면으로 넘김. 서로 다르다.
- 방문 시각은 전날 17시 계획값이다. "다음 방문" 강조, ETA, 실시간 재정렬은 없다. 묶음 안 순서는 예정 시각순(구현됨)이다.
- "이미지 저장"은 맨 위에 두고, 저장 그림은 지금처럼 PC 표 전체다. mine 이면 내 일정만.

## 3. 화면 동작

| 영역 | 동작 |
|---|---|
| 머리 | `오늘 실측` · `n곳 · 실측 a · 넘김 b` · `이미지 저장`. 그 아래 탭 줄이 셸 머리 밑에 붙는다(sticky) |
| 탭 줄 | `전체` + 담당자(목록 순서). 누르거나 목록을 좌우로 밀면 바뀐다. 담당자 탭이면 그 묶음만 보인다. 선택 상태는 `?mgr=` 로 `replaceState` 한다 |
| 전체 탭 | 맨 위에 `담당 n명 · 펼침 k` + `모두 펼치기/접기`. 처음에는 **내 묶음만** 펼친다(없으면 첫 묶음). 마지막 펼침 상태는 localStorage(try/catch)에 둔다 |
| 담당 띠 | 이름·"나"·진행 막대·`실측 n/m`·접기 화살표를 누르면 접히고 펴진다. 오른쪽 둥근 버튼 = 담당 전화(`tel:`) |
| 목록 줄 | 체크 칸 = 실측만 완료(지금 API 그대로). 나머지를 누르면 바텀시트. 오른쪽에 시간 칩, 사진이 있으면 `📷 n`, 넘긴 주문은 이름 옆 `실측 완료` 표시 |
| 바텀시트 | 지금 주문 카드(`render_queue_card_v2`)를 그대로 옮겨 넣어 보여 준다. 머리에 `김OO 담당 2 / 4` + 이전·다음(같은 담당 안, 목록 순서) + 닫기. 시트 안 "실측 체크" 토글(같은 API). 맨 아래 "실측 완료"(기존 확인 창). 뒤로 가기 = 시트 닫기 |
| 실측 사진 | 카드가 이미 그리는 첨부 썸네일 블록을 시트 안에서 가로 줄로 보이게 CSS 만 바꾼다. 누르면 기존 미리보기 모달이 열린다. 사진 0장이면 칸 없음 |
| mine 모드 | 탭 줄·모두 펼치기 없음. 내 묶음 하나만 펼친 채 |

## 4. 구현 범위

| 파일 | 변경 |
|---|---|
| `templates/measurement/partials/mobile_list.html` | 탭 줄, 모두 펼치기 줄, 담당 띠 접기 단추, 줄의 `›`·`📷 n`·넘김 표시. 아래 카드 16장은 숨은 원본 칸으로 감싸고(`hidden`), 시트가 열릴 때 그 카드 노드를 시트로 옮긴다(`id="meas-card-N"`·`data-measurement-mobile-order-id` 유지). 시트 틀 1개(`role=dialog`) |
| `static/js/measurement/mobile-glance.js` (+ 필요하면 새 파일 `mobile-glance-sheet.js`, 300줄 한도) | 탭 거르기·밀기, 접기·모두 펼치기, 시트 열기/닫기/이전·다음, `history.pushState({measSheet})`/`popstate`, 체크 뒤 띠·탭·머리 숫자 갱신 |
| `static/css/contexts/measurement/measurement-mobile-glance.css` | 새 규칙만 덧붙임: 탭·sticky·접힘·시트·사진 가로 줄·`📷 n`·넘김 표시. 기존 규칙 불변 |
| 서버 | 새 쿼리·새 API 없음. 줄 dict 에 이미 있는 `attachment_preview_items`·`attachments_count` 를 쓴다(`foms/services/erp_mobile_order_display.py:172,794,909`). 사진 수 = 이미지 미리보기 항목 수 |
| 공용(건드리지 않음) | `erp_mobile_queue_card_v2.html`, `erp-attachment-preview-open.js`, `layout-scripts-core.js`(GlobalImageViewer), `foms-order-timeline-sheet.js`, `image-save-sheet.js`, `image-export.js` |
| 공용(작게 고침 — 이 SPEC 승인 대상) | `static/js/foms/erp-quest-approve.js`: 실측 완료 뒤 새로 읽고 제자리 복원(`restorePlace`)이 **숨은 카드**를 찾지 못한다. 복원 직전에 `foms:quest-approve:before-restore`(주문 id 전달) 이벤트를 하나 쏘고, 실측 화면이 그 주문의 탭·묶음을 펼친 뒤 줄로 스크롤하게 한다. 다른 화면은 이벤트를 듣지 않으므로 동작 불변 |
| 딥링크 | `?focus_order=N`(`static/js/measurement/mobile.js`, `dashboard.js`) 이 숨은 카드로 스크롤하던 것을 → 그 주문 담당 묶음 펼침 + 줄 스크롤 + 시트 자동 열기로 바꾼다 |

지켜야 할 표식: `erp-queue-card__quest-approve` + `data-confirm`, `data-queue-card-call-link`, `data-queue-card-map-link`, `foms-tl-trigger`/`data-foms-tl-open`, `data-meas-visit-toggle`, `data-meas-export-image`, `data-meas-glance-*`, `data-foms-erp-attachment-preview-gallery`·`-view-url`.

## 5. 위험과 대응

1. 제자리 복원·딥링크가 숨은 카드에서 조용히 실패 → 위 이벤트·딥링크 변경 + 스테이징 실측 완료 1회로 확인.
2. 사진 수 불일치(카드 `+n` 은 PDF 포함) → 실측 화면의 표시는 이미지 수로 통일.
3. 뒤로 가기 층(미리보기 모달 → 시트 → 목록) → GlobalImageViewer 가 history 를 쓰는지 확인하고, 시트 기록과 겹치지 않게 한다. 새로고침으로 남은 `measSheet` 는 시작할 때 지운다.
4. 아이폰 사파리: 두 단 sticky, 시트 스크롤 잠금, 가로 밀기와 뒤로 가기 밀기 겹침 → 실기기 확인 항목.
5. 좌우 밀기가 위아래 스크롤·체크 누름과 헷갈림 → 가로 이동이 세로의 1.5배 이상이고 60px 넘을 때만 탭을 바꾼다. 체크 칸·전화에서 시작한 밀기는 무시.
6. 숨은 카드 16장은 계속 서버에서 그린다(렌더 부담 불변). 썸네일은 `loading="lazy"` 라 시트를 열 때만 받는다.

## 6. 검증

- 단위·계약 테스트: 템플릿 표식, 탭·시트 JS 계약(`await` 없이 즉시 동작 등), CSS 는 기존 규칙 불변(원문 비교) + 새 규칙만 추가.
- 전체 pytest · `pre_push_smoke.ps1` · CI · 배포 확인.
- 스테이징 실데이터(2026-08-20 등): 16곳 세로 길이 before/after 실측, 탭·밀기·접기·시트·이전/다음·체크 숫자 갱신·사진 미리보기·실측 완료 뒤 제자리 복원·`?focus_order` 딥링크·mine 모드·이미지 저장.
- 운영 승격은 사용자 명시 요청 때만.

## 7. 구현 중 보강 (2026-09-23)

1. `static/js/runtime/erp-shell.js` popstate 첫머리: `e.state.fomsShellKeep` 이면 넘어간다(한 줄). 셸은 `/erp/measurement` 에서 뒤로 가기가 나면 같은 주소를 다시 읽는다. window popstate 는 등록 순서대로만 불려 뒤에 실리는 시트가 막을 수 없다(Chromium 149 확인). 시트가 열릴 때만 이 표식을 단다 — 다른 화면은 표식을 쓰지 않아 동작 불변.
2. `erp-quest-approve.js`: 이벤트 `foms:quest-approve:before-restore`(cancelable)에 더해 `window.__fomsQuestApproveRestore` 에 같은 값을 남긴다. `restorePlace` 는 defer 로 DOMContentLoaded 전에 돌고 실측 번들은 그 뒤 동적으로 실려, 이벤트만으로는 받을 리스너가 없다.
