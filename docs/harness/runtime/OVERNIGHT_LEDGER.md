# OVERNIGHT_LEDGER — 감사 로깅 T8~T-CP3 (2026-08-07 야간, 3차 런)

플랜 정본: `docs/plans/2026-08-05-system-audit-logging-plan.md` (T8~T-CP3 완료 기준 명시)
스펙: `docs/specs/2026-08-05-system-audit-logging-design.md` §4 Phase 3
상위 원장: `docs/plans/2026-08-05-system-audit-logging-ledger.md`
브랜치: `deploy` / 2차 런 종결: 원격 `156cb70c` CI 4/4 green + 스테이징 E2E 13/13

| # | task | 상태 | 검증 결과 | 커밋 SHA |
|---|---|---|---|---|
| T8 | security_logs 구조화(action·target·detail JSONB) | DONE | 메인 직접 76+PG 8 passed+APP_OK. 위임분 domains 4077·PG 675. 우선 호출부 7종 액션 코드화, additional_data 유실 결함 해소, 감사 화면 필터 | `7a8bf528` |
| T9 | 감사 원장 수명주기(FK drop·retention purge·cron 체이닝) | DONE | 메인 직접 47+PG 18 passed+APP_OK+EXPLAIN(소형 테이블 Seq Scan 정상·인덱스 유지). 위임분 PG 692·domains 4113. channel_delivery 자기참조 FK 재귀 가드(뮤테이션 확인) | `bac253cc` |
| T10 | Sentry(no-op 경로까지) + gunicorn access log | DONE(사용자 액션 잔여) | 메인 직접 20 passed + `import app` 후 sentry_sdk 모듈 **0개** 실측(no-op 증명) + Procfile·start.sh access-logfile diff 확인. 잔여=DSN 발급·Railway env·실수신(사용자 몫) | `7519a416` |
| T11 | 잔여 구멍(user_deletion·FAILOPEN·EXTERNAL) | DONE | 메인 직접 242 passed+APP_OK. 위임분 domains 4144·PG 47. 사용자 삭제→비활성화(감사 actor 보존), SWALLOW_BY_CONTROL_FLOW 180 무성장(인위 +1 red 실증). ③ EXTERNAL은 인벤토리 타 세션 미커밋으로 생략 | `a9b8ecb7` |
| T-CP3 | 최종 검증·AI_STATUS·(push 제외) | DONE | smoke exit 0 + hygiene 15 + verify_result success:true + AI_STATUS 갱신. push는 아침 | — |

## Phase 0 (2026-08-07 야간)

- 워킹트리 clean(타 세션 잔여 M 소멸), APP_OK green, 미push 117(계보 분기 이중 계상 —
  본 세션 잔여는 문서 커밋 `7e140151` 1개).

## 가정 (무인 중 질문 금지)

- 순차 실행 T8→T9→T10→T11→T-CP3 (T9 마이그레이션이 T8 컬럼 뒤 체이닝).
- T10 Sentry: **DSN 등록·실수신 확인은 사용자 몫** — no-op 경로·마스킹 워커·테스트까지
  구현하고 BLOCKED 아닌 DONE(사용자 액션 잔여) 처리, 아침 안내.
- T9 결정 ④⑤는 기승인(FK drop + models·runner 동기 / 사용자 삭제 의미 변경).
  보존기간: security_logs 2년·notification_events/channel_delivery_logs/access_logs 1년
  (스펙 제안값 — 원장 가정 기록으로 확정).
- 마이그레이션 down_revision은 push 시점 origin head 재확인 후 필요 시 재부모화
  (2차 런 함정 학습).
- 커밋은 pathspec(`git commit -F msg -- <경로>`), 재위임 2회 실패 시 BLOCKED 전진.
