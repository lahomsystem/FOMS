# SPEC — 시공일 지난 적체 주문 매일 자동 완료 (2026-11-23)

> 상태: **승인(2026-11-23 사용자, 질문 창 "승인, 만들기") · 구현 완료**. 되돌리기 근거는 이벤트 `before` 에 workflow dict 까지 싣는다(설계보다 넓음 — 스냅샷 파일과 같은 모양). 요청: 사용자 2026-11-23 "매일 같은 시간 처리 해(오전 7시)" → 질문 창에서 "새벽 2시 밤 청소에 끼우기" 선택.
> 바탕 설계서: `docs/plans/2026-09-22-past-construction-bulk-complete-spec.md` (손으로 1~5차 운영 적용, 누계 587 + 506 + 101 + 21).

## 1. 왜

ERP 는 도면 → 영업 컨펌까지만 실사용하고 생산부터는 쓰지 않는다. 그래서 이미 시공이 끝난 주문이
도면·생산·CS 단계에 계속 쌓인다. 지금은 사람이 부탁할 때마다 손으로 도구를 돌린다(11-11 · 11-20 · 11-23).
매일 저절로 돌게 한다.

## 2. 무엇을 바꾸나 (판정 규칙은 그대로)

- 판정: 손으로 돌린 것과 같다. `erp_construction_date < 오늘(KST)` (`--cutoff-days 0`, 곧 "시공일이 어제까지").
- 모드: `main`(stage+status 완료) · `as_stage_only`(AS 주문은 stage 만, status·AS 칸 불변) — 그대로.
- 제외: 초안 · 보류 · 물류 진행(SCHEDULED·SHIPPED_PENDING) · 네이버 클레임 진행 · 이미 끝난 stage — 그대로.
- 알림톡·폰 알림·퀘스트 처리는 부르지 않는다 — 그대로.

## 3. 만들 것

1. `tools/cron/auto_complete_past_construction.py` (새 파일, 150줄 안쪽)
   - `DATABASE_URL` 로 접속(다른 밤 단계와 같다). `--apply` 없으면 plan 만 찍고 끝(다른 단계와 같은 계약).
   - 순서: 데이터 지문으로 환경 판별(운영/스테이징 둘 다 FOMS-cron 이 이 파일을 돈다 — 둘 다 같은 규칙으로 돈다)
     → `build_plan(cutoff_days=0)` → 대상마다 `apply_one` (기존 core 함수 재사용, 판정 코드 복사 금지).
   - **안전 상한**: 대상이 `--max-rows`(기본 200)를 넘으면 하나도 안 바꾸고 exit 3. 평소 하루 대상은 수십 건이다(11-23 21건).
     갑자기 많아지면(시공일 일괄 오입력 등) 사람이 보고 손 도구로 돌린다.
   - 로그 한 줄: `[auto_complete] env=… today=… cutoff=… planned=N main=… as_stage_only=… applied=… stale=… skipped={…}`.
     고객 이름·전화는 찍지 않는다(주문 id 만).
   - 행위자: 운영 `claude_master`(id57)와 같은 고정 시스템 계정이 아니라 env `FOMS_AUTO_COMPLETE_ACTOR_ID`. 없으면 exit 3(조용히 아무 이름으로 쓰지 않는다).
2. 되돌리기 근거: cron 컨테이너는 파일이 남지 않는다. 그래서 스냅샷 파일 대신 이미 쓰고 있는
   `order_events STAGE_OVERRIDE` payload(이전 stage·status·as_axis_status) + `security_logs` 감사행이 근거다.
   - batch 문자열을 날짜별로 바꾼다: `auto-YYYY-MM-DD` (지금은 core 에 `2026-09-22-backlog` 고정 — 인자로 받게 고친다. 손 도구 기본값은 그대로).
   - `bulk_complete_past_construction.py rollback --from-events --batch auto-2026-11-24` 를 더한다: 그 batch 의 이벤트에서 이전값을 읽어 되돌린다(workflow 원본 전체가 아니라 stage·status·stage_override 표식만 — 이 차이를 도움말에 적는다).
3. `tools/cron/nightly.py` `NIGHTLY_STEPS` 맨 끝에 한 줄: `NightlyStep("auto_complete_past_construction", "tools/cron/auto_complete_past_construction.py", ("--apply",))`.
   - 02:00 KST 실행. 07:00 과 같은 날이라 고르는 주문이 같다.
4. env: 운영·스테이징 FOMS-cron 서비스에 `FOMS_AUTO_COMPLETE_ACTOR_ID` 넣기(값은 구현 때 사용자에게 계정 확인).

## 4. 시험

- `tests/domains/` 순수: env 행위자 없음 → exit 3 · 상한 초과 → 쓰기 0 · `--apply` 없음 → 쓰기 0 · batch 문자열 날짜 반영.
- `tests/postgres/` PG 레인: main 1 · AS 1 · 제외 1(음성 대조군) 시드 → 자동 단계 1회 → main 완료 · AS status 바이트 동일 · 제외 불변.
  같은 날 두 번 돌려도 두 번째는 대상 0(멱등). `rollback --from-events` 왕복 뒤 stage·status 가 원래와 같다.
- `nightly.py` 단계 목록 계약 시험에 새 단계 등재.

## 5. 출시 순서

1. 구현 → 바뀐 파일 시험 → deploy 푸시(smoke · CI green).
2. 스테이징 FOMS-cron env 넣고 **수동 1회 실행**(Railway 에서 cron 즉시 실행) → 로그 한 줄 확인.
3. production 승격 PR(사용자 명시 요청 때만) → 운영 env 넣기 → 다음 날 02:00 로그와 단계 숫자 확인.

## 6. 알아 둘 것

- 시공일을 잘못 넣으면(예: 과거 날짜) 다음 날 새벽에 그 주문이 완료로 바뀐다. 지금 손 도구와 같은 위험이고, 상한(200)과 이벤트 되돌리기가 안전망이다.
- 실측 단계는 시공일이 없는 주문이 많아(11-11 212건) 계속 남는다 — 범위 밖.
- 범위 밖: 판정 규칙 바꾸기, 시공일 없는 주문, 비ERP 옛 주문, 고객 알림.
