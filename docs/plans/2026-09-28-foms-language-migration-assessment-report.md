# FOMS 언어·프레임워크 이전 필요성 정밀 분석 — 판정 보고서 (2026-09-28)

> 기준 HEAD `fbb391bee`(deploy). 지시서 `docs/plans/2026-09-28-foms-language-migration-assessment-prompt.md` §6 형식. 진행 원장 `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md`(워커 4개 결과·총괄 앵커 대조·리뷰 발견 전량·반영 결정).
> 표기: `[확인됨: 앵커]` = 저장소 경로:행 또는 실행 명령 출력 · `[외부: URL · 확인 날짜]` = 저장소 밖 사실 · `[가설]` = 앵커 없는 추론. 비용 단위 "주" = 개발 주(사람 1명 + 에이전트). 운영 수치는 하나도 추정하지 않았다. 리뷰(반대 심문·사실 검증) 발견을 1회 반영한 판이다.

## ① 판정

- **백엔드: 같은 언어 현대화(C1-B 축소판)** — Flask 3.1·Werkzeug 3.1·Jinja 3.1.6 상향 + psycopg3 로 psycogreen 제거. `select()` 전환·mypy 래칫은 지금 이득 근거가 없어 뺀다(⑦ #4 가 mypy 를 다시 연다). 다른 프레임워크(C2)·다른 언어(C3)는 관문에서 막힌다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:297`].
- **프런트: 유지(C0)** — 콘텐츠 해시 자산 매니페스트 중심. C5a·C5c 는 막히고, C5b(htmx 확대)는 G1 부분 증거·G2·G3 `미확정` 이라 권고하지 않되 ⑦ #7 로 가른다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:299`].
- **워커: 유지(C0)** — 워커 런타임 정본화(3.11·Nixpacks 제거) + 백그라운드 루프 감독 통일. C4(다른 런타임 부분 이전)는 워커·네이버 경계에서 막히고 실시간 경계는 `미확정` 이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:294`].

결론. FOMS 가 겪은 문제 중 언어·프레임워크에 귀속되는 몫을 재 보니 측정된 축에서는 거의 0 이다. fix 커밋 표본 80건 중 "다른 정적 타입 언어로 옮겨야만 막혔을" B 는 0건(95% 상한 4.58%)이고 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:64`], 사고 15건은 B 0·U 1(09-10, A/B 경계)이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:68`]. 파이썬 실행 시간은 오늘 스테이징 `/erp/as` 한 점에서 약 34ms / TTFB 324ms(약 11%)이고 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:223`], 몇 초짜리 꼬리는 그때 잰 렌더 구간 밖에 있다 [확인됨: `docs/harness/evidence/fragment-tail-ttfb-2026-07-02T125117.json:356`]. 보안 패치 수명 문제(Flask·Werkzeug 가 24개월 내내 창 밖)는 실재하지만 파이썬 안의 핀 문제라 같은 언어 상향으로 닫힌다 [외부: https://github.com/pallets/flask/security/policy · 확인 2026-09-28]. 이전 비용은 백엔드 다른 언어 기준 65주(24개월 가용 처리량 약 104주의 62%)이고, 24개월 환산 틀에서 C3·C5c 는 결함 이득을 최대로 잡아도 필요 이득에 닿지 않는다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:297-298`]. 그래서 세 경계 모두 언어를 옮기지 않는다.
단, 같은 언어 선택지들(C0·C1)도 환산 순이득은 모두 음수이고 서로 몇 주 차이다 — 잴 수 있는 이득(fix 커밋 비용)이 작기 때문이다. 그래서 C0 와 C1 사이 선택은 비환산 항목(보안 창·사고 유형·핀 세금)으로 내렸고, 그 사실을 ②에 명시한다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:295-296`]. 재작업(에이전트가 커밋 전에 겪는 타입 오류) 항은 저장소로 잴 수 없어 `미확정` 이며 ⑦ #4 가 세션 기록으로 가른다 [가설].
9-06 판정("조건부 유지")과 **방향(이전 안 함)은 같고, 백엔드 등급과 근거가 다르다.** 9-06 은 상향 패킷을 "유지의 조건" 으로 두었는데 그 조건 7개 중 22일 동안 이행 1·부분 1·미이행 5다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:158`]. 이 보고서는 상향을 조건이 아니라 백엔드 판정 자체(같은 언어 현대화)로 올리고, "유지" 의 근거를 조건 이행이 아니라 이전 후보의 관문 불통과에 둔다. 9-06 세부 근거 셋도 고친다: 상향 차단 요소 구성(H2), 워커 1개 강제의 성격(③ L2), 교체 비용 산정(H3).

## ② 세 관문과 수지표

