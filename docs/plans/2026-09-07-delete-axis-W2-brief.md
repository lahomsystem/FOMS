# W2 — `deleted_at` 저장 규약 한 벌 (쓰기)

계약 원문: `docs/plans/2026-09-07-delete-axis-unify-brief.md`
작업 트리: `c:\tmp\foms-s-s0907-202822` — 모든 명령을 `cd /c/tmp/foms-s-s0907-202822 && pwd && ...` 로 시작.
git 명령 금지. CRLF 보존(대상 파일 전부 CRLF). 파일 전체 재작성 금지.

## CEO 확정 사항

1. **정본 규약 = naive UTC 고정폭 문자열 `%Y-%m-%d %H:%M:%S`** (`soft_delete.py:48·78`).
   읽는 쪽(`format_datetime_kst(..., assume_utc_if_naive=True)`)이 이미 그걸 전제한다.
   **읽는 쪽에 보정을 넣지 않는다** — 넣는 순간 규약이 네 갈래가 된다.
2. **고쳐야 할 자리는 3곳이다.** 브리프의 2곳 + CEO 전수 조사에서 하나 더 나왔다:

| 자리 | 지금 값 | 결과 | 바꿀 값 |
| --- | --- | --- | --- |
| `foms/web/orders/listing.py:583` (페이지 일괄 삭제) | `now_kst().strftime('%Y-%m-%d %H:%M:%S')` | 화면에 **9시간 앞선 시각** | `now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')` |
| `foms/api/erp_orders_structured.py:2378` (드래프트 폐기) | `datetime.datetime.now().isoformat()` | `T` 형식 + 컨테이너 로컬 | 같은 정본 형식 |
| `tools/cron/cleanup_order_drafts.py:154·158` (48시간 지난 draft 정리) | `now.isoformat()` | `T` 형식 + 컨테이너 로컬 | 같은 정본 형식 |

   운영 휴지통 308건 중 ISO `T` 28건은 **위 두 ISO 경로가 함께 만든 것**이다(둘 다
   `original_status` 를 세우고 `structured_data['delete']` 를 안 남긴다). W3 의 백필 마커가
   이 사실에 기댄다.
3. **전수 조사 결과 — 이 밖에는 없다.** 값을 쓰는 자리 전부(`grep -rn "deleted_at.*=" --include=*.py`):
   - `foms/services/orders/soft_delete.py:78` — 정본(그대로 둔다)
   - `foms/web/orders/trash.py:318` — 복원(`None` clear, 형식 무관)
   - `foms/api/files/order_routes.py:620·689` — **다른 축**(`OrderAttachment.deleted_at`, DateTime 컬럼)
   - `foms/api/cs/as_orders.py:1338` · `foms/services/orders/as_upload_anchor.py:152` — **다른 축**
     (`structured_data.shipment.as_log[].deleted_at`, 이미 `now_utc_naive().isoformat()`)
   → 위 3곳만 고친다. 다른 축 4곳은 **건드리지 않는다**.
4. `listing.py` 의 legacy `status='DELETED'` + `original_status` 미러 쓰기 자체는 **이번 범위가 아니다**
   (DELETE-BULK-01 별건). `soft_delete_order` 로 갈아타지 않는다.

## 편집 허용 파일 (이 밖은 읽기만)
- `foms/web/orders/listing.py`
- `foms/api/erp_orders_structured.py`
- `tools/cron/cleanup_order_drafts.py`
- `tests/domains/test_deleted_at_write_convention.py` (신규)

## 해야 할 변경 (앵커별)

### A. `foms/web/orders/listing.py:583`
- `now_utc_naive` 는 이미 import 되어 있다(33행). `now_kst` 는 이 파일의 다른 자리
  (392·430·498행)에서 계속 쓰이므로 import 를 지우지 않는다.
- 한글 주석으로 **왜**를 남긴다: 이 컬럼은 naive UTC 규약이고, KST 를 넣으면 읽는 쪽이 다시 +9 해서
  화면이 9시간 미래를 말한다.

