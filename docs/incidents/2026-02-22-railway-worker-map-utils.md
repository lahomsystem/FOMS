# 2026-02-22 Railway Worker·지도변환·chat utils 이슈 보고

> GDM 검토 결과 요약. 원인·조치안·진행상황.

---

## 1. 원격 스테이징에서 지도 변환 전체 실패

### 발견
- **로컬**: 지도 변환 정상
- **원격 (lahom-dev.up.railway.app)**: 전체 실패

### 원인
- `erp_map.py`가 `enqueue_geocode_order_address`로 RQ 큐에 작업을 넣음
- **Worker가 offline** → 큐에 들어간 작업을 처리할 프로세스가 없음
- (구) `queue.py`: `USE_RQ_WORKER=1` + `REDIS_URL` 둘 다 있어야 enqueue → FOMS 웹에 `USE_RQ_WORKER=0`이면 enqueue 불가
- FOMS 웹 서비스에 `USE_RQ_WORKER=1`이 적용되면 enqueue 성공 → worker 미동작 시 작업 미처리 → 지도 변환 실패

### 조치안 (수정 반영)
**A. queue.py 수정**  
- `get_rq_queue()`: `REDIS_URL`만 있으면 큐 반환 (enqueue 가능)
- `USE_RQ_WORKER`는 `start.sh` 전용 — 웹은 gunicorn, Worker만 rq 실행

**B. FOMS 웹 서비스 Variables**
- `REDIS_URL`: Redis 서비스에서 공유 (필수, enqueue용)
- `USE_RQ_WORKER`: **0** 또는 미설정 (gunicorn 실행, 502 방지)

**C. Worker 서비스 Variables**
- `USE_RQ_WORKER`: **1**
- `REDIS_URL`: Redis 서비스에서 공유

이렇게 하면 지도 로드 시 geocode job이 enqueue되고, Worker가 처리 후 새로고침 시 좌표가 표시됩니다.

**D. Worker 서비스 정상 기동**  
- Worker online이면 RQ enqueue 방식 그대로 사용 가능 (아래 §2 참고)

---

## 2. Railway Worker 서비스 Offline

### 발견
- Worker 서비스 등록됨, 상태: **Service is offline**

### 점검 항목
| 항목 | 확인 위치 | 요구값 |
|------|----------|--------|
| Config Path | Worker > Settings | `railway-worker.toml` |
| REDIS_URL | Worker > Variables | Redis 서비스에서 공유 |
| 소스 연결 | Worker > Settings | FOMS와 동일 GitHub repo |
| Build/Start | Deploy 로그 | `rq worker default --url $REDIS_URL` 실행 |

### 조치안
1. Worker > Settings > **Config Path**: `railway-worker.toml` 설정
2. Worker > Variables: **REDIS_URL** 존재 확인 (Redis 서비스에서 참조)
3. Worker > Settings: FOMS와 같은 GitHub 저장소/브랜치 연결
4. Deploy 로그에서 `rq worker default` 시작 메시지 확인

### `railway-worker.toml` 내용
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "rq worker default --url $REDIS_URL"
```

---

## 3. chat/utils.py basedpyright 타입 에러 (수정 완료)

### 발견
- **51행**: `Invalid conditional operand of type "Column[str]"` — Column을 boolean으로 사용
- **52행**: `Cannot assign to attribute "thumbnail_url"` — str을 `Column[str]`에 할당

### 수정 내용
- **51행**: `not attachment.thumbnail_url` →  
  `not (getattr(attachment, 'thumbnail_url', None) or '')`  
  (Column boolean 사용 제거)
- **52행**: `attachment.thumbnail_url = ...` →  
  `setattr(attachment, 'thumbnail_url', build_file_view_url(thumbnail_key))`  
  (타입 검사 회피, 런타임 동작 유지)

### 파일
- `apps/api/chat/utils.py` 51–52행

---

## 다음 할 일

1. **지도 변환**: queue.py 반영 후 배포 — FOMS 웹 `REDIS_URL` + `USE_RQ_WORKER=0`, Worker `USE_RQ_WORKER=1` + `REDIS_URL`
2. **Worker 활성화**: §2 점검 항목에 따라 설정 후 재배포
3. **chat utils**: 이미 수정 반영, 기존 동작 유지
