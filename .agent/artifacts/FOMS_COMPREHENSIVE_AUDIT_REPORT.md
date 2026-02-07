# 📊 FOMS ERP 시스템 종합 분석 보고서

**작성일**: 2026-02-07  
**분석자**: Antigravity AI (Production Code Audit Skill 활용)  
**버전**: v1.0

---

## 📌 1. Executive Summary

### 1.1 프로세스 구성 완료도 평가

| 항목 | 완료도 | 상태 |
|-----|--------|------|
| **Blueprint 문서화** | 100% | ✅ 완료 |
| **프로세스 단계 구현** | 100% | ✅ RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION (+ COMPLETED/AS) |
| **대시보드 구현** | 95% | ✅ ERP 대시보드, 실측, 출고, 생산, 시공, AS 대시보드 모두 구현 |
| **Quest 시스템** | 100% | ✅ 단계별 승인 체계 완비 |
| **API 엔드포인트** | 90% | ✅ 대부분 구현, 일부 미세 조정 필요 |

### 1.2 전체 시스템 상태: 🟢 **Production-Ready (90% 완성도)**

---

## 📋 2. FOMS_FURNITURE_PROCESS_BLUEPRINT.md 분석

### 2.1 Blueprint 체크리스트 진행 상황

| Phase | 항목 | 상태 | 비고 |
|-------|-----|------|-----|
| **Phase 1** | 1.1 CS 상태 변경 플로팅 버튼 | ⚠️ 부분 구현 | Quick Status API 구현 완료, FAB UI 추가 필요 |
| | 1.2 시공 일정표 이미지 저장 | ⚠️ 미구현 | html2canvas 연동 필요 |
| **Phase 2** | 2.1 도면 전달 추적 | ✅ 구현 완료 | `api_order_transfer_drawing` 완비 |
| | 2.2 팀별 역할 확장 | ✅ 기반 구현 | `owner_team` 필드 활용 중 |
| | 2.3 생산 대시보드 | ✅ 구현 완료 | `erp_production_dashboard` 완비 |
| **Phase 3** | 3.1 알림 시스템 | ⚠️ 미구현 | Socket.IO 기반 알림 필요 |
| | 3.2 CS 단계 추가 | ⚠️ 미구현 | Quest 템플릿에 CS/AS 추가 필요 |
| | 3.3 대시보드 통합 뷰 | ⚠️ 미구현 | 팀별 자동 필터링 필요 |

### 2.2 결론
**Blueprint 문서 대비 구현 완료도: 70%**
- Phase 1, 2는 대부분 완료
- Phase 3 (고도화)는 아직 미착수

---

## 🔍 3. ERP Beta 프로세스 흐름 분석

### 3.1 전체 Workflow 단계

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  RECEIVED   │────▶│  HAPPYCALL  │────▶│   MEASURE   │────▶│   DRAWING   │
│  (주문접수)  │     │  (해피콜)    │     │   (실측)    │     │   (도면)    │
│  담당: CS    │     │  담당: CS    │     │  담당: SALES │     │ 담당: DRAWING│
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
       ┌───────────────────────────────────────────────────────────┘
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CONFIRM   │────▶│ PRODUCTION  │────▶│CONSTRUCTION │────▶│  COMPLETED  │
│  (고객컨펌)  │     │   (생산)    │     │   (시공)    │     │   (완료)    │
│  담당: SALES │     │담당:PRODUCTION│   │담당:CONSTRUCTION│ │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                                   ▼
                                                            ┌─────────────┐
                                                            │   AS_WAIT   │
                                                            │  (AS 대기)  │
                                                            └─────────────┘