G1 = 문제가 언어·런타임·프레임워크에 귀속된다는 증거 · G2 = 같은 문제를 막는 같은 언어 대안이 없거나 그 비용(기준)이 이전 비용(기준)의 절반 초과 · G3 = 이전 후보 기준 순이득 > 그 경계 최선 같은 언어 순이득. 순이득 = 환산 이득 − 비용(24개월, 주, 산정식 ⑥). 후보 정의는 겹치지 않게 했다: C0 = 9-06 거버넌스(상향 패킷 제외), C1-B = 상향을 포함한 같은 언어 현대화 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:291-293`]. C0·C1 이득은 9-06 이행률로 할인했다(기준 6% — 분기 창의 24% 가 지난 시점 값) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:158`]. "필요 이득" = 후보 비용 + 그 경계 최선 같은 언어 순이득 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:297`].

| 후보 | 경계 | G1 | G2 | G3 | 순이득(기준, 주) | 36개월 민감도 | 최종 |
|---|---|---|---|---|---|---|---|
| C0 | 백엔드 | 해당 없음(유지) | 해당 없음 | 해당 없음 | −2.4(비용 2.4 = #8 중 잠금·dependabot · #12 · #17 + #15·#16 절반, 이득 0.02) · 비환산: 15건 중 표적 사고 0(사본 #10·#11 은 C0 밖) [확인됨: `docs/plans/2026-09-06-foms-system-review-report.md:198`] | 유지비 2.4주는 세 경계 공통 | 차순 — C1-B 축소판과 환산 동률, 비환산에서 짐 |
| C0 | 워커 | 해당 없음(유지) | 해당 없음 | 해당 없음 | −2.7(비용 2.7 = #9 런타임 정본 + #23 감독 통일 3단위 + #16 절반, 이득 0.04) · 비환산: 워커 감독 유형 사고 5건 + 무감독 루프 사망 1건 = 최대 6/15, 3.11 창 밖 11개월 해소 — 둘 다 실적 0 약속 [확인됨: `start.sh:57-59`] | 변화 없음 | **선택** |
| C0 | 프런트 | 해당 없음(유지) | 해당 없음 | 해당 없음 | −0.8(비용 0.9 = #13 + #15 절반, 이득 0.06) · 비환산: 앞단 fix 터치 27.1% 가 핀 전용(할인 전 약 1.2주) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:72`] | 변화 없음 | **선택** |
| C1-B | 백엔드 | 해당 없음(같은 언어) | 해당 없음 | 해당 없음 | 전체 −7.2(이득 0.02) · 축소판(상향 + psycopg3) −2.4(이득 0) · 비환산: Flask·Werkzeug 창 밖 24→0개월, CVE-2024-49767 해소, 휴면 psycogreen 제거 — 9-06 이 같은 상향을 권고한 뒤 실적 0 [확인됨: `requirements.txt:106`] | 파이썬 3.12 종료 2028-10 → 36개월 안 3.13 약 0.6주 [외부: https://devguide.python.org/versions/ · 확인 2026-09-28] | **축소판 선택** |
| C1-B | 워커 | 해당 없음(같은 언어) | 해당 없음 | 해당 없음 | 백엔드와 같은 foms 코드를 돌리므로 축소판이 워커에도 함께 적용된다. 워커 고유 위험(3.11·Nixpacks)은 C0 #9 몫 [확인됨: `railway-worker.toml:4`] | 위와 같음 | 백엔드 판정으로 함께 적용 |
| C1-F | 프런트 | 해당 없음(같은 언어) | 해당 없음 | 해당 없음 | −10.5(타입 검사 부분만 −3.1) · A 0/80 · 재작업 `미확정` [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:151`] | 변화 없음 | 기각(⑦ #4 전까지) |
| C2 | 백엔드 | 통과 — Flask 2.3 창 밖은 프레임워크 버전 귀속(§4.3 은 L1 을 G1 증거로 인정) [확인됨: `requirements.txt:31`] | 불통과 — 같은 문제를 막는 상향 1.2 < 7.1 | 불통과 −14.2, 필요 이득 11.8 · 프레임워크 귀속 결함 0 | −14.2 | Django 5.2 LTS 2028-04 종료로 1회 더 상향 [외부: https://www.djangoproject.com/download/ · 확인 2026-09-28] | 불권고 |
| C3 | 백엔드 | 불통과(측정 축: B 0/80·사고 B 0·CPU 약 34ms/요청·수명 이득 0) · 재작업 축 `미확정` [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:64`] | 불통과 — C1-B 전체 7.2 < 32.5 | 불통과 −65.0 · 필요 62.6 > 결함 최대(B=100%) 23.5 → 24개월 틀에서 도달 불가 | −65.0 | 2027-03 재평가 때 약 79주 [가설: 줄 비례 항 +40%] | 불권고(사실상 영구 기각) |
| C4 | 워커 | 불통과 — 워커 사고 원인은 감독·재시작·env(C) [확인됨: `docs/incidents/2026-09-08-worker-self-kill-on-redis-restart.md:15`] | 불통과 — 감독 통일 1.8 < 8.2 | 불통과 −16.4 · 필요 13.7 > 워커 파일 결함 최대 0.5 | −16.4 | 이중 모델 유지 +1.2주 | 불권고 |
| C4 | 네이버 통합 | 불통과 — 공식 SDK 는 어느 언어에도 없고, 처리량 상한 2RPS 는 외부 [확인됨: `foms/services/integrations/naver_commerce/client.py:64-66`] | 불통과 — 외부 제약은 어느 언어로도 못 막음(같은 언어 대안 비용 0) | 불통과 −16.9 · 필요 약 14.2, 이득 출처 없음 | −16.9 | 동일 | 불권고 |
| C4 | 실시간 | `미확정` — emit 7곳, 문제 증거도 반증도 없음 [확인됨: `foms/platform/realtime.py:201`] | `미확정` — 같은 언어 대안(async 모드 교체) 비용 미측정 | `미확정` — 비용 12.5, 필요 약 10 | 약 −12.5 + 미확정 이득 | `미확정` | 권고 안 함(⑦ #6) |
| C5a | 프런트 | 불통과(측정 축: JS 39.9% ≈ CSS 40.0%, B 0) · 재작업 축 `미확정` [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:72`] | 불통과 — checkJs 부분 3.1 < 5.65 | 불통과 −11.3 · 필요 10.5 > 프런트 결함 최대 4.4 | −11.3 | Node LTS 가 새 패치 축(Node 24 종료 2028-04) [외부: https://endoflife.date/nodejs · 확인 2026-09-28] | 불권고 |
| C5b | 프런트 | 부분 증거 — 판정 3벌 갈라짐 사례 `a7d82df88`, 제품 파이썬+JS 동반 fix 119/1,073 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:284`] | `미확정` — 같은 언어 대안(서버가 판정 1벌, 화면은 읽기) 비용 미측정 | `미확정` — 필요 3.5 > 동반 fix 를 전부 없앤다 쳐도 3.1, 지연 이득 부호 미확정 | −4.3 + 미확정 이득 | 0 | 권고 안 함(⑦ #7) |
| C5c | 프런트 | 불통과 — B 0, B 경계는 Jinja 모양 오류 2건(모집단 약 0.2%) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:66`] | 불통과 — C1-F 10.5 < 18.55 | 불통과 −37.1 · 필요 36.3 > 프런트 결함 최대 4.4 | −37.1 | Node 축 + 서비스 워커·오프라인 큐 재작성 | 불권고(사실상 영구 기각) |

선택 근거: 같은 언어 선택지의 환산 순이득은 거의 "−비용" 이다 — 이득 항이 0 에 가까워 규칙(§4.3 끝 "기준값 순이득이 큰 쪽")이 사실상 "가장 싼 것 고르기" 로 줄어든다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:295-296`]. 그래서 결정은 비환산 항목으로 내렸다. 백엔드는 C0(−2.4)와 C1-B 축소판(−2.4)이 환산 동률인데, C1-B 축소판만 FOMS 방어선에 걸린 보안 창을 닫고 C0 백엔드 항목은 15건 중 표적 사고가 없다 → C1-B 축소판. 워커는 C0 만 감독 유형 사고(최대 6/15)를 겨냥한다 → C0. 프런트는 C0 가 환산으로도 C1-F 보다 9.7주 앞선다 → C0. 이 결정은 실적 0 의 약속에 기대므로 ⑦ #8 이 이행률로 다시 잰다.

## ③ 문제 귀속

### L1 수명·보안 패치 (24개월 창 2026-09-28 ~ 2028-09-28)

| 구성 | FOMS 앵커 | 상태 | 창 밖 개월(24/36) |
|---|---|---|---|
| Flask 2.3.3 | `requirements.txt:31` | 보안 수정은 현재 기능 릴리스(3.1.x)에만 | 24/36 — 이미 밖 |
| Werkzeug <3(로컬 2.3.8) | `requirements.txt:106` | 2.3.x 마지막 2023-11-08, 이후 수정은 3.x 에만 | 24/36 |
| Jinja2 3.1.2 | `requirements.txt:49` | 3.1 현역(3.1.6), 공지 5건 미적용 · FOMS 노출 0 | 핀만 올리면 0 |
| 파이썬 3.12(web) / 3.11(워커 빌더가 Nixpacks 일 때) | `Dockerfile:3` · `railway-worker.toml:4` | 3.12 종료 2028-10, 3.11 종료 2027-10 | 0/11 · 11/23 |
| SQLAlchemy 2.0.23 | `requirements.txt:95` | 2.0 유지보수 계열, 공개 공지 없음 | 종료일 미공개(확인 필요) |
| psycopg2 2.9.9 · psycogreen | `requirements.txt:67` · `requirements.txt:116` | psycopg2 활발, psycogreen 마지막 2020-02-22 | 0 · 휴면 |

- 근거: [외부: https://devguide.python.org/versions/ · 확인 2026-09-28] [외부: https://werkzeug.palletsprojects.com/en/stable/changes/ · 확인 2026-09-28] [외부: https://jinja.palletsprojects.com/en/stable/changes/ · 확인 2026-09-28] [외부: https://www.sqlalchemy.org/download.html · 확인 2026-09-28] [외부: https://pypi.org/pypi/psycogreen/json · 확인 2026-09-28] [외부: https://nixpacks.com/docs/providers/python · 확인 2026-09-28]
- FOMS 방어선에 직접 걸리는 미수정 취약점은 CVE-2024-49767(Werkzeug ≤3.0.5, multipart 로 `max_form_memory_size` 우회) 1건이다 [외부: https://github.com/pallets/werkzeug/security/advisories/GHSA-q34m-jh98-gwm2 · 확인 2026-09-28]. FOMS 는 바로 이 한도에 기댄다 [확인됨: `foms/platform/request_limits.py:164-172`]. 경로별 바이트 상한이 일부를 막는다 [확인됨: `foms/platform/request_limits.py:248`].
- 같은 언어 상향(Flask 3.1.3 · Werkzeug 3.1.9 · 파이썬 3.13 · psycopg3)으로 위 창은 전부 닫힌다 [외부: https://flask.palletsprojects.com/en/stable/changes/ · 확인 2026-09-28]. psycopg3 는 gevent 를 기본 지원해 psycogreen 이 필요 없다 [외부: https://www.psycopg.org/psycopg3/docs/advanced/async.html · 확인 2026-09-28].
- 보안 자세: 비밀번호 해시·서명 쿠키 세션·Jinja 자동 이스케이프·폼 파서 한도·SQL 바인딩은 프레임워크가 해 준다 [확인됨: `foms/services/security/password_policy.py:88`]. CSRF+Origin 가드·로그인 데코레이터·키 회전 세션·로그인 잠금·경로별 본문 한도·HTML 정화는 FOMS 가 직접 만들었다(약 3,500줄 + 테스트 17파일) [확인됨: `foms/services/request_write_guard.py:358` · `foms/web/auth/routes.py:272`]. 다른 언어로 옮기면 이 자작분 전부와 Werkzeug 해시 문자열 검증기를 다시 세워야 한다 [확인됨: `tests/domains/test_password_kdf_contract.py:31-33`].
- CSP·HSTS·X-Frame-Options 는 앱 코드에 0 이고, 있는 것은 Referrer-Policy 1곳과 nosniff 1곳뿐이다 [확인됨: `foms/api/share.py:131` · `foms/api/cs/settlement_channel.py:556`]. Spring 은 기본 헤더(HSTS·X-Frame-Options 등, CSP 는 기본 아님)를 넣지만 [외부: https://docs.spring.io/spring-security/reference/features/exploits/headers.html · 확인 2026-09-28], 같은 언어 after_request 한 곳으로 해결되므로 G2 에서 막힌다 [가설].

### L2 성능·동시성 — 구간별 수치

| 출처 | 화면 | 네트워크 | 서버 몫 | 파이썬 CPU(측정 구간) | 날짜 |
|---|---|---|---|---|---|
| `docs/harness/evidence/perf-gate-2026-09-11T085650.json:9` | staging 9화면 웜 | healthz 125ms | 0~128ms | Jinja 렌더 최소 2~19ms | 09-11 |
| 총괄 측정 `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:220-223` | staging `/erp/as` 1회 | tcp 45·tls 102ms | 핸들러 약 86ms | rd_normalize 2 + rd_loop 12 + 렌더 20.2 = 약 34ms | 09-28 |
| `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md:443-448` | 운영 워크벤치 유령 판정 | — | 조회 788 / 167ms | 판정 1.9~2.0ms | 09-11 |
| `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md:338` · `:417` | 운영 워크벤치 | — | — | Jinja 첫 컴파일 550~590ms → 워밍 뒤 9~52ms | 09-11 |
| `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md:16-20` | 운영 healthz·login | 왕복 약 150ms(tcp+tls) | — | — | 09-11 |
| `docs/harness/evidence/fragment-tail-ttfb-2026-07-02T125117.json:356` · `:360` | staging 이력 수정 후 | — | TTFB 최대 11,304ms | 렌더 3.7ms(그때 잰 유일한 구간) | 07-02 |
| `docs/harness/evidence/stress-tail-rca-construction-history-2026-07-02.json:14-15` | 시공·이력 2화면 수정 전 | `network_tail` false | `app_db_compute` | 분해 없음 | 07-02 |

- 언어 교체로 줄 수 있는 지연 상한은 서버 몫 안의 CPU 구간뿐이고, 측정값은 요청당 약 2~34ms 다(위 표). 어떤 언어도 이 구간을 0 으로 만들지 못하므로 실제 절감은 그보다 작다 [가설]. ORM 행 조립 CPU 는 DB 구간에 섞여 미계측이다 [확인됨: `foms/services/common/ept_b7_profile.py:1-3`].
- 지금까지의 지연 개선은 전부 같은 언어 안에서 조회 모양·캐시·워밍·클라이언트 구조를 고쳐 났다: `8ffc9c4ab`(시공·이력 12.4s 중앙값 원인 제거) · `438e298e3`(AS dTTFB 181→96) · `87d73ea6b`(Jinja 컴파일 튐 제거) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:47`]. 탭 전환 5,827ms [확인됨: `docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:7`] 는 스왑마다 스크립트 7개를 다시 돌리는 구조였다 [확인됨: `docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:27`].
- 동시성: 웹은 gevent 2워커이고 psycogreen 으로 DB 도 양보한다 [확인됨: `start.sh:127` · `app.py:3-11`]. solapi SMS 처럼 외부 API 를 요청 안에서 기다리는 호출은 패치된 소켓이라 gevent 모델에 맞다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:39`]. 약점은 CPU 가 루프를 막는 작업(PBKDF2 약 0.4초/건 CI 기준·합본 사진 Pillow·folium 폴백 `foms/api/erp_map.py:624`)인데 운영 영향은 미계측이다 [가설].
- 네이버 제약은 외부다: 앱당 2RPS 고정 [확인됨: `foms/services/integrations/naver_commerce/client.py:64-66`] [외부: https://github.com/commerce-api-naver/commerce-api/discussions/6 · 확인 2026-09-28]. Railway 고정 IP 는 서비스 단위이고 복제가 공유하므로 [외부: https://docs.railway.com/reference/static-outbound-ips · 확인 2026-09-28], IP 한도가 강제하는 것은 "WORKER 서비스 한 곳 출구" 이지 "워커 프로세스 1개" 가 아니다 [확인됨: `start.sh:32-33`]. 9-06 의 "워커 1 은 IP 한도가 강제" 는 부분 반박이다 [확인됨: `docs/plans/2026-09-06-foms-system-review-report.md:285`]. 어느 쪽이든 언어 제약이 아니다.

### L7 생태계·인력·운영

| 통합 | TS/Node | Go | Kotlin·Java | C#/.NET | FOMS 지금 |
|---|---|---|---|---|---|
| 네이버 커머스 | 공식 SDK 없음 | 없음 | 없음 | 없음 | 직접 REST 28파일 17,781줄(언어 중립) |
| solapi | 있음 | 있음 | 있음 | 있음(.NET 5/Core 3.1 대상 — 지원 종료) | Python SDK |
| 채널톡 앱 SDK | 있음 | 있음 | 없음 | 없음 | requests 직접 호출 `foms/services/channel_client.py:12` |
| Web Push·R2·Sentry | 전 후보 있음(Go Web Push 는 커뮤니티판) | | | | pywebpush·boto3·sentry |

- 근거: [외부: https://github.com/commerce-api-naver/commerce-api · 확인 2026-09-28] [외부: https://github.com/solapi · 확인 2026-09-28] [외부: https://github.com/solapi/solapi-csharp · 확인 2026-09-28] [외부: https://github.com/channel-io/app-sdk · 확인 2026-09-28] [외부: https://github.com/web-push-libs · 확인 2026-09-28] [외부: https://github.com/SherClockHolmes/webpush-go · 확인 2026-09-28] [외부: https://developers.cloudflare.com/r2/examples/aws/ · 확인 2026-09-28] [외부: https://docs.sentry.io/platforms/ · 확인 2026-09-28]
- Railpack 은 Node·Python·Go·Java 를 지원하고 .NET 은 목록에 없다 [외부: https://docs.railway.com/reference/railpack · 확인 2026-09-28]. 루트 Dockerfile 은 언어와 무관하게 쓰인다 [외부: https://docs.railway.com/builds/dockerfiles · 확인 2026-09-28].
- 언어에 귀속되는 L7 신호는 채널톡 SDK(TS·Go) 하나뿐이고, 채널톡 fix 31건 중 SDK 가 막았을 후보는 1건(`f2e15b2c2` 토큰 수명 오판)이다 [가설]. 한국 채용 시장의 언어별 수요는 1차 자료를 찾지 못해 확인 필요다.

## ④ 결함·사고 판정

- 표본 명령(끝점 고정): `git log --since=2026-06-01 --no-merges --format='%H %s' fbb391bee | grep -E '^[0-9a-f]+ fix' | awk 'NR % 13 == 0' | head -80` → 13번째마다 82건, 앞 80건 사용. 모집단 fix 1,073건 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:179`].
- 판정 규칙: A = 버그를 모른 채 켤 수 있는 일반 도구(타입 검사기·린트·일반 계약)가 커밋 시점에 잡았을 것만. 모양 선언 같은 코드 작업이 전제면 A 가 아니다. 80건 전량 판정표는 원장에 있다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:61-62`].

| 판정 | type | concurrency | domain | data-sync | cache-deploy | ui-css | integration | ops | 합 |
|---|---|---|---|---|---|---|---|---|---|
| A | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| B | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C | 0 | 2 | 20 | 4 | 4 | 29 | 7 | 13 | 79 |
| U | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 합 | 1 | 2 | 20 | 4 | 4 | 29 | 7 | 13 | 80 |

- **B 비율 0/80 = 0%(Wilson 95% 상한 4.58%)**, A 1/80 = 1.25%(경계 2건 포함 시 3/80). ops 13건 중 10건은 제품 결함이 아니라 하네스·핀 동기 비용이다(표본의 12.5%) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:64`]. 유일한 A 는 `473d96d05` — tz 없는 `datetime.datetime.now()` 를 `now_utc_naive()` 로 바꾼 커밋이고 ruff DTZ005 가 잡는 종류다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:181`] [외부: https://docs.astral.sh/ruff/rules/call-datetime-now-without-tzinfo/ · 확인 2026-09-28].
- 보조 스캔(양성 후보만, 판정 대체 아님): 모집단에서 checkJs·린트 류 JS 3건(`d38d9536c`·`437263e3e`·`c5dae7ba6`), ruff F821 류 파이썬 3건(`545b9e833` Flask `g` 누락·`1cd00528d`·`c63ef424a`), A/B 경계인 Jinja 템플릿 모양 오류 2건(`32d1bdd4f`·`b0c1b372f`, 모집단 약 0.2%) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:66` · `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:252`]. JSONB 필드가 문자열·dict 로 섞인 `c4cd51c4e` 는 경계 모델(9-06 #11) 몫이다.
- 언어 경계 이중 구현(mirror, 교차표 밖 별도 줄): 제품 파이썬과 JS 를 함께 건드린 fix 커밋 119/1,073(11.1%). 같은 규칙이 두 언어에 두 벌 있어 생긴 사례가 `cef5acbb3`(예약금 clamp)·`acd2f2334`(빈 폼 판정 키)·`a7d82df88`(잠금 판정 3벌 갈라짐)이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:284-286`]. 이 결함들도 한 언어였다면 같은 모양으로 생겼을 것이라 B 가 아니고 C 로 두되, 고치는 비용이 두 배인 구조 비용으로 ⑦ #7 에서 잰다 [가설].
- 모집단 한계: 제목이 fix 로 시작하지 않는 결함 수정(결함 낱말이 든 비 fix 커밋 61건·revert 6건)은 빠졌고, fix 안에도 비결함(하네스·핀·사용자 요청)이 섞였으며, 판정자는 1명이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:83`]. cherry-pick 중복이 83건(patch-id 고유 990) 섞여 있어 F 는 약 8% 과대다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:285`].

사고 15건(`docs/incidents/`) — A 0 · B 0 · C 14 · U 1:

| 사고 | 판정·유형 | 한 줄 | 앵커 |
|---|---|---|---|
| 02-22 지오코딩 미실행 | C ops | 백필 미실행·웹 트리거 없음·env 의존 | `docs/incidents/2026-02-22-map-geocode-not-running.md:25-37` |
| 02-22 워커 offline | C cache-deploy | USE_RQ_WORKER·REDIS_URL 설정 | `docs/incidents/2026-02-22-railway-worker-map-utils.md:13-17` |
| 02-22 원격 진단 | C cache-deploy | 같은 사건 env 점검(한 사건 3문서) | `docs/incidents/2026-02-22-remote-geocode-diagnosis.md:37-43` |
| 02-23 503 TLS | C ops | Cloudflare 에지↔Railway 오리진 TLS 조기 종료(웹) | `docs/incidents/2026-02-23-503-ssl-unexpected-eof-cloudflare.md:4` |
| 08-03 실패잡 2,544 | C ops | 퇴역 잡 실패 큐 누적(워커, 소급) | `docs/incidents/2026-08-03-rq-failed-jobs-2544-cleanup.md:11` |
| 08-07 13시간 정지 | C ops | 부팅 레이스 + 재시작 예산 소진(워커, 소급) | `docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md:10-11` |
| 08-14 AS 55건 증발 | C data-sync | 파생 사본 status 덮어쓰기(소급) | `docs/incidents/2026-08-14-as-dashboard-bulk-complete-vanish.md:11` |
| 08-24 JSONB 키 소실 | C data-sync | 보존 목록 누락(소급) | `docs/incidents/2026-08-24-structured-data-server-owned-keys-lost-on-save.md:11` |
| 08-31 큐 정지 852초 | C ops | 워커 1대 재배포(워커, 소급) | `docs/incidents/2026-08-31-worker-redeploy-queue-stall-852s.md:15` |
| 09-01 자동 매칭 실패 | C data-sync | 플랫 phone 사본 stale | `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:24` |
| 09-02 DEAD 1,188 | C cache-deploy | SIDEFX 에만 카카오 키 없음(소급) | `docs/incidents/2026-09-02-sidefx-dead-effects-1188-missing-kakao-key.md:16` |
| 09-03 AS 축 누출 | C data-sync | 투영 사본이 게이트 밖(소급) | `docs/incidents/2026-09-03-as-axis-projection-escape.md:17` |
| 09-08 워커 자멸 | C ops | exec 로 PID 1 이 러너(워커, +8일 사후 등재) | `docs/incidents/2026-09-08-worker-self-kill-on-redis-restart.md:15` |
| 09-09 감시자 헛알림 | C ops | 판정부마다 다른 신선도 예산(워커) | `docs/incidents/2026-09-09-worker-watchdog-false-stall-flap.md:11` |
| 09-10 정산 루프 사망 | U(A/B 경계) type | `int(dict)` 가 try 밖 + 무감독 기동. 도구만 켜서는 못 잡고 모양 선언이 필요 | `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md:11` |

- 선별 편향: 소급 7건은 9-06 보고서가 원장 밖이라고 짚은 것을 `2b090b565`(2026-09-06 15:41) 한 커밋으로 채운 것이다 [확인됨: `docs/incidents/2026-08-03-rq-failed-jobs-2544-cleanup.md:25`]. 9-06 보고서 커밋 `062723348` 시점 사고는 5건이었다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:183`]. 거버넌스 틀로 쓴 보고서가 고른 사고라 C 쪽으로 기울 수 있지만, 원장 밖 운영 유실 2건(`7be8dbe73` 주문 4414·`188516ecc`)도 판정하면 C 다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:76`].

L4 언어별 fix 비율(지시서 명령 원문 재실행 — 전체 `1028 CSS 2716 HTML 1479 JS 6857 PY`, fix `419 CSS 1060 HTML 634 JS 2521 PY`) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:180`]:

| 언어 | 원문 비율 | 변형(핀 전용 터치 제외 · 소스만) | 7일 재수정률 | 크기 0~300 → 3000+ 줄 |
|---|---|---|---|---|
| PY | 2521/6857 = 36.8% | 소스만 922/2970 = 31.0% (tests 42.2%) | 47.3% | 25.3% → 35.5% |
| JS(`*_js.html` 포함) | 634/1479 = 42.9% | 39.9% | 59.3% | 34.9% → 46.4% |
| HTML | 1060/2716 = 39.0% | 34.6% | — | — |
| CSS | 419/1028 = 40.8% | 40.0% | 61.5% | 38.7% → 39.7%(1000~3000) |

- 타입 체계가 없는 CSS 가 JS 와 같은 비율이고 재수정률은 더 높다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:72`]. 이는 JS 와 파이썬 소스의 약 9포인트 차이가 앞단 면(UI 반복·기기 차이·핀 세금)에서 나온다는 해석과 맞는다. 그러나 네 언어 모두 타입 검사기가 없어 "타입 검사가 있으면 줄어드는가" 를 가를 대조군이 없다 — 언어 효과는 `미확정` 이다 [가설].
- fix 1위 `templates/orders/partials/erp_order_js.html`(63줄, fix 124/220)은 fix 124건 중 119건이 핀만 바꾼 운반 파일이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:73`]. `static/js/orders/erp-order-shared.js`(6,249줄) 0.57 은 같은 3000줄+ JS(0.32~0.34)보다 23포인트 높다 — 셸 3벌이 공용하는 주문 폼이라는 역할과 맞지만 인과는 미확정이다 [확인됨: `static/js/foms/tablet-measure-form.js:215`].
- 커밋 전 에이전트가 겪는 컴파일·타입 오류는 저장소에 남지 않는다. LLM 이 만든 TS 의 컴파일 오류 평균 94% 가 타입 검사 실패라는 연구가 있으나 [외부: https://arxiv.org/pdf/2504.09246 · 확인 2026-09-28], FOMS 에서의 크기는 로컬 세션 기록(115파일)으로만 잴 수 있다 — ⑦ #4 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:286`].

## ⑤ 후보별 찬성론과 반박

**C2 같은 언어 프레임워크 교체(FastAPI·Django·Quart)**
- 찬성론: Flask 2.3 은 이미 보안 창 밖이고 G1 을 통과한다 [확인됨: `requirements.txt:31`]. Django 는 CSRF·세션·인증을 기본으로 주고, FastAPI 는 pydantic 요청 검증(이미 핀 있음 `requirements.txt:70`)과 async 로 외부 API 대기에 맞는다 [가설]. 표면도 크지 않다 — 확장 핀 5종은 import 0 이고 실제 확장은 Limiter·SocketIO 둘뿐이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:123`].
- 반박: 같은 문제를 Flask 3.1.3 상향(설치 차단 2줄 + 해시 방식 결정, 1.2주)이 막는다 [확인됨: `requirements.txt:106`]. Quart 도 CVE-2024-49767 범위이고, Django 5.2 LTS 는 2028-04 에 끝나 24개월 안 한 번 더 올려야 한다 [외부: https://www.djangoproject.com/download/ · 확인 2026-09-28]. Django 기본 보안 헤더는 HSTS 가 기본 꺼짐이고 CSP 가 없다 — FOMS 헤더 공백을 채우지 않는다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:260`]. FOMS 자작 보안(약 3,500줄 + 테스트 17)을 바꾸면 재검증이 들고, Jinja 컴파일 비용은 FastAPI+Jinja 에도 그대로다 [확인됨: `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md:338`]. HTTP 테스트 320파일 손질 포함 14.2주 대 상향 1.2주다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:121`].

**C3 다른 언어 백엔드 전면 이전(TS·Go·Kotlin/Java·C#)**
- 찬성론(가장 강한 것부터): ① 타입이 "선택" 이면 쓰이지 않는다 — foms 반환 표기 81.3% 중 553개가 `dict`·`Any` 이고 TypedDict 는 0곳이며, 9-06 같은 언어 개선의 이행률은 약 6% 다. 정적 언어는 모양 선언을 강제한다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:76`]. ② 외부 근거: 공개 JS 버그의 약 15% 를 Flow·TypeScript 가 잡는다는 연구 [외부: https://blog.acolyer.org/2017/09/19/to-type-or-not-to-type-quantifying-detectable-bugs-in-javascript/ · 확인 2026-09-28], LLM 생성 TS 컴파일 오류 94% 가 타입 검사 실패 [외부: https://arxiv.org/pdf/2504.09246 · 확인 2026-09-28], TypeScript 가 에이전트 코딩과 함께 GitHub 사용량 1위가 됐다는 보고 [외부: https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/ · 확인 2026-09-28]. ③ 코드가 8주에 foms +71%·tests +139,644줄 순증했다 — 언젠가 옮길 거라면 지금이 가장 싸고, 되돌릴 수 없는 방향으로 멀어진다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:195-196`]. ④ 다중 스레드 런타임은 gevent 의 CPU 막힘(PBKDF2 약 0.4초)을 없앤다 [가설]. ⑤ 채널톡 SDK 는 TS·Go 에만 있다 [외부: https://github.com/channel-io/app-sdk · 확인 2026-09-28].
- 반박: ① 강제는 언어가 아니라 CI 에서 온다 — mypy strict + `Any` 금지 래칫을 CI 차단으로 걸면 같은 강제를 파이썬 안에서 얻는다(비용 약 2.4주 + 타입 부채) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:293`]. 이행률 6% 는 이전 실행력에도 같이 걸리는 할인이지 이전의 근거가 아니다 [가설]. ② 15% 는 "주석을 달면 잡히는" 결함, 즉 FOMS 틀로는 A(C1-F 몫)이고, FOMS 표본에서 그런 결함은 0/80 이다 — 차이는 엄격한 A 규칙과 UI·핀 fix 비중(ui-css 29/80)에서 온다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:64`]. 94% 는 커밋 전 모집단이라 ⑦ #4 로만 확인된다. ③ 은 G1 이 한 번이라도 통과할 때만 성립하는 조건문이고, 지금 증거는 반대다(B 0/80·사고 B 0/15). 또 줄 비례 비용이 자라는 만큼 결함 이득 상한은 처리량에 묶여 있어 C3 는 시간이 갈수록 더 멀어진다(2027-03 약 79주 [가설]). 주당 변화도 불안정하다 — 08-31 주 한 주가 25,272줄로 8주 합의 30% 다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:125`]. ④ 는 운영 영향 미계측, 측정된 파이썬 CPU 는 요청당 약 34ms 이하다. ⑤ 는 채널톡 fix 31건 중 1건 후보다 [가설]. 비용 65주(테스트 줄 91.8% 재작성)이고 후보 런타임도 24개월 안 상향이 필요하다 [외부: https://endoflife.date/nodejs · 확인 2026-09-28]. C# 은 solapi SDK 대상 .NET 이 지원 종료라 감점이다 [외부: https://github.com/solapi/solapi-csharp · 확인 2026-09-28].

