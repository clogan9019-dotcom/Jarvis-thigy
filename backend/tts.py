import os
import uuid
import tempfile
from pathlib import Path


def _apply_jarvis_effect(wav_path: str) -> str:
    """
    Post-process a WAV file to give it the JARVIS metallic/reverb quality.
    Returns path to the processed file (overwrites in-place).
    Uses only scipy + numpy — no extra deps.
    """
    try:
        import numpy as np
        from scipy.io import wavfile
        from scipy.signal import lfilter

        rate, data = wavfile.read(wav_path)

        # Ensure float64 for processing
        if data.dtype == np.int16:
            samples = data.astype(np.float64) / 32768.0
        elif data.dtype == np.int32:
            samples = data.astype(np.float64) / 2147483648.0
        else:
            samples = data.astype(np.float64)

        mono = samples if samples.ndim == 1 else samples[:, 0]

        # ── 1. Subtle high-frequency boost (crisp/digital edge) ──────────────
        # Simple FIR high-shelf: emphasise above ~3kHz
        b_shelf = np.array([1.3, -0.3])
        a_shelf = np.array([1.0])
        mono = lfilter(b_shelf, a_shelf, mono)

        # ── 2. Short reverb / room echo (JARVIS speaks in a "chamber") ───────
        delay_ms = 38          # ms — tight reflection
        decay    = 0.22        # how loud the echo is
        delay_samples = int(rate * delay_ms / 1000)
        reverb = np.zeros_like(mono)
        reverb[delay_samples:] = mono[:-delay_samples] * decay
        mono = mono + reverb

        # ── 3. Second, softer echo for depth ─────────────────────────────────
        delay2_ms = 72
        decay2    = 0.10
        delay2_samples = int(rate * delay2_ms / 1000)
        reverb2 = np.zeros_like(mono)
        reverb2[delay2_samples:] = mono[:-delay2_samples] * decay2
        mono = mono + reverb2

        # ── 4. Normalise so we don't clip ────────────────────────────────────
        peak = np.max(np.abs(mono))
        if peak > 0:
            mono = mono / peak * 0.92

        # Write back as int16
        out = (mono * 32767).astype(np.int16)
        wavfile.write(wav_path, rate, out)
        print("[TTS] JARVIS voice effect applied")

    except Exception as e:
        print(f"[TTS] Voice effect skipped: {e}")

    return wav_path


def tts_to_file(text: str) -> str | None:
    """
    Convert text to speech and return path to the audio file.
    Priority: ElevenLabs (if key set) → Windows SAPI → pyttsx3
    JARVIS voice effect is applied to SAPI / pyttsx3 output.
    """
    out_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
    out_dir.mkdir(exist_ok=True)

    # ── ElevenLabs (optional) ────────────────────────────────────────────────
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=api_key)
            voice = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            audio = client.text_to_speech.convert(
                text=text,
                voice_id=voice,
                model_id="eleven_multilingual_v2"
            )
            out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
            with open(out_path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            print(f"[TTS] ElevenLabs → {out_path.name}")
            return str(out_path)
        except Exception as e:
            print(f"[TTS] ElevenLabs failed: {e}")

    # ── Windows SAPI (pywin32) ───────────────────────────────────────────────
    try:
        import win32com.client
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        speaker = win32com.client.Dispatch("SAPI.SpVoice")

        # Slightly slower, more deliberate — JARVIS style
        speaker.Rate = -2   # range -10 to 10, default 0

        file_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        file_stream.Open(str(out_path), 3)  # SSFMCreateForWrite
        speaker.AudioOutputStream = file_stream
        speaker.Speak(text)
        file_stream.Close()
        print(f"[TTS] Windows SAPI → {out_path.name}")
        _apply_jarvis_effect(str(out_path))
        return str(out_path)
    except Exception as e:
        print(f"[TTS] Windows SAPI failed: {e}")

    # ── pyttsx3 fallback ─────────────────────────────────────────────────────
    try:
        import pyttsx3
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        engine = pyttsx3.init()

        # Slower, lower pitch for JARVIS character
        rate = engine.getProperty('rate')
        engine.setProperty('rate', max(120, rate - 40))

        # Pick lowest available voice for a deeper tone
        voices = engine.getProperty('voices')
        if voices:
            # Prefer male voice if available
            male = [v for v in voices if 'male' in v.name.lower() or 'david' in v.name.lower() or 'mark' in v.name.lower()]
            engine.setProperty('voice', (male[0] if male else voices[0]).id)

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

    print("[TTS] All TTS engines failed — no audio output")
    return None