### B. `foms/api/erp_orders_structured.py:2378`
- 45행 import 를 `from foms.services.datetime_kst import now_kst, now_utc_naive` 로 넓힌다
  (`now_kst` 가 이 파일에서 계속 쓰이는지 확인하고, 안 쓰이면 빼지 말고 그대로 둔다 — 범위 밖).
- `order.deleted_at = now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')`.

### C. `tools/cron/cleanup_order_drafts.py`
- **`now`/`threshold` 는 건드리지 않는다.** 그 둘은 `structured_updated_at`/`created_at` 과 견주는
  값이고 `Order.created_at` 기본값이 `datetime.datetime.now`(models.py:36 — 컨테이너 로컬)라
  기준축이 다르다. 여기서 UTC 로 바꾸면 선별 조건이 조용히 어긋난다.
- `deleted_at` 스탬프만 따로 만든다: `deleted_stamp = now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')`,
  SQL 파라미터 이름도 `:now_iso` → `:deleted_stamp` 로 바꿔 뜻을 맞춘다(154·158행).
- import 는 `from foms.services.datetime_kst import now_utc_naive` — 이 모듈은 `pytz` 만 물어
  Flask app 을 끌어오지 않는다(파일 머리의 "app 을 import 하지 않는다" 규율 유지).

### D. 신규 테스트 `tests/domains/test_deleted_at_write_convention.py`
문서를 읽지 않는다(CI-DOCSCOPE 대상 아님). 인벤토리 게이트는 **줄 번호를 박지 않는다**.
1. **전수 인벤토리 게이트(회귀 차단의 본체)**: 프로덕션 소스(`foms/`, `tools/`)에서 주문
   `deleted_at` 에 **문자열 값을 쓰는** 자리를 정규식으로 모아, 파일 집합이 정확히
   {`foms/services/orders/soft_delete.py`, `foms/web/orders/listing.py`,
   `foms/api/erp_orders_structured.py`, `tools/cron/cleanup_order_drafts.py`} 인지 확인한다.
   음성 대조군: 그 4개 파일의 `deleted_at` 쓰기 줄에 `now_kst(`·`datetime.now(`·`.isoformat()` 가
   **하나도 없다**. (`OrderAttachment`/`as_log` 축은 정규식에서 제외한다 — 제외 근거를 주석으로 적는다.)
2. **동작 계약**: `bulk_action` 삭제 → `deleted_at` 이 `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$` 이고
   `now_utc_naive()` 와 5분 이내, `now_kst()` 와는 약 9시간 차.
3. **드래프트 폐기** route → `T` 가 없고 같은 정규식 통과.
4. **cron** `run_cleanup(..., execute=True)`(SQLite `db_session`) → 같은 정규식 통과.
5. **읽기 왕복(사용자 증상 회귀 차단)**: 위 세 경로가 쓴 값을
   `format_datetime_kst(value, '%m-%d %H:%M')` 로 읽으면 `now_kst()` 의 같은 형식과 일치한다
   (지금은 일괄 삭제만 9시간 미래로 어긋난다).

## 하지 말 것
- 읽는 쪽(`format_datetime_kst` 호출부·`_parse_deleted_at`)에 보정 추가.
- `status`/`original_status` 미러 쓰기 변경, `soft_delete_order` 로 경로 교체.
- `OrderAttachment.deleted_at` · `as_log[].deleted_at` 손대기.
- `cleanup_order_drafts` 의 `now`/`threshold` 를 UTC 로 바꾸기.
- 기존 테스트 기대값 수정 — 깨지면 보고한다
  (`tests/domains/test_delete_bulk.py`, `tests/domains/test_cleanup_order_drafts.py`).

## 완료 기준 (돌릴 명령)
```
cd /c/tmp/foms-s-s0907-202822 && pwd
python -m pytest tests/domains -q
python -m pytest tests/domains/test_delete_bulk.py tests/domains/test_delete_trash.py tests/domains/test_cleanup_order_drafts.py -q
python -c "import app; print('APP_OK')"
```
보고에 반드시 적을 것: 고친 자리 3곳 목록, 전수 조사에서 **제외**한 자리와 그 이유,
`cleanup_order_drafts` 의 `now` 를 왜 안 건드렸는지.
