# Railway 밖 대피 계획 — SPEC (2026-10-22)

상태: **계획·준비만(2026-10-22 사용자: "지금 당장은 불가능하니 계획서와 준비만")**. 서버 구매·운영 변경은 하지 않는다.
돈이 들지 않고 운영을 건드리지 않는 준비(1단계 구성 파일·스크립트 초안)는 할 수 있다 — 착수 시점은 따로 정한다.
관련: `docs/guides/DISASTER_RECOVERY.md`(데이터 살리기 개요), 비공개 `lahomsystem/foms-ops-backup` 의 `RESTORE.md`(복원 절차·리허설 기록),
`docs/specs/2026-10-22-railway-api-mutation-guard_SPEC.md`(Railway 변경 허락 안전 장치).

## 한눈에
- **데이터는 Railway 가 사라져도 살린다.** 2026-10-22 첫 복원 리허설이 성공했다(새 DB 에는 pgvector 가 필요하다).
- **서비스를 다시 세울 곳과 절차가 없다.** 지금 복구 절차는 "Railway 에 새 프로젝트를 만든다"가 전제다.
- 가장 큰 걸림돌은 **주소가 Railway 것**이라는 점이다(`lahom-production.up.railway.app`, 자체 도메인 0개). 고객에게 이미 보낸
  공유 링크·QR, 채널톡 링크, 알림톡 서식, 직원 홈 화면 앱·웹 푸시 구독이 모두 이 주소에 묶여 있다.
- 그래서 1순위는 **자체 도메인**이다. 이것만 해 두면 대피는 "새 곳에 띄우고 DNS 한 줄 바꾸기"가 된다.
- 2순위는 Railway 없이도 뜨는 **구성 파일 한 벌**(Docker Compose)과 그것으로 하는 **리허설**이다.

## 1. 목적
Railway 가 통째로 사라지거나 오래 못 쓰게 돼도, FOMS 를 다른 곳에서 정해진 시간 안에 다시 띄운다.

## 2. 목표 (제안 — 결정 필요)
| 항목 | 제안 | 지금 |
|---|---|---|
| 잃는 데이터 | 최대 24시간 | 같음(매일 03:00 KST 백업, 90일 보관) |
| 서비스 재개 | 대피 선언 뒤 1영업일 | 기준 없음(세울 곳 없음) |
| 이미 보낸 고객 링크 | 계속 열린다 | Railway 주소라 Railway 와 함께 죽는다 |

## 3. 지금 상태 (2026-10-22 확인)
살릴 수 있는 것
- DB: 매일 `pg_dump` → age 암호화 → R2 백업 버킷(Railway 밖). 첫 복원 리허설 성공 — 운영과 `orders` 4,817·`users` 38·alembic 일치,
  표 101 중 100(빠진 1개 `designer_embeddings` 는 리허설 PC 에 pgvector 가 없어서, 운영에서도 0행).
- 환경변수: 6개 서비스 스냅샷(암호화, SIDEFX 는 10-22 부터). 서비스 구성 `topology.json`(10-22 갱신 — start 명령·헬스체크·cron).
- 코드: GitHub `lahomsystem/FOMS`. 루트 `Dockerfile` 은 Railway 밖에서도 그대로 빌드된다(`CMD sh start.sh`).
- 고객 파일: Cloudflare R2 앱 버킷(Railway 밖). **단, 따로 둔 사본은 없다.**

세울 곳: 없다.

## 4. Railway 에 묶인 것 (2026-10-22 코드 조사 — 주요 9개)
1. **주소** — 웹 서비스 도메인은 `lahom-production.up.railway.app` 하나, 자체 도메인 0개(`topology.json`).
   - 코드 기본값: `foms/services/channel_client.py:25`, `foms/services/share_consult.py:195,276`(운영 주소),
     `foms/services/channel_policy.py:46`(**스테이징 주소 — 숨은 버그**. 운영 web·WORKER·SIDEFX 는 `FOMS_BASE_URL` 을 넣어 둬서 지금은
     안 터진다. FOMS-cron 에는 `FOMS_BASE_URL` 이 없다).
   - 알림톡 공유 서식(라홈·하우드)과 대체 문자에 이 주소가 들어 있다(`docs/plans/2026-08-11-customer-share-phase-a-ledger.md:41`).
     주소를 바꾸면 새 서식을 카카오 심사에 다시 올려야 한다(며칠).
   - 세션 쿠키는 호스트 한정이라 주소가 바뀌면 전원 다시 로그인한다. 웹 푸시 구독·홈 화면 앱은 주소(origin)에 묶여 다시 설치·구독해야 한다.
2. **네이버 허용 IP 3칸** = WORKER 의 Railway 고정 출구 IP 3개(싱가포르 공용 `208.77.246.240~242`, `docs/guides/NAVER_INGEST_SETUP.md:29`).
   새 곳도 고정 출구 IPv4 3개 이하가 필요하다. 칸이 꽉 차 있어 바꾸는 동안 네이버 수집이 멈춘다.
