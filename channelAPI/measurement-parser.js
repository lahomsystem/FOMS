const moment = require('moment');

/**
 * 실측 스케쥴 메시지 파서
 * 간단하고 확실한 정규식 기반 파싱
 */
class MeasurementParser {
  constructor() {
    // 정규식 패턴으로 공백 문제 해결
    this.fieldPatterns = {
      measurementDate: /실\s*측\s*일\s*:\s*([^:\n]+?)(?=\s*(?:고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      customerName: /고\s*객\s*명\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      vendor: /발\s*주\s*사\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      constructionDate: /시\s*공\s*일\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      address: /주\s*소\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      contact: /연\s*락\s*처\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      productName: /제\s*품\s*명\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      specification: /규\s*격\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      interior: /내\s*부\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|색\s*상|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      color: /색\s*상\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|옵\s*션|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      option: /옵\s*션\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|손\s*잡\s*이|기\s*타)\s*:|$)/i,
      handle: /손\s*잡\s*이\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|기\s*타)\s*:|$)/i,
      etc: /기\s*타\s*:\s*([^:\n]+?)(?=\s*(?:실\s*측\s*일|고\s*객\s*명|발\s*주\s*사|시\s*공\s*일|주\s*소|연\s*락\s*처|제\s*품\s*명|규\s*격|내\s*부|색\s*상|옵\s*션|손\s*잡\s*이)\s*:|$)/i
    };

    // 제외할 발주사 목록
    this.excludedVendors = ['라홈', 'LAHOM', 'lahom', 'Lahom'];
  }

  /**
   * 메시지에서 실측 정보 추출
   * @param {string} messageContent - 메시지 내용
   * @returns {Object|null} 파싱된 실측 정보 또는 null
   */
  parseMeasurementInfo(messageContent) {
    if (!messageContent || typeof messageContent !== 'string') {
      return null;
    }

    // 실측 메시지인지 확인
    if (!this.isMeasurementMessage(messageContent)) {
      return null;
    }

    console.log(`🎯 [DEBUG] 실측 후보 메시지 발견: ${messageContent.substring(0, 100)}...`);

    // 정규식으로 한 번에 파싱
    const parsedData = {};
    
    for (const [field, pattern] of Object.entries(this.fieldPatterns)) {
      const match = messageContent.match(pattern);
      if (match) {
        parsedData[field] = match[1].trim();
      }
    }

    // 발주사 필터링 (라홈 제외)
    if (this.shouldExcludeByVendor(parsedData.vendor)) {
      console.log(`❌ [DEBUG] 실측 정보 파싱 실패 - 라홈 발주사 제외`);
      return null;
    }

    // 필수 필드 확인
    if (this.hasRequiredFields(parsedData)) {
      console.log(`✅ [DEBUG] 실측 정보 파싱 성공!`);
      return {
        ...parsedData,
        parsedAt: new Date().toISOString(),
        isValid: true,
        parsedBy: 'regex'
      };
    }

    console.log(`❌ [DEBUG] 실측 정보 파싱 실패`);
    return null;
  }

  /**
   * 실측 메시지인지 확인
   * @param {string} content - 메시지 내용
   * @returns {boolean}
   */
  isMeasurementMessage(content) {
    // 정규식으로 실측일 키워드 확인 (공백 무관)
    const measurementPattern = /실\s*측\s*일\s*:/i;
    const customerPattern = /고\s*객\s*명\s*:/i;
    
    const hasMeasurementDate = measurementPattern.test(content);
    const hasCustomerName = customerPattern.test(content);
    
    console.log(`🔍 [DEBUG] 실측 메시지 확인 - 실측일: ${hasMeasurementDate}, 고객명: ${hasCustomerName}`);
    
    // 실측일과 고객명이 모두 있어야 실측 메시지로 판단
    return hasMeasurementDate && hasCustomerName;
  }

  /**
   * 필수 필드가 있는지 확인
   * @param {Object} data - 파싱된 데이터
   * @returns {boolean}
   */
  hasRequiredFields(data) {
    // 실측 정보의 필수 필드: 고객명, 실측일
    const requiredFields = ['customerName', 'measurementDate'];
    const hasRequired = requiredFields.every(field => data[field] && data[field].trim() !== '');
    
    console.log(`🔍 [DEBUG] 필수 필드 확인 - 데이터:`, data);
    console.log(`🔍 [DEBUG] 중요 필드 존재 여부: ${hasRequired}`);
    
    return hasRequired;
  }

  /**
   * 발주사로 제외해야 하는지 확인
   * @param {string} vendor - 발주사명
   * @returns {boolean} true면 제외
   */
  shouldExcludeByVendor(vendor) {
    if (!vendor) return false;
    
    const normalizedVendor = vendor.trim().toLowerCase();
    return this.excludedVendors.some(excluded => 
      normalizedVendor.includes(excluded.toLowerCase())
    );
  }

  /**
   * 메시지 배열에서 실측 정보 추출
   * @param {Array} messages - 메시지 배열
   * @returns {Array} 파싱된 실측 정보 배열
   */
  parseMessages(messages) {
    if (!Array.isArray(messages)) {
      return [];
    }

    const results = [];
    let textMessageCount = 0;
    let measurementCandidates = 0;

    for (const message of messages) {
      // 텍스트 메시지만 처리
      const isTextMessage = message.type === 'text' || message.blocks?.some(block => block.type === 'text');
      const messageText = message.plainText || message.content || '';

      if (!isTextMessage || !messageText) {
        continue;
      }

      textMessageCount++;

      // 실측 관련 키워드가 있는지 먼저 확인
      if (this.containsMeasurementKeywords(messageText)) {
        measurementCandidates++;
        
        const parsed = this.parseMeasurementInfo(messageText);
        if (parsed) {
          results.push({
            messageId: message.id,
            createdAt: message.createdAt,
            manager: this.getManagerName(message),
            rawContent: messageText,
            parsedData: parsed
          });
        }
      }
    }

    console.log(`🔍 [DEBUG] 추출 완료 - 텍스트 메시지: ${textMessageCount}개, 실측 후보: ${measurementCandidates}개, 파싱 성공: ${results.length}개`);
    return results;
  }

  /**
   * 실측 관련 키워드가 포함되어 있는지 확인
   * @param {string} content - 메시지 내용
   * @returns {boolean}
   */
  containsMeasurementKeywords(content) {
    const keywords = ['실측일', '고객명', '발주사', '연락처', '제품명', '주소'];
    return keywords.some(keyword => content.includes(keyword));
  }

  /**
   * 매니저 이름 추출
   * @param {Object} message - 메시지 객체
   * @returns {string} 매니저명
   */
  getManagerName(message) {
    if (message.personType === 'manager') {
      return `Manager-${message.personId}`;
    }
    return 'User';
  }

  /**
   * 실측 정보 통계 생성
   * @param {Array} measurementInfos - 실측 정보 배열
   * @returns {Object} 통계 정보
   */
  generateStatistics(measurementInfos) {
    if (!measurementInfos || measurementInfos.length === 0) {
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

    measurementInfos.forEach(info => {
      // 발주사별 통계
      if (info.vendor) {
        vendorStats[info.vendor] = (vendorStats[info.vendor] || 0) + 1;
      }

      // 제품별 통계
      if (info.productName) {
        productStats[info.productName] = (productStats[info.productName] || 0) + 1;
      }

      // 월별 통계 (실측일 기준)
      if (info.measurementDate) {
        try {
          const month = this.extractMonthFromDate(info.measurementDate);
          if (month) {
            monthlyStats[month] = (monthlyStats[month] || 0) + 1;
          }
        } catch (error) {
          // 날짜 파싱 실패는 무시
        }
      }
    });

    return {
      totalCount: measurementInfos.length,
      vendorStats,
      productStats,
      monthlyStats
    };
  }

  /**
   * 날짜 문자열에서 월 추출
   * @param {string} dateString - 날짜 문자열
   * @returns {string|null} "YYYY-MM" 형식의 월 또는 null
   */
  extractMonthFromDate(dateString) {
    // "9월 3일", "9월", "2025-09-03" 등 다양한 형식 지원
    const monthMatch = dateString.match(/(\d+)월/);
    if (monthMatch) {
      const month = parseInt(monthMatch[1]);
      const currentYear = new Date().getFullYear();
      return `${currentYear}-${month.toString().padStart(2, '0')}`;
    }
    
    // ISO 날짜 형식
    const isoMatch = dateString.match(/(\d{4})-(\d{2})/);
    if (isoMatch) {
      return `${isoMatch[1]}-${isoMatch[2]}`;
    }
    
    return null;
  }
}

module.exports = MeasurementParser;
