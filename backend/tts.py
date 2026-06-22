import os
import re
import uuid
import asyncio
import tempfile
import subprocess
from pathlib import Path


def _download_file(url: str, dst, label: str) -> None:
    """
    Download a file with progress. Uses aria2c if available (fast, multi-conn),
    falls back to urllib with a live progress bar.
    """
    import shutil, urllib.request as _ur
    dst = str(dst)

    # ── Try aria2c ────────────────────────────────────────────────────────────
    aria2 = shutil.which("aria2c")
    if aria2:
        import subprocess as _sp
        import os as _os
        out_dir  = _os.path.dirname(dst)
        out_name = _os.path.basename(dst)
        print(f"[TTS] {label}: downloading via aria2c...")
        proc = _sp.Popen(
            [
                aria2, url,
                f"--dir={out_dir}",
                f"--out={out_name}",
                "--split=8",
                "--max-connection-per-server=8",
                "--min-split-size=1M",
                "--console-log-level=notice",
                "--show-console-readout=true",
                "--summary-interval=1",
            ],
            stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True
        )
        for line in proc.stdout:
            line = line.rstrip()
            # aria2 progress lines contain "%" — print them in-place
            if "%" in line or "Download" in line or "ETA" in line:
                print(f"\r[TTS] {label}: {line.strip()}", end="", flush=True)
        proc.wait()
        print()  # newline after progress
        if proc.returncode == 0:
            return
        print(f"[TTS] aria2c failed (rc={proc.returncode}), falling back to urllib...")

    # ── urllib fallback with live % progress ──────────────────────────────────
    def _hook(block, block_size, total):
        if total <= 0:
            return
        done = min(block * block_size, total)
        pct  = done * 100 // total
        mb_done  = done / 1_048_576
        mb_total = total / 1_048_576
        bar_len  = 30
        filled   = int(bar_len * done / total)
        bar      = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[TTS] {label}: [{bar}] {pct:3d}%  {mb_done:.1f}/{mb_total:.1f} MB", end="", flush=True)

    print(f"[TTS] {label}: downloading...", flush=True)
    _ur.urlretrieve(url, dst, reporthook=_hook)
    print(f"\n[TTS] {label}: done.")


def _escape_ps(text: str) -> str:
    """Escape text for safe embedding in a PowerShell string."""
    text = text.replace("'", "").replace('"', "").replace("`", "").replace("\n", " ")
    return text[:800]


