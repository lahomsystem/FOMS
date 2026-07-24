# Runbook: 백업 · 복원 (DB restore)

BACKUP-01(2026-07-24)로 deprecated 로컬 pg_dump 백업 서비스(`foms/api/backup.py`의
`/api/simple_backup`·`/api/backup_status`, `foms/services/admin/backup_service.py`의
`SimpleBackupSystem`, `backups/tier1_primary`·`tier2_secondary` 트리, 운영 배치
`🚨_간단_백업.bat`)를 제거했다. 그 도구는 동일 워크스테이션·동일 저장 위치에 의존해
재해복구 표준으로 부적합했다(근거: `docs/specs/2026-06-05-backup-feature-retirement_SPEC.md`).

이 runbook은 제거 이후의 **정본 백업·복원 절차**를 고정한다.

## 정본 백업 소스 (SSOT)

| 대상 | 정본 백업 | 위치 |
|------|-----------|------|
| production DB | Railway PostgreSQL 자동 백업/스냅샷 | Railway 대시보드 → Postgres 서비스 → Backups |
| 로컬 → 운영 동기화 덤프 | `scripts/ops/sync_local_to_railway.ps1` | `FOMS_RUNTIME_OUTPUT_ROOT\dumps\foms.dump` (미설정 시 `%USERPROFILE%\FOMS-runtime\dumps\foms.dump`) |

production 코드/템플릿 백업은 git(원격 저장소)이 정본이며 별도 파일 백업이 불필요하다.

## 복원 절차

### 1) production DB 복원 (재해복구 표준)

Railway PostgreSQL 스냅샷에서 복원한다.

1. Railway 대시보드 → 해당 프로젝트(운영 = centerbeam) → Postgres 서비스 → **Backups** 탭.
   - 운영/스테이징 혼동 주의: 운영은 `centerbeam`, 스테이징(dev)은 `hopper`
     (`REDIS_PUBLIC_DOMAIN`으로 교차 확인 — `project_railway_cli_link_dev_prod_ambiguity`).
2. 복원 시점 스냅샷 선택 → Restore. Railway가 새 볼륨으로 복원하고 `DATABASE_URL`을 재바인딩한다.
3. 복원 후 검증: `/health` 200, 주문 리스트 렌더, 최근 주문의 `structured_data`(실측·상태·워크플로) 존재 확인.

### 2) 로컬 덤프에서 원격 복원 (운영자 수동 동기화)

`scripts/ops/sync_local_to_railway.ps1`이 로컬 Postgres를 `pg_dump`(읽기 전용)로 떠서
원격(Railway `DATABASE_URL`)에만 `pg_restore --clean`으로 적용한다.
**로컬 DB는 절대 삭제/초기화하지 않는다**(스크립트 내장 가드).

```powershell
# 프로젝트 루트에서
.\scripts\ops\sync_local_to_railway.ps1
# 덤프 경로: %FOMS_RUNTIME_OUTPUT_ROOT%\dumps\foms.dump
```

상세: `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`.

### 3) 임의 `.dump` 파일을 특정 DB로 복원 (수동)

`pg_restore`로 직접 복원한다(전체 스키마·데이터 = 주문·상태·실측·체크리스트·워크플로 포함).

```powershell
$env:PGPASSWORD = "<db_password>"          # 셸 종료 시 소멸, 스크립트에 하드코딩 금지
pg_restore --clean --if-exists --no-owner `
  -h <host> -p <port> -U <user> -d <dbname> `
  "<path>\foms.dump"
```

> 보안: DB 비밀번호는 환경변수(`PGPASSWORD`)로만 전달하고 스크립트/배치에 하드코딩하지 않는다.
> (제거된 `SimpleBackupSystem`은 복구 `.bat`에 평문 비밀번호를 기록했던 안티패턴이다 — 되살리지 않는다.)

## 참조

- `docs/specs/2026-06-05-backup-feature-retirement_SPEC.md` — 은퇴 결정·스코프
- `docs/specs/2026-03-20-production-backup-and-restore-plan.md` — production 백업/복원 계획
- `docs/evolution/BACKUP_RESTORE_VERIFICATION.md` — (역사) 구 백업 메커니즘 검증 기록
- `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md` — 로컬→원격 동기화 절차
