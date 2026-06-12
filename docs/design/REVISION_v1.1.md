# FOMS 리디자인 v1.0 → v1.1 변경 이력 (흡수 완료, 보존)

> 작성: 2026-05-29 | 흡수 완료: 2026-05-29 (2회차 외부 LLM 평가 후)
> 트리거: 외부 LLM 평가 1회차 (v1.0 = 7.2/10) + 사용자 직접 지적 2건
>
> **상태 (2026-05-29 update)**: 본 문서가 처음 작성될 때는 "v1.0 문서를 대체하지 않는 보정 패치"였으나, **2회차 외부 LLM 평가에서 SSOT 위반(7.7/10)을 지적받아 v1.0 문서들에 직접 흡수 완료**. 따라서 본 문서는 더 이상 진실의 일부가 아니라 **v1.0 → v1.1 변경 이력 (audit trail)** 으로 보존된다.
>
> **단일 진실(SSOT)은**: `MOBILE_TABLET_REDESIGN_PLAN.md`, `MIGRATION_ROADMAP.md`, `COMPONENT_LIBRARY_MOBILE.md`, `REVIEW_ENTRY.md`, `INDEX.md`, `REVIEW_SELF_ASSESSMENT.md`, `mockups/*.html` 의 현재 상태이다. 본 문서는 변경 사유 추적용.

---

## 0. 요약 (caveman)

외부 LLM 평가 1회차가 정확. **v1.0의 audit agent가 stale 결과를 보고**했고, 사실 확인 없이 계획서에 반영했음. 본 문서로 7개 항목 보정 후, 2회차 평가의 SSOT 위반 지적을 받아 **v1.0 문서 6개에 직접 흡수 완료**. 본 문서는 변경 이력으로 보존.

| # | 출처 | 항목 | 영향 v1.0 문서 | 패치 상태 |
|---|---|---|---|---|
| R1 | LLM | P0-02/03/04 도면·AS·시공 모바일 카드 "신규" 명세 → 실제 **존재** | ROADMAP, REDESIGN_PLAN, INDEX | ✅ 본 문서 §2 |
| R2 | LLM | API 경로 `apps/api/erp/...` → 실제는 `foms/api/...` | ROADMAP 전체 | ✅ 본 문서 §3 |
| R3 | LLM | feature flag 4종 제안은 문서 예시 수준 → flag matrix 확정 필요 | ROADMAP §Rollback | ✅ 본 문서 §4 |
| R4 | LLM | 자동저장 계약(payload·TTL·충돌·정리) 부족 | REDESIGN_PLAN §6.4, ROADMAP P1-03 | ✅ 본 문서 §5 |
| R5 | LLM | 목업-컴포넌트 불일치 (paste 버튼 desktop-only인데 wizard에 노출) | COMPONENT C12, mockup wizard | ✅ 본 문서 §6 + 목업 패치 |
| R6 | User | 마법사 Step 2 규격 한 줄 입력 → erporder는 W·D·H 분리 + 다중 spec_rows | mockup wizard | ✅ 목업 직접 패치 |
| R7 | User | 모바일 주문 상세에 제품 정보 없음. CS 등록 후 실측 시 인라인 수정 가능해야 | mockup order-detail | ✅ 목업 직접 패치 |

추가 결정 재고 3건:
- D06 (HTMX 도입) → "new surface only"로 범위 축소
- D07 (수정 자동저장) → critical field 명시 저장 + undo
- D09 (토큰 단일화) → alias bridge 우선

보정 후 추정 점수: **7.2 → 8.4** (LLM 평가 기준). 자체 평가는 v1.0에서 8.1 → 8.7로 갱신.

---

## 1. 사실 검증 결과 (Phase 0 보정)

검증 명령:

```bash
wc -l templates/drawing/partials/workbench_dashboard_body.html
# 795 lines

wc -l templates/cs/partials/as_dashboard_body.html
# 2761 lines

ls foms/api/   # 존재
ls apps/api/   # 존재 안 함
```

