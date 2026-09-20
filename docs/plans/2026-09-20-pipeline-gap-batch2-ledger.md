# 파이프라인 잔여 결함 4묶음 처리 원장 (2026-09-20, 배치 2)

브리프 `docs/plans/2026-09-20-pipeline-gap-batch2-brief.md` · 앞 배치 원장 `2026-09-20-measure-deadend-and-deferred-defects-ledger.md` ·
지도 `2026-09-17-pipeline-map-scout.md` · 검수 `2026-09-20-pipeline-persona-audit.md`.
작업 트리 `C:\tmp\foms-s-measure-deadend`(base origin/deploy, 직전 커밋 `246978993`).

## 1. 사용자 결정 (2026-09-20)

| # | 결정 |
|---|---|
| D1 | 경리팀(ACCOUNTING) 승인은 **필요한 칸(CS)에 기록**하고 실제 누른 팀을 함께 남긴다. |
| D2 | 실측 보드 [완료] 버튼은 **정식 경로(cs/complete)** 로 보낸다. 막히면 이유를 화면에 보여 준다. |
| D3 | 시공 완료: **사진·서명 증빙 게이트를 운영에도 켠다.** |
| D4 | 도면 수령 확정·시공 불가: **둘 다 정식 전이 경로로.** |
| D5 | 쓰이지 않는 `POST /api/orders/<id>/confirm/customer` **삭제**. |
| D6 | 모바일: **새 화면(v3) + 빠진 버튼 모두**(수정 제작·제작 취소·완료 취소·시공 불가). |
| D7 | 단계 배지 CS 는 **"CS"**. |

## 2. 삭제한 고객컨펌 API 의 설계 이력 (사용자 질문에 대한 조사 결과)

- **2026-02-07 출생**(`6ce8a03e0`, apps/erp_beta.py): 프로세스 블루프린트 V3 의 E 단계(고객컨펌) 완료 처리. 짝은 `drawing/request-revision`. 처음엔 실제로 **stage·status 를 PRODUCTION 으로 옮겼다**(이력 note "고객 컨펌 완료 → 생산 단계로 이동").
- **2026-02-13 설계 변경**(`99c262f16`, 같은 커밋에서 생산 대시보드에 `is_sales_approved` 도입): 주석과 함께 단계 이동을 잘라 냈다 — "CONFIRM 단계 유지, 생산팀이 제작 시작을 누를 때만 PRODUCTION". 이때부터 이 API 는 **기록 전용**이 됐다.
- 그 뒤 quest 승인 경로가 같은 `blueprint.customer_confirmed` 기록 + quest 종결을 맡았고, 2026-09-17 배치에서 승인이 CONFIRM→PRODUCTION 전이까지 하게 되면서 완전히 대체됐다.
- **화면 호출자는 출생부터 0건**(templates·static 전 이력 grep 0). 남아 있던 문제는 quest 를 안 닫아 제작 시작 게이트가 계속 막히는 것.
- 기록 키(`blueprint.customer_confirmed`)는 도면 리비전 감사(`audit_drawing_revisions.py`)가 읽으므로 유지되고, 그 쓰기는 `foms/api/quest.py` 가 한다.

## 3. 구현 (60 파일, 워커 4 병렬 + 통합 검증 + 리뷰 2 + CEO 판정 + fix)

| 계약 | 무엇 |
|---|---|
| C-A1 팀 별칭 | 신규 `quest_approve_authz.approval_slot_team(...)` — 승인 슬롯 키를 **필수 팀 중 actor capability 가 만족하는 팀**으로 고르고, 슬롯에 `by_team`(정규화 전 원문 팀)을 남긴다. 읽기 술어(`check_quest_approvals_complete` 정확 일치)는 그대로. ACCOUNTING STAFF 승인이 CS 칸을 채워 단계가 넘어간다. |
| C-A2 담당자·팀 버튼 | PC 그리드·태블릿 시트의 `can_edit_erp or ...` 제거 → `can_assignee_approve` 단독, 팀 버튼은 `approvable_teams`. 문구도 "(승인 권한 없음)". |
| C-B1·B2 완료 경로 | 신규 `foms/services/orders/complete_path_policy.py`(추가 쿼리 0) — `complete_block_reason`·`build_complete_ctas`·`rejects_completed_field_write`. 실측 3보드 [완료] 는 CS 단계면 `cs/complete`, 아니면 사유를 보여 주고 비활성. quest 미승인이면 "승인하러 가기" 딥링크. 서버는 `update_order_field`·`update_order_status`·`bulk_update_order_status` 세 곳 모두 메인 파이프라인 주문의 `status=COMPLETED` 를 409 `USE_CS_COMPLETE` 로 거부(AS·출고 축 값은 술어에 들어오지도 않는다). |
| C-B3 증빙 게이트 | `FOMS_CONSTRUCTION_GATE_ENABLED` 기본값 False→**True**. 화면은 `missing` 코드를 사람 말("완료 사진 2장"·"고객 서명")로 옮겨 보여 준다. |
| C-C1 도면 수령 확정 | 신규 명령 `DRAWING_RECEIPT_CONFIRM`(DRAWING→CONFIRM, event `DRAWING_RECEIPT_CONFIRMED`) + `drawing_receipt_command.py`. 순서 고정: 가드 → 전이 → 도면 축·파일 정리 → 이벤트 → commit(전이 실패 시 파일 정리가 일어나지 않는다). 도면만 TRANSFERRED 이고 단계가 DRAWING 이 아니면 **단계를 되돌리지 않고** 도면 축만 확정(`stage_moved: false`) — 옛 코드의 조용한 역행 제거. 타임라인 라벨 등재. |
| C-C2 시공 불가 | 단일 명령 + 다중 to_values 로 엔진 전이(`expected_from=CONSTRUCTION`), 이중 영수증·이중 버전 없이 기존 `execute_order_mutation` 과 한 경계. 캐시 family 채움. |
| C-C3 죽은 API | `foms/api/cs/confirm.py` 삭제 + 블루프린트 등록·writer 예외 태그·네임스페이스 계약 정리(근거는 §2). |
| C-D1·D2 모바일 | v2 생산 큐에 [수정 제작]·[제작 취소]·[완료 취소], 시공 큐에 [시공 불가]. v3 화면에 생산·시공 액션 신설(같은 `data-action` 이름으로 기존 위임 재사용). 사유 입력은 `window.prompt` 대신 공용 시트(`foms_reason_sheet.html` + `foms-reason-sheet.js/css`). 버튼 노출 술어는 신규 `can_act_construction`(= 서버 데코레이터와 같은 조건). v3 진입 관측은 하루 1행, **짧은 별도 세션**으로 기록. |
| C-D3 라벨 | `stage_badge_label` CS→"CS", `object.html` JS 라벨표에 CS·COMPLETED·AS 보강. |

