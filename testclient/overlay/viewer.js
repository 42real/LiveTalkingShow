const avatar = document.getElementById('avatar');
const urlParams = new URLSearchParams(window.location.search);
let frameRenderer = createFrameRenderer(avatar);

let serverBase = urlParams.get('server') || 'http://127.0.0.1:8050';
let clickThrough = urlParams.get('clickThrough') === '1';
let playAudio = urlParams.get('playAudio') === '1';
let autoSession = urlParams.get('autoSession') !== '0';
let closeSessionOnExit = urlParams.get('closeSessionOnExit') === '1';
let zoomScale = clampScale(readPositiveFloatParam('scale', 1));

let socket = null;
let audioSocket = null;
let sessionId = null;
let sessionPromise = null;
let audioContext = null;
let audioNode = null;
let audioInitPromise = null;
let reconnectVideoTimer = null;
let reconnectAudioTimer = null;
let closing = false;
let pendingFrame = null;
let drawing = false;
let contextReloadTimer = null;
let frameStats = {
  received: 0,
  drawn: 0,
  dropped: 0,
  lastFpsAt: performance.now(),
  lastDrawn: 0
};
let lastWindowRequest = {
  width: 0,
  height: 0,
  scale: 0
};
let lastSourceFrame = {
  width: 0,
  height: 0
};
let lastFrameSignature = '';
let firstFrameLogged = false;

function log(message, data) {
  window.overlayApi?.log?.('viewer', message, data);
}

function readPositiveFloatParam(name, fallback) {
  const value = Number.parseFloat(urlParams.get(name) || '');
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function clampScale(value) {
  if (!Number.isFinite(value)) return 1;
  return Math.min(3, Math.max(0.25, value));
}

function wsUrl(server, path) {
  const url = new URL(server);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = path;
  return url.toString();
}

function connect() {
  if (reconnectVideoTimer) clearTimeout(reconnectVideoTimer);
  if (socket) {
    socket.onclose = null;
    socket.close();
  }

  log('connect video websocket', { serverBase, url: wsUrl(serverBase, '/alpha/ws') });
  socket = new WebSocket(wsUrl(serverBase, '/alpha/ws'));
  socket.binaryType = 'arraybuffer';
  socket.onopen = () => {
    log('video websocket open');
    ensureAlphaSession();
  };
  socket.onclose = (event) => {
    log('video websocket close', { code: event.code, reason: event.reason, wasClean: event.wasClean });
    if (closing) return;
    if (autoSession) {
      sessionId = null;
      sessionPromise = null;
    }
    reconnectVideoTimer = setTimeout(connect, 2000);
  };
  socket.onerror = (event) => {
    log('video websocket error', { type: event.type });
  };
  socket.onmessage = (event) => {
    frameStats.received++;
    if (pendingFrame) frameStats.dropped++;
    pendingFrame = event.data;
    scheduleDraw();
  };
}

async function ensureAlphaSession() {
  if (!autoSession) return null;
  if (sessionPromise) return sessionPromise;

  log('request alpha session', { serverBase });
  sessionPromise = fetch(`${serverBase}/alpha/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reuse: true })
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok || payload.code !== 0) {
        throw new Error(payload.msg || 'alpha session create failed');
      }
      sessionId = String(payload.data.sessionid);
      log('alpha session ready', { sessionId });
      return sessionId;
    })
    .catch((error) => {
      console.error(error);
      log('alpha session failed', { error: String(error) });
      sessionPromise = null;
      setTimeout(() => {
        if (!closing) ensureAlphaSession();
      }, 2000);
      return null;
    });

  return sessionPromise;
}

function closeAlphaSession() {
  if (!sessionId || !closeSessionOnExit) return;
  const body = JSON.stringify({ sessionid: sessionId });
  log('close alpha session', { sessionId });
  try {
    navigator.sendBeacon(
      `${serverBase}/alpha/close`,
      new Blob([body], { type: 'application/json' })
    );
  } catch (_) {
    fetch(`${serverBase}/alpha/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true
    }).catch(() => {});
  }
}

function connectAudio() {
  if (!playAudio) return;
  if (reconnectAudioTimer) clearTimeout(reconnectAudioTimer);
  if (audioSocket) {
    audioSocket.onclose = null;
    audioSocket.close();
  }

  log('connect audio websocket', { serverBase, url: wsUrl(serverBase, '/alpha/audio') });
  audioSocket = new WebSocket(wsUrl(serverBase, '/alpha/audio'));
  audioSocket.binaryType = 'arraybuffer';
  audioSocket.onopen = () => log('audio websocket open');
  audioSocket.onmessage = (event) => pushPcm(event.data);
  audioSocket.onerror = (event) => log('audio websocket error', { type: event.type });
  audioSocket.onclose = (event) => {
    log('audio websocket close', { code: event.code, reason: event.reason, wasClean: event.wasClean });
    if (closing) return;
    reconnectAudioTimer = setTimeout(connectAudio, 2000);
  };
}

