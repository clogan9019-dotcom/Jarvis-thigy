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
_pause_event = threading.Event()
_TRIGGERS = {"jarvis", "jarvish", "jarvas", "davis", "harvest"}  # common mishears
_COMMAND_WINDOW_SEC = 8.0  # after wake, treat the next heard phrase as the user command


def _is_wake(text: str) -> bool:
    lower = text.lower()
    return any(t in lower for t in _TRIGGERS)


def _command_after_wake(text: str) -> str:
    """Return words spoken after the wake word in the same transcript, if any."""
    import re

    for trigger in sorted(_TRIGGERS, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(trigger)}\b[,.!?;:\- ]*(.*)$", text, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,!?:;-\t\n")
    return ""


def _queue_command(text: str) -> None:
    """Send a wake-word command through the same path as normal STT results."""
    _wake_queue.put({
        "type": "stt_result",
        "ok": True,
        "text": text,
        "source": "wake_word",
    })


def _listen_loop(chunk_sec: float = 1.5, silence_threshold: float = 0.003):
    """
    Continuously records short clips at the mic's NATIVE sample rate,
    resamples to 16 kHz for Whisper, and detects the wake word "Jarvis".
    """
    try:
        import sounddevice as sd
        import numpy as np
        from scipy.signal import resample as scipy_resample
        from scipy.io import wavfile
    except ImportError as e:
        print(f"[WAKE] Missing dependency ({e}) — wake word disabled")
        return

    from stt import _load_cpu_model
    try:
        model = _load_cpu_model("tiny.en")  # CPU — fast enough, avoids CUDA DLL conflict
    except Exception as e:
        print(f"[WAKE] Could not load tiny.en: {e} — wake word disabled")
        return

    # ── Query native mic sample rate (Windows mics often NOT 16000 Hz) ────
    try:
        dev_info  = sd.query_devices(kind="input")
        native_sr = int(dev_info.get("default_samplerate", 16000))
    except Exception:
        native_sr = 44100
    TARGET_SR = 16000
    chunk_samples = int(native_sr * chunk_sec)

    temp_dir  = Path(tempfile.gettempdir()) / "jarvis_wake"
    temp_dir.mkdir(exist_ok=True)
    clip_path = str(temp_dir / "clip.wav")

    print(f"[WAKE] Mic native rate: {native_sr} Hz  |  chunk: {chunk_sec}s  |  model: tiny.en")
    print("[WAKE] Listening for 'Jarvis'... (you will see [WAKE] Heard: ... for every non-silent clip)")
    armed_until = 0.0

    while True:
        try:
            if _pause_event.is_set():
                time.sleep(0.05)
                continue

            audio = sd.rec(chunk_samples, samplerate=native_sr, channels=1, dtype="float32")
            sd.wait()
            audio = audio.flatten()

            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < silence_threshold:
                continue  # silent clip — skip

            # Resample to 16000 Hz for Whisper
            if native_sr != TARGET_SR:
                target_len = int(len(audio) * TARGET_SR / native_sr)
                audio = scipy_resample(audio, target_len).astype(np.float32)

            wavfile.write(clip_path, TARGET_SR, (audio * 32767).astype(np.int16))

            try:
                segs, _ = model.transcribe(
                    clip_path, language="en",
                    beam_size=1, vad_filter=True,
                    condition_on_previous_text=False
                )
                text = " ".join(s.text for s in segs).strip()
            except Exception as infer_err:
                err_s = str(infer_err).lower()
                if any(k in err_s for k in ("cublas", "cuda", "dll", "library")):
                    from stt import _load_cpu_model as _cpu
                    print(f"[WAKE] CUDA inference failed ({infer_err}) — switching to CPU permanently")
                    model = _cpu("tiny.en")
                    continue  # retry next clip with CPU model
                raise

            if text:
                print(f"[WAKE] Heard: {text!r}")

            if _is_wake(text):
                print("[WAKE] *** 'Jarvis' detected — activating ***")
                command = _command_after_wake(text)
                armed_until = 0.0 if command else time.time() + _COMMAND_WINDOW_SEC
                # Play chime in a separate thread so it doesn't block recording
                threading.Thread(target=_play_chime, daemon=True).start()
                _wake_queue.put({"type": "wake_word", "heard": text})
                if command:
                    print(f"[WAKE] Command in wake phrase: {command!r}")
                    _queue_command(command)
            elif text and time.time() < armed_until:
                print(f"[WAKE] Command after wake: {text!r}")
                armed_until = 0.0
                _queue_command(text)

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


def pause() -> None:
    """Temporarily pause wake-word mic capture so push-to-talk can own the device."""
    _pause_event.set()


def resume() -> None:
    """Resume wake-word mic capture after push-to-talk or another exclusive capture."""
    _pause_event.clear()


def is_paused() -> bool:
    return _pause_event.is_set()


def get_queue() -> queue.Queue:
    return _wake_queue
