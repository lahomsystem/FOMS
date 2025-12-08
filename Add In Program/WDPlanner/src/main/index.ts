import { app, BrowserWindow } from 'electron';
import path from 'path';
import os from 'os';

let mainWindow: BrowserWindow | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // 개발 모드에서는 Vite 개발 서버 사용
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  
  if (isDev) {
    // 네트워크 IP 주소 자동 감지
    const networkInterfaces = os.networkInterfaces();
    let localIP = 'localhost';
    
    // IPv4 주소 찾기 (로컬호스트 제외)
    for (const interfaceName in networkInterfaces) {
      const interfaces = networkInterfaces[interfaceName];
      if (interfaces) {
        for (const iface of interfaces) {
          // IPv4 체크 (Node.js 버전에 따라 family가 'IPv4' 또는 숫자 4)
          // 타입 안전성을 위해 문자열 변환 후 비교
          const family = String(iface.family);
          const isIPv4 = family === 'IPv4' || family === '4';
          if (isIPv4 && !iface.internal) {
            localIP = iface.address;
            break;
          }
        }
        if (localIP !== 'localhost') break;
      }
    }
    
    const devServerURL = `http://${localIP}:5173`;
    console.log(`개발 서버 주소: ${devServerURL}`);
    console.log(`로컬 접속: http://localhost:5173`);
    console.log(`네트워크 접속: ${devServerURL}`);
    
    mainWindow.loadURL(devServerURL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../../dist/index.html'));
  }
  
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

