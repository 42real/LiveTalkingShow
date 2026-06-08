const avatar = document.getElementById('avatar');
const urlParams = new URLSearchParams(window.location.search);
let frameRenderer = createFrameRenderer(avatar);
let packedRenderer = null;

let serverBase = urlParams.get('server') || 'http://127.0.0.1:8050';
let clickThrough = urlParams.get('clickThrough') === '1';
let playAudio = urlParams.get('playAudio') === '1';
let autoSession = urlParams.get('autoSession') !== '0';
let closeSessionOnExit = urlParams.get('closeSessionOnExit') === '1';
let zoomScale = clampScale(readPositiveFloatParam('scale', 1));
let videoMaxWidth = readNonNegativeIntParam('videoMaxWidth', 0);
let videoMaxHeight = readNonNegativeIntParam('videoMaxHeight', 0);
let videoFps = readPositiveFloatParam('videoFps', 0);
let videoFormat = readFormatParam('videoFormat', 'bgra');
let videoQuality = readQualityParam('videoQuality', 80);
let outputMode = readOutputModeParam('output', 'ws');

let socket = null;
let audioSocket = null;
let rtcPeer = null;
let rtcAudioTrack = null;
let rtcAudioElement = null;
let packedVideoElement = null;
let packedRenderHandle = null;
let packedRenderHandleType = '';
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
  lastDrawn: 0,
  lastReceiveAt: 0,
  receiveGapMs: 0,
  receiveGapCount: 0,
  maxReceiveGapMs: 0,
  lastDrawAt: 0,
  drawGapMs: 0,
  drawGapCount: 0,
  maxDrawGapMs: 0
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
let lastPackedMediaTime = -1;

function log(message, data) {
  window.overlayApi?.log?.('viewer', message, data);
}

