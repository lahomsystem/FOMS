# P0 Spec — 위험 레이더 드릴다운 정밀화 (SSOT + risk_frame)

- 작성: 2026-06-13 · 근거: [risk-radar-drilldown-ux 연구](../research/2026-06-13-risk-radar-drilldown-ux.md)
- 성격: **승인 대기 Spec**. 승인 후 구현.
- 범위: P0 2건. (P1 수명·CTA / P2 전용 view는 별도.)

## 문제 (라이브 입증)
1. `construction_unready`·`balance_due`가 동일 `alert_type=construction_d3` → 착지 동일·부정확.
2. 4종 모두 착지 모집단이 카드보다 넓음(`measurement_d4`는 미배정 아닌 전체 실측).
3. 한 위험에 술어 3개(카드 `_risk_*` / 칩 `_q_stats` SQL / 리스트 메모리 `_erp_alerts`) → 숫자 불일치, "전체 N" 칩 + 0건 리스트.
4. 착지가 일반 "작업 큐"(글로벌 단계 칩) → 위험 프레임 상실.

## 설계 원칙
**위험 모집단의 단일 진실원(SSOT).** 카드 카운트·착지 칩·착지 리스트가 **동일 술어 하나**(= 정확 order-id 집합)를 공유. 라우팅이 아니라 *"이 위험에 속한 주문"의 정의를 한 곳*에 두는 게 핵심.

구현 방식 = **ID-set 물성화(materialization)**: `_risk_*`가 이미 계산하는 정확 모집단을 order-id 리스트로 노출 → 착지 큐를 `Order.id.in_(risk_ids)`로 필터. JSONB-in-SQL 곡예 없이 3숫자 일치를 **구조적으로 보장**. (잔금·미배정은 기존대로 후보 200캡 스캔 — counts에서 이미 수용된 비용.)

---

## P0-1. `risk=<key>` 파라미터 + ID-set SSOT

### 서비스 `foms/services/orders/dashboard_control_tower.py`
키별 **id 함수** 분리(기존 `_risk_*`는 이를 감싸 카드용 count/samples 생성):

```python
RISK_KEYS = ("construction_unready", "drawing_stalled", "measure_unassigned", "balance_due")

def _ids_construction_unready(base, cons_dates) -> list[int]:
    return [r[0] for r in base.filter(
        Order.erp_construction_date.in_(cons_dates),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(_INSTALL_READY_CODES)),
    ).with_entities(Order.id).all()]

def _ids_drawing_stalled(base) -> list[int]:
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=48)
    return [r[0] for r in base.filter(
        Order.erp_stage_code.in_(["DRAWING", "CONFIRM"]),
        Order.erp_stage_updated_at.isnot(None), Order.erp_stage_updated_at <= cutoff,
    ).with_entities(Order.id).all()]

def _ids_measure_unassigned(base, meas_dates) -> list[int]:
    cand = base.filter(Order.erp_measurement_date.in_(meas_dates)).limit(_RISK_CAND_LIMIT).all()
    return [o.id for o in cand if not _measure_assigned(o, _ensure_dict(getattr(o, "structured_data", None)))]

def _ids_balance_due(base, cons_dates) -> list[int]:
    cand = base.filter(Order.erp_construction_date.in_(cons_dates)).limit(_RISK_CAND_LIMIT).all()
    return [o.id for o in cand if (_balance_remaining(_ensure_dict(getattr(o, "structured_data", None))) or 0) > 0]

def build_risk_order_ids(db, current_user, key, *, today=None) -> list[int]:
    """위험 key의 정확 order-id 집합 (착지 큐 SSOT). 카드와 동일 술어."""
    today = today or datetime.date.today()
    base = _tower_base_query(db, current_user)
    cons = _business_window_dates(today, max_business_days=3, window_days=10)
    meas = _business_window_dates(today, max_business_days=4, window_days=12)
    return {
        "construction_unready": lambda: _ids_construction_unready(base, cons),
        "drawing_stalled": lambda: _ids_drawing_stalled(base),
        "measure_unassigned": lambda: _ids_measure_unassigned(base, meas),
        "balance_due": lambda: _ids_balance_due(base, cons),
    }.get(key, list)()
```

- 기존 `_risk_construction_unready` 등은 내부에서 `_ids_*` 호출 → `count=len(ids)` (카드=SSOT 동일 술어).
- `_risk_group` 의 filter를 `{"alert_type": ...}` → **`{"risk": key}`** 로 변경. (카드 href가 `?view=queue&risk=<key>`.)

