# FOMS 언어·프레임워크 이전 필요성 정밀 분석 — 진행 원장 (2026-09-28)

> 총괄만 쓴다. 지시서 `docs/plans/2026-09-28-foms-language-migration-assessment-prompt.md` §7 이 플랜이다. 사용자 첫 메시지로 플랜 승인을 갈음했다. 커밋 단계 없음.

## 0. 시작 기록

- 시작 시각: 2026-09-28 11:07:58 +0900
- HEAD: `fbb391bee fix(measurement): 연락처 특이사항 칸이 전화 아이콘을 가리던 문제` (사실 카드 기준 커밋과 같음 — 재측정 병기 불필요)
- 브랜치: deploy
- 시작 상태: `git status --porcelain` 11줄 → 스크래치패드 `status_before.txt` 에 저장
  - ` M docs/AI_CHANGELOG.md` · ` M docs/AI_STATUS.md` · `?? .env.bak-20260828` · `?? docs/harness/evidence/perf-gate-2026-09-11T*.json` 5개 · `?? docs/plans/2026-09-04-as-legacy-stage-cleanup-plan.md` · `?? docs/plans/2026-09-07-naver-claim-measure-context-brief.md` · `?? docs/plans/2026-09-28-foms-language-migration-assessment-prompt.md`
- `docs/AI_STATUS.md` 상단 40줄 읽음(갱신하지 않음). 스택 줄 "Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)".

## 1. 워커 배치

| 워커 | 축·가설 | 상태 |
|---|---|---|
| W1 수명·생태계 | L1 · L7 · H2 · H7 (외부 확인) | 완료 |
| W2 성능·동시성 | L2 · H4 (스테이징 측정은 명령만) | 완료 |
| W3 결함·사고·에이전트 | L3 · L4 · H1 · H5 · H6 (표본 80 + 사고 15 전량) | 완료 |
| W4 비용·경로·프런트 | L5 · L6 · H3 · H8 | 완료 |

## 2. 워커 결과 (받는 즉시 기록)

### 2.2 W2 성능·동시성 (완료 — 도구 87회, 약 12.7분)

**L2 요약**
- 웜 상태 스테이징 9화면(`docs/harness/evidence/perf-gate-2026-09-11T085650.json`, 추적): 네트워크 기준 `base_ttfb_ms` 125(9행) · 서버 몫 `delta_ttfb_ms` 0~128ms · Jinja 렌더 `min_render_ms` 2~19ms. 최소 TTFB 중 네트워크 49~100%, 서버 0~51%, Jinja 1.6~7.5%. `/erp/dashboard` 253ms 중 서버 128(51%)·렌더 19(7.5%).
- AS 대시보드 수정 전(커밋 `438e298e3` 메시지, 스테이징): 서버 129ms = tab_counts 27 + list_query 21 + row_display 49(rd_sanitize 18 + rd_timeline 17) + render 24. 파이썬 CPU 몫 59ms = 서버 몫 46%, TTFB 약 24%. 같은 언어로 해소(`docs/AI_STATUS.md:227` dTTFB 181→96).
- 네이버 워크벤치 운영(`docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md`): 유령 판정 파이썬 1.9~2.0ms 대 조회 788/167ms(`:443-448`, `:489`) — 파이썬 0.24~1.2%. Jinja 첫 렌더 컴파일 550~590ms(`:338-351`) → 부팅 워밍 `87d73ea6b` 로 9~52ms(`:417-418`). 수정 후 서버 렌더 189~297ms, 남은 몫은 조회(`:650`·`:661`·`:428`).
- 네트워크: 운영 healthz TTFB 한국 192~215ms, tcp 42·tls 90(`...:16-20`). 스테이징 healthz 113~125ms.
- DB: detoast `wb_refresh` 버퍼 14,736·50.5ms → 사본 컬럼 뒤 249·1.5ms(`:515-518` → `:635-636`). 07-02 RCA 근본 원인 전부 조회 모양(`stress-tail-rca-construction-history-2026-07-02.json:42-63,93-114`).
- 클라이언트: 첫 방문 자산 80개·1,229KB 직렬 9,151ms(캐시 헤더, `...:55`·`:63-64`, `ed98d2a95` 수정). 실측 탭 A-B-A 5,827ms(`stress-compare-2026-07-02T103000-final.json`) — 스왑마다 스크립트 7개 재실행 구조(`docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:27`).
- 언어 절감 상한: 웜 요청 서버 몫 ≤128ms(스테이징) 안의 CPU 구간뿐. 측정값 Jinja 2~19ms, 최악 59ms(해소). 초 단위 꼬리는 측정된 서버 구간 밖(`fragment-tail-ttfb-2026-07-02T125117.json` 렌더 ≤324.6ms 대 TTFB 최대 11,304ms). ORM 행 조립 CPU 는 미계측.
- 계측 도구: `X-FOMS-EPT-B7-RENDER-MS` = 템플릿 렌더만(`foms/services/common/ept_b7_profile.py:3`). 구간 헤더 PHASES 는 2026-08-10 `74b9878ae` 부터. perf-gate 판정값 = 최소 TTFB − 최소 healthz(`tools/perf/staging_perf_gate.py:13-14`), p95 미판정(`:17`), PHASES 미수집. deploy 는 경고만(`.github/workflows/perf-gate.yml:61-67`), production PR 은 차단(`:69-75`). 예산 `tools/perf/perf_budgets.json:40-76` 경로별 99~291ms.

**동시성**
- 웹 `start.sh:127` gevent -w 2, gevent patch_all·psycogreen `app.py:3-16`, DB 풀 5+5·대기 10초(`db.py:52-55`). 워커 수 주석은 `start.sh` 가 아니라 `db.py:52`·`railway.toml:5`.
- solapi SMS 는 web 요청 안에서 httpx 동기 호출(`foms/api/share.py:1147`→`:1237`→`:1130`) — 패치된 소켓이라 양보. 알림톡은 outbox→SIDEFX(`foms/services/kakao_alimtalk.py:1068`), 네이버는 web 에서 안 부름(`foms/services/jobs/queue.py:213`).
- gevent 약점(CPU 루프 막힘) 재료: PBKDF2 약 0.399초/건(CI, `d97312366`), 합본 사진 Pillow(`share.py:607-676`), folium 폴백(`foms/api/erp_map.py:624-631`), BeautifulSoup sanitize(`foms/services/as_content_safety.py:11`). 영향 미계측.
- 워커: `rq.Worker` 상속·작업마다 fork(`tools/ops/run_rq_worker.py:108-115,172`), PID 1 감시 루프 `start.sh:88-125`, 서브셸 루프 5개 `start.sh:23-73`.
- 네이버: 앱 단위 2RPS(`foms/services/integrations/naver_commerce/client.py:64-66`), 호출 IP 3개 = Railway 고정 IP(`naver_commerce/__init__.py:3-6`·`start.sh:32-33`). Railway 고정 IP 는 서비스 단위·복제 공유(외부) → 강제되는 것은 "WORKER 서비스 단일 출구" 이지 "워커 프로세스 1개" 가 아님. 9-06 `:285` 부분 반박.
- CPU 라이브러리: folium 1곳(폴백), Pillow 3곳(썸네일 RQ 우선·합본 요청 경로·업로드 트림 요청 경로), openpyxl 런타임 0(`foms/services/settlement_channel_export.py:16`), RapidFuzz 사용 0(핀만 `requirements.txt:85`).

**H4 판정: 부분** — 모순 아님, 범위·시점·통계량 차이. RCA(07-02 11:45, 수정 전 2화면, 중앙값·배치 지연 설명) → 수정 `8ffc9c4ab`(07-02 12:46) → 네트워크 문서(`c189e2a8e`, 07-03, 수정 뒤 표본). 네트워크 문서 근거 RENDER-MS 는 템플릿만 → "코드/서버/DB 아님" 은 부분 확인. "3KB 정적파일 스파이크" 저장소 앵커 없음. 지금: 웜 정상 상태는 네트워크 왕복이 최대 단일 몫, 초 단위 꼬리 원인은 미확정(07월 이후 재측정 없음, Cloudflare 엣지 런북 실행 기록 없음 — `docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:120` 뿐). 어느 문서도 언어를 가리키지 않음.

**gate_inputs 요지**: C2 G1 없음(Jinja 컴파일은 FastAPI+Jinja 에도 그대로). C3 G1 약함(측정 CPU 2~19ms/요청, 해소된 59ms), 멀티스레드 런타임이면 gevent 막힘 사라짐[가설, 미계측]. C4 워커·네이버 G1 없음(2RPS·단일 출구 = 외부). C5a 런타임 지연 불변. C5b 왕복 증가로 음수 가능[가설]. 같은 언어 지연 수정 실적: `8ffc9c4ab`·`438e298e3`·`2b98985ab`(590→34ms)·`87d73ea6b`·`e1e9fa835`/`aac966c72`.

