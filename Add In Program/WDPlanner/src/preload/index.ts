import { contextBridge } from 'electron';

// IPC 통신을 위한 API 노출 (필요시 확장)
contextBridge.exposeInMainWorld('electronAPI', {
  // 향후 IPC 통신 함수들을 여기에 추가
});