**C4 교살자 방식 부분 이전(워커·네이버 통합·실시간 중 하나)**
- 찬성론: 워커 감독 유형 사고가 5건(08-03·08-07·08-31·09-08·09-09)이고 무감독 루프 사망이 1건(09-10) 더 있다 — 13시간 정지도 여기서 났다 [확인됨: `docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md:10`]. 네이버 호출은 어차피 한 서비스 출구로 모아야 하니 그 경계만 떼어 감독이 강한 런타임으로 옮기면 폭발 반경이 작다 [확인됨: `start.sh:32-33`]. 실시간은 emit 7곳뿐이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:55`].
- 반박: 워커 사고 원인은 전부 감독·재시작 정책·env 누락이다(C) — 같은 언어 감독 루프가 RQ 소비자에는 이미 있고 [확인됨: `start.sh:88-125`], 정산 루프는 무감독 `&` 기동이었다 [확인됨: `start.sh:57-59`]. 네이버 처리량은 언어와 무관하게 2RPS 가 상한이다. 실시간도 emit 이 적을 뿐 옮기는 비용은 import 폐포 25,339줄 기준 약 12.5주라 "작은 파일럿" 이 아니다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:294`]. 이중 런타임은 배포·관측·하네스를 두 벌로 만든다.

**C5a TypeScript 소스 전환(.ts + 빌드 단계)**
- 찬성론: JS fix 비율 39.9% 가 파이썬 소스 31.0% 보다 9포인트 높고 7일 재수정률도 12포인트 높다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:72`]. 최다 fix JS 파일이 6,249줄이다. CI 러너 이미지에 Node 22 가 이미 있고 [외부: https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md · 확인 2026-09-28], node 로 JS 를 실행하는 계약 전례가 있으며 [확인됨: `tests/contracts/wdcalculator/_node_runner.py:24`], 휴면 TS/Vite 설정 견본(`Add In Program/` 98파일)도 있다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:154`].
- 반박: 타입 없는 CSS 가 40.0% 로 JS 와 같다 — 측정된 차이는 언어가 아니라 앞단 면과 맞는다. JS 관련 B 는 0 이고, 모집단의 JS 타입 류 3건은 빌드 없는 checkJs 로 잡힌다(C1-F, 3.1주) [가설]. Railway 에 node 빌드 단계를 넣을 수 있는지는 미확정이고(서비스별 빌더가 대시보드에 있음) [확인됨: `railway-worker.toml:4`], 이에 따라 C5a 비용이 갈린다. 서비스 워커 캐시 키가 `?v=` 핀이라 산출물 경로 규약도 다시 짜야 한다 [확인됨: `static/sw.js:89`].

