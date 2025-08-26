const ChannelAPI = require('./channel-api');
const ConstructionParser = require('./construction-parser');
const moment = require('moment');

/**
 * 발주 관련 그룹에서 시공일 정보를 검색하는 클래스
 * 영업팀_발주정보(209990), 발주방(229625), 실측스케쥴(229923) 그룹에서 시공일 정보를 추출합니다.
 */
class ConstructionGroupSearcher {
  constructor(api, parser) {
    this.api = api;
    this.parser = parser;
    
    // 그룹 정보
    this.groups = {
      salesOrder: {
        id: '209990',
        name: '영업팀_발주정보',
        description: '발주내용 올리신후 한번더 한번더 더더블 체크 필수 !!'
      },
      orderRoom: {
        id: '229625',
        name: '발주방',
        description: '발주방에 등록된 발주만 발주하세요 !!발주서만 올려주세요 (잡담금지)'
      },
      measurementSchedule: {
        id: '229923',
        name: '실측스케쥴',
        description: '실측 스케쥴 관리'
      }
    };
  }

  /**
   * 영업팀_발주정보 그룹에서 시공일 정보를 검색합니다.
   * @param {string} startDate - 검색 시작 날짜 (YYYY-MM-DD)
   * @param {number} limit - 가져올 메시지 수 제한
   * @returns {Promise<Object>} 검색 결과 (시공일 정보 배열 및 통계)
   */
  async searchConstructionInSalesOrderGroup(startDate, limit = 500) {
    console.log('🎯 영업팀_발주정보 그룹에서 시공일 정보 검색 시작');
    return await this.searchConstructionInGroup(this.groups.salesOrder, startDate, limit);
  }

  /**
   * 발주방 그룹에서 시공일 정보를 검색합니다.
   * @param {string} startDate - 검색 시작 날짜 (YYYY-MM-DD)
   * @param {number} limit - 가져올 메시지 수 제한
   * @returns {Promise<Object>} 검색 결과 (시공일 정보 배열 및 통계)
   */
  async searchConstructionInOrderRoomGroup(startDate, limit = 500) {
    console.log('🎯 발주방 그룹에서 시공일 정보 검색 시작');
    return await this.searchConstructionInGroup(this.groups.orderRoom, startDate, limit);
  }

  /**
   * 실측스케쥴 그룹에서 시공일 정보를 검색합니다.
   * @param {string} startDate - 검색 시작 날짜 (YYYY-MM-DD)
   * @param {number} limit - 가져올 메시지 수 제한
   * @returns {Promise<Object>} 검색 결과 (시공일 정보 배열 및 통계)
   */
  async searchConstructionInMeasurementScheduleGroup(startDate, limit = 500) {
    console.log('🎯 실측스케쥴 그룹에서 시공일 정보 검색 시작');
    return await this.searchConstructionInGroup(this.groups.measurementSchedule, startDate, limit);
  }

  /**
   * 모든 발주 관련 그룹에서 시공일 정보를 검색합니다.
   * @param {string} startDate - 검색 시작 날짜 (YYYY-MM-DD)
   * @param {number} limit - 각 그룹별 가져올 메시지 수 제한
   * @returns {Promise<Object>} 검색 결과 (모든 그룹의 시공일 정보 통합)
   */
  async searchConstructionInAllGroups(startDate, limit = 500) {
    console.log('🎯 모든 발주 관련 그룹 + 실측스케쥴에서 시공일 정보 검색 시작');
    
    try {
      const results = await Promise.all([
        this.searchConstructionInSalesOrderGroup(startDate, limit),
        this.searchConstructionInOrderRoomGroup(startDate, limit),
        this.searchConstructionInMeasurementScheduleGroup(startDate, limit)
      ]);

      // 결과 통합
      const allConstructions = [];
      const groupResults = [];

      results.forEach((result, index) => {
        groupResults.push(result);
        allConstructions.push(...result.constructions);
      });

      console.log(`📊 전체 시공일 정보: ${allConstructions.length}개`);

      // 중복 제거 및 최신 정보 우선 처리
      const uniqueConstructions = this.parser.removeDuplicates(allConstructions);

      console.log(`📊 중복 제거 후: ${uniqueConstructions.length}개`);

      // 통합 통계 생성
      const combinedStatistics = this.parser.generateStatistics(uniqueConstructions.map(c => c.parsedData));

      return {
        searchInfo: {
          startDate,
          limit,
          totalGroupsSearched: results.length,
          searchTime: new Date().toISOString()
        },
        summary: {
          totalGroups: results.length,
          totalMessages: results.reduce((sum, r) => sum + r.summary.totalMessages, 0),
          filteredMessages: results.reduce((sum, r) => sum + r.summary.filteredMessages, 0),
          totalConstructions: uniqueConstructions.length,
          duplicateRemoved: allConstructions.length - uniqueConstructions.length
        },
        groupResults,
        constructions: uniqueConstructions,
        statistics: combinedStatistics
      };

    } catch (error) {
      console.error('❌ 모든 그룹 시공일 검색 실패:', error.message);
      throw error;
    }
  }

