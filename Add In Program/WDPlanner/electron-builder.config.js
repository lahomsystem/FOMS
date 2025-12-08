export default {
  appId: 'com.wdplanner.app',
  productName: 'WD Planner',
  directories: {
    output: 'release',
  },
  files: [
    'dist/**/*',
    'dist-electron/**/*',
    'package.json',
  ],
  win: {
    target: 'nsis',
  },
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
  },
};