신규 테스트 5파일(팀 별칭 슬롯·완료 경로·도면 전이·시공 불가 전이·모바일 액션) + 기존 계약 갱신.

## 4. CEO 판정 (fix 1회, 채택 12·기각 4)

채택 P1 2건이 계약의 두 잣대를 깨서 ship 이 아니라 fix 였다.
1. **완료 우회로가 하나 더 있었다** — `update_order_status`·`bulk_update_order_status` 도 COMPLETED 를 직접 썼다. 세 진입점 모두 같은 술어로 막았다.
2. **v3 시공 버튼 술어가 서버보다 좁았다** — 화면이 시공팀·관리자만 보고 있어 CS·영업팀은 버튼이 0개였다(서버는 200). `can_act_construction` 으로 통일.

그 밖 P2·P3 10건(멱등 replay 중복 실행, v3 관측 세션 경계, 막힌 버튼 사유가 title 뿐, 증빙 missing 사람 말, 슬롯 폴백이 승인 칸 덮어쓰기, drift 경로 이력 시각, 시공 불가 payload 상세, 단계 원천 불일치, v2 생산 버튼 권한, 그리드 대조군 테스트) 반영.

기각: 딥링크 막다른 길 주장(서버가 `focus_order` 를 처리한다), `cta=None` 죽은 코드 주장(계약 테스트가 그 경로를 잠근다), `CONSTRUCTION_REWORKED` axis 가 타임라인 집계를 바꾼다는 주장(최초 도달만 기록).

## 5. 게이트 (총괄이 직접 재실행)

| 게이트 | 결과 |
|---|---|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `python -m pytest tests/domains -q` | 7700 passed, 5 skipped |
| `python -m pytest tests/contracts tests/harness tests/services tests/security -q` | 2606 passed |
| `scripts/ops/pre_push_smoke.ps1` | **EXIT 0** (33 targets) |

인벤토리 4종(writer·state·failopen·감사 커버리지) 재생성 후 `--check` exit 0, 파일 크기 래칫 신규 초과 0(`erp_orders_draftsman.py` 499/500).

## 6. 운영 영향(승격 전 고지 필요)

- **실측 3보드 [완료] 버튼이 CS 단계가 아닌 주문에서 막힌다.** 그 경로로 바로 완료하던 업무는 시공 완료 → CS 승인 → 완료 2단계를 밟아야 한다. 화면이 막힌 이유와 "승인하러 가기" 링크를 보여 준다.
- **시공 완료에 사진 2장 + 고객 서명이 필수가 된다.** 운영에 그 변수가 없어 배포 즉시 적용된다. 끄려면 `FOMS_CONSTRUCTION_GATE_ENABLED=false`.
- ADMIN 이 팀 지정 없이 승인하면 이제 자기 팀이 아니라 **아직 승인 안 된 필수 팀** 칸이 채워진다.

## 7. 잔여 위험·다음 배치

- `CONSTRUCTION_REWORKED` 는 타임라인 라벨표에 여전히 없다(원래 구멍) — "기타 변경" 으로 뜬다.
- terminal 상태 목록이 매크로와 `complete_path_policy.py` 두 벌이다(드리프트 위험).
- 도면 drift 경로(`drawing_status=TRANSFERRED` 인데 단계가 DRAWING 아님) 실제 건수는 스테이징에서 한 번 세 봐야 결정이 맞았는지 확인된다.
- v3 화면에서 숨겨진 데스크톱 폴백 안의 스크립트가 실행된다는 가정은 마크업 구조 판단이다 — 스테이징 실기기·실화면 연기 테스트로 확인 필요.
- 앞 배치에서 이월된 것: 팀 alias `effective_team` 의 다른 경로, `check_quest_approvals_complete` 첫 일치 정렬 통일, PC 그리드 담당자 버튼 추가 정리, F8 v3 코호트 실측.
