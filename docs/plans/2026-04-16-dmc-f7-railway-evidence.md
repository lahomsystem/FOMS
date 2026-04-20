# DMC-F7 / DMC-C2 — Railway·prod-like 운영 증거 (Dashboard micro-cache)

**상태:** `PENDING` — 본 파일에 **실제 로그·수치를 붙이기 전까지** 계획서 §4.5·§5의 Railway·prod 실측 항목은 완료로 표시하지 않는다.

**블로커 (2026-04-16):** 로컬 `railway status` → `Unauthorized. Please run railway login again.` — CI/에이전트 환경에서 운영 로그를 인용할 수 없음. **추정·샘플 숫자 기입 금지.**

---

## 1. 수집 절차 (운영자)

1. `railway login` 후 프로젝트 링크: `cd <FOMS_REPO_ROOT>; railway link` (이미 링크됨이면 생략).
2. Web 서비스 로그 스트림에서 아래 패턴 검색:
   - `[DashCache] page=`
   - `result=hit` | `result=miss` | `result=bypass`
   - `compute_ms=`
3. **miss 1건**과 **hit 1건** 이상을 같은 또는 인접 요청에서 확보 (가능하면 동일 `page`·`slice`).
4. (선택) Railway Metrics 또는 앞단 프록시에서 해당 라우트 **p50/p95** 또는 대표 응답 시간 스냅샷.
5. 아래 표에 **원문 로그 줄**과 **타임스탬프(UTC 또는 KST 명시)** 를 붙여 넣는다.

---

## 2. 로그 형식 (코드 기준)

`foms/services/common/dashboard_cache.py` — `get_or_compute_dashboard_slice`:

- Hit: `[DashCache] page=%s slice=%s result=hit compute_ms=0 key_suffix=%s cache=on`
- Miss: `[DashCache] page=%s slice=%s result=miss compute_ms=%s key_suffix=%s cache=on`
- Bypass: `[DashCache] page=%s slice=%s result=bypass compute_ms=%s key_suffix=%s cache=off` (또는 Redis 미사용 시 `cache=off`)

---

## 3. 라우트 식별 (대시보드)

| 페이지 | Blueprint·경로 (참고) |
|--------|---------------------|
| Orders ERP dashboard | `/erp/dashboard` 등 — `foms/web/orders/dashboard.py` |
| Measurement | `/erp/measurement` — `foms/web/measurement/dashboard.py` |
| Shipment | `/erp/shipment` — `foms/web/shipment/dashboard.py` |

정확한 경로는 배포 브랜치의 `url_map` 또는 앱 라우트 목록으로 확인.

---

## 4. 증거 테이블 (붙여넣기 전까지 비움)

| 항목 | 값 |
|------|-----|
| 증거 수집 시각 (timezone) | *(pending)* |
| 배포 환경 | *(e.g. Railway production / deploy)* |
| `FOMS_DASHBOARD_MICRO_CACHE_ENABLED` | *(pending)* |
| `REDIS_URL` 존재 여부 | *(pending)* |

### 4.1 Cache miss 샘플 (1건 이상)

```
(paste raw log line here)
```

### 4.2 Cache hit 샘플 (1건 이상)

```
(paste raw log line here)
```

### 4.3 Latency / 대표 타이밍 (선택)

| Route / page | Before (ms) | After (ms) | 출처 (metrics URL·스크린샷·로그) |
|--------------|-------------|------------|----------------------------------|
| *(pending)* | | | |

---

## 5. 체크리스트

- [ ] miss 로그 1건 이상 (원문)
- [ ] hit 로그 1건 이상 (원문)
- [ ] `compute_ms` 필드 포함 확인
- [ ] route·페이지 식별 가능
- [ ] (선택) before/after 또는 반복 요청 비교 근거

위 체크가 모두 채워지면 `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md` §4.5·§5의 Railway 관련 체크박스를 `[x]`로 옮길 수 있다.
