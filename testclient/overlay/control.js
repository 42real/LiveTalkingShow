const serverInput = document.getElementById('server');
const sessionInput = document.getElementById('sessionid');
const textInput = document.getElementById('text');
const statusEl = document.getElementById('status');

function setStatus(message) {
  statusEl.textContent = message;
}

function syncServer(server) {
  if (window.overlayApi?.setServer) {
    window.overlayApi.setServer(server);
  }
}

async function closeCurrentSession() {
  const sessionid = sessionInput.value;
  if (!sessionid) return;
  sessionInput.value = '';
  try {
    await fetch(`${serverInput.value}/close_session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionid }),
      keepalive: true
    });
  } catch (_) {
    // best effort
  }
}

async function connectSession() {
  await closeCurrentSession();
  const resp = await fetch(`${serverInput.value}/alpha/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });
  const payload = await resp.json();
  if (!resp.ok || payload.code !== 0) {
    throw new Error(payload.msg || '创建 alpha session 失败');
  }
  sessionInput.value = String(payload.data.sessionid);
  setStatus(`已连接 alpha session ${payload.data.sessionid}`);
}

async function speak() {
  if (!sessionInput.value) {
    await connectSession();
  }
  const body = {
    sessionid: sessionInput.value,
    type: 'echo',
    text: textInput.value,
    interrupt: true
  };
  const resp = await fetch(`${serverInput.value}/human`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  setStatus(resp.ok ? '已发送朗读' : '发送失败');
}

document.getElementById('connect').addEventListener('click', () => {
  connectSession().catch((err) => setStatus(err.message));
});
document.getElementById('speak').addEventListener('click', () => {
  speak().catch((err) => setStatus(err.message));
});
const closeButton = document.getElementById('close');
if (closeButton) {
  closeButton.addEventListener('click', async () => {
    await closeCurrentSession();
    window.close();
  });
}

serverInput.addEventListener('change', () => {
  syncServer(serverInput.value);
  closeCurrentSession();
  setStatus('服务器已切换');
});

window.addEventListener('beforeunload', () => {
  closeCurrentSession();
});

syncServer(serverInput.value);
