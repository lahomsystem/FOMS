# Railway 환경변수 (필수/권장)

## 1) 필수(최소 구동)

- **DATABASE_URL**: Railway Postgres를 붙이면 Railway가 자동으로 만들어줍니다.

## 2) 권장(프로덕션 파일 업로드: Cloudflare R2)

- **STORAGE_TYPE**: `r2`
- **R2_ACCOUNT_ID**
- **R2_ACCESS_KEY_ID**
- **R2_SECRET_ACCESS_KEY**
- **R2_BUCKET_NAME**
- **STORAGE_PUBLIC**: `false` (권장: presigned URL로 다운로드)

## 3) WDCalculator (권장: 단일 DB + 스키마 분리)

- **WD_CALCULATOR_SCHEMA**: `wdcalculator` (기본값)

## 4) (선택) 레거시: WDCalculator 별도 DB 유지 시에만

- **WD_CALCULATOR_DATABASE_URL**: `postgresql://user:password@host:port/wdcalculator_estimates`

## 배포 직후 1회 실행(권장)

Railway CLI에서:

```bash
railway run python railway_bootstrap.py
```

