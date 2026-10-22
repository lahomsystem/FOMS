# FOMS 대피 구성 (초안)

상태: **준비용 초안 — 2026-10-22. 아직 한 번도 띄워 보지 않았다.** 사용자 결정: "지금 당장은 옮길 수 없으니 계획서와 준비만".
설계: `docs/specs/2026-10-22-railway-exit-plan_SPEC.md`. 데이터 복원 절차 정본: 비공개 `lahomsystem/foms-ops-backup` `RESTORE.md`.

Railway 가 사라졌을 때 서버 1대(서울 VM)에서 FOMS 를 다시 띄우는 구성이다. 리허설 때는 **외부 발송을 끈 env** 로만 띄운다
(운영 DB 사본에는 실제 고객 연락처가 있다 — 알림톡·웹 푸시·네이버 자동 발송·채널톡 플래그를 끈다).

## 들어 있는 것
| 파일 | 하는 일 |
|---|---|
| `docker-compose.yml` | postgres(pgvector 17)·redis·migrate(predeploy)·web·worker(1개)·sidefx·cron(수동)·caddy(HTTPS) |
| `Caddyfile` | 도메인 HTTPS 자동 발급, web 으로 전달(웹소켓·긴 요청) |
| `../../tools/ops/vars_snapshot_to_env.py` | 환경변수 스냅샷 → 서비스별 `.env`(저장소 밖) |
| `../../tools/ops/offsite_restore.py` | R2 최신 덤프 받기 → sha256 → 복호화 → 빈 DB 에 복원 → 숫자 세기 |

## 순서 (서버에서)
1. 저장소를 받는다(`production` 브랜치). Docker·age·PostgreSQL 17 클라이언트를 설치한다.
2. 환경변수: `age -d -i <키> vars-latest.json.age | python tools/ops/vars_snapshot_to_env.py --out /srv/foms-env`
   — 사고 원인이 비밀값 유출이면 새 값으로 바꾼다.
3. `export FOMS_ENV_DIR=/srv/foms-env POSTGRES_PASSWORD=<새 값> REDIS_PASSWORD=<새 값> FOMS_DOMAIN=<도메인>`
4. DB 만 먼저 띄운다: `docker compose -f scripts/exit_compose/docker-compose.yml up -d postgres`
5. 복원: `python tools/ops/offsite_restore.py --key <키> --fetch --target postgresql://foms:<비번>@127.0.0.1:5432/foms`
   (DB 포트를 잠시 열거나 같은 네트워크에서 실행한다. 대상에 표가 있으면 스크립트가 거부한다.)
6. 나머지: `docker compose -f scripts/exit_compose/docker-compose.yml up -d` — migrate 가 먼저 돌고 web·worker·sidefx·caddy 가 뜬다.
7. cron(매일 17:00 UTC, 겹침 금지) — 호스트 crontab:
   `0 17 * * * flock -n /tmp/foms-cron.lock docker compose -f /srv/FOMS/scripts/exit_compose/docker-compose.yml --profile cron run --rm cron`
8. 점검: `/healthz` 200 · 로그인 · 주문 목록 · 첨부 보기(R2 CORS 에 새 주소 등록 필요) · 실시간 알림 · 작업 큐.
9. 바깥 등록: 네이버 허용 IP(서버 고정 IP), 카카오 JS 도메인, 채널톡 URL, 알림톡 서식(주소가 바뀌었으면 재심사).

## 아직 모르는 것
- 실제로 떠 본 적이 없다 — 첫 리허설에서 고친다.
- Caddy 한 단 뒤의 `X-Forwarded-For` 홉 수는 1 로 두었다. 리허설 때 로그인 잠금이 같은 IP 로 쌓이는지 확인한다.
- `FOMS_BASE_URL`·`CORS_ALLOWED_ORIGINS` 를 새 도메인으로 env 에 넣어야 한다(FOMS-cron 에는 원래 없다).