function readPositiveFloatParam(name, fallback) {
  const value = Number.parseFloat(urlParams.get(name) || '');
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function readNonNegativeIntParam(name, fallback) {
  const value = Number.parseInt(urlParams.get(name) || '', 10);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

function readFormatParam(name, fallback) {
  const value = (urlParams.get(name) || '').trim().toLowerCase();
  return ['raw', 'rgba', 'rgba8', 'bgra', 'bgra8', 'jpeg', 'jpg', 'png', 'webp'].includes(value) ? value : fallback;
}

function readOutputModeParam(name, fallback) {
  const value = (urlParams.get(name) || '').trim().toLowerCase();
  if (['webrtc-packed', 'packed-webrtc', 'packed', 'webrtc'].includes(value)) return 'webrtc-packed';
  if (['ws', 'websocket', 'raw'].includes(value)) return 'ws';
  return fallback;
}

function readQualityParam(name, fallback) {
  const value = Number.parseInt(urlParams.get(name) || '', 10);
  return Number.isFinite(value) && value >= 1 && value <= 100 ? value : fallback;
}

function clampScale(value) {
  if (!Number.isFinite(value)) return 1;
  return Math.min(3, Math.max(0.25, value));
}

function wsUrl(server, path) {
  const url = new URL(server);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const [pathname, search = ''] = path.split('?');
  url.pathname = pathname;
  url.search = search;
  return url.toString();
}

function httpUrl(server, path) {
  const url = new URL(server);
  const [pathname, search = ''] = path.split('?');
  url.pathname = pathname;
  url.search = search;
  return url.toString();
}

function alphaVideoPath() {
  const params = new URLSearchParams();
  if (videoMaxWidth > 0) params.set('max_width', String(videoMaxWidth));
  if (videoMaxHeight > 0) params.set('max_height', String(videoMaxHeight));
  if (videoFps > 0) params.set('fps', String(videoFps));
  params.set('format', videoFormat);
  if (videoQuality > 0) params.set('quality', String(videoQuality));
  const query = params.toString();
  return query ? `/alpha/ws?${query}` : '/alpha/ws';
}

function connect() {
  if (outputMode === 'webrtc-packed') {
    connectPackedWebRTC().catch((error) => {
      console.error(error);
      log('packed webrtc connect failed', { error: String(error) });
      scheduleVideoReconnect();
    });
    return;
  }
  connectAlphaWebSocket();
}

function connectAlphaWebSocket() {
  if (reconnectVideoTimer) clearTimeout(reconnectVideoTimer);
  reconnectVideoTimer = null;
  if (socket) {
    socket.onclose = null;
    socket.close();
  }

  const videoPath = alphaVideoPath();
  log('connect video websocket', {
    serverBase,
    url: wsUrl(serverBase, videoPath),
    videoMaxWidth,
    videoMaxHeight,
    videoFps,
    videoFormat,
    videoQuality
  });
  socket = new WebSocket(wsUrl(serverBase, videoPath));
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
    recordReceiveGap();
    if (pendingFrame) frameStats.dropped++;
    pendingFrame = event.data;
    scheduleDraw();
  };
}

function scheduleVideoReconnect() {
  if (closing) return;
  if (reconnectVideoTimer) clearTimeout(reconnectVideoTimer);
  reconnectVideoTimer = setTimeout(connect, 2000);
}

async function connectPackedWebRTC() {
  if (reconnectVideoTimer) clearTimeout(reconnectVideoTimer);
  reconnectVideoTimer = null;
  stopAlphaWebSocket();
  stopAudioSocket();
  stopPackedWebRTC();

  const pc = new RTCPeerConnection({
    sdpSemantics: 'unified-plan',
    bundlePolicy: 'max-bundle'
  });
  rtcPeer = pc;

  pc.addTransceiver('audio', { direction: 'recvonly' });
  pc.addTransceiver('video', { direction: 'recvonly' });

  pc.addEventListener('connectionstatechange', () => {
    log('packed webrtc connection state', { state: pc.connectionState, sessionId });
    if (['failed', 'disconnected', 'closed'].includes(pc.connectionState) && !closing && rtcPeer === pc) {
      scheduleVideoReconnect();
    }
  });

  pc.addEventListener('iceconnectionstatechange', () => {
    log('packed webrtc ice state', { state: pc.iceConnectionState });
  });

  pc.addEventListener('track', (event) => {
    log('packed webrtc track', {
      kind: event.track.kind,
      id: event.track.id,
      mid: event.transceiver?.mid || ''
    });
    if (event.track.kind === 'audio') {
      rtcAudioTrack = event.track;
      applyRtcAudioPlayback();
      return;
    }
    attachPackedVideoTrack(event.track);
  });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await waitIceComplete(pc);

  log('send packed webrtc offer', { serverBase, url: httpUrl(serverBase, '/alpha/webrtc/packed_offer') });
  const offerPayload = {
    sdp: pc.localDescription.sdp,
    type: pc.localDescription.type
  };
  if (videoMaxWidth > 0) offerPayload.max_width = videoMaxWidth;
  if (videoMaxHeight > 0) offerPayload.max_height = videoMaxHeight;
  if (videoFps > 0) offerPayload.fps = videoFps;
  const response = await fetch(httpUrl(serverBase, '/alpha/webrtc/packed_offer'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(offerPayload)
  });
  const answer = await response.json();
  if (!response.ok || !answer.sdp) {
    throw new Error(answer.msg || `packed offer failed: ${response.status}`);
  }

  sessionId = String(answer.sessionid || '');
  sessionPromise = Promise.resolve(sessionId);
  await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
  log('packed webrtc connected', { sessionId, tracks: answer.tracks });
}

function waitIceComplete(peer) {
  if (peer.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve) => {
    const check = () => {
      if (peer.iceGatheringState === 'complete') {
        peer.removeEventListener('icegatheringstatechange', check);
        resolve();
      }
    };
    peer.addEventListener('icegatheringstatechange', check);
  });
}

function stopAlphaWebSocket() {
  if (reconnectVideoTimer) clearTimeout(reconnectVideoTimer);
  reconnectVideoTimer = null;
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
}

function stopPackedWebRTC() {
  cancelPackedRenderLoop();
  const peer = rtcPeer;
  rtcPeer = null;
  if (peer) {
    peer.ontrack = null;
    for (const sender of peer.getSenders()) {
      if (sender.track) sender.track.stop();
    }
    for (const receiver of peer.getReceivers()) {
      if (receiver.track) receiver.track.stop();
    }
    peer.close();
  }
  if (packedVideoElement) {
    packedVideoElement.pause();
    packedVideoElement.srcObject = null;
    packedVideoElement.remove();
    packedVideoElement = null;
  }
  stopRtcAudioPlayback();
  rtcAudioTrack = null;
}

