const axios = require('axios');
const config = require('./config');

/**
 * 간단한 채널톡 API 클래스
 * 요청 제한 관리 없이 즉시 API 호출
 */
class SimpleChannelAPI {
  constructor() {
    this.baseUrl = `${config.api.baseUrl}/open/${config.api.version}`;
    this.accessKey = config.channelAuth.accessKey;
    this.secretKey = config.channelAuth.secretKey;
    this.timeout = 15000; // 15초 타임아웃
    
    // axios 인스턴스 생성 (요청 제한 관리 완전 제거)
    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
        'x-access-key': this.accessKey,
        'x-access-secret': this.secretKey
      }
    });

    // 간단한 에러 처리
    this.client.interceptors.response.use(
      response => response,
      error => {
        console.error('API 요청 오류:', error.response?.data || error.message);
        return Promise.reject(error);
      }
    );
  }

  /**
   * 매니저 목록 조회 (연결 테스트용)
   * @returns {Promise<Object>} API 응답
   */
  async getManagers() {
    try {
      const response = await this.client.get('/managers');
      return response.data;
    } catch (error) {
      throw new Error(`매니저 목록 조회 실패: ${error.message}`);
    }
  }

  /**
   * 그룹 정보 조회
   * @returns {Promise<Object>} API 응답
   */
  async getGroups() {
    try {
      const response = await this.client.get('/groups');
      return response.data;
    } catch (error) {
      throw new Error(`그룹 목록 조회 실패: ${error.message}`);
    }
  }

  /**
   * 특정 그룹의 메시지 조회 (간단한 버전)
   * @param {string} groupId - 그룹 ID
   * @param {Object} params - 검색 파라미터 (limit, next 등)
   * @returns {Promise<Object>} API 응답
   */
  async getGroupMessages(groupId, params = {}) {
    try {
      const response = await this.client.get(`/groups/${groupId}/messages`, { params });
      return response.data;
    } catch (error) {
      throw new Error(`그룹 ${groupId} 메시지 조회 실패: ${error.message}`);
    }
  }

  /**
   * 실측스케쥴 그룹 메시지 조회
   * @param {Object} params - 검색 파라미터 (limit, next 등)
   * @returns {Promise<Object>} API 응답
   */
  async getMeasurementScheduleMessages(params = {}) {
    try {
      const MEASUREMENT_GROUP_ID = '229923';
      const response = await this.client.get(`/groups/${MEASUREMENT_GROUP_ID}/messages`, { params });
      return response.data;
    } catch (error) {
      throw new Error(`실측스케쥴 그룹 메시지 조회 실패: ${error.message}`);
    }
  }

  /**
   * 영업팀_발주정보 그룹 메시지 조회
   * @param {Object} params - 검색 파라미터 (limit, next 등)
   * @returns {Promise<Object>} API 응답
   */
  async getSalesOrderMessages(params = {}) {
    try {
      const SALES_ORDER_GROUP_ID = '209990';
      const response = await this.client.get(`/groups/${SALES_ORDER_GROUP_ID}/messages`, { params });
      return response.data;
    } catch (error) {
      throw new Error(`영업팀_발주정보 그룹 메시지 조회 실패: ${error.message}`);
    }
  }

  /**
   * 발주방 그룹 메시지 조회
   * @param {Object} params - 검색 파라미터 (limit, next 등)
   * @returns {Promise<Object>} API 응답
   */
  async getOrderRoomMessages(params = {}) {
    try {
      const ORDER_ROOM_GROUP_ID = '229625';
      const response = await this.client.get(`/groups/${ORDER_ROOM_GROUP_ID}/messages`, { params });
      return response.data;
    } catch (error) {
      throw new Error(`발주방 그룹 메시지 조회 실패: ${error.message}`);
    }
  }

  /**
   * API 연결 테스트
   * @returns {Promise<boolean>} 연결 성공 여부
   */
  async testConnection() {
    try {
      const startTime = Date.now();
      await this.getManagers();
      const endTime = Date.now();
      console.log(`✅ 채널톡 API 연결 성공 (${endTime - startTime}ms)`);
      return true;
    } catch (error) {
      console.error('❌ 채널톡 API 연결 실패:', error.message);
      return false;
    }
  }
}

module.exports = SimpleChannelAPI;
