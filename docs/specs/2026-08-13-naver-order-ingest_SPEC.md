# 네이버 스마트스토어 주문 자동 수집 (NAVER-INGEST-01) — 스펙

- 작성: 2026-08-13
- 상태: **승인 대기**
- 근거: 2026-08-13 실 API 호출 검증(아래 §1.2는 추정이 아니라 실측 응답)
- 관련: ORDER-CREATE-01(`foms/services/orders/order_create.py`), ORDER-IMPORT-01(`foms/services/orders/order_import.py`), SIDEFX-00/WORKER-01, DATA-MEASUREMENT-01(geocode outbox)

## 1. 문제와 검증된 사실

### 1.1 문제

스마트스토어 주문이 FOMS에 **손으로** 들어온다. 판매자센터 화면을 보고 사람이 옮겨 적는다.
오타·누락·이중입력이 구조적으로 생기고, 접수 시각이 사람 근무시간에 묶인다.
플레이오토 같은 주문관리 SaaS가 해결하는 문제이며, 같은 공개 API를 우리도 쓸 수 있다.

### 1.2 실측으로 확인된 것 (2026-08-13, 사무실 IP `118.37.217.203`)

`api.commerce.naver.com` 실주문 조회 결과:

- **연락처는 실번호다.** `order.ordererTel`, `shippingAddress.tel1` 모두 `010-XXXX-XXXX`(len=13).
  050 안심번호가 아니다 → **해피콜·실측 연락 워크플로가 그대로 성립**한다. 이 프로젝트의
  존폐를 가르는 관문이었고 통과했다.
- **위경도가 응답에 있다.** `shippingAddress.longitude/latitude`. 다만 **주문서 주소와 실제
  고객(시공) 주소가 다른 경우가 많아** 이 좌표는 신뢰할 수 없다 → 2026-08-13 결정으로
  **주입하지 않고 기존 지오코딩을 그대로 태운다**(§3.5). 원본은 `raw_snapshot` 에만 남긴다.
- **주문자 ≠ 수취인 케이스가 실재한다.** 표본 3건 중 2건에서 `ordererName` 과
  `shippingAddress.name` 이 달랐다(대리주문). 둘 다 보존해야 한다.
- 변경분 조회는 **상태 변경 이벤트 전부**를 준다(3일에 163건). 신규 주문만 뽑으려면 필터가 필요하다.
- `takingAddress` 는 반품 수거지(자사 주소)다. 고객 정보가 아니다 — 매핑에서 제외.

### 1.3 인프라 제약 (이게 설계를 결정한다)

| 항목 | 실측값 |
|---|---|
| 커머스API센터 앱당 호출 IP 한도 | **3개** |
| Railway static outbound IP | 서비스당 **IPv4 3개** (Pro 플랜 포함, 추가비용 0) |
| Railway 워크스페이스 플랜 | PRO (검증됨) |
| 현재 static egress 상태 | 전 서비스 `egressGateways: []` = 미설정 |
| 리전 | `asia-southeast1-eqsg3a` (이동 시 IP 변경) |

3 = 3, **여유 슬롯 0**. 두 서비스에서 static IP를 켜면 IP가 6개가 되고 절반이 차단된다.

## 2. 목표 / 비목표

**목표**
1. 스마트스토어 신규 결제완료 주문을 주기 폴링으로 수집해 FOMS 주문 **초안**을 만든다.
2. 같은 주문을 두 번 만들지 않는다(`productOrderId` 멱등).
3. 수집 주문도 기존 주문과 동일한 지오코딩 경로를 탄다(네이버 좌표 주입 안 함 — §3.5).
4. 네이버 원본 응답을 보존해, 매핑을 나중에 고쳐도 재처리할 수 있다.

**비목표 (v1에서 안 한다)**
- `productOption` 문자열에서 규격(W/H)·색상 **자동 파싱**. v1은 원문 보존까지만 하고
  사람이 ERP에서 채운다. (파싱은 실제 옵션 문자열 표본을 본 뒤 별도 스펙 — §7 참조)
- **역방향 쓰기**(발주확인·발송처리·송장 push). production에 SIDEFX 서비스가 아직 없다(§3.5).
- 다채널(쿠팡·11번가 등) 일반화. 단, 테이블 스키마는 채널 확장을 막지 않게 만든다.
- 반품·교환·취소 동기화.

## 3. 설계

### 3.1 실행 위치 — WORKER 서비스 단일 출구 (강제)

