# SFC-B2 — Root constants/config family freeze

> Batch: `SFC-B2`  
> 실행일: 2026-04-15  
> 성격: **docs-only** (실행 계획 `§5` Catalog, `§6.3`)  
> 선행: `SFC-B0`, `SFC-B1`  
> 입력: `constants.py` (전체), `rg 'from constants import'` (제품 트리; `backups/` 제외)

## 1. 목표

- 루트 `constants.py`를 **한 번에 rename 이동하지 않고** 심볼 패밀리별로 쪼개 canonical home을 고정한다.
- `SFC-B3`에서 수행할 **authoritative target map**과 **금지 규칙**을 잠근다.

## 2. 금지 (계획 `§6.3`)

1. `constants.py`를 **단일 파일로** 다른 경로에 rename만 하는 것.  
2. consumer reroute 없이 **re-export shim**만 추가하는 것.  
3. 본 배치에서 **런타임 코드·테스트 변경** (B2는 문서 전용).

## 3. Authoritative target map (1:1 심볼 → 파일)

소스: 루트 `constants.py` 현재 정의 전체.

### 3.1 `foms/services/orders/status_constants.py`

| 심볼 | 역할 |
|------|------|
| `STATUS` | 주문/프로세스 단계 라벨 맵 |
| `BULK_ACTION_STATUS` | 일괄 작업용 (`DELETED` 제외) |
| `CABINET_STATUS` | 수납장 상태 매핑 |

**소비자 (B3에서 import 경로 변경):**  
`foms/api/orders/status.py`, `field_update.py`, `calendar.py`, `foms/api/erp_orders_structured.py`, `foms/api/quest.py`, `foms/services/context_processors.py`, `foms/services/channel_event_payloads.py`, `apps/order_pages.py`, `apps/order_edit.py`, `apps/dashboards.py`, `apps/erp_history_page.py`, `apps/storage_dashboard.py`, `apps/erp_dashboard.py` (BULK_ACTION만).

### 3.2 `foms/services/files/upload_policy.py`

| 심볼 | 역할 |
|------|------|
| `ALLOWED_EXTENSIONS` | 엑셀 등 업로드 허용 확장자 |
| `CHAT_ALLOWED_EXTENSIONS` | 채팅 첨부 확장자 |
| `ERP_MEDIA_ALLOWED_EXTENSIONS` | ERP 미디어 확장자 |
| `DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES` | Direct upload Content-Type 화이트리스트 |

**소비자:**  
`foms/services/files/file_utils.py`, `foms/api/chat/utils.py`, `foms/api/chat/routes_files.py`, `foms/api/attachments_internal/common.py`, `order_routes.py`, `direct_upload.py`.

### 3.3 `foms/services/orders/estimate_defaults.py`

| 심볼 | 역할 |
|------|------|
| `ESTIMATE_COMPANY_INFO` | 견적/회사 정보 dict |
| `ESTIMATE_PAYMENT_INFO` | 결제 안내 dict |
| `ESTIMATE_LEGAL_NOTICE` | 법적 고지 문자열 |
| `ESTIMATE_STATUS` | 견적 상태 맵 (**현재 다른 모듈에서 import되지 않음** — 동일 파일로 이전 후 정적 검색으로 확인) |
| `ERP_DRAFT_PLACEHOLDER_CUSTOMER` | ERP Beta placeholder |
| `ERP_DRAFT_PLACEHOLDER_PHONE` | 동일 |
| `ERP_DRAFT_PLACEHOLDER_PRODUCT` | 동일 |

**소비자:**  
`foms/services/estimate_service.py`, `foms/api/erp_estimates.py`, `foms/api/erp_orders_structured.py`, `apps/order_pages.py`.

### 3.4 `foms/services/files/storage_paths.py`

| 심볼 | 역할 |
|------|------|
| `UPLOAD_FOLDER` | 런타임 업로드 루트 상대 경로 (`static/uploads`) |

**소비자:**  
`foms/platform/app_factory.py`, `apps/excel_import.py`.

## 4. 패밀리 간 의존성

- 네 모듈은 **서로 import하지 않는다** (순수 데이터/상수).  
- 기존 `constants.py`는 단일 파일에 모든 심볼이 공존했으므로, 분리 후에도 **순환 의존 없음** 유지.

## 5. `SFC-B3` 수행 순서 (이 배치에서 규칙만 고정)

1. 위 네 파일 **신규 생성** (본문은 `constants.py`에서 이동·복사, 동일 값).  
2. **모든 소비자** `import`를 canonical 경로로 교체 (`foms` + `apps`).  
3. 루트 `constants.py` **삭제**.  
4. 검증: `rg 'from constants import|import constants' foms apps --glob '*.py'` → 0 ( `backups/` 제외).  
5. `python -c "import app; print('APP_OK')"`, `verify_result.py --json`, 관련 pytest.

## 6. SG* (본 배치)

- B2는 코드 미변경 → **SG* 수치 변화 없음** (B1 baseline 유지).

## 7. 검증

- Docs-only → 컴파일 검증 불필수. (선택: 워크스페이스 `APP_OK` 유지 확인.)

## 8. 다음 legal batch

- **`SFC-B3`** — Root constants retirement (코드).

## 9. GDM 감리 Round 1

| 계획 `§6.3` | 충족 |
|-------------|------|
| 패밀리 분해 (rename-only 금지) | 예 — 4파일 맵 |
| shim-only 금지 | 예 — B3에서 reroute 후 root 삭제 |
| authoritative target 경로 | 예 — `foms/services/orders/`, `foms/services/files/` |

**판정:** **합격** — Round 2는 `SFC-B3` 구현·diff에 대해 substantive만.
