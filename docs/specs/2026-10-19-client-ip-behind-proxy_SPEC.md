# 프록시 뒤에서 앱이 보는 손님 IP 바로잡기 — SPEC (2026-10-19)

## 목적
같은 손님의 연속 요청은 앱에서도 같은 IP(`request.remote_addr`)로 보이게 한다. 그래야 IP 를 키로 쓰는 한도(로그인 (아이디, IP) 잠금, 로그인 POST 볼륨 한도 `FOMS_LOGIN_RATE_LIMIT`, 가입·비밀번호 재설정 한도, Flask-Limiter 기본 한도의 IP 단계)가 뜻대로 작동한다. 이번 커밋은 **어느 헤더 모양에서도 안전한 부분**만 바꾸고, 앱이 고르는 IP 자체를 바꾸는 일은 스테이징 실측 뒤로 미룬다.

## 증상
- 2026-10-19 스테이징(lahom-dev.up.railway.app), 한 PC 에서 없는 아이디로 `POST /login` 21회 → (아이디, IP) 임계 8 에서는 한 번도 안 잠기고, 계정 카운터(IP 무관, 임계 20)만 20번째에 잠겼다.
- 같은 날 로컬(같은 IP)에서는 8번째에 잠긴다.

## 지금 구조
줄 번호는 변경 전(origin/deploy `4a967c466`) 기준.
- ProxyFix 는 `X-Forwarded-For` 를 오른쪽에서 `FOMS_TRUSTED_PROXY_HOPS`(기본 1)번째 항목으로 `REMOTE_ADDR` 를 덮는다. `x_proto`·`x_host`·`x_prefix` 도 1로 믿는다 — `foms/platform/app_factory.py:168-201`. 홉 수는 한 번도 실측되지 않았다(`docs/harness/foms_bugfix_progress_ledger.md:33` "Railway hop 실측 merge-gate").
- 적용 조건은 `FLASK_ENV == production` 또는 `RAILWAY_ENVIRONMENT == production` 또는 `TRUST_PROXY` — `app_factory.py:226-229`, `:267-269`. 스테이징 프로젝트도 환경 이름이 production 이라 운영과 똑같이 적용된다. 두 서버 모두 `TRUST_PROXY` 는 없다.
- werkzeug ProxyFix(설치 2.3.8)는 항목 수가 홉 수보다 적으면 덮지 않고 소켓 상대 주소(Railway 내부 주소)를 그대로 둔다. 항목이 IP 모양이 아니어도 그대로 넣는다.
- IP 를 쓰는 곳: 로그인 버킷·잠금 키 `foms/services/security/auth_rate/login_lockout.py:192`, Flask-Limiter 기본 키의 마지막 단계 `foms/services/rate_limit.py:215`, 로그인 볼륨 한도 `rate_limit.py:179-183`(키 = 로그인 버킷 키), 가입·비밀번호 재설정 한도 `foms/platform/realtime.py:182-196`, WAM 수집 `foms/api/channel/channel_wam.py:49`, 감사 기록의 `ip` 칸 여러 곳.
- 로그인 잠금 저장소는 limiter 저장소(스테이징·운영 web 은 Redis)라 워커 2개(`start.sh:27`)가 같은 카운터를 본다.
- gunicorn 접근 로그(`start.sh:27` `--access-logfile -`)의 첫 칸 `h` 는 `environ['REMOTE_ADDR']` 다(gunicorn `glogging.py` `atoms`, 로컬 설치 25.0.1 로 확인. `requirements.txt` 는 `>=22.0.0` 이라 서버 버전은 빌드 시점 최신). ProxyFix 가 같은 environ 을 제자리에서 고치므로 **접근 로그 첫 칸 = 앱이 고른 IP** 다. gunicorn 자체는 `X-Forwarded-For` 로 `REMOTE_ADDR` 를 바꾸지 않는다.

