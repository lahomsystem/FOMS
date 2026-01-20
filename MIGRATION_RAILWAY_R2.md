# Railway + R2 배포(다운타임 허용) 마이그레이션 가이드

## 목표
- **로컬 Postgres(furniture_orders)** 데이터를 **Railway Postgres**로 이관
- 기존 업로드 파일(`static/uploads`)을 **Cloudflare R2**로 이관
- DB의 파일 링크를 **영구 링크(`/api/files/view/<key>`)**로 통일해서 만료/경로 문제 제거

---

## 0) 사전 준비(최초 1회)
- Railway에 Postgres 추가 → `DATABASE_URL` 자동 생성
- Railway Variables에 R2 세팅:
  - `STORAGE_TYPE=r2`
  - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
  - `STORAGE_PUBLIC=false` (권장)

---

## 1) 다운타임 시작(로컬 쓰기 중지)
- 로컬 서버/작업을 중지해서 신규 주문/채팅/업로드가 발생하지 않게 합니다.

---

## 2) 로컬 파일 → R2 업로드 + DB 링크 통일(로컬에서 실행)

### 2-1) (권장) 먼저 dry-run으로 누락 파일 체크
```bash
python migrate_local_uploads_to_r2.py
```

### 2-2) 실행(실제 업로드 + DB 업데이트)
R2 환경변수를 로컬에 설정한 뒤:

```bash
python migrate_local_uploads_to_r2.py --execute --skip-existing
```

---

## 3) 로컬 DB 덤프
권장: custom format (pg_restore용)

```bash
pg_dump -Fc --no-owner --no-privileges -f ./foms.dump "postgresql://postgres:lahom@localhost/furniture_orders"
```

---

## 4) Railway DB로 복원
```bash
railway link
railway run pg_restore --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL" ./foms.dump
```

---

## 5) 배포 직후 1회: 테이블/스키마 보정
```bash
railway run python railway_bootstrap.py
```

---

## 6) 체크리스트
- 채팅방에서 과거 이미지/영상/파일이 열리고 다운로드 되는지
- 주문 상세에서 도면이 열리는지
- 신규 업로드가 R2에 저장되는지(재배포 후에도 파일 유지)

