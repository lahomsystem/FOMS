# 앱 응답에 표준 보안 헤더를 전역 한 곳에서 붙이기 — SPEC (2026-10-19)

## 목적
앱 응답에 표준 보안 헤더가 하나도 없다. 2026-10-19 운영·스테이징의 `GET /login` 응답에 `Content-Security-Policy`·`X-Frame-Options`·`Strict-Transport-Security`·`X-Content-Type-Options`·`Referrer-Policy`·`Permissions-Policy` 가 전부 없었다. 앞단은 Railway 엣지(`server: railway-hikari`)뿐이고 Cloudflare 가 없으니 앱이 직접 붙여야 한다. 목표는 남의 사이트가 FOMS 화면을 몰래 틀(iframe)에 넣는 공격(클릭재킹)·내용 형식 추측·주소 유출을 막고, 배포 환경은 HTTPS 로만 접속하게 하는 것이다.

## 지금 구조
- 요청 훅은 `foms/platform/http.py` 의 `register_http_bootstrap` 에 모여 있다. after_request 는 `_contain_error_responses`(`foms/platform/http.py:323`)·`_log_request_duration`(`:350`) 두 개다. 보안 헤더는 붙이지 않는다.
- 보안 헤더를 붙이는 곳은 2곳뿐이다.
  - 공유 화면 블루프린트 after_request `_share_headers`(`foms/api/share.py:125-138`) — `Referrer-Policy: no-referrer`·`X-Robots-Tag` 를 **대입**한다.
  - 정산 CSV 내려받기(`foms/api/cs/settlement_channel.py:550-559`) — 응답 생성 때 `X-Content-Type-Options: nosniff`.
- Flask 는 블루프린트 after_request 를 앱 after_request 보다 **먼저** 돌린다. 그래서 앱 쪽에서 `setdefault` 로 붙이면 위 두 곳의 값이 그대로 남는다.
- 배포 판단(`foms/platform/app_factory.py`): `is_production`(`:226`, `FLASK_ENV`/`RAILWAY_ENVIRONMENT == production`)·`is_railway`(`:247`). `SESSION_COOKIE_SECURE`(`:254-256`)는 `is_production or is_railway` 일 때 켠다.
- 정적 파일 `/static/*` 은 Flask 앞의 WhiteNoise(`app_factory.py:230-237`)가 바로 내보낸다 — after_request 를 거치지 않는다.

### 틀(iframe) 사용처 조사
| 구분 | 위치 | 판단 |
|---|---|---|
| 채널톡 데스크 안 WAM | `/channel/wam/`·`/channel/wam/api/*` (`foms/api/channel/channel_wam.py:30-31`) — "WAM 은 Desk/Front 안의 격리된 iframe 에서 동작"(`docs/plans/2026-03-26-foms-channeltalk-integration-focus-plan.md:102`) | 화면·API 는 410 퇴역(`channel_wam.py:202-213`)이지만 데스크 앱 설정의 WAM 주소가 아직 이 경로를 열 수 있다. 같은 출처만 허용하면 퇴역 안내 대신 "연결 거부" 화면이 뜬다 → **채널톡 출처 허용** |
| 채널톡 짧은 링크 | `/w/<token>` (`channel_wam.py:421-426`) → `/erp/orders/<id>/mobile` 리다이렉트 | 메시지 본문의 링크라 새 탭으로 열린다. 지금 발송 링크는 바로 `/erp/orders/<id>/mobile`(`foms/services/channel_client.py:95-100`, `foms/services/channel_policy.py:49`) → **같은 출처만** |
| 주문 편집 안 견적 계산기 | `templates/orders/partials/edit_order_body.html:641-645` (`/wdcalculator?embedded=1`) | 같은 출처 → SAMEORIGIN 으로 충분 |
| 태블릿 실측 계산기·견적서 | `static/js/foms/tablet-measure-form.js:1249,1264` (src `/wdcalculator?embedded=1`·`/edit/<id>?embedded=1`, `:128-142`) | 같은 출처 |
| 첨부 미리보기 | `static/js/channel/attachments.js:324` (WAM 레이아웃 전용 `templates/channel/wam/layout.html`) | FOMS 가 남을 싣는 쪽이라 FOMS 헤더와 무관 |
| `<embed>`·`<object>` | 템플릿·JS 0건 | — |

### 브라우저 기능(Permissions-Policy) 사용처 조사
| 기능 | 사용처 | 결정 |
|---|---|---|
| camera | `getUserMedia`: `static/js/foms/foms-qr-scan.js:134`(QR 스캔). `capture="environment"` 파일 입력: `static/js/foms/photo-capture.js:33`, `static/js/foms/tablet-measure-form.js:884,974`, `templates/construction/partials/modals.html:39,72,110`, `templates/cs/partials/as_mobile_v2_camera_bar.html:29` 등 | `camera=(self)` |
| microphone | `SpeechRecognition`: `static/js/foms/voice-input.js:44`, `static/js/orders/foms-call-log.js:101` (크롬은 음성 인식을 마이크 정책으로 묶는다) | `microphone=(self)` |
| geolocation | 코드 사용처 0건(`geolocation`·`getCurrentPosition` 전수 검색) | 현장 태블릿 용도 요청대로 `geolocation=(self)` — 다른 출처 틀만 막힌다 |
| accelerometer·gyroscope·magnetometer | `DeviceMotion`/`DeviceOrientation` 0건 | `()` 막음 |
| payment·usb·serial·hid·midi·display-capture | 0건 | `()` 막음 |
| fullscreen·web-share·clipboard-write | 공유 `navigator.share`(`static/js/measurement/image-save-sheet.js:65`, `static/js/orders/estimate-preview.js:652`), 복사 `navigator.clipboard`(`static/js/foms/kv-copy.js:35` 외) | 목록에 넣지 않음 — 브라우저 기본값(self) 유지 |

