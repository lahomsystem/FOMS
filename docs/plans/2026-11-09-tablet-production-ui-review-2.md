# 리뷰어 ② 단순화 심판 — 보고 원문 (2026-11-09)

> 원장 §5 의 본문. 리뷰어(Fable 5.1 high, 읽기 전용) 보고를 그대로 붙였다. 총괄 재확인·반영은 원장 §6.

목업 `docs/design/mockups/tablet-production-ui.html`: **미도착**(폴더에 없음, 두 번 확인). 아래는 설계서·플랜·전수표·코드만으로 판정.

## 표 1. 바뀐 칸 판정

| 바뀐 칸 | 판정 | 이유 한 줄 | 설계서 위치 |
|---|---|---|---|
| F1 ① 레일 배율 단추 | **지움**(하려면 include 1줄) | 배율은 사람·기기마다 1번 저장(`ui-zoom.js:28`, 키 `…:touch`) → 세로로 한 번 돌려 서랍 손잡이(`erp_mobile_menu_drawer.html:82-83`)로 정하면 끝. 워커 B H9 ④도 "가로에서 못 바꿈"일 뿐 매일 바꿀 일은 아님. 꼭 두려면 새 단추 묶음·CSS 말고 `foms_ui_zoom_control.html` 을 `variant='rail'` 로 include — JS 는 document 위임(`ui-zoom.js:55-56`)이라 0줄 | §5 F1 ① |
| F1 ② 카드 "공정 n/5" | **지움** | 카드엔 이미 칩 10종(`tablet_kanban_body.html:230-320`). 세로 카드에 있는 이유는 세로엔 시트가 없어서(`mobile_queue.html:90-96`). 가로는 카드 탭 = 시트 | §5 F1 ② |
| F1 ③ 60vh 보정 | 남김 | 130% 잘림 버그, CSS 1줄 | §5 F1 ③ |
| F2 ① 전화·주소 한 줄 | 남김 | D3. 모바일 상세 꼴 재사용(`order_detail_mobile_v2.html:139,150`) | §5 F2 ① |
| F2 ② "상차 M/D · 시공팀" | **지움**(시공팀) + 이름 고침 | "상차" 값은 시공일 키(`dashboard.py:371-372,446`, F-19) → 카드 "시공 M/D D-x" 와 같은 사실이 다른 이름으로 두 번. 시공팀은 출고 보드·출고 시트(`shipment/partials/tablet_sheet.html:19`)에 이미 있고 생산은 쓰기 없음 | §5 F2 ② |
| F2 ③ 공정 5체크+불량 | 남김 | F-03 핵심 | §5 F2 ③ |
| F2 ④ 도면 스트립 | **줄임** | 썸네일 N장만. "1/3" 은 전역 뷰어가 이미 "n / N"(`layout-scripts-core.js:262-263`). "바뀐 도면 · M/D 바로 반영"은 바로 위 변경 알림 섹션(`tablet_sheet.html:73-87`)과 같은 사실 | §5 F2 ④ |
| F2 ⑤ 링크 두 개 | **줄임**(1개) | "상세" 하나. 인쇄는 F8 확정 전엔 링크 없음 | §5 F2 ⑤ |
| F3 뷰어 위 글·아래 단추 | **지움**(새 JS 0) | 고객명·#id 는 시트에서 열었으니 아는 것, 장수는 뷰어 내장, 바뀐 도면은 시트 변경 알림, 단추는 뷰어 닫으면 바로 시트 | §5 F3 |
| F6 ① 하단 탭 생산 | 남김 | F-07, 기존 분기 꼴 1줄(`erp_mobile_shell.html:48-56`) | §5 F6 ① |
| F6 ② QR 막대 위치 | **지움(미룸)** | D4 지금 방식에 QR 없음. 위치 이동은 결함 아닌 취향 | §5 F6 ② |
| F7 ① 착지 = 생산 보드 | 남김 | F-01 근본 수정 | §5 F7 ① |
| F7 ② 컨트롤타워 시트 읽기 전용 | **줄임**(문구만) | ① 뒤엔 생산팀이 컨트롤타워 갈 이유가 거의 없음. `fragment-loader.js:96` 문구 1곳. Q-D 사라짐 | §5 F7 ② |
| F7 ③ AS 행 시트 URL | **지움**(별건 1줄 커밋) | 생산 범위 밖. 끼우면 Q-E 가 생김 | §5 F7 ③ |
| F8 인쇄 페이지 | **미룸** | D4 는 조건부. "계약 시험이 인쇄 금지"는 과장 — 시험은 `foms-prod-pcbar__actions/__label` 클래스 부재만 단언(`test_tablet_t2_contract.py:427-438`). 확정되면 라우트1+템플릿1+CSS1 불가피 | §5 F8 |
| F-13 품목 취소 알림 | **줄임**(호출 1줄) | 배지+규격 표 제외는 이미 있음. 새 kind 라벨·스트립 종류 말고 `apply_production_change_alert` 호출만 — 라벨 기본값 "주문 변경"(`production_change.py:138`), 템플릿 else 분기가 아이콘 처리 | §7 |
| T5-3 공지·프로필 레일 | **지움(미룸)** | 레일 아바타가 이미 프로필로 감(`foms_tablet_rail.html:51-56`) | 플랜 T5-3 |
| D5 실패 문구 | 남김+범위 추가 | `foms-production-steps.js:263,296` 도 같은 문구로 | §8 |