3. **운영 판정이 Railway 변수에 기댄다** — 운영 env 에 `FLASK_ENV`·`STORAGE_TYPE` 이 없다(10-22 스냅샷).
   `foms/platform/app_factory.py:217-218` 은 `RAILWAY_ENVIRONMENT` 로 운영을 판정하고, `foms/services/storage.py:173-211` 은 `RAILWAY_*` 가
   있을 때만 R2 를 고른다. Railway 밖에서 그대로 띄우면 개발 모드(보안 쿠키·HSTS·ProxyFix 꺼짐)로 돌고 **업로드가 컨테이너 임시 디스크로
   조용히 간다.**
4. **배포 파이프라인이 없다** — 브랜치 push → Railway 자동 배포. 배포마다 한 번 `predeploy.sh`(`alembic upgrade head`), `/healthz` 통과 뒤
   전환, 겹침 전환이 전부 Railway 몫이다. `.github/workflows` 에 배포 작업이 없다.
5. **프로세스 4종** — web(`start.sh` gunicorn gevent), WORKER(`USE_RQ_WORKER=1`, 1개 고정 — 네이버 IP·하루 1회 자동 발송),
   SIDEFX(`tools/ops/run_domain_side_effect_outbox.py --loop`), FOMS-cron(`tools/cron/nightly.py`, 매일 17:00 UTC, 겹치면 안 된다).
   실제 start 명령·replica 는 대시보드에만 있고 `topology.json` 에 사본이 있다.
6. **프록시 동작** — `X-Forwarded-For` 모양과 홉 수(`FOMS_TRUSTED_PROXY_HOPS`), `X-Forwarded-Proto/Host`(틀리면 쓰기 요청이 전부 403 —
   `foms/services/request_write_guard.py` 가 Origin 을 `request.scheme://request.host` 와 비교), 웹소켓(유휴 60초 이상), 요청 시간 120초 이상.
7. **DB 확장** — PostgreSQL 17 + `vector`(운영 0.8.2) + `pg_trgm`. pgvector 가 없으면 마이그레이션이 일부러 실패한다
   (`migrations/versions/designer_pgvector.py`).
8. **운영 도구·기록** — `tools/ops/check_deploy_drift.py`, `tools/ops/railway_pitr.py`, cron 설정 도구, httpLogs 비교, perf gate
   (`/healthz` 의 커밋 값이 `RAILWAY_GIT_COMMIT_SHA` — `foms/api/health.py:38`). 로그는 Railway 에만 있어 함께 사라진다.
9. **외부 등록** — 카카오 JS 도메인, 채널톡 웹훅·함수 URL, R2 버킷 CORS(브라우저 직접 업로드), 백업 심박 주소.

## 5. 대피처를 고르는 기준
지역(서울 또는 도쿄 — 지금 싱가포르보다 가깝다, `docs/guides/NETWORK_EDGE_TAIL_FIX.md`), 고정 출구 IPv4 3개 이하,
Docker 이미지 그대로 실행, PostgreSQL 17 + pgvector, 웹소켓·긴 요청 허용, 국내 결제, 관리 부담.

## 6. 후보
| 후보 | 내용 | 좋은 점 | 걸리는 점 |
|---|---|---|---|
| **A. 서울 VM 1대 + Docker Compose** | web·WORKER·SIDEFX·cron·Postgres(pgvector 이미지)·Redis·HTTPS 프록시를 한 서버에 | 고정 IP 가 기본(네이버 1칸), 가장 단순, 리허설이 쉽다, 월 비용이 낮다 | 서버 한 대가 죽으면 같이 죽는다. OS·보안 업데이트·DB 백업을 우리가 한다 |
| B. 다른 PaaS(Render·Fly.io 등) | Railway 와 비슷한 방식 | 편하다 | 고정 출구 IP 가 비싸거나(Render 전용 IP 3개 묶음 월 $100) 제약이 있다(Fly 는 지역별 IP, 2026-07 도쿄 IP 부족 사용자 보고). 같은 종류의 플랫폼 사고 위험 |
| C. 큰 클라우드(AWS 서울 ECS + RDS 등) | 관리형 DB·로드밸런서 | 튼튼하다 | 구성·비용·학습이 크다 |

**추천: A 를 대피처로 준비한다.** 평소에는 구성 파일과 스크립트만 두고 서버는 리허설 때만 만든다. 실제로 옮길지는 Railway 사고 결과를 보고
따로 정한다. VM 업체·사양·월 비용은 결정 항목이다.

B 의 출처(2026-10-22 검색): Render 전용 IP https://render.com/docs/dedicated-ips ·
Fly.io 출구 IP https://fly.io/docs/networking/egress-ips ·
Fly 도쿄 IP 부족 글 https://community.fly.io/t/no-more-egress-ips-available-for-allocation-in-nrt-is-the-tokyo-pool-exhausted/28349

