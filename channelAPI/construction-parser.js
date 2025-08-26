const moment = require('moment');

/**
 * 시공일 정보 파싱 클래스
 * 유연한 필터링 및 중복 처리 로직 포함
 */
class ConstructionParser {
  constructor() {
    // 개선된 정규식 패턴 - 줄바꿈과 공백을 무시하고 다음 헤더나 숫자 리스트 전까지 모든 내용을 가져옴
    this.fieldPatterns = {
      constructionDate: /시\s*공\s*일\s*:\s*([^]*?)(?=\s*(?:고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      customerName: /고\s*객\s*명\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      vendor: /발\s*주\s*사\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      measurementDate: /실\s*측\s*일\s*:\s*([^]*?)(?=\s*(?:고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      address: /주\s*소\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      contact: /연\s*락\s*처\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      productName: /제\s*품\s*명\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      size: /규\s*격\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      interior: /내\s*부\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      color: /색\s*상\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      option: /옵\s*션\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      handle: /손\s*잡\s*이\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|기\s*타)\s*:|\s*\d+\s*\.|$)/i,
      etc: /기\s*타\s*:\s*([^]*?)(?=\s*(?:시\s*공\s*일|고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이)\s*:|\s*\d+\s*\.|$)/i,
    };

    // 그룹 우선순위 정의 (높은 숫자가 높은 우선순위) - 가장 최근 업데이트 순서
    this.groupPriorities = {
      '229625': 3, // 발주방 (최종 업데이트 - 가장 최근)
      '209990': 2, // 영업팀_발주정보 (중간 업데이트)
      '229923': 1  // 실측스케쥴 (초기 등록)
    };
  }

  /**
   * 단일 메시지에서 시공일 정보를 파싱합니다.
   * @param {Object} message - 채널톡 메시지 객체
   * @returns {Object|null} 파싱된 시공일 정보 또는 null (유효하지 않은 경우)
   */
  parseMessage(message) {
    const text = message.plainText || '';
    const parsedData = {};
    let hasRequiredFields = false;

    // 시공일 키워드가 있는지 확인
    const hasConstructionKeyword = /시\s*공\s*일/i.test(text);
    if (!hasConstructionKeyword) {
      return null;
    }

    for (const key in this.fieldPatterns) {
      const match = text.match(this.fieldPatterns[key]);
      if (match && match[1]) {
        // 줄바꿈과 공백을 정리하여 저장
        parsedData[key] = this.cleanFieldValue(match[1]);
        if (key === 'customerName') {
          hasRequiredFields = true;
        }
      }
    }

    // 시공일 파싱 개선 - 더 유연한 패턴으로 재시도
    if (!parsedData.constructionDate) {
      const constructionMatch = text.match(/시\s*공\s*일\s*:\s*([^]*?)(?=\s*(?:고\s*객\s*명|발\s*주\s*사|실\s*측\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|\s*\d+\s*\.|$)/i);
      if (constructionMatch && constructionMatch[1]) {
        parsedData.constructionDate = this.cleanFieldValue(constructionMatch[1]);
      }
    }

    // 고객명이 없으면 유효하지 않은 것으로 간주
    if (!parsedData.customerName) {
      return null;
    }

    // 최소한 고객명은 있어야 유효한 메시지로 간주
    if (!hasRequiredFields) {
      return null;
    }

    return {
      messageId: message.id,
      createdAt: message.createdAt,
      plainText: text,
      parsedData: parsedData,
      groupId: message.group || 'unknown',
      groupPriority: this.groupPriorities[message.group] || 0
    };
  }

  /**
   * 필드 값을 정리합니다 (줄바꿈, 공백 처리)
   * @param {string} value - 정리할 필드 값
   * @returns {string} 정리된 필드 값
   */
  cleanFieldValue(value) {
    if (!value) return '';
    
    return value
      .replace(/\r\n/g, ' ') // Windows 줄바꿈을 공백으로
      .replace(/\n/g, ' ')   // Unix 줄바꿈을 공백으로
      .replace(/\r/g, ' ')   // Mac 줄바꿈을 공백으로
      .replace(/\s+/g, ' ')  // 연속된 공백을 하나로
      .trim();               // 앞뒤 공백 제거
  }

  /**
   * 메시지 배열에서 시공일 정보를 파싱합니다.
   * @param {Array} messages - 채널톡 메시지 객체 배열
   * @returns {Array} 파싱된 시공일 정보 배열
   */
  parseMessages(messages) {
    const constructions = [];
    messages.forEach(message => {
      const parsed = this.parseMessage(message);
      if (parsed) {
        constructions.push(parsed);
      }
    });
    return constructions;
  }

  /**
   * 중복 제거 및 최신 정보 우선 처리
   * @param {Array} constructionInfos - 시공일 정보 배열
   * @returns {Array} 중복 제거된 시공일 정보 배열
   */
  removeDuplicates(constructionInfos) {
    if (!constructionInfos || constructionInfos.length === 0) {
      return [];
    }

    console.log(`🔍 중복 제거 시작: ${constructionInfos.length}개 항목`);
    
    const uniqueMap = new Map();
    
    // 그룹 우선순위와 생성 시간 기준으로 정렬
    const sortedInfos = constructionInfos.sort((a, b) => {
      // 1. 그룹 우선순위 (높은 것이 먼저)
      if (a.groupPriority !== b.groupPriority) {
        return b.groupPriority - a.groupPriority;
      }
      // 2. 생성 시간 (최신이 먼저)
      return new Date(b.createdAt) - new Date(a.createdAt);
    });

    let addedCount = 0;
    let skippedCount = 0;

    for (const info of sortedInfos) {
      if (!info || !info.parsedData) {
        continue;
      }
      
      const parsedData = info.parsedData;
      const customerName = parsedData.customerName || '';
      
      // 고객명만으로 중복 판단 (동일 고객의 가장 최근 정보만 유지)
      const uniqueKey = customerName;

      // 맵에 없으면 추가 (우선순위가 높은 것과 최신 정보가 먼저 정렬되었으므로)
      if (!uniqueMap.has(uniqueKey)) {
        uniqueMap.set(uniqueKey, info);
        console.log(`✅ [중복 제거] ${customerName} - ${parsedData.constructionDate || 'N/A'} (새로 추가)`);
        addedCount++;
      } else {
        const existingInfo = uniqueMap.get(uniqueKey);
        const existingDate = existingInfo.parsedData.constructionDate || 'N/A';
        console.log(`🔄 [중복 제거] ${customerName} - ${parsedData.constructionDate || 'N/A'} (이미 존재: ${existingDate})`);
        skippedCount++;
      }
    }

    const result = Array.from(uniqueMap.values());
    console.log(`✅ 중복 제거 완료: ${constructionInfos.length}개 → ${result.length}개 (추가: ${addedCount}개, 제외: ${skippedCount}개)`);

    return result;
  }

  /**
   * 시공일 정보 통계 생성
   * @param {Array} constructionInfos - 시공일 정보 배열
   * @returns {Object} 통계 정보
   */
  generateStatistics(constructionInfos) {
    if (!constructionInfos || constructionInfos.length === 0) {
      return {
        totalCount: 0,
        vendorStats: {},
        productStats: {},
        monthlyStats: {}
      };
    }

    const vendorStats = {};
    const productStats = {};
    const monthlyStats = {};

    constructionInfos.forEach(info => {
      if (!info || !info.parsedData) {
        return;
      }
      
      const parsedData = info.parsedData;
      
      // 발주사별 통계
      if (parsedData.vendor) {
        vendorStats[parsedData.vendor] = (vendorStats[parsedData.vendor] || 0) + 1;
      }

      // 제품별 통계
      if (parsedData.productName) {
        productStats[parsedData.productName] = (productStats[parsedData.productName] || 0) + 1;
      }

      // 월별 통계
      if (parsedData.constructionDate) {
        const month = moment(parsedData.constructionDate, ['YYYY-MM-DD', 'MM월 DD일', 'M월 D일', 'YYYY.MM.DD', 'YY.MM.DD', 'MM.DD']).format('YYYY-MM');
        if (month !== 'Invalid date') {
          monthlyStats[month] = (monthlyStats[month] || 0) + 1;
        }
      }
    });

    return {
      totalCount: constructionInfos.length,
      vendorStats,
      productStats,
      monthlyStats
    };
  }
}

module.exports = ConstructionParser;
