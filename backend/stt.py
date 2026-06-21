"""
Speech-to-Text - Purely Local (No API Keys!)
Uses faster-whisper for local transcription
"""

import os
import time
import tempfile
from pathlib import Path

# ── Model cache: load once, reuse on every call ──────────────────────────────
_model_cache: dict = {}

def _load_whisper_model(model_size: str):
    """
    Load WhisperModel once and cache it for the lifetime of the process.
    GPU: int8_float16 — fastest on modern NVIDIA cards (Ampere+).
    CPU: int8 fallback.
    """
    if model_size in _model_cache:
        return _model_cache[model_size]

    from faster_whisper import WhisperModel

    download_root = os.path.join(os.getenv("APPDATA", "."), "jarvis", "models")

    # Try GPU with int8_float16 (fastest on Ampere/RTX cards)
    for compute in ("int8_float16", "float16"):
        try:
            model = WhisperModel(
                model_size,
                device="cuda",
                compute_type=compute,
                download_root=download_root
            )
            print(f"[STT] Loaded Whisper model: {model_size} (device: cuda, compute: {compute})")
            _model_cache[model_size] = model
            return model
        except Exception as e:
            print(f"[STT] CUDA/{compute} unavailable: {e}")

    # CPU int8 fallback
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        download_root=download_root
    )
    print(f"[STT] Loaded Whisper model: {model_size} (device: cpu, compute: int8)")
    _model_cache[model_size] = model
    return model


def transcribe_audio(audio_path: str = None) -> dict:
    """
    Transcribe an audio file using faster-whisper. Completely local, no API keys.
    """
    if audio_path is None:
        return {"ok": False, "error": "Audio path required."}
    if not os.path.exists(audio_path):
        return {"ok": False, "error": f"File not found: {audio_path}"}

    try:
        # tiny.en: fastest, English-only — perfect for voice commands
        # Change WHISPER_MODEL env var to "base" or "small" for higher accuracy
        model_size = os.getenv("WHISPER_MODEL", "tiny.en")
        model = _load_whisper_model(model_size)

        t0 = time.time()
        print("[STT] Transcribing...")
        segments, info = model.transcribe(
            audio_path,
            language="en",
            beam_size=1,        # greedy — instant, fine for conversational speech
            vad_filter=False,   # VAD was too aggressive for short PTT clips
        )

        full_text = " ".join([seg.text for seg in segments]).strip()
        elapsed = time.time() - t0
        print(f"[STT] Done! {elapsed:.2f}s | audio={info.duration:.1f}s | text={full_text[:60]!r}")

        return {
            "ok": True,
            "text": full_text,
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
