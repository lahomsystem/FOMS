# 네트워크 tail 근본 처방 — Cloudflare 엣지 (레버 2)

## 배경 (측정된 근본원인)

- 탭 로딩 간헐 2-9초 스파이크 = **한국 사용자 ↔ Railway 싱가포르** 왕복 경로. 코드/서버/DB 아님.
- 증거: fragment TTFB 5-8s인데 서버 렌더(`X-FOMS-EPT-B7-RENDER-MS`)는 11-260ms. 3KB 정적파일도 스파이크 → 순수 네트워크 경로. (참조: `project_tail_spike_network_rca`)
- Railway 아시아 리전 = 싱가포르 단일 → 리전 이전 불가.
- 클라이언트 prefetch/warm-nav(`erp-shell.js` EPT-B6)는 이미 최적 구현·baseline과 동일. 캐시 가능 경로는 이미 즉각. 남은 지연 = 첫 로드·캐시불가(measurement)·tail 스파이크 = 전부 경로 문제.

## 앱측 준비 상태 (완료 — 추가 코드 불필요)

Cloudflare를 앞단에 놓아도 **교차유저 유출 없음**이 이미 보장됨:

- 인증 fragment: `Cache-Control: no-store` — `foms/api/fragment.py:65`
- 파일 라우트: `no-store` — `foms/api/files/routes.py:34`
- 버전드 css/js(`?v=`): `no-cache` — `foms/platform/app_factory.py`
- 전역 after_request는 로깅만 — 허용적 캐시 없음

→ CF 기본 캐시레벨(origin 헤더 존중)에서 인증 콘텐츠는 자동 BYPASS. **"Cache Everything" 페이지룰 금지.**

## CF가 주는 이득 (콘텐츠 캐시가 아니라 커넥션·라우팅)

거의 모든 응답이 no-store/no-cache라 엣지 캐시는 거의 안 함. 이득은 **경로**에서 온다:

1. **TLS 종단이 서울 엣지(ICN)** — 핸드셰이크가 근거리(~10-30ms)에서. 싱가포르(~70-90ms) 대비 신규 커넥션당 수백 ms 절약.
2. **HTTP/3(QUIC)** 클라이언트↔엣지 — 0-RTT 재개, 손실 회복(모바일 유리).
3. **origin 웜 keep-alive 풀** — 엣지→싱가포르 커넥션 재사용 → 대부분 요청이 origin TCP+TLS 핸드셰이크 스킵. **콜드커넥션 스파이크 제거.**
4. **Argo Smart Routing(유료, tail 킬러)** — 엣지→origin을 공용 인터넷 대신 CF 백본 최적경로로 → 2-9s 라우팅/혼잡 tail 안정화. **이게 핵심.**

## 실행 런북 (사용자 대시보드 작업)

전제: 도메인 1개(예: `app.lahom.kr`), Cloudflare 계정(R2로 이미 보유), Railway 대시보드.

1. **Cloudflare에 도메인 추가** (이미 있으면 스킵). 네임서버를 CF로.
2. **Railway 커스텀 도메인 연결**: 각 web 서비스(FOMS-PRODUCTION=web, FOMS-DEV=FOMS) Settings → Networking → Custom Domain에 `app.lahom.kr`(운영), `dev.lahom.kr`(스테이징) 추가. Railway가 준 CNAME 타깃 확보.
3. **CF DNS 레코드**: `app` / `dev` → Railway CNAME 타깃, **Proxy status = Proxied(주황 구름) ON**.
4. **SSL/TLS 모드 = Full (strict)** (Railway가 유효 TLS 제공).
5. **HTTP/3 ON**, **0-RTT ON**, **Always Use HTTPS ON**.
6. **캐시 = 기본 유지**(Standard). **"Cache Everything" 룰 만들지 말 것**(인증 콘텐츠 유출 방지). 원하면 `/static/*` 중 이미지·폰트만 별도 캐시룰(css/js는 no-cache라 어차피 bypass).
7. **WebSocket**: CF는 WebSocket 기본 지원 — Socket.IO(`/socket.io/`) 통과 확인. Network 탭에서 101 Switching Protocols 확인.
8. **Argo Smart Routing 활성화**(Traffic → Argo). 유료지만 tail 스파이크의 실질 처방. 월 비용 대비 체감 개선 A/B로 판단.
9. **앱 도메인 전환**: 사용자·북마크를 `*.up.railway.app` → `app.lahom.kr`로. (기존 railway 도메인은 유지, 점진 전환.)

## 검증 (전환 후 실측 — 필수)

같은 도구로 CF 도메인 vs railway 도메인 TTFB tail 비교:

```powershell
# 한국 사용자 PC에서 (실경로)
$env:FOMS_STAGING_USERNAME="..."; $env:FOMS_STAGING_PASSWORD="..."
python tools/perf/fragment_tail_ttfb_diagnostic.py https://dev.lahom.kr https://lahom-dev.up.railway.app
```

- 기대: CF 경유 쪽 **p95 tail 뚜렷 감소**(특히 Argo ON), warm median은 비슷하거나 소폭 개선.
- 서버 렌더(`X-FOMS-EPT-B7-RENDER-MS`)는 불변(경로만 바뀜) — 정상.

## 최종 옵션 (haul 완전 제거 — 대공사, 지금 아님)

tail을 근본 소거하려면 **origin을 한국/일본 리전**에 두는 것. Railway는 SG 단일이라 불가 → Fly.io(NRT 도쿄)/AWS ap-northeast-2(서울) 등으로 이전 시 왕복 자체가 사라짐. DB(Postgres)·R2·배포 파이프라인 동반 이전 필요 → 별도 RPI Spec. CF+Argo로 충분치 않을 때만 검토.
