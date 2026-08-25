# parties.orderer 이름 축 분리 (ORDERER-AXIS-01)

- 작성: 2026-08-20
- 상태: **설계 — 사용자 승인 대기**
- 배경 원장: `docs/plans/2026-08-13-naver-order-ingest-ledger.md` §T15-O
- 선행: `ec6b22a9`(폼 저장 parties 보존) · `dd148b1f`(유실 연락처 복구)

## 1. 문제 — 한 키에 두 뜻

`structured_data.parties.orderer.name` 을 두 주체가 다른 뜻으로 쓴다.

| 쓰는 쪽 | 넣는 값 | 근거 |
|---|---|---|
| ERP 편집 폼 | **발주사**(라홈/하우드/직접입력) | `templates/orders/partials/erp_order_tab.html:172-176` (셀렉트 옵션이 라홈·하우드) |
| 네이버 수집 | **주문자 사람 이름** | `foms/services/integrations/naver_commerce/mapping.py` `build_structured_data` |

스테이징 실데이터(2026-08-20 SQL 조회): 주문 4462·4461 의 발주사 칸에 개인 이름이,
4242 에는 `라홈` 이 들어 있다. 같은 컬럼에 두 종류 값이 섞여 있다.

## 2. 영향 — 발주사 값으로 갈리는 로직

`parties.orderer.name` 은 `foms/services/erp_display.py:349` 에서 `order.orderer_name`
으로 투영되고, 아래가 그 값으로 분기한다. 수집 주문은 값이 사람 이름이라 **전부 '라홈이
아님' 쪽으로 떨어진다**.

| 소비자 | 위치 | 지금 수집 주문에서 벌어지는 일 |
|---|---|---|
| 알림톡 브랜드 프로필 | `kakao_alimtalk.py:353` | 라홈 주문인데 **하우드 프로필로 발송** |
| 도면 양식 로고 | `drawing_wizard_defaults.py:128` | 하우드 로고가 찍힌다 |
| 실측일 삭제 시 접수 복귀 | `api/erp_orders_structured.py:327` `_is_lahom_like_orderer` | 복귀 안 함 |
| 퀘스트 CS 팀 override | `erp_quest_display.py:108` · `orders/audit_order_quests.py:114` · `orders/erp_policy_quests.py:125` | CS 승인 팀이 안 붙는다 |
| 견적서 라홈 분기 | `estimate_service.py:343` | 라홈 양식이 아니다 |
| 대시보드 라홈 표기·황금 예약금 | `web/orders/dashboard.py:230` · `erp_template_filters.py:257` · `orders/dashboard_dto.py:67` | 표기 누락 |
| 표시 '발주사' | 실측 대시보드 컬럼 · 도면 워크벤치 · 채널톡 `발주사` · WAM `발주처` | 고객 이름이 발주사 칸에 노출 |

PR #113(deploy 전체 승격)이 머지되면 **운영에도 그대로 넘어간다**.

## 3. 결정

1. **`parties.orderer` 는 발주사 전용**(ERP 정본 유지). 값 후보는 폼 셀렉트와 동일.
2. **사람(구매자)은 새 키 `parties.buyer = {"name", "phone"}`** 로 옮긴다. `buyer` 는
   현재 저장소 어디에서도 쓰지 않는 자유 키다(코드·템플릿·JS 전수 grep 0건).
3. **네이버 수집 주문의 발주사 = `라홈`** (사용자 결정 2026-08-20). 네이버 스마트스토어가
   라홈 스토어이므로, 라홈 전용 로직(알림톡 프로필·도면 로고·CS 팀·초기 단계)이 맞아떨어진다.
4. 기존 `parties.orderer.phone` 은 **폐기 경로**가 된다(사람 번호가 발주사 칸에 있던 값).
   백필이 `buyer.phone` 으로 옮기고 그 자리는 비운다. 과거 변경 이력 표시를 위해 감사 라벨은
   남긴다.

## 4. 작업 목록

### T1 — 수집 매핑 (`mapping.build_structured_data`)
- `parties.orderer = {"name": DEFAULT_ORDERER_NAME}` (`constants.py` 에 `"라홈"` 상수 신설).
- `parties.buyer = {"name": ordererName, "phone": ordererTel}`.
- 모듈 docstring 의 "주문자는 parties.orderer 에 보존한다" 문구를 새 축으로 갱신.
- **완료 기준**: `tests/services/integrations/test_naver_ingest.py` 갱신 + 신규 계약
  "수집 주문의 발주사는 라홈, 사람은 buyer" green.

