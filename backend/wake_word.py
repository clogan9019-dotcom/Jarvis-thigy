"""
Wake Word Detector - listens for "Jarvis" using faster-whisper tiny.en.
Fully local, no API keys, no new packages (faster-whisper + sounddevice already installed).
"""
import os
import time
import queue
import threading
import tempfile
from pathlib import Path


def _play_chime():
    """Two-tone Iron Man-style activation chime. Plays async so it doesn't block the listener."""
    try:
        import numpy as np
        import sounddevice as sd
        sr = 22050
        def _tone(freq, dur, vol=0.35):
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            wave = vol * np.sin(2 * np.pi * freq * t)
            fade = int(sr * 0.01)
            if fade > 0:
                wave[:fade] *= np.linspace(0, 1, fade)
                wave[-fade:] *= np.linspace(1, 0, fade)
            return wave.astype(np.float32)
        # Ascending two-tone: subtle but recognisable
        chime = np.concatenate([_tone(880, 0.10), np.zeros(int(sr * 0.03), dtype=np.float32), _tone(1320, 0.18)])
        sd.play(chime, sr)
        # Don't sd.wait() here — fire and forget so listener resumes immediately
    except Exception:
        pass

_wake_queue: queue.Queue = queue.Queue()
_TRIGGERS = {"jarvis", "jarvish", "jarvas", "davis", "harvest"}  # common mishears


def _is_wake(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in _TRIGGERS)


def _listen_loop(sample_rate: int = 16000, chunk_sec: float = 1.2, silence_threshold: float = 0.008):
    """Continuously records short clips and transcribes with tiny.en to spot 'Jarvis'."""
    try:
        import sounddevice as sd
        import numpy as np
        from scipy.io import wavfile
    except ImportError:
        print("[WAKE] sounddevice/scipy not installed — wake word disabled")
        return

    # Import here to avoid circular import (stt imports nothing from wake_word)
    from stt import _load_whisper_model
    try:
        model = _load_whisper_model("tiny.en")
    except Exception as e:
        print(f"[WAKE] Could not load tiny.en: {e} — wake word disabled")
        return

    temp_dir = Path(tempfile.gettempdir()) / "jarvis_wake"
    temp_dir.mkdir(exist_ok=True)
    clip_path = str(temp_dir / "clip.wav")

    chunk_samples = int(sample_rate * chunk_sec)
    print("[WAKE] Listening for 'Jarvis'...")

    while True:
        try:
            audio = sd.rec(chunk_samples, samplerate=sample_rate, channels=1, dtype="float32")
            sd.wait()

            import numpy as np
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < silence_threshold:
                continue  # silence — skip transcription

            from scipy.io import wavfile
            wavfile.write(clip_path, sample_rate, (audio * 32767).astype(np.int16))

            segs, _ = model.transcribe(
                clip_path, language="en",
                beam_size=1, vad_filter=True,
                condition_on_previous_text=False
            )
            text = " ".join(s.text for s in segs).strip()

            if text:
                print(f"[WAKE] Heard: {text!r}")

            if _is_wake(text):
                print("[WAKE] *** 'Jarvis' detected — activating ***")
                _play_chime()
                _wake_queue.put({"type": "wake_word", "heard": text})

        except Exception as e:
            print(f"[WAKE] Loop error: {e}")
            time.sleep(1)


_thread: threading.Thread | None = None


def start(enabled: bool = True) -> None:
    """Start the wake word detector background thread (idempotent)."""
    global _thread
    if not enabled:
        print("[WAKE] Wake word disabled (WAKE_WORD=0)")
        return
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_listen_loop, daemon=True, name="WakeWordDetector")
    _thread.start()


def get_queue() -> queue.Queue:
    return _wake_queue
