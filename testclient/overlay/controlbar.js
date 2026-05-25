const zoomReset = document.getElementById('zoomReset');
const toggleInteractionButton = document.getElementById('toggleInteraction');

function log(message, data) {
  window.overlayApi?.log?.('controlbar', message, data);
}

function setZoomLabel(scale) {
  const value = Number.isFinite(scale) && scale > 0 ? scale : 1;
  zoomReset.textContent = `${Math.round(value * 100)}%`;
  log('set zoom label', { scale: value });
}

function setInteractionLabel(clickThrough) {
  toggleInteractionButton.textContent = clickThrough ? '穿透' : '管理';
  log('set interaction label', { clickThrough });
}

function bindButton(id, action) {
  const button = document.getElementById(id);
  button.addEventListener('pointerdown', (event) => {
    log('button pointerdown', {
      id,
      button: event.button,
      buttons: event.buttons,
      x: event.clientX,
      y: event.clientY
    });
  });
  button.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    log('button click', {
      id,
      x: event.clientX,
      y: event.clientY
    });
    action();
  });
}

bindButton('toggleInteraction', () => window.overlayApi?.toggleInteraction?.());
bindButton('zoomOut', () => window.overlayApi?.zoom?.('out'));
bindButton('zoomReset', () => window.overlayApi?.zoom?.('reset'));
bindButton('zoomIn', () => window.overlayApi?.zoom?.('in'));
bindButton('reconnect', () => window.overlayApi?.reconnect?.());
bindButton('minimize', () => window.overlayApi?.minimize?.());
bindButton('close', () => window.overlayApi?.close?.());

document.getElementById('drag').addEventListener('pointerdown', (event) => {
  log('drag pointerdown', {
    button: event.button,
    buttons: event.buttons,
    x: event.clientX,
    y: event.clientY
  });
});

if (window.overlayApi?.onInteractionMode) {
  window.overlayApi.onInteractionMode((state = {}) => {
    log('receive interaction mode', state);
    setInteractionLabel(Boolean(state.clickThrough));
  });
}

if (window.overlayApi?.onZoomState) {
  window.overlayApi.onZoomState((state = {}) => {
    log('receive zoom state', state);
    setZoomLabel(Number(state.scale));
  });
}

log('controlbar loaded', {
  userAgent: navigator.userAgent,
  devicePixelRatio: window.devicePixelRatio
});
setInteractionLabel(true);
setZoomLabel(1);
