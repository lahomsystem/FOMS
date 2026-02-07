# 📦 FOMS 가구 주문 프로세스 대규모 업데이트 Blueprint

**생성일**: 2026-02-07  
**버전**: v1.0  
**목표**: Furniture Process.md 기반 FOMS 시스템 완전 정렬

---

## 📊 1. 현재 시스템 분석 (Production Code Audit)

### 1.1 기술 스택
| 구분 | 기술 |
|-----|-----|
| **Backend** | Python 3.12+ / Flask |
| **Database** | PostgreSQL + SQLAlchemy |
| **Frontend** | Jinja2 Templates + Vanilla JS + Bootstrap 5 |
| **Storage** | Cloudflare R2 (S3 호환) |
| **배포** | Railway |
| **실시간** | Socket.IO (WebSocket) |

### 1.2 핵심 모델 구조
```
Order (주문)
├── id, received_date, customer_name, customer_phone, address
├── product, options, status
├── construction_date (시공일)
├── manager (영업 담당자)
├── structured_data (JSON) ← ERP 확장 데이터
│   ├── stage (현재 단계)
│   ├── flags (urgent, etc.)
│   └── items[] (제품 상세)
├── blueprint_file (도면 첨부)
└── relationships
    ├── OrderAttachment[] (첨부 파일)
    ├── OrderEvent[] (이벤트 스트림)
    └── OrderTask[] (팔로업/이슈)

User (사용자)
├── username, password, name
├── role (ADMIN, MANAGER, STAFF)
└── is_active

ChatRoom / ChatMessage / ChatAttachment (채팅 시스템)
```

### 1.3 현재 프로세스 단계 (erp_quest_templates.json)
```
RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION
  (A)        (B)          (C)       (D)        (E)        (F)           (G)
```

### 1.4 현재 대시보드 목록
| 대시보드 | 파일 | 용도 |
|---------|-----|-----|
| **ERP 대시보드** | `erp_dashboard.html` | 메인 작업 큐 (단계별 주문 관리) |
| **실측 대시보드** | `erp_measurement_dashboard.html` | 실측 일정 관리 |
| **출고 대시보드** | `erp_shipment_dashboard.html` | 시공 일정/출고일지 |
| **AS 대시보드** | `erp_as_dashboard.html` | AS 접수 및 관리 |
| **지방 대시보드** | `regional_dashboard.html` | 지방 주문 관리 |
| **수도권 대시보드** | `metropolitan_dashboard.html` | 수도권 주문 관리 |
| **셀프실측 대시보드** | `self_measurement_dashboard.html` | 고객 직접 실측 |
| **주문 목록** | `index.html` | 전체 주문 테이블 |

---

## 🔍 2. Gap 분석: Furniture Process vs 현재 FOMS

### 2.1 프로세스 매핑

| Furniture Process 단계 | FOMS 현재 구현 | 상태 | Gap |
|----------------------|---------------|------|-----|
| **A. 주문 접수** | ✅ RECEIVED 단계 | 🟢 | 완료 |
| **B. 해피콜** | ✅ HAPPYCALL 단계 | 🟢 | 완료 |
| **C. 실측** | ✅ MEASURE 단계 + 실측 대시보드 | 🟢 | 완료 |
| **D. 도면 작성** | ✅ DRAWING 단계 + blueprint_file | 🟢 | 완료 |
| **E. 고객 컨펌** | ✅ CONFIRM 단계 | 🟡 | 도면 전달 추적 부족 |
| **F. 생산** | ✅ PRODUCTION 단계 | 🟡 | 생산팀 전용 뷰 없음 |
| **G. 시공** | ✅ CONSTRUCTION 단계 + 출고 대시보드 | 🟢 | 완료 |
| **H. CS 관리** | ✅ AS 대시보드 | 🟡 | CS 상태 변경 접근성 부족 |

### 2.2 Special Notes 분석

| 개선 요구사항 | 우선순위 | 현재 상태 | 필요 작업 |
|-------------|---------|----------|----------|
| **CS 상태 변경 접근성 강화** | ⭐ HIGH | ❌ 없음 | 플로팅 메뉴/공통 상태 변경 버튼 |
| **시공 일정표 이미지화** | ⭐⭐ CRITICAL | ❌ 없음 | [이미지 저장] 버튼 구현 |
| **누락 기능/카테고리 추가** | ⭐ HIGH | 분석 필요 | 아래 상세 참조 |

### 2.3 누락된 기능 상세

#### 2.3.1 CS 상태 변경 접근성 강화
- **현재**: 주문 상세 페이지 또는 ERP 대시보드에서만 상태 변경 가능
- **요구**: 모든 화면에서 접근 가능한 공통 버튼
- **해결책**: 
  - 플로팅 액션 버튼 (FAB) 구현
  - 또는 네비게이션 바에 "빠른 상태 변경" 드롭다운 추가
  - 주문 ID 입력 → 현재 상태 표시 → 변경 가능 상태 선택

