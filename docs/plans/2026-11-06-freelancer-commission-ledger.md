# 프리랜서 영업 수수료 — 진행 원장 (FCOMM-01)

설계서 `docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md` · 플랜 `docs/plans/2026-11-06-freelancer-commission-plan.md` · 검수 원장 `docs/plans/2026-11-06-freelancer-commission-review-ledger.md`.
규칙: task 가 끝나면 그 자리에서 상태를 바꾼다. 막히면 BLOCKED 와 사유를 적고 다음 task 로 간다.

## 0. 기준

- 워크트리 `c:/tmp/foms-s-freelancer-commission`, 브랜치 `session/freelancer-commission`, 시작 origin/deploy `65dec3151`(2026-11-06). 검수 중 origin/deploy `5f714be` 로 1커밋 전진(마이그레이션 변화 없음).
- 메인 체크아웃 `C:/DEV/FOMS` 는 origin/deploy 보다 95 뒤 · 9 앞. 사용자 결정: 지금은 그대로(다른 창 작업 중).
- 모델 Opus 5.5, effort xhigh 기본(사용자 지정 — 상황 따라 조절). 조사 에이전트 Explore(xhigh·high), 검수 3개(반증 xhigh · 단순화 high · 사실 검증 high).

## 1. 사용자 지시·결정 기록

| # | 날짜 | 요지 | 반영 |
|---|---|---|---|
| U1 | 11-06 | 엑셀 공유, 영업 조직 3분류, 공식, 프리랜서는 우리 ERP, 회계팀 입력 + 프리랜서 실시간 대시보드, 페르소나로 구성 → 프롬프트부터 | 설계 프롬프트 |
| U2 | 11-06 | 차감은 곱하기 전 · 발주사에 프리랜서 이름(지금 1명, 회사 영업에서 전향) · 자기 담당만 · 세금 사람마다 · 숨고 회계팀 지정 · 예외 보기는 CS 뱃지 | D1·D3·D4·D11·D12 |
| U3 | 11-06 | 확정매출액 = 출고가 칸 · 11월 실측분부터 · 정산일 10일 · 마감 뒤 다음 달 · 차감 재사용은 UI 에이전트로 조사 · 요율 사람마다(컨트롤 패널) · 알림톡 회사 이름 추후 | D2·D5·D8·D9·D10·D13·D14 |
| U4 | 11-06 | 시공 완료 기준(실측일·시공 완료 기준 필터) | D6·D7 |
| U5 | 11-06 | "여기서 설계 시작" · effort xhigh 기본 · 상황에 맞게 조절해서 구현 | 이 세션 |
| U6 | 11-06 | 프리랜서마다 시작 달 지정 | D8 |
| U7 | 11-06 | 시작 달 = 그 달 1일 이후 실측 · 실측 없음 = 접수일 · 요율 적용 달 고르기 · 차감 알림 보냄 | D8·D15·D16·D17 |
| U8 | 11-06 | 승인: 취소 품목 빼기 · 구멍 두 개는 3단계 때 · 알림톡 발주사 글 추후 · "이대로 진행" | D18·D19·D20, 구현 시작 |

## 2. 상태

| task | 상태 | 메모 |
|---|---|---|
| 설계서 1판 | DONE | 11-06 |
| 교차 검수 3개 | DONE | 반증 20 · 단순화 12 · 사실 검증 62/틀림 4 — 처리 원장 전량 기록 |
| 설계서 2판 | DONE | 승인 대기 |
| 사용자 승인 | DONE | 11-06 "이대로 진행" |
| T0 | 없음 | D19 — T17 로 합침 |
| T1 | PENDING | |
| T2 | PENDING | |
| T3 | PENDING | |
| T4 | PENDING | |
| T5 | PENDING | |
| T6 | PENDING | |
| T7 | PENDING | |
| T8 | PENDING | |
| T9 | PENDING | |
| T10 | PENDING | |
| T11 | PENDING | |
| T12 | PENDING | 2027-01-10 전 |
| T13 | PENDING | |
| T14 | PENDING | |
| T15 | PENDING | |
| T16 | PENDING | |
| T17 | PENDING | |
| T18 | PENDING | |