**외부**: Railway 고정 IP 서비스당 3개·복제 공유·Pro 전용 [https://docs.railway.com/reference/static-outbound-ips · 2026-09-28]. 네이버 커머스 앱 2RPS 고정·429 [https://github.com/commerce-api-naver/commerce-api/discussions/6 · 2026-09-28]. 앱당 호출 IP 최대 3개 = 확인 필요(#2128 에 수치 없음).

**열린 질문**: 운영 동시 요청·복제당 CPU·운영 gunicorn/gevent 버전·풀 대기(확인 필요). 07월 이후 꼬리 빈도·원인(`req_duration` 400ms+ 로그를 `X-Request-ID` 로 짝지어야). ORM 조립 CPU 분리. 사용자 결정: Cloudflare 엣지+Argo 런북 실행 여부, 여러 표본 측정 허용.

**스테이징 측정 요청**: `/erp/as?view=fragment` 로그인 1회 + GET 1회, PHASES·RENDER-MS 헤더와 curl 구간(dns·tcp·tls·ttfb). 명령 원문은 W2 반환에 있음 → 총괄 실행 결과는 §3.

**명령 출력(W2 결정적 한 줄)**: `git ls-files docs/harness/evidence | grep '\.json$' | wc -l` → 37 · `grep -rnE "\.emit\(" foms --include=*.py | wc -l` → 7 · `git log -1 --date=iso 8ffc9c4ab` → 2026-07-02 12:46:05 · `git log -1 --date=iso c189e2a8e` → 2026-07-03 10:38:48 · `grep psycogreen` → `app.py:7 patch_all`·`app.py:10 patch_psycopg()` · rapidfuzz 사용 0.

### 2.3 W3 결함·사고·에이전트 (완료 — 도구 72회, 약 16.5분)

**L3 표본**: 지시서 명령 → 13번째마다 82건, head -80 사용. 모집단 fix 1,073(사실 카드 일치). 80건 중 64건이 tests/ 동반.

**80건 판정(짧은 sha · 판정 · 유형)** — 스크래치 `w3/judg.tsv` 원본
1 5ebfef2b2 C ui-css · 2 2f0500e45 C integration · 3 7e687d378 C domain · 4 4443b762e C integration · 5 434a370f3 C ops · 6 467e8f5ab C ops · 7 188516ecc C domain(부수 floating promise — A 경계) · 8 791600229 C ui-css · 9 78871c8b8 C domain · 10 1288e99b2 C ops · 11 a2f9d3007 C domain · 12 603a4a92c C cache-deploy · 13 cf4ba5e9b C domain · 14 2a7a1a734 C ui-css · 15 2692871fa C cache-deploy · 16 245e227ae C ops · 17 80e25a7d3 C integration · 18 0a7270bd9 C ui-css · 19 cef5acbb3 C domain · 20 bf6629934 C domain · 21 1bcf0c88c C ui-css · 22 f7a2f7e5c C integration · 23 e689382ca C concurrency · 24 274643947 C concurrency · 25 9a93ecadb C ui-css · 26 699bc06e3 C integration · 27 e0d5fbbfc C ops · 28 53cfb5525 C ui-css · 29 21ef7d5c7 C ui-css · 30 3db4e4f0b C data-sync · 31 14ebd552a C domain · 32 755b630fb C cache-deploy · 33 45e1fd000 C ops · 34 ef837fa41 C ui-css · 35 3a1f835ab C domain · 36 b4a1dbc53 C ops · 37 99644ad9a C domain · 38 10ba59981 C data-sync · 39 84c464bc0 C ui-css · 40 73320a30c C domain · 41 a9d31d0ae C ui-css · 42 b2dc9b834 C data-sync(스키마 대조 — A 경계) · 43 6116f5f9b C ops · 44 7be8dbe73 C domain · 45 0e98c1082 C ops · 46 f0bb9066e C ops · 47 4de18703b C ui-css · 48 99c0a8860 C domain · 49 90511d195 C ui-css · **50 473d96d05 A type**(tz 없는 `datetime.now()` → ruff DTZ005) · 51 efd938772 C ui-css · 52 b34afabdd C ops · 53 64cd35bfb C ui-css · 54 60c8aca90 C integration · 55 9be7d305a C domain · 56 fbe9f7c87 C ui-css · 57 22ad4d890 C ui-css · 58 ea23af2bd C ui-css · 59 2a65cd22d C domain · 60 4b3513b83 C domain · 61 3471502a6 C domain · 62 451276bfb C ops · 63 6f84ba5ec C ui-css · 64 3b6bc9887 C ui-css · 65 acd2f2334 C domain · 66 f24db8eb3 C integration · 67 fdc14196f C cache-deploy · 68 bf0c18436 C domain · 69 bf0416177 C ui-css · 70 ff0e06d03 C ui-css · 71 154c30222 C ui-css · 72 f67eaa1d6 C ui-css · 73 e6c9ce784 C ui-css(data-* 문자열 계약 — TS 로도 못 잡음) · 74 6e69295bb C ui-css · 75 c76bf9736 C ui-css · 76 c391210f1 C ui-css · 77 7dd4e4656 C ops · 78 42bc5907d C data-sync · 79 da568555e C domain · 80 71a22de61 C ui-css

**교차표**: A 1(type 1) · B 0 · C 79(concurrency 2·domain 20·data-sync 4·cache-deploy 4·ui-css 29·integration 7·ops 13) · U 0 · 합 80. A 경계 2건(7·42) 넣으면 A 3/80. B 는 어느 해석에서도 0. **B 비율 0/80 = 0%, Wilson 95% 상한 4.58%**. A 1/80 = 1.25%(Wilson 0.22~6.75%). ops 13 중 10건은 하네스·핀 동기 비용(12.5%).

**보조 스캔(양성 후보 전용)**: A 류 d38d9536c(`closest()` null)·437263e3e(respondWith(undefined))·c5dae7ba6·c4cd51c4e·667f408ac. A/B 경계 = Jinja 템플릿 모양 오류 32d1bdd4f(`cat.items`)·b0c1b372f(문자열에 `.get`) — 모집단 약 0.2%.

**사고 15건**: A 1(조건부, #15 settle-loop, type) · B 0 · C 14(ops 7 · data-sync 4 · cache-deploy 3). 파일·앵커:
02-22 map-geocode C ops `:25-37` · 02-22 railway-worker C cache-deploy `:13-17` · 02-22 remote-geocode C cache-deploy `:37-43` · 02-23 503-ssl C ops `:21-30` · 08-03 rq-failed-2544 C ops `:11` · 08-07 redis-boot-race C ops `:11` · 08-14 as-bulk-vanish C data-sync `:11` · 08-24 server-owned-keys C data-sync `:11` · 08-31 redeploy-stall C ops `:15` · 09-01 triage-miss C data-sync `:24-31` · 09-02 sidefx-dead C cache-deploy `:16` · 09-03 as-axis C data-sync `:17` · 09-08 self-kill C ops `:15` · 09-09 watchdog C ops `:11` · 09-10 settle-loop A(조건부) type `:11`.
등재: 7건(08-03·08-07·08-14·08-24·08-31·09-02·09-03) 은 `2b090b565`(2026-09-06 15:41) 한 커밋 소급. 9-06 보고서 `062723348`(같은 날 11:03) 시점 5건(`git ls-tree`). 09-08 건은 +8일 사후. 02-22 3건은 한 사건 3문서.

**L4 언어별 fix 비율(지시서 명령 원문 출력)**: 전체 `1028 CSS · 2716 HTML · 1479 JS · 6857 PY` / fix `419 CSS · 1060 HTML · 634 JS · 2521 PY` → PY 36.8% · JS 42.9% · HTML 39.0% · CSS 40.8%. 변형: PY 소스만 922/2970 = 31.0%, tests 42.2% · 핀 전용 터치 제외 JS 39.9% · HTML 34.6% · CSS 40.0%. 앞단 fix 터치 2,113 중 572(27.1%) 핀 전용. 7일 재수정률 `.py` 47.3% · `.js` 59.3% · `.css` 61.5%. 크기 구간(핀 제외 소스) `.py` 25.3→33.0→35.0→35.5% · `.js` 34.9→36.0→41.5→46.4% · `.css` 38.7→41.7→39.7%.
**fix 상위**: `erp_order_js.html` 63줄 124/220(핀 119 — 핀 제외 0.24) · `erp-order-shared.js` 6249줄 98/171 = 0.57(핀 0) · `layout_head.html` 73/171 · `foms-mobile-surfaces.css` 56/82(핀 50) · `naver_ingest.py` 7042줄 54/140 = 0.39 · … 3000줄+ JS 5개 0.32~0.57, 3000줄+ PY `fulfillment.py` 0.66·`naver_ingest.py` 0.39·`models.py` 0.11.
**셸 3벌**: `foms/services/feature_flags.py:263-293`(legacy·v2·v3, 281행) · `templates/partials/shared/layout_head.html:210-217` · 주문 폼 PC·모바일·태블릿(`static/js/foms/tablet-measure-form.js` 215행 미러 주석, "미러" 25개).

**가설**: H1 확인됨(편향 경고 — 소급 7건은 거버넌스 틀 보고서가 고름, 원장 밖 운영 유실 7be8dbe73·188516ecc 와 핀 사고도 C). H5 부분 — A(조건부)이지 B 아님: 수정 전 `result` 무표기·`-> dict`·`stats: dict[str, Any]` 라 mypy strict 로도 `int(Any)` 통과[추론], TypedDict/dataclass 모양 선언이 있어야 잡힘. foms TypedDict 0곳, 반환 표기 3,753 중 553 이 dict/Any. 피해 지속 주원인 = try 밖 + `start.sh:57-59` 무감독 `&` 기동(감시 루프는 RQ 만 `start.sh:100-123`). H6 언어 탓 반박(약)·구조 탓 부분 — CSS 가 JS 와 같은 비율, 크기 효과는 두 언어 모두(+10~11p), `erp-order-shared.js` 는 같은 크기 JS 보다 23p 높음(역할·미러, 인과 미확정).

**gate_inputs**: C3 G1 미충족(B 0/80, 상한 4.6%, 파이썬 소스 fix 31.0% 최저). C4 워커 G1 미충족(워커 사고 전부 ops). C5a G1 미충족(JS 39.9% ≈ CSS 40.0%). C5c 유일 B 경계는 Jinja 모양 오류 2건. C5b 판정 재료 없음. C1-B A 몫: `datetime.now()` 42곳, `Mapped[` 0·`Column(` 930(모델 타입 검사 선행 비용; 02-22 basedpyright 오탐 `setattr` 우회 `docs/incidents/2026-02-22-railway-worker-map-utils.md:69-81`). C0: 표본 10/80 하네스·핀, 앞단 fix 27.1% 핀 전용.
**월별 fix**: 6월 247/430(57%) · 7월 268/757(35%) · 8월 342/1152(30%) · 9월 216/640(34%, 09-28 09:44 까지). 최근 3개월 평균 약 275/월 → 24개월 약 6,600[가설: 속도 불변]. fix 커밋 변경 줄 평균 160.4·중앙 62(tests 제외 99.9·32) 대 비 fix 중앙 29(12). fix 1건당 시간 데이터 없음 → 비용 미확정.

**외부**: arXiv 2504.09246 — LLM 생성 TS 컴파일 오류 평균 94% 가 타입 검사 실패, 타입 제약 디코딩으로 74.8%(HumanEval)·56.0%(MBPP) 감소 [https://arxiv.org/pdf/2504.09246 · 2026-09-28]. MultiPL-E [https://arxiv.org/abs/2208.08227 · 2026-09-28](2022 모델, 적용성 낮음). ruff DTZ005 [https://docs.astral.sh/ruff/rules/call-datetime-now-without-tzinfo/ · 2026-09-28].

**열린 질문**: fix 1건당 실제 소요 시간 · 커밋 전 실패 시도 수(저장소에 안 남음) · 원장 밖 운영 사고 전수 · 09-10 수정 뒤 정산 루프 생존. 사용자 결정: 사고 원장 등재 기준 · C1-B 타입 래칫 범위에 `scripts/`·TypedDict 포함 여부. 모집단 한계: 비 fix 커밋 중 결함 키워드 61건(잡음 포함)·revert 6건 누락, fix 안 비결함(하네스·핀 10/80, 사용자 요청) 혼입, 판정자 1명.

**명령 출력(W3 결정적 한 줄)**: `python -m mypy --version` → No module named mypy · `which pyright basedpyright tsc ruff eslint` → 전부 없음 · `node --version` → v24.19.0 · `grep -c 'Mapped\[' models.py` → 0 · `grep -c 'Column(' models.py` → 930 · ast → `foms FUNCS 4614 RETURN_ANN 3753 RET_dict_or_Any 553` · `grep -rnE 'datetime\.(datetime\.)?now\(\)' foms --include=*.py | wc -l` → 42 · `git ls-tree --name-only 062723348 docs/incidents/` → 5파일 · `git log -1 2b090b565` → 2026-09-06 15:41:05.

### 2.1 W1 수명·생태계 (완료 — 도구 145회, 약 18분)

**L1 ① 24개월 창(2026-09-28 ~ 2028-09-28) 보안 패치**: 대부분 못 받는다. 전부 파이썬 생태계 안 핀 문제, 상류는 활발. 언어 귀속 수명 문제 없음.
- Flask 2.3.3 `requirements.txt:31` — Pallets 정책 "current feature release" 만 보안 수정(3.1.x). 24/24·36/36 창 밖.
- Werkzeug `>=2.3.5,<3` `requirements.txt:106`(풀린 값·로컬 2.3.8, 2023-11-08) — 보안 수정 3.x 에만. 24/24·36/36.
- Jinja2 3.1.2 `requirements.txt:49` — 3.1 계열 현역(3.1.6), 공지 5건 미적용 → 핀만 올리면 0. FOMS 노출 0(xmlattr·샌드박스·사용자 템플릿 0).
- 파이썬 3.12(web `Dockerfile:3`, CI `.github/workflows/ci.yml:54`) 지원 종료 2028-10 → 0/약 11. 3.11(`.python-version`, 워커·cron·SIDEFX 가 Nixpacks 면 — `railway-worker.toml:4`·`railway-cron.toml:13`·`railway-domain-sidefx.toml:9`) 2027-10 → 약 11/약 23 [실제 대시보드 설정 확인 필요].
- SQLAlchemy 2.0.23 `requirements.txt:95` 2.0 유지보수 계열(최신 2.0.54), 공개 공지 없음, 유지보수 종료일 미공개.
- psycopg2-binary 2.9.9 `requirements.txt:67` 상류 활발(2.9.13), 3.13 은 2.9.10 부터. psycogreen `requirements.txt:116`·`app.py:8-13` 마지막 2020-02-22 휴면 → psycopg 3.1.14+ 가 gevent 기본 지원.
- gevent 26.9.0(2026-09-16) 활발. Nixpacks 유지보수 모드(Railpack 권고) — 배포 도구 수명 위험.
- **직접 걸리는 미수정 취약점**: CVE-2024-49767(Werkzeug ≤3.0.5, multipart 로 `max_form_memory_size` 우회) — FOMS 가 이 한도에 기댐(`foms/platform/request_limits.py:164-172`), 경로별 바이트 상한(`:248`, 전체 `:74`)이 일부 방어. CVE-2026-27205(Flask <3.1.3, 저위험, 전제 3개) — `in session` 6곳. 디버거 CVE-2024-34069 노출 0.
- 같은 언어 상향(Flask 3.1.3·Werkzeug 3.1.9·파이썬 3.13·psycopg3)으로 전부 닫힘.

**L1 ② 보안 자세**: 프레임워크 몫 = Werkzeug 해시(`foms/services/security/password_policy.py:88`·`foms/web/auth/routes.py:410`) · 서명 쿠키 세션 · Jinja 자동 이스케이프(`autoescape false` 0, `|safe` 28) · 폼 파서 한도(`request_limits.py:171-172`) · ProxyFix(`foms/platform/app_factory.py:193-200`) · SQLAlchemy 바인딩(`text(f"...")` 12곳 전부 식별자·상수, `foms/services/orders/delete_retention.py:277`) · Flask-Limiter(`foms/services/rate_limit.py:11`). FOMS 자작 = CSRF+Origin 가드 `foms/services/request_write_guard.py:358`(416줄) · 로그인 데코레이터 `foms/web/auth/routes.py:272`(Flask-Login 없음) · 키 회전 세션 `foms/services/security/signing/signing_keys.py:214-238`(1,097줄) · 로그인 잠금 auth_rate 932줄(`login_lockout.py:36`) · 경로별 본문 한도 `request_limits.py:141` · HTML 정화 `foms/services/as_content_safety.py:75`(215줄) · 테스트 17파일. 이전 시 추가: Werkzeug 해시 문자열 검증기(없으면 전원 비밀번호 재설정) · 부분 이전이면 itsdangerous 쿠키 호환. 보안 헤더(CSP·HSTS·XFO) 앱 코드 0(Referrer-Policy `foms/api/share.py:131`, nosniff `foms/api/cs/settlement_channel.py:556` 뿐) — Spring 은 기본 헤더(찬성 재료)지만 같은 언어 after_request 로 해결 → G2 차단.

**L7**: 네이버 커머스 공식 SDK 어느 언어에도 없음(FOMS 직접 REST 28파일 17,781줄, 언어 중립). solapi SDK Node·Python·PHP·Kotlin·Rust·Go·C#(C# 은 .NET 5/Core 3.1 대상 — 지원 종료). 채널톡 앱 SDK TS·Go 만(FOMS 는 requests 직접, `foms/services/channel_client.py:12`). Web Push Node·Java·C#·PHP·Python 공식, Go 커뮤니티. R2·Sentry 전 후보. Railpack Node·Python·Go·Java 지원, .NET 목록에 없음(루트 Dockerfile 은 언어 무관). 한국 채용 시장 = 확인 필요.

**H2 부분**: 작다는 점은 확인(더 강해짐), 4곳 구성은 틀림. 설치 차단 2줄(`requirements.txt:31` — 9-06 누락, `:106`). `request_limits.py:248` 은 차단 아님(3.1.9 `LimitedStream(is_max)` 동일). `app.py:20-36` 안 깨짐(3.1.9 에 `_hash_internal` 동일 서명) — 다만 옛 해시를 되살리는 실동작 코드로 성격 변화. 9-06 누락 동작 변화: 3.0 부터 기본 해시 scrypt → `password_policy.py:88`·`naver_commerce/accounts.py:50` 이 조용히 scrypt 로, `tests/conftest.py:27-28` 완화 무효, `tests/domains/test_password_kdf_contract.py:31` 빨강. 확장 핀 5종(`:32-36`) 차단 0(상한 없음, import 0). werkzeug import 12줄 전부 공개 API.
**H7 반박됨**: Query API "not being removed"(2.0), 2.1 "legacy API, behavior hasn't changed". 폐기 예정 `Query.get()` 1곳(`foms/services/channel_inbound.py:259`), `session.get(` 106. 2.1 기본 드라이버 psycopg3 이나 FOMS 는 드라이버 명시(`db.py:21-28`·`:68`·`wdcalculator_db.py:26-33`). 다른 언어면 select() 코드도 재작성 → 이전 판별 기준 못 됨. `.query( 748 / select( 8` 일치.

**차단 요소 전수 표(요지)**: `requirements.txt:31`·`:106` 설치 차단(각 1줄) · `:32-36` 확장 5종 안 막음(5줄 삭제 선택) · `app.py:20-36` 안 깨짐(운영 해시 접두어 확인 뒤 삭제·유지) · `tests/conftest.py:27-28`+kdf 계약 2~3파일 · 기본 해시 사용 2곳(결정 1건 + 2줄) · `request_limits.py:46,248`·`:170-209` 안 깨짐(172행 1MiB 명시라 3.1 기본값 500kB 영향 없음) · `signing_keys.py:214-229` 안 깨짐 · `app.py:4-16`·`start.sh:127` gevent·psycogreen 은 psycopg3 때 5줄. 3.13 선행 상향: Pillow 11+(`requirements.txt:61`)·numpy 2.1+(`:56`)·psycopg2 2.9.10+(`:67`)·SQLAlchemy(`:95`, 버전 확인 필요)·`Dockerfile:3`·`.python-version`·`ci.yml:54`. psycopg3 범위: 엔진 3곳(`db.py:59-68`·`wdcalculator_db.py:87-97`·`foms/services/audit_writer.py:118-129`) + `foms/services/db_url_resolver.py:138` + `app.py:8-13`, psycopg2.errors·extras 0.

**gate_inputs 요지**: C0 — 잠금·dependabot 은 창을 못 닫음, 09-06 이후 `requirements.txt`·`Dockerfile`·`.python-version` 커밋 0, DECISIONS 스택 기록 0. C1-B — L1 창 전부 닫음, 약 6~8파일[가설]. C2 — G1 없음, Quart 도 CVE-2024-49767 범위(≤0.20.0), Django 5.2 LTS 2028-04 종료(24개월 안 1회 상향). C3 — G1 없음, 후보 런타임도 상향 필요(Node 24 약 5개월 창 밖, .NET 10 0/약 10, Go 매년, Java 25 0/0, 파이썬 3.13 0/0) → 수명 이득 0 또는 손해. L7 가산 = 채널톡 SDK(TS·Go)뿐, C# 감점. 자작 보안 약 3,500줄 + 테스트 17 + 해시·세션 호환 재구축. C4 — 워커 L1 위험(Nixpacks·3.11)은 같은 언어 설정 변경, 채널톡 fix 12/31 중 SDK 가 막았을 후보 1건(`f2e15b2c2` 토큰 수명)[가설]. C5a·C5c — 운영에 Node 런타임 없음(루트 package.json 없음), Node LTS 가 새 패치 축으로 추가(비용).

**외부 25건(확인 2026-09-28)** — devguide 파이썬 수명 https://devguide.python.org/versions/ · Werkzeug changes https://werkzeug.palletsprojects.com/en/stable/changes/ · GHSA-q34m-jh98-gwm2 https://github.com/pallets/werkzeug/security/advisories/GHSA-q34m-jh98-gwm2 · GHSA-2g68-c3qc-8985 · Werkzeug 3.1.9 소스 raw · Flask changes https://flask.palletsprojects.com/en/stable/changes/ · GHSA-68rp-wp8r-4726 · Pallets 보안 정책 https://github.com/pallets/flask/security/policy · Jinja changes https://jinja.palletsprojects.com/en/stable/changes/ · SQLAlchemy download https://www.sqlalchemy.org/download.html · Query guide https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html · migration_21 https://docs.sqlalchemy.org/en/21/changelog/migration_21.html · psycopg2 news https://www.psycopg.org/docs/news.html · psycopg3 async https://www.psycopg.org/psycopg3/docs/advanced/async.html · psycogreen pypi · gevent changelog https://www.gevent.org/changelog.html · Pillow python-support · numpy 2.1.0 notes · Flask-SocketIO/Limiter/Caching pypi · Nixpacks https://nixpacks.com/docs/getting-started · Railpack https://docs.railway.com/reference/railpack · Railway Dockerfile https://docs.railway.com/builds/dockerfiles · 채널톡 app-sdk https://github.com/channel-io/app-sdk · solapi https://github.com/solapi · solapi-csharp · 네이버 commerce-api README https://github.com/commerce-api-naver/commerce-api · web-push-libs https://github.com/web-push-libs · webpush-go · R2 aws 예시 https://developers.cloudflare.com/r2/examples/aws/ · Sentry platforms https://docs.sentry.io/platforms/ · Node eol https://endoflife.date/nodejs · .NET 정책 https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core · oracle-jdk eol https://endoflife.date/oracle-jdk · Go release https://go.dev/doc/devel/release · Django download https://www.djangoproject.com/download/ · Spring headers https://docs.spring.io/spring-security/reference/features/exploits/headers.html

**열린 질문**: 운영 해시 접두어 분포(로컬 dev pbkdf2 10건) · 워커·cron·SIDEFX 실제 빌더·파이썬 버전 · Cloudflare 캐시 규칙·엣지 보안 헤더 · 운영 `pip freeze` · SQLAlchemy 2.0 유지보수 종료 · 3.13 지원 첫 SQLAlchemy 2.0.x · `requirements.txt:82` pythonnet 등이 3.13 설치를 막는지 · 벤더 JS 3종(alpine 3.14.9·htmx 2.0.4·konva 9.3.22) 보안 공지 · 한국 채용 1차 자료. 사용자 결정: 새 해시 방식(scrypt/pbkdf2 명시) · `app.py:20-36` 유지/삭제 · 목표 파이썬(3.13/3.14) · psycopg3 전환 시점 · 워커 빌더 교체 · 두 번째 개발자 언어 조건.

**명령 출력(W1 결정적 한 줄)**: `grep -rnE '^\s*(from|import) werkzeug' foms --include=*.py | wc -l` → 12 · 확장 import(flask_session·caching·migrate·sqlalchemy·wtf) → 0 files · `Werkzeug 2.3.8`·`PY 3.12.10`(로컬) · `.query( / select(` → 748 / 8 · `session.get(` → 106 · `git log --since=2026-09-06 -- requirements.txt Dockerfile .python-version` → 출력 없음 · postgres MCP(로컬 dev) → pbkdf2 10건.

### 2.4 W4 비용·경로·프런트 (완료 — 도구 90회, 약 21.8분)

**§2.4 재측정 원문**: `route: 383 / render_template: 110 / url_for: 937 / Column(: 950 / .query( 748 / select( 8 / emit: 7` · `test_client files: 320 / read_text files: 264 / flag_modified: 175` · `FUNCS 4614 RETURN_ANN 3753 / tools files: 123` — 전부 사실 카드 일치. 8주 합 foms 83,020·static 51,835·templates 23,326 일치.

**테스트 자산 분류(test_*.py 825, 스크래치 `w4/classify_tests.py`)**: T1 HTTP만 3(0.4%, 163줄, 예 `tests/domains/test_health.py:12`) · T2 HTTP+ORM 시드 46(5.6%, 11,034줄, 예 `tests/domains/test_admin_override_idempotency.py:17-18`) · T3 HTTP+foms 내부 159(19.3%, 55,641) · T3b HTTP+소스 읽기 112(13.6%, 51,300) · T4 소스 읽기 161(19.5%, 37,320 — 파이썬·Jinja 150 재작성, static 만 11 유지) · T5 내부 단위 302(36.6%, 68,520) · T6 기타(node 러너 등) 42(5.1%, 5,768). HTTP 합 320 일치. C3 이면 재사용 56파일 7,885줄 · 심 재사용 46파일 11,034줄 · 재작성 723파일 210,827줄(파일 87.6%, 줄 91.8%). C2 이면 HTTP 320 파일 손질(`session_transaction` 239·`get_json(` 196). 한계: T1 도 conftest 가 ORM·SQLite 로 앱을 세움(`tests/conftest.py:41-43`), 경로 휴리스틱, fixture 간접 의존 못 잡음.

**데이터·인증·통합·하네스**: flag_modified 175 · migrations 98(versions .py 97) · `wdcalculator_db.py` = 같은 DB `wdcalculator` 스키마 search_path 별도 엔진·scoped session(`wdcalculator_db.py:91`·`:105`), alembic 밖 `create_all`(`:175`)·부팅 멱등 ALTER(`:125`), 레거시 `.query`(`:108`), 테이블 4(`wdcalculator_models.py:13`), import 11파일. 인증 전부 자체(`foms/web/auth/routes.py:272`·`:294`, CSRF itsdangerous `foms/services/request_write_guard.py:39`·`:178`, 세션 30일 `foms/platform/app_factory.py:257-258`), Flask-Login·WTF·CSRFProtect 0, 확장 핀 5종 import 0, 실제 확장은 Limiter·SocketIO 둘. Socket.IO 핸들러 `foms/api/channel/socketio_handlers.py:5`·서버 `foms/platform/realtime.py:201`. 통합: 네이버 28파일 17,781줄 + `naver_ingest.py` 7,042 · solapi `foms/services/kakao_alimtalk.py:446` · 웹푸시 `foms/services/notifications/push_sender.py:147` · R2 `foms/services/storage.py:23` · 채널톡 49파일 13,191줄(상한) · RQ 13파일 enqueue 24. 하네스 `tools/` 123파일 23,164줄 · `.claude/hooks/` 파이썬 11파일 1,349줄 · smoke 가 전체 pytest(`scripts/ops/pre_push_smoke.ps1:235`) · ast/Jinja 파싱 도구 12개 3,258줄 · ast 테스트 22파일.

**움직이는 과녁(주당 추가+삭제)**:
| 주 | foms/ | static/ | templates/ | 커밋 |
|---|---|---|---|---|
| 08-03~09 | 7,832 | 3,428 | 2,810 | 260 |
| 08-10~16 | 12,100 | 8,151 | 5,088 | 333 |
| 08-17~23 | 7,554 | 4,880 | 3,473 | 181 |
| 08-24~30 | 11,468 | 6,575 | 3,027 | 248 |
| 08-31~09-06 | 25,272 | 13,140 | 4,889 | 382 |
| 09-07~13 | 8,707 | 5,475 | 2,214 | 239 |
| 09-14~20 | 4,223 | 2,786 | 927 | 60 |
| 09-21~27 | 5,864 | 7,400 | 898 | 82 |
| 합 | 83,020 | 51,835 | 23,326 | 1,785 |
8주 제품 코드 추가 150,528줄 비중: foms 49.3%(api+web+platform 16.4%) · static JS 20.0% · CSS 10.3% · templates 10.6%.

**비용 모델(개발 주, 사람 1 + 에이전트, 스크래치 `w4/cost_model.py`)**: 처리량 C = 37,352줄/주(8주 경계별 추가 298,812 ÷ 8; 느린 2주 19,463 → ×1.92, 최고 79,400 → ×0.47). KRW(다른 언어 의미 번역) 0.5/1.5/3.0[가설 — 실적 없음] · KMECH(같은 언어 기계적) 0.45/0.7/1.5(낙관 = 04-07~17 모듈러 개편 164커밋·rename 806·194파일 32,432줄 실적) · .js→.ts 0.2/0.5/1.0[가설] · JS 분해 19.4k churn/주(04-12~16 wdcalculator 분해 실적). 이전 후보 총비용 = W × (1 + 꼬리 + s_b), 꼬리 0.2/0.5/1.0[가설], s_b = 경계 기능 흐름 비중. 점진 후보 꼬리 0.1/0.2/0.3, s_b 0.
| 후보 | 낙관 | 기준 | 비관(주) | 기준(개월) |
|---|---|---|---|---|
| C0 | 3.0 | 7.2 | 21.6 | 1.7 |
| C1-B | 2.4 | 7.9 | 27.2 | 1.8 |
| C1-F | 4.5 | 10.5 | 25.3 | 2.4 |
| C2 | 4.6 | 14.2 | 61.8 | 3.3 |
| C3 | 22.4 | 65.0 | 165.5 | 15.0 |
| C4 | 4.5 | 16.4 | 46.5 | 3.8 |
| C5a | 3.3 | 11.3 | 31.5 | 2.6 |
| C5b | 1.3 | 4.3 | 11.5 | 1.0 |
| C5c | 11.9 | 37.1 | 98.3 | 8.6 |
구성 요지: C1-B = 상향 패킷 0.5/1/3 + 3.13 0.2/0.5/2 + psycopg3(43곳) 0.3/1/3 + select 전환(748) 0.5/1.5/5 + mypy 래칫 0.5/2/6, ×1.1. C1-F 타입 검사 부분만 1.1/3.1/12.0. C3 = W 12.3/30.6/63.0 + 꼬리 2.5/15.3/63.0 + 이중 구현 7.7/19.1/39.5. C3 처리량 민감도 46~97주. C3+C5c = 34.3/102.0/263.8주 = 7.9/23.6/60.9개월. 24개월 가용 처리량 약 104 개발 주 → C3 기준값 62%.
**9-06 "12~24개월"**: 산정식 없음(`docs/plans/2026-09-06-foms-system-review-report.md:300`), "130k 줄 JS" 는 JS+CSS 130,592(062723348 static/js 82,033). 새 산정에서 C3 기준 15개월 ~ 전면 기준 23.6개월 사이. 비관 꼬리(38·61개월) 숨김, C2(3.3개월) 를 같은 묶음에.

**L6**: 자체 JS 89,507줄 183파일(vendor 압축본 5줄). 1,000줄+ 23파일 50,158줄, 300줄+ 73파일 74,029줄. 상위 `static/js/orders/erp-order-shared.js` 6,249 · `static/js/drawing/wizard.js` 4,627 · `static/js/cs/as-dashboard.js` 3,773. JSDoc 태그 623(45파일), `@ts-check` 0. 셸 3벌 `foms/services/feature_flags.py:263-294`, 템플릿 셸 게이트 120줄 42파일, JS 미러 표기 56줄. `static/sw.js`: 같은 출처만, `/static/` css·js 캐시 우선+TTL(`static/sw.js:89`, 키는 `?v=`), 이미지 SWR, 오프라인 큐 네트워크 우선(`:97`), push(`:336`), HTML 탐색 미캐시 → C5b 는 SW 와 충돌 없음, C5a·C5c 는 산출물 URL·핀 규약 재정립. node 전례 `tests/contracts/wdcalculator/_node_runner.py:24-25`(PATH node 가정), node 검사 스크립트 58·러너 사용 테스트 22파일, CI setup-node 없음(`.github/workflows/ci.yml:24` ubuntu-latest, `:115` 전체 pytest) — 러너 이미지 Node 22 에 기댐, tsc 없음(외부). 로컬 node v24.19.0·npm 있음, tsc·package.json·tsconfig·jsconfig 없음. **Railway node 단계 = 미확정**(`Dockerfile:3` python:3.12-slim 단일 단계, `railway.toml` [build] 없음, `railway-worker.toml:4` nixpacks; 서비스별 실제 빌더는 대시보드) — (a) Dockerfile node 단계 (b) 산출물 커밋 + CI 드리프트 검사. `Add In Program/` 98파일(ts 36·tsx 34) TS/TSX 13,886줄, React ^18.2·TS ^5.3·Vite ^5·Electron ^28, 마지막 실질 변경 05-17, 참조 0. htmx 2.0.4(`templates/partials/shared/htmx_layout.html:3`) `hx-` 14개(템플릿 2), alpine 3.14.9(`templates/partials/shared/alpine_layout.html:4`) `x-data` 2파일. 자체 조각 교체 셸 `static/js/runtime/erp-shell.js:2-3`(1,140줄)·`foms/api/fragment.py:1`·조각 라우트 11. `innerHTML =` 438줄·`fetch(` 395곳.

**H3 부분**: C3 5.2/15.0/38.2개월, 전면 7.9/23.6/60.9개월. 자릿수 맞음, 비관 꼬리 숨김·C2 혼입·"130k JS" 오류.
**H8 부분**: 판정 문장은 반증 불가 구조(`docs/plans/2026-09-06-foms-system-review-report.md:278`) 맞으나 근거 전제마다 반증 증거 정의 가능 → 확인됨 아님.
**9-06 ④ 이행표(09-06 이후 병합 제외 413커밋)**: 1 방향 래칫 이행 `2b090b565` · 2 파일 크기 래칫 이행 `2b090b565` · 3 드리프트 감사 이행 `125ad8cc9`·`9e51b2e73` · 4 하트비트·Sentry 이행 `41df23606`(+`4182d756c`) · 5 사고 원장 이행 `2b090b565` · 6 로그인 한도 이행 `40d25bb1b` · 7 두 번째 개발자 부팅 이행 `1d0a4eebd` · 8 의존성 층+상향 미이행(`ls` 없음, Flask 2.3.3) · 9 파이썬 단일화 미이행(3.11.9) · 10 생성 컬럼 미이행 · 11 키 레지스트리 미이행 · 12 인증 services 이동 미이행(`foms/web/auth/routes.py:61`) · 13 해시 매니페스트 미이행 · 14 셸 공용 계층 미이행 · 15 단일 초록 부분(`a7bf23bf0` 09-22 smoke 전체 스위트, 스탬프 없음) · 16 배포 정본·롤백 미이행 · 17 매니페스트 3자 미이행 · 18 PII 미이행 · 19 색인 자동화 미이행 · 20~24 전부 미이행(스택 ADR 0). 요약: "지금" 7/7(09-06 하루 6커밋), "이번 분기" 12 중 완전 0·부분 1(22일 경과 = 분기 24%), "12~24개월" 0/5. ⑤ 조건 7개 중 이행 1·부분 1·미이행 5.
**반증 조건(9-06 논리 안)**: P1 수명(상향 시도에서 파이썬 안 해결 불가 차단 + 비용 > C2 절반 7.1주 → C2) · P2 사고 원인(조건 이행 뒤 B 비율 높음 — 단 B 100% 여도 24개월 결함 이득 상한 25.8~30.0주 < C3 65주, C2·C4·C5a 규모만 뒤집힘) · P3 프런트(C1-F 뒤 12주 static fix 비율 불변 + checkJs 못 잡는 타입 결함 → C5a) · P4 워커(감독 통일 뒤에도 루프 사망 + gevent·RQ 런타임 귀속 → C4) · P5 비용 전제(분기 말 12항목 완료율 50% 미만 → G2 비교로).

**gate_inputs 요지**: C2 G2 1.5 < 7.1 불통과 · C3 G2 C0+C1-B 15.1 < 32.5 불통과, 결함 이득 상한(B=100%) 25.8~30.0주 < 65 · C4 G2 감독 통일 1.5 < 8.2 불통과(전례 `41df23606` 493줄) · C5a G2 3.1 < 5.65 불통과, 낙관 3.3 + B ≥ 70% 일 때만 본전 · C5b C1-F 보다 쌈(4.3 < 10.5), 지연 부호 미확정 · C5c G2 10.5 < 18.6 불통과. 결함 이득 상한 출처: fix 월 약 279 → 24개월 약 6,690건, 커밋당 1주/223커밋, 8주 churn fix 몫 24.8%, 프런트 fix churn 15.7%. C0 실적 할인 거버넌스 8항목 이행 0·부분 1 → 실현율 약 6%.
**외부**: Railway 루트 Dockerfile 기본 [https://docs.railway.com/guides/dockerfiles · 2026-09-28] · ubuntu-latest = 24.04 [https://github.com/actions/runner-images · 2026-09-28] · 24.04 이미지 Node 22.23.2, TypeScript 없음 [https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md · 2026-09-28].
**열린 질문**: 서비스별 실제 빌더 · 현장 iOS·웹뷰 버전·대수 · 활성 세션 수 · C5b 왕복 실측. 사용자 결정: 동결 대 이중 구현 · 두 번째 개발자 계획 · package.json·typescript devDependency 승인 · legacy 셸 폐기 · 9-06 분기 마감일. 측정 못 함: KRW 실적(파일럿 예 `foms/api/channel/socketio_handlers.py` 178줄) · T2 심 재사용 · Starlette url_for 호환 · 경로 합산 차이 8%(298,812 대 323,134).
**총괄 메모 — W3·W4 월별 fix 수 차이**: W3 7월 268·8월 342·9월 216(합 1,073 = 사실 카드) 대 W4 7월 278·8월 337·9월 221(8월 전체 1,112 대 W3 1,152). 월 경계·시간대 처리 차이로 보인다. 보고서는 사실 카드 합과 맞는 W3 값을 쓰고, 결함 이득 상한은 W4 식(월 약 279)을 그대로 인용하되 차이는 2% 안이라 판정에 영향 없음.

## 3. 총괄 앵커 대조

### 3.1 W1 대조 (10곳 직접 열람 — 전부 일치)
- `requirements.txt:31-36,49,67,95,106,115,116` 핀 값 일치(Flask==2.3.3 · 확장 5종 · Jinja2==3.1.2 · psycopg2-binary==2.9.9 · SQLAlchemy==2.0.23 · Werkzeug>=2.3.5,<3 · gevent · psycogreen).
- `foms/platform/request_limits.py:164-172` max_form_memory_size 1 MiB 의존 · `:248` `LimitedStream(stream, max_body_bytes + 1, is_max=True)` 일치.
- `foms/services/security/password_policy.py:88` `generate_password_hash(plaintext)` method 없음 일치(Werkzeug 3 에서 scrypt 로 바뀔 자리).
- `foms/services/channel_inbound.py:259` `db.query(ChannelInboundEventLog).get(log_id)` 일치.
- `railway-worker.toml:4` `builder = "nixpacks"` 일치.
- `tests/conftest.py:26-28` · `tests/domains/test_password_kdf_contract.py:31-32` 일치.
- `foms/services/request_write_guard.py:358` `def enforce_csrf_origin()` · `foms/web/auth/routes.py:272` `def login_required(f):` 일치.
- 미이행 거버넌스 파일 6종 `ls` → 전부 No such file(사실 카드 §2.2 그대로).

### 3.3 W3 대조 (직접 재실행 — 전부 일치)
- 표본 명령 → `SAMPLE 82`, head -80 의 1·50·80번째 = `5ebfef2b2`·`473d96d05`·`71a22de61`(W3 목록과 같은 위치).
- L4 명령 원문 재실행 → 전체 `1028 CSS 2716 HTML 1479 JS 6857 PY` · fix `419 CSS 1060 HTML 634 JS 2521 PY` 일치.
- `473d96d05` diff `-datetime.datetime.now().isoformat()` → `+now_utc_naive().isoformat()` 일치(A 판정 근거).
- `667f408ac` diff `-"calls": int(stats.get("calls") or 0),` · 수정 전 257행 `def _heartbeat_metadata(*, ran_now: bool, result, tick: int = 0) -> dict:`(result 무표기) 일치.
- `2b090b565` 2026-09-06 15:41:05 · incidents 7파일 · `062723348` 시점 incidents 5파일 일치.
- `start.sh:57-59` 정산 루프 `--json &` 무감독 기동 일치.

### 3.4 W4 대조 (12곳 — 11 일치, 1 차이)
- `docs/plans/2026-09-06-foms-system-review-report.md:278`(판정 문장)·`:300`(교체 비용 문장, 산정식 없음) 일치.
- `wdcalculator_db.py:91`(search_path)·`:105`(scoped_session)·`:108`(query_property)·`:125`(ensure_settings_schema_upgrades)·`:175`(create_all) 일치.
- `static/sw.js:89` staticCacheFirst · `:97` networkFirstQueue · `:336` push 일치. `tests/contracts/wdcalculator/_node_runner.py:24` node PATH 가정 일치. `foms/services/feature_flags.py:263,281` 셸 변형 3종 일치. `.github/workflows/ci.yml:24,54,115` 일치. `foms/platform/app_factory.py:257-258` 세션 30일 일치.
- 커밋 `41df23606`·`40d25bb1b`·`9e51b2e73`·`1d0a4eebd`·`125ad8cc9` 전부 2026-09-06, `a7bf23bf0` 2026-09-22 일치. 08-31 주 foms churn 재실행 → 25272 일치. `git ls-files "Add In Program" | wc -l` → 98 일치.
- **차이**: W4 "`hx-` 속성 14개(템플릿 2)" → 총괄 재측정 `grep -rnoE 'hx-[a-z]+' templates --include=*.html | wc -l` → 7, 파일 2개(`foms_search_overlay.html`·`foms_split_shell.html`). 보고서는 7 을 쓴다(판정 영향 없음 — 어느 쪽이든 htmx 실사용은 미미).
- 참고: W2 앵커 `docs/AI_STATUS.md:21`(/erp/as 168/168) 은 다른 창이 AI_STATUS 를 수정 중이라 줄이 밀림(현재 16행) — 보고서에서 AI_STATUS 앵커는 쓰지 않는다. W2 `...tab-roundtrip...:489` 는 빈 줄 → 같은 수치의 실제 위치 `:443-448` 을 쓴다.

### 3.5 총괄 추가 측정
- 8주(08-03~09-27) 순증: `git log ... --numstat -- <dir>` → `foms/ add=74279 del=8741 net=65538` · `static/ add=45630 del=6205 net=39425` · `templates/ add=15939 del=7387 net=8552` · `tests/ add=148284 del=8640 net=139644`.
- 08-03 직전 커밋 `b8f31bcbd` 의 py·js·html·css 줄 합: foms 92,254 · static 102,609 · templates 51,082 → 지금(사실 카드) foms 157,831(+71%) · static 142,181(+39%) · templates 59,659(+17%). 이전 비용의 줄 비례 항이 8주에 이만큼 자란다(움직이는 과녁).
- 워커 런타임 파일(`start.sh`·`tools/ops/run_rq_worker.py`·`tools/ops/wait_for_redis.py`·`scripts/maintenance/`·`foms/services/sidefx_worker.py`·`foms/services/jobs/`·railway toml 3종·Procfile)을 건드린 fix 커밋 19/1,073(1.8%).
- 총괄 수지 모델 `scratchpad/lead/net_model.py` 출력(24개월, 개발 주, 비용은 W4 그대로, 이득 = 결함 비율 × fix 총비용 F(30.0/27.9/25.8) × C0·C1 은 9-06 이행률 할인 R(0.31/0.06/0)):
  - `C0 benefit [1.4, 0.15, 0.0] cost [3.0, 7.2, 21.6] net [-1.6, -7.1, -21.6]`
  - `C1-B benefit [0.35, 0.02, 0.0] net [-2.1, -7.9, -27.2]` · `C1-F net [-4.4, -10.5, -25.3]`
  - `C2 net [-4.6, -14.2, -61.8]` · `C3 benefit [1.16, 0.0, 0.0] net [-21.2, -65.0, -165.5]` · `C4 net [-3.3, -16.4, -46.5]`
  - `C5a net [-3.1, -11.3, -31.5]` · `C5b net [-1.3, -4.3, -11.5]`(이득 미확정) · `C5c net [-11.7, -37.1, -98.3]`
  - 할인을 비용·이득 둘 다 걸면 기준 C0 −0.29 · C1-B −0.45 · C1-F −0.63(순위 같음). 프런트 핀 세금 대체 추정 1.28/1.19/1.10주. B=100% 상한 백엔드 25.3/23.5/21.7 · 프런트 4.7/4.4/4.1.
  - 모델 확정 후 C0 표적 비율을 6/80(프런트 핀 3 · 워커 루프·부팅 2 · 백엔드 1)으로 정정(스크립트의 7/80 은 초안 값). 기준 이득 0.15 → 0.13, 판정 영향 없음.

### 3.2 W2 대조 (6곳 직접 열람 — 전부 일치)
- `foms/services/common/ept_b7_profile.py:1-3` "render_ms 는 템플릿 렌더만 담는다" 일치.
- `docs/harness/evidence/perf-gate-2026-09-11T085650.json:9` `"base_ttfb_ms": 125` 일치.
- `stress-tail-rca-construction-history-2026-07-02.json:3-4,14-15,25,32` run_id 07-02T11:45 · scope · `app_db_compute` · `network_tail: false` · p95 8901·10735 일치.
- `foms/services/integrations/naver_commerce/client.py:64-66` 앱당·API당 2 RPS 고정 일치.
- `db.py:52-55` pool 5+5·timeout 10 일치. `railway.toml:5` Replica 2 주석 일치.
- `start.sh:32-33` "호출 IP 한도 3 = Railway static IP 3 … 이 서비스 한 곳으로" 일치 — 강제 대상은 서비스(출구)이지 프로세스 수가 아니라는 W2 해석과 맞음.
- `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md:16-20` healthz 192~215ms · 네트워크 왕복 ~150ms 일치.
- 참고: 사실 카드의 크리덴셜 위치 `tools/perf/staging_perf_gate.py:807-808` 은 실제 `_credentials()` 정의가 807행(env `FOMS_STAGING_USERNAME`/`PASSWORD`). 측정은 가이드(`docs/guides/REAL_SERVER_TEST_ACCOUNT.md:17`)의 secrets 파일로 했다.

### 3.2a 총괄 스테이징 측정 (§3.7 — 로그인 1회 + 읽기 GET 1회, 쓰기 0, production 0)
- 시각 2026-09-28 11:22:39 +0900, 계정 claude_master(staging), 대상 `https://lahom-dev.up.railway.app/erp/as?view=fragment`, W2 반환 명령 그대로.
- 출력 원문:
  - `HTTP/1.1 200 OK`
  - `x-foms-ept-b7-phases: tab_counts=21;list_query=21;rd_normalize=2;rd_attach_q=3;rd_thumbs=0;rd_loop=12;rd_sanitize=0;rd_timeline=11;rd_drift=2;rd_sales_delivery=0;row_display=24`
  - `x-foms-ept-b7-render-ms: 20.2` · `x-foms-ept-b7-route: erp_as_dashboard` · `x-request-id: 7978655962384f00af65a9ffaf1f66c3` · `Content-Length: 36010`
  - `dns=0.008875 tcp=0.045108 tls=0.102481 ttfb=0.323985 total=0.370620 size=36010`
- 계산(W2 읽는 법): 핸들러 ≈ 21+21+24+20.2 = 86ms · 파이썬 CPU ≈ rd_normalize 2 + rd_loop 12 + render 20.2 = 34ms(TTFB 324ms 의 약 11%, 핸들러의 약 40%) · DB 쪽(ORM 조립 섞임) ≈ 21+21+3+0+2+0 = 47ms · ttfb − tls − 핸들러 ≈ 324 − 102 − 86 = 136ms(왕복 + 대기열 + 계측 밖 미들웨어). 표본 1개 — 꼬리 판정 불가, "지금 CPU 몫" 한 점.

## 4. 판정 메모(총괄)
- 이전 후보 G1: C2·C3·C4(워커·네이버)·C5a·C5c 는 막는 증거가 있어 불통과. C4 실시간·C5b 는 막는 증거도 통과 증거도 없어 미확정 → 권고 안 함, ⑦ 에 측정.
- C0·C1 선택: 환산 순이득(결함 fix 비용 기준) 은 모든 후보 음수 — 잴 수 있는 언어 귀속 이득이 거의 0 이기 때문. 규칙대로 기준값 비교 → 백엔드·워커는 C0(−5.8, 묶음) > C1-B(−7.9), 프런트는 C0(−1.3) > C1-F(−10.5). C0·C1-B 는 워커와 백엔드가 같은 foms 코드를 돌리므로 묶음으로 비교한다.
- C0 정의: 9-06 ⑤ 조건 목록에 "상향 패킷" 이 들어 있으므로 C0 는 9-06 #8(상향 패킷 포함)·#9·#12·#13·#15·#16·#17·#23 8항목. C1-B 도 상향 패킷을 포함(겹침) — 두 후보 모두 L1 창을 닫고, 차이는 C1-B 의 3.13·psycopg3·select()·mypy 대 C0 의 거버넌스.

- 초안 작성 완료(보고서 281줄). 초안 §8 기계 검사: `REPORT_OK` · `SECTIONS ①②③④⑤⑥⑦⑧⑨` · `EXTERNAL 22` · `CAND_ROWS 23 HYP_ROWS 8` · `LINES 281 MAX_LINE 795` · `MATCHED 132` · `ANCHOR_BAD 0` · `HANJA 0`. 이어서 리뷰어 R1(반대 심문)·R2(사실 검증) 병렬 발주.

## 5. 리뷰 발견 (전량)

### 5.1 R1 반대 심문 (완료 — 도구 36회, 약 16.5분) — "이전 안 함" 은 유지, 백엔드·워커 "유지(C0)" 표기와 ⑦ 설계가 무너짐

**판정 도전 3개**: ① 타입 강제 대 선택 + 에이전트 되먹임(Gao 2017 JS 버그 약 15% 를 Flow·TS 가 잡음 [https://blog.acolyer.org/2017/09/19/to-type-or-not-to-type-quantifying-detectable-bugs-in-javascript/ · 2026-09-28], Octoverse 2025 TS 사용량 1위·에이전트 코딩 [https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/ · 2026-09-28]) — 이전 대비 지고, C0 대 C1 에서는 이김(C1 몫). ② 언어 경계 이중 구현(`cef5acbb3`·`acd2f2334`·모집단 `a7d82df88`, 파이썬+JS 동반 fix 119/1,073 = 11.1%) — TS 전 스택 대비 지고, C5b G1 을 "부분 증거" 로 올림(G2 는 불통과 쪽). ③ 움직이는 과녁 + 일방통행 — 이전 권고로는 지고, ⑦ 구조 비판으로는 이김.

**발견 16건**
- R1-1 치명 · ①·② C1-B 행·⑧ 1번 — C0 에 상향 패킷을 넣어 C1-B 와 겹침, 가격 불일치(C0 항목 균일 0.5 대 C1-B 상향 1.0·C2 G2 1.5, 감독 통일 C4 G2 1.5 대 C0 0.5, ×1.1 세금 C1-B 만, 이득 0 인 select() 1.5 가 C1-B 에). select() 빼면 C1-B −5.92 대 C0 −5.79 동률, ×1.1 도 빼면 C1-B −5.38 이 앞섬, #8·#23 같은 단가면 C0 −8.8. 이득 ≈ 0 이라 규칙이 "가장 싼 것" 으로 퇴화. → 백엔드·워커 판정을 "같은 언어 현대화 축소판(상향+psycopg3) + C0 감독 통일" 로, 겹침 제거, 비환산 항목으로 결정했다고 명시, C3 G2 15.1 이중 계산 수정.
- R1-2 치명 · ⑦ 1·3·6·7·H8 — 이전 후보 뒤집힘 경로가 산술상 닿지 않음(H8 함정 반복). #1 B→C2 논리 오류, C3 는 B=100% 여도 −41.5, #3 은 G1 만 열고 지연 비환산이라 G3 계산 불가, #6 C5b 임계 넘어도 이득 약 0.33주 < 필요 3.0주, #7 프런트 B ≥ 70% 는 ui-css 29/80 에서 도달 불가. → 후보마다 "G3 통과에 필요한 이득(주)" 명시, 24개월 틀에서 도달 불가 후보는 "사실상 영구 기각" 명시·⑨ 사용자 결정으로, H8 행에 "이 보고서의 이전 판정도 같은 구조" 반영.
- R1-3 중대 · ② C0 백엔드·선택 근거 — "창 밖 24→0" 은 실적 0 약속을 할인 없이 적음(`git log --since=2026-09-06 -- requirements.txt` 출력 없음). "사고 14/15 를 C0 만 겨냥" 과장 — C0 8항목에 #10·#11(사본) 빠짐 → 최대 10/15.
- R1-4 중대 · ⑥ 재작업 항 0 → §3.5 위반. L4 는 네 언어 모두 검사기 없음이라 대조군 없음 → `미확정`. 자료는 로컬 세션 기록 `~/.claude/projects/c--DEV-FOMS/*.jsonl` 115파일 1.3GB(08-29~09-28). ⑦ 에 예외 유형별 실패 측정 추가.
- R1-5 중대 · 09-10 사고 A(조건부) 는 표본 A 규칙("도구만 켜서")과 불일치 → U(B 경계). ① "B 0, U 1".
- R1-6 중대 · ⑤ C3 찬성론이 가장 강한 형태 아님 — Gao 15%·Octoverse 누락, 반박이 노력 크기만 비교(강제 여부·이행률 6% 누락). → 반박을 "같은 강제를 mypy 래칫·checkJs CI 차단으로" 로, Gao 15% 대 FOMS 프런트 A 0/80 차이 설명.
- R1-7 중대 · C5b G2 비교 대상 오류 — 같은 언어 대안은 "서버가 판정 1벌, 화면은 읽기"(`a7d82df88`). G1 부분 증거, G2 `미확정`.
- R1-8 중대 · 언어 경계 이중 구현(mirror)이 A·B·C 틀 밖 — 보조 유형 추가, ⑦ 에 측정.
- R1-9 경미 · 움직이는 과녁 — 2027-03 재평가 시점 C3 비용 병기, 08-31 주 이상치 언급.
- R1-10 경미 · H6 "언어 탓 반박(약)" 과함 → `미확정`(비교군 모두 검사기 없음). R1 재측정: JS 만 건드린 커밋 59.8%·CSS 만 65.0%, 동반 26.5% 대 27.9%.
- R1-11 경미 · C0 낙관 이득 세 값 불일치(2.3·1.16·1.4).
- R1-12 경미 · fix 1,073 중 patch-id 고유 990 — cherry-pick 중복 83건(7.7%, 예 `c63ef424a`/`5714a267f`·`b0c1b372f`/`c78938c79`). F 약 8% 할인 병기.
- R1-13 경미 · C2 G1 — §4.3 은 L1 을 G1 증거로 인정, Flask 2.3 창 밖은 프레임워크 버전 귀속 → G1 통과, G2 에서 막음.
- R1-14 경미 · 보조 스캔에 파이썬 A 누락 — NameError·import 누락 3건(`545b9e833`·`1cd00528d`·`c63ef424a`, ruff F821). JSONB 모양 혼재 `c4cd51c4e`·`b0c1b372f` 는 경계 모델(9-06 #11) 몫.
- R1-15 경미 · R 6% 는 분기 24% 경과 시점 값 — 명시.
- R1-16 경미 · 앵커 부정확(`ledger:117` 은 제목, 이행표 158, F 산정 139·151·161).
**반례 검토**: 표본 12 + 모집단 8건 `git show` — 표본 B=0 은 못 뒤집음. `667f408ac` → U. `32d1bdd4f` B 경계. `b0c1b372f`·`c4cd51c4e` A*(경계 모델). `545b9e833`·`1cd00528d`·`c63ef424a` A(F821). `b2dc9b834` C 유지(alembic check 1.9+, compare_type 1.12 기본 True [https://alembic.sqlalchemy.org/en/latest/autogenerate.html · 2026-09-28], String→UUID 등 검출은 확인 필요). `cef5acbb3`·`acd2f2334` C + mirror. 나머지 C 동의.

### 5.2 R2 사실 검증 (완료 — 도구 39회, 약 9.6분) — 판정 방향을 바꾸는 오류 없음

- **앵커 10개 무작위(시드 `random.Random(20260928)`, 원장 밖 93개 중 9 + 원장 39개 중 1)**: 일치 7 · 부분 3 · 불일치 0. 부분 = ① `docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:27`(5,827ms 는 7·52행) ② `docs/incidents/2026-08-07-...:11`(13시간은 10행, 02-23 TLS 는 워커 아님) ③ ledger:59(수치는 64행). 추가 대조: H1 행 `...rq-failed-jobs-2544-cleanup.md:25` 는 "원장 밖" 만 받침, `tests/conftest.py:41-43` 에 SQLite 언급 없음(부분).
- **외부 5개(같은 시드)**: 일치 4 · 부분 1(Spring 기본 헤더에 CSP 없음). 추가 6개: devguide·endoflife Node·Django 5.2 LTS·Railway 고정 IP·GHSA-q34m 일치. Django `SECURE_HSTS_SECONDS` 기본 0·CSP 기본 없음 → C2 찬성론 "Django 는 보안 헤더를 기본으로" 과장.
- **재실행 수치**: §2.4·ast·L3 표본(82/80, 1·50·80번째)·L4 두 명령 전부 일치. 부가: `hx-` 7곳·2파일, session_transaction 239, TypedDict 0 일치. `innerHTML =` 437(정규식 따라 440)·`fetch(` static+templates 402 대 보고서 438·395 — 근사, 재현 명령 없음.
- **§8 기계 검사**: `REPORT_OK` · `SECTIONS ①②③④⑤⑥⑦⑧⑨` · `EXTERNAL 22` · `CAND_ROWS 23 HYP_ROWS 8` · `LINES 281 MAX_LINE 795` · `MATCHED 132` · `ANCHOR_BAD 0` · `HANJA 0` · 7번 `ONLY_REPORT_FILES_ADDED`(늘어난 줄 = 보고서·원장 2줄).
- **산술 발견**:
  - R2-A1 ⑥ C0 낙관 이득 2.3·순이득 −0.7 재현 불가 — 적힌 식 10/80 × 30.0 × 0.31 = 1.16(순이득 −1.8), 모델 12/80 = 1.4(−1.6). 2.3 이면 "이득 1.5배여도 부호 불변" 문장이 거짓(+0.45).
  - R2-A2 ② C4 네이버 −46.5·실시간 −4.5 는 W4 의 비관·낙관 시나리오 값(배수·꼬리도 다름). 기준 배수로 다시 재면 실시간 약 12.5~13.0주·네이버 약 16.9주. "실시간 = 가장 작은 파일럿 경계" 비용 근거 약 3배 과소.
  - R2-A3 ⑦ 1번 논리 결함 — B 는 "다른 언어로만 막힘" 이라 파이썬인 C2 이득이 될 수 없음(② C2 이득 0 과 모순). 지표를 프레임워크 귀속 결함으로 바꾸거나 B 임계를 C4·C5a 에 연결.
  - R2-A4 "할인 둘 다 걸면 C0 −0.29" 는 정정 전 7/80 값 — 6/80 이면 −0.31.
  - R2-A5 G2 "같은 언어 대안 비용" 기준이 행마다 다름(C2 는 상향분 1.5, C3 는 C0 전체+C1-B, C5a 는 checkJs 3.1, C5b 는 C1-F 전체 10.5). 결론 불변.
  - R2-A6 C4 낙관 이득 1.16 은 백엔드 전체 Wilson 상한 — 한 경계 후보에 전체 이득(이전 쪽에 유리한 과대). 판정 불변.
- **형식 발견**:
  - R2-F1 ② 칸 앵커 의무 광범위 미충족(표 행 101개 중 태그 있는 행 21) — C3·C5a·C5c 칸, C2 G2·G3, C1-F 순이득.
  - R2-F2 ② C4 네이버 G2 "해당 없음" → 통과·불통과·미확정 중 하나로.
  - R2-F3 ⑦ C4 실시간 G2·G3·36개월 `미확정` 칸 전용 측정 없음(5번은 수요만).
  - R2-F4 ⑦ 10번 측정 방법이 "사용자 결정" — ⑨ 로 옮기거나 지표 변경.
  - R2-F5 ⑧ 2·3번 검증에 테스트 경로·명령 없음.
  - R2-F6 원장 앵커 39/132, 그중 20개가 제목 줄 — 어긋난 예: H8 → ledger:117(이행표 158), emit 7 → ledger:27(55), 원장 밖 유실 → ledger:61(76), 사고 B 0 → ledger:61(68), 34ms·11% → ledger:220(223), ④ 100~103행 → ledger:59(62·64·66·83).
  - R2-F7 태그 없는 문장 대표: ① 8~10행 "G1 에서 막힌다" · ④ "사고 15건 — A 1·B 0·C 14" · C2 찬성론 Django 헤더·FastAPI · C2 반박 "HTTP 320 … 14.2주" · C4 "실시간 가장 작은 파일럿" · C5b "innerHTML 이 미러의 원천"(인과 → [가설]) · C5c "타입 컴포넌트가 Jinja 오류 제거"([가설]) · ⑥ C0 낙관 식 · ⑧ 이유 문장(교차 참조뿐, "0건 이행" → "완전 0·부분 1") · 69·138·181행.
  - R2-F8 사실 과장: "ops 7건이 워커 쪽/감독·재시작·env" — 02-23 은 웹 오리진 TLS(`docs/incidents/2026-02-23-503-ssl-unexpected-eof-cloudflare.md:4`), 02-22 는 백필·웹 트리거 → 워커 감독 유형은 08-03·08-07·08-31·09-08·09-09 5건. "조용한 루프 사망 반복" → 루프 사망은 09-10 1건. "Referrer-Policy 1곳뿐" → nosniff 1곳 더(`foms/api/cs/settlement_channel.py:556`). "꼬리는 측정된 서버 구간 밖" → 07-02 측정 구간은 렌더뿐이므로 "렌더 구간 밖". `https://nixpacks.com/docs/providers/python` 은 W1 목록에 있음(원장 111행 목록에는 getting-started 만 적혔으나 W1 반환 16번에 providers/python 포함 — 총괄 확인 필요).
  - R2-F9 한자 0·과대광고 없음·운영 수치 추정 없음. 최상위 제목·② 행 키·⑦ 행 수·⑨ 구성 충족.

### 5.3 총괄 재검증과 반영 결정(1회 반영)

**총괄 재확인**
- R1 "파이썬+JS 동반 fix 119": 제품 파이썬(foms·models·app·db) + JS(static/js·`*_js.html`) 기준 재실행 → `FOMS_PY_AND_JS_FIX 119` 일치(tests 파이썬까지 넣으면 305 — 보고서는 119 를 쓴다).
- R1 patch-id: fix 1,073 의 `git patch-id --stable` 고유 → 990 일치(중복 83, 7.7%).
- R1 `a7d82df88` 본문 8행 "H1(잠겨야 할 집에 체크박스가 열림)이 정확히 그 갈라짐에서 나왔는데" 일치. 세션 기록 `ls ~/.claude/projects/c--DEV-FOMS/*.jsonl | wc -l` → 115 일치.
- R2 사실: `foms/api/cs/settlement_channel.py:556` nosniff 일치 · `tests/conftest.py:33` `sqlite:///:memory:` (41-43 이 아님) · 5,827ms 는 `docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:7` · 13시간은 `docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md:10` · 02-23 은 `docs/incidents/2026-02-23-503-ssl-unexpected-eof-cloudflare.md:4` 에지↔오리진 TLS(워커 아님) · pydantic `requirements.txt:70`.
- 재현 명령: `grep -rnE 'innerHTML\s*=' static/js --include=*.js | grep -v '/vendor/' | wc -l` → 438 · `grep -rn 'fetch(' static/js --include=*.js | grep -v '/vendor/' | wc -l` → 279(templates 포함 399).
- W1 외부 목록 보충: W1 반환 16번에 `https://nixpacks.com/docs/providers/python`(`.python-version` 읽음·기본 3.11, 확인 2026-09-28) 이 있었다 — 111행 목록에 빠뜨린 것.

**수지 모델 v2** (`scratchpad/lead/net_model2.py` — 후보 정의를 겹치지 않게, 단가 통일, 병렬 세션 세금 ×1.1 제거, select() 는 C1-B 전체에만)
- `C0 per boundary {'백엔드': (0.88, 2.4, 7.8), '워커': (0.99, 2.7, 8.78), '프런트': (0.33, 0.9, 2.93)} maint (1.2, 2.4, 6.0) C0 total (3.4, 8.4, 25.5)`
- `C1-B full (2.2, 7.2, 24.7) C1-B min(upgrade+psycopg3) (0.88, 2.4, 7.8) upgrade only (0.55, 1.2, 3.9) mypy only (0.55, 2.4, 7.8) py313 only (0.22, 0.6, 2.6)`
- `C4 realtime (4.52, 12.48, 35.36) worker (5.68, 16.4, 45.35) naver (5.82, 16.86, 46.5)`
- `C0 백엔드 benefit (0.23, 0.02, 0.0) net (-0.65, -2.38, -7.8)` · `C0 워커 benefit (0.35, 0.04, 0.0) net (-0.64, -2.66, -8.78)` · `C0 프런트 benefit (0.58, 0.06, 0.0) net (0.25, -0.84, -2.93)`
- `C1-B min net (benefit 0) (-0.88, -2.4, -7.8)` · `C1-B full benefit (0.35, 0.02, 0.0) net (-1.85, -7.18, -24.7)`
- 필요 이득(기준, = 후보 비용 + 그 경계 최선 같은 언어 순이득): `C2 11.8 · C3 62.6 · C4 워커 13.7 · C4 네이버 14.5(백엔드 기준; 워커 기준 14.2) · C4 실시간 9.8(워커 기준; 웹 = 백엔드 기준 10.1) · C5a 10.5 · C5b 3.5 · C5c 36.3`
- `defect max B=100%: backend 23.5 front 4.4 worker files 0.49 mirror(py+js fix 119/1073) 3.09` · `cherry-pick dup discount F x0.92 (27.6, 25.67, 23.74)`
- `G2: C2 upgrade 1.2 vs 7.1 | C3 C1-B full 7.2 vs 32.5 | C4 worker #23 1.8 vs 8.2 | C5a checkJs 3.1 vs 5.65 | C5c C1-F 10.5 vs 18.55`
- `C3 at 2027-03 [assume +40% line part] 79.1`

**반영 결정**
- 수용(보고서 개정): R1-1(백엔드 = C1-B 축소판 같은 언어 현대화, 워커·프런트 = C0, 겹침 제거·단가 통일, 비환산 항목으로 결정했다고 명시) · R1-2(필요 이득 열, 24개월 틀 도달 불가 명시, H8 자기 비판) · R1-3(창 해소는 실적 0 약속으로, C0 표적 최대 10/15) · R1-4(재작업 `미확정`, ⑦ 세션 기록 측정) · R1-5(09-10 → U) · R1-6(Gao·Octoverse 찬성론, 강제 논거 반박) · R1-7(C5b G1 부분·G2 미확정) · R1-8(mirror 보조 줄 119/1,073) · R1-9(2027-03 C3 약 79주 [가설]) · R1-10(H6 언어 쪽 미확정) · R1-11(C0 낙관 통일) · R1-12(중복 83 한계·F ×0.92) · R1-13(C2 G1 통과·G2 차단) · R1-14(파이썬 A 3건 보조 스캔) · R1-15(R 시점 명시) · R1-16·R2-F6(원장 앵커 정확한 줄로) · R2-A1~A6 · R2-F1~F8.
- 부분 수용: R2-F1(② 칸마다 앵커) — 칸 수가 많아 줄 길이 대신 행마다 대표 앵커 1개 이상으로. R1-8 mirror 를 교차표 열로 넣지 않고 별도 줄로(80건 판정은 W3 원판 유지, 겹치지 않는 유형 8종 고정 규칙 때문).
- 미반영: 없음.

## 6. §8 완료 검증 (개정판 보고서 288줄, 총괄 직접 실행)

- 1 `REPORT_OK` · 2 `SECTIONS ①②③④⑤⑥⑦⑧⑨` · 4 `EXTERNAL 21`(≥5) · 5 `CAND_ROWS 23 HYP_ROWS 8` · 6 `LINES 288 MAX_LINE 1023`(≤500) — 통과.
- 3 앵커 실존 스니펫(글자 그대로): `MATCHED 173` · `ANCHOR_BAD 0` · `HANJA 0` — 통과.
- 7 저장소 무변경: `ONLY_REPORT_FILES_ADDED`. 시작 상태 대비 늘어난 줄은 `?? ...-ledger.md`·`?? ...-report.md` 2줄뿐. 다른 창 변경 없음. HEAD 는 여전히 `fbb391bee`.
- 표본 앵커 5곳(시드 `random.Random(928)`, 원장 밖 4 + 원장 1) 직접 열람 — 전부 보고서 주장과 일치:
  - `foms/services/channel_inbound.py:259` → `log = db.query(ChannelInboundEventLog).get(log_id)` (H7 폐기 예정 `Query.get()` 1곳)
  - `requirements.txt:67` → `psycopg2-binary==2.9.9` (③ L1 표)
  - `tests/domains/test_password_kdf_contract.py:31-33` → `assert prefix == f"pbkdf2:sha256:{FOMS_TEST_PBKDF2_ITERATIONS}"` (해시 문자열 형식 계약)
  - `docs/incidents/2026-09-02-sidefx-dead-effects-1188-missing-kakao-key.md:16` → "SIDEFX 서비스에만 KAKAO_REST_API_KEY 가 없었다" (④ 사고표)
  - 원장 158행 → 9-06 ④ 이행표 (① · ⑧ · H8)
- 종료 시각: 2026-09-28(세션 내). 커밋 없음(지시서대로 사용자 결정).

## 7. 후속 — 사용자 선택 "Flask 올리기 시작" (분석 종료 뒤 별도 작업)

- 사용자 결정: 비밀번호 저장 방식 = 지금과 같게(pbkdf2:sha256 60만 회), 설계서 "이대로 진행".
- 작업 장소: 세션 worktree `c:/tmp/foms-s-flask31`(브랜치 `session/flask31`, base origin/deploy `fbb391bee`) + 격리 venv(공용 Python312 는 손대지 않음). venv 설치: requirements.txt 전체 + pywin32 311(윈도 DPAPI 테스트용).
- 커밋: `0492f4eb9` chore(deps) Flask 3.1.3·Werkzeug 3.1.9·Jinja2 3.1.6 + `hash_password` SSOT(해시 호출 8곳) + urlencoded 1 MiB 한도 복원(`FomsRequest`) + 테스트 레인·KDF 계약 + DECISIONS 1건 + fail-open 인벤토리 · `c0e09e981` AI_STATUS 진행 중 1줄.
- 발견: Werkzeug 3 는 urlencoded 본문에 `max_form_memory_size` 를 걸지 않는다(`werkzeug/formparser.py` `_parse_urlencoded` 주석) → `tests/domains/test_request_body_limits.py::test_form_memory_over_1mib_rejected` 가 200 을 받음 → FOMS 가 직접 한도를 건다(chunked 포함 단위 테스트 추가).
- 검증: venv APP_OK · 전체 스위트 `10416 passed, 614 skipped` · tests/harness `543 passed`(첫 회 2건 xdist 순서 의존 sys.path 오염 — 재실행 2회 모두 통과, Flask 무관) · 기존 Flask 2.3 에서도 관련 36 passed · `pre_push_smoke.ps1`(venv PATH) `=== PRE-PUSH SMOKE PASSED ===` 종료 0.
- 상태: origin/deploy 대비 ahead 2, behind 0. 푸시 대기(사용자 확인 필요). 잔여: 스테이징 로그인·사진 업로드·Socket.IO 확인.
- 푸시: `git push origin HEAD:deploy` → `fbb391bee..c0e09e981`. `ci_watch.py` → `ALL GREEN ✓`. `check_deploy_drift.py` → `[판정 불가] railway list 실패(exit 1): Unauthorized` (Railway CLI 로그인 만료).
- 스테이징 반영 직접 확인: `GET /healthz` → `{"commit":"c0e09e981467df43804b580480ff9c387849b0bd","status":"ok"}` (web). WORKER·cron·SIDEFX 반영은 CLI 불가로 미확인.
- 스테이징 확인(claude_master, 읽기 + 로그인): LOGIN_OK(기존 pbkdf2 해시 대조) · `/erp/dashboard?view=fragment` 200 353,243B 582ms · `/erp/as?view=fragment` 200 474ms · `/erp/measurement` 200 902ms · `/erp/history/` 200 374ms · Socket.IO polling 핸드셰이크 200(sid 발급, upgrades websocket). 사진 업로드는 미확인(쓰기).
- 후속 커밋 `b9084fdd7` AI_STATUS 진행 중 줄 갱신 → smoke 통과 시 deploy 푸시(백그라운드).
- 스테이징 사진 업로드 확인(사용자 선택, 스크래치 `lead/staging_upload_check.py`): 시험 주문 `POST /api/erp/order-draft/submit` → 200 order_id 4754(CLAUDE-TEST-FLASK31, 010-0000-0000) · 멀티파트 `POST /api/orders/4754/attachments`(640×480 JPEG 5,429B, category measurement) → 200 · 목록에 id 2120 표시, 썸네일 약 3초 뒤 생성 · 정리 `DELETE .../attachments/2120` 200 · `POST /delete/4754` 302 → 재조회 `/api/orders/4754/structured` 404·살아 있는 첨부 0. 썸네일이 RQ 워커로 났는지 스레드풀 폴백으로 났는지는 구분 못 함.
- 운영 승격(사용자 요청): `promote_own_to_production.py --shas 0492f4eb9` → 완전성 INCOMPLETE(baseline deps 4: `0e63b7f6`·`2afa9453`·`ca687c49`·`8a709e77`) exit 2. 대조: 0492f4eb9 가 건드린 12파일 모두 `origin/production`(`74b748141`) 과 0492f4eb9^ 가 md5 동일 → 오탐. 사용자 승인 뒤 `--allow-incomplete` → PR #431(`promote/own-1790577931-29608`, head `c0a103a32`, 부모 = origin/production). 문서 커밋 c0e09e981·b9084fdd7 은 deploy 에 둠.
- 승격 트리 검증(`c:/tmp/foms-promo-flask31`, Flask 3 venv): APP_OK · 전체 스위트 `10416 passed, 614 skipped` · PR 검사 harness·perf-gate·pg-lane·test 전부 pass. pre_push_smoke 진행 중.
- 승격 트리 pre_push_smoke(Flask 3 venv) → SMOKE_EXIT 0 · `PRE-PUSH SMOKE PASSED` · 트리 변경 없음.
- 사용자 지시 "스테이징에서 이상 없으면 합쳐" → 스테이징 재확인: `/healthz` commit `b9084fdd7` · 로그인 OK · `/erp/dashboard`·`/erp/as`·`/erp/shipment`·`/erp/drawing-workbench` 200 · Socket.IO 200(`/admin/naver/workbench` 404 는 경로 오기 — 실제 라우트 아님). → `gh pr merge 431 --merge` → MERGED, production 병합 커밋 `ec7e5d843`. 운영 CI·`/healthz` 반영 확인 진행 중(백그라운드).
- 운영 반영 확인: `ci_watch.py ec7e5d843 production` → `ALL GREEN ✓`. 운영 `/healthz`(비로그인 GET, 1분 간격) 5번째에 `commit=ec7e5d843639` → PROD_DEPLOYED(병합 뒤 약 4~5분). WORKER·cron·SIDEFX 반영은 Railway CLI 인증 만료로 미확인.
- 상태 문서: AI_STATUS 스택 줄 `Flask 2.3` → `Flask 3.1`, 진행 중 줄 = production `ec7e5d843`·잔여 워커 반영 확인 → 커밋 후 smoke → deploy 푸시(백그라운드).
- 상태 문서 커밋 `4aff84dbd` → smoke 0 → deploy 푸시(`b9084fdd7..4aff84dbd`) → CI `ALL GREEN ✓`. 검증용 승격 트리 `c:/tmp/foms-promo-flask31`(detached, .env 사본만 있음) 제거. 남은 것: 세션 worktree `c:/tmp/foms-s-flask31`(venv·.env 사본) 정리, 워커 서비스 반영 확인(railway login 필요).
- 운영 로그인 1회 확인(사용자 요청, `docs/guides/REAL_SERVER_TEST_ACCOUNT.md` 절차): 사용자가 `railway login` → 스크래치 `rw-prod` 에만 `railway link -p FOMS-PRODUCTION -e production -s Postgres` → 상태 `(57, False, 'pbkdf2:sha256:600000')` → 해제(is_active 만, 1행) → LOGIN_OK(기존 pbkdf2 해시가 Werkzeug 3 에서 대조) · `/healthz` ec7e5d843 · `/erp/dashboard` 200 429ms(render 59.2) · `/erp/as` 200 442ms(82.4) · `/erp/shipment` 200 1,187ms(150.5) · `/erp/drawing-workbench` 200 695ms · Socket.IO 200 · `GET /logout` 405(POST 전용 — 계정 재잠금으로 세션 무효, `foms/web/auth/routes.py:286` is_active 검사) → 재잠금(1행) → `(57, False, ...)`. 비밀번호 무변경. 끝나고 `railway unlink`.
- 서비스별 배포: `check_deploy_drift.py` → production ec7e5d84·staging 4aff84db 일치(웹만). `railway deployment list --service <svc>` → 운영 WORKER·FOMS-cron·SIDEFX·web 전부 `SUCCESS ec7e5d843`(2026-09-28T07:07Z).
- 상태 문서 커밋 `85c2fb2c3`("잔여 없음") → smoke 0 → deploy 푸시(`4aff84dbd..85c2fb2c3`). 그 CI 실행(36392342398)은 `cancelled` — 다른 창이 곧바로 `fc21fe95f` 를 푸시해 동시 실행 규칙으로 끊김. 검증은 아래 다음 커밋 CI 가 덮는다.
- 사용자 선택 "둘 다 하기": (1) `docs/guides/REAL_SERVER_TEST_ACCOUNT.md` 비밀번호 교체 1단계를 `werkzeug.security.generate_password_hash` → `foms.services.security.password_policy.hash_password` 로(직접 호출은 Werkzeug 3 기본값 scrypt 로 저장). 커밋 `806b2e761` → smoke 0 → deploy 푸시(`fc21fe95f..806b2e761`) → `ci_watch.py` `ALL GREEN ✓` → `check_deploy_drift.py` production ec7e5d84·staging 806b2e76 일치 exit 0. (2) 세션 worktree 정리: `session_worktree.py cleanup` 미리보기에서 flask31 외에 meas-unify·measure-deadend 도 removable 로 나와 `--remove`(일괄) 대신 flask31 만 같은 규칙(미커밋 0·origin/deploy 에 합쳐짐 확인, 강제 없음)으로 `git worktree remove` → exit 0, `git branch -d session/flask31`, 폴더·venv·.env 사본 삭제 확인. 다른 창 worktree 는 손대지 않음.
- 사용자 선택 "DB 연결 부품 바꾸기 계획" → `docs/plans/2026-09-28-psycopg3-migration-plan.md`(157줄, 코드 변경 0). 핵심 사실: 드라이버 없는 `postgresql://` 엔진이 운영 경로 5곳(SIDEFX `sidefx_worker.py:135`, cron 3곳, alembic `env.py:127-129`)이라 psycopg2 를 먼저 빼면 멈춤 · `ensure_schema.py` 는 predeploy 에서 psycopg2 직접 사용 · psycopg3 오류에 `pgcode` 없음(3.3.6 `errors.py`) · psycopg3 는 import 시점에 gevent 대응 결정(`waiting.py:505-562`). 권고: 1단계(드라이버 이름 한 곳, 동작 변화 0)만 먼저, 2단계는 `ClientCursor` 로.
- 사용자 선택 "1단계 시작" → 세션 worktree `c:/tmp/foms-s-pgdriver`(branch `session/pgdriver`, base `69794c367`, 격리 venv). 커밋 `13962a7c0` refactor(db) 드라이버 정본 `db_url_resolver`(PG_SQLALCHEMY_DRIVER="psycopg2"·sqlalchemy_url·postgres_dbapi_connect·pg_error_code), 34파일. 계획 문서는 이 커밋으로 저장소에 들어갔고 메인 트리 미추적 사본은 삭제(pull 충돌 방지). 검증: 대상 테스트 207 passed · 새 계약 11 passed(운영 경로 5곳 음성 대조: 옛 bare URL `engine.url.drivername == "postgresql"`) · 전체 11152 passed(tests/visual 24 error 는 file-backed SQLite 전제 — CI 메인 레인은 `--ignore=tests/visual`) · PG 레인 로컬 PostgreSQL 17(5441, 새 initdb) 794 passed · APP_OK · smoke 0 → deploy 푸시 `69794c367..13962a7c0` → CI `ALL GREEN ✓`. `check_deploy_drift.py` → Railway Unauthorized(로그인 만료) → 웹 `/healthz` 로 대체 확인 중.
- 단계 1 스테이징 확인: `/healthz` 17:23:54 `13962a7c0`(이후 다른 창 `6e74afe59` — `merge-base --is-ancestor` 로 포함 확인, 내 파일 무변경). 배포 전 단계(alembic `env.py`·`ensure_schema.py`)가 통과해야 web 이 뜨므로 alembic 경로 동작 확인. 로그인 OK · `/erp/dashboard?view=fragment` 200 601ms · `/erp/as?view=fragment` 200 · `/erp/measurement` 200 · `/erp/history/` 200 · `/erp/shipment` 200 · 계산기 DB `GET /api/wdcalculator/products` 200 items=27 · Socket.IO 200. `/api/foms/ops/worker-heartbeats`(admin, 읽기): SIDEFX DELIVERY·EXPIRY_SCAN·RETENTION 나이 5초, WORKER 루프 5종 신선, not_ready 0. 단 `ready:false` = `dead_count` 42(DEAD 전체 누적 수, `sidefx_worker.py:607`). 약 10분 간격 2회 모두 42로 늘지 않음. 매일 점검 워크플로의 "DEAD 0건"은 production 대상(`heartbeat_report_http.py:51`)이라 스테이징 기준값이 아님 → DEAD 발생 시각은 Railway 로그인 없이 확인 불가(열린 항목). 미확인: SIDEFX·WORKER·cron 서비스별 배포 커밋(`check_deploy_drift` Unauthorized), cron 다음 실행(KST 02:00).
- 사용자 `railway login` 뒤 확인: `check_deploy_drift.py` exit 0 — production `5f2662d3`(다른 창, 내 커밋 미포함 — 정상) · staging `aa78befd`(내 `13962a7c0` 포함). 스크래치 `rw-dev` 만 `link -p FOMS-DEV`(status name=FOMS-DEV): `deployment list` → FOMS(web)·worker·SIDEFX·FOMS-cron 전부 `SUCCESS aa78befd5`(08:30Z), 그 앞 `13962a7c0`(08:20Z)·`6e74afe59` 는 REMOVED(대체). DEAD 42건 읽기 전용 조회(DSN 파일 → 가드 project=FOMS-DEV·host maglev:24958·TESTCLR 10행, `default_transaction_read_only=on`): GEOCODE 25(09-20~09-28 07:15Z, GeocodeTransientError) · STAGE_NOTIFICATION 11 + CHANNEL_PUSH_RECORDED 4 + NOTIFICATION 1(모두 09-01 05:28Z, NoHandlerError) · HOLD_NOTIFICATION 1(09-20). **내 배포(08:20Z) 이후 DEAD 0건** → 단계 1 무관. DSN 파일 삭제·`unlink`·status "No linked project". 참고: `C:\DEV\FOMS`·`C:\tmp` 가 FOMS-PRODUCTION 에 링크돼 있음(이 세션 무관, 미변경) → 메모리 기록.
- 스크립트 실행 확인: cleanup_order_drafts·purge_audit_logs·purge_order_mutation_receipts·purge_domain_side_effect_outbox·run_domain_side_effect_outbox 를 저장소 밖 cwd(`/c`)에서 `--help` → 전부 exit 0(sys.path 부트스트랩 동작). 사용자 선택 "내일 야간 정리 본 뒤 운영 올리기" → 오늘은 멈춤. 다음: 스테이징 FOMS-cron 02:00 KST(17:00Z) 실행 로그 확인 → 이상 없으면 `promote_own_to_production.py --shas 13962a7c0`. worktree `c:/tmp/foms-s-pgdriver`(venv·.env 사본) 유지.
- [2026-09-29] 야간 정리 확인(스테이징, 스크래치 rw-dev link FOMS-DEV): FOMS-cron 활성 배포 `5fca92111`(12:55Z) — `13962a7c0` 포함·내 파일 무변경. 대시보드 startCommand(GraphQL `serviceInstance`) = cleanup `&&` purge_order_mutation_receipts `&&` purge_audit_logs, cron `0 17 * * *`. 09-28T17:04Z 실행 로그: `[cleanup_order_drafts] mode=execute scanned=0 deleted=0 ... elapsed=0.6s` → **새 코드(sqlalchemy_url 경유)로 DB 연결·조회 정상**. 단 purge 두 도구 출력 없음. 변경 전 배포 `dc5842f87`(09-24~09-27 실행)도 **똑같이 cleanup 한 줄만** → 단계 1 무관한 기존 문제. DB 읽기 전용 확인: `order_mutation_receipts` 중 7일 넘게 만료된 행 368/399(가장 오래된 expires_at 2026-08-04) → **스테이징에서 purge 가 실제로 돌지 않는다**(보존 정책 미집행). 메모리 2026-09-14 기록("purge 두 줄 없음·DB 미삭제")과 같은 증상 — 대시보드 명령은 이제 맞으므로 원인은 다른 곳. 운영 여부 미확인. DSN 파일 삭제·unlink 완료.
- [2026-09-29] 야간 정리 purge 미실행 원인(사용자 선택 "지우기 문제 원인부터"): 스테이징·운영 FOMS-cron 활성 배포의 `meta.serviceManifest.build.builder` = **DOCKERFILE**(`/Dockerfile` 자동 감지 — 서비스 설정 RAILPACK·toml nixpacks 와 다름). Railway 문서(https://docs.railway.com/guides/start-command, 확인 2026-09-29): Dockerfile 빌드는 start command 가 ENTRYPOINT 를 **exec form(셸 없음)** 으로 덮는다. 관측: 두 환경 모두 실행 로그에 cleanup 한 줄만, purge 두 도구는 성공·SKIPPED·failed 어느 줄도 없음(세 경우 모두 로그를 남기는 코드) → 프로세스가 시작조차 안 함. cleanup 은 `parse_args()` 엄격 파싱이라 `&& python ...` 가 인자로 넘어왔다면 unrecognized arguments 로 죽었을 것 → Railway 가 `&&` 뒤를 **버리고 첫 명령만** exec 한 것으로 판단(직접 증거는 아님, 유일하게 모순 없는 설명). 영향(읽기 전용 집계): 스테이징 만료 7일 초과 receipt 368/399(최고 2026-08-04), **운영 2952/4359(최고 2026-09-07)**. 감사 로그 4표는 보존 기간 초과 행 0 → purge_audit_logs 미실행의 현재 영향 없음. 운영 조회: 가드 FOMS-PRODUCTION·yamanote:34306·`default_transaction_read_only=on`, 집계만, DSN 파일 삭제·unlink. 09-14 메모리의 "대시보드 필드가 실행된다" 결론은 이 원인으로 대체.
- [2026-09-29] 사용자 승인 "상황판은 운영 것 그대로 두고 올리기": 승격 도구 INCOMPLETE(baseline deps 21) → 13962a7c0 이 건드린 파일 중 운영과 다른 것은 AI_STATUS·failopen 인벤토리·표면 계약(2478행대, 내 편집 413행대와 무관) 3개뿐. 시험 트리(`c:/tmp/foms-promo-pgcheck`, origin/production)에 cherry-pick → 충돌 AI_STATUS 1곳만 → 운영 쪽 유지, 인벤토리 최신, 대상 테스트 237 passed·APP_OK. 운영이 PR #434(824b2c1d3)로 전진해 rebase → 33파일. smoke 0 → 브랜치 `promote/own-1790639126-pgdriver` → **PR #435** 검사 harness·perf-gate·pg-lane·test 전부 pass → merge `0b356a0cb` → 운영 `/healthz` 08:53 반영, check_deploy_drift 일치, 운영 서비스 web·WORKER·SIDEFX·FOMS-cron 전부 `SUCCESS 0b356a0cb`(23:52Z).
- [2026-09-29] 사용자 승인 "야간 청소 이대로 만들기": `tools/cron/nightly.py`(단계 3개 subprocess, 단계 독립, 20분 제한, 요약 줄), toml·configure 도구 상수·verify ps1 needle = `python tools/cron/nightly.py`. 계약: `test_cron_purge_wiring.py` 개정(러너 단계·셸 연산자 금지·옛 명령 음성 대조), `tests/domains/test_nightly_cron_runner.py`(실패·시간초과 뒤에도 나머지 실행). 12 passed. 종단 확인: 로컬 PostgreSQL 17 새 DB(create_all) + 30일 지난 receipt 1행 → 셸 없이 `subprocess.run([python, tools/cron/nightly.py])` → exit 0, 세 단계 모두 로그, purge deleted=1, 남은 receipt 0. (훅이 DROP DATABASE 를 막아 새 이름 DB 로 진행.)
- [2026-09-29] 야간 러너 배포: 전체 10975 passed(tests/visual 제외, CI 와 같음) → 커밋 `ef6124476` → smoke 0 → deploy 푸시(`44ee4d195..ef6124476`) → CI `ALL GREEN ✓`. 스테이징 FOMS-cron 새 배포 `929fb6ee` SUCCESS, 배포 메타 startCommand 이미 `python tools/cron/nightly.py`(toml 반영), builder 여전히 DOCKERFILE. `railway_configure_cron_service.py --target staging --dry-run`(Before = 옛 체이닝, latestDeployment = 929fb6ee 로 대상 확인) → 적용: 대시보드 startCommand `python tools/cron/nightly.py`·cron `0 17 * * *` → 재배포 `8901a9c4` SUCCESS `ef6124476`. 시험 승격 트리 `c:/tmp/foms-promo-pgcheck` 제거. 다음: 오늘 밤 17:00Z 실행 로그에 `[nightly]` 세 단계 줄·스테이징 만료 receipt 368 → 0 확인 → 사용자 요청 시 운영 승격 + `--target production`.
- [2026-09-29] 사용자 "지금 진행 해봐" → 스테이징 즉시 실행: GraphQL `deploymentInstanceExecutionCreate(serviceInstanceId=31dabdf3…)`(가드: serviceInstance 가 스테이징 FOMS-cron·startCommand `python tools/cron/nightly.py`). 실행 전 읽기 전용 기준값 만료>7일 receipt 368/399. 00:32:47Z 실행 로그: cleanup rc=0 → `[purge_order_mutation_receipts] ... scanned=368 deleted=368 batches=1` rc=0 → purge_audit_logs 4표 0건 rc=0 → `[nightly] done steps=3 failed=none`. **Railway 에서 처음으로 purge 가 실제로 돌았다.** 실행 뒤 재집계는 아래 줄.
- 재집계(읽기 전용): 스테이징 만료>7일 receipt **0**, 전체 399 → 31(남은 31건은 7일 안 된 것). DSN 파일 삭제·unlink.
- [2026-09-29] 사용자 "운영 올리고 바로 한 번 돌리기": 시험 트리 `c:/tmp/foms-promo-nightly`(origin/production=0b356a0cb) cherry-pick `ef6124476` → 운영과 다른 파일은 AI_STATUS 하나(코드 7파일 모두 운영과 동일) → 앞 승격과 같은 방식(운영 쪽 유지) → 인벤토리 최신·대상 42 passed → smoke 0 → **PR #436** 검사 4종 pass → merge `59afb4c33` → 운영 `/healthz` 09:56 KST 반영, 운영 FOMS-cron `9e80436e SUCCESS 59afb4c33`. `railway_configure_cron_service.py --target production`(dry-run: instance `ffb3acba…`, Before 옛 체이닝) → 대시보드 `python tools/cron/nightly.py` → 재배포 `f5cba046 SUCCESS`. 읽기 전용 기준값: 만료>7일 **2998** / 전체 4442 / 활성 454. 가드(serviceInstance id·startCommand) 뒤 `deploymentInstanceExecutionCreate` → 00:59:30Z 로그: cleanup rc=0 → receipt purge batch 1000·1000·998 = **deleted=2998** rc=0 → 감사 로그 4표 0 rc=0 → `[nightly] done steps=3 failed=none`. 재집계: 만료>7일 **0** · 전체 1444 · **활성 454 그대로**. DSN 파일 삭제·unlink. 승격 시험 트리 제거. AI_STATUS "잔여 없음" 커밋 → deploy(백그라운드).
- [2026-09-29] 사용자 "연결 부품 2단계 준비": 단계 0 수행. ① 중계기: 스테이징·운영 web `DATABASE_URL` 호스트 `postgres.railway.internal:5432`(pooler 아님). ② 기준선: deploy 마다 perf-gate CI. ③ gevent 협력(로컬 PG17, 8×pg_sleep 0.5): 패치 없음 4.09s · app.py 패치 0.52s · patch_all 만(psycogreen 없음) 4.06s. psycopg 3.3.6 을 **작업 폴더 venv 에만** 설치(사전 고지, requirements 무변경)해 미리 보기: 패치 없음 4.08s · 패치 뒤 import 0.515s · 패치 전 import 도 0.515s(Windows 는 wait_c 미사용 → 순서 위험은 Linux 에서만). 커밋 `b03fec6bb` test(db): `tests/postgres/test_gevent_db_cooperation_pg.py`+`gevent_db_probe.py`(app.py 실제 패치 블록 AST 실행, 음성 대조 no-patch ≥3.2s), `tests/contracts/runtime/test_gevent_patch_runs_first.py`. harness·contracts 786 passed → smoke 0 → deploy → CI ALL GREEN, **PG 레인(Linux, postgres:16) 756→758 passed·skipped 11 동일 → 새 시험 2개가 CI 에서 실제 실행·통과**. 부수: Railway `~/.railway/config.json` 이 끝에 `}` 한 글자 남는 손상(동시 쓰기 추정) → 고치려 했으나 그 사이 CLI 가 다시 써서 정상화(내 변경 없음). 이 과정에서 설정 파일 꼬리를 출력하다 **자격 증명 일부가 대화에 노출** → 사용자에게 `railway logout`·재로그인 권고.
- [2026-09-29] 사용자 "2단계 본 작업 시작": worktree `c:/tmp/foms-s-pgdriver`(session/pgdriver). 변경 = resolver 드라이버 `psycopg`+ClientCursor, Engine connect 이벤트(URL 엔진에도 ClientCursor), app.py psycogreen 삭제, requirements psycopg[binary]==3.3.6 추가·psycogreen 삭제(psycopg2-binary 유지), 마이그레이션 7개 COMMIT 트릭 → autocommit_block, 계약 3종 + PG 시험 `test_psycopg_client_binding_pg.py`. 첫 PG 레인 2 failed(AmbiguousParameter `$1` = URL 엔진 서버 바인딩 / DROP INDEX CONCURRENTLY in transaction = psycopg2 트랜잭션 미추적 의존) → 근본 수정 뒤 **PG 레인 798 passed**, 전체 11038 passed, APP_OK. 커밋 `39e959883` → smoke 0 → rebase → 재smoke 0 → **push 거부(deploy 선행 이동)** — ci_watch 가 로컬 커밋을 보고 "워크플로 없음 green" 이라 해서 착각할 뻔함(푸시 출력 hint 로 발견). → rebase·smoke·push 재시도 루프(백그라운드 bu551g27u). 다음: CI green → 스테이징 확인(로그인·화면·쓰기·업로드·Socket.IO·계산기·하트비트·야간 즉시 실행·서비스 로그 psycopg 오류) → 운영은 사용자 요청 시.
- [2026-09-29] 단계 2 deploy: 재시도 루프 1회차에 `b28412a9a` 푸시(base 78e308284, smoke 0) → CI ALL GREEN, **CI PG 레인(Linux postgres:16) psycopg-3.3.6 설치·760 passed·skipped 11**(758+새 2). 스테이징 서비스 4종 `SUCCESS b28412a9a`. 확인: 로그인 · `/healthz` b28412a9a · 화면 5개 200(대시보드 447ms·AS 516ms·실측 1008ms·이력 276ms·출고 321ms) · 계산기 DB 27 · Socket.IO 200 · 하트비트 8종 전부 ready(not_ready 0) · 쓰기: 시험 주문 4756 생성 → 사진 업로드 → 워커 썸네일 약 3초 → 첨부·주문 삭제 · 야간 즉시 실행(04:36Z) 3단계 rc=0(receipt 3 삭제) · 서비스 로그(배포 뒤 ~4분): web 610줄·SIDEFX 10줄 DB 오류 0, worker 는 썸네일 재사용 확인용 R2 `head_object` 404 트레이스 1건(`foms/services/storage.py:257-259` 정상 경로, 같은 잡 3초 뒤 Successfully completed) 뿐. DEAD 42→43 은 GEOCODE 03:11Z(배포 전, 기존 일시 실패와 같은 종류). DSN 삭제·unlink.
- [2026-09-29] 사용자 "운영 올리고 로그인 1회도 확인": 시험 트리(`c:/tmp/foms-promo-pg2`, 첫 시도는 `--no-commit` 뒤 abort 불가 → worktree remove 가 세션 cwd 잠금으로 Permission denied → 이어진 명령 일부가 `c:/tmp/foms-s-pgdriver` 에서 실행됐으나 자기 HEAD cherry-pick 이라 변경 0 확인·빈 폴더 삭제 → 새 이름 `foms-promo-pg2b`, 이후 `git -C` 로만 조작). origin/production(229d305c5) 에 `b03fec6bb`(단계 0 시험) → `b28412a9a`(단계 2) cherry-pick, 충돌 AI_STATUS 만(운영 쪽 유지), 인벤토리 최신·52 passed·APP_OK → smoke 0 → **PR #445** 검사 4종 pass → merge `2f9d73d1d` → 운영 `/healthz` 13:51 KST, 서비스 web·WORKER·SIDEFX·FOMS-cron 전부 `SUCCESS 2f9d73d1d`. 운영 claude_master 1회: status `(57, False, pbkdf2:sha256:600000)` → unlock 1행 → LOGIN_OK · 대시보드 200 474ms(render 109) · AS 200 631ms · 출고 200 1076ms · 도면 워크벤치 200 410ms · 계산기 API 200(목록 형식 파싱 실패로 개수 미확인) · 하트비트 200 not_ready 0·DEAD 0·9종 신선 · Socket.IO 200 · lock 1행 → `(57, False, …)` 비번 무변경. 운영 야간 즉시 실행(04:52Z): cleanup deleted=1 · receipt deleted=124 · 감사 0 · `failed=none`. 배포 뒤 서비스 로그(약 2.5분) web 293·WORKER 42·SIDEFX 3줄 DB 오류 0. 승격 트리 제거. AI_STATUS 운영 반영 커밋 → deploy(백그라운드).
- [2026-09-29] AI_STATUS 운영 반영 커밋 `64faf95cd` → smoke 0 → deploy(`997139c4f..64faf95cd`) → CI ALL GREEN. 남은 것: 단계 3 승인 대기, worktree `c:/tmp/foms-s-pgdriver` 정리, railway 재로그인 권고.
- [2026-09-29] psycopg3 단계 3 구현: ensure_schema(predeploy)·data_doctor·bulk_complete·naver_return_watch·scripts/migrations 7개를 psycopg 로, requirements 에서 psycopg2-binary 삭제, pg_error_code sqlstate 만. psycopg2 없는 venv 전체 11059 passed. PG 레인 1건 실패(튜플 IN — psycopg 는 튜플을 IN 목록으로 안 풂) → ANY/ALL + 계약 test_no_tuple_placeholder_after_in. 커밋 f620c7743(rebase 전), deploy push 진행.
- [2026-09-29] 단계 3 deploy `3d08ab91c`: CI 4종 green(PG 레인 760 passed, psycopg2 미설치), 스테이징 4서비스 SUCCESS, predeploy ensure_schema [SCHEMA] 완료(psycopg), 로그인·화면 5·계산기 27·socket.io OK.
- [2026-09-29] **단계 2 결함(운영)**: SQLAlchemy psycopg 방언의 RENDER_CASTS 가 파이썬 값 형으로 `'4445'::VARCHAR` 를 붙여 AS 방문일 저장 500. ClientCursor 는 이걸 못 막는다(내 설계 결정 1 의 빈틈 — 레인 시험이 정수 id 만 썼다). 다른 세션이 `41dc29b62`(bind_typing=NONE 하위 방언, PR #446) 로 고침. 그 하위 클래스에 `supports_statement_cache = True` 가 없어 SQL 컴파일 캐시 꺼짐 — 스테이징 web·worker·SIDEFX 로그 경고, 로컬 측정 단순 select 컴파일 300회 300ms→100ms(플래그 켠 뒤). 한 줄 수정 필요.
- [2026-09-29] 캐시 한 줄은 다른 세션이 먼저 고침(`671e9a2e7`, 운영 PR #447). 내 쪽은 DB 없이 도는 계약만 `7078e5869`(deploy, CI green).
- [2026-09-29] **단계 3 운영 시뮬레이션**(사용자 지시 "철저히 파악 후 이상 없으면 올려"): 시험 트리 = production `550df27f0` + 3d08ab91c + 7078e5869, requirements 만으로 새 venv(psycopg2 없음, pip check 깨끗).
  - predeploy: 운영 스키마 사본(pg_dump -s 읽기 전용, pgvector 칸 대체) 에서 현재 운영 코드 vs 새 코드 → 둘 다 exit 0·출력 동일·결과 스키마 0줄 차이·운영 스키마엔 변화 0.
  - 서비스 진입점(SIDEFX once·야간 3단계 dry-run·rq worker) 운영 스키마 사본에서 OK.
  - SQL 동등성: PG 레인 전 문장 최종 SQL 을 psycopg2 vs psycopg 로 녹화·비교(짝 10,232) — 표기 차이만(시각 T/공백, UUID·NULL cast 없음, 정수 목록 '{..}'::int4[], JSON ::jsonb/::json). designer 13칸 모델 JSON vs 운영 jsonb — json→jsonb 대입 cast 로 저장 OK, 비교 코드 0.
  - yield_per(서버 쪽 바인딩) 12곳 46변형 운영 스키마 사본에서 OK. 차이는 None 을 두 형 문맥에 쓸 때만(코드 0).
  - 잠금 대기 초과 55P03 판정 실측 OK(음성 대조 42703). 운영 도구 읽기 전용 스테이징 실행 old/new 출력 동일.
  - 스테이징: 쓰기 흐름(문자열 id 날짜 저장 5/5·사진)·야간 즉시 실행 failed=none·트레이스백 0·캐시 경고 0. 되돌리기 리허설 깨끗.
  - 운영 PR #448 생성, 검사 대기.
- [2026-09-29] **단계 3 운영 완료**: PR #448 → production `52b978b2f`, 검사 4종 green, 서비스 4종 SUCCESS, drift 일치, healthz 52b978b2f. 운영 predeploy 출력 = 시뮬레이션. 배포 뒤 11분 응답 1,177(5xx 0), 실사용 쓰기 정상, outbox DEAD 0, 하트비트 신선. 로그인 확인은 안 함(요청 없음). 상태판·계획 `28ef21c7e`(deploy, CI green). 시뮬레이션 폴더·DSN 파일·스키마 덤프 삭제. 남은 것: 오늘 밤 운영 야간 청소 첫 실행 확인, pgdriver 작업 폴더·로컬 PG 시험 DB 정리.
- [2026-09-29] 사용자 선택 3건: ① 운영 로그인 1회 확인(claude_master 해제→읽기 GET→재잠금 is_active=False): 대시보드·AS·출고·도면 워크벤치 200, 하트비트 not_ready 0·dead 0, socket.io 200, healthz 287782ce3(단계 3 포함). ② 내일 야간 청소 확인 예약(세션 전용 일회 작업 a827405d, 2026-09-30 08:47 KST). ③ 정리: 로컬 PG 시험 클러스터(5441) 정지·삭제, 작업 폴더 foms-s-pgdriver·브랜치 session/pgdriver 삭제(커밋은 모두 deploy 에 있음).
- [2026-09-29] 사용자 "해야 될 일 목록 → 필수 순" 선택: 1·3·4·5·6·7·8(2 레일웨이 재로그인은 사용자가 직접 — 완료, 링크 유지 확인). 작업 폴더 `c:/tmp/foms-s-chores0929`.
  - 1: `.gitignore` 에 `.env.bak*`(비밀값 백업 사본 커밋 방지, `.env.example` 영향 없음) + 메인 저장소 `.git/info/exclude` 에도 같은 줄(즉시 보호).
  - 3: 이 원장·지시서·보고서를 저장소에 올림(비밀값 검사: DSN·토큰·비번 0, 프록시 호스트 이름은 이미 추적 파일에 있음). 이후 원장 기록은 추적 파일에.
  - 5: designer 13칸 `JSON` → `JSON_PG_JSONB`(운영 jsonb 와 일치, SQLite 는 JSON 그대로). 스냅숏 계약 `tests/domains/test_designer_json_column_types.py`(운영 스키마 2026-09-29 기준 jsonb 13·json 34, 음성 대조).
  - 8: `datetime.utcnow()` 5곳 → `now_utc_naive()`, `Query.get` 16곳 → `Session.get`, 테스트 잘못된 이스케이프 1곳. 남김: SQLite `DISTINCT ON` 경고(SQLAlchemy 계획에서), sqlite3 기본 날짜 어댑터 경고(테스트 레인), `run_erp_draft_orders` 의 `datetime.now()` 로컬 시각(운영 UTC 라 동일, 기준축 변경은 동작 변경이라 범위 밖).
- [2026-09-29] 선택 4·6·7 은 코어라 문서부터: 설계서 `docs/specs/2026-09-29-worker-loop-supervisor-spec.md`(WORKER 배경 루프 5개 무감독 확인 — `start.sh:23-73` `&` 한 번 실행, RQ 만 감독. 실제 빌드는 네 서비스 모두 Dockerfile — 운영·스테이징 배포 manifest `builder=DOCKERFILE`, toml 의 nixpacks 는 죽은 설정), 계획 `docs/plans/2026-09-29-sqlalchemy-2-0-54-upgrade-plan.md`(2.0.24~54 변경 기록 대조 — 깨는 항목 없음, 2.1.1 이미 출시라 정확 고정 필요, `do_orm_execute`+`yield_per` 경로 시험), 계획 `docs/plans/2026-09-29-asset-content-hash-url-plan.md`(`asset_url` 도우미, 시범 `erp_order_js.html` 37개). 조사는 서브에이전트 3개 병렬 + 핵심 주장 직접 확인(start.sh 구조·러너 import·JSON 경로 `->` 렌더·PyPI 판·WhiteNoise `v=` 미들웨어). 부수: `ci_watch` 가 런이 4개 있는데 "워크플로 없음 — green" 거짓 초록(b86f4c5d3) → gh 로 직접 감시.
- [2026-09-29] 사용자 승인: 워커 감독(선택 A 파이썬 지킴이 + C 러너 약점 + 스테이징 죽여 보기), SQLAlchemy 2.0.54, 화면 파일 버전 시범(주문 화면 한 파일), ci_watch 거짓 초록 수정.
  - ci_watch `9e8d1dc76`: gh 조회 실패 = None(판정 불가, exit 4) — 옛 코드로 "진행 중 → 조회 실패 1회" 를 재현하면 exit 0·"워크플로 없음" 문구가 그대로 나옴(원인 확정). 시험 10.
  - SQLAlchemy 2.0.54 `a7f50c8d9`: 새 가상환경(저장소 밖 `c:/tmp/venv-foms-sa254` — 저장소 안에 두면 파일 크기 래칫이 site-packages 를 세어 빨강) 전체 11198·PG 776, 경고 요약 동일. DISTINCT ON 4곳 PG 시험 없음 → 후속.
  - 워커 감독자(커밋 전): `tools/ops/worker_supervisor.py`(작업 목록 정본 `worker_jobs`, 작업별 백오프 5→60·60초 생존 시 되돌림, rq 는 매번 wait_for_redis 선행, TERM→25초→KILL, PID 1 이면 떠돌이 자식 거둠, `--print-jobs` 는 REDIS_URL 가림). `start.sh` WORKER = wait_for_redis → `exec python tools/ops/worker_supervisor.py`. 러너 3곳 metadata 조립 가드(`loop_heartbeat.safe_metadata`), 좌표 스윕 라운드 `except Exception`. start.sh 글자를 읽던 시험 9곳을 작업 목록 기준으로 옮김(`tests/support/worker_jobs.py`), 실행 시험 `test_worker_supervisor_process.py`(가짜 자식 + 진짜 자식). toml 3개 builder 줄에 "실제는 Dockerfile" 주석.
  - 화면 파일 버전 시범: 별도 에이전트가 격리 작업 폴더에서 구현 중(검토 후 반영).
- [2026-09-29] deploy `5810946a8`(ci_watch·SQLAlchemy 2.0.54·워커 감독자·상태판): CI 4종 green(직접 gh 폴링). 스테이징 4서비스 SUCCESS. WORKER 로그 `[supervisor] managing 5 job(s)`(escalation·order_sync·auto_dispatch·settle_sync·rq — 스테이징은 좌표 스윕 꺼짐), rq 는 wait_for_redis 뒤 기동. `railway ssh` 로 PID 1 = `python tools/ops/worker_supervisor.py` 확인, escalation(pid 3) `kill -9` → `exited rc=-9 after 82s - restarting in 5s` → 새 pid 141 → `[escalation-loop] started`(스테이징만, 사용자 허용).
- [2026-09-29] 화면 파일 버전 시범: 에이전트 커밋 `866609f4b` 검토(37개 전환·시험 13개가 뜻 유지·중복 실행 방지 확인) → cherry-pick, 전체 11234 passed.
