import os
import uuid
import tempfile
from pathlib import Path


def tts_to_file(text: str) -> str | None:
    """
    Convert text to speech and return path to the audio file.
    Priority: ElevenLabs (if key set) -> Windows SAPI -> pyttsx3
    """
    out_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
    out_dir.mkdir(exist_ok=True)

    # ── ElevenLabs (optional, if API key is set) ──────────────────────────────
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
            print(f"[TTS] ElevenLabs -> {out_path.name}")
            return str(out_path)
        except Exception as e:
            print(f"[TTS] ElevenLabs failed: {e}")

    # ── Windows SAPI (pywin32) ─────────────────────────────────────────────────
    try:
        import win32com.client
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        file_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        file_stream.Open(str(out_path), 3)  # SSFMCreateForWrite
        speaker.AudioOutputStream = file_stream
        speaker.Speak(text)
        file_stream.Close()
        print(f"[TTS] Windows SAPI -> {out_path.name}")
        return str(out_path)
    except Exception as e:
        print(f"[TTS] Windows SAPI failed: {e}")

    # ── pyttsx3 (cross-platform fallback) ────────────────────────────────────
    try:
        import pyttsx3
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        engine = pyttsx3.init()
        # Slow down a bit and lower pitch for a JARVIS feel
        rate = engine.getProperty('rate')
        engine.setProperty('rate', max(130, rate - 30))
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
        engine.stop()
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[TTS] pyttsx3 -> {out_path.name}")
            return str(out_path)
        print("[TTS] pyttsx3 produced empty file")
    except Exception as e:
        print(f"[TTS] pyttsx3 failed: {e}")

    print("[TTS] All TTS engines failed — no audio output")
    return None
