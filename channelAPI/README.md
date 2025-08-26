# 채널톡 메시지 검색 도구

채널톡 Open API를 사용하여 특정 그룹('실측스케쥴')의 메시지에서 키워드와 날짜 조건에 맞는 텍스트를 검색하는 Node.js 애플리케이션입니다.

## 🎯 주요 기능

- ✅ **날짜 필터링**: 특정 날짜 이후의 메시지만 검색
- ✅ **키워드 검색**: 특정 단어가 포함된 메시지 추출
- ✅ **채팅 목록 조회**: 모든 사용자 채팅 목록 확인
- ✅ **API 연결 테스트**: 설정 검증 및 연결 상태 확인
- ✅ **사용자 친화적 인터페이스**: 대화형 메뉴 시스템

## 📋 요구사항

- Node.js 14.0 이상
- 채널톡 Open API 키 (Access Key, Secret Key)
- npm 또는 yarn

## 🚀 설치 및 설정

### 1. 의존성 설치

```bash
npm install
```

### 2. API 키 설정

`config.js` 파일에서 다음 정보를 입력하세요:

```javascript
module.exports = {
  channelAuth: {
    accessKey: '68a420d8089ae130672a',      // 실제 Access Key
    secretKey: '7a607d84f2734081dfaaee782eac09b8'  // 실제 Secret Key
  },
  // ... 기타 설정
};
```

### 3. 연결 테스트

```bash
npm run test
# 또는
node test-connection.js
```

## 📖 사용법

### 기본 실행

```bash
npm start
# 또는
node index.js
```

### 메뉴 옵션

1. **특정 채팅에서 메시지 검색**: 채팅 ID를 알고 있는 경우
2. **모든 채팅에서 메시지 검색**: 전체 채팅에서 키워드 검색
3. **채팅 목록 조회**: 사용 가능한 채팅 목록 확인
4. **그룹 정보 조회**: '실측스케쥴' 그룹 찾기 시도
5. **설정 정보 표시**: 현재 API 설정 확인

### 사용 예시

```bash
🔍 채널톡 메시지 검색 도구
========================================
📡 채널톡 API 연결 확인 중...
✅ 채널톡 API 연결 성공

📋 메뉴를 선택하세요:
1. 특정 채팅에서 메시지 검색
2. 모든 채팅에서 메시지 검색
3. 채팅 목록 조회
4. 그룹 정보 조회 (실측스케쥴)
5. 설정 정보 표시
0. 종료
선택: 2

🔍 전체 채팅 검색
------------------------------
검색할 키워드를 입력하세요: 실측
시작 날짜 (YYYY-MM-DD, 기본값: 2024-01-15): 2024-01-01
검색할 최대 채팅 수 (기본값: 10): 5

🚀 전체 채팅 검색을 시작합니다...
```

## 📁 프로젝트 구조

```
channelAPI/
├── package.json          # 프로젝트 설정 및 의존성
├── config.js            # API 키 및 설정 (실제 키 포함)
├── config.example.js    # 설정 파일 예시
├── index.js             # 메인 애플리케이션
├── channel-api.js       # 채널톡 API 클라이언트
├── message-search.js    # 메시지 검색 로직
├── test-connection.js   # API 연결 테스트
└── README.md           # 이 파일
```

## 🔧 API 정보

### 사용되는 채널톡 API 엔드포인트

- `GET /open/v5/managers` - 매니저 목록 조회
- `GET /open/v5/user-chats` - 사용자 채팅 목록 조회
- `GET /open/v5/user-chats/{userChatId}/messages` - 특정 채팅의 메시지 조회

### 인증 방식

- **Header 기반 인증**:
  - `x-access-key`: Access Key
  - `x-access-secret`: Secret Key

## ⚠️ 주의사항

1. **그룹 채팅 제한**: 채널톡 Open API에서 내부 그룹 채팅 조회가 제한적일 수 있습니다.
2. **API 호출 제한**: 과도한 API 호출을 방지하기 위해 적절한 딜레이가 포함되어 있습니다.
3. **권한 필요**: API 키에 메시지 조회 권한이 있어야 합니다.

## 🐛 문제 해결

### 일반적인 오류들

#### 401 Unauthorized
- API 키가 잘못되었거나 누락된 경우
- `config.js`의 `accessKey`와 `secretKey`를 확인하세요

#### 403 Forbidden
- 해당 리소스에 접근 권한이 없는 경우
- 채널톡 관리자 페이지에서 API 권한을 확인하세요

#### 422 Unprocessable Entity
- 잘못된 파라미터로 요청한 경우
- 입력값을 다시 확인하세요

#### 429 Too Many Requests
- API 호출 제한에 걸린 경우
- 잠시 기다린 후 다시 시도하세요

### 디버깅

`config.js`에서 `debug: true`로 설정하면 상세한 로그를 확인할 수 있습니다.

## 📚 참고 문서

- [채널톡 Open API 가이드](https://docs.channel.io/trainingcenter/ko/articles/Open-API-3f0a4dbc)
- [채널톡 API 문서](https://api-doc.channel.io/)
- [채널톡 개발자 문서](https://developers.channel.io/)

## 📝 라이센스

ISC License

## 👥 기여

문제점이나 개선사항이 있다면 이슈를 생성하거나 풀 리퀘스트를 제출해주세요.

