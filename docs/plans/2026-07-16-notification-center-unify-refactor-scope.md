# 알림센터 단일화 — PC/모바일/태블릿 리팩터 범위
> 작성일: 2026-07-16 | 상태: 🟢 Phase 0–2 구현 중 (게이트 확정)  
> 목표: 디바이스별 **진입 크롬만** 남기고, 목록·쓰기·urgent pin·push CTA를 **하나의 JS/마크업 계약**으로 통합
>
> **게이트 확정 (2026-07-16 순차 진행):**
> 1. PC UX = **동일 offcanvas 시트** (dropdown 폐기, 기능 패리티)
> 2. ack/archive **필수 패리티**
> 3. 생산/시공 로컬 벨 → `data-foms-notif-open` 재배선 (레거시 panel 마크업은 후속 삭제)
> 4. Phase 3 urgent 송신 통일 = **후속** (이번 묶음 제외). Push CTA는 시트 footer로 PC 포함.

---

## 1. 현재 분기 (As-Is)

```
                    ┌─────────────────────────────────────┐
                    │  API SSOT (이미 단일)                 │
                    │  /notifications · badge · read/ack  │
                    │  FOMSNotificationBadge · Write      │
                    └──────────────┬──────────────────────┘
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
     Mobile sheet            Tablet rail              PC dropdown
     mobile-notification.js  (hooks only)             layout_scripts inline
     + push CTA              → same sheet             + prod/const page panels
     + urgent sheet                                   urgent = inline form
```

| 표면 | 진입 | 패널 UI | 쓰기(read/ack/archive) | Push CTA | Urgent 송신 |
|------|------|---------|------------------------|----------|-------------|
| Mobile | 셸 헤더 벨 | Offcanvas sheet | ✅ mobile-notification.js | ✅ | sheet |
| Tablet | 레일 벨 (+헤더) | **동일 sheet** | reuse | sheet 열면 동일 | sheet |
| PC global | topnav 벨 | dropdown `#global-notification-*` | read만(인라인). ack/archive-all 약함 | ❌ | — |
| PC page | 생산/시공 `notification-btn` | 별도 panel | 페이지 스크립트 복제 | ❌ | — |
| PC urgent | 주문 상세 | — | — | — | inline `d-lg-flex` |

**이미 단일:** API, badge poll, write header, tablet→mobile sheet 훅.  
**이중화 핵심:** PC dropdown(+페이지 패널) vs mobile sheet 로직·기능 격차.

---

## 2. 목표 (To-Be)

**단일 Notification Center 모듈** (`static/js/foms/notification-center.js` 가칭):

- 열기 트리거: `[data-foms-notif-open]` (모바일 헤더·태블릿 레일·**PC 벨**)
- 패널 호스트: 하나의 마크업(반응형)
  - `<lg`: Offcanvas bottom sheet (현행)
  - `≥lg`: dropdown 또는 end-sheet (현행 global panel 슬롯에 동일 리스트 렌더)
- 기능 패리티: list · urgent pin · read · read-all · archive · archive-all · ack · deep_link
- Push CTA: sheet/panel footer — **PC에도 표시**(지원 브라우저+flag). tablet은 자연 포함
- Badge: 계속 `FOMSNotificationBadge`만 구독 (추가 fetch 금지)

Urgent **송신** UI는 센터 밖(주문/워크벤치 컨텍스트) — 이번 범위는 **수신 센터** 통합. 송신은 Phase 후속으로 `d-lg-*` 분기만 정리 가능.

---

## 3. 페이즈 · 파일 범위

### Phase 0 — 계약 고정 (반나절, 코드 최소)

- [ ] 기능 매트릭스 테스트 확장: PC global도 ack/archive 가능해야 함(또는 “의도적 제외”를 SPEC에 명시)
- [ ] `tests/visual/test_mobile_notification_center.py` 형제: desktop trigger + 동일 `data-*` 계약
- [ ] deep_link SSOT: PC `readGlobalNotification` vs mobile `deepHref` 불일치 목록화

**예상 불일치(수정 후보):**

| 항목 | Mobile | PC global |
|------|--------|-----------|
| limit | 30 | 10 |
| ack 버튼 | urgent pin | 없음 |
| archive | 항목/일괄 | 없음 |
| deep_link | `deep_link_url` / `/edit/...` | type별 workbench / edit |
| read-all | ✅ | ❌(배지만) |

### Phase 1 — JS SSOT 추출 (핵심, 1–2일)