## 원인 후보와 증거
1. **확정 — 앱이 고른 IP 가 연속 요청 사이에 바뀌었다.** 계정 카운터가 정확히 20번째에 잠겼다는 것은 20건이 모두 같은 저장소의 같은 카운터에 쌓였다는 뜻이다. (아이디, IP) 카운터도 같은 저장소를 쓰므로, IP 가 고정이었다면 8번째에 잠겼어야 한다. 로그인 볼륨 한도(분당 10)도 같은 IP 키라 안 걸렸다. 워커가 카운터를 나눠 가진 경우는 계정 카운터가 20에 닿은 것으로 배제된다.
2. **강한 후보(미확정) — Railway 가 붙이는 `X-Forwarded-For` 가 항목 2개이고, 홉 1 설정이 손님이 아니라 오른쪽 끝 중간 주소를 고른다.**
   - Railway 공식 문서(Public Networking › Specs & Limits)는 `X-Real-IP` 만 "손님의 원격 IP" 로 적고, `X-Forwarded-For` 는 적지 않는다(규칙 보장 없음).
   - Railway 직원(phin, 2026-06-12): "We do strip X-Forwarded-For at our edge and ensure clients cannot overwrite it." / "The first value of the X-Forwarded-For is the real connecting IP." / "You may see another hop as the request is forwarded through our network." / "X-Real-IP ... serves as a single source of truth for the connecting IP." (station `security-critical-questions-on-edge-prox-8fddd775`)
   - 다른 사용자 실측(2026-09-08~09): 손님이 보낸 `X-Forwarded-For` 는 앱에 안 닿고, 앱이 받은 값은 **[실제 손님, 중간 주소] 2개**였다. 오른쪽 끝은 CDN77/Datacamp(152.233.x) 같은 CDN 대역이었다. `X-Real-IP` 는 실제 손님. 소켓 상대는 100.0.0.0/8. "trust proxy = 1 은 손님이 아니라 인프라 홉을 읽는다"(station `does-the-edge-strip-client-x-forwarded-f-613e5cb6`).
   - 2026-03-26 회귀: `X-Forwarded-For`·`X-Real-IP` 에 Fastly 엣지 주소(167.82.231.36, 167.82.231.24, 140.248.75.140 — 요청마다 다름)가 들어왔고 Railway 가 당일 고쳤다고 답했다(station `x-forwarded-for-contains-fastly-cdn-i-ps-f3039f98`). CDN 경유 요청에서 `X-Real-IP` 가 CDN 주소가 되는 버그를 추적 중이라는 직원 답변도 인용돼 있다(위 613e5cb6 글).
   - 이 모양이면 홉 1 = 오른쪽 끝 = 엣지/CDN 노드 주소다. 노드가 여럿이라 요청마다 다른 값이 나오고, 21건이 노드 몇 개에 흩어지면 어느 하나도 8에 닿지 않는다. 증상과 맞는다.
   - 확정하려면 실제 스테이징 요청의 헤더 모양(항목 수와 위치)을 봐야 한다. 이 작업은 실서버를 보지 않았다.
3. **약한 후보 — 손님 PC 의 출구 IP 가 실제로 바뀐다**(회선 2개 부하 분산, 이동통신 등). 21건에서 어느 IP 도 8번을 못 채우려면 출구가 3개 이상이어야 해 흔하지 않다. 아래 "지금 바로 할 수 있는 확인"으로 가린다.
4. **배제 — gunicorn 이 IP 를 바꿈.** gunicorn(로컬 25.0.1)은 `REMOTE_ADDR` 를 소켓 상대로만 채운다(`gunicorn/http/wsgi.py`). `forwarded_allow_ips` 는 scheme 헤더에만 쓰인다.

