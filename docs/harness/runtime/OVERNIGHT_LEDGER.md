# OVERNIGHT_LEDGER — 감사 로깅 T4~T-CP2 (2026-08-06 야간, 2차 런)

플랜 정본: `docs/plans/2026-08-05-system-audit-logging-plan.md` (T4·T5·T6·T-CP2 완료 기준 명시)
스펙: `docs/specs/2026-08-05-system-audit-logging-design.md` (2차 개정판)
상위 원장: `docs/plans/2026-08-05-system-audit-logging-ledger.md`
브랜치: `deploy` / 시작 HEAD: `db1bfa24` / 1차 런(T2·T3·T-CP1): push `d7f0d9ea` CI 4/4 green 종결

| # | task | 상태 | 검증 결과 | 커밋 SHA |
|---|---|---|---|---|
| T4 | 첨부 soft delete + 이벤트 + 전역 필터 | DONE | 메인 직접 재실행 110 passed(신규 35·권한·게이트 4종) + APP_OK. 위임분: PG 6(왕복·EXPLAIN)·첨부 관련 856·PG 전수 652·전체 4473 passed(6 fail은 T4 무관 기존 환경 문제 — clean HEAD 재현 확인). 이탈 판단 4건 수용: 404(권한 후 판정)·outbox 2행·인덱스 2종·manifest 등재. **⚠ push 의존: 마이그레이션이 타 세션 `account_self_00` 위 체이닝** | `3ec9bfd2` |
| T5 | 관리자 행위 구조화 + 접근거부 기록(독립 감사 헬퍼) | DONE | 메인 직접 재실행 76 passed(신규 15·셀프서비스·게이트) + APP_OK. 위임분: PG 7(독립 커밋 인과 증명)·연관 599·smoke 게이트 253. SQLite 독립성 한계는 PG 레인으로 증명(문서화). auth 겹침 없음(셀프서비스 커밋 위 작업) | `9d02f0f5` |
| T6 | access_logs 부활 (파일 접근 3곳, T5 헬퍼 공유) | DONE | 메인 직접 재실행 103 passed(신규 32·T4/T5 공존·게이트) + APP_OK. 위임분: PG 8(FK 실증·EXPLAIN)·PG 전수 667·영향 영역 343, 뮤테이션 검증 확인. 403/404/tombstone 미기록 결정 | `ea8a1abc` |
| T-CP2 | Phase 2 검증·커밋(push는 승인 범위 밖) | DONE | pre_push_smoke exit 0 + hygiene 15 passed. push·스테이징 확인은 아침(⚠ 마이그레이션 account_self_00 의존 — REPORT 참조) | — |

## Phase 0 점검 (2026-08-06 야간)

- APP_OK green. 워킹트리 타 세션 잔여 M 2파일(regional) — 스테이징 금지 목록.
- 미push 80커밋(타 세션 다수 + 본 세션 문서 3개: 8e5169aa·bcdeebc7·757d2907).
- ⚠️ 타 세션 "계정 셀프서비스 v1"(748eb337)이 auth 영역 커밋 + `test_auth_self_service.py`
  실시간 편집 감지(30분 내) — **T5와 `foms/web/auth/routes.py` 겹침 위험**.
  T5 착수 전 파일 최신 상태 재확인 + 겹치면 T5를 마지막으로 순연.

## 가정 (무인 중 질문 금지)

- 실행 순서 T4 → T5 → T6 순차(공유 워킹트리 — 병렬 금지, T6은 T5 헬퍼 의존).
- 커밋은 자기 몫 파일만 명시 스테이징. 재위임 2회 실패 시 BLOCKED 후 전진.
- 마이그레이션(T4)은 로컬 PG에 upgrade/downgrade 왕복 검증까지, 스테이징 적용은
  push(배포) 시 자동.
- T5 auth 겹침 발생 시: 타 세션 커밋 위에서 작업(로컬 HEAD 기준), 실시간 동시 편집
  감지되면 해당 파일만 BLOCKED 기록.
