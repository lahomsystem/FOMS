# 지방주문 AS 접수 시 상차일 입력 → 상차 예정 알림 자동 승격 (SPEC)

- 작성일: 2026-07-22
- 상태: 설계 승인 대기
- 유형: 코어 변경(API + 프론트 워크플로) — RPI 프로토콜 적용
- 관련 대시보드: `/regional_dashboard` (지방 대시보드) "상차 예정 알림"

## 1. 문제 정의 (현상)

지방 대시보드에서 상차완료 건의 상태를 `AS접수(AS_RECEIVED)`로 바꾸고 상차일을 입력하면
"상차 예정 알림"으로 올라가고 AS 뱃지가 붙어야 하는데 작동하지 않는다.

## 2. 근본 원인 (정밀 리뷰 결과)

### 2.1 주 원인 — 지방 대시보드 상태 드롭다운의 stage-override 오탐 (경로 차단)
- 지방 대시보드 상태 `<select class="inline-edit status-dropdown">` change 핸들러가
  `FOMS_STAGE_OVERRIDE.interceptStatusChange`를 먼저 실행한다.
  (`templates/measurement/regional_dashboard.html:1750-1757`)
- `AS_RECEIVED`는 stage-override RANK 맵에 없어 rank `-1` → 모든 `→AS_RECEIVED`가
  `jump`으로 분류되어 override 모달이 뜬다. (`static/js/orders/erp-stage-override.js:8-17, 323-347`)
- 그러나 override 모달은 AS_* 타깃 선택 불가이며, 서버
  `foms/services/orders/stage_override.py:155-157`도 AS 타깃을 거부한다.
  → 취소 시 드롭다운이 원복된다. **대시보드에서 상태를 AS접수로 바꾸는 경로 자체가 막혀 있다.**

### 2.2 부차적 겹침 (증상 가중)
- 같은 `.inline-edit` select에 `change` + `blur` 이중 제출
  (`regional_dashboard.html:1726-1734` vs `1743-1767`).
- 체크리스트 자동 상태(`SCHEDULED`/`PENDING`)와 수동 상태변경 경쟁 (`1536-1558`).
- `update_order_field`로 status만 직접 넣어도 `as_received_date` 미설정·`as_content` 없음
  → 정본 AS 등록과 불일치. 상차일도 별도 입력 → 리로드 2회 레이스.

### 2.3 서버 버킷 로직은 이미 정상 (수정 불필요)
```
foms/web/measurement/dashboard.py:533-549
  status == "AS_RECEIVED" (OR measurement_completed)
  AND shipping_scheduled_date >= today
  AND status not in [COMPLETED, ON_HOLD, SCHEDULED]
  → shipping_alerts (상차 예정 알림)
```
- 템플릿은 `order.status == 'AS_RECEIVED'`일 때 AS 뱃지를 렌더한다.
  (`regional_dashboard.html:295, 300, 340-358`)
- 이 의도는 `tests/domains/test_regional_dashboard_buckets.py:142-178`에 계약으로 고정돼 있다.

**결론**: 데이터(status=AS_RECEIVED + 미래 shipping_scheduled_date)를 한 번에·정본 경로로
올바르게 쓰면 승격·뱃지는 전부 자동. 근본 해결은 "AS 모달(=`/as/register`)에서
지방주문 상차일도 함께 저장"하는 것이다.

## 3. 결정 사항 (승인됨)
- D1. 승격 목적지: **지방 대시보드(`/regional_dashboard`)의 상차 예정 알림**.
- D2. 범위: **A안** — AS 모달에 지방 상차일 입력 추가(정본 경로, 최소·저위험). 대시보드 겹침 리팩터는 하지 않음.
- D3. 상차일 입력: **선택(optional)** — 미입력 시 상차일 없이 AS접수만 진행, 이후 대시보드에서 입력 가능.
- D4. 기존 지방 대시보드 상태 드롭다운 → AS 경로: **그대로 둠**(앞으로 AS접수는 erporder AS 모달로 유도. 대시보드 드롭다운은 손대지 않음).

## 4. 설계 (A안)

### 4.1 데이터 흐름 (변경 후)
```
erporder 상세
  → 단계(Workflow) = AS접수 선택 + 저장
  → asReceiveModal 오픈
     (지방주문이면: 상차일 date input 노출, 기존값 prefill)
  → "AS 접수 확인"
  → POST /api/orders/{id}/as/register  { as_content, shipping_scheduled_date? }
       - status = AS_RECEIVED, as_received_date = today, workflow.stage = AS_RECEIVED,
         shipment.as_content = 내용, (shipping_scheduled_date 제공 시) order.shipping_scheduled_date 설정
  → (첨부 업로드) → PUT /structured (stage 동일 → no-op) → /erp/as 리다이렉트
  → 지방 대시보드 재진입 시: status=AS_RECEIVED + 미래 상차일 → 상차 예정 알림에 AS 뱃지로 자동 등장
```

