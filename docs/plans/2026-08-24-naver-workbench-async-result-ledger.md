# 진행 원장 — 네이버 워크벤치 불가역 3종 결과 즉시 반영 (2026-08-24)

스펙: `docs/specs/2026-08-24-naver-workbench-async-result_SPEC.md`
상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md`
선행 원장: `docs/plans/2026-08-23-naver-workbench-v3-ledger.md`
작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

## 사용자 확정 (2026-08-24, 착수 전 질의)
- 갱신 범위 = **화면 전체 soft refresh**(목록 배지·칩·탭·상세가 한 번에 정합).
- 벌크 = **폴링 없이** "보내는 중" + 15초 뒤 1회 갱신(단건 3종 우선).
- 검증 = **스테이징 가짜 링크 1건**으로 실패 경로 실측(실고객 불가역 버튼 미클릭).

## Task

| # | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | `_household_of_link` 분리 + `_fulfillment_state` + GET `fulfillment-state` | 게이트 OFF 404 / 400 / 404 / 판정키 없음 / 형제 전부 / rev 변화 — 회귀 6건 green | DONE |
| T2 | fulfillment·cancel 라우트 응답에 enqueue **직전** `rev` | 회귀 2건 green (enqueue 전 계산 순서 포함) | DONE |
| T3 | JS `softRefresh()` | `.naver-workbench` 교체 + 글자배율·벌크·offlist 복구, 조각 아니면 reload 폴백 | DONE |
| T4 | JS `watchFulfillment()` 폴링 | 2초·최대 25초, pollToken+paneToken 2중 차단, 타임아웃 시 1회 갱신 후 정지 | DONE |
| T5 | 단건 3종 배선 + 폴링 중 불가역 버튼 4종 잠금 | `location.reload()` 3곳 제거, 실패는 pane ack 빨강 | DONE |
| T6 | 벌크 가볍게(`#wb-bulk-note` + 15초 뒤 1회 갱신) | 벌크 폴링 없음(계약 테스트로 못박음) | DONE |
| T7 | 검증 — pytest 전수 · APP_OK · `?v` 범프 · pre_push_smoke exit 0 | 전부 green | DONE |
| T8 | 스테이징 가짜 링크 실패 경로 실측 후 삭제 | 새로고침 없이 실패 사유가 뜨는 것 눈 확인 | PENDING |
| T9 | 커밋 · deploy 푸시 · CI 전 워크플로 green | `gh run list` 로 4종 확인 | PENDING |

## 기록

### 구현 (2026-08-24)
- **진짜 원인**: 발송처리·취소·주문 만들기는 이미 `location.reload()` 를 하고 있었다.
  안 보이던 이유는 새로고침이 없어서가 아니라 **워커보다 먼저** 새로고침해서다.
- 서버: `_group_of_link` 를 `_household_of_link(db, link) -> (group, rows)` 로 쪼개 링크 행을
  재사용(조회 3회 → 2회). `_fulfillment_state` 는 워커 표식만 요약하고 **판정을 하지 않는다**.
- `FULFILLMENT_ACTION_LABELS` 를 상수로 올려 실패 띠와 폴링 응답이 같은 표를 쓴다.
- JS: `watchFulfillment`(2초·최대 25초, `pollToken`+`paneToken` 2중 차단) + `softRefresh`
  (`.naver-workbench` 통째 교체 — 이 화면 배선이 전부 document 위임이라 가능).
- 모달을 **닫기 전에** 폴링을 시작한다 — 닫는 애니메이션(최대 0.6초) 동안 pane 의 불가역
  버튼이 열려 있으면 그 틈에 한 번 더 눌린다.
- 재시도(`submitRetry`)도 같은 결함 부류라 벌크와 같은 규칙으로 함께 고쳤다(집마다 폴링 없음).

### 검증 (2026-08-24)
- `tests/services/integrations/` **518 passed** (신규 16건 포함).
- `python -c "import app; print('APP_OK')"` 성공.
- `scripts/ops/pre_push_smoke.ps1` **exit 0** (pytest 서브셋 324 passed).
- `failopen_scan.py` 재생성 결과는 **줄밀림만**이라 커밋하지 않는다(게이트가 안 보는 축).
  `order_mutation_writer_scan.py` 는 변화 없음(새 경로는 읽기 전용 GET).
- 자산 핀 `?v=20260824g → 20260824h` (CSS·JS 둘 다).
