#!/usr/bin/env node

const ChannelAPI = require('./channel-api');
const MeasurementParser = require('./measurement-parser');

/**
 * 실측스케쥴 그룹 전용 검색 클래스
 */
class MeasurementGroupSearcher {
  constructor() {
    this.api = new ChannelAPI();
    this.parser = new MeasurementParser();
  }

  /**
   * 실측스케쥴 그룹에서 실측 정보 검색
   * @param {string} startDate - 검색 시작 날짜 (YYYY-MM-DD)
   * @param {number} limit - 검색할 메시지 수 (기본: 100)
   * @returns {Promise<Object>} 검색 결과
   */
  async searchMeasurementSchedules(startDate = null, limit = 100) {
    console.log('🎯 실측스케쥴 그룹에서 실측 정보 검색 시작');
    console.log(`📅 검색 기준일: ${startDate || '전체'}`);
    console.log(`📄 검색할 메시지 수: ${limit}개`);

    try {
      // 1. 실측스케쥴 그룹 메시지 조회
      const response = await this.api.getMeasurementScheduleMessages({ limit });
      const messages = response.messages || [];
      
      console.log(`📥 실측스케쥴 그룹에서 ${messages.length}개 메시지 조회됨`);

      // 2. 날짜 필터링 (옵션)
      let filteredMessages = messages;
      if (startDate) {
        filteredMessages = this.filterMessagesByDate(messages, startDate);
        console.log(`📅 날짜 필터링 후: ${filteredMessages.length}개 메시지`);
      }

      // 3. 실측 정보 추출
      const measurementResults = this.parser.parseMessages(filteredMessages);
      console.log(`🎯 실측 정보 추출 완료: ${measurementResults.length}개`);

      // 4. 통계 생성
      const statistics = this.parser.generateStatistics(measurementResults);

      return {
        searchInfo: {
          groupName: '실측스케쥴',
          groupId: '229923',
          startDate: startDate,
          limit: limit,
          searchTime: new Date().toISOString()
        },
        summary: {
          totalMessages: messages.length,
          filteredMessages: filteredMessages.length,
          measurementCount: measurementResults.length
        },
        measurements: measurementResults,
        statistics: statistics,
        next: response.next // 다음 페이지 토큰
      };

    } catch (error) {
      console.error('❌ 실측스케쥴 그룹 검색 실패:', error.message);
      throw error;
    }
  }

  /**
   * 페이지네이션을 이용한 대량 실측 정보 검색
   * @param {string} startDate - 검색 시작 날짜
   * @param {number} maxPages - 최대 페이지 수 (기본: 5)
   * @param {number} limitPerPage - 페이지당 메시지 수 (기본: 100)
   * @returns {Promise<Object>} 검색 결과
   */
  async searchMeasurementSchedulesWithPagination(startDate = null, maxPages = 5, limitPerPage = 100) {
    console.log('🎯 실측스케쥴 그룹 대량 검색 시작 (페이지네이션)');
    console.log(`📄 최대 ${maxPages}페이지 × ${limitPerPage}개씩 = 최대 ${maxPages * limitPerPage}개 메시지 검색`);

    const allMeasurements = [];
    const allMessages = [];
    let nextToken = null;
    let currentPage = 1;

    try {
      while (currentPage <= maxPages) {
        console.log(`\n📖 페이지 ${currentPage}/${maxPages} 검색 중...`);
        
        const params = { limit: limitPerPage };
        if (nextToken) {
          params.next = nextToken;
        }

        // 그룹 메시지 조회
        const response = await this.api.getMeasurementScheduleMessages(params);
        const messages = response.messages || [];
        
        if (messages.length === 0) {
          console.log('📄 더 이상 메시지가 없습니다.');
          break;
        }

        console.log(`📥 페이지 ${currentPage}: ${messages.length}개 메시지 조회됨`);
        allMessages.push(...messages);

        // 날짜 필터링
        let filteredMessages = messages;
        if (startDate) {
          filteredMessages = this.filterMessagesByDate(messages, startDate);
          console.log(`📅 날짜 필터링 후: ${filteredMessages.length}개 메시지`);
        }

        // 실측 정보 추출
        const measurementResults = this.parser.parseMessages(filteredMessages);
        console.log(`🎯 페이지 ${currentPage} 실측 정보: ${measurementResults.length}개`);
        
        allMeasurements.push(...measurementResults);

        // 다음 페이지 토큰 확인
        nextToken = response.next;
        if (!nextToken) {
          console.log('📄 마지막 페이지에 도달했습니다.');
          break;
        }

        currentPage++;
        
        // API 호출 제한을 위한 대기
        await new Promise(resolve => setTimeout(resolve, 500));
      }

      // 통계 생성
      const statistics = this.parser.generateStatistics(allMeasurements);

      console.log(`\n🎯 대량 검색 완료!`);
      console.log(`📊 총 ${allMessages.length}개 메시지에서 ${allMeasurements.length}개 실측 정보 추출`);

      return {
        searchInfo: {
          groupName: '실측스케쥴',
          groupId: '229923',
          startDate: startDate,
          maxPages: maxPages,
          limitPerPage: limitPerPage,
          actualPages: currentPage - 1,
          searchTime: new Date().toISOString()
        },
        summary: {
          totalMessages: allMessages.length,
          measurementCount: allMeasurements.length,
          pagesSearched: currentPage - 1
        },
        measurements: allMeasurements,
        statistics: statistics
      };

    } catch (error) {
      console.error('❌ 실측스케쥴 그룹 대량 검색 실패:', error.message);
      throw error;
    }
  }

