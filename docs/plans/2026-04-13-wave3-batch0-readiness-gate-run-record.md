# Wave 3 Batch W3-B0 — Readiness gate + priority queue lock

> **batch ID:** W3-B0  
> **risk axis:** docs / truth (queue lock only)  
> **live truth source:** `foms/platform/blueprints.py`, Wave 2 run records W2-B1 … W2-B6  
> **실행일:** 2026-04-13

## Scope lock

- 본 배치는 **Wave 3 우선순위 큐 확정 + pilot context lock**만 수행한다.
- 런타임 코드·`blueprints.py`·controlling spec 본문·Wave 3 plan 파일은 **변경하지 않음**.

## Inputs consumed

| 입력 | 존재 | 비고 |
|------|------|------|
| W2-B1 `2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` | ✅ | truth map evidence |
| W2-B2 `2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md` | ✅ | spec bridge debt |
| W2-B3 `2026-04-13-wave2-batch3-blueprint-registry-clarity-run-record.md` | ✅ | registry 주석 |
| W2-B4 `2026-04-13-wave2-batch4-apps-thin-adapter-contract-run-record.md` | ✅ | AM-001…004 adapter matrix |
| W2-B5 `2026-04-13-wave2-batch5-readme-coverage-run-record.md` | ✅ | FR20 앵커 |
| W2-B6 `2026-04-13-wave2-batch6-closeout-run-record.md` | ✅ | Wave 3 shortlist handoff |
| `foms/platform/blueprints.py` | ✅ | 등록 순서·import 경로 live truth |

**Stop 조건:** 위 여섯 W2 run record 중 하나라도 없으면 중단 — **해당 없음 (모두 존재).**

## Wave 2 key normalization (registry lane / spec domain / FR20 context key)

아래 authoritative queue 표의 각 행에 동일 스키마를 적용한다.

