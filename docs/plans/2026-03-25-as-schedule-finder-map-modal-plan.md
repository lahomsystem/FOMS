# AS 일정찾기 지도 거리 측정 모달

**날짜**: 2026-03-25
**작업 유형**: 기능 추가 (UI + 백엔드 소규모 변경)
**요청**: AS 일정찾기 결과 건에 지도 아이콘 추가, 클릭 시 기준주소와 결과 건 간 경로/거리를 지도 모달로 표시

## 1. 배경

AS 대시보드의 "가까운 일정 찾기" 모달은 현재 텍스트 리스트로만 결과를 보여줌.
사업주가 기준주소와 각 결과 건 사이의 실제 경로/거리/소요시간을 **지도 위에서 시각적으로** 확인하고 싶어함.

실측 대시보드(`map_view.html`)에 이미 동일한 기능이 있음:
- Leaflet.js + OpenStreetMap 타일 기반 지도
- `/api/calculate_route` API로 카카오 내비게이션 경로 계산
- 두 마커 간 Polyline + 경로 정보 패널(거리/시간/통행료)

## 2. 핵심 전략

**기존 모듈 최대 재사용, 신규 API/라이브러리 도입 없음**

| 재사용 대상 | 위치 | 용도 |
|------------|------|------|
| `/api/calculate_route` API | `apps/api/erp_map.py:591-606` | 두 좌표 간 경로/거리/시간/통행료 계산 |
| `FOMSAddressConverter.calculate_route()` | `foms_address_converter.py:403-464` | 카카오 내비게이션 REST API 호출 |
| 경로 정보 패널 UI | `foms_map_generator.py:467-477` | 출발/도착/거리/시간/통행료 HTML 패턴 |
| Polyline 스타일 | `foms_map_generator.py:452-456` | `color: #ff4757, weight: 5, opacity: 0.8` |
| Leaflet.js 라이브러리 | `map_view.html` (Folium 경유) | 지도 렌더링 — AS 대시보드에서는 CDN 직접 로드 |

**신규 API 키 불필요** — 카카오 REST API 키(`map_config.py`)는 백엔드에서만 사용, 프론트는 Leaflet + OpenStreetMap(무료).

## 3. 변경 파일

| # | 파일 | 변경 유형 | 변경 내용 |
|---|------|-----------|-----------|
| 1 | `apps/api/orders.py` | 수정 (2줄) | `route_item()`에서 `_lat`/`_lng` pop 대신 `lat`/`lng`로 이름 변경하여 응답에 유지 |
| 2 | `templates/erp_as_dashboard.html` | 수정 | Leaflet CDN 로드 + 지도 모달 HTML + renderResults 아이콘 + JS 함수 |
| 3 | `static/css/erp-pro.css` | 추가 | `.schedule-map-container`, `.schedule-map-route-info` 등 전용 CSS 클래스 |

## 4. 상세 구현

### 4-1. 백엔드: 좌표 데이터 프론트 전달 (orders.py)

**위치**: `apps/api/orders.py` — `route_item()` 함수 (416-418행)

```python
# Before (현재 — 좌표 제거)
item.pop('_lat', None)
item.pop('_lng', None)

# After (변경 — 좌표 유지, 이름 변경)
item['lat'] = item.pop('_lat', None)
item['lng'] = item.pop('_lng', None)
```

**영향 범위**: `/api/orders/nearby` 응답의 각 결과 아이템에 `lat`, `lng` 필드 추가.
기존 프론트엔드 `renderResults()`는 알려지지 않은 필드를 무시하므로 **하위 호환성 유지**.

### 4-2. 프론트엔드: Leaflet.js CDN 로드

**위치**: `templates/erp_as_dashboard.html` — head 또는 body 하단

```html
<!-- Leaflet.js (지도 모달용) -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
```

### 4-3. 프론트엔드: 지도 모달 HTML

**위치**: `<!-- Schedule Search Modal -->` 블록 닫힘(`</div>` 572행) 바로 아래에 추가

```html
<!-- Schedule Map Modal -->
<div class="modal fade" id="scheduleMapModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-lg modal-fullscreen-md-down">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">
          <i class="fas fa-route"></i> 기준 ↔ 시공지 거리 측정
        </h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body p-0">
        <!-- 지도 영역 — 높이는 erp-pro.css .schedule-map-container에서 지정 -->
        <div id="scheduleMapContainer" class="schedule-map-container"></div>
        <!-- 경로 정보 패널 -->
        <div id="scheduleMapRouteInfo" class="p-3">
          <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm me-2"></div>경로 계산 중...
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

### 4-3a. CSS 클래스 추가 (erp-pro.css)

```css
/* AS 일정찾기 지도 모달 */
.schedule-map-container {
  height: 400px;
  width: 100%;
}

.schedule-map-route-info {
  background: #d4edda;
  padding: 15px;
  border-radius: 5px;
  border-left: 4px solid #28a745;
}

.schedule-map-route-info h6 {
  margin-bottom: 0.5rem;
}

