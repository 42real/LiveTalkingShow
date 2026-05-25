import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, Cable, Mic, Play, RotateCcw, Send, Square, Video } from 'lucide-react';
import './styles.css';

const DEFAULTS = {
  liveTalkingUrl: import.meta.env.VITE_LIVETALKING_URL || 'http://127.0.0.1:8050',
  ttsServerUrl: import.meta.env.VITE_TTS_SERVER_URL || 'http://127.0.0.1:8036',
  alphaInputWs: import.meta.env.VITE_ALPHA_INPUT_WS || 'ws://127.0.0.1:8050/alpha/input/audio',
  text: import.meta.env.VITE_DEFAULT_TEXT || '这是一段 robottts 兼容接口流式测试。',
  prompts: import.meta.env.VITE_DEFAULT_PROMPTS || '请自然清晰地朗读。',
  voiceId: Number.parseInt(import.meta.env.VITE_DEFAULT_VOICE_ID || '0', 10),
  mode: import.meta.env.VITE_DEFAULT_MODE || 'instruct2'
};

function wsUrl(base, path) {
  const url = new URL(base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = path;
  url.search = '';
  return url.toString();
}

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
  const [frameInfo, setFrameInfo] = useState({ width: 0, height: 0, seq: 0, fps: 0 });
  const [logs, setLogs] = useState([]);
  const canvasRef = useRef(null);
  const socketRef = useRef(null);
  const frameStatsRef = useRef({ lastAt: performance.now(), lastSeq: 0 });

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
      alphaWs: wsUrl(live, '/alpha/ws')
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
    let fps = frameInfo.fps;
    if (elapsed >= 1000) {
      fps = ((frame.seq - stats.lastSeq) * 1000) / elapsed;
      stats.lastAt = now;
      stats.lastSeq = frame.seq;
    }
    setFrameInfo({ width: frame.width, height: frame.height, seq: frame.seq, fps });
  }, [addLog, frameInfo.fps]);

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
    socket.onmessage = (event) => drawFrame(event.data);
    socket.onerror = () => {
      setVideoState('error');
      addLog('alpha 视频流连接错误');
    };
    socket.onclose = (event) => {
      setVideoState('disconnected');
      addLog('alpha 视频流已断开', { code: event.code });
    };
  }, [addLog, drawFrame, normalized.alphaWs]);

  const disconnectVideo = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    setVideoState('disconnected');
  }, []);

  useEffect(() => () => disconnectVideo(), [disconnectVideo]);

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
            <span>Status: {status} {sessionId ? `| session ${sessionId}` : ''}</span>
          </div>
          <pre>{logs.join('\n')}</pre>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
