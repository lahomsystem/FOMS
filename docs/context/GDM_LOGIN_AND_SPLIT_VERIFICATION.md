# GDM 검증: 로그인 로직·codex5.3 수정·app/api 분리

> **검증일**: 2026-02-18  
> **디버그 코드**: 삭제 완료 (debug-redirect 라우트, REDIRECT_LOOP_ANALYSIS.md)

---

## 1. 현재 로그인 로직 (codex5.3 반영)

### 1.1 인증 흐름

```
[비로그인] GET / → login_required → redirect /login?next=/
[비로그인] GET /login → render login form (next_url 유지)
[비로그인] POST /login → 검증 → session 설정 → redirect next_url
[로그인] GET /login → user 유효 시 → redirect /
[로그인] GET / → login_required 통과 → index 렌더
```

### 1.2 codex5.3 변경 사항 (apps/auth.py)

| 항목 | 이전 | 이후 |
|------|------|------|
| **next 파라미터** | `request.url` (절대 URL, https 포함 가능) | `_build_next_param()` (상대 경로만) |
| **next 검증** | 없음 | `_normalize_next_url()` (//, 외부 URL 차단) |
| **login_required** | user_id 존재만 확인 | user_id + get_user_by_id 유효성 + is_active 확인 |
| **login 진입** | session에 user_id 있으면 무조건 redirect | user_id + DB 유효성 + is_active 확인 후 redirect |
| **에러 시** | - | session.clear() 후 재로그인 유도 |

### 1.3 수정된 코드 요약

- **`_build_next_param()`**: `request.path` + query만 사용 (절대 URL 사용 금지) → 리다이렉트 루프 방지
- **`_normalize_next_url()`**: `//`, 비상대 경로 차단 → open redirect 방지
- **login_required**: user 삭제/비활성화 시 `session.clear()` 후 /login 리다이렉트
- **login**: 기존 세션 무효 시 `session.clear()` 후 폼 렌더

### 1.4 templates/login.html

- `<input type="hidden" name="next" value="{{ next_url or '' }}">` 추가 → POST 시 next 유지

---

## 2. codex5.3이 수정한 파일

| 파일 | 변경 |
|------|------|
| **apps/auth.py** | _build_next_param, _normalize_next_url, login_required/role_required·login 강화 |
| **apps/order_pages.py** | index 예외 시 session.clear() 추가 (루프 방지) |
| **templates/login.html** | hidden next 필드 추가 |
| **app.py** | ProxyFix 조건부 적용 (본 세션), debug-redirect 삭제 (GDM) |

---

## 3. app.py ↔ apps/api 분리 검증

### 3.1 Blueprint 등록

- **총 163개 라우트** (API 111개)
- **apps/api/ Blueprint** 20개 등록:
  - files, address, orders, notifications, erp_shipment_settings, erp_measurement
  - erp_map, erp_orders_quick, erp_orders_drawing, erp_orders_revision
  - erp_orders_draftsman, erp_orders_production, erp_orders_construction
  - erp_orders_cs, erp_orders_as, erp_orders_confirm
  - chat, wdcalculator, backup, attachments, tasks, events, quest
  - erp_orders_blueprint, erp_orders_structured

### 3.2 핵심 라우트 확인

| 경로 | 엔드포인트 | 상태 |
|------|------------|------|
| / | order_pages.index | ✅ |
| /login | auth.login | ✅ |
| /api/orders | orders.api_orders | ✅ |
| /upload | excel.upload_excel | ✅ |
| /map_view | erp_map.map_view | ✅ |
| /calendar | calendar.calendar | ✅ |

### 3.3 결론

- app.py와 apps/api 분리 구조 정상 동작
- Blueprint 등록 및 라우트 매핑 일관됨

---

## 4. role_required 미반영 사항

`role_required`는 여전히 `request.url`을 사용함:

```python
return redirect(url_for('auth.login', next=request.url))  # ← request.url
```

- `login_required`는 `_build_next_param()`으로 변경됨
- `role_required`도 `_build_next_param()`로 통일 권장 (선택)
