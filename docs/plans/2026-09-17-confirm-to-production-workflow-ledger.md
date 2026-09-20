# 고객 컨펌 → 생산 워크플로 정정 원장 (2026-09-17 ~ 2026-09-20)

브리프 `docs/plans/2026-09-17-confirm-to-production-workflow-brief.md` · 파이프라인 지도 `2026-09-17-pipeline-map-scout.md` ·
CEO 설계 정본 `2026-09-17-confirm-flow-ceo-design.json`(spec·contract·워커 브리프 4벌·페르소나 브리프·open_risks).

## 1. 사용자 결정 (2026-09-17)

- D1 고객 컨펌 승인 즉시 stage `CONFIRM → PRODUCTION`(새 명령 `CUSTOMER_CONFIRM`).
- D2 생산 보드 버킷 = 단계 + current run. 제작 시작 = run 발급(단계 무변경), 제작 취소 = run 종결(단계 유지).
- D3 승인은 됐는데 CONFIRM 에 남은 운영 주문(이다은 류)은 코드로 푼다(데이터 이관·운영 DB 조사 없음).
- 페르소나 검수는 deploy 푸시 뒤 스테이징 실서버에서.
- 스펙 승인 2026-09-17(사용자 "승인, 구현 시작").

## 2. 원인 (정찰 확정)

- "승인 완료" 판정이 세 곳에서 달랐다: 승인 라우트(assignee_approval·COMPLETED) / 생산 보드 표시(assignee 읽음) /
  생산 API 게이트 `check_quest_approvals_complete`(**team_approvals 만**). 이다은 = 담당자 승인 완료 → 화면은 제작 시작 버튼, 서버는 409.