§1.3 제약 때문에 **네이버로 나가는 모든 HTTP는 WORKER 서비스에서만** 나가야 한다.

- WORKER에 static outbound IP를 켜고, 받은 **IPv4 3개를 커머스API센터에 등록**한다.
  (사무실 IP는 슬롯을 비우기 위해 제거한다 — 한도가 3이라 공존 불가)
- 주기 폴링: `start.sh` 의 **기존 escalation loop 패턴을 그대로 따른다**
  (`USE_RQ_WORKER=1` 분기 안, 백그라운드 서브셸, 환경변수 게이트):
  ```bash
  if [ "$FOMS_NAVER_SYNC_ENABLED" = "1" ]; then
    python scripts/maintenance/run_naver_order_sync.py --loop \
      --interval "${FOMS_NAVER_SYNC_INTERVAL_SECONDS:-300}" --json &
  fi
  ```
  스윕 실패가 rq worker 본체를 죽이지 않는 구조까지 동일하다.
- 화면의 "지금 수집" 버튼은 **web에서 직접 호출하지 않는다**. `default` 큐에 rq enqueue만
  하고 실행은 WORKER가 한다. web에서 부르면 IP가 달라 차단된다. **이건 취향이 아니라 제약이다.**

### 3.2 인증 — 토큰 캐시

`foms/services/integrations/naver_commerce/client.py` (신규)

- 토큰: `POST /external/v1/oauth2/token`, `grant_type=client_credentials`, `type=SELF`.
  서명 = `base64(bcrypt.hashpw(f"{client_id}_{timestamp_ms}", client_secret))` — **client_secret이 salt**다.
- 유효기간 실측 `expires_in=10799`(3시간). Redis에 캐시하고 만료 5분 전 갱신.
- 비밀값은 `NAVER_COMMERCE_CLIENT_ID` / `NAVER_COMMERCE_CLIENT_SECRET` 환경변수.
  **코드·저장소에 절대 두지 않는다**(CLAUDE.md 하드코딩 비밀키 금지).

### 3.3 수집 파이프라인

```
[워터마크 이후 ~ 지금] 구간(최대 24h)으로 잘라서
  GET  /v1/pay-order/seller/product-orders/last-changed-statuses
    → productOrderId 목록 (상태변경 전부)
  필터: productOrderStatus == PAYED 이고 아직 링크가 없는 것만
  POST /v1/pay-order/seller/product-orders/query  (배치, 페이징)
    → 상세
  각 건: 원본 스냅샷 저장 → 매핑 → create_order() → 링크 행 생성
  성공 구간 끝을 워터마크로 커밋
```

- 구간 상한 24h는 API 제약이다. 워터마크가 24h보다 뒤처지면 **하루씩 나눠 순회**한다.
- 실패는 구간 단위로 재시도한다. 워터마크는 **성공한 구간까지만** 전진한다(유실 방지).

### 3.4 멱등 — 링크 테이블 (새 테이블)

`models.ExternalOrderLink`

| 컬럼 | 설명 |
|---|---|
| `id` | PK |
| `channel` | `'NAVER'` (확장 여지) |
| `external_id` | `productOrderId` |
| `order_id` | FK → orders.id (nullable — 매핑 실패 보류 상태 존재) |
| `external_order_no` | `orderId`(주문번호, 묶음 단위 참조용) |
| `raw_snapshot` | JSONB, 네이버 원본 응답 그대로 |
| `sync_status` | `LINKED` / `PENDING_REVIEW` / `FAILED` |
| `failure_reason` | 매핑 실패 사유 |
| `created_at` / `updated_at` | |

- **`UNIQUE (channel, external_id)`** 가 중복 수집을 DB 레벨에서 막는다. 앱 체크만으로는
  동시 실행 레이스를 못 막는다.
- Order에 컬럼을 붙이지 않는 이유: 채널 추가마다 컬럼이 늘고, 원본 보존 자리가 없고,
  주문 soft delete와 수집 이력의 수명이 다르다.

### 3.5 주문 생성 — `create_order()` 경유 (우회 금지)

ORDER-CREATE-01 규약대로 **raw `Order(...)` 금지**. `create_order()` 를 부른다.
그러면 mutation_version·owner 배정·`ORDER_CREATED` 이벤트·quest seed가 공짜로 붙는다.

**owner — 미배정 보류함 방식 (결정, §7 Q1)**: `resolve_order_owner()` 는 STAFF=본인,
ADMIN/MANAGER=명시된 **활성 SALES** 사용자를 요구한다. owner 없는 주문은 만들 수 없다
(ASSIGNMENT-00 상 owner row가 authorization 근거다). 자동 수집에는 사람 actor가 없다.