### 지금 바로 할 수 있는 확인(코드 변경 없이, Railway 대시보드 권한 필요)
- 스테이징 web 의 **HTTP Logs** 에서 `@path:/login AND @method:POST` 로 2026-10-19 시험 시각의 21건을 본다. `@srcIp` 는 Railway 가 본 손님 IP 다(공식 문서).
- 같은 시각 **Deploy Logs** 의 gunicorn 접근 로그 `"POST /login` 줄 첫 칸을 본다. 이것이 앱이 고른 IP 다.
- 판정: `srcIp` 가 한 값인데 첫 칸이 줄마다 다르면 후보 2 확정(첫 칸 대역이 CDN·엣지인지도 함께 본다). `srcIp` 도 바뀌면 후보 3.

## 변경(이번 커밋 — 어느 헤더 모양에서도 안전한 부분)
새 모듈 `foms/platform/client_ip_trust.py`, `apply_proxy_fix` 는 이것을 부르는 얇은 함수로 둔다.
1. **홉 수 해석을 한 곳으로.** 값 해석은 지금과 같다(미설정 → 1, 정수 아님 → 1, 음수 → 0). 다른 점은 정수 아님·음수일 때 경고 로그를 남기는 것과, 기동 때 적용값과 출처(env/기본값)를 INFO 한 줄로 남기는 것이다. 기본값은 바꾸지 않는다 — 2로 바꾸면 항목이 1개인 요청이 소켓 상대(모든 손님이 공유하는 내부 주소)로 떨어져 남의 시도로 내가 잠기는 더 나쁜 실패가 될 수 있다.
2. **`X-Forwarded-Prefix` 신뢰 끄기(`x_prefix=0`).** Railway 문서의 헤더 목록에 없고, 엣지 규칙도 경로 접두어를 바꾸지 않는다. FOMS 는 루트(`/`)에서 돈다. 그러니 이 헤더에 값이 있다면 손님이 넣은 것뿐이고, 믿을 이유가 없다.
3. **IP 를 믿기 어려울 때 경고 로그.** ProxyFix 안쪽에서 요청마다 헤더 모양만 보고, 아래 사유가 있으면 `logger.warning` 1줄. 같은 사유 조합은 프로세스당 10분에 1번만 남긴다(워커 2개 → 최대 시간당 12줄/조합). 응답과 `remote_addr` 는 바꾸지 않는다.
   - `xff_missing` / `xff_short`: 항목이 없거나 홉 수보다 적다 → 앱 IP 가 소켓 상대(공유 내부 주소)로 떨어졌다.
   - `xff_long`: 항목이 홉 수보다 많다 → 믿는 창 밖에 항목이 있다(인프라 홉이 하나 더 있거나 손님이 넣은 값).
   - `real_ip_mismatch`: `X-Real-IP`(Railway 문서가 손님 IP 라고 적은 헤더)가 앱이 고른 IP 와 다르다.
   - `resolved_not_global`: 고른 IP 가 공인 주소가 아니다(사설·CGNAT 100.64/10·루프백·IP 모양 아님).
   - 로그 내용: 홉 수, `X-Forwarded-For` 항목 수와 각 항목의 **앞 두 마디**(예 `203.0.*.*`, IPv6 는 앞 두 묶음), 고른 IP·`X-Real-IP`·소켓 상대의 앞 두 마디, `X-Real-IP` 와 고른 IP 가 `X-Forwarded-For` 의 몇 번째 항목인지, `Host` 와 `X-Forwarded-Host` 가 같은지(yes/no), `X-Railway-Edge` 값, 손님 IP 관련 헤더의 **이름**(`x-real-ip`·`forwarded`·`x-envoy-external-address`·`fastly-client-ip`·`cf-connecting-ip`·`true-client-ip`·`cdn-loop`·`x-forwarded-host`·`x-forwarded-prefix`) 유무, 요청 경로(쿼리 제외). 전체 IP 는 남기지 않는다.
   - 이 로그가 곧 실측 수단이다. 배포 뒤 스테이징에서 로그인 한 번이면 Railway 가 보내는 모양이 Deploy Logs 에 남는다.

