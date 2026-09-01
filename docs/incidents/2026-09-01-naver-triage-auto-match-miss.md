# 네이버 트리아지 자동 매칭 실패 진단 (문기범 / 주문 #4915)

작성 2026-09-01. 운영 실데이터 읽기 전용 조회 + 로컬 재현으로 확정. 코드 변경 없음.

## 증상
`/admin/naver-ingest/triage` 처리 탭에서 수집분(수취인 문기범, 010-3468-7933,
서울특별시 성북구 화랑로48길 16 (석관동, 두산아파트) 110동 2403호)이
"이 고객의 기존 주문을 자동으로 찾지 못했습니다" 로 표시된다.
같은 카드의 "주문 직접 찾아 붙이기"에서 `문기범` 으로 검색하면 주문 #4915 가 `이름 일치` 로 나온다.

## 결론
자동 매칭 축 3개가 전부 불발했다. 두 개의 독립 결함이 겹쳐야 나는 증상이다.

렌더 경로는 캐시가 아니다 — `foms/web/admin/naver_ingest.py:1376` 이 요청마다
`find_order_candidates` 를 live 로 부른다(후보를 저장하는 컬럼·키 없음).

### 축 1·2 — 수취인 전화(100점) / 주문자 전화(80점)
`foms/services/integrations/naver_commerce/order_candidates.py:644-645`

    base.filter(or_(Order.erp_phone_digits == digits, Order.phone == digits))

- 네이버 수취인·주문자 tel 둘 다 `010-3468-7933` → digits `01034687933`
- 주문 #4915 의 `erp_phone_digits` = `01096215670` (다른 번호)
  - 원인: `order_field_changes` id 7017 (2026-08-30 05:05, actor 27) 이
    `parties.customer.phone` 을 `010-3468-7933` → `010-9621-5670` 로 변경.
    `erp_phone_digits` 는 structured_data 를 따라 갱신됐고
    플랫 `orders.phone` 컬럼만 옛 번호로 남았다.
- 뒤 갈래 `Order.phone == digits` 는 포맷된 원문과 숫자열을 `==` 로 견준다 → 영구 불일치.
  운영 활성 주문 3811건 중 `phone` 이 숫자만인 행 0건, 네이버 링크 243건 전수 대조 적중 0건.
  저장소에서 raw `Order.phone` 을 digits 와 `==` 로 견주는 곳은 이 한 줄뿐이고,
  형제 구현 `bulk_dispatch.py:614-621` 은 같은 자리에서 `normalize_phone_digits(phone)` 를 쓴다.

### 축 3 — 이름 + 주소 접두(60점, "전화가 바뀐 재주문" 안전망)
`order_candidates.py:655-668`, `ADDRESS_PREFIX_LEN = 10`

- 이름 `문기범` 은 `orders.customer_name` 과 정확히 일치(축은 여기서 안 끊겼다)
- 네이버 주소 접두 10자 = `'서울특별시 성북구 '`
- 주문 #4915 `address` = `'성북구 화랑로48길 16, 두산아파트 110동 2403호'`
- `startswith` = False

주소는 stale 이 아니다. 운영 180일 ERP 주문 중
`structured_data.site.address_full` != `address` 컬럼인 건 0건.
사람 입력 축약형 vs 네이버 공식 전체 주소(`mapping.build_address`)의 **표기 형식 차이**다.

## 타임라인
- 08-21 주문 #4915 생성(사람 입력 주소, 시/도 없음)
- 08-28 네이버 링크 189·190 정상 부착(당시 전화 일치)
- 08-30 05:05 전화 수정 → 축 1·2 절단
- 09-01 새 수집분 도착 → 축 3 도 원래부터 이 주소에서 못 걸림 → 후보 0건

