const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  globalShortcut,
  ipcMain,
  nativeImage,
  screen
} = require('electron');
const fs = require('fs');
const path = require('path');

let viewerWindow = null;
let controlWindow = null;
let tray = null;
let currentServer = process.env.LIVETALKING_SERVER || 'http://127.0.0.1:8050';
let clickThrough = process.env.LIVETALKING_CLICK_THROUGH !== '0';
let sourceAspectRatio = 720 / 1280;
let currentScale = 1;
let movingControlFromViewer = false;
let movingViewerFromControl = false;

const playAudio = process.env.LIVETALKING_PLAY_AUDIO === '1';
const autoSession = process.env.LIVETALKING_AUTO_SESSION !== '0';
const closeSessionOnExit = process.env.LIVETALKING_CLOSE_SESSION_ON_EXIT !== '0';
const videoMaxWidth = envInt('LIVETALKING_VIDEO_MAX_WIDTH', 0);
const videoMaxHeight = envInt('LIVETALKING_VIDEO_MAX_HEIGHT', 0);
const videoFps = envFloat('LIVETALKING_VIDEO_FPS', 0);
const videoFormat = envFormat('LIVETALKING_VIDEO_FORMAT', 'raw');
const videoQuality = envInt('LIVETALKING_VIDEO_QUALITY', 80);
const outputMode = envOutputMode('LIVETALKING_OUTPUT', 'webrtc-packed');
const logFile = path.join(__dirname, 'overlay-debug.log');

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
app.commandLine.appendSwitch('enable-unsafe-swiftshader');

function debugLog(scope, message, data) {
  const record = {
    ts: new Date().toISOString(),
    pid: process.pid,
    scope,
    message
  };
  if (data !== undefined) record.data = data;
  try {
    fs.appendFileSync(logFile, `${JSON.stringify(record)}\n`);
  } catch (_) {
    // Logging must never break the overlay.
  }
}

function windowInfo(win) {
  if (!win || win.isDestroyed()) return null;
  return {
    id: win.id,
    bounds: win.getBounds(),
    visible: win.isVisible(),
    focused: win.isFocused(),
    minimized: win.isMinimized()
  };
}

function attachWindowLogging(name, win) {
  win.on('ready-to-show', () => debugLog(name, 'ready-to-show', windowInfo(win)));
  win.on('show', () => debugLog(name, 'show', windowInfo(win)));
  win.on('hide', () => debugLog(name, 'hide', windowInfo(win)));
  win.on('focus', () => debugLog(name, 'focus', windowInfo(win)));
  win.on('blur', () => debugLog(name, 'blur', windowInfo(win)));
  win.on('move', () => debugLog(name, 'move', windowInfo(win)));
  win.on('resize', () => debugLog(name, 'resize', windowInfo(win)));
  win.on('closed', () => debugLog(name, 'closed'));
  win.webContents.on('did-finish-load', () => debugLog(name, 'did-finish-load', windowInfo(win)));
  win.webContents.on('render-process-gone', (_event, details) => debugLog(name, 'render-process-gone', details));
  win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    debugLog(name, 'console-message', { level, message, line, sourceId });
  });
}