### 이번에 하지 않는 것(이유)
- **`x_host=0`(X-Forwarded-Host 신뢰 끄기)는 보류.** 안전하지 않은 경우가 있다. 쓰기 요청 Origin 검사가 `request.scheme://request.host` 와 비교한다(`foms/services/request_write_guard.py:74`). Railway 가 앱에 넘기는 `Host` 가 공개 도메인과 다르면, `x_host=0` 순간 모든 쓰기가 403 이 된다. Railway 문서는 `X-Forwarded-Host` 를 "원래 Host" 라고만 적고 `Host` 를 그대로 넘기는지는 적지 않는다. 엣지가 `X-Forwarded-Host` 를 덮어쓴다는 답변(모더레이터)이 있어 지금 당장 위조 위험은 낮다. 위 경고 로그의 `host_eq_xfh` 가 yes 로 확인되면 다음 커밋에서 끈다.
- **앱이 고르는 IP 바꾸기**(아래 "실측 뒤 할 일").

## 실측 뒤 할 일(총괄 결정)
경고 로그(또는 위 HTTP Logs 대조)로 모양을 본 뒤 고른다.
- **A. 항상 [손님, 중간 주소] 2개이고 `X-Real-IP` = 첫 항목**: web 서비스(스테이징 FOMS → 운영 web) env `FOMS_TRUSTED_PROXY_HOPS=2` + 재배포. 코드 변경 없음. 확인: 경고 로그가 더는 안 나오고 로그인 8번째에 잠김.
- **B. 항목 수가 요청마다 1개·2개로 섞임**: 홉 수 하나로는 못 맞춘다. `X-Real-IP` 를 우선 쓰는 코드 변경을 별도 설계서로 낸다. 위조 방지를 위해 `X-Real-IP` 가 공인 주소이고 `X-Forwarded-For` 항목 중 하나와 같을 때만 쓰고, 아니면 지금 규칙으로 돌아간다. 2026-09-12 에 "손님이 보낸 X-Real-IP 가 앱에 닿았다"는 보고(station `supported-trust-model-for-client-ip-head-aafb68bc`)가 있어 그 교차 확인이 필요하다.
- **C. 항목 1개이고 앱 IP 가 고정**: 원인은 손님 출구 회전(후보 3). 코드는 그대로 두고 계정 카운터에 맡긴다.
- **D. `X-Real-IP`·오른쪽 항목이 CDN 대역**(Railway 회귀 재발): Railway 에 신고하고 A/B 중 맞는 쪽.
- 어느 경우든 운영 승격 전 운영 web 에서도 같은 로그로 모양이 같은지 확인한다(서비스·도메인마다 경로가 다를 수 있다).

### ADMIN 전용 확인 수단 — 제안만
경고 로그로 모양을 볼 수 있으면 **필요 없다**. 로그가 안 나오는데(사유 없음) 증상이 남거나, 로그 접근이 어려울 때만 만든다. 모양: ADMIN 로그인 필수 GET 1개, 응답은 위 경고 로그와 같은 필드(헤더 이름·항목 수·위치·IP 앞 두 마디)만, 전체 IP·쿠키·인증 헤더 값은 내지 않음, `Cache-Control: no-store`, 다른 역할은 404. 만들지는 총괄이 정한다.

