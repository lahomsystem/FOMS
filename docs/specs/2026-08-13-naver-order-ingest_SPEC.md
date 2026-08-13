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
- **위경도가 응답에 있다.** `shippingAddress.longitude/latitude` → 수집 주문은 지오코딩
  단계를 건너뛴다(FOMS `Order.lat/lng/geocode_status` 에 직접 주입).
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
3. 수집 주문은 지오코딩 없이 지도에 뜬다(네이버 좌표 주입).
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

**좌표 주입**: `create_order()` 는 주소가 있으면 GEOCODE outbox를 예약한다. 네이버가 좌표를
주므로 불필요한 지오코딩이다. 그런데 **production에 SIDEFX 서비스가 없다**(서비스 목록:
Postgres/WORKER/Redis/web/FOMS-cron). 예약된 outbox 행이 소비되지 않고 쌓인다.
→ `create_order()` 에 `skip_geocode: bool = False` 파라미터를 추가하고, 수집 경로는 True로
부른 뒤 `lat/lng/geocode_status='success'/geocoded_at/address_hash` 를 직접 채운다.
(기존 호출자 동작은 기본값 False로 그대로 유지)

### 3.6 필드 매핑

| 네이버 | FOMS `Order` | 비고 |
|---|---|---|
| `shippingAddress.name` | `customer_name` | 수취인 우선 |
| `shippingAddress.tel1` | `phone` | 실번호 |
| `ordererName` / `ordererTel` | `structured_data['orderer']` | 주문자≠수취인 보존 |
| `baseAddress` + `detailedAddress` | `address` | 결합 |
| `zipCode` | `structured_data['zip_code']` | |
| `longitude` / `latitude` | `lng` / `lat` | `geocode_status='success'` |
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
| T4 | 매핑 + `create_order()` 연동 + `skip_geocode` 파라미터 | 저장된 fixture 응답 → 주문 생성 테스트, 같은 fixture 재실행 시 **주문 0건 추가**(멱등), 기존 create_order 호출자 회귀 없음 |
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
- 좌표: 수집 주문이 지도에 즉시 표시되고 `geocode_status='success'`.
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
