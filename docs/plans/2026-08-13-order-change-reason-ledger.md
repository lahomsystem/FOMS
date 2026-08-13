# 주문 변경 사유 + 보존 실측 — Progress Ledger (ORDER-REASON-00 / RETENTION-00)

- 스펙: `docs/specs/2026-08-13-order-change-reason_SPEC.md`
- 작업 트리: `c:\tmp\foms-s-reason0813` (브랜치 `session/reason0813`, base `origin/deploy e496a9d2`)
- 주의: 메인 트리 `C:\DEV\FOMS` 의 로컬 `deploy` 는 `origin/deploy` 와 갈라져 있다
  (ahead 192 / behind 316, ORDER-DIFF 코드 부재) — **여기서 편집 금지**.

| T | 내용 | 완료 기준 | 상태 | 커밋 |
|---|---|---|---|---|
| T0 | 작업 트리·기준선 | heads 1개 · APP_OK · 기존 4종 36 passed | **DONE** | — |
| T1 | 스펙 문서 | 결정·경로·API·스키마 기재 | **DONE** | — |
| T2 | 서버 SSOT(중요 경로·사유 코드·판정 함수) | 신규 유닛 테스트 green | PENDING | |
| T3 | 모델 + 마이그레이션 | upgrade/downgrade 왕복 · heads 1 · PG 테스트 green | PENDING | |
| T4 | 저장 응답 확장(전체·인라인) + detail reason_code | 계약 테스트: required 판정·detail 예산 | PENDING | |
| T5 | 첨부 API + ACTION_LABELS | readability_3 green · 409/24h/권한 테스트 green | PENDING | |
| T6 | 프론트(PC 모달 · 인라인 배너) | `?v=` 범프 + 전수 grep 일치 · 로컬 스모크 | PENDING | |
| T7 | 이력 탭 표시 | field-changes 응답 reason · 탭 테스트 green | PENDING | |
| T8 | 보존 실측 리포트(운영 읽기전용) | 일평균 행수·90일 추정·크기·분포 표 + 보존안 3개 | PENDING | |
| T9 | 최종 검증·푸시 | pre_push_smoke exit 0 · deploy push · 전 워크플로 green | **DONE** | `ab4e2d44`(1차) |
| T10 | 금액 임계(사용자 추가 결정) | 5%/5만원 판정 + 빈도 실측 정정 | **DONE** | `b820f0c6` |
| T11 | 시공일은 확정 이후만 + CI red 해소(policy 매니페스트) | test_auth_enforcement green · 재측정 57% | **DONE** | `4b791879` |
| T12 | 사유 집계 화면 + 우회율 | ADMIN API·화면·PG 질의 테스트 green | **DONE** | `23f7123d` |
| T13 | 스테이징 E2E QA | 비민감 False·금액 True·첨부 200·재첨부 409·이력 사유 표시 | **DONE** | 주문 4400(생성→검증→soft delete) |
| T14 | 실화면 QA + 리다이렉트 결함 수정 | 브라우저에서 시트 유지·사유 기록 후 이동 | **DONE** | `e82fa777` |
| T15 | 태블릿·모바일 사유 표면 | 자산 전역화 계약 테스트·태블릿 명시 저장 배선 | **DONE** | `ec8e1d03` |
| T16 | 축 3개로 축소 + 최초 입력 제외 | 유닛/계약 green · 운영 재측정 | **DONE** | `d09a92c1` |
| T17 | 단계 이동(취소) 축 복원 | 유닛 green | **DONE** | `3c13d05b` |
| T18 | 제품 세부=기록만 + 주문 취소 사유 수집 | 삭제 사유 3건 green · 빈도 15% | **DONE** | `af6d26c9` |

## 기준선 (T0 실측, 2026-08-13)

```
alembic heads : senderphone_00 (head)   # 단일
import app    : APP_OK
pytest        : tests/domains/test_{structured_diff,order_field_changes_ledger,
                order_change_history_tab,structured_item_uid}.py = 36 passed
```

## 알려진 함정

- `security_logs.detail` 4,000자 초과 = 통째 표식 → `_DETAIL_CHANGES_BUDGET` 3,200 안에서만.
- 새 action 은 `ACTION_LABELS` 등재 필수(`tests/domains/test_admin_audit_screen_readability_3.py`).
- JS/CSS 수정 시 `?v=` 범프 + 저장소 전수 grep(핀 하드코딩 계약 테스트가 pre_push_smoke 밖).
  현재 핀: `order-change-history.js?v=20260811a` (`templates/orders/partials/edit_order_body.html:610`,
  `tests/domains/test_order_change_history_tab.py:149`).
- `tests/domains` 전체 실행 시 태블릿 계약 3건 red = 타 세션(`8a76c938`) 몫.
- 원장 쓰기 fail-open + `logger.warning(exc_info=True)`.

## production 승격 차단 사유 (2026-08-13 확인)

운영 브랜치에는 `structured_item_uid.py` 가 **없다**. 마이그레이션 사슬도
`share_token_00 → itemuid_00 → senderphone_00 → naver_link_00 → orderreason_00` 이라
이번 작업만 떼어 승격할 수 없다:

- `share_token_00` — 타 세션(운영 미반영, 이번 세션 시작 시점부터 계속 확인 중)
- `itemuid_00` — ORDER-ITEM-UID(승격 대기)
- `senderphone_00` · `naver_link_00` — 타 세션

`structured_diff` 가 `item_uid_of` 를 import 하므로 ITEM-UID 없이 올리면 운영에서 import 가
깨진다. **선행 승격이 정리되기 전에는 임의 진행 금지**(타 세션 커밋 혼입 = 프로젝트 규칙 위반).

## 최종 규칙 (2026-08-14 사용자 결정 반영)

| 축 | 사유를 묻나 | 조건 |
|---|---|---|
| 시공일 | O | 고객 컨펌 이후 · 최초 입력 제외 |
| 금액(품목 단가·계약금·할인·자유입력) | O | \|변화\| ≥ 5만원 또는 5% · 최초 입력 제외 |
| 단계 이동 | O | — |
| 주문 취소(휴지통 이동) | O | 삭제 **요청 전에** 수집(닫으면 삭제 안 함) |
| 제품 세부(규격·색상·손잡이·옵션·품목 추가삭제) | **X — 기록만** | 원장에는 before→after 로 계속 남는다 |
| 실측일·AS 방문일·연락처·주소·비고 | X — 기록만 | 〃 |

빈도 실측(운영 2일): **15%**(하루 약 8회). 첫 트리거는 전부 금액. 60% → 15% 로 내려간 것은
제품 세부를 기록 전용으로 돌린 결과다.

## 실화면 QA 가 잡은 것 (T14, 2026-08-13)

브라우저로 실제 저장해 보기 전에는 서버 계약·유닛 테스트가 전부 green 이었다. 그런데
전체 저장은 성공 직후 대시보드로 **이동**한다 — 사유 시트가 뜨자마자 화면과 함께 사라졌다.
네트워크 로그(`PUT 200` → `change-reason-codes 200`)가 없었으면 "시트가 안 뜬다"로 오진했을
자리다. 수정은 `FomsChangeReason.prompt()` 가 돌려주는 약속을 저장 경로가 기다린 뒤 이동하는 것.

교훈: **저장 후 화면 전환이 있는 경로에서는, UI 를 띄우는 것과 UI 가 살아 있는 것이 다르다.**