## 테스트
새 파일 `tests/domains/test_client_ip_trust.py`:
- 헤더 모양별 `remote_addr`(실제 `apply_proxy_fix` 스택): 홉 1·항목 1 → 손님 / 홉 1·[손님, CDN 주소] → CDN 주소 + `xff_long`·`real_ip_mismatch` 경고 / 홉 2·같은 모양 → 손님, 경고 없음 / 홉 2·항목 1 → 소켓 상대 + `xff_short`·`resolved_not_global` / 항목 없음 → `xff_missing` / 내부 주소(10.x) → `resolved_not_global` / IP 모양 아닌 항목 → 그대로 들어감 + 경고(가린 값 `invalid`).
- 증상 재현: 손님은 같고 둘째 항목만 바뀌는 요청 3건 → 홉 1 이면 IP 3개, 홉 2 이면 1개.
- 로그인 잠금 연결: 같은 모양으로 `/login` 실패 → 홉 1 이면 (아이디, IP) 잠금이 안 걸리고, 홉 2 이면 임계에서 429 + `scope=ip`.
- 경고 묶기: 같은 사유는 10분에 1번, 시간이 지나면 다시, 다른 사유 조합은 따로.
- 로그에 전체 IP 가 없다(앞 두 마디만).
- 홉 해석: 미설정 → 1(default), "2" → 2, " 2 " → 2, "abc" → 1 + 경고, "-3" → 0 + 경고. 기동 INFO 1줄.
- `X-Forwarded-Prefix` 무시(`script_root == ""`), `X-Forwarded-Host` 는 아직 믿음(보류 결정 고정).
- 회귀: `tests/domains/test_proxy_xff_trust.py`, `tests/domains/test_login_rate_limit_lockout.py`, `tests/domains/test_login_account_lockout.py`, `tests/domains/test_rate_limit.py`, `tests/domains/test_rum_ingest.py`, `tests/domains/test_wam_telemetry.py`.

## 배포 뒤 스테이징 확인
1. Deploy Logs 에 기동 줄 `proxy trust: x_for=1 (FOMS_TRUSTED_PROXY_HOPS 미설정 → 기본값)` 이 워커마다 1줄.
2. 브라우저나 curl 로 `POST /login`(없는 아이디) 1회 → Deploy Logs 에서 `client-ip 신뢰 의심` 줄을 찾는다.
   - `reasons=xff_long,real_ip_mismatch xff_count=2 real_ip_pos=xff[0] resolved_pos=xff[1]` 류면 후보 2 확정 → "실측 뒤 할 일" A.
   - `xff_count` 가 줄마다 1·2 로 섞이면 B. 경고가 없고 HTTP Logs `srcIp` 도 바뀌면 C.
   - `host_eq_xfh=yes` 면 `x_host=0` 후속 커밋 가능.
3. 기존 기능 회귀 확인: 로그인 성공, 주문 저장 1건(쓰기 Origin 검사), `X-Forwarded-Prefix: /x` 를 붙인 요청의 리다이렉트 주소에 `/x` 가 안 붙음.

## 영향
- 요청마다 헤더 몇 개 읽기 + IP 1개 해석(마이크로초). 경고는 사유 조합별 프로세스당 10분 1줄.
- 응답·세션·`remote_addr`·한도 키는 그대로다(배포 순간 진행 중인 카운터가 무효화되지 않는다). 손님이 넣은 `X-Forwarded-Prefix` 만 더는 URL 생성에 반영되지 않는다.
- 로그에 IP 앞 두 마디가 남는다(접근 로그는 이미 전체 IP 를 남긴다).
- 실측 전까지 증상은 남는다: IP 기준 한도는 사실상 꺼져 있고, 계정 카운터(20회)만 추측을 막는다. 또 중간 주소가 여러 손님에게 공유되므로 가입·비밀번호 재설정 한도(시간당 5)처럼 낮은 IP 한도는 **남의 요청 때문에 정상 사용자가 막힐 수도** 있다 — 실측과 A/B 적용을 미루지 않는 이유다.
- 운영도 같은 코드(`RAILWAY_ENVIRONMENT == production`)라 승격하면 같은 경고 로그가 운영에도 생긴다.

## 등급
`**B` — 인증·한도의 IP 경계와 배포 구성(프록시 신뢰)에 걸친 변경. 이번 커밋은 판정을 바꾸지 않는 관측·하드닝이고, 판정 변경은 실측 뒤 별도 결정.
