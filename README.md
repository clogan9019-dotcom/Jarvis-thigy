# J.A.R.V.I.S — Windows Desktop AI Assistant

**Iron Man-style AI assistant - 100% LOCAL, no API keys required!**

<img src="https://img.shields.io/badge/LLM-Ollama-brightgreen" />
<img src="https://img.shields.io/badge/STT-faster--whisper-blue" />
<img src="https://img.shields.io/badge/TTS-Windows%20SAPI-green" />
<img src="https://img.shields.io/badge/Search-DuckDuckGo-orange" />

---

## 🎯 What is J.A.R.V.I.S?

A fully local AI desktop assistant inspired by Tony Stark's JARVIS. No cloud services, no API keys, your data stays on your machine.

### GUI
Frameless Electron HUD — glowing cyan orb, HUD rings, live waveform, streaming transcript. Windows 11 Mica / acrylic.

### Backend
Python FastAPI — **completely local**

| Component | Local Solution |
|-----------|----------------|
| **LLM** | Ollama (qwen2.5-coder, llama3.2, etc.) |
| **STT** | faster-whisper (local transcription) |
| **TTS** | Windows SAPI (built into Windows) |
| **Memory** | ChromaDB (local vector database) |
| **Search** | DuckDuckGo (free, no API key) |
| **Vision** | Ollama vision model (llava) |

### Tools
- 👁️ **screen_vision** - Screenshot + AI analysis
- ⌨️ **computer_control** - Open apps, type, click, hotkeys
- 📁 **file_terminal** - Read/write files, run commands
- 🌐 **web_search** - DuckDuckGo (no key needed!)
- 🔬 **deep_research** - Autonomous research agent
- 💾 **memory_rag** - ChromaDB persistent memory

---

## 🚀 Quick Start

### 1. Install Ollama

Download from https://ollama.com and install.

Then pull your model:
```powershell
ollama pull qwen2.5-coder-14b-instruct-abliterated:latest
```
Or use any model you prefer:
```powershell
ollama pull llama3.2
```

Start Ollama (keep running):
```powershell
ollama serve
```

### 2. Backend Setup

```powershell
cd backend

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure
copy .env.example .env

# Run backend
python main.py
```

You should see:
```
╔══════════════════════════════════════════════════════════╗
║           J.A.R.V.I.S Backend - LOCAL MODE               ║
╚══════════════════════════════════════════════════════════╝

🚀 Starting at http://127.0.0.1:8765
✅ Ollama for LLM
✅ Windows SAPI for TTS
✅ ChromaDB for memory
✅ DuckDuckGo for web search
```

### 3. Frontend Setup

```powershell
cd app
npm install
npm run dev
```

Electron window launches with Vite HMR.

---

## 📋 .env Configuration

```env
# OLLAMA (Required)
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder-14b-instruct-abliterated:latest
OLLAMA_VISION_MODEL=llava:latest

# TTS (Optional - Windows SAPI works automatically)
# ELEVENLABS_API_KEY=  # Not needed!

# STT (Optional - faster-whisper runs locally)
WHISPER_MODEL=base

# Search (Optional - DuckDuckGo is free!)
# BRAVE_SEARCH_API_KEY=  # Not needed!

# Server
JARVIS_PORT=8765
JARVIS_HOST=127.0.0.1
```

---

## 🎮 Features

| Command | What it does |
|---------|--------------|
| `/ask <question>` | Chat with AI |
| `analyze_screen` | Take screenshot and describe |
| `deep_research` | Autonomous research on any topic |
| `open_app <name>` | Open Windows application |
| `memory_add <fact>` | Remember something |
| `web_search <query>` | Search the web |
| `run_cmd <command>` | Execute shell command |

### Keyboard Shortcuts (in GUI)
- **Space** - Push to talk
- **Esc** - Interrupt
- **Tab** - Toggle HUD
- **`** - Toggle dock

---

## 🔧 Optional Enhancements

### GPU Acceleration (for faster STT)
```powershell
pip install torch
```

### Screen Vision (AI analysis)
```powershell
ollama pull llava
```

### Larger Whisper Model
```powershell
# Better accuracy, slower
WHISPER_MODEL=medium
```

---

## 📦 Build Windows EXE

```powershell
cd app
npm run build:win
# -> app/dist/JarvisSetup-0.1.0.exe
```

Or via GitHub Actions:
```powershell
git tag v0.1.0
git push origin v0.1.0
```

---

## ❓ Troubleshooting

### "Ollama not responding"
```powershell
ollama serve
# Keep this running!
```

### "STT not working"
```powershell
pip install faster-whisper sounddevice scipy
```

### "TTS not working"
Windows SAPI should work automatically. If not:
```powershell
pip install pywin32
```

### "Web search failing"
```powershell
pip install duckduckgo-search
```

---

## 📁 Project Structure

```
Jarvis-thigy/
├── app/                    # Electron + React frontend
│   ├── electron/          # Main process
│   └── src/               # React components
├── backend/               # Python FastAPI backend
│   ├── tools/             # Tool implementations
│   ├── main.py            # API server
│   ├── llm_agent.py       # Ollama agent
│   ├── stt.py             # Whisper STT
│   ├── tts.py             # Windows SAPI TTS
│   └── requirements.txt   # Python dependencies
├── README.md
└── index.html
```

---

**No API keys. No cloud. 100% local.**

*MIT License*