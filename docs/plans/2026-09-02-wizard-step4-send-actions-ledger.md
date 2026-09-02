# WIZ-SEND-01 진행 원장

설계: `docs/plans/2026-09-02-wizard-step4-send-actions-plan.md`
브랜치: `session/wizard-push-alimtalk` / worktree: `c:\tmp\foms-s-wizard-push-alimtalk`

| task | 상태 | 담당 | 완료 기준 | 검증 결과 |
|---|---|---|---|---|
| T1 알림톡 sd 발송 계층 | DONE | agent | 신규+기존 알림톡 pytest green | CEO 재검증: diff 직접 확인 + `pytest test_wizard_alimtalk_sd_send.py test_kakao_alimtalk_send.py` 54 passed |
| T2 실측방 본문 서버 조립기 | DONE | agent | 골든 계약 테스트 green | CEO 재검증: 17 passed + 초안형 sd 실제 렌더 육안 대조(PC 포맷 일치) |
| T3 초안 발송 라우트+manifest | PENDING | agent | write_guard/audit inventory green | |
| T4 마법사 UI | DONE(코드) | agent | 소스 계약 + 실화면 동작 | CEO 재검증: 계약 9 passed·`node --check` OK·diff 확인. 실브라우저 QA 는 T3 착지 후 |
| T5 이력 컬럼·승계 | DONE | agent | 단일 head + 승계 pytest | 컬럼·마이그레이션·서비스 착지. 승계 방식은 rev_99 게이트 충돌로 D4' 재작업(T5b) |
| T5b 승계 D4' 재작업 | DONE | agent | rev_99/state_guard green + EXTERNAL 24 불변 | CEO 재검증: rev_99 포함 70 passed, diff 확인(ORM 쓰기 0건) |
| T3 라우트+manifest+감사라벨 | DONE | agent | write_guard/audit/contracts green | CEO 재검증: 158 passed(계약 게이트 포함) |
| 통합 검증 | DONE | CEO | APP_OK + pre_push_smoke exit 0 | pre_push_smoke PASSED. 전체 스위트 red 2건(ci.yml 레지스트리 2종 미등재) 직접 수정 후 재실행 |
| 로컬 실브라우저 QA | DONE | CEO | 미저장 초안 발송 확인 | 헤드리스 실브라우저: 미리보기 2종 라이브 반영·미자격 차단·실발송(자격 미달 아님, 벤더 auth 오류)·초안 이력 기록·감사행·주문 승계 전부 확인 |
| 스테이징 QA | PENDING | 사용자 | 실채널 발송 확인 | 채널톡 키가 로컬에 없어 실측 PUSH 실발송은 스테이징 전용 |
