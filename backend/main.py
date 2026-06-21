"""
J.A.R.V.I.S Backend - Purely Local (No API Keys Required!)
FastAPI server with WebSocket support
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from llm_agent import JarvisAgent
from stt import transcribe_audio, transcribe_microphone
from tts import tts_to_file

load_dotenv()

app = FastAPI(title="J.A.R.V.I.S Backend - LOCAL ONLY")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

agent = JarvisAgent()

# ============ MODELS ============
class ChatIn(BaseModel):
    message: str
    stream: bool = True

class TTSIn(BaseModel):
    text: str

# ============ HEALTH ============

@app.get("/")
def root():
    """Landing endpoint for browsers hitting the backend base URL."""
    return {
        "ok": True,
        "name": "J.A.R.V.I.S Backend",
        "mode": "LOCAL_ONLY",
        "message": "Backend is running. Use the app UI or one of the API endpoints below.",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "chat": "/chat",
            "websocket": "/ws",
            "memory": "/memory"
        }
    }

@app.get("/health")
def health():
    """Check backend health and capabilities"""
    import httpx
    
    # Check Ollama
    ollama_ok = False
    ollama_model = os.getenv("OLLAMA_MODEL", "unknown")
    try:
        resp = httpx.get(f"{os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')}/api/tags", timeout=5)
        models = resp.json().get("models", [])
        ollama_ok = True
    except:
        models = []
    
    return {
        "ok": True,
        "status": "online",
        "mode": "LOCAL_ONLY",
        "ollama": {
            "connected": ollama_ok,
            "model": ollama_model,
            "available_models": [m.get("name", "unknown") for m in models[:5]]
        },
        "features": {
            "llm": "✅ Ollama",
            "stt": "⚠️ faster-whisper (needs setup)",
            "tts": "✅ Windows SAPI",
            "memory": "✅ ChromaDB",
            "web_search": "✅ DuckDuckGo (free)",
            "deep_research": "✅ Ollama + DuckDuckGo",
            "screen_vision": "⚠️ Ollama vision model (needs llava)"
        },
        "config": {
            "ollama_host": os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            "ollama_model": os.getenv("OLLAMA_MODEL"),
            "whisper_model": os.getenv("WHISPER_MODEL", "base")
        }
    }

# ============ CHAT ============
@app.post("/chat")
async def chat(inp: ChatIn):
    """Non-streaming chat"""
    result = await agent.chat(inp.message)
    return result

# ============ TTS ============
@app.post("/tts")
async def tts(inp: TTSIn):
    """Convert text to speech (local TTS)"""
    audio_path = tts_to_file(inp.text)
    if audio_path and os.path.exists(audio_path):
        return {"ok": True, "audio_path": audio_path}
    return {"ok": False, "error": "TTS failed - Windows SAPI not available?"}

# ============ STT ============
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Transcribe uploaded audio file (local Whisper)"""
    # Save uploaded file
    temp_dir = Path(os.getenv("TEMP", "/tmp")) / "jarvis_stt"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"upload_{os.urandom(8).hex()}.wav"
    
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    result = transcribe_audio(str(temp_path))
    
    # Cleanup
    try:
        os.remove(temp_path)
    except:
        pass
    
    return result

@app.post("/transcribe_mic")
async def transcribe_mic(duration: float = Form(5.0)):
    """Record and transcribe from microphone"""
    return transcribe_microphone(duration)

# ============ WEBSOCKET ============
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket for streaming chat + voice"""
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
                    
                    # Allow interruption
                    try:
                        await ws.send_text(json.dumps({"type": "keepalive"}))
                    except:
                        pass
                
                # TTS (local Windows SAPI)
                if full.strip():
                    await ws.send_text(json.dumps({"type": "tts_start"}))
                    audio_path = tts_to_file(full)
                    if audio_path and os.path.exists(audio_path):
                        await ws.send_text(json.dumps({"type": "tts", "path": audio_path}))
            
            elif data.get("type") == "interrupt":
                # User wants to stop current response
                await ws.send_text(json.dumps({"type": "interrupted"}))
            
            elif data.get("type") == "transcribe_mic":
                # Microphone transcription
                duration = data.get("duration", 5.0)
                result = transcribe_microphone(duration)
                await ws.send_text(json.dumps({"type": "stt_result", **result}))
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Error: {e}")

# ============ MEMORY ============
@app.get("/memory")
async def memory_search(q: str = "", k: int = 5):
    """Search memory"""
    from tools.memory_rag import memory_search as search
    results = search(q, k)
    return {"ok": True, "results": results}

@app.post("/memory")
async def memory_add(text: str = ""):
    """Add to memory"""
    from tools.memory_rag import memory_add
    result = memory_add(text)
    return result

# ============ MAIN ============
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("JARVIS_PORT", "8765"))
    host = os.getenv("JARVIS_HOST", "127.0.0.1")
    
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           J.A.R.V.I.S Backend - LOCAL MODE               ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("")
    print(f"🚀 Starting at http://{host}:{port}")
    print(f"📋 Health check: http://{host}:{port}/health")
    print(f"🔌 WebSocket: ws://{host}:{port}/ws")
    print("")
    print("✅ Ollama for LLM")
    print("⚠️  faster-whisper for STT (needs setup)")
    print("✅ Windows SAPI for TTS")
    print("✅ ChromaDB for memory")
    print("✅ DuckDuckGo for web search")
    print("✅ Ollama for deep research")
    print("")
    
    uvicorn.run("main:app", host=host, port=port, reload=False)