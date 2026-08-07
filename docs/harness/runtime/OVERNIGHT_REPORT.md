# OVERNIGHT_REPORT — 감사 로깅 T8~T-CP3 (2026-08-07 야간, 3차/최종 런)

플랜: `docs/plans/2026-08-05-system-audit-logging-plan.md` / 원장: `OVERNIGHT_LEDGER.md`
승인: **커밋까지**(push 제외). 이전 런: P1 `d7f0d9ea`·P2 `156cb70c` 둘 다 CI green.

## 완료 task (BLOCKED 0)

| task | SHA | 검증 원문 |
|---|---|---|
| T8 security_logs 구조화 | `7a8bf528` | 메인 직접 76 + PG 8 passed + APP_OK. 위임분 domains 4077·PG 675. action/target/detail JSONB + 인덱스, log_access 확장(additional_data 유실 결함 해소), 우선 호출부 7종 코드화, 감사 화면 필터·페이지네이션 |
| T9 감사 원장 수명주기 | `bac253cc` | 메인 직접 47 + PG 18 passed + APP_OK + 조인 EXPLAIN. 위임분 PG 692·domains 4113. order_events FK 분리(models·runner DDL 3중 정합), purge_audit_logs(730/365일·advisory lock·keyset·dry-run 기본), cron 체이닝 |
| T10 Sentry + access log | `7519a416` | 메인 직접 20 passed + **`import app` 후 sentry_sdk 모듈 0개 실측**(no-op 증명) + Procfile·start.sh diff 확인 |
| T11 잔여 구멍 | `a9b8ecb7` | 메인 직접 242 passed + APP_OK. 위임분 domains 전수 4144·PG 47. 사용자 삭제→비활성화(감사 actor 보존), FAILOPEN `SWALLOW_BY_CONTROL_FLOW` 180 무성장 게이트(인위 +1 red 실증) |
| T-CP3 최종 검증 | — | `pre_push_smoke.ps1` **exit 0** + hygiene 15 passed + `verify_result.py --json` **success: true** + AI_STATUS 갱신 |

## 가정하고 진행한 결정

1. T9 보존기간 확정: security_logs 730일 / notification_events·channel_delivery_logs·
   access_logs 365일. `order_events`는 purge 영구 제외.
2. T9 `channel_delivery_logs` 자기참조 FK(NO ACTION) 때문에 재귀 CTE survivor guard +
   자식 우선 삭제 도입(뮤테이션 검증으로 load-bearing 확인).
3. T11 가입거절(row 삭제) 경로는 FK 충족상 감사 필드 NULL 유지 — 비활성화 경로와
   분리(detach 함수 2종). Chat 3종 hard delete 불변.
4. T11 ③ EXTERNAL 감축 **미수행** — 대상 인벤토리가 타 세션 미커밋 상태(브리프 조건).
   EXTERNAL 22 baseline 불변, 전량 0은 별도 플랜 소관.
5. T10 Sentry 키 이름 기반 마스킹 추가(이벤트는 키/값 분리 구조라 문자열 패턴만으론
   로그인 form body 차단 불가) — 신설 파일 내 한정.
6. FAILOPEN baseline은 스펙의 179가 아니라 실측 180으로 고정.

## push·CI 상태

- **push 안 함**(승인 범위). 본 런 커밋 4 + 문서. 이전 런 잔여 문서 커밋 포함
  자기 몫만 cherry-pick push 권장(`push_own_session_commits.py --shas ...`).
- ⚠ 마이그레이션 3개 체인: `seclog_struct_00` → `auditlife_00`(둘 다 이번 런) —
  push 전 origin head 재확인 후 필요 시 재부모화(2차 런 학습).
- push 후 `gh run list`로 전 워크플로 green 확인(perf-gate 포함).

## 아침 체크리스트

1. push(자기 몫 cherry-pick) → CI 전 워크플로 green.
2. **Sentry 사용자 액션**: sentry.io 프로젝트 생성 → DSN 발급 → Railway FOMS-DEV
   `SENTRY_DSN` env 등록 → 스테이징 고의 예외 1건 수신·PII 부재 확인.
3. 운영 반영 전 확인: purge cron은 **dry-run 아님**(`--apply` 체이닝) — 첫 실행 전
   보존기간 값(730/365) 합의 여부 최종 확인.
