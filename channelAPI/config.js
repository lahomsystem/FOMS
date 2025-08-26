// 채널톡 API 설정 파일
// 실제 API 키가 포함된 설정

module.exports = {
  // 채널톡 API 인증 정보
  channelAuth: {
    accessKey: '68a7f6b5cb82a6d7ddf1',
    secretKey: '3b1dd0cf2cee675fd1958f176bf6bd73'
  },
  
  // API 기본 설정
  api: {
    baseUrl: 'https://api.channel.io',
    version: 'v5',
    timeout: 30000, // 30초로 증가
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
