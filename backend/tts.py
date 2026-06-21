import os, uuid, tempfile
from pathlib import Path

def tts_to_file(text: str) -> str | None:
    """Returns path to a .mp3 / .wav file. Tries ElevenLabs, falls back to Windows SAPI."""
    out_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
    out_dir.mkdir(exist_ok=True)

    # ElevenLabs
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=api_key)
            voice = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            audio = client.text_to_speech.convert(text=text, voice_id=voice, model_id="eleven_multilingual_v2")
            out_path = out_dir / f"j_{uuid.uuid4().hex}.mp3"
            with open(out_path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            return str(out_path)
        except Exception as e:
            print("ElevenLabs TTS failed:", e)

    # Windows SAPI fallback
    try:
        import win32com.client
        out_path = out_dir / f"j_{uuid.uuid4().hex}.wav"
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        file_stream = win32com.client.Dispatch("SAPI.SpFileStream")
        file_stream.Open(str(out_path), 3)  # SSFMCreateForWrite
        speaker.AudioOutputStream = file_stream
        speaker.Speak(text)
        file_stream.Close()
        return str(out_path)
    except Exception as e:
        print("SAPI TTS failed:", e)
        return None
