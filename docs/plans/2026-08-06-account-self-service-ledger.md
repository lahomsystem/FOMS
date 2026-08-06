# 계정 셀프서비스 v1 — progress ledger (2026-08-06)

스펙: docs/specs/2026-08-06-account-self-service-design.md
브랜치: deploy (공유 트리 — 타 세션은 map_view 계열 편집 중, 파일 겹침 없음. 커밋은 `git commit -F msg -- <경로>` 경로 지정)

| T | 작업 | 완료 기준 | 상태 |
|---|------|-----------|------|
| T1 | 스펙+원장 문서 | 두 파일 존재 | DONE |
| T2 | 모델+마이그레이션 (approval_status, password_reset_requests) | alembic upgrade/downgrade 왕복 + APP_OK | DONE (offline SQL 왕복 검증, 실 PG 적용은 스테이징 predeploy) |
| T3 | 라우트 (register 개방·로그인 게이트·재설정 요청·admin approve/reject/handle) | APP_OK + 신규 테스트 통과 | DONE |
| T4 | rate limit 배선 + write guard 정합 | 대상 엔드포인트 limit 적용 확인(테스트/코드) | DONE (IP 키 고정 — 세션 쿠키 키는 익명 엔드포인트에서 버킷 회전 우회 가능. manifest 2종 등재) |
| T5 | 템플릿 (register·login 링크·reset 폼·user_list 섹션) | 렌더 테스트 통과 | DONE |
| T6 | 테스트 신규+기존 회귀 | test_auth_self_service + bootstrap_admin/auth_enforcement/password_policy/user_delete 전부 green | DONE (신규 14 + 회귀 79 + namespace 계약 180 green) |
| T7 | 검증·AI_STATUS·커밋 | pytest 대상 green + APP_OK + 커밋 SHA 기록 | DONE — pre_push_smoke exit 0(307 passed), 커밋 SHA는 커밋 후 기입 |

## 비고
- failopen 인벤토리 재생성(+4 auth, 전부 LOG_AND_CONTINUE·로그 있음).
- AI_STATUS head 예산 초과(타 세션 라인 +15자)는 완료 항목 1건을 '최근 완료'로 이관해 해소.
- 스테이징 QA(실브라우저 가입→승인→로그인 흐름)는 deploy push 후 별도 수행.
