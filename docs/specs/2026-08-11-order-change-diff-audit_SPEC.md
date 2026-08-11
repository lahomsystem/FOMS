# 주문 저장 변경내역 감사 (ORDER-DIFF-00) — 1안 스펙

- 작성: 2026-08-11
- 상태: **승인 대기** (Research 완료 → Plan)
- 기준 코드: production `ede486f7`
- 결정 전제(사용자 승인 2026-08-11): 1안 우선 / PII **원문 기록** / 품목 변경 **포함**

## 1. 문제 (운영 실측)

운영 `/security_logs` 최근 50행 전수 조사:

| 행위 | 건수 | before/after |
|---|---|---|
| ORDER_STRUCTURED_SAVED | 25 | **0** |
| CHANNEL_PUSH_SENT | 10 | 0 |
| FILE_UPLOADED/DELETED | 10 | 해당없음 |
| 합계 | 50 | **0 / 50** |

`detail` 키 전수 = `customer_name`·`order_type`(맥락), `mode`, 파일 메타. **값 변경 내역 0개.**

원인은 배선 위치다. 필드 단위 기록기 `describe_field_change(before, after)` 는 이미 존재하고
구(舊) 평면 경로(`foms/api/orders/field_update.py`·`status.py`·`regional.py`)만 쓴다.
현 주력 편집기인 ERP 구조화 저장은 두 지점 모두 값을 남기지 않는다:

- 전체 저장 `foms/api/erp_orders_structured.py:1110` → `detail={'mode':'full', ...}` — 변경 필드조차 없음
- 인라인 저장 `foms/api/erp_orders_structured.py:845` → `detail={'mode':'inline','field': <경로>}` — 경로만, 값 없음

대체 원장도 없다. `order_events` 는 긴급·실측일·오너팀 **3종만** from/to 를 남기고
(`erp_orders_structured.py:409`), 주문 스냅샷/리비전 테이블은 존재하지 않는다.

결과: "누가 언제 주문을 저장했다"까지만 남고 "무엇이 어떻게 바뀌었다"가 없다.
금액·일정·품목 규격 분쟁 시 감사 원장으로 되짚을 수 없다.

## 2. 목표 / 비목표

**목표**
1. 주문 저장(전체·인라인) 시 **변경된 필드의 이전값→새값**을 감사 원장에 남긴다.
2. 화면이 그 변경을 사람 언어로 읽는다("실측일 8/12 → 8/14 외 3건").
3. 스키마 마이그레이션 없이(기존 `security_logs.detail` JSONB) 끝낸다.

**비목표 (후속 2안 이후)**
- 필드 단위 SQL 질의용 정규화 테이블(`order_field_changes`)
- 주문 상세의 변경이력 탭 / 되돌리기
- 변경 사유(reason) 입력 UX
- 보존(retention) 정책
- 품목 안정 UUID (ITEM-ID-00 연계)

## 3. 설계

### 3.1 differ SSOT

신규 `foms/services/orders/structured_diff.py`

```python
def diff_structured(old_sd: dict, new_sd: dict, *, max_changes: int = 40) -> DiffResult
```

- 반환 `DiffResult(changes: list[Change], total: int, truncated: int)`
- `Change = {'path','label','before','after','op'}`, `op ∈ {'set','clear','add','remove'}`
- **화이트리스트 pull 방식** — 전체 트리 순회 금지(§3.2 경로 목록만 읽는다). hot path 비용을 경로 수로 고정한다.
- **값 정규화**: `None` / `''` / 키 부재를 모두 "빈값"으로 동일 취급 → 저장만 눌러도 변경이 뜨는 노이즈 차단.
  숫자는 문자열/숫자 혼재를 정규화 후 비교(구조화 데이터가 문자열 저장이 섞여 있다).
- **문자열 절단**: 값 120자 초과 시 앞 120자 + `…`, `Change['truncated_value']=True`. 절단 사실을 숨기지 않는다.

### 3.2 화이트리스트 (staging 실데이터 인벤토리 기반, 2026-08-11 조회)

staging 주문 3,412건의 `structured_data` 실제 키 분포에서 뽑았다.

