"""
J.A.R.V.I.S Backend - Purely Local (No API Keys Required!)
FastAPI server with WebSocket support
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

# Serve TTS audio files so the frontend can play them via HTTP
_tts_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
_tts_dir.mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(_tts_dir)), name="audio")

agent = JarvisAgent()

# ── PTT recording state (one active session at a time) ───────────────────────
_rec: dict = {"active": False, "chunks": [], "stream": None}

# ============ MODELS ============
class ChatIn(BaseModel):
    message: str
    stream: bool = True

class TTSIn(BaseModel):
    text: str

# ============ HEALTH ============

@app.get("/")
def root():
    return {
        "ok": True,
        "name": "J.A.R.V.I.S Backend",
        "mode": "LOCAL_ONLY",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "chat": "/chat",
            "websocket": "/ws",
            "memory": "/memory",
            "greeting": "/greeting"
        }
    }

@app.get("/health")
def health():
    import httpx
    ollama_ok = False
    ollama_model = os.getenv("OLLAMA_MODEL", "unknown")
    try:
        resp = httpx.get(f"{os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')}/api/tags", timeout=5)
        models = resp.json().get("models", [])
        ollama_ok = True
    except Exception:
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
        "config": {
            "ollama_host": os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            "ollama_model": os.getenv("OLLAMA_MODEL"),
            "whisper_model": os.getenv("WHISPER_MODEL", "base")
        }
    }

# ============ CHAT ============
@app.post("/chat")
async def chat(inp: ChatIn):
    result = await agent.chat(inp.message)
    return result

# ============ TTS ============
@app.post("/tts")
async def tts(inp: TTSIn):
    """Convert text to speech. Runs in thread so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    audio_path = await loop.run_in_executor(None, tts_to_file, inp.text)
    if audio_path and os.path.exists(audio_path):
        filename = Path(audio_path).name
        return {"ok": True, "audio_path": audio_path, "audio_url": f"/audio/{filename}"}
    return {"ok": False, "error": "All TTS engines failed — check backend logs"}

# ============ STT ============
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    temp_dir = Path(os.getenv("TEMP", tempfile.gettempdir())) / "jarvis_stt"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"upload_{os.urandom(8).hex()}.wav"

    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, transcribe_audio, str(temp_path))

    try:
        os.remove(temp_path)
    except Exception:
        pass

    return result

@app.post("/transcribe_mic")
async def transcribe_mic_http(duration: float = Form(5.0)):
    """HTTP fallback for mic transcription."""
    import functools
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, functools.partial(transcribe_microphone, duration))
    return result