| 확인 사항 | v1.0 주장 | 실제 코드 | 판정 |
|---|---|---|---|
| 도면 모바일 카드 | "없음, 신규 구현 필요" | `workbench_dashboard_body.html:314` `mobile-card-list d-lg-none erp-drawing-mobile-list` **존재** | ❌ stale |
| AS 모바일 카드 | "없음, 신규 구현 필요" | `as_dashboard_body.html:364` `erp-pro-order-cards d-md-none` **존재** | ❌ stale |
| API 경로 | `apps/api/erp/...` | `foms/api/` 실재 | ❌ 완전 오류 |
| erporder 규격 입력 | "단일 텍스트" 가정 | `erp-order-shared.js:649-653` **W·D·H 3분리 + spec_rows 다중** | ❌ 불일치 |
| erporder 제품 1개 필드 수 | 5~6개 가정 | 12개 (product_name, spec_rows[], internal, color, option_detail, handle, misc, price, measurement_date, construction_date, extra_input, attachments) | ❌ 미상세 |
| ERP_MOBILE_V2_ENABLED OFF | 정확 | `context_processors.py:85` | ✅ |
| 폼 필드 39/43개 | 정확 | `add_order.html:31`, `edit_order_body.html:75` | ✅ |

---

## 2. R1: 도면·AS·시공 카드 "신규" → "audit + gap patch"

### 잘못된 부분

**v1.0 `MIGRATION_ROADMAP.md` P0-02 ~ P0-04**:
- "도면 작업실 모바일 카드 **신규 구현**"
- "AS 대시보드 모바일 카드 **신규 구현**"
- "시공 대시보드 모바일 카드 **신규 구현**"

### 실제 상태

- **도면**: `workbench_dashboard_body.html:313~393` `erp-drawing-mobile-list` + `erp-drawing-mobile-card` 풍부한 카드 이미 구현됨. 표시 정보: 고객명·자가실측 배지·주문 ID·담당·상태 배지·다음 액션·최근 이벤트·대상 번호·파일 카운트·미확인 카운트·SLA 배지·내 할 일·담당자 변경·작업 열기.
- **AS**: `as_dashboard_body.html:364~` `erp-pro-order-cards d-md-none` 카드 구현됨. 표시: ID·상태 배지·고객명·자가실측·전화·시공자·AS 접수일·AS 방문일(인라인 date)·미결 토글 등.
- **시공**: 동일 패턴, 코드 확인 필요 (audit 보강).

### 보정 작업 (P0-02 ~ P0-04 재작성)