#### 2.3.2 시공 일정표 이미지화
- **현재**: 출고 대시보드에서 화면으로만 확인
- **요구**: 고화질 이미지로 다운로드하여 시공팀에 공유
- **해결책**:
  - `html2canvas` 또는 `dom-to-image` 라이브러리 활용
  - 출고 대시보드 날짜별 일정을 PNG/WebP로 내보내기
  - 시공팀 그룹 전용 공유 탭 추가 (선택)

#### 2.3.3 추가 식별된 Gap
| 카테고리 | Gap | 권장 해결책 |
|---------|-----|-----------|
| **도면 전달 추적** | 도면 전달 시각/방법 기록 없음 | `structured_data.blueprint_sent_at`, `blueprint_sent_via` 필드 추가 |
| **생산팀 전용 뷰** | 생산 단계 주문만 보는 대시보드 없음 | 생산 대시보드 신규 생성 또는 ERP 대시보드 필터 개선 |
| **팀별 권한** | 팀별 접근 제어 세분화 부족 | `User.team` 필드 추가, 팀별 필터링 |
| **알림 시스템** | 단계 변경 시 관련 팀 알림 없음 | 이벤트 기반 알림 (Socket.IO 활용) |

---

## 🎯 3. 개발 계획 (Phase별)

### Phase 1: 긴급 수정 (1-2일)

#### 1.1 CS 상태 변경 플로팅 버튼
**파일**: `templates/layout.html`, `static/js/quick-status-change.js`

```html
<!-- 플로팅 액션 버튼 -->
<div class="quick-status-fab" id="quickStatusFab">
  <button class="fab-main-btn" onclick="openQuickStatusModal()">
    <i class="bi bi-lightning-charge-fill"></i>
  </button>
</div>

<!-- 빠른 상태 변경 모달 -->
<div class="modal" id="quickStatusModal">
  <input type="text" id="quickOrderId" placeholder="주문번호 입력">
  <div id="currentStatusDisplay"></div>
  <select id="newStatusSelect"></select>
  <button onclick="changeStatus()">변경</button>
</div>
```

**API**: `/api/orders/<id>/quick-status` (POST)

#### 1.2 시공 일정표 이미지 저장
**파일**: `templates/erp_shipment_dashboard.html`, `static/js/shipment-image-export.js`

```javascript
async function exportShipmentAsImage() {
  const element = document.querySelector('.shipment-schedule');
  const canvas = await html2canvas(element, {
    scale: 2, // 고해상도
    useCORS: true
  });
  const link = document.createElement('a');
  link.download = `시공일정표_${selectedDate}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
}
```

### Phase 2: 프로세스 정합성 개선 (3-5일)

#### 2.1 도면 전달 추적
**변경 파일**: `models.py`, `erp_policy.py`, `erp_dashboard.html`

```python
# models.py - Order.structured_data 스키마 확장
{
  "blueprint": {
    "file_key": "...",
    "uploaded_at": "2026-02-07T10:00:00",
    "sent_at": "2026-02-07T11:00:00",
    "sent_via": "channeltalk",  # channeltalk, kakao, sms
    "customer_confirmed": false,
    "confirmed_at": null
  }
}
```

#### 2.2 팀별 역할 확장
**변경 파일**: `models.py`, `apps/auth.py`

```python
# models.py - User 모델
class User(Base):
    # 기존 필드...
    team = Column(String(50), nullable=True)  # CS, SALES, DRAWING, PRODUCTION, CONSTRUCTION