→ **전용 시스템 계정 2개**를 쓴다:
- actor = `naver_ingest_bot` (role=MANAGER) — 이벤트 author·`assigned_by`.
- owner = `naver_unassigned` (role=STAFF, team=SALES, active) — **미배정 보류함**.
  실존 영업사원이 아니라 "아직 주인 없음"을 표현하는 자리다. 로그인 불가로 잠근다.

수집 주문은 이 보류함 owner로 생성되고, 관리 화면의 **미배정 큐**에 뜬다. 사람이 담당자를
지정하면 기존 배정 경로(`OrderAssignment`, source=REASSIGN)로 넘어간다.
`naver_unassigned` 가 owner인 주문은 대시보드에서 "담당 미지정" 뱃지로 구분한다.

> 이 방식을 택한 이유: `create_order()` 에 "owner 없음" 예외 경로를 뚫으면 ASSIGNMENT-00
> 불변식(모든 주문에 owner row 1개)이 깨진다. 보류함 계정은 불변식을 유지하면서 미배정을
> 표현하는 방법이다.

**좌표 — 네이버 좌표를 주입하지 않는다 (2026-08-13 사용자 결정으로 변경)**

당초 설계는 `create_order()` 에 `skip_geocode` 를 추가하고 네이버의
`shippingAddress.longitude/latitude` 를 `Order.lat/lng` 에 직접 넣는 것이었다. **폐기한다.**

이유: 네이버 좌표는 **주문서에 적힌 주소** 기준인데, 실제 고객(시공) 주소와 다른 경우가 많다.
그 좌표를 그대로 넣으면 실측 동선·지도가 틀린 위치를 가리키고, `geocode_status='success'` 라
재지오코딩 대상에서도 빠진다 — 틀린 값이 조용히 굳는다.

→ 수집 주문도 **기존 주문과 똑같이 지오코딩한다**. `create_order()` 를 기본값으로 호출해
GEOCODE outbox 를 정상 예약하고(다른 모든 주문 생성 경로와 동일), 네이버 좌표는
`raw_snapshot` 안에 원본으로만 남긴다(나중 대조용). **`create_order()` 시그니처는 건드리지
않는다.**

### 3.6 필드 매핑

| 네이버 | FOMS `Order` | 비고 |
|---|---|---|
| `shippingAddress.name` | `customer_name` | 수취인 우선 |
| `shippingAddress.tel1` | `phone` | 실번호 |
| `ordererName` / `ordererTel` | `structured_data['orderer']` | 주문자≠수취인 보존 |
| `baseAddress` + `detailedAddress` | `address` | 결합 |
| `zipCode` | `structured_data['zip_code']` | |
| `longitude` / `latitude` | — (`raw_snapshot` 에만) | 주문서 주소 기준이라 실주소와 상이. 주입 금지 |
| `productName` | `product` | |
| `productOption` | `options` (원문 그대로) | v1 파싱 없음 |
| `orderDate` | `received_date` / `received_time` | KST 변환 |
| `totalPaymentAmount` | `payment_amount` | |
| `shippingDueDate` | `structured_data['naver']['shipping_due_date']` | |
| `sellerProductCode` | `structured_data['naver']['seller_product_code']` | 자사 상품 매핑 키 |
| `productOrderId` | 링크 테이블 `external_id` | 멱등 키 |
| `takingAddress.*` | — | 반품 수거지, 버림 |

`status` 는 `RECEIVED` 고정. `structured_data['source'] = 'NAVER_SMARTSTORE'` 로 수집분을 표시한다.

### 3.7 화면

- 주문 상세: "네이버 수집" 배지 + 원본 스냅샷 보기(관리자 전용).
- 관리 화면: 수집 이력 목록(성공/보류/실패), "지금 수집" 버튼(=rq enqueue), 워터마크·마지막 성공 시각.
- `PENDING_REVIEW` 건은 목록에서 사람이 확인 후 수동 연결/폐기.

## 4. 단계와 완료 기준

