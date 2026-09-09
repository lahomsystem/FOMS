# AS 재접수 UX — 진행 원장 (2026-08-24)

브랜치 `deploy`. **현재 단계 = 설계 목업(코드 변경 0)**. 저장소 신규 파일은 목업 1개 + 본 원장뿐.

## 산출물

| 파일 | 상태 |
|---|---|
| `docs/design/mockups/as-reintake-workbench.html` | **2차 완성** (4섹션 재조립·렌더 검증 통과, 12,615px) |
| 설계 결정서 `DESIGN_DECISIONS.md` (scratchpad `as-reintake/`) | CEO 2인 검수 반영 완료 |
| 목업 조각·브리프 (scratchpad `as-reintake/`) | BRIEF.md · FIX_ROUND2.md · sec-{pc,mobile,chart,modal}.html · shell-{head,foot}.html |

scratchpad 경로: `C:\Users\USER\AppData\Local\Temp\claude\c--DEV-FOMS\0e78c91e-61e6-49d6-ac3a-e8328b62ec08\scratchpad\as-reintake\`

## 확정 사실 (코드 직접 검증 — 재조사 불필요)

- AS 건 = `structured_data['as_lifecycle'].cycles[]`. 완료 뒤 재접수 = 새 cycle, 열린 건 재접수 = 기록만 갱신 (`as_orders.py:565-575`)
- 완료일 지우기 → 확인 없이 `reopen_as_cycle` (`field_update.py:265-282`)
- `cycles[]` 를 읽는 템플릿·JS **0개**
- 완료 transition payload = `{"note"}` 뿐, 재접수가 `as_received_date` 덮고 `as_completed_date`=None (`as_cycle_service.py:404-407`, `:526-529`) → **지난 건 날짜 복원 불가**
- `as_billing` = 주문당 1슬롯 → 새 건 재시드 시 지난 건 확정 금액 소멸. 완화 지점은 지방 재상차 경로와 **공유**(`as_orders.py:527-530`)
- `current_as_round` = **1 + 미결 판정 수** (`as_log.py:147-170`) — "방문 횟수" 아님
- 회차 버킷 키 = 정수 하나 (`as_round_chart.py:97-99`, `:264-266`) → 건별 1차 재시작 시 서로 다른 건의 1차가 섞임
- `[N차 기록]` 이 발주처 PUSH 로 나감 (`channel_as_message.py:168`)
- LEGACY_BRIDGE 건은 접수일=브리지 실행 시각, 과거 미복원 (`as_cycle_service.py:229-276`)

## 사용자 결정 (2026-08-24)

1. 범위 = 화면 + 회차 기록(백엔드 소폭) 2. 완료일 지우기 = 팝업 2갈래 3. 표면 4개 전부
4. 목업 먼저 5. 지난 AS 요약 = **저장부터 늘린다**(B2·B3) 6. 배포 = **4단계 S1~S4**
7. 회차 숫자 = **설명을 코드에 맞춘다**(계산 무변경) 8. 다음 = 목업 수정

## 용어 (고정)

- 접수 건(cycle) = **"N번째 AS"** (보라) — 1번째는 배지 없음
- 처리 회차(round) = **"N차"** (회색) — "못 끝냈다고 판정할 때마다 +1"
- 재발 = 빨강 칩

## 백엔드 델타 7개 / 단계

B1 as_log cycle_id 스탬프(S1) · B2 cycle 접수일·완료일 스냅샷(S1) · B3 cycle billing 스냅샷(S1) ·
B4 recurrence(S1) · B5 그룹핑 키 (cycle_id, round)+null 규칙(S3) · B6 billing 재시드 **새 건 한정**(S4) ·
B7 완료일 clear 의도 플래그 기본 reopen(S4)

## Task 상태 — 구현 단계 (2026-08-24 착수)

설계 목업 T1~T7 은 종료. 아래는 **실제 구현** 진행표.

| # | Task | 상태 | 산출/검증 |
|---|---|---|---|
| I0 | 배선 지도(모든 버튼 → 파일:라인) | DONE | scratchpad `WIRING_MAP.md` 641줄 |
| I1 | S1 저장 계층(cycle_id 스탬프·날짜/비용 스냅샷·recurrence) | DONE | `as_log.py`·`as_cycle_service.py`, 158 passed |
| I1b | 건 투영 SSOT `foms/services/orders/as_cycle_view.py` | DONE | 메인 작성 + T2a 확장 |
| I2a | 라우트 확장 + 행/상세 투영 | DONE | `as_orders.py`·`as_dashboard_display.py`·`erp_orders_structured.py`·`edit.py`, 120 passed |
| I2b | 회차 차트 뷰 건 묶기 `(cycle_id, round)` | DONE | `as_round_chart.py`, 138 passed |
| I3 | PC 대시보드 표 화면 | DONE | 팝업 3케이스 Playwright 실측, 95 passed |
| I4 | 모바일 카드 + 바텀시트 | DONE | 신규 시트 파셜·JS, 106 passed |
| I5 | 회차 차트 화면 | DONE | 지난 건 접힘·예전 기록 블록, 렌더 15항목 실측 |
| I6 | 재접수 모달 3모드 | DONE | new/edit/reintake 판정 payload 기반, 142 passed |
| I7 | 계약·매니페스트·캐시핀·전체 스위트 | DONE | 4469 passed/4 failed(전부 타 세션) · E2E 5단계 PASS · 실동작 결함 1건 발견·수정 |
| I8 | CEO 2인 최종 감독 | DONE | 둘 다 조건부 — 블로커 3건·누락 8건 |
| I9 | 블로커 수정 R-A/R-B/R-C | DONE | day1 차트 공백 재현→수정 확인(중복 회차 0) · 스냅샷 재봉인 2경로 · 인벤토리 HEAD 복원 |
| I10 | 누락 마감 P1~P4 | DONE | 잔류 안내 줄·칩 44px·증상/처리 행·불명 3종 |


### 구현 확정 사항
- 재접수 버튼은 **기존 상태 셀 안**(13열 추가 금지 — colspan/위치 셀렉터 계약)
- 대시보드→모달 진입 = **딥링크 `?open=erp-order&as_reintake=1`**
- 완료일 팝업은 `as-dashboard.js` 완료일 **change 핸들러**에 삽입(saveDateField 초입 금지)
- 비용 재시드 게이트 = `새 cycle AND 직전 cycle billing_snapshot 봉인됨`(레거시 주문 판정 증발 방지)
- 모바일 비용 세그먼트는 **ERP 편집 권한자만**(현장 기사 미노출)
- 취소 종결(CANCEL)은 이번 범위 제외

### 선재 red 3건 (타 세션 기인, I7 에서 처리)
- `test_as_timeline_contract::test_as_log_write_call_sites_are_the_known_set` — `as_upload_anchor.py` 호출부 미등재
- `test_erp_order_shared_form_scripts` 2건 — `erp_order_js.html` 핀 범프 후 계약 미갱신
- `foms-as-round-chart.css` `?v=` 는 2곳(as_dashboard_body:19 + map_view:1324), 지키는 테스트 없음

## 범위 밖으로 확정 (CEO 지적 중 미이행 — 근거 기록)

- 2-B "이렇게 저장돼요" 미리보기 줄 · 2-D 카드 설명 문단 = 목업 주석 성격(제품 UI 아님)
- PC 행·모바일 카드 `N차` 배지 = S3 범위(회차 의미 변경과 함께 가야 함)
- PC 표 AS 방문일 컬럼은 여전히 주문당 1슬롯 — 차트만 건별 격리됨(목업이 표에 약속한 바 없음)

## 미결 (사용자 결정 대기)

1. 재접수 버튼 권한 게이트·노출 기한(완료 후 N일)
2. reopen 으로 되살린 건의 회차: 이어서(유력) vs 1차 재시작
3. S4 전까지 재접수 모달 비용칸을 잠글지
4. 4-D 모달 제목을 지방 전용으로 좁힐지

## 2차 수정에서 확정된 것

- **소급 그룹핑 = "분류 안 됨" 박스**(사용자 결정 2026-08-24): 표식(cycle_id) 생긴 뒤 기록만 건별로 묶고,
  그 전 기록은 맨 아래 접힌 "예전 기록" 블록에 그대로 둔다. 시각 추정 폐기 — 단정하는 자리를 0으로.
- **취소 종결(CANCEL) 보류**(사용자 결정 2026-08-24): 이번 범위에서 제외. 목업 1-C (c) 카드는 제안 상태로만 유지.

- 현장 기사에겐 **비용 선택칸 미노출**(사무실 권한 토글로만) — 보증·과실 판단 정보가 현장에 없음
- 완료일 지우기 팝업 **3케이스**: (a) 완료 건 reopen (b) 열린 건 잔존 완료일만 삭제 (c) 취소 종결 제안(S4·미결)
- 재접수 후 행이 완료 탭에서 사라지는 것 → "미완료 탭으로 옮겼어요 · 보러가기" 안내 줄로 설명
- 옛 주문 표기 = `이력 시작 전` 배지 + 접수일 `불명` (PC·모바일·차트 3표면)
- 소급 그룹핑 후보에서 "전부 1번째 AS" 폐기

## 커밋 분할안 (CEO 2번 제시 — 아직 커밋 안 함)

- **C0 선행**: 인벤토리 JSON 2종은 이번 작업에서 제외(HEAD 복원 완료). 남은 red 3건은 HEAD 자체가 낡은 것 + 타 세션 미추적 모듈 기인
- **C1 = S1 저장**: `as_log.py` · `as_cycle_service.py` · `as_orders.py`(recurrence hunk) · `test_state_as.py` · `test_as_timeline_contract.py`
- **C2 = S2 화면**: `as_cycle_view.py`(신규) · `as_dashboard_display.py` · `erp_orders_structured.py` · `web/orders/edit.py` · 템플릿 5종 · `as-dashboard.js` · `as-reintake-sheet.js`(신규) · `erp-order-shared.js` · CSS 3종
- **C3 = S3 차트 그룹핑**(별도 배포 창): `as_round_chart.py` · `as_round_chart.html` · `foms-as-round-chart.css` · `map_view.html` · `test_as_round_chart.py`
- **C4 = S4 비용 재시드**: `as_orders.py`(재시드 hunk) · `erp-order-shared.js`(비용 잠금 해제 hunk) · `test_as_billing.py`

**주의**: 워킹트리에 타 세션 미커밋분이 섞여 있다 — `git commit -F msg -- <경로>` 로 경로 지정 필수,
`erp_order_js.html` 은 staged+unstaged 혼재라 `git add -p` 필요.

## 회귀 주의

`as_round_chart.html` = AS 대시보드 + 지도 카드 **공유 부품**. 계약 테스트 20여종(`test_as_round_chart` 는 소스 리터럴 핀).
JS/CSS 변경 시 `?v=` 범프 필수. 신규 mutation 이면 manifest 2종 + `audit_message_display` 라벨.

## 스테이징 배포 완료 (2026-08-25)

**푸시 `77fc7cb4..a84c31a5`, CI 4종 전부 green**(Harness·FOMS CI·PostgreSQL Lane·perf-gate).

로컬 `deploy` 가 원격보다 **1068 커밋 뒤처져** 있어(세션 시작부터의 상태) 원격 tip 기준 워크트리
`c:/tmp/asmerge` 에서 cherry-pick + 의미 병합 후 푸시했다. 충돌 5파일:
- `as_round_chart.html` · `as_dashboard_body.html` — 원격이 `data-order-id` 를 행 컨테이너로 일원화 →
  우리 신규 마크업 3곳에서 속성 제거 + `as-dashboard.js` 를 원격 헬퍼 `orderIdOf()` 로 전환.
  **미조치 시 재접수 팝업 무동작 + `test_as_row_order_id_scope` CI red**였다.
- `as_dashboard_display.py` — 원격 구간 계측(`record_phase`)과 우리 행 투영을 같은 루프에 공존.
- `erp_order_js.html`·`test_erp_order_shared_form_scripts.py` — 원격 최신 핀 전량 유지 + 우리가 고친
  `erp-order-shared.js` 만 `20260824b` 전진 범프.
- 인벤토리 2종은 라인시프트 정합만(external 24 불변, 신규 external writer 0).

푸시된 커밋: a78ad0ad(저장) · d0988dfd(차트) · 2a94ffd7(화면) · 14b10e16(문서) · a84c31a5(인벤토리)

> 위 절은 백업 가지 `backup/deploy-local-20260902` 에만 남아 있던 것을 2026-09-04 에 회수했다. 그 가지를 지우기 전 전수 대조(76건)에서 상류에 없는 유일한 내용이었다. 기능·코드는 전부 상류에 있었고 잃을 뻔한 것은 이 병합 절차 기록뿐이다.
