# 관리자 전 단계 강제 변경 원장 (ADMIN-OVERRIDE-01, 2026-09-21)

브리프 `docs/plans/2026-09-21-admin-full-stage-control-brief.md` · 앞 배치 원장 `2026-09-20-measure-deadend-and-deferred-defects-ledger.md` · `2026-09-20-pipeline-gap-batch2-ledger.md`.
사람용 도식(주문 일생) https://claude.ai/artifact/TV4bDyeMpijUbdVNS7LZc2 — "되돌아가는 길" 절은 이 배치 승격 뒤 갱신한다.

## 1. 사용자 지시와 결정

> "관리자는 모든 단계를 변경 할 수 있어야 돼"

| # | 결정 |
|---|---|
| D1 | 범위는 **삭제까지 포함** — 본공정 8단계 + AS 접수·AS 처리·AS 완료 + 삭제됨. |
| D2 | 관리자는 일반 화면에서도 역행·건너뛰기가 바로 된다. |
| D3 | 관리자는 업무 게이트(시공 증빙·컨펌 승인·CS 승인·보류·AS 열림·완료 단계 제한)를 뚫고 진행할 수 있다. |
| D4 | 뚫을 때는 **사유 필수 + 이력에 "관리자 강제 진행"** 이 보인다. |

## 2. 착수 전 실측 — 관리자가 막히던 자리 10곳

강제 변경은 본공정 8단계로 제한(`stage_override.py` 의 `MAIN_PIPELINE_CODES`, role 예외 없음) · 일반 화면 역행·건너뛰기 403(`status.py`·`field_update.py`) · 완료 409 `USE_CS_COMPLETE` · 도면 전달 전 수령 확정 400 · 도면 단독 승인 409 `COMMAND_REQUIRED` · 제작 시작의 컨펌 승인 409 · 제작 완료의 생산 승인 409 · 보류 409 · 시공 증빙 400(기본 ON) · CS 완료의 단계·승인·보류·AS 409. 엔진의 `emergency_override` 는 어떤 라우트도 노출하지 않았다.

## 3. 계약 (CEO 확정)

### C0 두 축을 섞지 않는다
- **권한 축 `admin_override`**: 업무 게이트를 사람 판단으로 뚫는다. ADMIN 전용, 사유 필수.
- **정합 축(뚫을 수 없다)**: If-Match(mutation_version) 409 · 잠금 아래 `expected_from` 불일치 · `to_values` 위반 · `confirm != true` · 빈 사유 · 동일 단계 · 일괄 1000건 상한 · 삭제된 주문 404 · **중복 발급 계열**(이미 제작중, `ALREADY_STARTED`).
- 기존 `emergency_override` 는 **권한 소유 축**(MANAGER 의 도메인·팀 소유 넘기)이라 의미·시그니처를 그대로 뒀다. 엔진 인자는 세 번째 축(인접성 완화)이고 라우트가 `admin_override` 를 받아 엔진 호출 때만 번역한다. `admin_override` 는 `emergency_override` 를 켜지 않는다 — 켜면 매니저가 업무 게이트를 뚫는 길이 생긴다.

### C1 전달 방식
본문 키 `{"admin_override": true, "override_reason": "<사유>"}`(없으면 같은 본문의 `reason`). 헤더가 아닌 이유: 일괄 요청은 본문이 본체이고, 영수증 `request_hash` 가 본문만 해싱해 헤더로 실으면 평소 요청과 뚫은 요청이 같은 해시로 서로를 덮는다. 일괄은 최상위 한 벌만 — 주문별 override 는 400 `ADMIN_OVERRIDE_SHAPE`. 비관리자 403 `ADMIN_ONLY`, 빈 사유 422 `REASON_REQUIRED`, 둘 다 업무 게이트보다 먼저 판정한다. 판정 정본은 신규 `foms/services/orders/admin_override.py`.

### C2 AS 3종 목표
raw stage 쓰기 금지, `as_cycle_service` 명령만 쓴다. 현재 cycle 상태별 분기표로 확정(없음/접수/진행/완료 × 목표 3종). 진행 중 AS 를 접수로 되돌리는 길은 **admin_override 로도 안 뚫린다** — 권한이 아니라 상태기계에 그 명령이 없다. 일괄에서 AS 목표는 `include_as` 와 무관하게 AS overlay 주문을 항상 포함한다.

### C3 DELETED 목표
`soft_delete_order` + 휴지통 미러 4종(원래 상태 보존·`status='DELETED'` 미러·감사행·커밋 뒤 캐시 무효화)을 신규 `foms/services/orders/trash_mirror.py` 한 곳으로 모았다. 휴지통 목록이 아직 옛 상태 술어를 쓰기 때문이다. ADMIN + `admin_override` 필수. 일괄은 한 건이라도 실패하면 전체 롤백.