function envInt(name, fallback) {
  const value = Number.parseInt(process.env[name] || '', 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function envFloat(name, fallback) {
  const value = Number.parseFloat(process.env[name] || '');
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function envFormat(name, fallback) {
  const value = (process.env[name] || '').trim().toLowerCase();
  return ['raw', 'jpeg', 'jpg', 'png', 'webp'].includes(value) ? value : fallback;
}

function envOutputMode(name, fallback) {
  const value = (process.env[name] || '').trim().toLowerCase();
  if (['webrtc-packed', 'packed-webrtc', 'packed', 'webrtc'].includes(value)) return 'webrtc-packed';
  if (['ws', 'websocket', 'raw'].includes(value)) return 'ws';
  return fallback;
}

function createViewerWindow() {
  const initialWidth = envInt('LIVETALKING_WIDTH', 360);
  const initialHeight = envInt('LIVETALKING_HEIGHT', 640);
  currentScale = envFloat('LIVETALKING_SCALE', 1);
  debugLog('main', 'create viewer window', {
    initialWidth,
    initialHeight,
    currentServer,
    clickThrough,
    playAudio,
    autoSession,
    closeSessionOnExit,
    videoMaxWidth,
    videoMaxHeight,
    videoFps,
    videoFormat,
    videoQuality,
    outputMode
  });

  viewerWindow = new BrowserWindow({
    width: initialWidth,
    height: initialHeight,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: true,
    hasShadow: false,
    focusable: true,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: `${__dirname}/preload.js`,
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  attachWindowLogging('viewer', viewerWindow);
  viewerWindow.setAlwaysOnTop(true, 'screen-saver');
  viewerWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  viewerWindow.setAspectRatio(initialWidth / initialHeight);

  const x = Number.parseInt(process.env.LIVETALKING_X || '', 10);
  const y = Number.parseInt(process.env.LIVETALKING_Y || '', 10);
  if (Number.isFinite(x) && Number.isFinite(y)) {
    viewerWindow.setPosition(x, y);
  }

  const params = new URLSearchParams({
    server: currentServer,
    clickThrough: clickThrough ? '1' : '0',
    playAudio: playAudio ? '1' : '0',
    autoSession: autoSession ? '1' : '0',
    closeSessionOnExit: closeSessionOnExit ? '1' : '0',
    scale: String(envFloat('LIVETALKING_SCALE', 1)),
    renderer: process.env.LIVETALKING_RENDERER || 'webgl',
    videoMaxWidth: String(videoMaxWidth),
    videoMaxHeight: String(videoMaxHeight),
    videoFps: String(videoFps),
    videoFormat,
    videoQuality: String(videoQuality),
    output: outputMode
  });
  viewerWindow.loadFile('viewer.html', { search: `?${params.toString()}` });

  viewerWindow.webContents.once('did-finish-load', () => {
    debugLog('viewer', 'initial renderer loaded');
    applyInteractionMode();
    keepControlOnTop();
  });

  viewerWindow.on('closed', () => {
    viewerWindow = null;
  });

  viewerWindow.on('move', () => {
    if (!movingViewerFromControl) positionControlWindow();
    keepControlOnTop();
  });

  viewerWindow.on('resize', () => {
    positionControlWindow();
    keepControlOnTop();
  });
}

function createControlWindow() {
  debugLog('main', 'create control window');
  controlWindow = new BrowserWindow({
    width: envInt('LIVETALKING_CONTROL_WIDTH', 340),
    height: envInt('LIVETALKING_CONTROL_HEIGHT', 44),
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    focusable: true,
    acceptFirstMouse: true,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: `${__dirname}/preload.js`,
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  attachWindowLogging('control', controlWindow);
  controlWindow.setAlwaysOnTop(true, 'screen-saver');
  controlWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  controlWindow.setIgnoreMouseEvents(false);
  controlWindow.loadFile('controlbar.html');

  controlWindow.webContents.once('did-finish-load', () => {
    controlWindow.webContents.send('viewer:interaction-mode', {
      clickThrough,
      controlsVisible: true,
      playAudio
    });
    broadcastZoomState();
    positionControlWindow();
    keepControlOnTop();
  });

  controlWindow.on('move', () => {
    if (movingControlFromViewer || !viewerWindow || viewerWindow.isDestroyed()) return;
    const controlBounds = controlWindow.getBounds();
    const viewerBounds = viewerWindow.getBounds();
    const nextX = controlBounds.x + controlBounds.width - viewerBounds.width;
    const nextY = controlBounds.y + controlBounds.height + 8;
    debugLog('control', 'manual move adjusts viewer', {
      controlBounds,
      viewerBounds,
      nextViewerBounds: { x: nextX, y: nextY, width: viewerBounds.width, height: viewerBounds.height }
    });
    movingViewerFromControl = true;
    viewerWindow.setPosition(nextX, nextY);
    setTimeout(() => {
      movingViewerFromControl = false;
    }, 80);
    keepControlOnTop();
  });

  controlWindow.on('closed', () => {
    controlWindow = null;
  });
}

function positionControlWindow() {
  if (!viewerWindow || viewerWindow.isDestroyed()) return;
  if (!controlWindow || controlWindow.isDestroyed()) return;
  const viewerBounds = viewerWindow.getBounds();
  const controlBounds = controlWindow.getBounds();
  const display = screen.getDisplayMatching(viewerBounds);
  const area = display.workArea;
  let x = viewerBounds.x + viewerBounds.width - controlBounds.width;
  let y = viewerBounds.y - controlBounds.height - 8;

  if (x < area.x) x = area.x;
  if (x + controlBounds.width > area.x + area.width) {
    x = area.x + area.width - controlBounds.width;
  }
  if (y < area.y) {
    y = viewerBounds.y + viewerBounds.height + 8;
  }
  if (y + controlBounds.height > area.y + area.height) {
    y = Math.max(area.y, viewerBounds.y + 8);
  }

  debugLog('control', 'position relative to viewer', {
    viewerBounds,
    controlBounds,
    workArea: area,
    nextControlPosition: { x, y }
  });
  movingControlFromViewer = true;
  controlWindow.setPosition(Math.round(x), Math.round(y));
  setTimeout(() => {
    movingControlFromViewer = false;
  }, 80);
  keepControlOnTop();
}

function keepControlOnTop() {
  if (!controlWindow || controlWindow.isDestroyed()) return;
  controlWindow.setAlwaysOnTop(true, 'screen-saver');
  try {
    controlWindow.moveTop();
  } catch (error) {
    debugLog('control', 'moveTop failed', { error: String(error) });
  }
}

function applyInteractionMode() {
  if (!viewerWindow || viewerWindow.isDestroyed()) return;
  viewerWindow.setIgnoreMouseEvents(clickThrough, { forward: true });
  const state = {
    clickThrough,
    controlsVisible: !clickThrough,
    playAudio
  };
  viewerWindow.webContents.send('viewer:interaction-mode', state);
  if (controlWindow && !controlWindow.isDestroyed()) {
    controlWindow.webContents.send('viewer:interaction-mode', {
      ...state,
      controlsVisible: true
    });
    controlWindow.setIgnoreMouseEvents(false);
    keepControlOnTop();
  }
  debugLog('main', 'apply interaction mode', {
    state,
    viewer: windowInfo(viewerWindow),
    control: windowInfo(controlWindow)
  });
  rebuildTrayMenu();
}

function toggleManageMode() {
  clickThrough = !clickThrough;
  debugLog('main', 'toggle interaction', { clickThrough });
  applyInteractionMode();
}

function rebuildTrayMenu() {
  if (!tray) return;
  tray.setToolTip(clickThrough ? 'LiveTalking viewer: display mode' : 'LiveTalking viewer: manage mode');
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: clickThrough ? 'Enter manage mode' : 'Enter display mode',
      click: toggleManageMode
    },
    {
      label: 'Reconnect stream',
      click: () => {
        if (viewerWindow && !viewerWindow.isDestroyed()) {
          viewerWindow.webContents.send('viewer:reconnect');
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => app.quit()
    }
  ]));
}

function createTray() {
  tray = new Tray(nativeImage.createEmpty());
  debugLog('main', 'create tray');
  rebuildTrayMenu();
}

function registerShortcuts() {
  globalShortcut.register('CommandOrControl+Alt+M', toggleManageMode);
  globalShortcut.register('CommandOrControl+Alt+R', () => {
    if (viewerWindow && !viewerWindow.isDestroyed()) {
      viewerWindow.webContents.send('viewer:reconnect');
    }
  });
  globalShortcut.register('CommandOrControl+Alt+=', () => {
    if (viewerWindow && !viewerWindow.isDestroyed()) {
      viewerWindow.webContents.send('viewer:zoom', 'in');
    }
  });
  globalShortcut.register('CommandOrControl+Alt+-', () => {
    if (viewerWindow && !viewerWindow.isDestroyed()) {
      viewerWindow.webContents.send('viewer:zoom', 'out');
    }
  });
  globalShortcut.register('CommandOrControl+Alt+0', () => {
    if (viewerWindow && !viewerWindow.isDestroyed()) {
      viewerWindow.webContents.send('viewer:zoom', 'reset');
    }
  });
  globalShortcut.register('CommandOrControl+Alt+Q', () => app.quit());
}

function fitContentSize(sourceWidth, sourceHeight, requestedScaleOverride) {
  if (!viewerWindow || viewerWindow.isDestroyed()) return;
  if (!sourceWidth || !sourceHeight) return;

  sourceAspectRatio = sourceWidth / sourceHeight;
  viewerWindow.setAspectRatio(sourceAspectRatio);

  const display = screen.getDisplayNearestPoint(viewerWindow.getBounds());
  const maxWidth = Math.max(1, Math.floor(display.workAreaSize.width * 0.9));
  const maxHeight = Math.max(1, Math.floor(display.workAreaSize.height * 0.9));
  const requestedScale = Number.isFinite(requestedScaleOverride) && requestedScaleOverride > 0
    ? requestedScaleOverride
    : envFloat('LIVETALKING_SCALE', 1);
  const scale = Math.min(requestedScale, maxWidth / sourceWidth, maxHeight / sourceHeight);
  currentScale = scale;
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));

  debugLog('viewer', 'fit content size', {
    sourceWidth,
    sourceHeight,
    requestedScale,
    effectiveScale: scale,
    contentSize: { width, height },
    maxWidth,
    maxHeight
  });
  viewerWindow.setContentSize(width, height);
  positionControlWindow();
  keepControlOnTop();
  broadcastZoomState(scale);
}

function broadcastZoomState(effectiveScale = currentScale) {
  if (controlWindow && !controlWindow.isDestroyed()) {
    controlWindow.webContents.send('viewer:zoom-state', {
      scale: effectiveScale
    });
  }
}

app.whenReady().then(() => {
  debugLog('main', 'app ready', {
    version: app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    platform: process.platform,
    argv: process.argv,
    env: {
      LIVETALKING_SERVER: process.env.LIVETALKING_SERVER,
      LIVETALKING_CLICK_THROUGH: process.env.LIVETALKING_CLICK_THROUGH,
      LIVETALKING_PLAY_AUDIO: process.env.LIVETALKING_PLAY_AUDIO,
      LIVETALKING_SCALE: process.env.LIVETALKING_SCALE,
      LIVETALKING_RENDERER: process.env.LIVETALKING_RENDERER,
      LIVETALKING_OUTPUT: process.env.LIVETALKING_OUTPUT,
      LIVETALKING_VIDEO_FORMAT: process.env.LIVETALKING_VIDEO_FORMAT,
      LIVETALKING_VIDEO_QUALITY: process.env.LIVETALKING_VIDEO_QUALITY
    }
  });
  createViewerWindow();
  createControlWindow();
  createTray();
  registerShortcuts();
});

app.on('window-all-closed', () => {
  debugLog('main', 'window-all-closed');
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', () => {
  debugLog('main', 'will-quit');
  globalShortcut.unregisterAll();
});

ipcMain.on('overlay:set-ignore-mouse', (_event, ignore) => {
  debugLog('ipc', 'overlay:set-ignore-mouse', { ignore });
  clickThrough = Boolean(ignore);
  applyInteractionMode();
});

ipcMain.on('overlay:toggle-interaction', () => {
  debugLog('ipc', 'overlay:toggle-interaction');
  toggleManageMode();
});

ipcMain.on('overlay:close', () => {
  debugLog('ipc', 'overlay:close');
  app.quit();
});

ipcMain.on('overlay:minimize', () => {
  debugLog('ipc', 'overlay:minimize');
  if (viewerWindow && !viewerWindow.isDestroyed()) viewerWindow.minimize();
  if (controlWindow && !controlWindow.isDestroyed()) controlWindow.minimize();
});

ipcMain.on('viewer:resize', (_event, { width, height, scale }) => {
  debugLog('ipc', 'viewer:resize', { width, height, scale });
  const w = Math.max(1, Math.round(width || 1));
  const h = Math.max(1, Math.round(height || 1));
  const requestedScale = Number.parseFloat(scale);
  fitContentSize(w, h, requestedScale);
});

ipcMain.on('viewer:zoom-state', (_event, { scale }) => {
  debugLog('ipc', 'viewer:zoom-state', { scale });
  const zoom = Number.parseFloat(scale);
  if (Number.isFinite(zoom) && zoom > 0) {
    currentScale = zoom;
    broadcastZoomState(zoom);
  }
});

ipcMain.on('viewer:zoom-request', (_event, action) => {
  debugLog('ipc', 'viewer:zoom-request', { action });
  if (viewerWindow && !viewerWindow.isDestroyed()) {
    viewerWindow.webContents.send('viewer:zoom', action);
  }
  keepControlOnTop();
});

ipcMain.on('viewer:set-server', (_event, server) => {
  debugLog('ipc', 'viewer:set-server', { server });
  if (!server || typeof server !== 'string') return;
  currentServer = server;
  if (viewerWindow && !viewerWindow.isDestroyed()) {
    viewerWindow.webContents.send('viewer:server-updated', currentServer);
  }
});

ipcMain.on('viewer:request-reconnect', () => {
  debugLog('ipc', 'viewer:request-reconnect');
  if (viewerWindow && !viewerWindow.isDestroyed()) {
    viewerWindow.webContents.send('viewer:reconnect');
  }
});

ipcMain.on('overlay:log', (_event, payload = {}) => {
  const scope = typeof payload.scope === 'string' ? payload.scope : 'renderer';
  const message = typeof payload.message === 'string' ? payload.message : 'log';
  debugLog(scope, message, payload.data);
});
