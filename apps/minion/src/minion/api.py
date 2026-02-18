import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from minion.events import Event, EventDispatcher

logger = logging.getLogger(__name__)

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Minion Chat</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #eee; height: 100vh; display: flex; flex-direction: column; }
  #header { padding: 12px 16px; background: #16213e; border-bottom: 1px solid #0f3460; font-weight: 600; }
  #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; }
  .msg.user { align-self: flex-end; background: #0f3460; }
  .msg.agent { align-self: flex-start; background: #16213e; }
  .msg.system { align-self: center; color: #888; font-size: 0.85em; }
  #input-area { padding: 12px 16px; background: #16213e; border-top: 1px solid #0f3460; display: flex; gap: 8px; }
  #input { flex: 1; padding: 10px 14px; border: 1px solid #0f3460; border-radius: 8px; background: #1a1a2e; color: #eee; font-size: 1em; outline: none; }
  #input:focus { border-color: #e94560; }
  #send { padding: 10px 20px; background: #e94560; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 1em; }
  #send:hover { background: #c73e54; }
  #send:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
</head>
<body>
<div id="header">Minion Chat</div>
<div id="messages"></div>
<div id="input-area">
  <input id="input" type="text" placeholder="Type a message..." autocomplete="off">
  <button id="send">Send</button>
</div>
<script>
const msgs = document.getElementById('messages');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
let ws;

function addMsg(text, cls) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/ws');
  ws.onopen = () => addMsg('Connected', 'system');
  ws.onclose = () => { addMsg('Disconnected. Reconnecting...', 'system'); setTimeout(connect, 3000); };
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      addMsg(data.content || e.data, 'agent');
    } catch { addMsg(e.data, 'agent'); }
  };
}

function send() {
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  addMsg(text, 'user');
  ws.send(JSON.stringify({content: text, sender: 'user'}));
  input.value = '';
}

sendBtn.onclick = send;
input.onkeydown = (e) => { if (e.key === 'Enter') send(); };
connect();
</script>
</body>
</html>"""


class ChatRequest(BaseModel):
    content: str
    sender: str = "user"


def create_app(dispatcher: EventDispatcher) -> FastAPI:
    app = FastAPI(title="Minion Agent", docs_url=None, redoc_url=None)
    websockets: list[WebSocket] = []

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/")
    async def chat_page() -> HTMLResponse:
        return HTMLResponse(CHAT_HTML)

    @app.post("/chat")
    async def chat(req: ChatRequest) -> JSONResponse:
        event = Event(type="chat", source="api", payload=req.model_dump())
        response = await dispatcher.dispatch(event)
        return JSONResponse({"response": response})

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        websockets.append(ws)
        logger.info("WebSocket client connected (%d total)", len(websockets))
        try:
            while True:
                data = await ws.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {"content": data, "sender": "user"}

                event = Event(type="chat", source="websocket", payload=payload)
                response = await dispatcher.dispatch(event)
                if response:
                    await ws.send_text(json.dumps({"content": response, "sender": "agent"}))
        except WebSocketDisconnect:
            pass
        finally:
            websockets.remove(ws)
            logger.info("WebSocket client disconnected (%d remaining)", len(websockets))

    return app
