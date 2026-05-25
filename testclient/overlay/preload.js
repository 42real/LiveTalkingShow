const { contextBridge, ipcRenderer } = require('electron');

function send(channel, payload) {
  ipcRenderer.send(channel, payload);
}

function rendererLog(scope, message, data) {
  ipcRenderer.send('overlay:log', { scope, message, data });
}

contextBridge.exposeInMainWorld('overlayApi', {
  log: rendererLog,
  setIgnoreMouse: (ignore) => {
    rendererLog('preload', 'send overlay:set-ignore-mouse', { ignore });
    send('overlay:set-ignore-mouse', ignore);
  },
  toggleInteraction: () => {
    rendererLog('preload', 'send overlay:toggle-interaction');
    send('overlay:toggle-interaction');
  },
  close: () => {
    rendererLog('preload', 'send overlay:close');
    send('overlay:close');
  },
  minimize: () => {
    rendererLog('preload', 'send overlay:minimize');
    send('overlay:minimize');
  },
  resize: (width, height, scale) => {
    rendererLog('preload', 'send viewer:resize', { width, height, scale });
    send('viewer:resize', { width, height, scale });
  },
  zoom: (action) => {
    rendererLog('preload', 'send viewer:zoom-request', { action });
    send('viewer:zoom-request', action);
  },
  setZoomState: (scale) => {
    rendererLog('preload', 'send viewer:zoom-state', { scale });
    send('viewer:zoom-state', { scale });
  },
  setServer: (server) => {
    rendererLog('preload', 'send viewer:set-server', { server });
    send('viewer:set-server', server);
  },
  reconnect: () => {
    rendererLog('preload', 'send viewer:request-reconnect');
    send('viewer:request-reconnect');
  },
  onServerChanged: (callback) => {
    ipcRenderer.removeAllListeners('viewer:server-updated');
    ipcRenderer.on('viewer:server-updated', (_event, server) => {
      rendererLog('preload', 'receive viewer:server-updated', { server });
      callback(server);
    });
  },
  onInteractionMode: (callback) => {
    ipcRenderer.removeAllListeners('viewer:interaction-mode');
    ipcRenderer.on('viewer:interaction-mode', (_event, state) => {
      rendererLog('preload', 'receive viewer:interaction-mode', state);
      callback(state);
    });
  },
  onReconnect: (callback) => {
    ipcRenderer.removeAllListeners('viewer:reconnect');
    ipcRenderer.on('viewer:reconnect', () => {
      rendererLog('preload', 'receive viewer:reconnect');
      callback();
    });
  },
  onZoom: (callback) => {
    ipcRenderer.removeAllListeners('viewer:zoom');
    ipcRenderer.on('viewer:zoom', (_event, action) => {
      rendererLog('preload', 'receive viewer:zoom', { action });
      callback(action);
    });
  },
  onZoomState: (callback) => {
    ipcRenderer.removeAllListeners('viewer:zoom-state');
    ipcRenderer.on('viewer:zoom-state', (_event, state) => {
      rendererLog('preload', 'receive viewer:zoom-state', state);
      callback(state);
    });
  }
});
