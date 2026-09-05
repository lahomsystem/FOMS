# 정산탭 CFO 감사 후속 수정 — 진행 원장 (2026-09-05)

브리프: `docs/plans/2026-09-05-settlement-cfo-fixes-brief.md` · 스펙: `2026-09-05-settlement-cfo-review-report.md` §3·§4
워크트리 `c:/tmp/foms-s-settle-cfo` · 브랜치 `session/settle-cfo` · base origin/deploy `7100e2aa1`
방식: 사용자 지시로 CEO 워크플로(CEO 설계 → BE/FE 병렬 → 통합 검증 → 2판정 리뷰 → CEO 판정) 뒤 총괄 무신뢰 재검증 → smoke → push_own → CI → 스테이징 QA

| task | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | D-02 예외 머리 숫자 모집단화 + "N건 중 M건" | strip 테스트 3곳 교체 + 상한 초과·미만 대조군 | PENDING |
| T2 | D-01 미매칭 정산액·aging KPI + 화면 한 줄 | `_KPI_SCALARS` 갱신·신규 테스트·질의 예산 6 유지 | PENDING |
| T3 | F-07 워커 루프 창당 1회 가드 | 순수 함수 테스트 4건 | PENDING |
| T4 | 라벨 묶음 6종(A-01·A-03·G-01·G-03·G-04·C-02) + `expected_unassigned_amount`·`ledger.totals` | 렌더 계약 문구 6개·API 테스트 | PENDING |
| T5 | C-01 전기 정의(꽉 찬 달력 월) + `range.prev` + 라벨 | 테스트 5케이스·`_DATA_KEYS` 갱신 | PENDING |
| G | 총괄 게이트: APP_OK·정산 스위트(기준선 922)·sync 테스트·contracts+ns·perf guard·CRLF·smoke exit 0 | 전부 green | PENDING |
| P | push_own → CI 전 워크플로 green → 스테이징 실화면 QA(핀 20260905a 도달·예외 머리·미매칭 금액·라벨·전기 구간) | 완료 | PENDING |

범위 밖(사용자 결정 2026-09-05): B-02 보류 누적 잔액(M) · F-07 RETRO 누적(M) · D-03 AMOUNT_DIFF · H-01 인덱스 · E-05 비번 로테이션(별도 선택지) · 그 외 백로그 6~14.

## 기록
- 2026-09-05 감사 완료(보고서 커밋 `8894e4c41`). 사용자 선택 "쉬운 수정 5개 바로 고치기".