| 파일 | 작업 |
|------|------|
| `static/js/foms/notification-center.js` | **신규** — list render, open/close, write actions, badge subscribe. `__FOMS_NOTIF_CENTER_BOUND` |
| `static/js/foms/mobile-notification.js` | thin re-export 또는 삭제 후 shell이 center 로드 |
| `templates/partials/shared/layout_scripts.html` | `loadGlobalNotifications` / `readGlobalNotification` / toggle **제거** → center API 호출 |
| `templates/partials/shared/layout_nav.html` | 벨에 `data-foms-notif-open` 부여, panel에 center 호스트 id/data 속성 |
| `templates/partials/shared/erp_mobile_notification_panel.html` | 공용 partial로 승격(이름 `notification_center_panel.html`) 또는 PC도 동일 include |
| `templates/partials/shared/foms_app_shell.html` | script 태그 center로 교체 |
| `static/js/foms/mobile-push.js` | CTA 셀렉터 공용 유지(`[data-foms-push-cta]`). PC 패널에 CTA 호스트 추가 |

**금지:** 인라인 스타일 신규, 동기 script, CDN. defer 유지. G4 singleton 가드 유지.

### Phase 2 — PC 페이지 패널 퇴역 (반나절–1일)

| 파일 | 작업 |
|------|------|
| `templates/production/partials/dashboard_body.html` | 로컬 `notification-btn` 제거 또는 global만 사용 |
| `templates/production/partials/scripts.html` | 중복 notification handlers 삭제 |
| `templates/construction/partials/...` | 동일 |
| `templates/orders/partials/dashboard_main.html` | 잔존 panel 정리 |
| `static/js/orders/dashboard-notifications.js` | 삭제 또는 badge-only stub → center 위임 |
| `static/css/.../dashboard-gateway-notifications.css` | 미사용 규칙 정리(시각 회귀 주의) |

### Phase 3 — Push CTA · Urgent 송신 정리 (선택)

- PC 패널 footer에 push CTA (mobile-push.js 그대로)
- 주문 상세 urgent: inline vs sheet를 단일 opener(`[data-foms-urgent-call]`)로 통일 — **센터 통합과 분리 가능**

### Out of Scope (이번 리팩터 제외)

- API/스키마 변경
- Chat toast (`showGlobalChatNotification`) — 채널 유지
- Admin `notifications_send.html` 발송 UI
- Escalation push 갭 → 별도 Spec `2026-07-16-notification-escalation-push-realtime_SPEC.md`
- production 승격

---

## 4. 리스크 · 가드

| 리스크 | 완화 |
|--------|------|
| layout_scripts 인라인 거대 블록 삭제 시 PC 회귀 | Phase 0 계약 테스트 + gstack browse PC 1280 스모크 |
| fragment swap 이중 바인딩 | `__FOMS_NOTIF_CENTER_BOUND` + document 위임만 |
| 태블릿 레일 배지 정지 재발 | `querySelectorAll('[data-foms-notif-badge]')` 유지 |
| 생산/시공 페이지 벨 제거 후 발견성 | global nav 벨만 남김 — T7 태블릿 크롬과 충돌 없는지 확인 |
| deep_link PC/모바일 불일치 | center에서 API `deep_link_url` 우선, 없으면 type 맵(현 PC 로직) |

perf: 신규 sync CDN script 금지. center 1파일 defer. badge 폴 중복 fetch 금지.

---

## 5. 검증 계획

- [ ] `APP_OK`
- [ ] `pytest tests/visual/test_mobile_notification_center.py` + 신규 desktop 계약
- [ ] `tests/domains/test_notification_ownership.py` 등 API 회귀
- [ ] gstack/browse: mobile 390 — 벨→시트→ack→archive→badge
- [ ] browse: desktop 1280 — 벨→패널→동일 쓰기→deep_link workbench
- [ ] tablet coarse landscape — 레일 벨→동일 시트, 배지 동기
- [ ] `python tools/perf/perf_scan.py --guard` · `pre_push_smoke.ps1`

---

## 6. 공수 추정

| Phase | 공수 | 의존 |
|-------|------|------|
| 0 계약 | 0.5d | — |
| 1 JS SSOT | 1–2d | Phase 0 |
| 2 페이지 패널 퇴역 | 0.5–1d | Phase 1 |
| 3 Push/Urgent 정리 | 0.5d | Phase 1 |
| **합** | **~2.5–4d** | 승인 후 |

---

## 7. 승인 게이트

구현 들어가기 전 확정:

1. PC 패널 UX: **dropdown 유지** vs **desktop도 offcanvas end**?
2. PC에 ack/archive **필수 패리티** vs read-only 유지(비권장)?
3. 생산/시공 로컬 벨 **삭제** OK?
4. Phase 3(urgent 송신 통일) 이번 묶음 포함 여부?

상태: 📋 범위만 고정. 코딩은 위 게이트 승인 후.

형제 문서: Spec A `2026-07-16-notification-escalation-push-realtime_SPEC.md` · E2E `2026-07-16-notification-e2e-sequences.md`
