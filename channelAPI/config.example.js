// 채널톡 API 설정 예시 파일
// 실제 사용시 config.js로 복사하여 API 키를 입력하세요

module.exports = {
  // 채널톡 API 인증 정보
  channelAuth: {
    accessKey: 'your_access_key_here',  // 68a420d8089ae130672a (실제 키로 교체)
    secretKey: 'your_secret_key_here'   // 7a607d84f2734081dfaaee782eac09b8 (실제 키로 교체)
  },
  
  // API 기본 설정
  api: {
    baseUrl: 'https://api.channel.io',
    version: 'v5',
    timeout: 10000,
    retryAttempts: 3
  },
  
  // 검색 기본 설정
  search: {
    defaultLimit: 100,
    maxLimit: 1000,
    dateFormat: 'YYYY-MM-DD'
  },
  
  // 디버그 모드
  debug: true
};