### 4.2 변경 파일 (5개 + 테스트)
> 백엔드 2(`as_orders.py`, `erp_orders_structured.py`) + JS 1(`erp-order-shared.js`, 로드/오픈/제출) + 템플릿 2(`erp_order_tab.html`, `erp_order_tab_mobile.html`)

**(1) 백엔드 — `foms/api/cs/as_orders.py` `api_as_register` (L247-308)**
- payload에서 `shipping_scheduled_date` 읽기(optional).
- 값이 있으면 `YYYY-MM-DD` 형식 검증(명시적 구현):
  ```python
  raw_ship = str(data.get("shipping_scheduled_date") or "").strip()
  if raw_ship:
      try:
          datetime.datetime.strptime(raw_ship, "%Y-%m-%d")   # 형식 오류 → ValueError
      except ValueError:
          raise ValueError("상차일 형식이 올바르지 않습니다. (YYYY-MM-DD)")
      order.shipping_scheduled_date = raw_ship
  ```
  - `ValueError`는 함수 말미 `except ValueError → 409`(L303-305)로 전파(조용한 무시 금지).
  - 빈 문자열/None/키 없음 → 컬럼 미변경(기존값 보존).
- 지방주문 전용 게이팅은 두지 않는다(비지방이면 UI가 안 보내므로 무해; 백엔드는 값이 오면 검증만).
- 위치: `order.as_received_date = today` / `order.status = "AS_RECEIVED"` (L278-279) 부근에서 설정.
- 성공 응답에 `shipping_scheduled_date`(적용된 값 또는 기존값) 에코 — 통합 테스트에서 assert.

**(2) GET 구조 응답에 상차일 노출 — `foms/api/erp_orders_structured.py` (L569-583)**
- 반환 dict에 `'shipping_scheduled_date': getattr(order, 'shipping_scheduled_date', None) or ''` 추가.
- 이유: AS 모달 prefill은 flat 컬럼값이 필요한데 `structured_data`에는 없다. 로더가 이 GET 응답을 사용.

**(3) 로더 — `static/js/orders/erp-order-shared.js` (L1846-1853 부근)**
- `data.shipping_scheduled_date`를 전역에 보관: `window.__erpShippingScheduledDate = data.shipping_scheduled_date || '';`
- 기존 `data.is_regional` 로드 로직 옆에 추가.

**(4) AS 모달 오픈 — `static/js/orders/erp-order-shared.js`**
- 모달 오픈은 전 코드베이스에서 `erpSaveStructuredOnce`의 transitioningIntoAsReceived 블록(L2358-2381)이
  유일 경로임을 리뷰로 확인(선언형 `data-bs-toggle` 오프너 없음). 여기에만 배선하면 충분.
- 모달 오픈 시 **매번 재평가**(idempotent):
  - `#erp-regional-order` 체크 → 상차일 래퍼 `d-none` 제거(노출), 미체크 → `d-none` 추가(숨김).
  - 노출 시 date input 값 = `window.__erpShippingScheduledDate || ''` prefill(미설정이면 빈 값).
- 모달 제출 핸들러(`initAsReceiveModal`, L2751-2845):
  - 지방주문이고 상차일 값이 있으면 `/as/register` body에 `shipping_scheduled_date` 포함(비지방/빈값이면 미전송).
  - 성공 후 `window.__erpShippingScheduledDate`를 제출값으로 갱신.

**(5) AS 모달 HTML — 상차일 필드 추가**
- `templates/orders/partials/erp_order_tab.html` (asReceiveModal, L514-560)
- `templates/orders/partials/erp_order_tab_mobile.html` (동일 모달)
- 필드: `<input type="date" id="as-receive-shipping-date">` + 라벨("상차일(지방주문)").
  - 기본 `d-none`(숨김). JS가 지방주문일 때만 노출.
  - 선택 입력이므로 `*` 필수 표시 없음. 안내 문구: "지방주문은 상차일 입력 시 상차 예정 알림으로 자동 등록됩니다."

### 4.3 대시보드 (변경 없음)
- 승격·AS 뱃지는 서버 버킷(`dashboard.py:533-549`) + 템플릿(`regional_dashboard.html`)이 이미 처리.