```

### 3.2 각 단계별 대시보드 매핑

| Workflow 단계 | 대시보드 | 표시 라벨 | 담당 팀 |
|--------------|---------|----------|--------|
| RECEIVED | ERP 대시보드 | 주문접수 | CS |
| HAPPYCALL | ERP 대시보드 | 해피콜 | CS |
| MEASURE | ERP 대시보드 + 실측 대시보드 | 실측 | SALES |
| DRAWING | ERP 대시보드 | 도면 | DRAWING |
| CONFIRM | ERP 대시보드 + 생산 대시보드 | 고객컨펌/제작대기 | SALES |
| PRODUCTION | 생산 대시보드 | 제작중 | PRODUCTION |
| CONSTRUCTION | 시공 대시보드 + 출고 대시보드 | 시공대기/시공중 | CONSTRUCTION |
| COMPLETED | 시공 대시보드 | 시공완료 | - |

---

## ⚠️ 4. 충돌/중복 로직 분석

### 4.1 발견된 중복 코드 (Code Duplication)

#### 4.1.1 `erp_beta.py` 내 중복 함수 정의
```python
# 중복 1: _erp_get_urgent_flag 함수가 2번 정의됨
_erp_get_urgent_flag(structured_data)  # Line 192-196
_erp_get_urgent_flag(structured_data)  # Line 350-354

# 중복 2: _erp_get_stage 함수가 2번 정의됨
_erp_get_stage(order, structured_data)  # Line 198-207
_erp_get_stage(order, structured_data)  # Line 356-365

# 중복 3: _erp_has_media 함수가 2번 정의됨
_erp_has_media(order, attachments_count)  # Line 209-211
_erp_has_media(order, attachments_count)  # Line 367-369

# 중복 4: _erp_alerts 함수가 2번 정의됨
_erp_alerts(order, structured_data, attachments_count)  # Line 213-269
_erp_alerts(order, structured_data, attachments_count)  # Line 371-427
```

**심각도**: 🟠 HIGH  
**영향**: Python에서 후자 정의가 전자를 덮어씁니다. 의도된 동작인지 확인 필요.  
**권장 조치**: 중복 정의 제거 또는 의도적인 경우 명확한 주석 추가

#### 4.1.2 `erp_policy.py`와 `erp_beta.py` 간 중복
- `STAGE_LABELS` 매핑이 두 파일에 정의됨
- `_erp_get_stage` 로직이 `erp_policy.py`의 `get_stage`와 유사

**권장 조치**: `erp_policy.py`를 단일 소스로 통합

### 4.2 발견된 로직 충돌

#### 4.2.1 Stage vs Display Label 불일치
```python
# erp_production_dashboard에서:
stage_label = stage
if stage == 'CONFIRM' or stage == '고객컨펌': stage_label = '제작대기'
if stage == 'PRODUCTION' or stage == '생산': stage_label = '제작중'
if stage == 'CONSTRUCTION' or stage == '시공': stage_label = '제작완료'

# erp_policy.py에서:
STAGE_LABELS = {
    "CONFIRM": "고객컨펌",  # ≠ '제작대기'
    "PRODUCTION": "생산",    # ≠ '제작중'
    "CONSTRUCTION": "시공",  # ≠ '제작완료'
}
```

**심각도**: 🟡 MEDIUM  
**영향**: UI에서 혼란을 줄 수 있음. "고객컨펌"과 "제작대기"가 같은 단계임을 사용자가 인지 못할 수 있음.  
**권장 조치**: 
1. `erp_policy.py`에 `DISPLAY_LABELS_BY_DASHBOARD` 추가
2. 또는 대시보드별 `display` 필드를 템플릿에서 통합 관리

#### 4.2.2 Quest 승인 vs 직접 Stage 변경 충돌
```python
# api_order_quick_status_update: 직접 stage 변경
wf['stage'] = new_status

# Quest System: team_approvals 기반 승인 후 stage 변경
# check_quest_approvals_complete() 검증 후 변경

# 충돌 시나리오:
# 1. Quest가 DRAWING 단계이고 DRAWING 팀 승인 대기 중
# 2. 관리자가 quick_status로 CONFIRM으로 변경
# 3. Quest 상태와 workflow.stage가 불일치
```

**심각도**: 🟠 HIGH  
**영향**: Quest 시스템과 Quick Status 시스템이 독립적으로 동작하여 데이터 불일치 발생 가능  
**권장 조치**:
1. `quick_status_update`에 `quests` 배열도 함께 업데이트
2. 또는 Quick Status 사용 시 Quest 무효화 경고 표시

#### 4.2.3 workflow.stage vs Order.status 이원화
```python
# workflow.stage: structured_data.workflow.stage (새 시스템)
wf['stage'] = 'PRODUCTION'

# Order.status: Legacy 필드 (기존 시스템)
order.status = 'CONSTRUCTION'

