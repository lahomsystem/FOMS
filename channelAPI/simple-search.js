const SimpleChannelAPI = require('./simple-channel-api');
const ConstructionParser = require('./construction-parser');
const moment = require('moment');

/**
 * 간단한 시공일 검색 클래스
 * 요청 제한 없이 빠르게 검색
 */
class SimpleSearch {
  constructor(api, parser) {
    this.api = api;
    this.parser = parser;
    
    this.groups = {
      salesOrder: { id: '209990', name: '영업팀_발주정보' },
      orderRoom: { id: '229625', name: '발주방' },
      measurementSchedule: { id: '229923', name: '실측스케쥴' }
    };
  }

  /**
   * 간단한 시공일 검색 (제한된 메시지만)
   * @param {string} startDate - 검색 시작 날짜
   * @returns {Promise<Object>} 검색 결과
   */
  async simpleSearch(startDate) {
    console.log('⚡ 간단한 시공일 검색 시작');
    const startTime = Date.now();

    try {
      // 실측스케쥴 그룹만 빠르게 테스트 (최근 100개 메시지만)
      const result = await this.searchGroupLimited(this.groups.measurementSchedule, startDate, 100);
      
      const endTime = Date.now();
      const searchDuration = endTime - startTime;

      console.log(`⚡ 간단한 검색 완료: ${searchDuration}ms`);
      console.log(`📊 결과: ${result.constructions.length}개 시공일 정보`);

      return {
        searchInfo: {
          startDate,
          searchDuration: `${searchDuration}ms`,
          searchMethod: 'simple',
          timestamp: new Date().toISOString()
        },
        summary: {
          totalGroups: 1,
          totalMessages: result.summary.totalMessages,
          filteredMessages: result.summary.filteredMessages,
          totalConstructions: result.constructions.length
        },
        constructions: result.constructions,
        performance: {
          duration: searchDuration,
          messagesPerSecond: Math.round(result.summary.totalMessages / (searchDuration / 1000))
        }
      };

    } catch (error) {
      console.error('❌ 간단한 검색 실패:', error);
      throw error;
    }
  }

  /**
   * 제한된 메시지로 그룹 검색
   * @param {Object} group - 그룹 정보
   * @param {string} startDate - 시작 날짜
   * @param {number} maxMessages - 최대 메시지 수
   * @returns {Promise<Object>} 그룹 검색 결과
   */
  async searchGroupLimited(group, startDate, maxMessages = 100) {
    console.log(`⚡ ${group.name} 그룹 간단 검색 시작 (최대 ${maxMessages}개)`);
    const groupStartTime = Date.now();

    try {
      const constructions = [];
      let totalMessages = 0;
      let nextToken = null;

      // 제한된 메시지만 가져오기
      while (totalMessages < maxMessages) {
        const params = { limit: Math.min(50, maxMessages - totalMessages) };
        if (nextToken) {
          params.next = nextToken;
        }

        const response = await this.api.getGroupMessages(group.id, params);
        const messages = response.messages || [];
        nextToken = response.next;
        
        totalMessages += messages.length;
        
        // 날짜 필터링
        const filteredMessages = this.filterMessagesByDate(messages, startDate);
        
        // 즉시 파싱
        const batchConstructions = this.parser.parseMessages(filteredMessages);
        constructions.push(...batchConstructions);
        
        console.log(`📦 ${group.name}: ${messages.length}개 메시지, ${batchConstructions.length}개 시공일`);
        
        // 더 이상 메시지가 없으면 종료
        if (!nextToken || messages.length === 0) {
          break;
        }
      }

      const groupDuration = Date.now() - groupStartTime;
      
      console.log(`✅ ${group.name} 검색 완료: ${constructions.length}개 시공일 (${groupDuration}ms)`);

      return {
        groupId: group.id,
        groupName: group.name,
        searchInfo: { 
          startDate, 
          totalMessagesFetched: totalMessages,
          maxMessages,
          duration: groupDuration
        },
        summary: {
          totalMessages,
          filteredMessages: constructions.length,
          constructionCount: constructions.length
        },
        constructions,
        performance: {
          duration: groupDuration
        }
      };

    } catch (error) {
      console.error(`❌ ${group.name} 그룹 검색 실패:`, error);
      throw error;
    }
  }

  /**
   * 실시간 날짜 필터링
   * @param {Array} messages - 메시지 배열
   * @param {string} startDate - 시작 날짜
   * @returns {Array} 필터링된 메시지 배열
   */
  filterMessagesByDate(messages, startDate) {
    if (!startDate || !messages || messages.length === 0) {
      return messages;
    }
    
    const startTimestamp = new Date(startDate + 'T00:00:00+09:00').getTime();
    
    return messages.filter(message => {
      if (!message.createdAt) return false;
      return parseInt(message.createdAt) >= startTimestamp;
    });
  }
}

module.exports = SimpleSearch;