  /**
   * 날짜로 메시지 필터링 (채널톡 UI 표시 기준)
   * @param {Array} messages - 메시지 배열
   * @param {string} startDate - 시작 날짜 (YYYY-MM-DD)
   * @returns {Array} 필터링된 메시지 배열
   */
  filterMessagesByDate(messages, startDate) {
    if (!startDate || !messages) return messages;
    
    // 검색 기준 날짜 (KST 기준 00:00:00)
    const startDateTime = new Date(startDate + 'T00:00:00+09:00');
    
    return messages.filter(message => {
      if (!message.createdAt) return false;
      
      const messageTimestamp = parseInt(message.createdAt);
      
      // 채널톡 API 타임스탬프는 이미 KST 기준이므로 직접 사용
      const messageDate = new Date(messageTimestamp);
      
      // 채널톡 UI에서 표시되는 날짜 기준으로 비교
      // 메시지 날짜를 KST 기준 날짜로 정규화
      const messageYear = messageDate.getFullYear();
      const messageMonth = messageDate.getMonth();
      const messageDay = messageDate.getDate();
      
      const startYear = startDateTime.getFullYear();
      const startMonth = startDateTime.getMonth();
      const startDay = startDateTime.getDate();
      
      // 년-월-일 기준으로 비교 (시간은 무시)
      const messageDateOnly = new Date(messageYear, messageMonth, messageDay);
      const startDateOnly = new Date(startYear, startMonth, startDay);
      
      console.log(`[DEBUG] 메시지 날짜 비교: 
        원본 타임스탬프: ${messageTimestamp}
        변환된 날짜: ${messageDate.toISOString()}
        메시지 날짜: ${messageDateOnly.toLocaleDateString('ko-KR')}
        기준 날짜: ${startDateOnly.toLocaleDateString('ko-KR')}
        결과: ${messageDateOnly >= startDateOnly}`);
      
      return messageDateOnly >= startDateOnly;
    });
  }

  /**
   * 실측스케쥴 그룹의 최신 메시지들 미리보기
   * @param {number} limit - 조회할 메시지 수 (기본: 10)
   * @returns {Promise<Array>} 메시지 미리보기 배열
   */
  async previewRecentMessages(limit = 10) {
    try {
      const response = await this.api.getMeasurementScheduleMessages({ limit });
      const messages = response.messages || [];
      
      return messages.map(msg => ({
        id: msg.id,
        createdAt: new Date(parseInt(msg.createdAt)).toLocaleString('ko-KR'),
        author: msg.personType === 'manager' ? `Manager-${msg.personId}` : 'User',
        content: (msg.plainText || '').substring(0, 100) + (msg.plainText?.length > 100 ? '...' : ''),
        isRealMeasurement: this.parser.isMeasurementMessage(msg.plainText || '')
      }));
    } catch (error) {
      console.error('❌ 메시지 미리보기 실패:', error.message);
      throw error;
    }
  }
}

module.exports = MeasurementGroupSearcher;