# 동기화 로직이 일부 API에만 적용됨
# api_production_complete: order.status = 'CONSTRUCTION' ✅
# api_construction_complete: order.status = 'COMPLETED' ✅
# api_order_transfer_drawing: order.status 미변경 ❌
```

**심각도**: 🟡 MEDIUM  
**영향**: Legacy 시스템과의 호환성 문제  
**권장 조치**: 모든 stage 변경 API에서 `order.status` 동기화 통일

### 4.3 발견된 잠재적 버그

#### 4.3.1 datetime import 충돌 (해결됨)
```python
# 이전 문제: datetime.datetime.now() 호출 시 에러
# 원인: 파일 상단에 `import datetime`이 있지만 어딘가에서 datetime 이름이 덮어써짐
# 해결: 함수 내부에서 `import datetime as dt_mod` 사용으로 우회
```

#### 4.3.2 erp_quest_templates.json에 COMPLETED/AS 단계 미정의
```json
// 현재 정의된 단계:
"RECEIVED", "HAPPYCALL", "MEASURE", "DRAWING", "CONFIRM", "PRODUCTION", "CONSTRUCTION"

// 미정의 단계:
"COMPLETED", "AS_WAIT", "AS"
```

**심각도**: 🟡 MEDIUM  
**영향**: CONSTRUCTION 이후 단계에 대한 Quest 관리 불가  
**권장 조치**: COMPLETED, AS 단계 Quest 템플릿 추가

---

## 🎯 5. 설계 의도 vs 실제 구현 분석

### 5.1 FOMS 설계 의도 (Blueprint 기반)

1. **주문 프로세스 자동화**: 주문 접수부터 시공 완료까지 전 과정 추적
2. **팀별 워크플로우**: 각 단계별 담당 팀 배정 및 승인 체계
3. **실시간 상태 추적**: 대시보드를 통한 현황 파악
4. **알림 시스템**: 중요 일정 임박 시 자동 알림

### 5.2 실제 구현 상태

| 설계 의도 | 구현 상태 | 평가 |
|----------|----------|------|
| 주문 프로세스 자동화 | ✅ 7단계 워크플로우 완비 | 🟢 우수 |
| 팀별 워크플로우 | ✅ Quest 시스템 기반 승인 | 🟢 우수 |
| 실시간 상태 추적 | ✅ 6개 대시보드 운영 | 🟢 우수 |
| 알림 시스템 | ⚠️ 미구현 | 🟠 개선 필요 |
| CS 빠른 접근 | ⚠️ API만 구현, UI 미완성 | 🟡 진행 중 |
| 이미지 내보내기 | ⚠️ 미구현 | 🔴 미완성 |

### 5.3 의도 대비 Gap

1. **알림 시스템 부재**: Socket.IO 기반 실시간 알림 미구현
2. **이미지 내보내기 부재**: 시공 일정표 이미지화 미구현
3. **통합 뷰 부재**: 팀별 자동 필터링 대시보드 미구현

---

## 💡 6. 추가 기능 제안

### 6.1 즉시 구현 권장 (Critical)

#### 6.1.1 Quest 시스템과 Quick Status 동기화
```python
# 제안: api_order_quick_status_update 수정
def api_order_quick_status_update(order_id):
    # ... 기존 로직 ...
    
    # Quest 동기화 추가
    quests = sd.get('quests') or []
    for q in quests:
        if q.get('stage') == old_status:
            q['status'] = 'SKIPPED'  # 또는 'SUPERSEDED'
    
    # 새 단계의 Quest 생성
    new_quest = create_quest_from_template(new_status, user.name, sd)
    if new_quest:
        quests.append(new_quest)
    sd['quests'] = quests