## 7. 단계

### 0단계 — 자체 도메인 (가장 먼저, Railway 배포 재개 뒤)
1. 도메인을 정한다. `docs/guides/NETWORK_EDGE_TAIL_FIX.md:30-42` 의 `app.lahom.kr` 은 예시였고 실행되지 않았다 — 공개 DNS 조회
   (2026-10-22)로 `lahom.kr` 은 네임서버가 없다(미등록으로 보임). 이미 등록된 도메인은 `lahom.co.kr`·`haud.co.kr`·`haudsystem.com`
   (모두 카페24 네임서버). 새로 사지 않고 **`erp.lahom.co.kr` 같은 하위 주소**를 카페24 DNS 에 CNAME 한 줄로 거는 길이 가장 싸다.
   소유·카페24 계정 관리자 확인이 필요하다(`lahom.com` 은 다른 등록 업체 — 소유 미확인).
2. Railway web 에 자체 도메인 연결 → 운영 `FOMS_BASE_URL` 변경 → 카카오 JS 도메인·채널톡 URL·R2 CORS 등록 → 알림톡 공유 서식을 새 주소로 재심사.
3. 옛 Railway 주소는 살아 있는 동안 그대로 둔다(이미 보낸 링크).

끝나면 대피 때 DNS 한 줄로 직원·고객이 새 곳으로 간다. 새 서버에서 같은 `SECRET_KEY`·VAPID 키를 쓰면 로그인·웹 푸시도 이어진다.

### 1단계 — Railway 없이 뜨게 (저장소 안 코드·구성)
1. Railway 변수 의존 끊기: 운영 env 에 `FLASK_ENV=production`·`STORAGE_TYPE=r2` 명시(배포 재개 뒤), `/healthz` 커밋 값은 `FOMS_RELEASE_ID`
   같은 대체를 허용, `channel_policy.py:46` 기본값 버그 수정, FOMS-cron 에 `FOMS_BASE_URL`.
2. 구성 파일 한 벌(가칭 `scripts/exit_compose/`): `docker-compose.yml`(서비스 6개 + HTTPS 프록시), `.env` 틀(이름만), cron 대체(겹침 금지 `flock`),
   재시작 정책 always, WORKER 1개 고정.
3. 복원 스크립트: R2 최신 덤프 받기 → sha256 대조 → age 복호화 → pg_restore(pgvector 이미지) → 행 수 확인. 10-22 리허설 순서를 그대로 옮긴다.
4. 환경변수 변환: 스냅샷(`vars-latest.json.age`) → 서비스별 `.env`(DB·Redis 주소만 새 값, `RAILWAY_*` 제외, 1번 변수 추가).
5. 프록시 테스트 갱신: 홉 수·`X-Forwarded-*`(`tests/domains/test_client_ip_trust.py` 등).

### 2단계 — 리허설 (분기 1회, 백업 리허설과 함께)
VM 한 대를 만들어 1단계로 띄운다. 운영 DB 사본을 쓰므로 **외부 발송은 끈다**(알림톡·웹 푸시·네이버 자동 발송·채널톡 관련 플래그).
로그인, 주문 목록·상세, 파일 보기, 실시간 알림, 작업 큐, cron 1회를 확인하고 걸린 시간을 적는다.

### 3단계 — 진짜 대피할 때 순서
1. 대피 선언(사용자)
2. VM 만들기, 1단계 구성 올리기
3. 최신 백업 복원
4. 환경변수 넣기(사고 원인에 따라 비밀값은 새 값)
5. 앱 기동·점검
6. DNS 전환(0단계를 했을 때)
7. 네이버 허용 IP 교체
8. 외부 등록 갱신(0단계를 안 했으면 전부 + 알림톡 서식 재심사)
9. 직원 공지(0단계를 안 했으면 새 주소·다시 로그인·푸시 재구독·홈 화면 앱 재설치)

## 8. 결정이 필요한 것
1. 자체 도메인 이름과 보유 여부.
2. 대피처 종류(추천 A), 업체, 월 비용 한도.
3. 목표(잃는 데이터 24시간·재개 1영업일)가 맞는지 — 더 줄이려면 백업 주기를 늘린다.
4. 대피처를 평소에 켜 둘지(대기 비용) 리허설 때만 만들지.
5. 고객 파일(R2 앱 버킷) 사본을 따로 둘지 — 지금 없다. 이번 사고처럼 키가 새면 지워져도 되살릴 길이 없다.

## 9. 하지 않는 것
- 지금 당장 Railway 를 떠나는 결정. 이 문서는 "떠날 수 있게" 준비하는 것이다.
- 비밀값 교체·DB 공개 주소 닫기. 사고 대응으로 따로 진행한다(배포 재개 뒤, 2026-10-22 결정).
