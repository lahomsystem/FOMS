# 2026-02-23 503 + SSL unexpected eof (Cloudflare 54113)

> **증상**: 접속 시 503, `error:0A000126:SSL routines::unexpected eof while reading`, Cloudflare Error 54113, `cache-icn1450055-ICN`  
> **의미**: Cloudflare 에지(ICN) ↔ 오리진(Railway) 구간에서 TLS 핸드셰이크 도중 연결이 끊김.

---

## 1. 오류 해석

| 항목 | 의미 |
|------|------|
| **503** | 서비스 일시 불가 (오리진 응답 불가 또는 프록시 구간 오류) |
| **0A000126 / unexpected eof** | OpenSSL: 상대가 TLS 완료 전에 연결을 닫음 |
| **Error 54113** | Cloudflare 내부 코드 (오리진 연결 실패 관련) |
| **cache-icn1450055-ICN** | Cloudflare ICN(인천/서울) PoP에서 발생 |

**흐름**: 사용자 → Cloudflare(ICN) → **Railway(오리진)**. Cloudflare가 Railway로 HTTPS 연결을 시도하다가, Railway 쪽에서 연결을 조기 종료해 “unexpected eof”가 발생한 상황으로 해석 가능.

---

## 2. 가능 원인

1. **Railway 앱 일시 중단/콜드스타트**  
   - 유휴 시 슬립 → 첫 요청에서 연결 끊김 또는 지연 후 타임아웃  
2. **Railway 워커 재시작**  
   - 배포/재시작 중에는 기존 연결이 끊어질 수 있음  
3. **오리진 타임아웃**  
   - Cloudflare → Railway 구간 대기 시간이 Railway/네트워크 타임아웃보다 길어서 끊김  
4. **네트워크 불안정**  
   - 일시적 패킷 손실로 TLS 핸드셰이크 실패  

---

## 3. 권장 대응 (순서대로)

### 3.1 즉시

- **재시도**  
  - 503/54113은 일시적일 수 있음. 몇 초~1분 후 새로고침 또는 재접속.
- **Railway 대시보드 확인**  
  - [Railway 프로젝트](https://railway.com/project/cbe0af66-875b-460c-88f6-780dd705f45c) → FOMS Web 서비스  
  - **Deployments**: 최근 배포/실패 여부  
  - **Metrics**: CPU/메모리 스파이크, 재시작  
  - **Logs**: `Worker graceful timeout`, `SIGTERM`, `Connection reset` 등 검색  

### 3.2 Cloudflare 사용 시 (커스텀 도메인 + Cloudflare 프록시)

- **SSL/TLS 모드**  
  - **Full** 또는 **Full (strict)** 권장. 오리진(Railway)이 유효한 TLS를 제공해야 함.  
- **오리진 연결**  
  - Railway 기본 URL(`*.up.railway.app`)은 TLS 지원. 커스텀 도메인만 Cloudflare에 연결했다면, DNS에서 Railway 쪽으로 오리진이 올바르게 설정돼 있는지 확인.  
- **타임아웃**  
  - Cloudflare 무료 플랜은 오리진 타임아웃 100초. 장시간 요청은 Railway/앱 쪽 타임아웃과 맞출 것.  

### 3.3 Railway 쪽 점검

- **gunicorn/앱 타임아웃**  
  - `railway.toml` / Procfile: `--timeout 120` 등으로 충분한지 확인.  
- **재시작/에러 로그**  
  - `gevent` 관련 오류, DB/Redis 연결 실패가 반복되면 503으로 이어질 수 있음.  

---

## 4. 참고

- **Cloudflare 상세 설정**: `docs/guides/CLOUDFLARE_SETUP.md` (사이트 추가, DNS, SSL/TLS, R2 CORS)
- Cloudflare 503: <https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-503/>  
- FOMS Railway 배포: `docs/guides/DEPLOY_NOTES.md`, `docs/CURRENT_STATUS.md`  
- 이전 Railway/gevent 사고: `docs/context/INCIDENT_RAILWAY_GEVENT_SOCKET_2026-02-20.md`