async def _edge_tts_async(text: str, out_path: str) -> bool:
    """Use Microsoft Edge neural TTS — en-GB-RyanNeural is a deep British male voice."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(
            text,
            voice="en-GB-RyanNeural",
            rate="-8%",
            pitch="-12Hz",
        )
        await communicate.save(out_path)
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except Exception as e:
        print(f"[TTS] edge-tts failed: {e}")
        return False


def tts_to_file(text: str) -> str | None:
    """
    Convert text to speech. Returns path to audio file.
    Priority:
      1. ElevenLabs (if ELEVENLABS_API_KEY set)
      2. Piper TTS - en_GB-alan-medium (offline, MALE British)
      3. Edge TTS  - en-GB-RyanNeural  (online, MALE British)
      4. PowerShell SAPI (George/Ryan voice)
      5. gTTS British (online, female - last resort)
      6. win32com SAPI
      7. pyttsx3
    """
    out_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
    out_dir.mkdir(exist_ok=True)

    # ── 1. ElevenLabs ────────────────────────────────────────────────────────
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=api_key)
            voice = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            audio = client.text_to_speech.convert(
                text=text, voice_id=voice, model_id="eleven_multilingual_v2"
            )
            out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
            with open(out_path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            print(f"[TTS] ElevenLabs → {out_path.name}")
            return str(out_path)
        except Exception as e:
            print(f"[TTS] ElevenLabs failed: {e}")

    # ── 2. Kokoro TTS — human-quality British male voice (bm_george) ────────────
    try:
        from kokoro_onnx import Kokoro
        import soundfile as _sf
        import numpy as _np
        _kokoro_dir = Path(os.getenv("APPDATA", ".")) / "jarvis" / "kokoro"
        _kokoro_dir.mkdir(parents=True, exist_ok=True)
        _model_path  = _kokoro_dir / "kokoro-v1.0.onnx"
        _voices_path = _kokoro_dir / "voices-v1.0.bin"
        if not _model_path.exists():
            _download_file(
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
                _model_path, "Kokoro model (~85 MB)"
            )
        if not _voices_path.exists():
            _download_file(
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
                _voices_path, "Kokoro voices (~80 MB)"
            )
        kokoro = Kokoro(str(_model_path), str(_voices_path))
        samples, rate = kokoro.create(text, voice="bm_george", speed=0.95, lang="en-gb")
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        _sf.write(str(out_path), samples, rate)
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] Kokoro (bm_george) → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] Kokoro failed: {e}")

    # ── 3. Piper TTS — offline MALE British voice (downloads model on first use) ─
    try:
        import wave, urllib.request
        from piper.voice import PiperVoice
        model_dir = Path(os.getenv("APPDATA", ".")) / "jarvis" / "piper_voices"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_file = model_dir / "en_GB-alan-medium.onnx"
        config_file = model_dir / "en_GB-alan-medium.onnx.json"
        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium"
        if not model_file.exists():
            print("[TTS] Piper: downloading en_GB-alan-medium model (~60MB)...")
            urllib.request.urlretrieve(f"{base_url}/en_GB-alan-medium.onnx", model_file)
            urllib.request.urlretrieve(f"{base_url}/en_GB-alan-medium.onnx.json", config_file)
            print("[TTS] Piper model downloaded.")
        voice = PiperVoice.load(str(model_file), config_path=str(config_file), use_cuda=False)
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        with wave.open(str(out_path), "wb") as wf:
            voice.synthesize(text, wf)
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] Piper (alan-GB) → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] Piper TTS failed: {e}")

    # ── 4. Edge TTS (RyanNeural — MALE British) ─────────────────────────────────
    try:
        out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
        ok = asyncio.run(_edge_tts_async(text, str(out_path)))
        if ok:
            print(f"[TTS] Edge TTS (RyanNeural) → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] Edge TTS error: {e}")

    # ── 5. PowerShell SAPI (no Python deps needed) ───────────────────────────
    try:
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        safe_text = _escape_ps(text)
        safe_out  = str(out_path).replace("\\", "\\\\")

        # Try British male voices first (George = classic JARVIS accent)
        # Falls back to David/Zira if no British voice is installed
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$preferred = @('George','Ryan','James'); "
            "foreach ($p in $preferred) { "
            "    $v = ($s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -like \"*$p*\" } | Select-Object -First 1); "
            "    if ($v) { $s.SelectVoice($v.VoiceInfo.Name); break } "
            "}; "
            "$s.Rate = -3; "
            f"$s.SetOutputToWaveFile('{safe_out}'); "
            f"$s.Speak('{safe_text}'); "
            "$s.Dispose()"
        )

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] PowerShell SAPI → {out_path.name}")
            return str(out_path)
        else:
            print(f"[TTS] PowerShell SAPI failed (rc={result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"[TTS] PowerShell SAPI error: {e}")

    # ── 6. gTTS — British accent (online, female — last resort) ─────────────────
    try:
        from gtts import gTTS as _gTTS
        out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
        _gTTS(text=text, lang="en", tld="co.uk", slow=False).save(str(out_path))
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] gTTS British (female fallback) → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] gTTS failed: {e}")

    # ── 7. win32com SAPI ─────────────────────────────────────────────────────
    try:
        import win32com.client
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        # Try British male voices
        for voice in speaker.GetVoices():
            if any(n in voice.GetDescription() for n in ('George', 'Ryan', 'James')):
                speaker.Voice = voice
                break
        speaker.Rate = -3
        file_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        file_stream.Open(str(out_path), 3)
        speaker.AudioOutputStream = file_stream
        speaker.Speak(text)
        file_stream.Close()
        print(f"[TTS] win32com SAPI → {out_path.name}")
        return str(out_path)
    except Exception as e:
        print(f"[TTS] win32com SAPI failed: {e}")

    # ── 8. pyttsx3 ───────────────────────────────────────────────────────────
    try:
        import pyttsx3
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        engine = pyttsx3.init()
        rate = engine.getProperty('rate')
        engine.setProperty('rate', max(120, rate - 40))
        voices = engine.getProperty('voices') or []
        male = [v for v in voices if any(n in v.name.lower() for n in ('male','david','mark','james'))]
        if male:
            engine.setProperty('voice', male[0].id)
        elif voices:
            engine.setProperty('voice', voices[0].id)
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
        engine.stop()
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] pyttsx3 → {out_path.name}")
            return str(out_path)
        print("[TTS] pyttsx3 produced empty file")
    except Exception as e:
        print(f"[TTS] pyttsx3 failed: {e}")

    print("[TTS] All engines failed — no audio")
    return None