### 라우트 `foms/web/orders/dashboard.py`
```python
f_risk = (request.args.get('risk') or '').strip()
if f_risk not in RISK_KEYS: f_risk = ''
...
if f_risk:
    from foms.services.orders.dashboard_control_tower import build_risk_order_ids
    _risk_ids = build_risk_order_ids(db, current_user, f_risk)
    _q = _q.filter(Order.id.in_(_risk_ids))   # _q_stats(칩)·리스트·total 전부 동일 집합 → SSOT
```
- 위치: `_q_stats` 복제 **이전**(today 필터처럼) → 칩·리스트·total 모두 스코프.
- `_has_drill` 에 `bool(f_risk)` 추가 → 타워 대신 큐.
- redirect-to-history 차단 조건에 `f_risk` 포함(빈 결과여도 큐 유지).
- filters dict + `_chip_params`(무한스크롤 보존)에 `risk` 추가.
- `alert_type` 경로는 **그대로 유지**(단계 타일 등 타 링크 호환). `risk` 는 additive.

### 카드 href (`templates/orders/partials/dashboard_mobile_tower.html`)
변경 없음 — `url_for(..., view='queue', **g.filter)` 가 `g.filter={'risk':key}` 를 그대로 사용.

---

## P0-2. `risk_frame` 착지 헤더

### 표시 메타 (서비스 SSOT)
```python
RISK_META = {
  "construction_unready": {"icon":"🔨","tone":"red","title":"시공 임박인데 미준비",
     "defect":"시공 단계 미도달 — 출고 확인 필요","cta":"생산/출고 독촉"},
  "balance_due": {"icon":"💰","tone":"red","title":"잔금 미수 · 시공 임박",
     "defect":"시공 전 잔금 미수","cta":"고객 연락 · 입금 확인"},
  "measure_unassigned": {"icon":"📐","tone":"amber","title":"실측 예정 · 담당 미배정",
     "defect":"실측 담당자 미배정","cta":"담당 배정"},
  "drawing_stalled": {"icon":"⏳","tone":"amber","title":"도면 컨펌 48h+ 정체",
     "defect":"도면/컨펌 48시간+ 정체","cta":"컨펌 독촉"},
}
def build_risk_frame(key, count) -> dict | None: ...  # title/icon/tone/defect/cta/count/back_href
```
라우트가 `f_risk` 일 때 `risk_frame=build_risk_frame(f_risk, total_orders)` 를 템플릿에 전달.

### 파셜 `templates/orders/partials/risk_frame.html` (신규)
```
<section class="foms-risk-frame foms-risk-frame--{tone}" data-risk-frame>
  <a class="foms-risk-frame__back" href="{back}">← 위험 레이더</a>
  <div class="foms-risk-frame__head"><span icon>{icon}</span>
    <h1>{title}</h1><span class="...__count">{count}건</span></div>
  <p class="foms-risk-frame__defect">{defect}</p>
  <p class="foms-risk-frame__cta">권장 행동: {cta}</p>
</section>
```
`dashboard_mobile_v2_body.html` 큐 분기 상단에 `{% if risk_frame %}{% include 'orders/partials/risk_frame.html' %}{% endif %}`.
빈 모집단: 일반 "필터 초기화" 빈상태 대신 **`✓ 이 위험은 지금 없음`** (risk_frame일 때 전용 빈상태).

### CSS (`dashboard-control-tower.css` 또는 신규) — 토큰 사용, 인라인 금지. tone별 red/amber 좌측 강조 + back 링크.

---

## 수용 기준 (Acceptance)
1. `잔금 미수` 클릭 → **잔금 주문만** 착지(미준비와 다른 리스트).
2. **카드 count == 착지 "전체" 칩 == 렌더 리스트 수** — 4 key 전부(3숫자 SSOT).
3. `measure_unassigned` 착지 = **미배정만**(전체 실측 아님).
4. 착지 상단 `risk_frame`(카테고리·결함·마감·CTA·뒤로=레이더) 노출. 글로벌 "작업 큐" 크롬 아님.
5. 빈 위험 → `✓ 이 위험 없음`(필터 초기화 아님).
6. `alert_type` 기존 링크 무회귀. APP_OK + 전체 CI 그린 + risk 착지 구조 테스트 추가.

## 검증
- 단위: `build_risk_order_ids` 4 key 정확성(시드 케이스).
- 통합(gstack 재dogfood): construction_unready vs balance_due 착지 **상이**, 3숫자 일치, risk_frame 표시.
- 회귀: CI 메인 + UI 구조 잡, pre_push_smoke.

## 변경 파일 (예상)
- `foms/services/orders/dashboard_control_tower.py` (id 함수·`build_risk_order_ids`·`RISK_META`·`build_risk_frame`·`_risk_group` filter)
- `foms/web/orders/dashboard.py` (`f_risk`·필터·`_has_drill`·history차단·filters·risk_frame ctx)
- `templates/orders/partials/dashboard_mobile_v2_body.html` (risk_frame include·전용 빈상태·chip_params)
- `templates/orders/partials/risk_frame.html` (신규)
- `static/css/contexts/orders/dashboard-control-tower.css` (frame 스타일) + 캐시버전
- `tests/...` (risk 착지 SSOT 구조 테스트)

## 비범위 (P1/P2)
- 행별 단일 CTA 실배선(전화/재배정/입금확인), 위험 수명(확인/스누즈/위임) → P1
- `/erp/risk/<key>` 전용 view, 추천 배정, 일괄 액션 → P2