function attachPackedVideoTrack(track) {
  if (packedVideoElement) {
    packedVideoElement.pause();
    packedVideoElement.srcObject = null;
    packedVideoElement.remove();
  }
  packedVideoElement = document.createElement('video');
  packedVideoElement.autoplay = true;
  packedVideoElement.playsInline = true;
  packedVideoElement.muted = true;
  packedVideoElement.disablePictureInPicture = true;
  packedVideoElement.className = 'media-decode-sink';
  packedVideoElement.srcObject = new MediaStream([track]);
  document.body.appendChild(packedVideoElement);
  packedVideoElement.addEventListener('loadedmetadata', () => {
    log('packed video metadata', {
      packedWidth: packedVideoElement.videoWidth,
      height: packedVideoElement.videoHeight,
      logicalWidth: Math.floor((packedVideoElement.videoWidth || 0) / 2),
      readyState: packedVideoElement.readyState
    });
    startPackedRenderLoop();
  });
  packedVideoElement.play()
    .then(startPackedRenderLoop)
    .catch((error) => log('packed video play blocked', { error: String(error) }));
}

function applyRtcAudioPlayback() {
  if (outputMode !== 'webrtc-packed' || !rtcAudioTrack) return;
  if (!playAudio) {
    stopRtcAudioPlayback();
    return;
  }
  if (!rtcAudioElement) {
    rtcAudioElement = document.createElement('audio');
    rtcAudioElement.autoplay = true;
    rtcAudioElement.controls = false;
    rtcAudioElement.style.display = 'none';
    document.body.appendChild(rtcAudioElement);
  }
  rtcAudioElement.srcObject = new MediaStream([rtcAudioTrack]);
  rtcAudioElement.play().catch((error) => log('packed audio play blocked', { error: String(error) }));
}

function stopRtcAudioPlayback() {
  if (!rtcAudioElement) return;
  rtcAudioElement.pause();
  rtcAudioElement.srcObject = null;
  rtcAudioElement.remove();
  rtcAudioElement = null;
}

function startPackedRenderLoop() {
  if (!packedVideoElement) return;
  if (packedRenderHandle !== null) return;
  packedRenderer = packedRenderer || createPackedWebRTCRenderer(avatar);
  schedulePackedRenderFrame();
}

function cancelPackedRenderLoop() {
  if (packedRenderHandle === null) return;
  if (
    packedRenderHandleType === 'videoFrame' &&
    packedVideoElement &&
    typeof packedVideoElement.cancelVideoFrameCallback === 'function'
  ) {
    packedVideoElement.cancelVideoFrameCallback(packedRenderHandle);
  } else {
    cancelAnimationFrame(packedRenderHandle);
  }
  packedRenderHandle = null;
  packedRenderHandleType = '';
}

function schedulePackedRenderFrame() {
  if (!packedVideoElement || closing || outputMode !== 'webrtc-packed') return;
  if (
    packedVideoElement.readyState >= 2 &&
    typeof packedVideoElement.requestVideoFrameCallback === 'function'
  ) {
    packedRenderHandleType = 'videoFrame';
    packedRenderHandle = packedVideoElement.requestVideoFrameCallback((_now, metadata = {}) => {
      packedRenderHandle = null;
      if (typeof metadata.mediaTime !== 'number' || metadata.mediaTime !== lastPackedMediaTime) {
        lastPackedMediaTime = metadata.mediaTime;
        drawPackedVideoFrame(metadata);
      }
      schedulePackedRenderFrame();
    });
    return;
  }

  packedRenderHandleType = 'animationFrame';
  packedRenderHandle = requestAnimationFrame(() => {
    packedRenderHandle = null;
    drawPackedVideoFrame();
    schedulePackedRenderFrame();
  });
}

