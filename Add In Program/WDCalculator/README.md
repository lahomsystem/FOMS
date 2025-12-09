# 가구 견적 계산기 (WDCalculator)

FOMS 시스템에 통합된 가구 견적 계산기입니다.

## 기능

- 제품 설정 및 관리
- 견적 자동 계산 (1m / 30cm 옵션 지원)
- 추가 옵션 관리
- 쿠폰가 적용 (할인율 / 고정 금액)

## 실행 방법

### 방법 1: 배치 파일 실행 (권장)

1. `start_wdcalculator.bat` 더블 클릭
   - FOMS 서버가 시작됩니다
   - 브라우저에서 `http://localhost:5000/wdcalculator` 접속

2. `start_wdcalculator_auto.bat` 더블 클릭
   - FOMS 서버가 시작되고 5초 후 브라우저가 자동으로 열립니다

### 방법 2: Python 직접 실행

```bash
cd C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS
python app.py
```

그 후 브라우저에서 `http://localhost:5000/wdcalculator` 접속

## 사용 방법

### 1. 제품 설정

1. `/wdcalculator/product-settings` 페이지로 이동
2. 제품 추가 버튼 클릭
3. 제품 정보 입력:
   - 제품명
   - 가격 산정 옵션 (1m 또는 30cm)
   - 가격 정보 입력
   - 추가 옵션 설정 (선택)
   - 쿠폰가 설정 (선택)
4. 저장 버튼 클릭

### 2. 견적 계산

1. `/wdcalculator` 페이지로 이동
2. 고객명 입력 (선택)
3. 제품 선택
4. 가로넓이(mm) 입력
5. 추가 옵션 추가 (필요시)
6. 쿠폰가 설정 (필요시)
7. 견적 결과 확인

## 견적 계산 알고리즘

### 1m 옵션
- 규격 2000mm 입력 시: `2 * 1m 설정비용`
- 규격 1200mm 입력 시: `1.2 * 1m 설정비용`

### 30cm 옵션
- 규격 3000mm 입력 시: `(3000/300) = 10 * 30cm 설정비용`
- 규격 3100mm 입력 시: `10 * 30cm 설정비용 + 10 * 1cm 설정비용`
  - 300으로 나눈 몫은 30cm 단위, 나머지는 1cm 단위로 처리

## 데이터 저장

제품 데이터는 `data/products.json` 파일에 저장됩니다.

## 요구사항

- Python 3.x
- Flask
- FOMS 시스템 (app.py)

## 라우트

- `/wdcalculator` - 견적 계산 메인 페이지
- `/wdcalculator/product-settings` - 제품 설정 페이지
- `/api/wdcalculator/products` - 제품 API
- `/api/wdcalculator/calculate` - 견적 계산 API