async function getAudioNode() {
  if (!audioInitPromise) {
    audioInitPromise = initAudioNode();
  }
  const node = await audioInitPromise;
  if (audioContext.state === 'suspended') await audioContext.resume();
  return node;
}

async function initAudioNode() {
  if (!audioContext) {
    audioContext = new AudioContext({ sampleRate: 16000, latencyHint: 'interactive' });
    log('create audio context', { sampleRate: audioContext.sampleRate, state: audioContext.state });
  }
  await audioContext.audioWorklet.addModule('audio-worklet.js');
  audioNode = new AudioWorkletNode(audioContext, 'pcm-ring-buffer', {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1]
  });
  audioNode.connect(audioContext.destination);
  return audioNode;
}

async function pushPcm(arrayBuffer) {
  const node = await getAudioNode();
  const samples = resamplePcm16(new Int16Array(arrayBuffer), 16000, audioContext.sampleRate);
  node.port.postMessage({ type: 'samples', buffer: samples.buffer }, [samples.buffer]);
}

function resamplePcm16(pcm, sourceRate, targetRate) {
  if (pcm.length === 0) return new Float32Array(0);
  if (sourceRate === targetRate) {
    const out = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) out[i] = pcm[i] / 32768;
    return out;
  }

  const ratio = targetRate / sourceRate;
  const outLength = Math.max(1, Math.round(pcm.length * ratio));
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const srcPos = i / ratio;
    const idx = Math.floor(srcPos);
    const frac = srcPos - idx;
    const a = pcm[Math.min(idx, pcm.length - 1)] / 32768;
    const b = pcm[Math.min(idx + 1, pcm.length - 1)] / 32768;
    out[i] = a + (b - a) * frac;
  }
  return out;
}

function resetAudio() {
  if (audioNode) audioNode.port.postMessage({ type: 'reset' });
}

function stopAudioSocket() {
  log('stop audio socket');
  if (reconnectAudioTimer) clearTimeout(reconnectAudioTimer);
  reconnectAudioTimer = null;
  if (audioSocket) {
    audioSocket.onclose = null;
    audioSocket.close();
    audioSocket = null;
  }
  resetAudio();
}

function scheduleDraw() {
  if (drawing) return;
  drawing = true;
  requestAnimationFrame(drawLatestFrame);
}

function drawLatestFrame() {
  drawing = false;
  const packet = pendingFrame;
  pendingFrame = null;
  if (!packet) return;

  const parsed = parseFrame(packet);
  if (!parsed) {
    log('drop invalid frame', { byteLength: packet.byteLength });
    return;
  }

  const signature = `${parsed.width}x${parsed.height}`;
  if (!firstFrameLogged || signature !== lastFrameSignature) {
    firstFrameLogged = true;
    lastFrameSignature = signature;
    log('frame size', {
      width: parsed.width,
      height: parsed.height,
      byteLength: packet.byteLength
    });
  }

  lastSourceFrame = { width: parsed.width, height: parsed.height };
  requestWindowResize(parsed.width, parsed.height);

  try {
    frameRenderer.draw(parsed);
  } catch (error) {
    console.error(error);
    scheduleContextReload();
    return;
  }
  frameStats.drawn++;
  updateFpsStatus();

  if (pendingFrame) scheduleDraw();
}

function requestWindowResize(width, height) {
  if (!window.overlayApi?.resize) return;
  if (
    lastWindowRequest.width === width &&
    lastWindowRequest.height === height &&
    Math.abs(lastWindowRequest.scale - zoomScale) < 0.001
  ) {
    return;
  }

  lastWindowRequest = { width, height, scale: zoomScale };
  log('request window resize', lastWindowRequest);
  window.overlayApi.resize(width, height, zoomScale);
}

function setZoomScale(nextScale) {
  const clamped = clampScale(nextScale);
  if (Math.abs(clamped - zoomScale) < 0.001) return;
  log('set zoom scale', { previous: zoomScale, next: clamped });
  zoomScale = clamped;
  window.overlayApi?.setZoomState?.(zoomScale);
  if (lastSourceFrame.width > 0 && lastSourceFrame.height > 0) {
    requestWindowResize(lastSourceFrame.width, lastSourceFrame.height);
  }
}