### C4 완료는 한 길만
신규 `foms/services/orders/cs_complete_service.py::complete_order_as_cs` 로 CS 완료 본체를 뽑아, 강제 변경·상태 변경·일괄·CS 라우트가 모두 그 함수를 탄다. 상태만 COMPLETED 이고 뒤가 빈 주문을 만들지 않는다.

### C5 기록
`ADMIN_OVERRIDE_USED` 이벤트 1행(뚫은 게이트 목록·사유·축·from/to), 타임라인 라벨 "관리자 강제 진행", 거부된 시도는 SecurityLog.

### C6 화면
거부 응답을 받으면 **관리자에게만** 2차 확인 + 사유 입력(배치 2의 공용 사유 시트 재사용) 후 같은 요청에 `admin_override` 를 실어 재전송. 비관리자 화면은 그대로.

## 4. CEO 판정 (fix 1회, 채택 12·기각 3)

P0 2건이 계약 C0 을 깼다.
1. **일괄 강제 완료가 앞 건을 조용히 되감았다** — 한 건 실패 시 세션 전체가 롤백되는데 루프가 계속 돌아 응답 숫자와 DB 가 어긋났다. 전체 롤백으로 고쳤다.
2. **강제 변경의 완료 목표가 빈 사유 가드를 잃었다** — 완료 목표를 `apply_stage_override` 밖으로 빼면서 유일한 검사 자리가 안 불렸다. 테스트 7793건으로도 안 잡혔다.

그 밖 P1·P2 10건: 단건 완료 목표의 동일 단계 가드, 모달에서 완료 목표에 `admin_override` 미탑재, 거부 시도 감사 비대칭(8곳은 남기고 3곳은 안 남김), 뚫어서 완료한 단건의 상태 변경 감사 누락, 사유 시트가 빈 사유를 통과시키던 것, 생산 3라우트(수정 제작·제작 취소·완료 취소) 배선 누락, 출고 대시보드 핀, 개행 10파일.

기각 3: role 대문자 정규화(재시도 화면도 같은 정규화를 한다), `window.MY_ROLE` 인라인(기준선에 이미 4곳, 이 배치가 만든 이탈이 아니다), 신규 모듈 6개가 소유권 표에 없다는 지적(계약이 신설을 지시한 파일들이다).

## 5. 게이트 (총괄이 직접 재실행)

| 게이트 | 결과 |
|---|---|
| `python -c "import app; print('APP_OK')"` | APP_OK |
| `pytest tests/domains -q` | 7815 passed, 5 skipped |
| `pytest tests/contracts tests/harness tests/services tests/security -q` | 2606 passed |
| `scripts/ops/pre_push_smoke.ps1` | **EXIT 0** (33 targets) |

두 P0 수정은 코드로 직접 확인했다(일괄 완료 실패 시 `db.rollback()` 후 즉시 반환, 빈 사유 가드가 확장 목표 경로에 재배치).

## 6. 운영 영향 — 사용자 확인 필요

- **매니저는 강제 변경으로 완료를 만들던 길을 잃는다.** 완료 목표가 CS 완료 서비스를 타므로 CS 승인·보류·AS 검사가 걸리고, 뚫으려면 관리자 권한이 필요하다. 결정 문장이 "관리자" 였으므로 그대로 구현했다 — 매니저에게도 줄지는 미결.
- 관리자는 사유를 적으면 어떤 단계로도 보낼 수 있다(AS 3종·삭제 포함). 삭제는 휴지통으로 가고 복구된다.
- 진행 중 AS 를 접수로 되돌리는 길은 없다(상태기계에 없다).

## 7. 절차에서 배운 것

- **동결 뒤 워커에게 메시지를 보내면 그 워커가 다시 깨어나 편집한다.** 이번에 총괄이 그렇게 네 번 깨웠고, 8분짜리 전량 게이트가 두 번 헛돌았다(계층 래칫 4건·자산 핀 1건이 실행 중 편집 때문에 빨강→초록). 동결을 선언했으면 총괄도 침묵한다.
- 통합 검증자가 잡은 가장 큰 것: **바뀐 JS 6개가 옛 자산 핀으로 실려, 서버는 뚫는데 화면에 재시도가 안 뜨는 상태**였다. 재시도 배선 JS 를 싣는 템플릿 줄을 전수로 검사하는 가드를 추가했다.
- 500줄 래칫 때문에 강제 변경 코드가 네 파일로 쪼개졌고 여유가 7~26줄이다. 다음 사람은 줄 수부터 재야 한다.

## 8. 다음 배치

- **DELETE-TRASH-01**: 휴지통 목록이 아직 `status=='DELETED'` 술어라 삭제를 두 곳에 쓴다(`deleted_at` + 미러). canonical 화는 별건.
- 매니저 권한 범위 결정.
- 앞 배치 이월분: `CONSTRUCTION_REWORKED` 타임라인 라벨, terminal 상태 목록 이중화, 도면 drift 건수 실측, v3 코호트 실측.
