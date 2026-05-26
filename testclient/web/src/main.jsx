import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, Cable, Mic, Play, RotateCcw, Send, Square, Video, Volume2, VolumeX } from 'lucide-react';
import './styles.css';

function wsUrl(base, path) {
  const url = new URL(base);
  const target = new URL(path, url.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = target.pathname;
  url.search = target.search;
  return url.toString();
}

const DEFAULT_LIVETALKING_URL = import.meta.env.VITE_LIVETALKING_URL || 'http://127.0.0.1:8050';

const DEFAULTS = {
  liveTalkingUrl: DEFAULT_LIVETALKING_URL,
  ttsServerUrl: import.meta.env.VITE_TTS_SERVER_URL || 'http://127.0.0.1:8036',
  alphaInputWs: import.meta.env.VITE_ALPHA_INPUT_WS || wsUrl(DEFAULT_LIVETALKING_URL, '/alpha/input/audio'),
  text: import.meta.env.VITE_DEFAULT_TEXT || '这是一段 robottts 兼容接口流式测试。',
  prompts: import.meta.env.VITE_DEFAULT_PROMPTS || '请自然清晰地朗读。',
  voiceId: Number.parseInt(import.meta.env.VITE_DEFAULT_VOICE_ID || '0', 10),
  mode: import.meta.env.VITE_DEFAULT_MODE || 'instruct2',
  audioSampleRate: Number.parseInt(import.meta.env.VITE_ALPHA_AUDIO_SAMPLE_RATE || '16000', 10),
  videoMaxHeight: Number.parseInt(import.meta.env.VITE_ALPHA_VIDEO_MAX_HEIGHT || '720', 10),
  videoPreviewFps: Number.parseFloat(import.meta.env.VITE_ALPHA_VIDEO_FPS || '8'),
  videoRenderIntervalMs: Math.max(33, Number.parseInt(import.meta.env.VITE_VIDEO_RENDER_INTERVAL_MS || '125', 10)),
  alphaAutoConnect: (import.meta.env.VITE_ALPHA_AUTO_CONNECT || '1') !== '0'
};

function parseFrame(packet) {
  if (!packet || packet.byteLength < 24) return null;
  const view = new DataView(packet);
  const magic = String.fromCharCode(...new Uint8Array(packet.slice(0, 4)));
  if (magic !== 'LTAF') return null;
  const version = view.getUint8(4);
  const format = view.getUint8(5);
  const width = view.getUint32(8, true);
  const height = view.getUint32(12, true);
  const seq = Number(view.getBigUint64(16, true));
  if (version !== 1 || format !== 1 || width <= 0 || height <= 0) return null;
  const pixels = new Uint8ClampedArray(packet, 24);
  if (pixels.byteLength !== width * height * 4) return null;
  return { width, height, seq, pixels };
}

function App() {
  const [liveTalkingUrl, setLiveTalkingUrl] = useState(DEFAULTS.liveTalkingUrl);
  const [ttsServerUrl, setTtsServerUrl] = useState(DEFAULTS.ttsServerUrl);
  const [alphaInputWs, setAlphaInputWs] = useState(DEFAULTS.alphaInputWs);
  const [text, setText] = useState(DEFAULTS.text);
  const [prompts, setPrompts] = useState(DEFAULTS.prompts);
  const [voiceId, setVoiceId] = useState(DEFAULTS.voiceId);
  const [mode, setMode] = useState(DEFAULTS.mode);
  const [voices, setVoices] = useState([]);
  const [sessionId, setSessionId] = useState('');
  const [status, setStatus] = useState('idle');
  const [videoState, setVideoState] = useState('disconnected');
  const [audioState, setAudioState] = useState('disconnected');
  const [frameInfo, setFrameInfo] = useState({ width: 0, height: 0, seq: 0, fps: 0 });
  const [audioInfo, setAudioInfo] = useState({ chunks: 0, bytes: 0 });
  const [logs, setLogs] = useState([]);
  const canvasRef = useRef(null);
  const socketRef = useRef(null);
  const audioSocketRef = useRef(null);
  const audioContextRef = useRef(null);
  const audioScheduleRef = useRef(0);
  const latestFramePacketRef = useRef(null);
  const renderTimerRef = useRef(0);
  const lastVideoDrawAtRef = useRef(0);
  const alphaAutoStartedRef = useRef(false);
  const frameStatsRef = useRef({ lastAt: performance.now(), lastSeq: 0, fps: 0 });
  const audioStatsRef = useRef({ chunks: 0, bytes: 0, lastUpdateAt: 0 });

  const addLog = useCallback((message, data) => {
    const time = new Date().toLocaleTimeString();
    const suffix = data ? ` ${JSON.stringify(data)}` : '';
    setLogs((items) => [`[${time}] ${message}${suffix}`, ...items].slice(0, 80));
  }, []);

  const normalized = useMemo(() => {
    const live = liveTalkingUrl.replace(/\/$/, '');
    const tts = ttsServerUrl.replace(/\/$/, '');
    return {
      live,
      tts,
      alphaWs: wsUrl(live, `/alpha/ws?max_height=${DEFAULTS.videoMaxHeight}&fps=${DEFAULTS.videoPreviewFps}`),
      audioWs: wsUrl(live, '/alpha/audio')
    };
  }, [liveTalkingUrl, ttsServerUrl]);

  const drawFrame = useCallback((packet) => {
    const frame = parseFrame(packet);
    if (!frame) {
      addLog('丢弃无效视频帧');
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (canvas.width !== frame.width || canvas.height !== frame.height) {
      canvas.width = frame.width;
      canvas.height = frame.height;
    }
    const ctx = canvas.getContext('2d');
    ctx.putImageData(new ImageData(frame.pixels, frame.width, frame.height), 0, 0);

    const stats = frameStatsRef.current;
    const now = performance.now();
    const elapsed = now - stats.lastAt;
    let fps = stats.fps;
    if (elapsed >= 1000) {
      fps = ((frame.seq - stats.lastSeq) * 1000) / elapsed;
      stats.lastAt = now;
      stats.lastSeq = frame.seq;
      stats.fps = fps;
    }
    setFrameInfo({ width: frame.width, height: frame.height, seq: frame.seq, fps });
  }, [addLog]);

  const renderLatestFrame = useCallback(() => {
    renderTimerRef.current = 0;
    const packet = latestFramePacketRef.current;
    latestFramePacketRef.current = null;
    if (packet) {
      drawFrame(packet);
      lastVideoDrawAtRef.current = performance.now();
    }
  }, [drawFrame]);

  const enqueueVideoFrame = useCallback((packet) => {
    latestFramePacketRef.current = packet;
    if (renderTimerRef.current) return;
    const elapsed = performance.now() - lastVideoDrawAtRef.current;
    const wait = Math.max(0, DEFAULTS.videoRenderIntervalMs - elapsed);
    renderTimerRef.current = window.setTimeout(renderLatestFrame, wait);
  }, [renderLatestFrame]);

  const connectVideo = useCallback(() => {
    if (socketRef.current) socketRef.current.close();
    const socket = new WebSocket(normalized.alphaWs);
    socket.binaryType = 'arraybuffer';
    socketRef.current = socket;
    setVideoState('connecting');
    addLog('连接 alpha 视频流', { url: normalized.alphaWs });
    socket.onopen = () => {
      setVideoState('connected');
      addLog('alpha 视频流已连接');
    };
    socket.onmessage = (event) => enqueueVideoFrame(event.data);
    socket.onerror = () => {
      setVideoState('error');
      addLog('alpha 视频流连接错误');
    };
    socket.onclose = (event) => {
      setVideoState('disconnected');
      addLog('alpha 视频流已断开', { code: event.code });
    };
  }, [addLog, enqueueVideoFrame, normalized.alphaWs]);

  const disconnectVideo = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    latestFramePacketRef.current = null;
    if (renderTimerRef.current) {
      clearTimeout(renderTimerRef.current);
      renderTimerRef.current = 0;
    }
    setVideoState('disconnected');
  }, []);

  const playAudioChunk = useCallback((packet) => {
    const audioContext = audioContextRef.current;
    if (!audioContext || !(packet instanceof ArrayBuffer) || packet.byteLength < 2) return;

    const samples = new Int16Array(packet);
    const buffer = audioContext.createBuffer(1, samples.length, DEFAULTS.audioSampleRate);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      channel[index] = Math.max(-1, Math.min(1, samples[index] / 32768));
    }

    const now = audioContext.currentTime;
    if (
      !audioScheduleRef.current ||
      audioScheduleRef.current < now + 0.03 ||
      audioScheduleRef.current > now + 0.8
    ) {
      audioScheduleRef.current = now + 0.05;
    }

    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.start(audioScheduleRef.current);
    audioScheduleRef.current += buffer.duration;

    const stats = audioStatsRef.current;
    stats.chunks += 1;
    stats.bytes += packet.byteLength;
    const updateAt = performance.now();
    if (updateAt - stats.lastUpdateAt >= 500) {
      stats.lastUpdateAt = updateAt;
      setAudioInfo({ chunks: stats.chunks, bytes: stats.bytes });
    }
  }, []);

  const disconnectAudio = useCallback(() => {
    audioSocketRef.current?.close();
    audioSocketRef.current = null;
    audioScheduleRef.current = 0;
    audioStatsRef.current = { chunks: 0, bytes: 0, lastUpdateAt: 0 };
    setAudioState('disconnected');
    setAudioInfo({ chunks: 0, bytes: 0 });
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
  }, []);

  const connectAudio = useCallback(async () => {
    disconnectAudio();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      setAudioState('error');
      addLog('浏览器不支持 Web Audio');
      return;
    }

    const audioContext = new AudioContextClass();
    audioContextRef.current = audioContext;
    await audioContext.resume();

    const socket = new WebSocket(normalized.audioWs);
    socket.binaryType = 'arraybuffer';
    audioSocketRef.current = socket;
    setAudioState('connecting');
    addLog('连接 alpha 音频流', { url: normalized.audioWs, sampleRate: DEFAULTS.audioSampleRate });
    socket.onopen = () => {
      setAudioState('connected');
      addLog('alpha 音频流已连接');
    };
    socket.onmessage = (event) => playAudioChunk(event.data);
    socket.onerror = () => {
      setAudioState('error');
      addLog('alpha 音频流连接错误');
    };
    socket.onclose = (event) => {
      setAudioState('disconnected');
      addLog('alpha 音频流已断开', { code: event.code });
    };
  }, [addLog, disconnectAudio, normalized.audioWs, playAudioChunk]);

  useEffect(() => () => {
    disconnectVideo();
    disconnectAudio();
  }, [disconnectAudio, disconnectVideo]);

  const checkHealth = async () => {
    setStatus('checking');
    try {
      const [liveResp, ttsResp, voiceResp] = await Promise.all([
        fetch(`${normalized.live}/alpha/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reuse: true })
        }),
        fetch(`${normalized.tts}/health`),
        fetch(`${normalized.tts}/tts/voices`)
      ]);
      const liveJson = await liveResp.json();
      const ttsJson = await ttsResp.json();
      const voiceJson = await voiceResp.json();
      if (liveJson?.data?.sessionid) setSessionId(String(liveJson.data.sessionid));
      setVoices(Array.isArray(voiceJson.voices) ? voiceJson.voices : []);
      setStatus('ready');
      addLog('健康检查完成', { live: liveJson.code, tts: ttsJson.status || ttsJson.provider });
    } catch (error) {
      setStatus('error');
      addLog('健康检查失败', { error: String(error) });
    }
  };

  const createSession = async () => {
    try {
      const resp = await fetch(`${normalized.live}/alpha/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reuse: true })
      });
      const payload = await resp.json();
      if (!resp.ok || payload.code !== 0) throw new Error(payload.msg || 'session failed');
      setSessionId(String(payload.data.sessionid));
      addLog('alpha session ready', { sessionid: payload.data.sessionid });
    } catch (error) {
      addLog('创建 alpha session 失败', { error: String(error) });
    }
  };

  useEffect(() => {
    if (!DEFAULTS.alphaAutoConnect || alphaAutoStartedRef.current) return;
    alphaAutoStartedRef.current = true;
    createSession();
    connectVideo();
  }, [connectVideo]);

  const speakViaLiveTalking = async () => {
    setStatus('speaking');
    try {
      const resp = await fetch(`${normalized.live}/alpha/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          type: 'echo',
          interrupt: true,
          sessionid: sessionId || undefined,
          tts: {
            voice_id: voiceId,
            prompts,
            mode
          }
        })
      });
      const payload = await resp.json();
      if (!resp.ok || payload.code !== 0) throw new Error(payload.msg || 'speak failed');
      if (payload?.data?.sessionid) setSessionId(String(payload.data.sessionid));
      setStatus('speaking');
      addLog('/alpha/speak 已提交', payload.data || {});
    } catch (error) {
      setStatus('error');
      addLog('/alpha/speak 失败', { error: String(error) });
    }
  };

  const pushViaTask = async () => {
    setStatus('task');
    try {
      const taskId = `test-${Date.now()}`;
      const resp = await fetch(`${normalized.tts}/tts/task/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: taskId,
          text,
          voice_id: voiceId,
          prompts,
          mode,
          target_hardware: alphaInputWs
        })
      });
      const payload = await resp.json();
      if (!resp.ok || payload.error) throw new Error(payload.message || JSON.stringify(payload));
      addLog('TTS task 已启动', { taskId });
    } catch (error) {
      setStatus('error');
      addLog('TTS task 失败', { error: String(error) });
    }
  };

  const interrupt = async () => {
    try {
      await fetch(`${normalized.live}/interrupt_talk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionid: sessionId })
      });
      setStatus('interrupted');
      addLog('已发送打断');
    } catch (error) {
      addLog('打断失败', { error: String(error) });
    }
  };

  return (
    <main className="app">
      <section className="workspace">
        <div className="panel controls">
          <div className="title">
            <Activity size={18} />
            <span>RobotTTS 流式测试</span>
          </div>

          <label>
            LiveTalking
            <input value={liveTalkingUrl} onChange={(event) => setLiveTalkingUrl(event.target.value)} />
          </label>
          <label>
            TTS Server
            <input value={ttsServerUrl} onChange={(event) => setTtsServerUrl(event.target.value)} />
          </label>
          <label>
            Alpha Audio Input
            <input value={alphaInputWs} onChange={(event) => setAlphaInputWs(event.target.value)} />
          </label>

          <div className="grid2">
            <label>
              Voice
              <select value={voiceId} onChange={(event) => setVoiceId(Number.parseInt(event.target.value, 10))}>
                {voices.length === 0 && <option value={voiceId}>voice {voiceId}</option>}
                {voices.map((voice) => (
                  <option value={voice.id} key={voice.id}>{voice.id} {voice.name}</option>
                ))}
              </select>
            </label>
            <label>
              Mode
              <select value={mode} onChange={(event) => setMode(event.target.value)}>
                <option value="instruct2">instruct2</option>
                <option value="zero-shot">zero-shot</option>
              </select>
            </label>
          </div>

          <label>
            Prompts
            <input value={prompts} onChange={(event) => setPrompts(event.target.value)} />
          </label>
          <label>
            Text
            <textarea value={text} onChange={(event) => setText(event.target.value)} />
          </label>

          <div className="buttons">
            <button onClick={checkHealth}><Cable size={16} />检查</button>
            <button onClick={createSession}><RotateCcw size={16} />Session</button>
            <button onClick={connectVideo}><Video size={16} />视频</button>
            <button onClick={disconnectVideo}><Square size={16} />断开</button>
            <button onClick={connectAudio}><Volume2 size={16} />音频</button>
            <button onClick={disconnectAudio}><VolumeX size={16} />静音</button>
            <button onClick={speakViaLiveTalking}><Send size={16} />alpha/speak</button>
            <button onClick={pushViaTask}><Mic size={16} />TTS task</button>
            <button onClick={interrupt}><Square size={16} />打断</button>
          </div>
        </div>

        <div className="panel videoPanel">
          <div className="videoHead">
            <span>Alpha Video</span>
            <span>{videoState} | {frameInfo.width}x{frameInfo.height} | #{frameInfo.seq} | {frameInfo.fps.toFixed(1)} fps</span>
          </div>
          <div className="canvasWrap">
            <canvas ref={canvasRef} />
          </div>
        </div>

        <div className="panel logs">
          <div className="title">
            <Play size={18} />
            <span>
              Status: {status} {sessionId ? `| session ${sessionId}` : ''}
              {' '}| audio {audioState} {audioInfo.chunks ? `| ${audioInfo.chunks} chunks` : ''}
            </span>
          </div>
          <pre>{logs.join('\n')}</pre>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