function adjustZoom(action) {
  log('adjust zoom', { action, zoomScale });
  if (action === 'in') {
    setZoomScale(zoomScale + 0.1);
  } else if (action === 'out') {
    setZoomScale(zoomScale - 0.1);
  } else if (action === 'reset') {
    setZoomScale(1);
  }
}

function parseFrame(packet) {
  if (packet.byteLength < 24) {
    log('invalid frame header length', { byteLength: packet.byteLength });
    return null;
  }
  const magicBytes = new Uint8Array(packet, 0, 4);
  const magic = String.fromCharCode(...magicBytes);
  if (magic !== 'LTAF') {
    log('invalid frame magic', { magic });
    return null;
  }

  const view = new DataView(packet);
  const version = view.getUint8(4);
  const format = view.getUint8(5);
  const width = view.getUint32(8, true);
  const height = view.getUint32(12, true);
  if (version !== 1 || format !== 1 || width <= 0 || height <= 0) {
    log('invalid frame metadata', { version, format, width, height });
    return null;
  }

  const expected = 24 + width * height * 4;
  if (packet.byteLength !== expected) {
    log('invalid frame payload length', { expected, actual: packet.byteLength, width, height });
    return null;
  }
  return {
    width,
    height,
    rgba: new Uint8Array(packet, 24)
  };
}

function createFrameRenderer(canvas) {
  if (urlParams.get('renderer') === '2d') return createCanvas2dRenderer(canvas);

  const gl = canvas.getContext('webgl', {
    alpha: true,
    antialias: false,
    depth: false,
    desynchronized: true,
    premultipliedAlpha: false,
    preserveDrawingBuffer: false,
    stencil: false
  });

  if (!gl) return createCanvas2dRenderer(canvas);

  const program = createProgram(
    gl,
    `
      attribute vec2 aPosition;
      attribute vec2 aTexCoord;
      varying vec2 vTexCoord;
      void main() {
        gl_Position = vec4(aPosition, 0.0, 1.0);
        vTexCoord = aTexCoord;
      }
    `,
    `
      precision mediump float;
      uniform sampler2D uTexture;
      varying vec2 vTexCoord;
      void main() {
        gl_FragColor = texture2D(uTexture, vTexCoord);
      }
    `
  );

  const vertices = new Float32Array([
    -1, -1, 0, 1,
     1, -1, 1, 1,
    -1,  1, 0, 0,
     1,  1, 1, 0
  ]);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

  const stride = 4 * Float32Array.BYTES_PER_ELEMENT;
  const position = gl.getAttribLocation(program, 'aPosition');
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, stride, 0);

  const texCoord = gl.getAttribLocation(program, 'aTexCoord');
  gl.enableVertexAttribArray(texCoord);
  gl.vertexAttribPointer(texCoord, 2, gl.FLOAT, false, stride, 2 * Float32Array.BYTES_PER_ELEMENT);

  const texture = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.useProgram(program);
  gl.uniform1i(gl.getUniformLocation(program, 'uTexture'), 0);
  gl.disable(gl.BLEND);

  let textureWidth = 0;
  let textureHeight = 0;
  let lastCanvasSignature = '';

  return {
    draw(frame) {
      const resized = resizeCanvasToDisplaySize(canvas, frame.width, frame.height);
      const canvasSignature = `${canvas.width}x${canvas.height}`;
      if (resized || canvasSignature !== lastCanvasSignature) {
        lastCanvasSignature = canvasSignature;
        gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
        log('renderer canvas size', {
          canvasWidth: canvas.width,
          canvasHeight: canvas.height,
          clientWidth: canvas.clientWidth,
          clientHeight: canvas.clientHeight,
          drawingBufferWidth: gl.drawingBufferWidth,
          drawingBufferHeight: gl.drawingBufferHeight,
          sourceWidth: frame.width,
          sourceHeight: frame.height
        });
      }

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      if (textureWidth !== frame.width || textureHeight !== frame.height) {
        textureWidth = frame.width;
        textureHeight = frame.height;
        gl.texImage2D(
          gl.TEXTURE_2D,
          0,
          gl.RGBA,
          frame.width,
          frame.height,
          0,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          frame.rgba
        );
      } else {
        gl.texSubImage2D(
          gl.TEXTURE_2D,
          0,
          0,
          0,
          frame.width,
          frame.height,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          frame.rgba
        );
      }
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  };
}

