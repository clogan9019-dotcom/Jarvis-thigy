import asyncio
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from llm_agent import JarvisAgent
from stt import transcribe_file
from tts import tts_to_file

load_dotenv()

app = FastAPI(title="Jarvis Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

agent = JarvisAgent()

class ChatIn(BaseModel):
    message: str
    stream: bool = True

@app.get("/health")
def health():
    return {"ok": True, "llm": agent.llm_backend}

@app.post("/chat")
async def chat(inp: ChatIn):
    result = await agent.chat(inp.message)
    return result

@app.post("/transcribe")
async def transcribe_audio():
    # For future: upload endpoint
    return {"text": ""}

# --- WebSocket for streaming chat + voice ---
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if data.get("type") == "chat":
                user_text = data.get("text", "")
                await ws.send_text(json.dumps({"type": "status", "text": "thinking"}))
                full = ""
                async for chunk in agent.stream_chat(user_text):
                    ctype = chunk.get("type")
                    if ctype == "delta":
                        full += chunk["text"]
                        await ws.send_text(json.dumps(chunk))
                    elif ctype in ("tool", "research_progress", "done"):
                        await ws.send_text(json.dumps(chunk))

                # TTS
                if full.strip():
                    await ws.send_text(json.dumps({"type": "tts_start"}))
                    audio_path = tts_to_file(full)
                    if audio_path and os.path.exists(audio_path):
                        await ws.send_text(json.dumps({"type": "tts", "path": audio_path}))
            elif data.get("type") == "interrupt":
                pass
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("JARVIS_PORT", "8765"))
    host = os.getenv("JARVIS_HOST", "127.0.0.1")
    uvicorn.run("main:app", host=host, port=port, reload=False)
