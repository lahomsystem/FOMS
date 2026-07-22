# 도면팀 ERP주문 변경 알림 Spec
> 작성일: 2026-07-15 | 상태: 🟢 승인됨 (게이트=목록 표기 포함 · debounce 설명·유지 · deploy 진행 OK) | CEO HOLD SCOPE

## 0. CEO 판정 (10-star / HOLD)

**사고 원인 ≠ 알림 인프라 부재.**  
PC/모바일/태블릿 Web Push·벨·배지·긴급호출은 2026-07-04에 이미 운영 배선됨.  
진짜 갭: **실측/CS가 ERP Order 저장해도 도면팀 수신 경로가 0**.  
워크벤치 `?tab=timeline`은 `drawing_transfer_history`(전달/수정요청)만 표시 — 주문 필드 변경 로그 없음.

**모드: HOLD SCOPE** — 알림 스택 재구축 금지. 기존 fanout/push/deep-link 패턴에 **1 유형 + 타임라인 로그 + 딥링크**만 추가.

**Selective 확장 (사고 방지에 필요):**
- 도면 관련 필드만 diff (전 필드 스팸 금지)
- 도면 작업 시작/진행 중일 때만 알림 (미배정 PENDING 노이즈 억제)
- Push deep link → 워크벤치 timeline (주문 상세 아님)
- 워크벤치 상단 “주문 변경 확인” 배너 (탭 닫혀 있어도 재진입 시 못 놓침)

**Out of scope:** 네이티브앱/FCM/SMS/카카오, STAGE_CHANGED 전면 Notification화, OrderEvent→timeline 전량 이식.

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
도면 담당자(팀 DRAWING + 해당 주문 DRAWING_DOMAIN 배정자)가:
1. **OS 알림**(Web Push) — ERP 탭 닫혀 있어도 PC/모바일/태블릿에서 수신
2. **인앱 벨/배지** — 브라우저 열림 시
3. **워크벤치 timeline** — `ERP_ORDER_CHANGED` 이력 행 + 하이라이트
4. **딥링크** — 알림 탭 → `/erp/drawing-workbench/{id}?tab=timeline&event_id=...`

을 통해 “누가·무엇을·언제” 바꿨는지 확인하고 도면 수정에 들어갈 수 있다.

### 1.2 기능 요구사항

1. **트리거 SSOT**  
   ERP Order 저장 경로에서 도면-relevant 필드 diff 발생 시:
   - `PUT /orders/<id>/structured` (`api_put_order_structured`)
   - `PATCH` structured 필드 (`apply_field_patch` 성공 경로)
   - (해당 시) `update_order_field` 중 structured에 반영되는 도면 관련 필드

2. **도면 타임라인에 남기는 ERP 필드** (변경 시 before→after):
   - 당사자: 담당자·고객·연락처·발주사·시공 담당자
   - 주소·실측/시공 일시
   - 제품 행별: 제품명·W/D/H·색상·내부재·옵션·손잡이 등 (**필드별 before→after**)
   - 메모·플래그·결제·지방/시공유형
   - (제외) drawing/quest/workflow.stage/전달이력 등 운영 JSON · 단계 단독 변경은 STAGE 경로

3. **게이트 (알림·로그·목록 표기 조건)** — 아래 중 하나면 발동:
   - `drawing_status` ∈ {IN_PROGRESS, TRANSFERRED, RETURNED, CONFIRMED} **또는**
   - DRAWING_DOMAIN assignee 존재 **또는**
   - workflow stage가 DRAWING 이상  
   → 게이트 미충족이면 history/Notification/목록 배지 **전부 안 씀** (노이즈 0).