- **registry lane:** `blueprints.py` 등록 블록에서 식별한 API/페이지 경계 (본 배치는 **API import symbol** 기준).
- **spec domain:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` Wave 3(§2.9) — **API canonicalization**.
- **FR20 context key:** 로컬 README가 필요할 때 쓰는 문맥 키; 단일 모듈 선행 시 `N/A(single module)` 허용.

## Contract table (readiness — public surface 요약)

본 배치의 “contract”는 **등록 경로·blueprint 심볼 freeze** 수준이다. 세부 HTTP contract는 `W3-B1` 이후 파일별 batch에서 잠근다.

| Context (registry lane) | module path (import) | blueprint symbol | url_prefix (관찰) | 등록 소스 |
|-------------------------|----------------------|------------------|-------------------|-----------|
| files | `apps.api.files` | `files_bp` | `/api/files` | `blueprints.py` L51, L109 |
| address | `apps.api.address` | `address_bp` | `/api/address` | L52, L110 |
| orders | `apps.api.orders` | `orders_bp` | `/api` | L53, L111 |
| notifications | `apps.api.notifications` | `notifications_bp` | (orders 인접) | L54, L112 |
| erp_shipment_settings | `apps.api.erp_shipment_settings` | `erp_shipment_bp` | `/api/erp/shipment-settings` | L55, L113 |
| erp_measurement | `apps.api.erp_measurement` | `erp_measurement_bp` | `foms.api.measurement` alias | L56, L114 |
| erp_map | `apps.api.erp_map` | `erp_map_bp` | `/api` | L57, L115 |
| erp_orders_lane | `apps.api.erp_orders_*` (다수 bp) | `*_bp` | 각 전용 prefix | L58–65, L116–123 |
| personal_board | `apps.api.personal_board` | `personal_board_bp` | `/api/personal-board` | L66, L124 |
| storage_dashboard | `apps.storage_dashboard` | (page) | — | L68 |
| chat | `apps.api.chat` | `chat_bp` | `/api/chat` | L69, L128 |
| wdcalculator | `apps.api.wdcalculator` | `wdcalculator_bp` | `/api/wdcalculator` | L70, L129 |
| backup | `apps.api.backup` | `backup_bp` | `/api/backup` | L71, L130 |
| attachments | `apps.api.attachments` | `attachments_bp` | `/api/attachments` | L75, L135 |
| tasks | `apps.api.tasks` | `tasks_bp` | `/api/tasks` | L76, L136 |
| events | `apps.api.events` | `events_bp` | `/api` | L77, L137 |
| quest | `apps.api.quest` | `quest_bp` | `/api/quest` | L78, L138 |
| erp_orders_blueprint | `apps.api.erp_orders_blueprint` | `erp_orders_blueprint_bp` | `/api/erp/orders` | L79, L139 |
| erp_orders_structured | `apps.api.erp_orders_structured` | `erp_orders_structured_bp` | `/api/erp/orders` | L80, L140 |
| channel_family | `apps.api.channel_*` | 다수 bp | 각 prefix | L87–94, L147–153 |
| erp_estimates | `apps.api.erp_estimates` | `erp_estimates_bp` | `/api/erp/estimates` | L95, L154 |
| debug | `apps.api.debug` | `debug_bp` | `/api/debug` | L96, L155 |

## Hidden side effect inventory (queue-level 요약)

| Context | hidden side effect 요약 | provisional tier |
|---------|-------------------------|-------------------|
| files | presigned/redirect, storage provider 분기, 경로 검증 | Tier 1 low-risk |
| address | Kakao 외부 HTTP, 쿼리 폴백 | Tier 1 low-risk |
| orders | mutation 다수, 정책 엔진 | Tier 0 precedent / Tier 3 mutation |
| personal_board | DB 집계 read-only, session | Tier 2 medium-risk |
| events | GET 다수 + **POST revert** + `flag_modified` | Tier 2 / revert lane Tier 3 |
| chat | Socket.IO binding | Tier 3 |
| attachments | storage/upload | Tier 3 |
| channel_* | webhook | Tier 3 |

## FR19 decision (merge vs extend vs add)

- 본 배치는 **문서만** — 코드 merge/extend/add **해당 없음**.

## Changes made

- `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md` (본 파일)

## Spec §4 delta summary

- product file delta: 없음  
- wrapper file delta: 없음  
- test file delta: 없음  
- canonical target: (후속 `W3-B2+`에서 파일별 기록)  
- removal or merge target: 없음  
- new shim retirement wave: 없음  
- local README update: 없음  

## Verification

| 검사 | 결과 |
|------|------|
| W2-B1…B6 파일 존재 | ✅ |
| `blueprints.py`와 충돌 시 live truth 우선 | ✅ (본 기록은 `blueprints.py` 기준) |
| docs-only | ✅ |

## FR20 / README gate

- 본 배치는 코드/패키지 증가 없음 → **FR20 신규 README 불필요.**

## Test footprint decision

- 테스트 변경 없음.

## Direction Lock answers (spec §2.8.1)

1. **SSOT 선명화:** Wave 3 실행 큐를 `blueprints.py`+W2 evidence로 재계산해 선명화 — **예**  
2. **split-brain:** 큐만 잠그고 구현은 후속 batch — **감소 방향, 임시 증가 없음**  
3. **delete/merge/extend:** 코드 파일 추가 없음 — **해당 없음**  
4. **chunk 크기:** 새 product 파일 없음 — **해당 없음**  
5. **파일 수:** 증가 없음 — **예**  
6. **순증가 제거 계획:** 해당 없음  
7. **local README:** 변경 없음 — **해당 없음 (문서 batch)**  
8. **10회 반복:** 큐 규율은 폴더 정리에 유리 — **예**  
9. **경계 선명:** API-only Wave 3 경계 유지 — **예**  
10. **기능 변경 혼입:** 없음 — **구조/문서 only 예**

## Drift / stop decision

- **Stop 조건 트리거 없음.**

## Authoritative queue (Wave 3 처리 관점 — 핵심 행)

| registry lane | spec domain | FR20 context key | module path | blueprint symbol | owner state (W2-B4) | hidden side effect 요약 | provisional tier | canonical target (Wave 3 계획) | W2 evidence |
|---------------|-------------|------------------|-------------|-------------------|---------------------|--------------------------|------------------|----------------------------------|-------------|
| files | API canonical | `files` | `apps.api.files` | `files_bp` | legacy → **pilot** | presigned/redirect/storage | Tier 1 | `foms/api/files` | W2-B6 shortlist #1, BD-008 |
| address | API canonical | `address` | `apps.api.address` | `address_bp` | legacy | Kakao proxy | Tier 1 | `foms/api/address` | W2-B6 shortlist #1 |
| erp_measurement | API canonical | `measurement` | `apps.api.erp_measurement` | `erp_measurement_bp` | **alias shim** (AM-002) | mutation lane 분리 필요 | Tier 0 / 2–3 | `foms/api/measurement` | AM-002, W3 plan §2.3 |
| orders | API canonical | `orders` | `apps.api.orders` | `orders_bp` | **thin adapter** (AM-003) | mutation | Tier 0 precedent | `foms/api/orders` | AM-003 |
| personal_board | API canonical | `personal_board` | `apps.api.personal_board` | `personal_board_bp` | legacy | DB read aggregate | Tier 2 | `foms/api/personal_board` | W3 plan §2.3 |
| events | API canonical | `events` | `apps.api.events` | `events_bp` | legacy | **POST revert** | Tier 2 (+mutation) | defer subset / Wave 4+ | W3 plan §2.3 |
| (기타 high-risk) | API canonical | 각종 | 아래 표 참조 | — | legacy | storage/realtime/webhook | Tier 3 | `W3-B6` defer | W2-B6 |

## Pilot lock decision

**Explicit check (`files` low-risk):**

- Route는 **GET 위주**, `@login_required` 적용.
- **DB 쓰기·`flag_modified`·webhook·realtime 없음** (파일 바이너리 스트리밍/redirect만).
- **presigned URL**은 R2/S3 **읽기 URL** 발급; 로컬은 앱 경로 JSON으로 반환 — 저장소 **쓰기 트랜잭션 없음**.
- 경로 traversal 가드(`..`, 절대경로) 존재 — **§2.2 보조 규칙** 충족.

**결론:** `files`가 Tier 1 low-risk 조건을 충족하므로, Wave 3 **pilot context = `files`** 로 lock한다 (실행 계획 §2.4 tie-break #1 준수).

## this plan §2.3 snapshot 대비 변경 row

| 항목 | §2.3 스냅샷 | W3-B0 authoritative 판정 | 비고 |
|------|-------------|---------------------------|------|
| first pilot | `files` (조건부) | **`files` 확정** | `blueprints.py` + `apps/api/files.py` 증거로 low-risk 유지 |
| W2-B6 shortlist 순서 | notifications·erp_map이 2·3위 | Wave 3 실행 계획 **§2.4 files→address→personal_board→events** 가 pilot 순서를 결정 | **Override:** W2-B6는 “후보 우선순위 힌트”; Wave 3는 **계획서 tie-break**가 API pilot 순서를 지배. 충돌 아님(다른 wave 목적). |

## W2-B6 shortlist vs Wave 3 tie-break (override 기록)

- W2-B6는 `files`+`address`를 1순위로 명시 — **Wave 3 §2.4와 정합.**
- W2-B6의 2순위 `notifications`는 Wave 3 본 실행 계획 **§4.2**에 따라 **W3-B6 defer** (mixed POST) — 본 배치에서 pilot으로 올리지 않음.

## Unresolved surface list (Wave 3 본 실행에서 즉시 처리 안 함)

- `notifications`, `tasks`, `erp_map`, `erp_estimates`, `attachments`, `chat`, `channel_*`, `backup`, `quest`, `debug`, `wdcalculator`, `erp_orders_*` mutation family — **W3-B6 defer register**로 이관 예정.

## Next step or defer

- **`W3-B1`:** `files` public contract + hidden side effect **line-by-line freeze** (`apps/api/files.py` 읽기 전용).

---

**touched files:** `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md`  
**verification result:** PASS (docs-only)  
**residual risk:** 없음 (후속 batch에서 contract 정밀화)