function createCanvas2dRenderer(canvas) {
  const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
  if (!ctx) throw new Error('Canvas 2D renderer is not available');
  const sourceCanvas = document.createElement('canvas');
  const sourceCtx = sourceCanvas.getContext('2d', { alpha: true, desynchronized: true });
  if (!sourceCtx) throw new Error('Canvas 2D source renderer is not available');
  return {
    draw(frame) {
      resizeCanvasToDisplaySize(canvas, frame.width, frame.height);
      if (sourceCanvas.width !== frame.width || sourceCanvas.height !== frame.height) {
        sourceCanvas.width = frame.width;
        sourceCanvas.height = frame.height;
      }
      sourceCtx.putImageData(
        new ImageData(
          new Uint8ClampedArray(frame.rgba.buffer, frame.rgba.byteOffset, frame.rgba.byteLength),
          frame.width,
          frame.height
        ),
        0,
        0
      );
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(sourceCanvas, 0, 0, canvas.width, canvas.height);
    }
  };
}

function resizeCanvasToDisplaySize(canvas, fallbackWidth, fallbackHeight) {
  const ratio = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || fallbackWidth;
  const cssHeight = canvas.clientHeight || fallbackHeight;
  const width = Math.max(1, Math.round(cssWidth * ratio));
  const height = Math.max(1, Math.round(cssHeight * ratio));
  if (canvas.width === width && canvas.height === height) return false;
  canvas.width = width;
  canvas.height = height;
  return true;
}

function scheduleContextReload() {
  if (contextReloadTimer) return;
  contextReloadTimer = setTimeout(() => {
    window.location.reload();
  }, 500);
}

function createProgram(gl, vertexSource, fragmentSource) {
  const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  const program = gl.createProgram();
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) || 'WebGL program link failed');
  }
  gl.useProgram(program);
  return program;
}

function createShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) || 'WebGL shader compile failed');
  }
  return shader;
}

function updateFpsStatus() {
  const now = performance.now();
  if (now - frameStats.lastFpsAt < 1000) return;
  const fps = (frameStats.drawn - frameStats.lastDrawn) * 1000 / (now - frameStats.lastFpsAt);
  frameStats.lastDrawn = frameStats.drawn;
  frameStats.lastFpsAt = now;
  console.debug(`raw alpha ${fps.toFixed(1)} fps, dropped ${frameStats.dropped}`);
  log('fps', {
    fps: Number(fps.toFixed(1)),
    received: frameStats.received,
    drawn: frameStats.drawn,
    dropped: frameStats.dropped
  });
}

function applyServer(server) {
  if (!server || server === serverBase) return;
  log('apply server', { previous: serverBase, next: server });
  closeAlphaSession();
  serverBase = server;
  sessionId = null;
  sessionPromise = null;
  resetAudio();
  ensureAlphaSession();
  connect();
  if (playAudio) connectAudio();
}

function applyInteractionState(state = {}) {
  clickThrough = Boolean(state.clickThrough);
  log('apply interaction state', state);
  if (typeof state.playAudio === 'boolean' && state.playAudio !== playAudio) {
    playAudio = state.playAudio;
    if (playAudio) connectAudio();
    else stopAudioSocket();
  }
  document.body.classList.toggle('display', clickThrough);
  document.body.classList.toggle('manage', !clickThrough);
}

function reconnectStreams() {
  log('reconnect streams');
  resetAudio();
  ensureAlphaSession();
  connect();
  if (playAudio) connectAudio();
}

log('viewer loaded', {
  serverBase,
  clickThrough,
  playAudio,
  autoSession,
  closeSessionOnExit,
  zoomScale,
  renderer: urlParams.get('renderer') || 'webgl',
  userAgent: navigator.userAgent,
  devicePixelRatio: window.devicePixelRatio
});

if (window.overlayApi?.onZoom) {
  window.overlayApi.onZoom(adjustZoom);
}

if (window.overlayApi?.onZoomState) {
  window.overlayApi.onZoomState((state = {}) => {
    if (typeof state.scale === 'number' && Number.isFinite(state.scale)) {
      zoomScale = clampScale(state.scale);
    }
  });
}

window.addEventListener('beforeunload', () => {
  if (!closing) {
    closing = true;
  }
  closeAlphaSession();
});

if (window.overlayApi?.onServerChanged) {
  window.overlayApi.onServerChanged(applyServer);
}

if (window.overlayApi?.onInteractionMode) {
  window.overlayApi.onInteractionMode(applyInteractionState);
}

if (window.overlayApi?.onReconnect) {
  window.overlayApi.onReconnect(reconnectStreams);
}
applyInteractionState({ clickThrough, playAudio });
ensureAlphaSession();
connect();
if (playAudio) connectAudio();