/* Leaflet z-index가 Bootstrap 모달 내부에서 정상 작동하도록 보정 */
#scheduleMapModal .leaflet-pane { z-index: 400; }
#scheduleMapModal .leaflet-control { z-index: 800; }
#scheduleMapModal .leaflet-popup { z-index: 900; }
```

### 4-4. 프론트엔드: 결과 건에 지도 아이콘 추가

**위치**: `renderResults()` 함수 (1305-1351행) — 하단 "바로가기" 옆

현재 코드:
```html
<div class="d-flex justify-content-end align-items-end mt-1">
  <small class="text-primary fw-bold"><i class="fas fa-external-link-alt"></i> 바로가기</small>
</div>
```

변경:
```html
<div class="d-flex justify-content-between align-items-end mt-1">
  ${(item.lat && item.lng) ? `
    <button type="button" class="btn btn-sm btn-outline-info schedule-map-btn"
      data-lat="${esc(item.lat)}" data-lng="${esc(item.lng)}"
      data-address="${esc(item.address)}" data-name="${esc(item.customer_name)}"
      data-score-text="${esc(item.score_text || '')}">
      <i class="fas fa-map"></i> 지도
    </button>` : '<span></span>'}
  <small class="text-primary fw-bold"><i class="fas fa-external-link-alt"></i> 바로가기</small>
</div>
```

**주의**: 지도 버튼은 `<button>`이므로 부모 `<a>` 태그의 링크 이동을 `e.stopPropagation()` + `e.preventDefault()`로 차단해야 함.

### 4-5. 프론트엔드: 지도 모달 JS

#### 4-5a. ref_lat/ref_lng 스코프 변수 저장

IIFE 내부에 기준 좌표 + 주소를 보관할 변수를 선언하고, `runSearch()` 응답 시 저장한다.

```javascript
// IIFE 내부 상단 (_lists, _searchState 옆)
let _refLat = null, _refLng = null, _refAddress = '';

// runSearch() 내부 — _lists 할당 직후 (1396행 부근)
_refLat = data.ref_lat || null;
_refLng = data.ref_lng || null;
_refAddress = address;  // runSearch의 첫 번째 인자
```

#### 4-5b. 지도 버튼 이벤트 핸들러

```javascript
// 이벤트 위임 — <a> 태그 링크 이동 차단 필수
document.body.addEventListener('click', function(e) {
  const btn = e.target.closest('.schedule-map-btn');
  if (!btn) return;
  e.stopPropagation();
  e.preventDefault();

  const targetLat = parseFloat(btn.dataset.lat);
  const targetLng = parseFloat(btn.dataset.lng);
  const targetAddress = btn.dataset.address;
  const targetName = btn.dataset.name;
  const scoreText = btn.dataset.scoreText || '';

  if (!_refLat || !_refLng) return;
  openScheduleMap(_refAddress, _refLat, _refLng, targetLat, targetLng, targetAddress, targetName, scoreText);
});
```

#### 4-5c. 핵심 함수 `openScheduleMap()`

```
1. scheduleMapModal.show()
2. shown.bs.modal 이벤트에서 Leaflet 지도 초기화 (OpenStreetMap 타일)
   - 모달이 완전히 열린 후 초기화해야 지도 크기가 정확함