**C5b htmx 확대(서버 조각으로 JS 축소)**
- 찬성론: 가장 싸고(4.3주) 점진적이다. 조각 교체 셸과 조각 라우트가 이미 있고 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:154`], 서비스 워커는 HTML 탐색을 캐시하지 않아 충돌이 없으며 [확인됨: `static/sw.js:97`], htmx 2.0.4 가 이미 실려 있다 [확인됨: `templates/partials/shared/htmx_layout.html:3`]. 같은 판정이 서버·목록 템플릿·JS 에 여러 벌 있어 갈라진 사고가 실제로 있었다(`a7d82df88`) — 서버가 조각을 그리면 판정이 한 벌로 준다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:286`]. 클라이언트에서 DOM 을 짓는 코드는 `innerHTML =` 438줄, `fetch(` 279곳(static/js)이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:288`].
- 반박: `a7d82df88` 자체가 같은 언어 해법(서버가 판정 1벌을 들고 화면은 읽기만)으로 고쳤다 — htmx 없이도 된다. 그 대안 비용을 재지 않아 G2 는 `미확정` 이다. ui-css 29/80 은 CSS 를 줄이지 않는 htmx 로 안 줄어든다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:64`]. 상호작용마다 한국↔싱가포르 왕복(healthz 113~215ms)이 붙을 수 있어 현장 태블릿 지연 이득의 부호가 미확정이다 [확인됨: `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md:16-20`]. 실사용 `hx-` 는 템플릿 2파일 7곳뿐이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:191`]. "innerHTML 코드가 셸 미러의 원천" 이라는 인과는 [가설] 이다.

**C5c SPA 재작성(React·Vue 등)**
- 찬성론: 셸 3벌(legacy·v2·v3)과 미러 구조가 1벌로 준다 [확인됨: `foms/services/feature_flags.py:281`]. 셸 누락 사고 봉합이 템플릿 조건 사슬에 쌓여 있다 [확인됨: `templates/partials/shared/layout_head.html:211-214`]. 타입 있는 컴포넌트가 Jinja 모양 오류 2건 같은 종류를 없앤다 [가설].
- 반박: 프런트 24개월 fix 총비용이 약 4.4주라 B=100% 여도 필요 이득 36.3주에 못 미친다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:298`]. 빌드 단계 필수(Railway 미확정), 서비스 워커·오프라인 큐·푸시 재작성 [확인됨: `static/sw.js:336`], 아이폰 웹뷰 QA 가 추가된다. 셸 통합 이득은 같은 언어 셸 공용 계층(9-06 #14)으로도 얻는다 [가설].

**제외 후보와 이유**
- PHP Laravel: solapi PHP SDK 는 있으나 C3 와 같은 G1 불통과이고 이득 증거가 없다 [외부: https://github.com/solapi · 확인 2026-09-28].
- Ruby Rails: solapi 공식 SDK 목록에 Ruby 가 없어 L7 이 C3 보다 나쁘다 [외부: https://github.com/solapi · 확인 2026-09-28].
- Elixir Phoenix LiveView: 실시간 강점이 있으나 FOMS 실시간 수요가 emit 7곳이라 이득 대상이 없다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:55`].
- Rust: 비용이 C3 이상이고 G1 증거가 같다 [가설].
- Litestar 등 다른 파이썬 프레임워크: C2 와 같은 판정 [가설].

## ⑥ 비용 모델

재측정 명령(지시서 §2.4 원문, W4 실행 — 총괄·리뷰어 교차 확인):
```text
route: 383 / render_template: 110 / url_for: 937 / Column(: 950 / .query( 748 / select( 8 / emit: 7
test_client files: 320 / read_text files: 264 / flag_modified: 175
FUNCS 4614 RETURN_ANN 3753 / tools files: 123
```
사실 카드와 전부 같다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:119`]. 8주 경계별 합 foms 83,020·static 51,835·templates 23,326 도 주별 합과 같다.

테스트 자산(test_*.py 825파일): HTTP 만 3 · HTTP+ORM 시드 46 · HTTP+foms 내부 159 · HTTP+소스 읽기 112 · 소스 읽기 161 · 내부 단위 302 · 기타(node 러너 등) 42. 다른 언어 이전이면 재사용 56파일 7,885줄, 심 재사용 46파일 11,034줄, 재작성 723파일 210,827줄(줄 91.8%) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:121`]. HTTP 만 두드리는 테스트도 conftest 가 SQLite 메모리 DB 로 앱을 세운다 [확인됨: `tests/conftest.py:33`].

움직이는 과녁(주당 추가+삭제 줄, `git log --since --until --no-merges --numstat --format= fbb391bee -- <경계>`) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:125`]:

| 주 | foms/ | static/ | templates/ |
|---|---|---|---|
| 08-03 | 7,832 | 3,428 | 2,810 |
| 08-10 | 12,100 | 8,151 | 5,088 |
| 08-17 | 7,554 | 4,880 | 3,473 |
| 08-24 | 11,468 | 6,575 | 3,027 |
| 08-31 | 25,272 | 13,140 | 4,889 |
| 09-07 | 8,707 | 5,475 | 2,214 |
| 09-14 | 4,223 | 2,786 | 927 |
| 09-21 | 5,864 | 7,400 | 898 |

- 순증(추가 − 삭제): foms +65,538 · static +39,425 · templates +8,552 · tests +139,644 → foms 는 8주에 92,254줄에서 157,831줄(+71%) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:195-196`].

산정식(가정값은 [가설]):
- 처리량 C = 37,352줄/주(8주 경계별 추가 298,812 ÷ 8). 느린 2주 속도면 줄 비례 항 ×1.92, 최고 주면 ×0.47 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:139`].
- 줄당 배수: 다른 언어 의미 번역 KRW 0.5/1.5/3.0 [가설 — 저장소에 언어 재작성 실적 없음] · 같은 언어 기계적 수정 0.45/0.7/1.5(낙관 = 2026-04 모듈러 개편 실적 164커밋·rename 806·194파일 32,432줄) · .js→.ts 0.2/0.5/1.0 [가설].
- 이전 후보 총비용 = W × (1 + 꼬리 + s_b). W = Σ(표면 줄 × 비율 × 배수) ÷ C + 고정비, 꼬리 = W × 0.2/0.5/1.0 [가설], s_b = 전환 동안 그 경계의 기능 흐름 비중(동결 또는 이중 구현). C4 는 경계마다 자기 폐포·자기 s_b 로 다시 쟀다.
- 같은 언어 후보: 거버넌스 1단위 0.2/0.5/1.5주, 감독 통일(#23)만 3단위(C4 G2 와 같은 값), 점진 꼬리 0.1/0.2/0.3, 병렬 세션 세금 ×1.1 은 모든 후보에서 뺐다(초안은 C1-B 에만 붙였음) [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:291`].
- 이득 = 결함 비율(표본 80건 몫) × F(24개월 fix 총비용 30.0/27.9/25.8주) × (C0·C1 만) 이행률 R 0.31/0.06/0. F = 월 약 279 fix × 24 ÷ 주당 223커밋과 fix churn 몫 24.8% × 104주 사이 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:161`]. cherry-pick 중복을 빼면 F 는 27.6/25.7/23.7 이다. R 은 9-06 전체 24항목 이행 7.5/24 · 거버넌스 8항목 약 6% · 분기 항목 완전 이행 0 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:158`]. 지연 항은 언어 귀속 몫이 요청당 수십 ms 로 비환산, 재작업 항은 `미확정`(⑦ #4).

| 후보 | 비용 낙관/기준/비관(주) | 이득 낙관/기준/비관 | 순이득 낙관/기준/비관 | 필요 이득(기준) | 핵심 항 |
|---|---|---|---|---|---|
| C0 | 3.4 / 8.4 / 25.5 | 1.16 / 0.13 / 0 | −2.2 / −8.3 / −25.5 | — | 경계별 백엔드 2.4 · 워커 2.7 · 프런트 0.9 + 유지 24개월 2.4 |
| C1-B | 2.2 / 7.2 / 24.7 | 0.35 / 0.02 / 0 | −1.9 / −7.2 / −24.7 | — | 상향 1 + 3.13 0.5 + psycopg3 1 + select() 1.5 + mypy 2(기준, 꼬리 전) |
| C1-B 축소판 | 0.88 / 2.4 / 7.8 | 0 / 0 / 0 | −0.9 / −2.4 / −7.8 | — | 상향 + psycopg3 |
| C1-F | 4.5 / 10.5 / 25.3 | 0.12 / 0 / 0 | −4.4 / −10.5 / −25.3 | — | 타입 검사 1.1/3.1/12.0 + 대형 23파일 분해 |
| C2 | 4.6 / 14.2 / 61.8 | 0 / 0 / 0 | −4.6 / −14.2 / −61.8 | 11.8 | HTTP 층 68,864줄 × 기계적 배수, 비관(Django)만 ORM 교체 |
| C3 | 22.4 / 65.0 / 165.5 | 1.16 / 0 / 0 | −21.2 / −65.0 / −165.5 | 62.6 | W 30.6 + 꼬리 15.3 + 이중 19.1(기준) |
| C4 | 워커 5.7/16.4/45.4 · 네이버 5.8/16.9/46.5 · 실시간 4.5/12.5/35.4 | 경계 몫만(워커 최대 0.5) | 전부 음수 | 워커 13.7 · 네이버 약 14.2 · 실시간 약 10 | import 폐포 × 2.46(테스트 배율) × KRW |
| C5a | 3.3 / 11.3 / 31.5 | 0.22 / 0 / 0 | −3.1 / −11.3 / −31.5 | 10.5 | JS 89,507줄 × .ts 배수 + 빌드·핀·SW |
| C5b | 1.3 / 4.3 / 11.5 | 미확정 | −1.3 / −4.3 / −11.5(이득 제외) | 3.5 | JS 30% 를 서버 조각으로 [가설 목표] |
| C5c | 11.9 / 37.1 / 98.3 | 0.22 / 0 / 0 | −11.7 / −37.1 / −98.3 | 36.3 | JS+templates 149,166줄 × KRW + SW·셸·iOS QA |

- 표 근거: [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:292-299`]. 이전 후보의 낙관 이득은 B 를 Wilson 상한 4.58% 로 둔 값이다. C0 낙관 이득은 표적 10/80 × 30.0 × 0.31 = 1.16 이다.
- 결함 이득의 최대(B=100%)는 백엔드 23.5 · 프런트 4.4 · 워커 파일 0.5주다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:298`]. 그래서 필요 이득이 이보다 큰 C3(62.6)·C5a(10.5)·C5c(36.3)·C4 워커(13.7)는 24개월 환산 틀에서 결함만으로는 닿지 않는다 — 다른 이득(지연·재작업·정지 시간)을 주 단위로 값 매기는 결정이 있어야 열린다(⑨).
- 24개월 가용 처리량은 약 104주다. C3 기준 65주는 62%, C3+C5c 전면 교체는 34.3/102.0/263.8주(7.9/23.6/60.9개월)다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:151`].
- 9-06 의 "12~24개월" 은 산정식이 없었다 [확인됨: `docs/plans/2026-09-06-foms-system-review-report.md:300`]. 새 산정에서 그 범위는 C3 기준(15.0개월)과 전면 교체 기준(23.6개월) 사이에 놓이지만, 비관 꼬리(38.2·60.9개월)를 숨겼고 C2(3.3개월)를 같은 묶음에 넣었으며 "130k 줄 JS" 는 JS+CSS 130,592줄이었다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:152`].
- 36개월 민감도: 이전 후보는 이득이 1.5배가 돼도 기준 순이득 부호가 안 바뀐다(기준 이득 0). 이전 비용의 줄 비례 항은 코드 성장과 함께 커진다(C3 2027-03 약 79주 [가설]). C0 는 3.12 종료(2028-10) 때문에 3.13 상향 약 0.6주가 붙는다 [외부: https://devguide.python.org/versions/ · 확인 2026-09-28].

## ⑦ 뒤집힘 조건

이 보고서의 이전 판정도 9-06 과 같은 함정(반증 경로가 산술상 닫힘)에 빠질 수 있어, 각 행에 "넘으면 실제로 무엇이 바뀌는지" 를 필요 이득과 함께 적었다. 24개월 환산 틀에서 C3·C5c 는 결함 축만으로는 열리지 않는다 — 열리는 길은 #1(상향 차단)·#4(재작업 실측)·⑨ 의 비환산 가치 결정뿐이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:297-298`].

| # | 경계 | 지표 | 측정 방법 | 임계값 | 넘으면 바뀌는 판정 | 재평가 시점 |
|---|---|---|---|---|---|---|
| 1 | 백엔드 | 상향 패킷 차단(9-06 반증 조건 P1) | Flask 3.1.3·Werkzeug 3.1.9 브랜치에서 `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"` + 단일 파일 테스트 | 파이썬 안에서 풀 수 없는 차단 + 해결 비용 > 7.1주(C2 기준의 절반) | C2 G2 통과, C1-B 불가 → 창을 닫는 길이 C2 뿐이 되어 C2 권고 검토 | 상향 시도 때(늦어도 2026-12-06) |
| 2 | 백엔드 | 프레임워크 귀속 결함 비율 | 지시서 L3 표본 명령을 `--since=2026-10-01`·새 HEAD 로 80건, "Flask 를 바꿔야만 막힌" 비율 판정 | 50% 이상(필요 11.8 ÷ 결함 최대 23.5) | C2 G3 통과 → C2 권고 | 2027-03 정기 재점검 |
| 3 | 백엔드 | 파이썬 CPU 몫(ORM 행 조립 미계측 칸) | staging 9경로에 행 조립 구간을 `X-FOMS-EPT-B7-PHASES` 로 추가하고 perf-gate 1회 | CPU 구간(렌더 + 행 조립 + rd_*) ≥ TTFB 중앙값 30% 인 경로 3개 이상, 같은 언어 최적화 2회 뒤에도 유지 | C3 G1(지연) 통과. G3 는 ⑨ 지연 단가가 정해져야 계산 | 분기 1회 |
| 4 | 백엔드·프런트 | 에이전트 커밋 전 재작업(재작업 `미확정` 칸) | 로컬 세션 기록 `~/.claude/projects/c--DEV-FOMS/*.jsonl`(115파일)에서 테스트·node 실행 실패 중 타입 계열 예외(파이썬 TypeError·AttributeError·NameError·KeyError, JS TypeError·ReferenceError)부터 같은 명령이 성공할 때까지의 경과 시간 합 → 24개월 환산 [가설: 1주 = 세션 경과 40시간] | 파이썬 ≥ 2.4주 · JS ≥ 2.3주 · JS ≥ 10.5주 · 파이썬 ≥ 39주 | 차례로 mypy 래칫을 C1-B 축소판에 편입 · 프런트 C0 → C1-F 타입 검사 · C5a G3 재계산 · C3 G3 재계산(결함 최대 23.5 + 39 ≥ 62.6) | 1회 측정 후 2027-03 |
| 5 | 워커 | 런타임 귀속 루프·큐 정지(9-06 반증 조건 P4) | 감독 통일 뒤 90일 사고 원장 + `worker-heartbeat-daily` 결과 | 원인이 gevent·RQ 런타임(설정·감독 아님)인 정지 2건 이상 | C4 워커 G1 통과. G3(필요 13.7주)는 ⑨ 정지 시간 단가가 있어야 계산 | 감독 통일 + 90일 |
| 6 | 워커(실시간) | C4 실시간 G1·G2·G3 `미확정` 칸 | G1: `grep -rnE "\.emit\(" foms --include=*.py \| wc -l`(지금 7) + 실시간 요구 기능 수 · G2·G3: staging 토폴로지 레인(9-06 #23)에서 Socket.IO 핸드셰이크 실패율과 같은 언어 async 모드 교체 견적 | G1: emit 30곳 이상 또는 신규 실시간 기능 3건 이상 · G2: 같은 언어 견적 > 6.25주(12.5 의 절반) · G3: 이득 ≥ 약 10주 | 차례로 C4 실시간 G1 → G2 → G3 판정 | 2027-03 |
| 7 | 프런트 | C5b G1 부분·G2·G3 `미확정` 칸 · mirror 비용 | 제품 파이썬+JS 동반 fix 119건을 "같은 규칙 두 벌" 여부로 분류 + 서버 판정 1벌 패턴(`a7d82df88` 방식) 1화면 적용 비용 실측 + 같은 화면 htmx 파일럿의 태블릿 상호작용 왕복 | mirror 몫 60% 이상 · 같은 언어 패턴 비용 > 2.15주 · htmx 지연 증가 100ms 이하 | 셋 다 넘으면 C5b G1·G2 통과, G3 는 mirror 이득(최대 3.1)+지연 이득으로 필요 3.5 재계산 | 분류 1회 + 파일럿 8주 |
| 8 | 전체 | C0·C1 이행률(9-06 반증 조건 P5) | 9-06 ④ 산출물 `ls` 루프(원장 이행표 방식) + `git log --since=2026-09-06 -- requirements.txt` | 2026-12-06(분기 마감 [가설])에 분기 12항목 완료 50% 미만, 또는 상향 패킷 미착수 | R 재설정 후 C0 대 C1 재비교. 같은 언어 실행력 부족은 이전 실행력에도 걸리므로 이전 판정은 G1 이 막아 불변 | 2026-12-06 |
| 9 | 백엔드·프런트 | 꼬리 지연 귀속(H4 미확정) | 2초 이상 꼬리 20건을 `X-Request-ID` 로 서버 `req_duration` 로그와 짝짓기 | 서버 몫이 절반 넘는 꼬리 10건 이상 | 지연을 앱 쪽으로 귀속 → #3 재측정, 네트워크면 엣지 런북 | 측정 허용 시 |

## ⑧ 권고와 첫 걸음

판정은 백엔드 같은 언어 현대화(C1-B 축소판), 워커·프런트 유지(C0)다. 다음 수는 판정마다 하나씩이고, 9-06 분기 항목이 22일 동안 완전 이행 0·부분 1 이었던 실적을 고치는 것이 목표다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:158`].

1. **상향 패킷(백엔드, 워커 코드에 함께 적용)** — 이유: Flask·Werkzeug 가 24개월 내내 창 밖이고 FOMS 가 기대는 폼 한도의 CVE 가 걸린다 [확인됨: `foms/platform/request_limits.py:164-172`].
   - 첫 걸음(한 세션): 사용자가 새 해시 방식(scrypt 수용 또는 pbkdf2 명시)을 정한 뒤 브랜치에서 `requirements.txt:31`·`requirements.txt:106` 두 줄, method 없는 `generate_password_hash` 2곳(`foms/services/security/password_policy.py:88`·`foms/services/integrations/naver_commerce/accounts.py:50`), 테스트 완화 `tests/conftest.py:26-28` 재계약.
   - 검증: `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"` · `PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_password_kdf_contract.py -q` · `scripts/ops/pre_push_smoke.ps1` exit 0. 마감 2026-12-06(⑦ #8).
2. **루프 감독 통일 + 워커 런타임 정본(워커)** — 이유: 워커 감독 유형 사고 5건 + 무감독 루프 사망 1건 [확인됨: `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md:11`].
   - 첫 걸음(한 세션): `start.sh:57-59` 정산 루프 1개를 RQ 소비자와 같은 재시작 감독(`start.sh:88-125`) 아래로 옮기고, `railway-worker.toml:4` nixpacks 를 루트 Dockerfile 정본으로 바꿀지 사용자 결정.
   - 검증: 새 계약 테스트 `tests/contracts/runtime/test_loop_supervisor.py`(신설 예정 — 루프 프로세스가 비정상 종료하면 감독자가 재기동 명령을 다시 내는지 `start.sh` 조각을 격리 실행해 단언) → `PYTHONIOENCODING=utf-8 python -m pytest tests/contracts/runtime/test_loop_supervisor.py -q` + `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"`.
3. **콘텐츠 해시 자산 매니페스트(프런트)** — 이유: 앞단 fix 터치의 27.1% 가 핀 전용이고 fix 1위 파일이 핀 운반 파일이다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:72-73`].
   - 첫 걸음(한 세션): `templates/orders/partials/erp_order_js.html` 한 파일만 해시 URL 헬퍼로 전환(`static/css/foundation/erp-pro.css` SSOT·인라인 스타일 금지 규칙 불변).
   - 검증: 새 단위 테스트 `tests/contracts/assets/test_asset_manifest.py`(신설 예정 — 자산 1바이트 변경 → 렌더 URL 변경) → `PYTHONIOENCODING=utf-8 python -m pytest tests/contracts/assets/test_asset_manifest.py -q`, 4주 뒤 `git log --since=<전환일> --no-merges -p -U0 -- templates static` 로 `?v=` 만 바뀐 fix 터치 수 재측정.

## ⑨ 열린 질문과 가설 판정

**운영 데이터 필요**(추정하지 않았다)
- 운영 `users.password` 해시 접두어 분포(로컬 dev 는 pbkdf2 10건) — 상향 때 옛 해시 호환(`app.py:20-36`) 유지 여부가 여기에 달린다.
- 워커·cron·SIDEFX 의 실제 빌더와 파이썬 패치 버전, 운영 이미지 `pip freeze`, 운영 gunicorn·gevent 버전.
- Cloudflare 캐시 규칙·엣지 보안 헤더(CVE-2026-27205 의 전제 조건).
- 운영 동시 요청 수·복제당 CPU·DB 풀 대기, 07월 이후 몇 초짜리 꼬리의 빈도와 원인, gevent CPU 막힘의 실제 크기.
- fix 1건당 실제 소요 시간, 에이전트가 커밋 전에 실패한 시도의 수·종류·시간(⑦ #4 로 1차 측정 가능).
- 원장 밖 운영 사고 전수와 노출 시간, 09-10 수정 뒤 정산 루프 생존 여부.
- 현장 기기 iOS·웹뷰 버전과 대수, 활성 세션 수, 사용자 수·주문량.
- 한국 채용 시장의 언어별 수요 1차 자료.

**사용자 결정 필요**
- 비환산 이득의 주 단위 가치 — 요청당 지연 ms, 워커 정지 1시간, 보안 창 1개월을 각각 몇 개발 주로 볼지. 이것 없이는 C3·C4·C5 의 G3 가 24개월 틀에서 결함 축만으로 닫혀 있다(⑥).
- 새 비밀번호 해시 방식, `app.py:20-36` 유지·삭제, 목표 파이썬(3.13 또는 3.14), psycopg3 전환 시점.
- 워커 빌더 교체(Nixpacks → Dockerfile 또는 Railpack), legacy 셸 폐기 여부.
- 9-06 "이번 분기" 조건의 마감일(이 보고서는 2026-12-06 으로 가정).
- 사고 원장 등재 기준(운영 유실·핀 사고 포함 여부), 타입 래칫 범위(`scripts/`·TypedDict 포함 여부).
- Cloudflare 엣지 + Argo 런북 실행 여부(꼬리 판정을 가를 가장 싼 실험), 여러 표본 스테이징 측정 허용, 세션 기록(⑦ #4) 분석 허용.
- 두 번째 개발자 계획과 언어 조건, package.json·typescript 개발 의존 도입(C1-F·C5a 전제), 전환 시 기능 동결 대 이중 구현.
- 리뷰 발견 중 반영하지 못한 것: 없음. 부분 수용 2건(② 칸마다 앵커 대신 행마다 대표 앵커, mirror 를 교차표 열이 아닌 별도 줄)은 원장에 사유가 있다 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:302-305`].

| 가설 | 판정 | 근거 |
|---|---|---|
| H1 | 확인됨(편향 경고) | 사고 15건 B 0·U 1·C 14, 소급 7건은 거버넌스 틀 보고서가 고른 모집단 — 원장 밖 유실 2건도 C [확인됨: `docs/incidents/2026-08-03-rq-failed-jobs-2544-cleanup.md:25`] |
| H2 | 부분 | 작다는 점은 확인. 설치 차단은 `requirements.txt:31`·`:106` 2줄(9-06 은 31행 누락), `foms/platform/request_limits.py:248` 은 차단 아님, `app.py:20-36` 는 안 깨지나 옛 해시를 되살리는 실동작으로 바뀜, 9-06 이 놓친 동작 변화는 기본 해시 scrypt 전환 [확인됨: `foms/services/security/password_policy.py:88`] |
| H3 | 부분 | 자릿수는 맞다(C3 15.0개월·전면 23.6개월 기준) — 비관 꼬리 38.2·60.9개월을 숨겼고 C2(3.3개월)를 같은 묶음에 넣었다 [확인됨: `docs/plans/2026-09-06-foms-system-review-report.md:300`] |
| H4 | 부분 | 모순이 아니라 시점·범위·통계량 차이: RCA 는 수정 전 2화면 중앙값(`8ffc9c4ab` 로 해소), 네트워크 문서 근거는 템플릿만 잰 헤더 — "코드/서버/DB 아님" 은 부분 확인. 지금 웜 상태 최대 단일 몫은 네트워크 왕복, 초 단위 꼬리 원인은 미확정 [확인됨: `docs/guides/NETWORK_EDGE_TAIL_FIX.md:5-6` · `foms/services/common/ept_b7_profile.py:1-3`] |
| H5 | 부분 | A 도 B 도 아닌 U(A/B 경계) — 수정 전 `result` 무표기·`dict[str, Any]` 라 도구만 켜서는 못 잡고[가설], 모양 선언(TypedDict)+검사기면 파이썬 안에서도 막힌다. 피해 지속의 주원인은 try 밖 + 무감독 기동 [확인됨: `start.sh:57-59`] |
| H6 | 부분 | 언어 탓은 `미확정` — CSS 40.0% ≈ JS 39.9% 는 앞단 면 효과와 맞지만 네 언어 모두 검사기가 없어 타입 효과를 가를 대조군이 없다. 구조 탓은 부분 확인(크기 효과 두 언어 모두 +10~11포인트, 공용 주문 폼 0.57, 인과 미확정) [확인됨: `static/js/foms/tablet-measure-form.js:215`] |
| H7 | 반박됨 | Query API 는 "not being removed", 2.1 도 동작 불변. 폐기 예정 `Query.get()` 은 1곳 [확인됨: `foms/services/channel_inbound.py:259`] [외부: https://docs.sqlalchemy.org/en/21/changelog/migration_21.html · 확인 2026-09-28] |
| H8 | 부분 | 9-06 판정 문장은 실패 가지도 "조건 이행" 으로 돌아가 문장상 반증 불가다 [확인됨: `docs/plans/2026-09-06-foms-system-review-report.md:278`]. 그러나 P1(상향 차단)·P2(조건 이행 뒤 높은 B)·P3(checkJs 뒤 프런트 fix 불변)·P4(감독 통일 뒤 런타임 귀속 정지)·P5(분기 이행률 50% 미만)를 정의할 수 있어 구조적 반증 불가는 아니다. 이 보고서의 이전 판정도 같은 구조다 — 24개월 환산 틀에서 C3·C5c 는 결함 축으로 닫혀 있고, 열리는 길은 ⑦ #1·#4 와 ⑨ 의 비환산 가치 결정뿐이다. 9-06 ④ 이행: 지금 7/7(09-06 하루), 이번 분기 12 중 완전 0·부분 1, 12~24개월 0/5 [확인됨: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md:158`] |
