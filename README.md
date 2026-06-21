# J.A.R.V.I.S — Windows Desktop

Iron Man-style AI assistant for Windows.

**GUI:** Frameless Electron HUD — glowing cyan orb, HUD rings, live waveform, streaming transcript. Windows 11 Mica / acrylic.

**Backend:** Python FastAPI
- STT: faster-whisper (local)
- LLM: OpenAI GPT-4o with function calling • Ollama fallback (qwen2.5 / llama3.1)
- TTS: ElevenLabs • System SAPI fallback
- Tools: screen_vision, computer_control, file_terminal, web_search, memory_rag
- Memory: ChromaDB RAG, persistent

---

## Quick Start (dev)

### 1. Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# copy .env.example -> .env and add keys
copy .env.example .env

python main.py
# -> http://127.0.0.1:8765
```

`.env` keys (all optional, there are fallbacks):
```
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
BRAVE_SEARCH_API_KEY=...
JARVIS_LLM=openai   # or ollama
OLLAMA_MODEL=qwen2.5:7b
```

No keys? It still runs: Ollama for LLM, system SAPI for TTS.

### 2. Frontend
```powershell
cd app
npm install
npm run dev
```
Electron window launches with Vite HMR.

---

## Build JarvisSetup.exe

Locally:
```powershell
cd app
npm run build:win
# -> app/dist/JarvisSetup-0.1.0.exe
```

Via GitHub Actions:
1. Push this repo to https://github.com/clogan9019-dotcom/Jarvis-thigy
2. Tag a release:
   ```
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. Actions → "Build Windows EXE" runs, uploads `JarvisSetup.exe` to the Release.

See `.github/workflows/build-windows.yml`

---

## Repo push commands

First time:
```powershell
cd jarvis-windows
git init
git add .
git commit -m "Jarvis Windows v0.1"
git branch -M main
git remote add origin https://github.com/clogan9019-dotcom/Jarvis-thigy.git
git push -u origin main
```
Authenticate with `gh auth login` or Git Credential Manager — do NOT paste a PAT in chat.

---

## Features

- Wake word "Hey Jarvis" + push-to-talk (Space)
- Streaming LLM responses with function calling
- Screen vision: "What's on my screen?"
- Computer control: open apps, click/type
- File / terminal tools
- Web search (Brave API, fallback DuckDuckGo)
- Long-term memory: ChromaDB RAG
- Interruptible TTS (Esc)
- System tray, always-on-top toggle

## Config

Settings are in `%APPDATA%/jarvis/config.json`, or edit `backend/.env`.

---

MIT
