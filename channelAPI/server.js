const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const cors = require('cors');
const path = require('path');
const moment = require('moment');

const ChannelAPI = require('./channel-api');
const MeasurementParser = require('./measurement-parser');
const MeasurementGroupSearcher = require('./measurement-group-search');
const ConstructionGroupSearcher = require('./construction-group-search');
const ConstructionParser = require('./construction-parser');

class ChannelMessageSearchServer {
  constructor() {
    this.app = express();
    this.server = http.createServer(this.app);
    this.io = socketIo(this.server, {
      cors: {
        origin: "*",
        methods: ["GET", "POST"]
      }
    });
    
    this.api = new ChannelAPI();
    this.measurementParser = new MeasurementParser();
    this.measurementGroupSearcher = new MeasurementGroupSearcher(this.api, this.measurementParser);
    this.constructionParser = new ConstructionParser();
    this.constructionGroupSearcher = new ConstructionGroupSearcher(this.api, this.constructionParser);
    this.port = process.env.PORT || 3000;

    this.setupMiddleware();
    this.setupRoutes();
    this.setupSocketHandlers();
  }

  setupMiddleware() {
    this.app.use(cors());
    this.app.use(express.json());
    this.app.use(express.static(path.join(__dirname, 'public')));
  }

  setupRoutes() {
    // 메인 페이지
    this.app.get('/', (req, res) => {
      res.sendFile(path.join(__dirname, 'public', 'index.html'));
    });


  }

  setupSocketHandlers() {
    this.io.on('connection', (socket) => {
      console.log('🔌 클라이언트 연결됨:', socket.id);



      // 실측 정보 검색 (실시간 진행상황 표시)
      socket.on('search-measurements', async (data) => {
        console.log('🎯 실측스케쥴 그룹에서 실측 정보 검색 시작:', data);
        
        try {
          const { startDate, maxMessages } = data;
          
          socket.emit('search-progress', { 
            status: 'starting', 
            message: '실측스케쥴 그룹에서 실측 정보를 검색합니다...' 
          });

          // 실측스케쥴 그룹에서 실측 정보 검색
          const result = await this.measurementGroupSearcher.searchMeasurementSchedules(
            startDate, 
            maxMessages || 100
          );
          
          socket.emit('search-progress', { 
            status: 'group-loaded', 
            message: `실측스케쥴 그룹에서 ${result.summary.totalMessages}개 메시지를 조회했습니다...`,
            totalMessages: result.summary.totalMessages
          });

          socket.emit('search-progress', { 
            status: 'parsing', 
            message: `${result.summary.measurementCount}개의 실측 정보를 발견했습니다!`,
            measurementCount: result.summary.measurementCount
          });

          socket.emit('measurement-search-complete', {
            status: 'completed',
            message: '실측스케쥴 그룹 검색이 완료되었습니다!',
            results: {
              searchInfo: {
                groupName: '실측스케쥴',
                groupId: '229923',
                startDate,
                maxMessages: maxMessages || 100,
                searchTime: new Date().toISOString()
              },
              summary: {
                totalMessages: result.summary.totalMessages,
                filteredMessages: result.summary.filteredMessages,
                totalMeasurements: result.summary.measurementCount,
                sourceType: 'group' // 그룹에서 가져온 것임을 표시
              },
              measurements: result.measurements,
              statistics: result.statistics
            }
          });

        } catch (error) {
          console.error('실측스케쥴 그룹 검색 오류:', error);
          socket.emit('search-error', { 
            status: 'error', 
            message: error.message 
          });
        }
      });

      // 시공일 정보 검색 (Socket.IO) - 발주 관련 그룹들 사용
      socket.on('search-constructions', async (data) => {
        console.log('🎯 발주 관련 그룹에서 시공일 정보 검색 시작:', data);
        
        try {
          const { startDate, maxMessages, groupType } = data;
          
          socket.emit('search-progress', { 
            status: 'starting', 
            message: '발주 관련 그룹에서 시공일 정보를 검색합니다...' 
          });

          let result;
          
          if (groupType === 'sales-order') {
            // 영업팀_발주정보 그룹만 검색
            result = await this.constructionGroupSearcher.searchConstructionInSalesOrderGroup(
              startDate, 
              maxMessages || 500
            );
          } else if (groupType === 'order-room') {
            // 발주방 그룹만 검색
            result = await this.constructionGroupSearcher.searchConstructionInOrderRoomGroup(
              startDate, 
              maxMessages || 500
            );
          } else {
            // 모든 발주 관련 그룹 검색
            result = await this.constructionGroupSearcher.searchConstructionInAllGroups(
              startDate, 
              maxMessages || 500
            );
          }
          
          socket.emit('search-progress', { 
            status: 'group-loaded', 
            message: `시공일 정보 검색 완료: ${result.summary.totalConstructions || result.constructions.length}개 발견`,
            constructionCount: result.summary.totalConstructions || result.constructions.length
          });

          socket.emit('construction-search-complete', {
            status: 'completed',
            message: '시공일 정보 검색이 완료되었습니다!',
            results: {
              searchInfo: result.searchInfo || {
                groupName: result.groupName,
                groupId: result.groupId,
                startDate,
                maxMessages: maxMessages || 500,
                searchTime: new Date().toISOString()
              },
              summary: result.summary || {
                totalMessages: result.summary.totalMessages,
                filteredMessages: result.summary.filteredMessages,
                totalConstructions: result.constructions.length,
                sourceType: 'group'
              },
              constructions: result.constructions,
              groupResults: result.groupResults,
              statistics: result.statistics
            }
          });

        } catch (error) {
          console.error('시공일 정보 검색 오류:', error);
          socket.emit('search-error', { 
            status: 'error', 
            message: error.message 
          });
        }
      });

      socket.on('disconnect', () => {
        console.log('🔌 클라이언트 연결 해제됨:', socket.id);
      });
    });
  }

  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  start() {
    this.server.listen(this.port, () => {
      console.log('🚀 채널톡 실측/시공일 검색 서버가 시작되었습니다!');
      console.log(`📍 URL: http://localhost:${this.port}`);
      console.log('🔍 웹 브라우저에서 위 URL로 접속하세요.');
      console.log('');
      console.log('💡 사용 가능한 기능:');
      console.log('  - 실측스케쥴 검색');
      console.log('  - 시공일 검색');
      console.log('  - 날짜별 필터링');
      console.log('  - 실시간 검색 진행 상황');
      console.log('');
    });
  }
}

// 서버 실행
if (require.main === module) {
  const server = new ChannelMessageSearchServer();
  server.start();
}

module.exports = ChannelMessageSearchServer;