```

```python
# apps/auth.py - 팀 기반 데코레이터
def team_required(*teams):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.team not in teams:
                return jsonify({'error': '접근 권한 없음'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

#### 2.3 생산 대시보드
**신규 파일**: `templates/erp_production_dashboard.html`
**Blueprint 등록**: `apps/erp_beta.py`

- PRODUCTION 단계 주문만 필터링
- 도면 오류 시 도면팀 피드백 기능
- 제작 완료 시 자동 시공 단계 전환

### Phase 3: 고도화 (5-10일)

#### 3.1 알림 시스템
**신규 파일**: `notifications.py`, `templates/partials/notifications.html`

```python
# 단계 변경 시 관련 팀에 Socket.IO 알림
def notify_stage_change(order_id, old_stage, new_stage, target_team):
    socketio.emit('stage_change', {
        'order_id': order_id,
        'old_stage': old_stage,
        'new_stage': new_stage,
    }, room=f'team_{target_team}')
```

#### 3.2 Quest 시스템 확장 - H단계 (CS) 추가
**변경 파일**: `data/erp_quest_templates.json`, `erp_policy.py`

```json
{
  "CS": {
    "title": "CS/AS 관리",
    "description": "",
    "owner_team": "CS",
    "required_approvals": ["CS"],
    "next_stage": null,
    "is_terminal": true,
    "entry_conditions": ["from_any_stage"]
  }
}
```

#### 3.3 대시보드 통합 뷰
- 각 팀별 맞춤 대시보드 뷰 (팀 역할에 따라 자동 필터링)
- 크로스 팀 협업 기능 (도면팀 ↔ 생산팀 피드백)

---

## 📋 4. 작업 체크리스트

### Phase 1 (긴급)
- [ ] 1.1 플로팅 상태 변경 버튼 구현
  - [ ] `layout.html`에 FAB 추가
  - [ ] `quick-status-change.js` 생성
  - [ ] `/api/orders/<id>/quick-status` API 추가
  - [ ] CSS 스타일링
- [ ] 1.2 시공 일정표 이미지 저장
  - [ ] `html2canvas` CDN 추가
  - [ ] `shipment-image-export.js` 생성
  - [ ] 출고 대시보드에 [이미지 저장] 버튼 추가

### Phase 2 (정합성)
- [ ] 2.1 도면 전달 추적
  - [ ] `structured_data` 스키마 문서화
  - [ ] 도면 전달 UI 추가
  - [ ] 고객 컨펌 상태 추적
- [ ] 2.2 팀별 역할 확장
  - [ ] `User.team` 필드 추가 마이그레이션
  - [ ] 관리자 페이지에서 팀 설정 UI
  - [ ] `team_required` 데코레이터 구현
- [ ] 2.3 생산 대시보드
  - [ ] 라우트 추가 (`/erp/production`)
  - [ ] 템플릿 생성
  - [ ] 네비게이션 메뉴 추가

### Phase 3 (고도화)
- [ ] 3.1 알림 시스템
  - [ ] Socket.IO 룸 기반 알림
  - [ ] 알림 센터 UI
  - [ ] 알림 히스토리 저장
- [ ] 3.2 CS 단계 추가
  - [ ] Quest 템플릿 업데이트
  - [ ] AS 대시보드 연동
- [ ] 3.3 대시보드 통합 뷰
  - [ ] 팀별 자동 필터링
  - [ ] 협업 기능

---

## 📁 5. 파일 변경 예상 목록

### 수정 대상
| 파일 | 변경 내용 |
|-----|----------|
| `templates/layout.html` | 플로팅 버튼, 알림 센터 추가 |
| `templates/erp_shipment_dashboard.html` | 이미지 저장 버튼 추가 |
| `templates/erp_dashboard.html` | 도면 전달 UI, 팀별 필터링 |
| `models.py` | `User.team` 필드 추가 |
| `apps/auth.py` | `team_required` 데코레이터 |
| `apps/erp_beta.py` | 생산 대시보드 라우트, 알림 연동 |
| `erp_policy.py` | CS 단계 정책 추가 |
| `data/erp_quest_templates.json` | CS 단계 템플릿 |

### 신규 생성
| 파일 | 설명 |
|-----|-----|
| `static/js/quick-status-change.js` | 빠른 상태 변경 |
| `static/js/shipment-image-export.js` | 일정표 이미지 저장 |
| `templates/erp_production_dashboard.html` | 생산 대시보드 |
| `notifications.py` | 알림 시스템 핵심 |
| `templates/partials/notifications.html` | 알림 UI |

---

## ⚠️ 6. 리스크 및 주의사항

| 리스크 | 영향도 | 대응책 |
|-------|-------|--------|
| DB 마이그레이션 | 🟠 Medium | Railway 스테이징 환경에서 테스트 후 적용 |
| 기존 데이터 호환성 | 🟠 Medium | `structured_data` 스키마 버전 관리 |
| 실시간 알림 부하 | 🟡 Low | Socket.IO 룸 기반으로 분리 |
| 이미지 저장 성능 | 🟡 Low | 클라이언트 사이드 처리로 서버 부하 없음 |

---

## 🚀 7. 실행 순서

```
1️⃣ Phase 1.2 시공 일정표 이미지화 (⭐⭐ CRITICAL - 우선 구현)
       ↓
2️⃣ Phase 1.1 CS 상태 변경 플로팅 버튼
       ↓
3️⃣ Phase 2.1 도면 전달 추적
       ↓
4️⃣ Phase 2.2 팀별 역할 확장
       ↓
5️⃣ Phase 2.3 생산 대시보드
       ↓
6️⃣ Phase 3.x 고도화 (선택적)
```

---

## 📌 8. 결론

### 현재 FOMS 상태: 🟢 **80% 완성도**
- 기본 프로세스 (A~G) 모두 구현됨
- Quest 시스템으로 단계별 승인 관리 가능
- 각 단계별 전용 대시보드 존재

### 주요 Gap: 
1. **CS 접근성** - 플로팅 버튼으로 해결
2. **시공 일정 공유** - 이미지 저장으로 해결
3. **팀별 세분화** - 역할 확장으로 해결

### 예상 소요 시간:
- Phase 1: **1-2일** (긴급)
- Phase 2: **3-5일** (정합성)
- Phase 3: **5-10일** (선택적 고도화)

---

**작성자**: Antigravity AI  
**검토자**: (사용자 확인 필요)  
**승인일**: (TBD)