| T | 내용 | 완료 기준 |
|---|---|---|
| T1 | Railway WORKER static outbound IP 활성화 → IPv4 3개 확보 → 커머스API센터 등록 교체 | WORKER에서 `run_naver_order_sync.py --once --dry-run` 이 토큰 발급 + 변경분 조회 성공 |
| T2 | `ExternalOrderLink` 모델 + alembic 마이그레이션(`downgrade()` 포함) | `alembic upgrade head` → `downgrade` → `upgrade` 왕복 성공, 단일 head 유지 |
| T3 | `naver_commerce/client.py` (토큰 캐시·조회·재시도·rate limit 백오프) | 유닛 테스트: 서명 생성, 토큰 캐시 만료, 24h 구간 분할, HTTP 오류 재시도 |
| T4 | 매핑 + `create_order()` 연동 | 저장된 fixture 응답 → 주문 생성 테스트, 같은 fixture 재실행 시 **주문 0건 추가**(멱등), 기존 create_order 호출자 회귀 없음 |
| T5 | WORKER 폴링 루프 + `FOMS_NAVER_SYNC_ENABLED` 게이트 + rq enqueue 경로 | 게이트 off면 루프 미기동, on이면 주기 실행. web 경로에서 직접 HTTP 나가지 않음을 테스트로 고정 |
| T6 | 관리 화면(수집 이력·수동 실행·배지) | 스테이징에서 실주문 1건 수집 → 화면 확인 → 재실행 시 중복 없음 |
| T7 | 앱 인증 만료 알림 | 만료 D-7 알림 발송 확인 |

T0(선행, 코드 아님): 커머스API센터에서 **시크릿 재발급**(2026-08-13 시험 중 노출) +
시스템 계정 2개(`naver_ingest_bot`·`naver_unassigned`) 생성.

각 T는 `pre_push_smoke` exit 0 + `APP_OK` 후 커밋한다.

## 5. 리스크

| 리스크 | 대응 |
|---|---|
| **앱 인증 기한 만료 → 자동 휴면 → API 전면 중단** | T7 만료 알림. 이게 없으면 조용히 죽는다 |
| IP 슬롯 3개 소진 | 네이버 호출은 WORKER 단일 출구(§3.1). 리전 이동 금지 |
| Railway static IP가 전용 아님(타 고객과 공유 가능) | 허용목록 용도라 기능상 무해. 문서에 명시만 |
| 매핑 실패로 쓰레기 주문 생성 | 실패는 주문을 만들지 않고 `PENDING_REVIEW` 로 남긴다(사람 확인) |
| 개인정보(실번호·주소) 저장 | FOMS가 이미 동일 등급 정보를 저장 중 — 신규 위험 아님. 단 `raw_snapshot` 은 관리자 전용 노출 |
| API rate limit | 지수 백오프 + 구간 단위 재시도 |
| 시크릿 노출 | 2026-08-13 시험 중 시크릿이 세션 기록에 남았다 → **구현 착수 전 재발급 필수** |

## 6. 검증 방법

- 스테이징: 가상 주문 대신 **실주문 읽기만**(수집은 읽기 전용이라 실데이터 오염 없음).
- 멱등: 같은 구간 3회 연속 실행 → 주문 수 불변.
- 좌표: 수집 주문이 기존 주문과 같은 지오코딩 경로를 타고(outbox 예약 확인) 완료 후 지도에 표시.
- 성능: 수집 루프는 대시보드 hot path와 무관(WORKER 프로세스). TTFB 영향 없음을 확인.

## 7. 결정 사항 (2026-08-13 사용자 확정)

| # | 질문 | 결정 | 설계 반영 |
|---|---|---|---|
| Q1 | 수집 주문의 SALES owner | **미배정 보류함 후 수동 배정** | §3.5 시스템 계정 2개 + 미배정 큐 |
| Q2 | `productOption` 자동 파싱 | **v1 미포함, 원문만 보관** | §2 비목표, §3.6 `options` 원문 |
| Q3 | 폴링 주기 | **5분** | `FOMS_NAVER_SYNC_INTERVAL_SECONDS=300` |
| Q4 | 수집 범위 | **전 상품** | 상품코드 필터 없음. 제외가 필요해지면 v2 |

Q4 결과로 §3.3 필터는 `productOrderStatus == PAYED` **하나뿐**이다(상품 필터 없음).
가구 외 상품도 주문으로 들어오므로, 미배정 큐에서 사람이 걸러내는 것이 1차 방어선이다.

---

## 8. 부록 v1.1 — 수집 주문 트리아지 작업대 (2026-08-13 추가 합의)

### 8.1 왜 필요한가

