# 진행 원장 — 감사 로그 가독성·커버리지 (AUDIT-LOG P4)

- 스펙: `docs/specs/2026-08-08-audit-log-readability-coverage-design.md`
- 플랜: `docs/plans/2026-08-08-audit-log-readability-coverage-plan.md`
- 상태: **A·B·C 전부 운영 승격 완료** (A·B=production `47f270e6`, C=production `7ceedde4` PR #69).
  D 만 사용자 결정 대기(D1 계측 미착수·D2 BLOCKED).

| Task | 상태 | 완료 기준(통과할 명령/판정) | 커밋 |
|---|---|---|---|
| A1 표시 SSOT 모듈 신설 | DONE | 신규 17 passed + edit 관련 83 passed + APP_OK. 사전 이중정의 계약은 red 실증 후 이관으로 green | (아래 커밋) |
| A2 보안 로그 화면 적용 | DONE | 계약 9 passed + 배치 1쿼리 고정 + **운영 30일 전수 1,438건 역파싱 실패 0·개선 877건(60%)** + APP_OK | (A2·A3 커밋) |
| A3 거부 로그 분리 | DONE | 기본 숨김·스위치·페이지링크 계약 green(구조화·구형식 둘 다). 스테이징 실측은 push 후 | (A2·A3 커밋) |
| B1 주문 변경 구조화(before→after) | DONE | 4경로(field_update·regional·status·listing) 계약 5 passed + PII 최소성 계약 + 관련 170 passed | (B1·B2 커밋) |
| B2 문장 조립 SSOT 통일 | DONE | grep 계약 3 passed. 벌크 상태 로그 영문 코드 2곳 해소 | (B1·B2 커밋) |
| C1 커버리지 배선(묶음별) | DONE | 신규 계약 12 passed(행위 1건=원장 1행·행위자·대상·PII 부재) + 표시 SSOT 25 + domains 전수 4275 passed + APP_OK | `0a2c098e` |
| C2 커버리지 게이트 | DONE | 게이트 11 passed(인위 red 실증 2종 포함) + 인벤토리 3종 정합 44 passed + pre_push_smoke exit 0 | `6d840c52` |
| C1-b 잔여 72곳 전량 배선 | DONE | 커버리지 100%(AUDITED 142·EXEMPT 30·UNAUDITED 0) + 신규 계약 15 + domains 전수 4288 passed + smoke exit 0 | `414e2664` |
| D1 열람 규모 계측 | PENDING | 1주 수집 후 수치 보고 → 사용자 결정 | — |
| D2 열람 기록 배선 | BLOCKED | D1 결과에 대한 사용자 결정 필요 | — |

## Phase C 완료 (2026-08-10, deploy `0a2c098e`·`6d840c52`)

- **C1 배선 6묶음** — 결제 확인/해제, 시공 시작·완료·재작업, 생산 5종, AS 13경로,
  도면 전달·전달취소·창구 업로드 2종·blueprint 확정, 첨부 업로드·삭제·복구.
  첨부는 `emit_attachment_event` chokepoint 1곳에 배선(업로드 API·direct upload·삭제·복구가
  한 지점을 지난다). `META_UPDATED` 는 의도적 제외(원장 도배 방지).
- **표시 SSOT 확장** — `ACTION_LABELS` + `describe_order_action()`. 값 요약은
  `_summarize_text` 로 뽑아 `format_value` 와 공유(사전 이중화 금지 계약 유지).
- **근본 수정 1건**: `log_access` 가 항상 `get_db()` 를 부르던 탓에, 호출자 소유 세션을 쓰는
  함수(도면 전달)에서 `g.db` 가 새로 붙어 요청 teardown 이 세션을 닫고 호출자 ORM 인스턴스가
  detach 됐다(`test_hook_drawing_transfer` red 로 검출). `log_access(db=...)` 세션 주입 신설.
- **C2 게이트** — `tools/harness/audit_coverage_scan.py`(AST, 같은 모듈 고정점 + `foms/` import
  4단계 추적으로 얇은 위임 래퍼 오판 방지) + 인벤토리/allowlist + 계약 11건 + smoke 편입.
- **커버리지 실측**: total 172 / AUDITED 91 / EXEMPT 19 / UNAUDITED 72 → **52.9%**
  (C1 배선 전 41.3%). 면제 19건은 자동저장 draft·계산 프리뷰·텔레메트리·읽음 표시 등
  전부 사유 기재(빈 사유는 계약 red).
- **C1-b(2026-08-10, `414e2664`)**: 남은 72곳을 전량 배선해 **커버리지 100%** 달성
  (AUDITED 142 / EXEMPT 30 / UNAUDITED 0). 주문 대상 배선 + 비주문 대상(단가표·견적·채팅·
  알림·주소 학습)용 `describe_action()` 신설.
  - PII 경계: 실측 연락처·주소, 채팅 본문, 채널톡 발송 본문, 주소 학습 원문은 **미기록**
    ("무엇을 고쳤는지"만). 발송 본문 이력은 `channel_delivery_logs` 소유.
  - 면제 30건은 전부 사유 기재(업로드 세션·ticket 발급·DRAFT 생성/취소·자동저장·프리뷰·
    텔레메트리·읽음 표시 등). 사유가 부실하면 계약 테스트가 red.
  - 게이트는 이제 "UNAUDITED 증가 금지"가 아니라 **0 유지**를 강제한다 — 새 쓰기 라우트는
    기록하거나 사유를 적어 면제해야 머지된다.

## 운영 실측 후속 (2026-08-10, PR #71 — production `c2b4d00f`)

승격 직후 사용자가 운영 감사 화면에서 표시 결함 2건을 발견했다. **기록은 정확했고 읽기 시점
가공만 문제** — 데이터·스키마 변경 0.

1. `주문 #4704 (황인영) (황인영)` — 쓰기 경로 문장이 이미 고객명을 품는데
   `_annotate_order_mentions` 가 또 붙였다(행위 기록은 `detail.field` 가 없어 humanize 경로를 탄다).
   주문 언급 뒤에 이미 괄호가 오면 덧붙이지 않는다.
2. `AS 방문일: (없음) → (지움)` — `before=null`·`after=""` 는 둘 다 빈 값이라 무변경인데,
   표기 문자열이 달라 화살표 생략 조건을 통과했다. 결과만 표기하도록 수정.
   **값이 있던 것을 지운 경우는 종전대로 `이전 → (지움)`** (되돌림 근거 보존).

- 실측 문장을 그대로 고정한 회귀 4건 신설. deploy `1dbf17ce`(CI 4/4 green) → production `c2b4d00f`.
- 교훈: 쓰기 시점 SSOT와 읽기 시점 humanize가 **같은 정보를 두 번 적용**할 수 있다.
  새 표시 경로를 추가할 때는 "이미 가공된 문장인가"를 먼저 판정할 것.

## Phase C 운영 승격 (2026-08-10, PR #69 — production `7ceedde4`)

- **세션 커밋 cherry-pick 승격**(deploy 전체 merge 아님): 7커밋 + 인벤토리 재생성 1.
  `675bb288`·`2c13f3f3`·`0a2c098e`·`6d840c52`·`209234bc`·`414e2664`·`90b94a96`.
- 시공 대시보드 계측 커밋 2건(`7f442490`·`74b9878a`)은 **failopen 인벤토리 파일로만** 얽혀
  있었다 → 그 커밋을 끌고 오는 대신 **승격 트리 기준으로 인벤토리를 재생성**해 의존을 끊었다
  (미검증 perf 기능을 운영에 반입하지 않음). 이 방법을 다음 승격에서도 쓸 것.
- 검증: cherry-pick 충돌 0, 승격 브랜치 domains 전수 **4294 passed**, 게이트 103 passed,
  `pre_push_smoke` exit 0, PR 체크 2/2 green(pg-lane·perf-gate), 머지 후 운영 healthz 200·login 200.
- **마이그레이션 없음**(스키마 변경 0) — 운영 DB 작업 불필요.

## 운영 승격 (2026-08-10, PR #63)

- 사용자 명시 승인으로 **deploy 전체 승격**. 승격 커밋 `47f270e6`(병합 트리는 deploy 와 동일).
- 마이그레이션 7종 적용(alembic head `seclog_time_00`), `security_logs` 구조화 컬럼 4/4.
- 데이터 무손실 실측(7개 원장 전부 승격 전 이상), order_events CASCADE FK 제거 확인,
  `ix_security_logs_timestamp_id` 생성 확인, purge 즉시 삭제 0건, healthz 200.
- 백업 `c:/tmp/foms-backups/prod-pre-audit-promote-20260810.dump`(4.4MB·89테이블 검증).
- 함정: `-X theirs` 병합이 `auth/routes.py` 에 승인·거절 라우트를 **중복 정의**로 남겼다
  (옛 위치+새 위치) — Flask 엔드포인트 충돌 직전이었고, 트리를 deploy 기준으로 정정해 해소.
  전체 승격 시 `git checkout origin/deploy -- .` 로 트리 동일성을 강제 확인할 것.
- 미포함: 승격 직후 deploy 에 올라온 타 세션 커밋 `967097ac`(채널톡 AS PUSH).

## 결정 기록

- 2026-08-08 사용자: **"계획서만 먼저"** — 구현 착수 전 범위·순서 확정.
- 2026-08-08 사용자: 열람 기록 여부 **보류** — 실측(D1) 후 결정.
- 2026-08-09 사용자: **A+B 승인**. `/trash` 거부 282회는 권한 변경 없이 **로그 분리만**(A3).

## 실측 근거 (2026-08-08, 운영 읽기 전용)

- `security_logs` 24,605행 / 최근 30일 1,471건 / 거부 로그 474건(32%).
- 활성 29명 중 12명 최근 30일 보안로그 0건. wlsghv2 = 주문 변경 126건인데 보안로그 0건.
- 쓰기 라우트 172개 중 102개(59%) 감사 기록 호출 없음.
- 운영 DB에 `security_logs.action/target_type/target_id/detail` 컬럼 없음(T8 미승격).