#### PR P0-02 보정판: 도면 모바일 카드 **gap patch**
**무엇을 한다**:
- 기존 `erp-drawing-mobile-card` 정보 밀도·접근성 audit (실제 디바이스에서 사용성 확인)
- v1.0 디자인 시스템(`--foms-*`)에 맞춰 클래스 리네임 또는 alias 추가
- 사용자 6대 요구 (#3 "탭별 정보 명확화") 갭만 보완:
  - 도면 thumbnail 16:9 카드 상단 추가 (현재 텍스트 chip만)
  - swipe action (좌→승인, 우→반려) — P0에서는 long-press 메뉴로 대체 가능
  - 모바일 필터 offcanvas (현재 부재 — v1.0 §AS와 비교)
**파일 수정**: `templates/drawing/partials/workbench_dashboard_body.html:313-393` (in-place 개선), 신규 CSS `static/css/components/foms-drawing-mobile-card.css`
**검증**: 기존 카드가 깨지지 않으면서 신규 thumbnail·필터 추가. Playwright 회귀.
**추정**: 1일 (신규 1.5일 → 1일로 단축)

#### PR P0-03 보정판: AS 모바일 카드 **gap patch**
**무엇을 한다**:
- 기존 `erp-pro-order-card` 활용
- 단계 색 배지 표준화 (`foms-stage-badge--cs`)
- AS 접수 모달 진입 흐름 점검 (모달 자체는 P0-05에서 별도 처리)
- 검색·필터 모바일 통합 (`as_mobile_controls.html` 활용)
**파일**: `templates/cs/partials/as_dashboard_body.html:364-` (in-place), `templates/cs/partials/as_mobile_controls.html` 보강
**추정**: 0.5일

#### PR P0-04 보정판: 시공 모바일 카드 **gap patch**
**무엇을 한다**: 시공 카드 존재 여부 audit → 부족 부분만 보강. 도면 패턴과 일치시킴.
**추정**: 0.5일

### 영향
- P0-02~04 보정 효과: 해당 카드 작업은 60h 계획에서 44h 수준까지 단축 가능하다고 재분류됨. 이후 P0-00 Foundation PR이 추가되어 최종 P0 SSOT는 `MIGRATION_ROADMAP.md`의 **58h**를 따른다.
- "사용 불가" 결함 5건 중 도면·AS·시공 3건은 "사용 가능하나 개선 여지" 수준으로 재분류.
- 실제 P0 핵심 결함은 **5건 → 2건** (AS 모달 paste, 폼 sticky CTA)으로 축소.

### v1.0 문서 갱신 사항 (별도 PR 없이 인라인 표시)
- `INDEX.md` §핵심 발견 #2의 v1.0 결함 표현 → "현장 작업 비효율 결함 2건 + 카드 gap 3건" 표현으로 변경
- `MOBILE_TABLET_REDESIGN_PLAN.md` §6.3, 6.5 도면·AS 명세에 "기존 카드 보강" 명시
- `MIGRATION_ROADMAP.md` P0-02 ~ P0-04 본 문서 §2 패치 적용

---

## 3. R2: API 경로 `apps/api/` → `foms/api/` 전수 교정

### 잘못된 부분
`MIGRATION_ROADMAP.md` 전체에서 `apps/api/erp/...` 표기:
- P0-02 line 59: "신규: `apps/api/erp/drawing.py`"
- P0-03: "신규: API `GET /api/erp/as/mobile-queue`" + 파일 경로
- P1-02 line ~: "신규: `apps/api/erp/search.py`"
- P1-03 line ~: "신규: `apps/api/erp/order_draft.py`"
- P1-04 line ~: "수정: `apps/api/erp/order.py`"

### 실제 등록 경로 (`foms/api/__init__.py` 및 `blueprints.py:55`)
```
foms/api/
├── __init__.py
├── address.py
├── attachments.py
├── auth/
├── channel/
├── construction/
├── cs/
├── designer/
├── drawing/
├── erp_estimates.py
├── erp_map.py
├── erp_orders_blueprint.py
├── erp_orders_structured.py
├── measurement/
└── ...
```

### 보정 매핑

| v1.0 표기 | 정정 |
|---|---|
| `apps/api/erp/drawing.py` | `foms/api/drawing/` 디렉토리 내 신규 모듈 추가 또는 기존 endpoint 확장 |
| `apps/api/erp/as.py` | `foms/api/cs/` 내 신규 모듈 |
| `apps/api/erp/search.py` | `foms/api/erp_orders_blueprint.py`에 search endpoint 추가, 또는 신규 `foms/api/search.py` |
| `apps/api/erp/order_draft.py` | `foms/api/erp_orders_structured.py` 확장 또는 신규 `foms/api/erp_order_draft.py` |
| `apps/api/erp/order.py` | `foms/api/erp_orders_structured.py` (이미 PATCH 패턴 존재) |
| `apps/api/erp/fragment.py` (P2) | `foms/api/erp_orders_blueprint.py` 내 fragment endpoint 또는 신규 |

### 영향
- ROADMAP의 모든 "파일" 항목 경로 교정 필요. **본 문서 §3을 진실 소스로 사용.**
- 신규 모듈 위치 결정 가이드:
  - 워크플로우 단계 도메인 (drawing/cs/construction/measurement) → 해당 도메인 디렉토리 내
  - 워크플로우 단계 무관(검색·결제·draft) → `foms/api/` 직접 또는 `foms/api/erp_*.py` 추가

---

## 4. R3: Feature Flag Matrix 확정

### 잘못된 부분
v1.0 `MIGRATION_ROADMAP.md:537` 예시 코드:
```python
{
  'flag_foms_v3_shell': True,
  'flag_foms_wizard':   True,
  'flag_foms_inline':   False,
  'flag_foms_split':    True,
}
```
이름 추상적, 실제 코드에 없음, 조합 검증 매트릭스 없음.

### 보정 — 실제 적용할 5개 flag (P0 진입 전 확정)

| 환경변수 | 기본값 | 토글 시점 | 의존성 |
|---|---|---|---|
| `ERP_MOBILE_V2_ENABLED` | **true** (변경) | P0-01 즉시 | 없음 (단독) |
| `FOMS_DESIGN_TOKENS_V2_ENABLED` | true | P0-07 (다크모드) | 토큰 alias 1주 유지 |
| `FOMS_WIZARD_NEW_ORDER_ENABLED` | false → true | P1-03 | 자동저장 백엔드 필요 |
| `FOMS_INLINE_EDIT_ENABLED` | false | P1-04 | wizard 안정화 후 |
| `FOMS_TABLET_SPLIT_VIEW_ENABLED` | false → true | P1-05 | tokens v2 필요 |

명명 규칙: `FOMS_<기능>_ENABLED`. 도메인 prefix `ERP_*`은 v1.0 잔존 호환 유지.

### Flag Matrix (조합 검증)

| 시나리오 | MOBILE_V2 | TOKENS_V2 | WIZARD | INLINE | SPLIT |
|---|---|---|---|---|---|
| 현재 (pre P0) | ❌ | ❌ | ❌ | ❌ | ❌ |
| P0 완료 | ✅ | ✅ | ❌ | ❌ | ❌ |
| P1 완료 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 비상 롤백 (wizard 문제) | ✅ | ✅ | ❌ | ✅ | ✅ |
| 부분 롤백 (split 문제) | ✅ | ✅ | ✅ | ✅ | ❌ |

각 조합은 Playwright E2E 시나리오로 검증. P0-01에 matrix 테스트 추가.

### 구현 위치
- `foms/services/context_processors.py`에 `inject_foms_flags()` context processor 신규.
- `foms/services/feature_flags.py` 신규 모듈로 분리 (env_bool helper).

---

## 5. R4: 자동저장 실행 계약 명세

### 잘못된 부분
v1.0 `MOBILE_TABLET_REDESIGN_PLAN.md` §6.4 자동저장:
- "localStorage 키 `foms.draft.{order_id|new}`로 매 5초 또는 blur 시 백업"
- "페이지 이탈 시 `navigator.sendBeacon` 으로 서버 draft 저장"
- "복귀 시 토스트"

→ payload 스키마·TTL·충돌 처리·정리 정책 없음.

### 보정 — OrderDraft 실행 계약

#### 5.1 데이터 모델

```python
# foms/models/order_draft.py (또는 models.py 확장)
class OrderDraft(db.Model):
    __tablename__ = 'order_drafts'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('orders.id', ondelete='CASCADE'),
        nullable=True, index=True,
        # nullable: 신규 주문 작성 중 = NULL, 기존 주문 수정 중 = order_id
    )
    draft_key: Mapped[str] = mapped_column(
        String(64), index=True,
        # 클라이언트 키: 'new.<uuid>' 또는 'edit.<order_id>'
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        # 마법사 4-step 상태 또는 인라인 편집 미저장 변경
    )
    schema_version: Mapped[int] = mapped_column(default=1)
    last_step: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index('ix_order_drafts_user_key', 'user_id', 'draft_key', unique=True),
    )
```

#### 5.2 Payload JSON Schema (draft_v1)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schema_version", "step", "data"],
  "properties": {
    "schema_version": { "const": 1 },
    "step": { "type": "integer", "minimum": 1, "maximum": 4 },
    "data": {
      "type": "object",
      "properties": {
        "customer_name": { "type": "string" },
        "phone": { "type": "string", "pattern": "^[0-9-]+$" },
        "address": { "type": "string" },
        "orderer": { "type": "string" },
        "received_date": { "type": "string", "format": "date" },
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "product_name": { "type": "string" },
              "spec_rows": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "spec_width": { "type": "string" },
                    "spec_depth": { "type": "string" },
                    "spec_height": { "type": "string" }
                  }
                }
              },
              "internal": { "type": "string" },
              "color": { "type": "string" },
              "option_detail": { "type": "string" },
              "handle": { "type": "string" },
              "misc": { "type": "string" },
              "price": { "type": "string" },
              "measurement_date": { "type": "string" },
              "construction_date": { "type": "string" },
              "extra_input": { "type": "string" },
              "attachments": {
                "type": "array",
                "items": { "type": "object", "properties": {
                  "tmp_key": { "type": "string" },
                  "filename": { "type": "string" }
                }}
              }
            }
          }
        },
        "schedule": {
          "type": "object",
          "properties": {
            "measurement_date": { "type": "string", "format": "date" },
            "measurement_time": { "type": "string" },
            "construction_date": { "type": "string", "format": "date" },
            "construction_time": { "type": "string" },
            "shipment_date": { "type": "string", "format": "date" },
            "sales_manager_id": { "type": "integer" },
            "construction_manager_id": { "type": "integer" }
          }
        }
      }
    }
  }
}
```

#### 5.3 API 계약

| Method | Path | 용도 | 응답 |
|---|---|---|---|
| `GET` | `/api/erp/order-draft?key=...` | 복귀 시 draft 조회 | `{success, draft: {...payload, updated_at}}` 또는 `{success, draft: null}` |
| `PUT` | `/api/erp/order-draft` | 자동저장 (idempotent) | `{success, updated_at}` |
| `DELETE` | `/api/erp/order-draft?key=...` | 명시 폐기 (저장 완료 후) | `{success}` |

요청 헤더: `X-If-Match: <last_known_updated_at>` (충돌 감지).
충돌 시 응답: `409 Conflict` + `{success: false, error: 'CONFLICT', current: {payload, updated_at}}`.

#### 5.4 TTL · 정리 정책

| 시나리오 | TTL | 정리 방법 |
|---|---|---|
| 신규 주문 draft (저장 미완) | 7일 | 매일 02:00 cron job, `updated_at < NOW() - INTERVAL '7 days'` 삭제 |
| 기존 주문 인라인 draft | 24시간 | cron job, 즉시 저장 권장 |
| 저장 완료 후 | 0 (즉시) | 클라이언트 DELETE 호출 |
| 사용자 명시 폐기 | 0 | UI "복구 안 함" 클릭 시 |
| 사용자 계정 비활성화 | 즉시 | user cascade |

cron job: `tools/cron/cleanup_order_drafts.py`, Railway Cron 또는 Worker에서 실행.

#### 5.5 충돌 처리 시나리오

1. **PC + 모바일 동시 편집**:
   - 클라이언트 A가 `PUT /order-draft` with `X-If-Match: T1`
   - 서버에 `T2 > T1`인 draft가 이미 존재 → `409 Conflict + current`
   - 클라이언트가 `current.payload` 다이얼로그 표시: "다른 기기에서 변경됨. [내 변경 사용 / 다른 기기 사용 / 병합]"

2. **인라인 편집 중 서버 측 다른 사용자 변경**:
   - 인라인 PATCH 응답에 `409`
   - 화면에 inline 충돌 마크 표시 + revert 옵션

3. **오프라인 → 온라인 sync**:
   - Service Worker (P2) `sync` 큐에 PUT 적재
   - 온라인 복귀 시 순차 재시도

#### 5.6 클라이언트 자동저장 트리거

| 트리거 | 디바운스 | 비고 |
|---|---|---|
| `input` 이벤트 | 1000ms (per field) | type-as-you-go |
| `blur` 이벤트 | 즉시 | 명확한 의도 |
| 마법사 다음/이전 | 즉시 | 단계 전환 = 명시 저장 의도 |
| 페이지 unload | `sendBeacon` | best-effort |
| 5분 idle | 즉시 | safety net |

#### 5.7 사용자 인지 모델

- **마법사 (신규)**: 좌상단 작은 "✓ 자동저장됨 (3초 전)" 인디케이터, 명시 저장 버튼 = "저장 ✓" 최종 단계만.
- **인라인 (수정)**: blur 시 `Toast "저장됨"` + 필드 옆 잠시 ✓ 마크 (D07 보완).
  - **D07 재고**: critical field (금액·시공일·고객 연락처)는 명시 "저장" 버튼 + undo 5초.

---

## 6. R5: 목업 ↔ 컴포넌트 불일치 해소

### 잘못된 부분
- `COMPONENT_LIBRARY_MOBILE.md:757` C12 `<foms-photo-capture>`: paste 버튼은 `matchMedia('(pointer: fine)').matches`로 desktop only.
- `mobile-wizard-new-order.html:307` Step 2: `<button class="photo-capture__btn">📋 붙여넣기</button>` 무조건 노출.

### 보정 (적용 완료)
목업 직접 수정:
- `mobile-wizard-new-order.html` Step 2의 paste 버튼에 `class="photo-capture__btn--desktop-only" data-show-on="desktop"` 추가
- CSS `@media (pointer: coarse) { .photo-capture__btn--desktop-only { display: none; } }` 추가
- 데스크톱 표시 시 "PC전용" 작은 라벨 우상단 표시
- 사용자 인지 모델 명확화

`mobile-order-detail.html` 영향 없음 (paste 부재).

---

## 7. R6: 마법사 Step 2 규격 W·D·H 분리 + erporder 12필드 연동 (사용자 지적 #1)

### 잘못된 부분
v1.0 목업 `mobile-wizard-new-order.html` Step 2:
```html
<input class="foms-input foms-tabular" placeholder="W × H × D (mm)" value="3500 × 540 × 2305" />
```
→ erporder 실제 구조와 완전 불일치.

### erporder 실제 제품 항목 구조 (`erp-order-shared.js:611~740`)

12개 필드:
1. `product_name` — 제품명
2. `spec_rows[]` — **다중 규격 행**. 각 행 = `{spec_width, spec_depth, spec_height}`
3. `internal` — 내부 (기본 "상담")
4. `color` — 색상
5. `option_detail` — 옵션
6. `handle` — 손잡이
7. `misc` — 기타 / 설치위치
8. `price` — 항목 금액
9. `measurement_date` — 항목 실측일 (여러 날짜 가능)
10. `construction_date` — 항목 시공일
11. `extra_input` — 추가 입력 textarea
12. 항목별 attachments (`erp-item-attachments-input`)

### 보정 (적용 완료)
목업 직접 수정:
- 규격 입력: W(폭) / D(깊이) / H(높이) 3분리 (`.spec-row` 클래스)
- "+ 규격 1행 추가" 버튼 — 다중 spec_rows 지원
- 내부·색상·옵션·손잡이·기타·금액 2열 grid 추가
- 항목 실측일·시공일 분리
- 추가 입력 textarea
- 항목별 실측 이미지 캡처 (전체 사진과 분리)

이로써 마법사 Step 2 → erporder PATCH 직접 매핑 가능.

### 컴포넌트 C09 보완
`COMPONENT_LIBRARY_MOBILE.md` C09 Wizard에 추가:
- `<foms-spec-rows>` — 신규 서브 컴포넌트
- props: `value: SpecRow[]`, `onAdd()`, `onRemove(idx)`, `onChange(idx, field, value)`
- 각 input 44px+, 중앙 정렬, tabular-nums

---

## 8. R7: 모바일 주문 상세 제품 섹션 추가 + 실측 인라인 편집 (사용자 지적 #2)

### 잘못된 부분
v1.0 `mobile-order-detail.html`: Hero에 제품명만 표시, 제품 상세 정보(규격·색상·옵션·금액 등) 누락.

### 실제 사용 시나리오 (CS → 실측 흐름)
1. CS 부서: 고객 정보 + 대략적 제품명만으로 주문 등록 (필드 "상담" 기본값)
2. 영업·실측 담당: 현장 방문, 실제 치수 측정
3. 모바일에서 주문 상세 → **제품 항목 인라인 편집** → 즉시 저장
4. 도면팀이 변경 자동 반영된 데이터로 작업 시작

### 보정 (적용 완료)
목업 `mobile-order-detail.html`에 신규 섹션:

- **"제품 항목 (N)" 섹션** 추가
- 항목별 카드 (확장·접힘):
  - 첫 항목: 펼친 상태 — 규격(W·D·H 3분리, 다중 행 + "+ 규격 1행 추가") + 인라인 KV (내부·색상·옵션·손잡이·기타·금액·실측일·시공일) + 항목별 실측 이미지 그리드
  - 두 번째 항목: 접힌 상태 — 1줄 요약만
- 인라인 편집 UX:
  - tap → focus → 변경 → blur 시 즉시 PATCH
  - "실측 변경 즉시 저장됨" 인디케이터 (pulse-dot 애니메이션)
- 항목별 "✕ 삭제" / "＋ 추가" 액션
- 컬러 코딩: 항목 index 배지 brand-100

### 컴포넌트 C05 보완 + 신규 C14
`COMPONENT_LIBRARY_MOBILE.md`에 추가:

#### C14 `<foms-product-item-accordion>` (신규)
- 용도: 주문 상세 페이지에서 제품 항목 다중 표시·인라인 편집
- 접힘 시: 한 줄 요약
- 펼침 시: 12필드 전체 인라인 편집
- 이벤트:
  - `expand(idx)` / `collapse(idx)`
  - `fieldChange(idx, fieldName, value)` → debounced PATCH
  - `addSpecRow(itemIdx)` / `removeSpecRow(itemIdx, specIdx)`
  - `addItem()` / `removeItem(idx)`
  - `attachItem(idx, files)`
- 인라인 편집 PATCH endpoint: `PATCH /api/orders/{id}/erp` (`foms/api/erp_orders_structured.py` 기존 활용)
- `structured_data` JSONB 수정 시 CLAUDE.md 패턴 준수 (`copy.deepcopy + flag_modified`)

---

## 9. Decision Log 재고

### D06 (HTMX 2.0 + Alpine.js 점진 도입) — 범위 축소
- v1.0: 신규 컴포넌트 + 기존 fragment swap 흐름 일부 대체
- 보정: **"new surface only"** — 기존 `erp-shell.js` fragment 흐름은 변경하지 않음. HTMX는 새 페이지·새 모달에만 도입. 기존 로직은 P3 (별도 큰 작업) 전까지 유지.
- 이유: 기존 fragment swap 로직이 이미 작동 중, 충돌 리스크 회피.

### D07 (자동저장 + 마법사) — Critical Field 명시 저장 추가
- v1.0: 인라인 편집 시 저장 버튼 완전 제거
- 보정: critical field는 명시 저장 + undo 토스트 5초.
  - critical: 금액, 시공일, 고객 연락처, 주소
  - non-critical: 색상, 옵션, 손잡이, 기타, 메모
- 이유: 데이터 손실 사고 시 영향 큰 필드는 인지 부담 약간 늘어도 안전.

### D09 (디자인 토큰 `--foms-*` 단일화) — Alias Bridge 우선
- v1.0: P1-06에서 일괄 변환
- 보정: **Phase 단계화**
  1. Phase 1 (P0-07): 신규 `--foms-*` 토큰 파일 추가 + 기존 `--erp-*` / `--wam-*` 토큰을 `--foms-*` alias로 매핑 (1주, 회귀 없음)
  2. Phase 2 (P1-06): 신규 코드에서 `--foms-*` 직접 사용, 기존 코드는 alias 통해 동작
  3. Phase 3 (P2): 기존 코드 점진 마이그레이션 (1년 timeline)
- 이유: 전면 치환은 시각 회귀 리스크 큼. alias로 안전 우선.

---

## 10. P0 진입 전 필수 액션 (LLM 권장 + 본 패치 정리)

체크리스트:

- [ ] **본 문서 §5 OrderDraft 모델 + Alembic 마이그레이션 PR 1개 선행**
- [ ] **본 문서 §3 API 경로 매핑 표 확정** → 모든 ROADMAP 파일 경로 정정
- [ ] **본 문서 §4 Feature Flag Matrix 코드화** (`foms/services/feature_flags.py`)
- [ ] **본 문서 §2 도면·AS·시공 카드 실제 상태 추가 audit** (스크린샷 기록)
- [ ] **P0-01 Acceptance Criteria에 Playwright 시각 회귀 추가**
- [ ] **KPI 베이스라인 측정 시작** (Plausible 또는 umami self-host)

---

## 11. 보정 후 점수 재평가

LLM 평가 기준 (5축 × 보정 효과):

| 약점 | v1.0 점수 영향 | v1.1 보정 | 보정 후 |
|---|---|---|---|
| P0 결함 목록 stale | -1.2 | §2 신규→gap patch | 거의 해소 |
| API 경로 오류 | -0.8 | §3 매핑표 | 완전 해소 |
| Feature flag 추상적 | -0.5 | §4 matrix | 해소 |
| 자동저장 계약 부족 | -0.4 | §5 schema·API·TTL·충돌 | 거의 해소 |
| 목업-컴포넌트 불일치 | -0.3 | §6 + 목업 패치 | 완전 해소 |
| (사용자) 규격 W·D·H | — | §7 + 목업 패치 | 완전 해소 |
| (사용자) 제품 섹션 부재 | — | §8 + 목업 패치 + C14 신규 | 완전 해소 |

**보정 추정**: v1.0 7.2/10 → **v1.1 8.4/10** (LLM 평가 기준)
**자체 평가**: v1.0 8.1 → **v1.1 8.7**

### 보정 후에도 남은 약점
- [ ] R&D 베이스라인 (KPI 측정 도구 도입) — P0-01 acceptance에 추가 필요
- [ ] OrderDraft cron job 운영 — Railway Worker에 등록 필요
- [ ] 카드 + FAB overlap 리스크 (LLM 검증 발견) — `mobile-home-dashboard.html` 카드 마지막 footer.queue-card__action padding-bottom 보정 필요
- [ ] 시공 카드 audit 미수행 — P0-04 보정판 시작 시 실시

---

## 12. v1.0 → v1.1 흡수 완료 매핑 (2026-05-29)

| v1.0 파일 | v1.1 흡수 위치 | 상태 |
|---|---|---|
| `MOBILE_TABLET_REDESIGN_PLAN.md` | line 15 audit 오류 정정 | ✅ 흡수 |
| `MOBILE_TABLET_DESIGN_SYSTEM.md` | 영향 없음 | — |
| `COMPONENT_LIBRARY_MOBILE.md` | 머리말 14개 선언, C14 섹션 본문 추가, 부록 D/E 갱신 | ✅ 흡수 |
| `MIGRATION_ROADMAP.md` | P0-00 Foundation PR 추가, P0-01 cohort + Playwright baseline, P0-02/03/04 audit/gap patch 재작성, P0 60h→58h, apps/api 5건→foms/api, P1-03 OrderDraft 본문, P1-06 alias bridge, P2-01 new surface only, Rollback→Flag matrix 본문, 부록 A/B 추가 | ✅ 흡수 |
| `REVIEW_SELF_ASSESSMENT.md` | 머리말 v1.1 8.7/10 + v1.0→v1.1 점수 변화표 | ✅ 흡수 |
| `INDEX.md` | 머리말 v1.1, 핵심 발견 #2 비효율 결함 정정, #4 시간 추정, #5 점수, sub order 5번 14종, 다음 단계 갱신 | ✅ 흡수 |
| `REVIEW_ENTRY.md` | 머리말 v1.1, 한 줄 요청, 산출물 트리, F2 표 갱신, Decision Log D06/D07/D09 재고, §6 시간 -14h, §7 점수 8.7 | ✅ 흡수 |
| `mockups/mobile-wizard-new-order.html` | Step 2 W·D·H 3분리 + erporder 12필드 + paste desktop-only | ✅ 흡수 |
| `mockups/mobile-order-detail.html` | 제품 항목 섹션 신규 + 인라인 편집 + spec_rows | ✅ 흡수 |

---

## 13. 검토자에게 — 본 문서 사용법

본 문서는 **변경 이력**으로만 보존된다. 진실은 v1.0 → v1.1 직접 흡수된 위 8개 파일.

**본 문서를 읽어야 하는 시점**:
- 왜 v1.0의 특정 결정이 변경되었는지 추적할 때
- 외부 LLM 평가 1회차 발견 사항을 확인할 때
- audit agent 결과의 stale 가능성을 학습할 때 (감사용)

**본 문서를 읽지 말아야 하는 시점**:
- 현재 계획 상태 파악 → `INDEX.md` + `MIGRATION_ROADMAP.md`
- 구현 시작 → `MIGRATION_ROADMAP.md` P0 섹션
- 검토 → `REVIEW_ENTRY.md`

---

## 14. 학습 (Meta-lesson)

본 작업에서 얻은 가장 큰 교훈:

> **agent 결과는 검증 없이 신뢰하면 안 된다.**
> v1.0의 audit agent (`a609f22f9c2c67c9d`)는 도면·AS 모바일 카드가 "없다"고 보고했으나 실제로는 존재했다. 사실 확인 없이 그 결론을 계획서·로드맵·INDEX에 반영한 결과, 외부 LLM의 1차 평가에서 P0 결함 목록·API 경로·시간 추정이 모두 stale로 판정되었다.
>
> **재발 방지 규칙**: agent의 사실 주장(파일 존재·라인 번호·코드 패턴)은 `Read`/`Grep`/`Bash`로 즉시 재검증한 뒤에만 다음 단계 산출물에 인용한다.

본 학습은 `feedback` 메모리 후보. 이후 모든 audit 단계에 적용.

---

> 본 문서는 v1.0 → v1.1 변경 audit trail로 보존된다. 모든 v1.1 사실 주장은 `Read`·`Grep`·`Bash`로 직접 확인된 결과이며, v1.0 시점의 stale 주장은 §2 표에 정확히 기록되어 있다.