## 5. 엣지 케이스 / 섀도우 패스
- 상차일 미입력(빈 값): 상차일 없이 AS접수만. 대시보드에서 `pending_orders`(진행 중)로 표시(정상). 이후 상차일 입력 시 상차 예정 알림으로 이동.
- 과거 상차일 입력: 서버가 `shipping_completed`(상차완료)로 분류(상차 예정 알림 아님). AS 뱃지는 상차완료 섹션에는 없음(현행 유지) — D2/D4 범위 밖.
- 비지방 주문: UI가 필드를 숨기고 값 미전송. 백엔드는 값이 와도 검증만.
- 형식 오류 날짜: 409 반환(조용한 무시 금지). 프론트는 alert.
- prefill 글로벌 미설정(draft/신규 주문 등 폼 로더 미실행): `window.__erpShippingScheduledDate`가 undefined → `|| ''`로 빈 값 prefill(안전).
- 2요청 부분 커밋(리뷰 지적): `/as/register`(status+상차일 커밋) 성공 후 후속 `PUT /structured` 실패 시에도 status·상차일은 이미 기록됨. **기존 지방주문(1차 시나리오)**에서는 무해(대시보드 진입 정상). 단, 같은 저장에서 `is_regional`/`construction_type`을 처음 세팅하면서 PUT이 검증 실패하면 지방 플래그 미갱신 → 지방 대시보드 미노출 가능(우선순위 낮음, 기존 저장 흐름의 한계이며 본 SPEC이 도입하는 회귀는 아님).
- 재-AS(이미 AS_RECEIVED 상태에서 재저장): 모달은 "전환 시"에만 뜸(prevStage != AS_RECEIVED). 이미 AS면 일반 PUT 경로 — 상차일은 대시보드에서 수정(현행). 본 SPEC 범위는 "AS접수 전환 시 상차일 동시 입력".
- 리다이렉트: AS 저장 후 `/erp/as`(AS 대시보드) 유지(기존). 지방 대시보드 등장은 데이터 기반(재진입 시). — 리다이렉트 변경은 비목표.

## 6. 비목표 (Non-goals)
- 지방 대시보드 상태 드롭다운의 겹침(change/blur 이중제출·오버라이드 오탐·체크리스트 경쟁) 리팩터 (B안).
- 상차완료 섹션 AS 뱃지 추가.
- AS 저장 후 지방 대시보드로 리다이렉트 변경.

## 7. 테스트 계획
> 리뷰 최대 위험(optional 필드 배선 누락 시 "원래 버그와 동일한 조용한 무동작") 방어를 위해
> 프론트 계약 테스트를 **필수**로 승격한다.
- 백엔드 단위: `api_as_register`
  - `shipping_scheduled_date` 유효값 → `order.shipping_scheduled_date` 설정 + status/as_received_date 정상 + 성공 응답 에코 assert.
  - 빈 값/키 없음 → 컬럼 미변경.
  - 형식 오류 → 409.
- GET 구조 응답: `shipping_scheduled_date` 키 포함 검증.
- 버킷 통합: 지방주문 + `/as/register`(미래 상차일) → `regional_dashboard`의 `shipping_alerts`에 포함 + AS 뱃지. (`tests/domains/test_regional_dashboard_buckets.py` 확장)
- 프론트 계약(**필수**): AS 모달 HTML에 상차일 필드(`id="as-receive-shipping-date"`) 존재 + 래퍼 기본 `d-none`
  (두 템플릿 모두). 정적 계약 테스트로 데스크톱·모바일 모달 양쪽에 필드가 있음을 고정(한쪽 누락 방지).

## 8. 검증 (완료 기준)
- `python -c "import app; print('APP_OK')"` → APP_OK
- 관련 pytest(regional buckets + as register + structured GET) green
- `python tools/perf/perf_scan.py --guard` (변경분) high 없음
- postgres MCP로 실제 지방 AS 주문/상차일 데이터 정합 확인(구현·인스펙션 단계)
- push 전 `scripts/ops/pre_push_smoke.ps1` exit 0

## 9. 구현 순서 (순차)
1. 백엔드 `api_as_register` 상차일 수용 + 검증
2. GET 구조 응답 `shipping_scheduled_date` 노출
3. AS 모달 HTML 필드 추가(데스크톱 + 모바일)
4. `erp-order-shared.js` 로드/오픈/제출 배선
5. 테스트 추가·수정 → green
6. 1:1 소스코드 리뷰 → 최종 full inspection