```

#### 6.1.2 COMPLETED/AS Quest 템플릿 추가
```json
{
  "COMPLETED": {
    "title": "시공 완료 확인",
    "description": "",
    "owner_team": "CS",
    "required_approvals": ["CS"],
    "next_stage": null,
    "is_terminal": true
  },
  "AS_WAIT": {
    "title": "AS 접수",
    "description": "",
    "owner_team": "CS",
    "required_approvals": ["CS"],
    "next_stage": "AS_COMPLETE",
    "entry_conditions": ["from_any_stage"]
  }
}
```

### 6.2 단기 개선 권장 (High)

#### 6.2.1 중복 함수 통합
`erp_beta.py`의 중복 함수들을 `erp_policy.py`로 이동하고 import 사용

#### 6.2.2 Stage/Display Label 통합 관리
```python
# erp_policy.py에 추가
DASHBOARD_DISPLAY_LABELS = {
    'production': {
        'CONFIRM': '제작대기',
        'PRODUCTION': '제작중',
        'CONSTRUCTION': '제작완료',
    },
    'construction': {
        'CONSTRUCTION': '시공대기',
        'CONSTRUCTING': '시공중',  # 새 상태 추가
        'COMPLETED': '시공완료',
    }
}
```

### 6.3 중장기 개선 권장 (Medium)

#### 6.3.1 알림 시스템 구현
```python
# notifications.py
def notify_stage_change(order_id, old_stage, new_stage, target_team):
    socketio.emit('stage_change', {
        'order_id': order_id,
        'old_stage': old_stage,
        'new_stage': new_stage,
    }, room=f'team_{target_team}')

def notify_imminent_deadline(order_id, deadline_type, d_minus):
    # D-4 실측, D-3 시공, D-2 생산 알림
    pass
```

#### 6.3.2 시공 일정표 이미지 내보내기
```javascript
// static/js/shipment-image-export.js
async function exportShipmentAsImage() {
    const element = document.querySelector('.shipment-schedule');
    const canvas = await html2canvas(element, { scale: 2 });
    const link = document.createElement('a');
    link.download = `시공일정표_${selectedDate}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
}
```

#### 6.3.3 팀별 대시보드 자동 필터링
```python
# 사용자 team 기반 자동 필터
@erp_beta_bp.route('/erp/my-dashboard')
@login_required
def erp_my_dashboard():
    user = get_user_by_id(session.get('user_id'))
    team = user.team if user else None
    
    if team == 'CS':
        return redirect(url_for('erp_beta.erp_dashboard', stage='RECEIVED'))
    elif team == 'PRODUCTION':
        return redirect(url_for('erp_beta.erp_production_dashboard'))
    elif team == 'CONSTRUCTION':
        return redirect(url_for('erp_beta.erp_construction_dashboard'))
    # ...
```

---

## 📊 7. 최종 평가

### 7.1 종합 점수

| 카테고리 | 점수 | 비고 |
|---------|------|-----|
| **아키텍처** | 8/10 | 깔끔한 모듈 분리, 일부 중복 존재 |
| **프로세스 완성도** | 9/10 | A~G 단계 + AS 모두 구현 |
| **코드 품질** | 7/10 | 중복 코드 및 일부 불일치 존재 |
| **확장성** | 8/10 | Quest 시스템으로 유연한 확장 가능 |
| **Production Readiness** | 8/10 | 로깅/에러 핸들링 양호, 알림 시스템 미비 |
| **종합** | **8/10** | **Production Ready with Minor Improvements** |

### 7.2 권장 조치 우선순위

1. 🔴 **즉시**: 중복 함수 정리 (의도치 않은 동작 방지)
2. 🟠 **1주 내**: Quest/Quick Status 동기화 로직 추가
3. 🟡 **2주 내**: COMPLETED/AS Quest 템플릿 추가
4. 🟢 **1달 내**: 알림 시스템 및 이미지 내보내기 구현

---

## 📁 8. 첨부: 파일별 분석 요약

| 파일 | 라인 수 | 역할 | 상태 |
|-----|--------|-----|------|
| `apps/erp_beta.py` | 2,514 | 메인 라우트 및 API | ⚠️ 중복 함수 정리 필요 |
| `erp_policy.py` | 623 | 정책/규칙 정의 | ✅ 양호 |
| `data/erp_quest_templates.json` | 55 | Quest 템플릿 | ⚠️ COMPLETED/AS 추가 필요 |
| `templates/erp_production_dashboard.html` | ~300 | 생산 대시보드 UI | ✅ 양호 |
| `templates/erp_construction_dashboard.html` | ~300 | 시공 대시보드 UI | ✅ 양호 |

---

**작성자**: Antigravity AI  
**검토자**: (사용자 확인 필요)  
**승인일**: (TBD)