### T2 — 백필 (`tools/ops/split_orderer_buyer_axis.py`)
`ExternalOrderLink.raw_snapshot` 을 정본으로 이미 수집된 주문을 옮긴다.

| 현재 상태 | 처리 |
|---|---|
| `orderer.name` == 스냅샷 주문자명 (사람 이름이 발주사 칸) | `buyer.name` 으로 옮기고 `orderer.name = "라홈"` |
| `orderer.name` 이 비어 있음 | `orderer.name = "라홈"`, `buyer.name` = 스냅샷 주문자명 |
| `orderer.name` 이 그 외 값(사람이 고른 발주사) | **건드리지 않는다.** `buyer.name` 만 채운다 |
| `orderer.phone` == 스냅샷 주문자 전화 | `buyer.phone` 으로 옮기고 `orderer.phone` 제거 |
| `orderer.phone` 이 그 외 값 | 그대로 둔다(사람이 넣은 값) |

- 기본 dry-run · `--execute` 로만 쓰기 · 멱등 · 번호 마스킹 — `restore_naver_lost_contacts.py`
  와 같은 골격.
- **완료 기준**: 계약 테스트(위 5행 각각) green + 스테이징 dry-run 목록이 예상과 일치 →
  `--execute` → 재실행 0건.

### T3 — 검색 경로
`buyer.name`·`buyer.phone` 을 후보에 추가한다(주문자 이름으로 찾던 동작 보존).
- `foms/services/erp_dashboard_search.py:170` · `foms/services/foms_unified_search.py:147`
  · `foms/api/events.py:75`
- **완료 기준**: 수집 주문을 주문자 이름·번호로 검색하면 나온다(테스트 3건).

### T4 — 감사 원장
- `orders/structured_diff.py` `SCALAR_PATHS` 에 `parties.buyer.name`·`parties.buyer.phone`
  ·`parties.customer.phone2` 추가(지금은 phone2 변경도 이력에 안 남는다).
- `services/audit_message_display.py` 라벨 등재: `buyer.name`=주문자명, `buyer.phone`=주문자
  연락처, `customer.phone2`=보조 연락처. **`parties.orderer.name` 라벨을 '주문자명' →
  '발주사'로 정정**(현재 라벨이 충돌의 흔적이다).
- **완료 기준**: 라벨 누락 CI 게이트 green(`test_audit_message_display` 계열).

### T5 — 표시
- ERP 주문 상세·모바일 상세에 **주문자** 행 추가 — `parties.buyer.name`/`phone` 이 있을 때만
  렌더(기존 주문은 값이 없으니 변화 없음).
- 발주사 칸은 그대로. 도크 패널은 이미 스냅샷 기반이라 변경 없음.
- **완료 기준**: 수집 주문 상세에 주문자 행이 뜨고, 일반 주문에는 안 뜬다(테스트 2건).

### T6 — 라홈 소비자 회귀
수집 주문 1건 fixture 로 라홈 경로를 타는지 고정: 알림톡 브랜드 프로필 `LAHOM`, 도면 로고
`lahom`, 퀘스트 CS 팀 포함, `_is_lahom_like_orderer` True(실측일 삭제 시 접수 복귀).
- **완료 기준**: 신규 계약 테스트 4건 green.

> `orders/initial_workflow_stage.py` 는 ERP 신규 주문 폼(`erp_order_draft`)만 부른다 —
> 수집 경로는 `status='RECEIVED'` 고정이라 이 축의 영향을 받지 않는다(확인 완료).

## 5. 순서·리스크

1. T1~T2 를 **PR #113 머지 전에** deploy 에 넣는 것이 이상적이다. 머지가 먼저면 운영에도
   백필을 한 번 더 돌린다(스크립트는 환경 무관·멱등).
2. 폼 저장은 `_merge_preserving_missing` 이 `parties` 를 통째로 보존하므로(`ec6b22a9`)
   폼이 모르는 `buyer` 키는 저장으로 사라지지 않는다 — 이 수정의 전제 조건이 이미 충족돼 있다.
3. 되돌리기: 백필은 `orderer.name` 을 `라홈` 으로 바꾸므로 원상복구는 스냅샷 재적용으로만
   가능하다. 실행 전 dry-run 목록을 사용자와 함께 확인한다.

## 6. 범위 밖

- 채널톡 수신 주문 등 다른 채널의 `parties.orderer` 사용(현재 사람 이름을 넣지 않는다).
- 발주사 값 목록 자체의 정규화(라홈/하우드/직접입력 문자열 상수화).
- 수집 원장 §598 "주문자와 수취인 중 화면 대표 이름" 결정 — 이 스펙은 **저장 위치**만 가른다.