function drawPackedVideoFrame(metadata = {}) {
  const video = packedVideoElement;
  if (!video || video.readyState < 2) return;

  const packedWidth = video.videoWidth || 0;
  const height = video.videoHeight || 0;
  const width = Math.max(1, Math.floor(packedWidth / 2));
  if (!packedWidth || !height) return;

  const signature = `${width}x${height}|packed=${packedWidth}`;
  if (!firstFrameLogged || signature !== lastFrameSignature) {
    firstFrameLogged = true;
    lastFrameSignature = signature;
    log('packed frame size', { width, height, packedWidth });
  }

  lastSourceFrame = { width, height };
  requestWindowResize(width, height);
  try {
    packedRenderer.draw(video, width, height, packedWidth);
  } catch (error) {
    console.error(error);
    log('packed renderer failed', { error: String(error) });
    scheduleContextReload();
    return;
  }
  frameStats.received++;
  frameStats.drawn++;
  recordDrawGap();
  updateFpsStatus(metadata);
}

async function ensureAlphaSession() {
  if (outputMode === 'webrtc-packed') return sessionId;
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
  if (outputMode === 'webrtc-packed') {
    applyRtcAudioPlayback();
    return;
  }
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
  if (outputMode === 'ws') {
    queueMicrotask(drawLatestFrame);
    return;
  }
  requestAnimationFrame(drawLatestFrame);
}