- ERP 대시보드 퀘스트 칸 "-" = `resolve_current_quest` 가 COMPLETED quest 를 버렸다(완료 배지 코드 도달 불가).
- 모바일 링크 = `is_command_required_stage` 집합에 CONFIRM 이 남아 `approve_label=None`. 라우트는 이미 CONFIRM 을 허용(2026-09-09, 운영 #5193).

## 3. 구현 (37 파일, 워커 4 병렬 + 통합 검증 + 리뷰 2 + CEO 판정)

| 층 | 무엇 |
|---|---|
| 판정 SSOT | `erp_policy_quests.check_quest_approvals_complete` 모드 인지(별칭 매칭·COMPLETED 최우선·assignee → `ASSIGNEE` 토큰). `quest_transition_service._stage_quest_complete` 는 이 함수 재사용, `_find_stage_quest` 별칭 통일 |
| 전이 | `_STAGE_ADVANCE["CONFIRM"]=(CUSTOMER_CONFIRM, CONFIRM, PRODUCTION, False)`; 레지스트리 `CUSTOMER_CONFIRM`(event `CUSTOMER_CONFIRMED`); `_COMMAND_REQUIRED_STAGES={DRAWING}` 서비스·라우트 통일; `_NO_AUTO_ADVANCE_STAGES` 삭제; 죽은 `complete_confirm_quest` 삭제; `PRODUCTION_CANCEL` TransitionCommand 제거 |
| 승인 라우트 | 전이 직후 stale 재요청(팀 없음 + 종결 quest 의 다음 단계 == 현 단계) → 409 `ALREADY_TRANSITIONED`(CEO P1: 재요청이 PRODUCTION quest 를 만들어 제작 완료를 잠그던 것) |
| 생산 보드 | `production_stage_bucket_expr` = `erp_stage_code` + `production_runs` 상관 EXISTS(`.correlate(Order)`, run 분기 먼저 → EXISTS 1회); `_production_quest_sales_state` 가 SSOT 로 판정; `api_production_start` (a) PRODUCTION∧run 없음 → run 발급 (b) CONFIRM 호환 → 전이+run (c) 409; `api_production_cancel` = run SUPERSEDED, 단계 유지; uncomplete/rework 가 run 재개·발급 |
| 표시 | `resolve_current_quest` 가 완료 quest 를 `is_done` 로 돌려줌; CTA `CONFIRM="고객 컨펌 완료"` + `done_label`; PC 그리드·모바일 큐 카드·모바일 상세 완료 배지(`.erp-quest-done`, CSS 는 `erp-pro/04-...css`); 큐 카드 CONFIRM 링크 분기 삭제 → 인라인 승인 버튼 |
| PC JS | 승인 버튼에 `data-confirm`(서버 문구) + 클릭 즉시 잠금 + 실패 시 `(code)` 표면화. 핀 `erp-dashboard-quest.js`·`detail-dom.js`·`entry.js` → `20260920a`, `erp-pro.css`·`04-...css` → `20260920a` |
| 타임라인 | `CUSTOMER_CONFIRMED`="고객 컨펌 완료", `PRODUCTION_CANCELLED`="제작 취소" 라벨·문장 |
| 모델 | `uq_production_run_current` 에 `sqlite_where=text('is_current')` — SQLite 테스트 레인이 부분 유니크를 무시해 한 주문 두 번째 run 이 IntegrityError 였다(운영 DDL 무변경) |
| 테스트 | 신규 4파일(`test_confirm_to_production_{predicate,flow,board,display}.py`, 각 500줄 미만) + 기존 계약 교체 9파일(CONFIRM standalone 거부 → 전이, 무전이 → 전이, PRODUCTION 무 run 시작 200, 묘비 제작대기 등) |

## 4. CEO 판정 (2026-09-20, fix)

리뷰 findings 17 → 채택 8(P1 1·P2 4·P3 3)·기각/병합 9. fix 워커가 주간 한도로 죽어 총괄이 직접 반영:
1. P1 stale 재요청 → 409 `ALREADY_TRANSITIONED` + 테스트(같은 키·키 없는 연타·team 모드 부분 승인 음성 대조군).
2. P2 멱등 테스트 관용 제거(위 테스트).
3. P2 `_find_stage_quest` 별칭 통일 + 테스트.
4. P2 타임라인 라벨 2종 + 테스트.
5. P2 설계 JSON C11 `--timeout` 제거(pytest-timeout 미설치), MEMORY.md 61→60줄.
6. P3 그리드 완료 배지 인라인 style → CSS.
7. P3 버킷 CASE 순서(EXISTS 1회).
8. P3 PC 승인 확인창·연타 잠금·code 표면화(스펙 4항과 계약 C7 상충을 스펙 쪽으로).

기각 근거·잔여 위험은 설계 JSON 판정 기록과 아래 §6.

## 5. 게이트

총괄이 세션 워크트리(origin/deploy 기준, 최신 5커밋 리베이스 뒤) 직접 실행: `APP_OK` · `tests/domains` 7549 passed(파일 분할·정렬 수정 뒤 재실행 exit 0) · `tests/contracts+harness` 624 passed · `pre_push_smoke` EXIT=0(33타깃) · 인벤토리 가드 31 passed · node --check 0.
deploy `0cb601e7b` CI red 1건 = 네이버 집 발송기한 테스트가 오늘 날짜(09-20)와 충돌 — 우리 변경 무관, `474efaf08` 로 단언 수정 → CI ALL GREEN.

## 5b. 스테이징 페르소나 검수 (2026-09-20, 3명 병렬 + 종합)

원장 `docs/plans/2026-09-20-pipeline-persona-audit.md`(A/B/C 개별 보고·스테이징 브리프 동봉). **약속 6항 전부 확인.** 결함:
- F1 P1 **이번 범위** — 모바일 큐 카드·상세의 [고객 컨펌 완료]·[실측 완료] 가 담당자 이름 대조를 통과한 사람에게만 떴다(서버·PC 는 CS/SALES 팀이면 허용). `_compute_can_assignee_approve` 를 SALES_DOMAIN 에서 서버와 같은 팀 규칙으로 정렬 + 대조군 테스트(`2ff318fd1`).
- F2 P0 범위 밖(지도 #5·계약 C8, 기존) — 퀘스트가 아직 안 생긴 CONFIRM 주문에 `production/start` API 를 직접 부르면 컨펌 없이 200. 화면은 버튼을 숨긴다. 닫으려면 CONFIRM 호환 경로에서 퀘스트 없음 = 409 + 기존 테스트 8파일 픽스처 수정 — **다음 배치 결정 사항**.
- P1 범위 밖(기존) — `POST /quest`·`PUT /quest/status` 200 인데 미저장(flag_modified 없음); PC 그리드가 승인 직후 합성 생산 quest 에 [승인] 을 그려 STAFF 는 403; 팀 승인 단계(접수·생산·시공·CS) 모바일 승인 버튼 없음; SALES owner 가 도면 수령 확정을 못 함.
- P2 범위 밖 — 360° 타임라인이 엔진 전이 이벤트를 안 읽어 "기록 없음"; 이벤트 6종 "기타 변경"; v3 모바일 생산 큐 카드에 제작 시작/완료 없음.
- 스테이징 잔여물: 페르소나 주문 22건 soft delete·계정 12개 비활성. 허용 잔여물(삭제 주문 하위 run·첨부·감사 로그·R2 1px png 2개)은 보고에 id 기록.

## 6. 잔여 위험·범위 밖 (다음 배치)

- 운영에 PRODUCTION 인데 current run 없는 주문은 배포 직후 제작대기에 [제작 시작] 과 함께 보인다. 승격 전 스테이징 count:
  `SELECT count(*) FROM orders o WHERE o.erp_stage_code IN ('PRODUCTION','생산') AND o.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM production_runs r WHERE r.order_id=o.id AND r.is_current)`.
- 제작 취소의 뜻이 "컨펌 다시 받기" → "제작 시작 취소". 컨펌 재수령은 관리자 강제 단계 변경으로.
- CONFIRM 인데 quest 가 아예 없는 주문: 화면 '고객 컨펌 전', API start 는 200(계약 C8). SSOT 원칙과 어긋남 — 결정 필요.
- `PUT /quest/status` 로 STAFF 가 COMPLETED 를 수동으로 찍으면 게이트 통과(계약 C1 의도) — 권한 축소 여부 DECISIONS 기록 필요.
- 생산 summary_counts 슬라이스 캐시 무효화 부재(기존), PC 생산 상세 모달이 run 없는 PRODUCTION 에 [제작 완료](의도·P2).
- 지도 16건 중 미해결: CS→COMPLETED UI 부재 / `field_update status=COMPLETED` 게이트 우회 / CONSTRUCTION→CS quest 게이트 부재 / DRAWING→CONFIRM·construction/fail 엔진 우회 / `cs/confirm.py` 가 quest 를 안 닫음 / 모바일 실측 완료의 AS 열림 억제 부재 / 모바일 rework·cancel·uncomplete·시공불가 없음 / `stage_badge_label` CS→"AS" / `object.html` STAGE_LABELS 하드코딩.
- 승인 뒤 PRODUCTION quest 를 일부러 만들지 않는다(만들면 제작 완료가 생산팀 승인 뒤로 잠긴다).