대시보드는 owner 스코프가 아니라 `mine` 이 선택 필터다. 즉 수집 주문은 **안 보이는 게 아니라
구별이 안 된다** — RECEIVED 칸에 정상 주문처럼 섞이는데 실제로는 담당자 없고 규격도 안 채워진
반쪽 초안이다. 여기에 v1 은 `productOption` 을 파싱하지 않기로 했으므로(§7 Q2) 사람이 원문을
읽고 채워야 하는데, **그 대상 목록이 없으면 아무도 안 채운다.** 반쪽 주문이 조용히 쌓이는 것이
이 기능의 실질적 실패 모드다.

또한 §7 Q1 의 미배정 보류함(`naver_unassigned`)은 "아직 주인 없음"을 표현하는 자리인데,
**주인을 정하는 화면이 없다** — 상태를 만들어놓고 해소 경로가 없는 셈이다.

`/admin/naver-ingest`(§3.7)로는 부족하다. 그건 "수집이 도는가"(운영 건강)에 답하는 화면이고,
여기서 필요한 건 "수집된 주문을 누가 마무리하는가"(업무)다. 한 화면에 합치면 둘 다 나빠진다.

### 8.2 모양 — 트리아지 작업대 (결정)

기존 workflow 대시보드를 복제하지 **않는다**. 수집 주문은 전부 RECEIVED 라 stage 칸 하나만
차 있는 빈 화면이 된다. 대신 한 건씩 처리하는 작업대를 만든다:

- **좌**: 확인 대기 큐(최신순). 고객명·제품·수집 시각.
- **우**: 네이버 원본(옵션 원문·주문자·수취인·주소)과 FOMS 현재 값을 나란히 대조 + 담당자 지정
  + "확인 완료".

> **규격 입력은 이 화면에서 하지 않는다(명시적 결정).** 규격은 `spec_rows` 구조이고 W 는 출고가·
> 시공비와 결합돼 있어(`eval_spec_width_mm` 가 총폭 SSOT) 두 번째 입력 UI 를 만들면 계산 규칙이
> 갈라진다. 작업대는 **옵션 원문을 크게 보여주고 주문 편집기로 보내는 것**까지 한다. 편집기가
> 규격 입력의 SSOT 로 남는다.

### 8.3 완료 판정 — 사람이 "확인 완료" (결정)

시스템이 "다 채웠는지"를 추측하지 않는다. 추측 규칙을 코드로 정하면 오판 여지가 생기고,
업무 기준이 바뀔 때마다 규칙을 고쳐야 한다.

상태는 `ExternalOrderLink` 에 둔다(주문이 아니라 **수집 이력의 속성**이다):

| 컬럼 | 설명 |
|---|---|
| `reviewed_at` | 확인 완료 시각. NULL = 확인 대기(큐에 뜬다) |
| `reviewed_by_user_id` | 확인한 사람(FK → users.id, ON DELETE SET NULL) |

`sync_status` 에 값을 더하지 않는 이유: 그건 **수집 결과**(LINKED/PENDING_REVIEW/FAILED)를
말하는 축이고, 트리아지는 **사람의 처리 여부**라 축이 다르다. 섞으면 "수집은 성공했지만 사람이
아직 안 본" 상태를 표현할 수 없다.

### 8.4 담당자 지정 — 기존 경로 재사용 (우회 금지)

`foms/services/orders/assignment.py::set_sales_assignee()` 를 그대로 부른다. 그러면
`execute_order_mutation`(REV-00) 경유로 version bump·receipt·`SALES_ASSIGNEE_SET` 이벤트·
partial unique(주문당 active owner 1명)가 전부 따라온다. `OrderAssignment` 를 직접 만들지 않는다.

교체 사유(`reason`)는 기존 owner 와 다른 사람으로 바꿀 때 필수다 — 보류함(`naver_unassigned`)
에서 실제 담당자로 옮기는 것도 교체이므로 사유가 필요하다. 화면이 기본 사유를 채워 보낸다.

### 8.5 단계

| T | 내용 | 완료 기준 |
|---|---|---|
| T8 | `ExternalOrderLink.reviewed_at`/`reviewed_by_user_id` + 마이그레이션 | 왕복 성공·단일 head·ORM↔마이그레이션 parity |
| T9 | 트리아지 화면(큐 + 원본/FOMS 대조 + 편집기 링크) | 확인 대기만 뜬다·확인 완료 시 큐에서 빠진다·원본 열람 감사 기록 |
| T10 | 담당자 지정(`set_sales_assignee` 경유) + 대시보드 "담당 미지정" 뱃지 | 지정 후 owner 교체·이벤트 1건·보류함 owner 주문에만 뱃지 |