| 묶음 | 경로 |
|---|---|
| 일정 | `schedule.measurement.date`·`.time`, `schedule.construction.date`·`.time`, `schedule.as_visit.*` |
| 당사자 | `parties.customer.name`·`.phone`, `parties.orderer.*`, `parties.manager.name` |
| 현장 | `site.address_full`, `site.address_detail` |
| 상태 | `workflow.stage` |
| 긴급 | `flags.urgent`, `flags.urgent_reason` |
| 배정 | `assignments.owner_team`, `assignments.drawing_assignee_user_ids` |
| 금액 | `totals.` 8종(`items_total`·`deposit_amount`·`balance_amount`·`final_amount`·`discount_amount`·`free_input_amount`·`contract_total`·`shipping_price`) |
| 결제 | `payment.deposit`, `payment.discount`, `payment.free_input`, `payment.cash_receipt` |
| 출고/시공 | `shipment.sales_delivery`, `shipment.construction_time`, `shipment.construction_workers`, `shipment.trip`, `shipment.as_billing`, `shipment.as_pending` |
| 비고 | `notes` (문자열 SSOT — `project_structured_notes_is_string_not_dict`) |
| 품목 | `items[i].` 14종(`product_name`·`price`·`spec_width`·`spec_height`·`spec_depth`·`spec`·`color`·`handle`·`option_detail`·`extra_input`·`misc`·`internal`·`measurement_date`·`construction_date`) + `spec_rows`(요약 비교) |

**제외**: `quests`·`meta`·`confidence`·`schema_version`·`entity_type`·`estimate_preview`·`drawing_*`·`channeltalk_*`·`workflow.history`·`shipment.as_log`·`payment.*_confirmed*`.
사유 — (a) 별도 원장이 이미 있다(`as_log` append-only, 결제 확인은 `PAYMENT_CONFIRMED` action, 도면은 `drawing_revisions`),
(b) 파생/캐시 값이라 사람 판단에 무의미, (c) BC 공식 경고("All Fields 금지")대로 볼륨을 통제한다.

### 3.3 품목(list) 매칭 — 알려진 한계 명시

`structured_data['items']` 는 **위치 인덱스 배열**이고 안정 UUID가 없다(ITEM-ID-00 진행 중).

v1 규칙:
- 인덱스로 짝짓는다. 길이 증가 = 뒤쪽 인덱스 `add`, 감소 = `remove`.
- 각 변경의 `label` 에 그 품목의 `product_name` 을 함께 넣는다 → "2번 품목(붙박이장) 단가 …".
- **중간 삽입/순서 변경은 여러 품목이 동시에 바뀐 것으로 보인다.** 이건 v1의 알려진 한계이며,
  NetSuite 서브리스트 사각지대와 같은 계열의 문제다. 안정 identity 도입(2안/ITEM-ID-00) 전까지 유지하고,
  테스트로 그 동작을 **문서화**한다(숨기지 않는다).
- `spec_rows`(중첩 배열)는 행 수 + 정규화 직렬화 비교로 "규격표 변경됨(3행→4행)" 수준만 남긴다. 셀 단위 diff는 v1 제외.

### 3.4 라벨·표시

- `foms/services/audit_message_display.py` 에 `PATH_LABELS: dict[str,str]` 신설(표시 SSOT 유지).
  `FIELD_LABELS`(평면 컬럼)와 별개 사전 — 경로 문법이 다르다. 미등재 경로는 **경로 자체를 노출**한다(감사 은닉 금지, 기존 `ACTION_LABELS` 규약과 동일).
- 값 포맷은 기존 `format_value` 재사용(날짜·불리언·체크박스 어휘).
- 문장: `describe_order_action` 확장 → `주문 #4727 (이진원) — 주문 저장: 실측일 8/12→8/14 외 3건`.
  변경 0건이면 기존 문장 유지(`전체 저장`).

### 3.5 detail 스키마

```json
{
  "mode": "full",
  "customer_name": "이진원",
  "order_type": "주문",
  "change_count": 5,
  "truncated": 0,
  "changes": [
    {"path": "schedule.measurement.date", "label": "실측일",
     "before": "2026-08-12", "after": "2026-08-14", "op": "set"}
  ]
}
```

- 상한 40건. 초과분은 버리지 않고 `truncated: N` 로 개수를 남기고 화면이 "외 N건"으로 표기한다(무성 절단 금지).
- PII: 사용자 결정에 따라 전화번호·주소·비고는 **원문 저장**. 열람은 ADMIN 전용 화면으로 제한된 현 구조를 유지한다.
  `SecurityLog` docstring 의 "PII 원문 금지" 문구는 이 결정에 맞춰 **범위를 명시**하도록 갱신한다(비밀번호·토큰은 여전히 금지).