## 표 2. 새로 만드는 것

| 새로 만드는 것 | 대신할 기존 것 | 판정 |
|---|---|---|
| JS `tablet-production-viewer.js` | `erp-attachment-preview-open.js` 마운터 — 읽기 전용 갤러리 N장 → `GlobalImageViewer.open(files, idx)`(`:163-167,200-202`), counter 내장. 생산 페이지에 로드 1줄, 또는 기존 인라인 폴백(`tablet_sheet.html:210-220`)을 노드 전체 루프로 | **지움** |
| `data-foms-drawing-files` JSON 속성 | 마운터는 DOM 노드에서 목록을 만듦(`galleryFilesFromNodes`) | 지움 |
| 인쇄 라우트+템플릿+CSS | 없음(전례 `erp_order_label`) | 미룸(D4 확정 뒤) |
| 알림 종류 `item_cancel` + 라벨 + 스트립 | 기본 라벨 fallback + else 분기 | 줄임(호출 1줄) |
| 레일 배율 단추 마크업·CSS | `foms_ui_zoom_control.html` include | 지움(또는 1줄) |
| 뷰 모델 `construction_team` | 출고 보드 | 지움 |
| 새 시험 파일 `test_production_team_landing.py` | 기존 `tests/domains/test_post_auth_navigation*.py` 에 사례 추가 | 줄임 |
| 시트 섹션 새 CSS | `.foms-prod-sheet__card`·`__card-title` 재사용 | 줄임 |
| `localStorage` 날짜 키(T4-3) | Q-C "그대로"면 0 | 지움 |
| 60vh → `calc(60vh / zoom)` | — | 남김 |

## 글 결함(원문 → 고침)
- 시트 머리 "#id · 상차 M/D" → "#id · 시공 M/D"(카드와 같은 값·같은 이름, `dashboard.py:372` 주석 "시공(상차)").
- "바뀐 도면 · M/D 바로 반영" → 지움("바로 반영"은 내부 말).
- 뷰어 위 글 전부 지움.
- 시트 단추 "생산 완료"(`tablet_sheet.html:197`) vs 세로 카드 "제작 완료"(`mobile_queue.html:72`) — 한 이름으로("제작 완료").
- "주문 상세 보기" vs 세로 "[상세]" → "상세".
- F-13 본문 "(남은 품목 n개)" 지움.
- Q-D 문구 "생산팀은 보기만 할 수 있어요" → "이 주문은 보기만 할 수 있어요".

## 플랜 축소안
- 삭제: T1-3, T2-4, T3-2, T4-1(또는 T4-2 에 include 1줄), T4-3, T5-1·T5-2·T5-3(P5 미룸).
- 합치기: T2-1+T2-2 · T2-3+T2-5 · T3-1 에 뷰어 연결 흡수 · T4-2+T4-4 는 P2 끝에.
- 결과: 17 task → 8, 단계 P1→P2→P3.

## §11 질문 판정
- Q-A 금액: 설계자 결정 "그대로"(범위 밖 기록). Q-B 레일: "지금처럼". Q-C 모달: "그대로"(코드가 의도된 마찰, `tablet_kanban_body.html:347-351`). Q-D: "문구만". Q-E: "별건". → 승인 질문 창 비어도 됨.