async function drawLatestFrame() {
  const packet = pendingFrame;
  pendingFrame = null;
  if (!packet) {
    drawing = false;
    return;
  }

  const parsed = parseFrame(packet);
  if (!parsed) {
    log('drop invalid frame', { byteLength: packet.byteLength });
    drawing = false;
    if (pendingFrame) scheduleDraw();
    return;
  }

  const signature = `${parsed.width}x${parsed.height}`;
  if (!firstFrameLogged || signature !== lastFrameSignature) {
    firstFrameLogged = true;
    lastFrameSignature = signature;
    log('frame size', {
      width: parsed.width,
      height: parsed.height,
      byteLength: packet.byteLength,
      format: parsed.formatName
    });
  }

  lastSourceFrame = { width: parsed.width, height: parsed.height };
  requestWindowResize(parsed.width, parsed.height);

  try {
    await frameRenderer.draw(parsed);
  } catch (error) {
    console.error(error);
    scheduleContextReload();
    drawing = false;
    return;
  }
  frameStats.drawn++;
  recordDrawGap();
  updateFpsStatus();

  drawing = false;
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
  if (version !== 1 || width <= 0 || height <= 0) {
    log('invalid frame metadata', { version, format, width, height });
    return null;
  }

  if (format === 1 || format === 5) {
    const expected = 24 + width * height * 4;
    if (packet.byteLength !== expected) {
      log('invalid frame payload length', { expected, actual: packet.byteLength, width, height });
      return null;
    }
    return {
      width,
      height,
      format,
      formatName: format === 5 ? 'bgra' : 'rgba',
      bgra: format === 5,
      rgba: new Uint8Array(packet, 24)
    };
  }
  if (format === 2 || format === 3 || format === 4) {
    return {
      width,
      height,
      format,
      formatName: format === 2 ? 'jpeg' : format === 3 ? 'png' : 'webp',
      encoded: new Uint8Array(packet, 24)
    };
  }
  log('unsupported frame format', { format });
  return null;
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
      uniform bool uBgra;
      varying vec2 vTexCoord;
      void main() {
        vec4 color = texture2D(uTexture, vTexCoord);
        gl_FragColor = uBgra ? vec4(color.b, color.g, color.r, color.a) : color;
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
  const bgraUniform = gl.getUniformLocation(program, 'uBgra');
  gl.disable(gl.BLEND);

  let textureWidth = 0;
  let textureHeight = 0;
  let lastCanvasSignature = '';

  return {
    async draw(frame) {
      if (frame.format !== 1 && frame.format !== 5) {
        await drawEncodedFrame(canvas, frame);
        return;
      }
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
      gl.uniform1i(bgraUniform, frame.bgra ? 1 : 0);
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
    async draw(frame) {
      resizeCanvasToDisplaySize(canvas, frame.width, frame.height);
      if (frame.format !== 1) {
        if (frame.format === 5) {
          drawRawBgra2d(frame);
          return;
        }
        await drawEncodedFrame(canvas, frame);
        return;
      }
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

  function drawRawBgra2d(frame) {
    resizeCanvasToDisplaySize(canvas, frame.width, frame.height);
    if (sourceCanvas.width !== frame.width || sourceCanvas.height !== frame.height) {
      sourceCanvas.width = frame.width;
      sourceCanvas.height = frame.height;
    }
    sourceCtx.putImageData(
      new ImageData(bgraToRgba(frame.rgba), frame.width, frame.height),
      0,
      0
    );
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(sourceCanvas, 0, 0, canvas.width, canvas.height);
  }
}

function bgraToRgba(bgra) {
  const rgba = new Uint8ClampedArray(bgra.byteLength);
  for (let i = 0; i < bgra.byteLength; i += 4) {
    rgba[i] = bgra[i + 2];
    rgba[i + 1] = bgra[i + 1];
    rgba[i + 2] = bgra[i];
    rgba[i + 3] = bgra[i + 3];
  }
  return rgba;
}

function createPackedWebRTCRenderer(canvas) {
  const gl = canvas.getContext('webgl', {
    alpha: true,
    antialias: false,
    depth: false,
    desynchronized: true,
    premultipliedAlpha: false,
    preserveDrawingBuffer: false,
    stencil: false
  });
  if (!gl) throw new Error('WebGL renderer is required for packed WebRTC alpha');

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
      uniform sampler2D uPacked;
      varying vec2 vTexCoord;
      void main() {
        vec2 colorCoord = vec2(vTexCoord.x * 0.5, vTexCoord.y);
        vec2 alphaCoord = vec2(0.5 + vTexCoord.x * 0.5, vTexCoord.y);
        vec4 color = texture2D(uPacked, colorCoord);
        float alpha = texture2D(uPacked, alphaCoord).r;
        gl_FragColor = vec4(color.rgb, alpha);
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
  gl.useProgram(program);
  gl.uniform1i(gl.getUniformLocation(program, 'uPacked'), 0);
  gl.disable(gl.BLEND);

  let lastCanvasSignature = '';

  return {
    draw(video, logicalWidth, logicalHeight, packedWidth) {
      const resized = resizeCanvasToDisplaySize(canvas, logicalWidth, logicalHeight);
      const canvasSignature = `${canvas.width}x${canvas.height}`;
      if (resized || canvasSignature !== lastCanvasSignature) {
        lastCanvasSignature = canvasSignature;
        gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
        log('packed renderer canvas size', {
          canvasWidth: canvas.width,
          canvasHeight: canvas.height,
          clientWidth: canvas.clientWidth,
          clientHeight: canvas.clientHeight,
          drawingBufferWidth: gl.drawingBufferWidth,
          drawingBufferHeight: gl.drawingBufferHeight,
          sourceWidth: logicalWidth,
          sourceHeight: logicalHeight,
          packedWidth
        });
      }

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  };
}

async function drawEncodedFrame(canvas, frame) {
  const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
  if (!ctx) throw new Error('Canvas 2D renderer is not available');
  resizeCanvasToDisplaySize(canvas, frame.width, frame.height);
  const mime = frame.format === 2 ? 'image/jpeg' : frame.format === 3 ? 'image/png' : 'image/webp';
  const bitmap = await createImageBitmap(new Blob([frame.encoded], { type: mime }));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
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

function updateFpsStatus(metadata = {}) {
  const now = performance.now();
  if (now - frameStats.lastFpsAt < 1000) return;
  const fps = (frameStats.drawn - frameStats.lastDrawn) * 1000 / (now - frameStats.lastFpsAt);
  frameStats.lastDrawn = frameStats.drawn;
  frameStats.lastFpsAt = now;
  console.debug(`${outputMode} alpha ${fps.toFixed(1)} fps, dropped ${frameStats.dropped}`);
  const playbackQuality = packedVideoElement && typeof packedVideoElement.getVideoPlaybackQuality === 'function'
    ? packedVideoElement.getVideoPlaybackQuality()
    : null;
  log('fps', {
    outputMode,
    fps: Number(fps.toFixed(1)),
    received: frameStats.received,
    drawn: frameStats.drawn,
    dropped: frameStats.dropped,
    avgReceiveGapMs: frameStats.receiveGapCount
      ? Number((frameStats.receiveGapMs / frameStats.receiveGapCount).toFixed(1))
      : undefined,
    maxReceiveGapMs: frameStats.maxReceiveGapMs ? Number(frameStats.maxReceiveGapMs.toFixed(1)) : undefined,
    avgDrawGapMs: frameStats.drawGapCount
      ? Number((frameStats.drawGapMs / frameStats.drawGapCount).toFixed(1))
      : undefined,
    maxDrawGapMs: frameStats.maxDrawGapMs ? Number(frameStats.maxDrawGapMs.toFixed(1)) : undefined,
    mediaTime: typeof metadata.mediaTime === 'number' ? Number(metadata.mediaTime.toFixed(3)) : undefined,
    presentedFrames: metadata.presentedFrames,
    processingMs: typeof metadata.processingDuration === 'number'
      ? Number((metadata.processingDuration * 1000).toFixed(2))
      : undefined,
    totalVideoFrames: playbackQuality ? playbackQuality.totalVideoFrames : undefined,
    droppedVideoFrames: playbackQuality ? playbackQuality.droppedVideoFrames : undefined,
    corruptedVideoFrames: playbackQuality ? playbackQuality.corruptedVideoFrames : undefined,
    readyState: packedVideoElement ? packedVideoElement.readyState : undefined,
    paused: packedVideoElement ? packedVideoElement.paused : undefined
  });
  frameStats.receiveGapMs = 0;
  frameStats.receiveGapCount = 0;
  frameStats.maxReceiveGapMs = 0;
  frameStats.drawGapMs = 0;
  frameStats.drawGapCount = 0;
  frameStats.maxDrawGapMs = 0;
}

function recordReceiveGap() {
  const now = performance.now();
  if (frameStats.lastReceiveAt > 0) {
    const gap = now - frameStats.lastReceiveAt;
    frameStats.receiveGapMs += gap;
    frameStats.receiveGapCount++;
    frameStats.maxReceiveGapMs = Math.max(frameStats.maxReceiveGapMs, gap);
    if (gap > 80) log('video receive jitter', { gapMs: Number(gap.toFixed(1)), outputMode });
  }
  frameStats.lastReceiveAt = now;
}

function recordDrawGap() {
  const now = performance.now();
  if (frameStats.lastDrawAt > 0) {
    const gap = now - frameStats.lastDrawAt;
    frameStats.drawGapMs += gap;
    frameStats.drawGapCount++;
    frameStats.maxDrawGapMs = Math.max(frameStats.maxDrawGapMs, gap);
    if (gap > 80) log('video draw jitter', { gapMs: Number(gap.toFixed(1)), outputMode });
  }
  frameStats.lastDrawAt = now;
}

function applyServer(server) {
  if (!server || server === serverBase) return;
  log('apply server', { previous: serverBase, next: server });
  closeAlphaSession();
  serverBase = server;
  sessionId = null;
  sessionPromise = null;
  resetAudio();
  stopPackedWebRTC();
  stopAlphaWebSocket();
  ensureAlphaSession();
  connect();
  if (playAudio) connectAudio();
}

function applyInteractionState(state = {}) {
  clickThrough = Boolean(state.clickThrough);
  log('apply interaction state', state);
  if (typeof state.playAudio === 'boolean' && state.playAudio !== playAudio) {
    playAudio = state.playAudio;
    if (outputMode === 'webrtc-packed') {
      if (playAudio) applyRtcAudioPlayback();
      else stopRtcAudioPlayback();
    } else if (playAudio) connectAudio();
    else stopAudioSocket();
  }
  document.body.classList.toggle('display', clickThrough);
  document.body.classList.toggle('manage', !clickThrough);
}

function reconnectStreams() {
  log('reconnect streams');
  resetAudio();
  stopPackedWebRTC();
  stopAlphaWebSocket();
  if (autoSession || outputMode === 'webrtc-packed') {
    sessionId = null;
    sessionPromise = null;
  }
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
  videoMaxWidth,
  videoMaxHeight,
  videoFps,
  videoFormat,
  videoQuality,
  outputMode,
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
  stopPackedWebRTC();
  stopAlphaWebSocket();
  stopAudioSocket();
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