### 3.6 배선 지점

| 경로 | 파일:라인(ede486f7) | 조치 |
|---|---|---|
| 전체 저장 PUT | `erp_orders_structured.py:1107` | `_mutate` 안에서 이미 잡은 `old_sd` 와 최종 `structured_data` 로 diff → detail 병합 |
| 인라인 PATCH | `erp_orders_structured.py:840` | 같은 differ 사용(단일 경로라 결과 1건), `field`+before/after 채움 |
| 초안 제출 | `ORDER_DRAFT_SUBMITTED` | v1 제외(신규 생성이라 diff 무의미) |

성능: 화이트리스트 경로 약 60 + 품목당 15키. 저장 1회 O(60 + 15N), 순수 dict 접근이라 쿼리 증가 0.
`AGENTS.md` 성능 가드 대상(hot path 쿼리) 아님 — 그래도 전체 트리 순회는 금지 규칙으로 못박는다.

## 4. 화면

- **상세 내용 칸**: 문장 + 변경 3건까지 인라인 표기, 초과 시 접이식으로.
- **부가정보 칸**: 기존 맥락 키 유지. `changes` 는 JSON 원문에도 그대로 남는다(원장 = 원문).
- 감사 화면 CSS/JS 수정 시 `templates/admin/*.html` 의 `?v=` 핀 동반 범프(기존 계약).

## 5. 완료 기준 (테스트)

1. `tests/domains/test_structured_diff.py` (신규)
   - `None`/`''`/키부재 동치 → 변경 0건
   - 값 변경·추가·삭제 3종 op
   - 화이트리스트 밖 경로(`quests`·`meta`) 무시
   - 40건 초과 시 `truncated` 정확
   - 품목 중간 삽입의 **알려진 오탐**을 그대로 문서화하는 테스트
2. `tests/domains/test_order_save_audit_diff.py` (신규)
   - PUT 전체 저장 후 `security_logs.detail['changes']` 에 실제 변경만 존재
   - PATCH 인라인 저장 후 before/after 존재
   - 변경 없는 저장 → `change_count: 0`, 문장 회귀 없음
3. 기존 표시 계약 회귀: `test_admin_audit_screen_readability_1/2/3`·`test_audit_message_display`·`test_audit_message_assembly_contract` green
4. `python -c "import app; print('APP_OK')"` + `scripts/ops/pre_push_smoke.ps1` exit 0

## 6. 리스크

| 리스크 | 완화 |
|---|---|
| 품목 인덱스 시프트 오탐 | 라벨에 품목명 병기 + 한계 테스트로 문서화, 2안에서 안정 identity |
| detail JSONB 비대 | 40건 캡 + 값 120자 절단 |
| 저장 경로 성능 | 화이트리스트 pull, 전체 순회 금지 |
| 동시 저장 시 old_sd 신뢰성 | `_mutate` 트랜잭션 내부에서 읽은 값이라 낙관 잠금과 일관 |
| PII 확대 | 열람 ADMIN 전용 유지, 비밀번호·토큰은 여전히 기록 금지 |

## 7. 근거 (상용 ERP 표준)

- SAP `CDHDR`/`CDPOS` — 헤더(누가·언제·무슨 객체) + 항목(테이블·키·**필드·구값·신값**) 2단 분리
- Oracle Fusion — 비즈니스 객체별 **감사 속성 선택** 후 create/update/delete 추적
- Dynamics 365 BC — 테이블·필드 선택 추적, 공식 경고 "All Fields 금지(성능)"·"보존 정책으로 만료"
- NetSuite System Notes — Old/New Value 컬럼, **서브리스트 일부 미기록**(라인 사각지대 실존)
- Odoo — `tracking=True` 필드만 from→to
- 21 CFR 11.10(e) — 사용자·시각·행위·레코드·**구값·신값·변경사유** 7요소, 이전 기록 은닉 금지
- SOX 실무 — INSERT 전용 감사 테이블·before/after·7년 보존

## 8. 후속 (2안 이후)

`order_field_changes` 정규화 테이블(헤더 = 이 `security_logs` 행) → "실측일 바뀐 주문 전부",
"금액 내린 사람" 같은 SQL 질의. 그 다음 주문별 변경이력 탭 → 되돌리기 → 변경 사유 → 보존 정책.
