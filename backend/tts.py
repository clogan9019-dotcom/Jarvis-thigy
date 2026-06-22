import os
import re
import uuid
import asyncio
import tempfile
import subprocess
from pathlib import Path


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

    # ── 2. Piper TTS — offline MALE British voice (downloads model on first use) ─
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

    # ── 3. Edge TTS (RyanNeural — MALE British) ─────────────────────────────────
    try:
        out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
        ok = asyncio.run(_edge_tts_async(text, str(out_path)))
        if ok:
            print(f"[TTS] Edge TTS (RyanNeural) → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] Edge TTS error: {e}")

    # ── 4. PowerShell SAPI (no Python deps needed) ───────────────────────────
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

    # ── 5. gTTS — British accent (online, female — last resort) ─────────────────
    try:
        from gtts import gTTS as _gTTS
        out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
        _gTTS(text=text, lang="en", tld="co.uk", slow=False).save(str(out_path))
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] gTTS British (female fallback) → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] gTTS failed: {e}")

    # ── 6. win32com SAPI ─────────────────────────────────────────────────────
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

    # ── 7. pyttsx3 ───────────────────────────────────────────────────────────
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
