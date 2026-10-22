# 재해복구 (Railway 프로젝트 소실)

> 이 저장소는 **공개**다. 시크릿·백업 자산은 여기에 두지 않는다.
> 절차 정본과 자동화는 비공개 저장소 **`lahomsystem/foms-ops-backup`** 에 있다.

## 방어 계층

| 사고 | 방어 수단 | 위치 |
|---|---|---|
| 테이블 삭제·데이터 오염 | Railway 볼륨 데일리 백업(6일 보관) | Railway 대시보드 (FOMS-PRODUCTION Postgres) |
| **프로젝트 삭제** | 48시간 복원 링크(메일) → 이후엔 오프사이트 백업만 | `foms-ops-backup` |

Railway 볼륨 백업은 **같은 프로젝트+환경으로만 복원 가능**하다. 프로젝트가 사라지면
볼륨 백업도 함께 사라진다. 삭제 후 48시간이 지나면 Railway도 복구하지 못한다.

## 오프사이트 백업 대상

- 운영 Postgres 논리 덤프 → age 암호화 → R2 **백업 전용** 버킷 (앱 버킷과 분리)
- Railway 환경변수 6개 서비스(web·WORKER·SIDEFX·FOMS-cron·Postgres·Redis) 스냅샷 → age 암호화 → `foms-ops-backup/secrets/` (SIDEFX 는 2026-10-22 부터)
- 서비스 구성(healthcheckPath·Config Path·cron·start 명령 등 대시보드 전용 설정) → `topology.json`

첨부파일·이미지는 Cloudflare R2(Railway 밖)에 있어 프로젝트 삭제의 영향을 받지 않는다.

백업 파일을 여는 age 개인키는 CI 에 없다. 키를 잃으면 백업 전부를 못 연다 — 서로 다른 두 곳
이상에 오프라인으로 둔다.

## Railway 자체를 못 쓰게 되면

`RESTORE.md` 3번은 Railway 에 새 프로젝트를 다시 만드는 것을 전제로 한다. Railway 를 아예 못 쓰면
데이터(DB 덤프·환경변수·첨부파일)는 살릴 수 있지만, 같은 구성(web·WORKER·SIDEFX·FOMS-cron·
Postgres 17·Redis)을 다른 곳에 세우는 절차는 아직 없다(2026-10-22). 루트 `Dockerfile` 은 있다.

## 프로젝트가 삭제됐다면

1. **받은편지함에서 Railway 복원 메일부터 찾는다** (48시간 이내면 링크 한 번으로 끝).
2. 지났으면 `foms-ops-backup/RESTORE.md` 절차를 따른다.

복구 시 잊기 쉬운 것: 새 프로젝트는 **도메인·고정 IP가 전부 바뀐다.**
네이버 커머스API 허용 IP 3슬롯, 카카오 지도 도메인 허용목록, Solapi 콜백을 재등록해야 한다.