3b. **도면 작업실 목록 표기** (`/erp/drawing-workbench`) — 사용자 승인 반영:
   - 해당 주문에 미확인 `ERP_ORDER_CHANGED`가 있으면 리스트 행에 **「주문변경」** 배지/칩 표시
   - 상세 진입·타임라인 확인(또는 배너 dismiss/ack) 전까지 유지
   - SSOT 플래그: `structured_data.drawing.order_change_pending = true` (history 최신 ERP_ORDER_CHANGED와 동기; ack 시 false)
   - 목록 카드/행에서 한눈에 “이 건 주문 내용 바뀜” 인지 가능해야 함

4. **타임라인 로그** (`structured_data.drawing_transfer_history` append):
   ```json
   {
     "action": "ERP_ORDER_CHANGED",
     "by_user_id": ...,
     "by_user_name": "...",
     "at": "YYYY-MM-DD HH:MM:SS",
     "note": "치수 W 1200→1300 · 시공일 07-20→07-22",
     "changed_fields": ["items.0.width", "schedule.construction.date"],
     "changes": [{"path": "...", "from": "...", "to": "..."}],
     "acked": false
   }
   ```
   - note 요약 ≤ 200자 (초과 시 `외 N건`)
   - **60초 debounce merge** (스팸 방지):
     - 의미: 같은 사람이 같은 주문을 **60초 안에 여러 번 저장**하면 알림·이력 행을 **5개 만들지 않고 1개로 합침**
     - 예: 치수 저장 → 3초 뒤 주소 저장 → 10초 뒤 시공일 저장 → timeline/벨/푸시 = **1건**, note에 변경 전부 누적
     - 60초 지나 다시 저장 → **새 1건** 추가

## 6. 승인 기록 (2026-07-15)
1. 게이트 + **목록「주문변경」표기** — 승인(요구 반영)
2. 60초 debounce — 설명 후 유지(스팸 방지)
3. 구현→리뷰→deploy 푸시 — OK

5. **Notification**:
   - `notification_type = 'ERP_ORDER_CHANGED'`
   - `target_team = 'DRAWING'`
   - title: `주문 내용 변경 (도면 확인 필요)`
   - message: `주문 #{id} — {note 요약}` + 변경자명
   - fan_out + enqueue_push + emit_realtime (DRAWING_REVISION 패턴 복제)
   - P1: `_DEFAULT_P1_TYPES`에 `ERP_ORDER_CHANGED` 추가
   - deep link: `_resolve_notification_deep_link`에 타입 추가 → tab=timeline, action=ERP_ORDER_CHANGED
   - push `_deep_link` / `_generic_title`: 도면 워크벤치 경로 + “도면·주문 변경” 제목

6. **UI/UX**
   - timeline 배지: `ERP_ORDER_CHANGED` → `주문 변경` (warning/amber)
   - 모바일 handoff thread 동일 라벨
   - 워크벤치 상세 상단: 미확인 ERP_ORDER_CHANGED가 있으면 sticky 배너  
     “주문 내용이 변경되었습니다 — 타임라인에서 확인” → 스크롤/탭 포커스
   - 알림 시트·벨: 기존 컴포넌트 재사용 (신규 패널 금지)
   - Push CTA: 기존 mobile-push CTA 유지. 도면 워크벤치(모바일/태블릿)에 **미구독 시 1회 안내 칩**(기존 CTA로 연결) — 새 구독 스택 금지

7. **디바이스 커버리지 점검 결과 (구현 전 실측 요약)**
   | 채널 | PC | 모바일 | 태블릿 | 탭 닫힘 |
   |------|----|--------|--------|---------|
   | Web Push (SW) | ✅ 구독 시 | ✅ (iOS=홈화면 추가+구독) | ✅ | ✅ |
   | Socket.IO overlay | ✅ | ✅ | ✅ | ❌ |
   | 벨/배지 poll | ✅ | ✅ | ✅ | 재진입 시 ✅ |
   | **ERP_ORDER_CHANGED** | ❌ 미구현 | ❌ | ❌ | ❌ |