## 변경
1. 새 모듈 `foms/platform/security_headers.py` — 정책 값 상수와 `apply_security_headers(response, path, *, hsts)` 순수 함수. 모든 헤더를 `setdefault` 로 붙여 이미 정한 값은 덮어쓰지 않는다.
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - 프레임: 기본은 `X-Frame-Options: SAMEORIGIN` + `Content-Security-Policy: frame-ancestors 'self'`.
     `/channel/wam` 과 그 하위만 `Content-Security-Policy: frame-ancestors 'self' https://desk.channel.io https://*.channel.io` 이고 `X-Frame-Options` 는 붙이지 않는다(출처 목록을 담을 수 없다 — `ALLOW-FROM` 은 폐기).
   - `Permissions-Policy: camera=(self), microphone=(self), geolocation=(self), accelerometer=(), gyroscope=(), magnetometer=(), payment=(), usb=(), serial=(), hid=(), midi=(), display-capture=()`
   - `Strict-Transport-Security: max-age=31536000` — `hsts=True` 일 때만. `includeSubDomains`·`preload` 는 넣지 않는다(공용 도메인 `*.up.railway.app`).
2. `foms/platform/http.py` — `register_http_bootstrap` 에 `deployed: bool = False` 인자를 더하고 after_request `_attach_security_headers` 한 곳에서 위 함수를 부른다.
3. `foms/platform/app_factory.py` — `deployed=(is_production or is_railway)` 를 넘긴다(`SESSION_COOKIE_SECURE` 와 같은 기준).

## 테스트
새 파일 `tests/domains/test_response_headers.py`:
- 대표 화면 `/login`·JSON `/healthz`·로그인 JSON `/erp/api/notifications/badge`·404·정산 CSV 내려받기에 기본 헤더 5종이 정확히 1개씩 붙는다(CSV 의 `nosniff` 중복 없음).
- 공유 화면 `/s/<token>`(정상·404)은 `no-referrer` 가 유지되고 프레임 정책은 같은 출처.
- `/channel/wam/`·`/channel/wam/api/bootstrap`(410)은 채널톡 출처를 허용하고 `X-Frame-Options` 가 없다. `/w/<token>` 과 `/channel/wamx` 등 이름이 비슷한 경로는 같은 출처만(음성 대조군).
- 테스트(비배포) 앱엔 HSTS 가 없다. `hsts=True` 면 `max-age=31536000` 만 붙는다. 미리 정한 값은 덮어쓰지 않는다. HSTS 기준 문자열이 app_factory 의 배포 기준과 같다.
- 음성 대조: 훅을 빈 함수로 바꾸면 통합 테스트 10건이 실패한다.
- 기존 단일 파일 회귀: `tests/domains/test_order_share_view.py` · `test_channel_wam_routes.py` · `test_channel_wam_backend.py` · `test_channel_wam_templates.py` · `test_settlement_channel_export_api.py` · `test_settlement_channel_access.py` · `test_session_cookie_stability.py` · `test_last_seen_touch.py` · `test_rev_99.py` · `test_inactive_user_session_gate.py`.

## 영향·위험
- 다른 출처가 FOMS 화면을 틀에 싣던 경우가 있다면 깨진다. 코드 조사상 채널톡 WAM 외에는 없다. 채널톡 Front(고객 메신저) 안 WAM 은 최상위가 고객 사이트라 `frame-ancestors` 를 통과하지 못하지만, FOMS WAM 은 데스크 전용이었고 이미 퇴역했다.
- `nosniff` 는 형식이 틀린 스크립트·스타일을 막는다. Flask 가 내보내는 스크립트는 `/chat/scripts.js` 하나이고 `application/javascript` 로 정확하다(`foms/web/channel/routes.py:50`).
- HSTS 는 스테이징·운영 호스트 각각에만 1년 고정된다(하위 도메인 제외). 되돌릴 때는 `max-age=0` 을 한 번 내보내야 한다.
- 정적 파일(WhiteNoise)에는 붙지 않는다 — 다음 단계.
- 요청당 비용은 헤더 6개 대입뿐이다.

## 다음 단계(이번 범위 밖)
- 스크립트·스타일을 제한하는 CSP 본문(`script-src`·`style-src`·`connect-src` 등): 인라인 `<script>`·이벤트 속성과 CDN·외부 SDK(카카오 지도·공유, 다음 우편번호 등) 목록 정리가 먼저다. 먼저 `Content-Security-Policy-Report-Only` 로 위반을 모은 뒤 강제한다.
- 정적 파일 응답(`_add_static_response_headers`)에 `nosniff` 추가.
- 채널톡 데스크 앱 설정에서 퇴역한 WAM 주소를 지우면 `/channel/wam` 예외도 없앤다.

## 등급
`**B` — 앱 전역 응답 경계(배포·보안) 변경, 틀·기능 정책은 화면 회귀 확인이 필요하다.
