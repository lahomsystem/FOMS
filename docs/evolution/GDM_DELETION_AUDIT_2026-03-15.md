# GDM 삭제 파일 1:1 소스코드 안정성 감리

> 2026-03-15 | 삭제된 6개 파일에 대한 검증 결과

## 요약

| # | 파일 | 판정 | 근거 |
|---|------|------|------|
| 1 | `docs/context/HOOK_RAW_DUMP.txt` | ✅ 안전 | Hook 디버그 덤프, 런타임/빌드 미참조 |
| 2 | `docs/context/.hook_raw_once` | ✅ 안전 | Hook 1회 마커, 런타임/빌드 미참조 |
| 3 | `templates/partials/_erp_amount_block.html` | ✅ 안전 | 어디에서도 `{% include %}` 없음 |
| 4 | `templates/partials/chat_scripts.html` | ✅ 안전 | `chat_scripts_bundle.html`만 사용, chat.html은 route 사용 |
| 5 | `r2_storage.py` | ✅ 안전 | import 0건, `services/storage.py`에 R2 로직 통합 |
| 6 | `check_orders.py` | ✅ 안전 | import 0건, 임시 스크립트, Staging DB URL 하드코딩(보안 위험) |

**결론: 6건 모두 불필요 파일로 판정. 복원 불필요.**

---

## 1. `_erp_amount_block.html` 상세 검증

### 삭제된 내용 (원본)
```html
{# ERP 금액 블록 공용 partial - total_formatted, deposit_formatted, remaining_formatted 전달 #}
<div class="... erp-amount-block">
  <div>출고가 {{ total_formatted }}</div>
  <div>예약금 {{ deposit_formatted }}</div>
  <div>잔금 {{ remaining_formatted }}</div>
</div>
```

### 검색 결과
- `{% include 'partials/_erp_amount_block.html' %}` → **0건**
- `include.*erp_amount` / `include.*amount_block` → **0건**

### 기존 템플릿의 금액 블록
- `erp_beta_tab.html`, `erp_drawing_workbench_detail.html`, `erp_measurement_dashboard.html`, `erp_dashboard_scripts_detail_dom.html` → 각각 **인라인 마크업** 사용 (`erp-amount-block` 클래스만 공유)
- Jinja 변수(`total_formatted` 등) 대신 JS로 `#erp-items-total`, `#erp-deposit-amount` 등 업데이트

**판정**: partial은 미사용. 인라인 구현이 실제 사용 경로.

---

## 2. `chat_scripts.html` 상세 검증

### 삭제된 내용 (원본)
```html
<script>
{% include 'partials/chat_scripts_core.html' %}
... (11개 partial)
</script>
```

### 실제 사용 경로
- `chat.html` L235: `<script src="{{ url_for('chat.chat_scripts_js') }}"></script>`
- `apps/api/chat/routes.py` L951: `render_template('partials/chat_scripts_bundle.html', ...)`

### 비교
| 항목 | chat_scripts.html (삭제) | chat_scripts_bundle.html (사용 중) |
|------|--------------------------|-------------------------------------|
| 래퍼 | `<script>` | 없음 (route가 JS로 응답) |
| include 목록 | 동일 11개 | 동일 11개 |
| 참조 | 0건 | chat.chat_scripts_js route |

**판정**: `chat_scripts_bundle.html`이 실제 사용. `chat_scripts.html`은 레거시로 미참조.

---

## 3. `r2_storage.py` 상세 검증

### 삭제된 내용 (원본)
- `get_r2_client()`, `upload_file_to_r2()`, `generate_presigned_url()` 등 boto3 기반 R2 함수

### `services/storage.py`와 비교
| 기능 | r2_storage.py | services/storage.py |
|------|---------------|----------------------|
| R2/S3 클라이언트 | ✅ | ✅ StorageAdapter |
| 업로드 | upload_file_to_r2 | _upload_to_cloud |
| Presigned URL | generate_presigned_url | get_download_url, generate_presigned_put_url |
| 로컬 폴백 | 없음 | ✅ |
| 채팅/썸네일 | 없음 | ✅ |

### import 검색
- `r2_storage` / `from r2_storage` → **0건**

**판정**: `services/storage.py`에 R2 로직 통합 완료. `r2_storage.py`는 미사용.

---

## 4. `check_orders.py` 상세 검증

### 삭제된 내용 (원본)
```python
STAGING_URL = 'postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@...'
conn_stg = psycopg2.connect(STAGING_URL)
# Staging DB 조회 스크립트
```

### 검색 결과
- `check_orders` import/참조 → **0건**

**판정**: 일회성 스크립트, DB URL 하드코딩으로 보안 위험. 삭제 적절.

---

## 5. Hook 디버그 파일

- `HOOK_RAW_DUMP.txt`, `.hook_raw_once` → Cursor hook 디버그용
- 앱/빌드/테스트에서 참조 없음
- `.gitignore`에 추가 완료

---

## Residual Risk

없음. 6건 모두 삭제 유지 권장.
