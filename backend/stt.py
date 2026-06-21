"""
Speech-to-Text - Purely Local (No API Keys!)
Uses faster-whisper for local transcription
"""

import os
import time
import tempfile
from pathlib import Path


def _load_whisper_model(model_size: str):
    """
    Load WhisperModel, preferring CUDA (GPU). Falls back to CPU automatically.
    faster-whisper uses ctranslate2 which has its own CUDA support,
    independent of whether torch is installed.
    """
    from faster_whisper import WhisperModel

    download_root = os.path.join(os.getenv("APPDATA", "."), "jarvis", "models")

    # Try GPU first
    try:
        model = WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16",
            download_root=download_root
        )
        print(f"[STT] Loaded Whisper model: {model_size} (device: cuda, compute: float16)")
        return model
    except Exception as e:
        print(f"[STT] CUDA unavailable ({e}), falling back to CPU")

    # CPU fallback
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        download_root=download_root
    )
    print(f"[STT] Loaded Whisper model: {model_size} (device: cpu, compute: int8)")
    return model


def transcribe_audio(audio_path: str = None) -> dict:
    """
    Transcribe an audio file using faster-whisper. Completely local, no API keys.

    Args:
        audio_path: Path to audio file (wav, mp3, etc.)

    Returns:
        {"ok": True, "text": "transcribed text"} or {"ok": False, "error": "..."}
    """
    if audio_path is None:
        return {"ok": False, "error": "Audio path required."}

    if not os.path.exists(audio_path):
        return {"ok": False, "error": f"File not found: {audio_path}"}

    try:
        model_size = os.getenv("WHISPER_MODEL", "base")
        model = _load_whisper_model(model_size)

        print("[STT] Transcribing...")
        segments, info = model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            vad_filter=False   # VAD was too aggressive for short PTT clips
        )

        full_text = " ".join([segment.text for segment in segments])
        print(f"[STT] Done! Duration: {info.duration:.1f}s, Text: {full_text[:50]}...")

        return {
            "ok": True,
            "text": full_text.strip(),
            "language": info.language,
            "duration": info.duration,
            "model": model_size
        }

    except ImportError:
        return {
            "ok": False,
            "error": "faster-whisper not installed. Run: pip install faster-whisper",
            "hint": "For GPU: pip install faster-whisper ctranslate2"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def transcribe_microphone(duration_seconds: float = 5.0) -> dict:
    """
    Record from microphone and transcribe. Completely local.

    Args:
        duration_seconds: How long to record (default 5 seconds)

    Returns:
        {"ok": True, "text": "transcribed text"}
    """
    try:
        import sounddevice as sd
        import numpy as np
        from scipy.io import wavfile
    except ImportError:
        return {
            "ok": False,
            "error": "sounddevice not installed. Run: pip install sounddevice scipy numpy"
        }

    try:
        print(f"[STT] Recording for {duration_seconds}s...")
        recording = sd.rec(
            int(duration_seconds * 16000),
            samplerate=16000,
            channels=1,
            dtype='float32'
        )
        sd.wait()

        temp_dir = Path(tempfile.gettempdir()) / "jarvis_stt"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"mic_{int(time.time())}.wav"

        audio_16bit = (recording * 32767).astype(np.int16)
        wavfile.write(str(temp_path), 16000, audio_16bit)

        print("[STT] Recording complete, transcribing...")
        return transcribe_audio(str(temp_path))

    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    print("To install dependencies: pip install faster-whisper sounddevice scipy numpy")
    print("For GPU support: ensure ctranslate2 is built with CUDA")
