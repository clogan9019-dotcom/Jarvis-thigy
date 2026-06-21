import os
import re
import uuid
import tempfile
import subprocess
from pathlib import Path


def _apply_jarvis_effect(wav_path: str) -> str:
    """Post-process WAV: reverb + high-freq boost for the JARVIS metallic sound."""
    try:
        import numpy as np
        from scipy.io import wavfile
        from scipy.signal import lfilter

        rate, data = wavfile.read(wav_path)

        if data.dtype == np.int16:
            samples = data.astype(np.float64) / 32768.0
        elif data.dtype == np.int32:
            samples = data.astype(np.float64) / 2147483648.0
        else:
            samples = data.astype(np.float64)

        mono = samples if samples.ndim == 1 else samples[:, 0]

        # High-frequency crisp/digital edge
        b_shelf = np.array([1.3, -0.3])
        mono = lfilter(b_shelf, [1.0], mono)

        # Short room echo
        d1 = int(rate * 0.038)
        rev = np.zeros_like(mono)
        rev[d1:] = mono[:-d1] * 0.22
        mono = mono + rev

        # Softer second echo for depth
        d2 = int(rate * 0.072)
        rev2 = np.zeros_like(mono)
        rev2[d2:] = mono[:-d2] * 0.10
        mono = mono + rev2

        peak = np.max(np.abs(mono))
        if peak > 0:
            mono = mono / peak * 0.92

        wavfile.write(wav_path, rate, (mono * 32767).astype(np.int16))
        print("[TTS] JARVIS voice effect applied")
    except Exception as e:
        print(f"[TTS] Voice effect skipped: {e}")
    return wav_path


def _escape_ps(text: str) -> str:
    """Escape text for safe embedding in a PowerShell string."""
    # Remove characters that break PS string literals
    text = text.replace("'", "").replace('"', "").replace("`", "").replace("\n", " ")
    return text[:800]  # cap length to avoid CLI arg limits


def tts_to_file(text: str) -> str | None:
    """
    Convert text to speech. Returns path to audio file.
    Priority:
      1. ElevenLabs (if ELEVENLABS_API_KEY set)
      2. Windows SAPI via PowerShell (no extra deps, always works on Windows)
      3. Windows SAPI via pywin32 (fallback if PS fails)
      4. pyttsx3
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

    # ── 2. PowerShell SAPI (no Python deps needed) ───────────────────────────
    try:
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        safe_text = _escape_ps(text)
        safe_out  = str(out_path).replace("\\", "\\\\")

        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = -2; "
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
            _apply_jarvis_effect(str(out_path))
            return str(out_path)
        else:
            print(f"[TTS] PowerShell SAPI failed (rc={result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"[TTS] PowerShell SAPI error: {e}")

    # ── 3. win32com SAPI ─────────────────────────────────────────────────────
    try:
        import win32com.client
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = -2
        file_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        file_stream.Open(str(out_path), 3)
        speaker.AudioOutputStream = file_stream
        speaker.Speak(text)
        file_stream.Close()
        print(f"[TTS] win32com SAPI → {out_path.name}")
        _apply_jarvis_effect(str(out_path))
        return str(out_path)
    except Exception as e:
        print(f"[TTS] win32com SAPI failed: {e}")

    # ── 4. pyttsx3 ───────────────────────────────────────────────────────────
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
            _apply_jarvis_effect(str(out_path))
            return str(out_path)
        print("[TTS] pyttsx3 produced empty file")
    except Exception as e:
        print(f"[TTS] pyttsx3 failed: {e}")

    print("[TTS] All engines failed — no audio")
    return None