### 1.3 예외/제약
- 변경자 본인이 DRAWING 팀원이어도 fanout은 팀 전원(본인 제외는 recipients SSOT 기존 규칙 따름)
- Push payload에 고객명/주소 전문 금지 (기존 generic body 정책)
- 마이그레이션 불필요 (타입=문자열, history=JSONB)
- N+1/hot-path: diff는 메모리 비교; 알림 생성은 커밋 후 push enqueue
- fragment JS idempotent (`window.__FOMS_*_BOUND`)
- script defer / CDN 동기 금지

---

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 |
|------|------|
| `foms/services/notifications/drawing_order_change.py` | **신규** diff·게이트·history append·Notification create SSOT |
| `foms/api/erp_orders_structured.py` | PUT/PATCH 성공 경로에서 SSOT 호출 |
| `foms/api/orders/field_update.py` | 해당 필드 시 SSOT 호출 (필요 시) |
| `foms/services/notifications/push_sender.py` | P1 + title + deep_link workbench |
| `foms/api/notifications/__init__.py` | `_resolve_notification_deep_link` 타입 확장 |
| `models.py` | Notification 타입 주석에 ERP_ORDER_CHANGED |
| `foms/web/drawing/workbench.py` | action_label 맵 + 미확인 배너 + **목록 order_change_pending 배지** |
| `templates/drawing/partials/workbench_*.html` (list+detail) | 목록「주문변경」칩 · 상세 배너·라벨 |
| `templates/drawing/partials/workbench_mobile_handoff.html` | 동일 라벨 |
| `static/css/contexts/drawing/` (기존 workbench css) | 배너·warning 배지 |
| `static/js/foms/drawing-handoff.js` 또는 workbench JS | 배너→timeline 스크롤 (idempotent) |
| `tests/domains/test_drawing_erp_order_change_alert.py` | **신규** diff/게이트/알림/딥링크 |

### 2.2 아키텍처
- 패턴 복제: `erp_orders_revision.py` (history + Notification + fan_out + push + realtime)
- Diff SSOT 한 함수 → 저장 경로 여러 곳에서 호출 (중복 emit 금지)
- Debounce: 같은 tx 내 1회; 60초 soft-merge는 history last entry 갱신

### 2.3 영향 범위
- DB 스키마 변경 없음
- 기존 DRAWING_* 알림 회귀 테스트 유지
- Railway env: `FOMS_PUSH_P1_TYPES` 커스텀 시 운영에 `ERP_ORDER_CHANGED` 수동 추가 필요 — 기본 frozenset에 넣으면 미설정 env는 자동 포함

---

## 3. Steps — 실행 단계
- [ ] Step 1: SSOT 서비스 `drawing_order_change.py` + 단위 테스트
- [ ] Step 2: structured PUT/PATCH 배선
- [ ] Step 3: push P1 + deep link + generic title
- [ ] Step 4: workbench timeline 라벨·배너·CSS/JS
- [ ] Step 5: 1:1 소스 리뷰 (cavecrew-reviewer)
- [ ] Step 6: pytest + APP_OK + perf_scan --guard
- [ ] Step 7: pre_push_smoke → **deploy 푸시** (사용자 요청 시)

---

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 
- [ ] 신규 pytest green (diff/게이트/emit/딥링크)
- [ ] 기존 notification/push/drawing workbench 회귀
- [ ] `python tools/perf/perf_scan.py --guard` high=0
- [ ] 스테이징: 주문 치수 변경 → DRAWING 유저 벨+timeline+push(구독 시)
- [ ] PC/모바일/태블릿: 벨 UI·딥링크 워크벤치 timeline 랜딩

---

## 5. 참고
- 기존: `docs/AI_STATUS.md` 2026-07-04 모바일 알림센터+Web Push
- 패턴: `foms/api/drawing/erp_orders_revision.py`
- 딥링크: `foms/api/notifications/__init__.py` `_resolve_notification_deep_link`
- 페르소나: 도면 담당 — “치수 바뀐 줄 모르고 옛 도면 전달” 사고 방지