# ============ WEBSOCKET ============
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

                # Generate TTS in a thread so the event loop stays free
                if full.strip():
                    await ws.send_text(json.dumps({"type": "tts_start"}))
                    loop = asyncio.get_event_loop()
                    audio_path = await loop.run_in_executor(None, tts_to_file, full)
                    if audio_path and os.path.exists(audio_path):
                        await ws.send_text(json.dumps({"type": "tts", "path": audio_path}))

            elif data.get("type") == "interrupt":
                await ws.send_text(json.dumps({"type": "interrupted"}))

            elif data.get("type") == "transcribe_mic_start":
                # Start streaming mic capture (non-blocking InputStream callback)
                try:
                    import sounddevice as sd
                    # Stop any leftover stream
                    if _rec.get("stream"):
                        try:
                            _rec["stream"].stop()
                            _rec["stream"].close()
                        except Exception:
                            pass
                    _rec["active"] = True
                    _rec["chunks"] = []

                    # Query the mic's native sample rate — many Windows mics
                    # only support 44100 or 48000 Hz, NOT 16000, causing silence
                    try:
                        dev_info = sd.query_devices(kind="input")
                        native_sr = int(dev_info.get("default_samplerate", 16000))
                    except Exception:
                        native_sr = 16000
                    _rec["sample_rate"] = native_sr

                    def _audio_cb(indata, frames, time_info, status):
                        if status:
                            print(f"[STT] Stream status: {status}")
                        if _rec["active"]:
                            _rec["chunks"].append(indata.copy())

                    stream = sd.InputStream(
                        samplerate=native_sr, channels=1,
                        dtype="float32", callback=_audio_cb
                    )
                    stream.start()
                    _rec["stream"] = stream
                    print(f"[STT] PTT recording started… (mic={native_sr}Hz)")
                except Exception as e:
                    await ws.send_text(json.dumps({
                        "type": "stt_result", "ok": False,
                        "error": f"Could not open mic: {e}"
                    }))

            elif data.get("type") == "transcribe_mic_stop":
                # Stop capture, save WAV, transcribe in thread
                import numpy as np
                from scipy.io import wavfile as scipy_wavfile
                from scipy.signal import resample as scipy_resample
                import time as _time

                _rec["active"] = False
                stream = _rec.get("stream")
                native_sr = _rec.get("sample_rate", 16000)
                _rec["stream"] = None
                if stream:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass

                chunks = _rec["chunks"]
                _rec["chunks"] = []

                if not chunks:
                    await ws.send_text(json.dumps({
                        "type": "stt_result", "ok": False, "error": "No audio recorded"
                    }))
                else:
                    audio = np.concatenate(chunks, axis=0).flatten()
                    duration_s = len(audio) / native_sr
                    rms = float(np.sqrt(np.mean(audio ** 2)))
                    print(f"[STT] PTT stopped — {duration_s:.1f}s | RMS={rms:.4f}")

                    # Resample to 16000 Hz for Whisper if mic used different rate
                    if native_sr != 16000:
                        target_len = int(len(audio) * 16000 / native_sr)
                        audio = scipy_resample(audio, target_len).astype(np.float32)
                        print(f"[STT] Resampled {native_sr}Hz → 16000Hz")

                    # Too quiet — mic not picking up audio at all
                    if rms < 0.001:
                        print("[STT] Audio is silent — mic may not be capturing")
                        await ws.send_text(json.dumps({
                            "type": "stt_result", "ok": False,
                            "error": "Mic too quiet — open Windows Sound Settings → Recording tab → right-click your mic → Set as Default Device"
                        }))
                    # Too short — released Space before speaking
                    elif duration_s < 0.4:
                        await ws.send_text(json.dumps({
                            "type": "stt_result", "ok": False,
                            "error": "Hold Space while you speak, then release"
                        }))
                    else:
                        stt_dir = Path(tempfile.gettempdir()) / "jarvis_stt"
                        stt_dir.mkdir(parents=True, exist_ok=True)
                        tmp_wav = stt_dir / f"ptt_{int(_time.time())}.wav"
                        scipy_wavfile.write(str(tmp_wav), 16000,
                                            (audio * 32767).astype(np.int16))

                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, transcribe_audio, str(tmp_wav)
                        )
                        print(f"[STT] Result: ok={result.get('ok')}, text={repr(result.get('text','')[:60])}")
                        await ws.send_text(json.dumps({"type": "stt_result", **result}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Error: {e}")

# ============ MEMORY ============
@app.get("/memory")
async def memory_search(q: str = "", k: int = 5):
    from tools.memory_rag import memory_search as search
    results = search(q, k)
    return {"ok": True, "results": results}

@app.post("/memory")
async def memory_add(text: str = ""):
    from tools.memory_rag import memory_add
    result = memory_add(text)
    return result

# ============ GREETING ============
@app.get("/greeting")
async def greeting():
    """Personalised JARVIS startup greeting using long-term memory + Ollama."""
    from datetime import datetime
    from tools.memory_rag import memory_search as search
    import functools

    hour = datetime.now().hour
    if hour < 5:
        period = "the early hours"
    elif hour < 12:
        period = "morning"
    elif hour < 17:
        period = "afternoon"
    elif hour < 21:
        period = "evening"
    else:
        period = "night"

    # Run memory search in thread (ChromaDB is sync)
    loop = asyncio.get_event_loop()
    memories = await loop.run_in_executor(
        None, functools.partial(search, "user name preferences habits projects work", 12)
    )
    mem_lines = [m["text"] for m in memories if m.get("text")]
    mem_block = "\n".join(f"- {l}" for l in mem_lines) if mem_lines else \
        "(no memories yet — first session)"

    prompt = f"""You are J.A.R.V.I.S., Tony Stark's AI assistant.
Generate a single personalised greeting. It is currently {period}.

Facts about the user:
{mem_block}

Rules:
- 1-2 sentences only
- Do NOT start with "Good {period}"
- Reference something personal if memory has it
- Classic JARVIS tone: formal, slightly witty
- Output ONLY the greeting, nothing else."""

    import httpx
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    greeting_text = ""
    try:
        resp = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: httpx.post(
                    f"{host}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.7, "num_predict": 80}},
                    timeout=15
                )
            ),
            timeout=18
        )
        greeting_text = resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[Greeting] Ollama error: {e}")

    if not greeting_text:
        fallbacks = {
            "the early hours": "Running diagnostics at this ungodly hour, I see. All systems online — at your disposal.",
            "morning":   "Systems nominal and ready for the day. Whenever you are, so am I.",
            "afternoon": "All systems nominal. A productive afternoon awaits — what shall we tackle?",
            "evening":   "Evening protocols engaged. Systems running smoothly — I'm here when you need me.",
            "night":     "Burning the midnight oil again? All systems online. Let's make it count.",
        }
        greeting_text = fallbacks.get(period, "Neural interface online. Always at your service.")

    print(f"[Greeting] {period}: {greeting_text[:80]}")
    return {"ok": True, "greeting": greeting_text, "period": period, "memories": len(mem_lines)}

# ============ MAIN ============
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("JARVIS_PORT", "8765"))
    host = os.getenv("JARVIS_HOST", "127.0.0.1")

    print("╔══════════════════════════════════════════════════════════╗")
    print("║           J.A.R.V.I.S Backend - LOCAL MODE               ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"🚀 Starting at http://{host}:{port}")
    print(f"📋 Health check: http://{host}:{port}/health")
    print(f"🔌 WebSocket: ws://{host}:{port}/ws")
    print()

    uvicorn.run("main:app", host=host, port=port, reload=False)