  /**
   * 특정 그룹에서 시공일 정보를 검색합니다.
   * @param {Object} group - 그룹 정보 (id, name, description)
   * @param {string} startDate - 검색 시작 날짜 (YYYY-MM-DD)
   * @param {number} limit - 가져올 메시지 수 제한
   * @returns {Promise<Object>} 검색 결과
   */
  async searchConstructionInGroup(group, startDate, limit = 500) {
    console.log(`📅 검색 기준일: ${startDate || '전체'}`);
    console.log(`📄 검색할 메시지 수: ${limit}개`);

    try {
      let allMessages = [];
      let nextToken = null;
      let fetchedCount = 0;

      do {
        const params = { limit: Math.min(limit - fetchedCount, 100) }; // API limit max 100
        if (nextToken) {
          params.next = nextToken;
        }

        const response = await this.api.getGroupMessages(group.id, params);
        const messages = response.messages || [];
        allMessages.push(...messages);
        fetchedCount += messages.length;
        nextToken = response.next;

        if (fetchedCount >= limit) {
          break;
        }
      } while (nextToken);

      console.log(`📥 ${group.name} 그룹에서 ${allMessages.length}개 메시지 조회됨`);

      // 날짜 필터링 (한국 표준시 기준)
      let filteredMessages = allMessages;
      if (startDate) {
        filteredMessages = this.filterMessagesByDate(allMessages, startDate);
        console.log(`📅 날짜 필터링 후: ${filteredMessages.length}개 메시지`);
      }

      const extractedConstructions = this.parser.parseMessages(filteredMessages);
      console.log(`🎯 시공일 정보 추출 완료: ${extractedConstructions.length}개`);

      const statistics = this.parser.generateStatistics(extractedConstructions.map(c => c.parsedData));

      return {
        groupId: group.id,
        groupName: group.name,
        searchInfo: { 
          startDate, 
          limit, 
          totalMessagesFetched: allMessages.length, 
          filteredMessagesCount: filteredMessages.length 
        },
        summary: {
          totalMessages: allMessages.length,
          filteredMessages: filteredMessages.length,
          constructionCount: extractedConstructions.length
        },
        constructions: extractedConstructions,
        statistics: statistics
      };

    } catch (error) {
      console.error(`❌ ${group.name} 그룹 메시지 검색 실패:`, error.message);
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
    
    console.log(`🔍 날짜 필터링 시작: ${startDate} 이후 메시지 필터링`);
    
    // 검색 기준 날짜 (KST 기준 00:00:00)
    const startDateTime = new Date(startDate + 'T00:00:00+09:00');
    const startTimestamp = startDateTime.getTime();
    
    console.log(`📅 검색 기준 타임스탬프: ${startTimestamp} (${startDateTime.toISOString()})`);
    
    const filteredMessages = messages.filter(message => {
      if (!message.createdAt) return false;
      
      const messageTimestamp = parseInt(message.createdAt);
      const messageDate = new Date(messageTimestamp);
      
      // 디버깅을 위해 처음 몇 개 메시지의 타임스탬프 출력
      if (messages.indexOf(message) < 3) {
        console.log(`📅 메시지 ${messages.indexOf(message) + 1}: ${messageTimestamp} (${messageDate.toISOString()}) - ${messageTimestamp >= startTimestamp ? '포함' : '제외'}`);
      }
      
      // 메시지가 시작 날짜 이후인지 확인
      return messageTimestamp >= startTimestamp;
    });
    
    console.log(`📅 날짜 필터링 결과: ${messages.length}개 → ${filteredMessages.length}개`);
    
    return filteredMessages;
  }
}

module.exports = ConstructionGroupSearcher;
