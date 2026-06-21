import os
import re
import uuid
import asyncio
import tempfile
import subprocess
from pathlib import Path


def _apply_jarvis_effect(wav_path: str) -> str:
    """Post-process WAV: metallic high-freq boost + reverb for the JARVIS sound."""
    try:
        import numpy as np
        from scipy.io import wavfile
        from scipy.signal import lfilter, butter, sosfilt

        rate, data = wavfile.read(wav_path)

        if data.dtype == np.int16:
            samples = data.astype(np.float64) / 32768.0
        elif data.dtype == np.int32:
            samples = data.astype(np.float64) / 2147483648.0
        else:
            samples = data.astype(np.float64)

        mono = samples if samples.ndim == 1 else samples[:, 0]

        # Strong high-frequency metallic/digital edge
        b_shelf = np.array([1.5, -0.5])
        mono = lfilter(b_shelf, [1.0], mono)

        # Subtle high-pass to remove muddiness
        sos = butter(2, 120.0 / (rate / 2), btype='high', output='sos')
        mono = sosfilt(sos, mono)

        # Short room echo — gives the suit-speaker feel
        d1 = int(rate * 0.032)
        rev = np.zeros_like(mono)
        rev[d1:] = mono[:-d1] * 0.18
        mono = mono + rev

        # Second softer echo for depth
        d2 = int(rate * 0.065)
        rev2 = np.zeros_like(mono)
        rev2[d2:] = mono[:-d2] * 0.08
        mono = mono + rev2

        # Normalize
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
    # ── 2. gTTS — British accent (Google TTS, free, needs internet) ────────────
    try:
        from gtts import gTTS
        out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
        tts_obj = gTTS(text=text, lang="en", tld="co.uk", slow=False)
        tts_obj.save(str(out_path))
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] gTTS British → {out_path.name}")
            return str(out_path)
    except Exception as e:
        print(f"[TTS] gTTS failed: {e}")

      3. Edge TTS - en-GB-RyanNeural (free Microsoft neural voice, JARVIS-like)
      3. Edge TTS - en-GB-RyanNeural (free Microsoft neural, needs internet)
      4. Windows SAPI via PowerShell (built-in fallback)
      5. pyttsx3
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

      2. gTTS British accent (free Google TTS, co.uk = British)
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
            _apply_jarvis_effect(str(out_path))
            return str(out_path)
        else:
            print(f"[TTS] PowerShell SAPI failed (rc={result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        print(f"[TTS] PowerShell SAPI error: {e}")

    # ── 5. win32com SAPI ─────────────────────────────────────────────────────
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
        _apply_jarvis_effect(str(out_path))
        return str(out_path)
    except Exception as e:
        print(f"[TTS] win32com SAPI failed: {e}")

    # ── 6. pyttsx3 ───────────────────────────────────────────────────────────
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