3. 기준주소 마커 (빨간색, popup: 기준주소) 배치
4. 시공지 마커 (초록색, popup: 고객명 + 주소) 배치
5. map.fitBounds() — 두 마커 모두 보이게 자동 줌 (padding: [50, 50])
6. /api/calculate_route 호출 (기존 API 그대로)
7. 성공 시:
   - route_coords로 Polyline 그리기 (color: #ff4757, weight: 5)
   - 경로 정보 패널 렌더링 (출발/도착/거리/시간/통행료)
8. 실패 시:
   - 직선거리(score_text) + "경로 계산 실패" 메시지 표시
9. hidden.bs.modal 이벤트에서:
   - map.remove() 호출 (메모리 정리)
   - _scheduleMap = null 초기화
```

#### 4-5d. 경로 캐싱 (rate limiting 대응)

동일 좌표 쌍에 대한 반복 API 호출을 방지하기 위해 프론트엔드 메모이제이션을 적용한다.

```javascript
const _routeCache = new Map();  // key: "lat1,lng1-lat2,lng2" → value: routeData

function _routeCacheKey(lat1, lng1, lat2, lng2) {
  return `${lat1.toFixed(6)},${lng1.toFixed(6)}-${lat2.toFixed(6)},${lng2.toFixed(6)}`;
}
```
- `/api/calculate_route` 호출 전 캐시 확인 → hit 시 API 생략
- 카카오 내비 API 일일 할당량 보호 (동일 좌표 쌍 반복 클릭 시)

### 4-6. 마커 스타일

| 마커 | 색상 | 라벨 | 참고 |
|------|------|------|------|
| 기준주소 (출발) | 빨간색 `#ff6b6b` | 기준 주소 텍스트 (짧게 자름) | 실측 지도 출발 마커와 동일 |
| 시공지 (도착) | 초록색 `#4caf50` | 고객명 | 실측 지도 도착 마커와 동일 |

### 4-7. 경로 정보 패널 HTML (실측 지도 패턴 재사용)

인라인 스타일 대신 `erp-pro.css`의 `.schedule-map-route-info` 클래스를 사용한다.

```html
<div class="schedule-map-route-info">
  <h6><i class="fas fa-car-side me-1"></i> 경로 정보</h6>
  <div class="mb-1"><strong>출발:</strong> {기준주소}</div>
  <div class="mb-1"><strong>도착:</strong> {시공지주소}</div>
  <div class="mb-1"><strong>거리:</strong> {distance_text}</div>
  <div class="mb-1"><strong>소요시간:</strong> {duration_text}</div>
  <div><strong>통행료:</strong> {toll_text}</div>
</div>
```

## 5. 데이터 흐름도

```
[AS 대시보드] 일정찾기 버튼 클릭
    │
    ▼
[scheduleSearchModal] 기준주소로 /api/orders/nearby 호출
    │
    ▼
[백엔드] 결과 아이템에 lat/lng 포함하여 응답  ← Step 4-1 변경
    │
    ▼
[renderResults()] 각 건에 "지도" 버튼 표시     ← Step 4-4 변경
    │
    ▼ (지도 버튼 클릭)
    │
[scheduleMapModal] Leaflet 지도 + 두 마커 표시
    │
    ▼
[/api/calculate_route] 기존 API로 경로 계산    ← 기존 코드 재사용
    │
    ▼
[Polyline + 경로 정보 패널] 지도 위에 표시
```

## 6. 위험 요소 및 대응

| 위험 | 확률 | 대응 |
|------|------|------|
| Leaflet CDN 로드로 AS 대시보드 초기 로딩 느려짐 | 낮음 | Leaflet CSS/JS는 각각 40KB/150KB로 경량. `defer` 속성 추가 |
| `/api/calculate_route` 호출 실패 (카카오 API 장애) | 낮음 | 직선거리 + "경로 계산 실패" 메시지로 fallback |
| 좌표 없는 결과 건 (geocoding 실패) | 중간 | `lat`/`lng`가 null이면 지도 버튼 미표시 |
| 모달 열고 닫기 반복 시 지도 인스턴스 메모리 누수 | 중간 | `hidden.bs.modal` 이벤트에서 `map.remove()` 호출 |
| 카카오 내비 API 일일 할당량 소진 | 중간 | 동일 좌표 쌍 프론트 캐싱(`_routeCache`) + 429 응답 시 직선거리 fallback |
| Leaflet z-index와 Bootstrap 모달 z-index 충돌 | 낮음 | `erp-pro.css`에서 `#scheduleMapModal .leaflet-*` z-index 명시적 지정 |
| 두 모달 동시 열림 (scheduleSearchModal + scheduleMapModal) | 낮음 | Bootstrap은 다중 모달을 지원하며, 지도 모달이 위에 쌓임. 닫으면 일정 모달로 복귀 |

## 7. 테스트 체크리스트

- [ ] AS 대시보드 정상 로드 확인 (Leaflet CDN 추가 후)
- [ ] 일정찾기 결과 건에 "지도" 버튼 표시 확인
- [ ] 좌표 없는 건에는 지도 버튼 미표시 확인
- [ ] 지도 버튼 클릭 시 모달 열림 + 두 마커 표시 확인
- [ ] 경로선(Polyline) 정상 그려지는지 확인
- [ ] 경로 정보 패널(거리/시간/통행료) 표시 확인
- [ ] 모달 닫기 후 재열기 시 정상 동작 확인
- [ ] 모바일에서 모달 전체화면 표시 확인
- [ ] "바로가기" 링크가 지도 버튼과 겹치지 않는지 확인
- [ ] 지도 버튼 클릭 시 부모 `<a>` 태그 링크 이동 차단 확인
- [ ] 동일 좌표 쌍 반복 클릭 시 캐시 hit 확인 (API 재호출 안 함)
- [ ] 지도 모달 닫기 후 일정찾기 모달로 정상 복귀 확인

## 8. 감리 결과 반영 이력

| # | 감리 지적 | 심각도 | 반영 내용 |
|---|-----------|--------|-----------|
| 1 | ref_lat/ref_lng 스코프 저장 코드 미비 | HIGH | 4-5a절에 변수 선언 + runSearch 내 할당 코드 추가 |
| 2 | 인라인 스타일 사용 (CLAUDE.md 위반) | HIGH | 4-3a절에 erp-pro.css 전용 클래스 추가, 4-7절 수정 |
| 3 | scheduleSearchModal 행 번호 불일치 | MEDIUM | 주석 기준 위치로 수정 |
| 4 | 이벤트 버블링 처리 누락 | MEDIUM | 4-5b절에 stopPropagation + preventDefault 명시 |
| 5 | 카카오 API rate limiting 대응 부재 | MEDIUM | 4-5d절에 프론트 캐싱 추가, 위험 요소 표 보강 |
| 6 | Leaflet 컨테이너 인라인 스타일 | LOW | CSS 클래스로 대체 |
| 7 | z-index 충돌 미언급 | LOW | CSS 보정 코드 + 위험 요소 추가 |