## 규모 (운영 링크 243건 vs 180일 활성 주문 2289건 전수 대조)
- 수취인명 정확일치 성립: 224건
- 그중 주소 접두 10자 통과: 119건 → **105건(47%)이 주소 표기 차이만으로 안전망 상실**
- `erp_phone_digits` 완전일치 적중: 226건 / raw `phone` 갈래 적중: **0건**
- `erp_phone_digits` != digits(`phone`) 인 활성 주문: 130건
  (일부는 복수 전화 문자열의 VARCHAR(20) 절단분, #4915 는 진짜 desync)
- 시제 정규화(시/도 제거·괄호 제거·구두점 제거 후 도로명+건물번호 비교) 적용 시
  119 → 159~168건 회복, 후보 2건 이상 생기는 링크는 2건

## 구조적 원인 2가지

### (A) 플랫 `orders.phone` 이 저장 경로에 따라 갈린다
- PATCH `/api/orders/<id>/structured/fields` → `erp_orders_structured.py:1049-1052` 가 `order.phone` 직접 기록
- PUT `/api/orders/<id>/structured`(전체 저장, 7017 을 만든 경로) → `:1513 sync_erp_flat_columns` 만 호출.
  그 함수(`foms/services/erp_sync_columns.py:66-68`)는 `erp_phone_digits` 만 쓴다.
  파일 전체에서 `order.phone =` 는 `:858` 한 곳뿐이고 그건 draft 승격 분기 안이라 기존 주문에선 스킵된다.
  같은 PUT 이 주소는 `reset_order_geocode_on_address_change` 로 flat 동기한다 — phone·customer_name 만 빠졌다.
- `foms/services/orders/erp_flat_audit.py:52-66` 의 `DERIVED_COLUMNS` 12개에 `phone` 이 없다
  → 정합 감사·부팅 백필이 이 컬럼을 영원히 못 고친다.
- 읽기 헬퍼 `apply_erp_display_fields`(`erp_display.py:325-341`)가 렌더 시 sd 값으로 덮어 그려
  화면은 늘 옳고 SQL 만 틀린 무증상 상태가 된다 → 130행이 신호 없이 누적.
- 역방향 생성기: legacy 편집 폼 `foms/web/orders/edit.py:381-382` 는 flat `phone`·`customer_name` 만 쓰고
  sd parties 는 안 고친다. 같은 파일 `:55-58` 주석은 "sd 쌍둥이가 원장에 싣는다"고 적혀 있으나
  실제로는 전화 변경이 `order_field_changes` 에 남지 않는다(별도 감사 구멍).

### (B) 같은 스냅샷을 두 화면이 다른 축으로 판정한다
`bulk_dispatch.find_unlinked_matches` 는 `_snapshot_keys` 를 **같이 쓰면서**(`bulk_dispatch.py:598`)
전화가 실패하면 **수령인명 단독**으로 매칭한다(`:681-684`, reason `수령인명 일치`).
그 운영 규칙의 근거 실데이터로 `문기범/문유주` 가 인용되어 있다
(`bulk_dispatch.py:576`, `docs/plans/2026-08-31-naver-bulk-dispatch-result-ui-ledger.md:105`, 2026-09-01 사용자 확정).
트리아지 후보표에는 그 축이 배선되지 않았다.

## 함정 — 전화축에 flat 컬럼을 정규화해 넣으면 안 되는 이유
#4915 의 stale flat `phone` 이 들고 있는 값이 정확히 네이버가 들고 온 옛 번호라서,
`normalize_phone_digits(Order.phone)` 로 갈래를 살리면 이 버그가 100점으로 "사라진다".
그러나 그건 데이터 결함이 기능의 받침대가 되는 것이고,
(A)를 고치는 순간 조용히 원복된다. 옛 전화로 사람을 찾는 것 자체는 업무적으로 옳지만
그 이력의 정본은 flat 컬럼이 아니라 `order_field_changes` 원장이다.

## 수리 권고 (순위)
1. **주소 양쪽 정규화** — 이 버그 + 105건 계열을 고친다. stale 데이터에 의존하지 않고,
   이름 정확일치가 두 번째 신호라 오탐 위험이 낮고, SQL 무변화라 perf-gate 무영향.
   정규화 함수는 공용 1곳에 두고 `bulk_dispatch` 와 공유할 자리를 만든다.
2. 이름 단독 약축(낮은 점수·명시 라벨) — `bulk_dispatch` 선례와 정합. 동명이인 위험은 사람 확인으로 흡수.
3. 전화축 flat 정규화 — 넣는다면 별도 사유 라벨(`옛 전화(변경 전) 일치`)·낮은 점수로만. (5)(6)과 충돌 계약 기록 필수.
4. `order_field_changes` 원장에서 옛 전화 조회 — (3)이 우연히 얻는 것을 설계로 얻는다. 성능 설계 필요.
5. 쓰기 경로 flat 동기 수정 — 근본이지만 `Order.phone` 을 읽는 검색 8곳을 문다. 매처 수정과 다른 배포로.
6. 130행 backfill — VARCHAR(20) 절단분이 섞여 있어 sd 단일 번호로 덮으면 보조 연락처가 소실된다. 분류 선행.
7. 좌표/buildingManagementNo 축 — `mapping.py:7-11` 이 이미 기각한 축(네이버 좌표는 주문서 주소 기준, 관측 90m 차이). 권장 안 함.

## 테스트가 못 잡은 이유
`tests/services/integrations/test_naver_order_candidates.py:19-47` fixture 는
ERP 주소 `"서울시 강남구 테헤란로 152 101동 1001호"`, 네이버 base `"서울시 강남구 테헤란로 152"` —
ERP 주소가 네이버 base 를 글자 그대로 접두로 포함하는 모양이라 운영 실데이터 형태가 아니다.
`test_name_and_address_match_when_phone_changed` 가 초록인 이유가 이 fixture 다.
또 `_order` 는 `phone` 과 `digits` 를 항상 짝맞춰 넘겨 desync 를 한 번도 태우지 않는다.
raw phone 갈래를 무는 테스트는 한 건도 없다.

필요 회귀 테스트(관례상 `tests/services/integrations/`):
T1 이 사고 그대로(먼저 빨강) / T2 음성 대조군(다른 이름·다른 건물번호·다른 구, 모두 모집단 안에서) /
T3 주소 표기 변형 등가 클래스(순수 함수) / T4 raw phone 갈래 미적중 단정 /
T5 `NAME_SCAN_CAP=200` 절단 신호 / T6 화면 문구 부재(소스 단정) /
T7 `find_unlinked_matches` 와 `find_order_candidates` 축 정합.

---

# 부록 A. 전화 어긋남 130건 분류 (조사만, 수정 없음 — 2026-09-01)

운영 활성 주문 3811건 중 `erp_phone_digits` != digits(`phone`) 인 130건을 읽기 전용으로 분류했다.

| 갈래 | 건수 | 내용 | 판정 |
|---|---|---|---|
| A. VARCHAR(20) 절단 | 71 | 복수 전화 문자열(`010-…/010-…`)의 digits 가 20자에서 잘림. sd 와 `phone` 컬럼은 **서로 일치**한다 | desync 아님. 다만 두 번째 번호로는 전화 검색이 안 걸린다(별건) |
| C. 진짜 desync | 48 | `erp_phone_digits` == digits(sd) 인데 `phone` 컬럼만 다른 번호 | **방향을 알 수 없다 — 아래 참조** |
| F. 기타(복수 전화 + 불일치) | 10 | sd 에 전화가 여러 개, 컬럼은 그중 하나만. digits 는 절단 | 사람 확인 필요 |
| E. sd 전화 없음 | 1 | id 812 (2025-07 접수) | 레거시 |

## C 48건을 지금 backfill 하면 안 되는 이유

C 는 **두 방향이 섞여 있고 구분이 안 된다.**

- PUT `/api/orders/<id>/structured` 경로: sd 가 새 값, `phone` 컬럼이 옛 값 (주문 #4915 가 이것)
- legacy 편집 폼 `foms/web/orders/edit.py:381`: `phone` 컬럼이 새 값, sd 가 옛 값
  (이 폼은 sd parties 를 안 고치므로 digits 는 옛 sd 를 따라 재계산된다 → 겉모습이 위와 똑같다)

**48건 중 `order_field_changes` 에 전화 변경 기록이 남은 것은 12건뿐**이다. 나머지 36건은
어느 쪽이 최신인지 판정할 근거가 데이터에 없다. sd 를 정답으로 두고 일괄로 덮으면 legacy 폼으로
고친 최신 번호가 지워진다.

세부 갈래(48건): 050 안심번호가 컬럼에 남은 건 5건, 컬럼이 깨진 값(`010-`) 1건, 나머지 42건은 번호 자체가 다름.

## 권고
1. 갈래 A(71건)는 `erp_phone_digits` 절단 문제이지 desync 가 아니다 — backfill 대상에서 제외.
2. 갈래 C 는 legacy 편집 폼이 sd 를 안 고치는 것(=원장에도 안 남는 것)을 먼저 막아야
   방향 판정이 가능해진다. 그 전에는 일괄 덮어쓰기 금지.
3. 개별 건은 `order_field_changes` 기록이 있는 12건부터 사람이 확인해 고칠 수 있다.
