"""
Speech-to-Text - Purely Local (No API Keys!)
Uses faster-whisper for local transcription
"""

import os
import tempfile
from pathlib import Path

def transcribe_audio(audio_path: str = None) -> dict:
    """
    Transcribe audio file to text using faster-whisper.
    Completely local, no API keys needed!
    
    Args:
        audio_path: Path to audio file (wav, mp3, etc.)
                   If None, uses microphone input
    
    Returns:
        {"ok": True, "text": "transcribed text"}
    """
    
    if audio_path is None:
        return {"ok": False, "error": "Audio path required. Implement mic recording separately."}
    
    if not os.path.exists(audio_path):
        return {"ok": False, "error": f"File not found: {audio_path}"}
    
    try:
        from faster_whisper import WhisperModel
        
        # Get model from env or use default
        model_size = os.getenv("WHISPER_MODEL", "base")
        
        # Determine compute type based on GPU availability
        try:
            import torch
            compute_type = "cuda" if torch.cuda.is_available() else "int8"
        except ImportError:
            compute_type = "int8"
        
        print(f"[STT] Loading Whisper model: {model_size} (compute: {compute_type})")
        
        model = WhisperModel(
            model_size, 
            device="auto", 
            compute_type=compute_type,
            download_root=os.path.join(os.getenv("APPDATA", "."), "jarvis", "models")
        )
        
        print("[STT] Transcribing...")
        segments, info = model.transcribe(
            audio_path, 
            language="en",
            beam_size=5,
            vad_filter=True  # Voice activity detection
        )
        
        # Combine all segments
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
            "hint": "For GPU acceleration: pip install faster-whisper[torch]"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def transcribe_microphone(duration_seconds: float = 5.0) -> dict:
    """
    Record from microphone and transcribe - completely local!
    
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
            "error": "sounddevice not installed. Run: pip install sounddevice scipy",
            "hint": "Also install: pip install numpy"
        }
    
    try:
        # Record audio
        print(f"[STT] Recording for {duration_seconds}s...")
        recording = sd.rec(
            int(duration_seconds * 16000), 
            samplerate=16000, 
            channels=1,
            dtype='float32'
        )
        sd.wait()
        
        # Save to temp file
        temp_dir = Path(tempfile.gettempdir()) / "jarvis_stt"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"mic_{int(os.times().time)}.wav"
        
        # Convert to 16-bit audio for faster-whisper
        audio_16bit = (recording * 32767).astype(np.int16)
        wavfile.write(str(temp_path), 16000, audio_16bit)
        
        print("[STT] Recording complete, transcribing...")
        
        # Transcribe
        return transcribe_audio(str(temp_path))
        
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Quick test
if __name__ == "__main__":
    print("[STT] Testing transcription...")
    print("Note: You need an audio file to test. Run transcribe_audio('path/to/file.wav')")
    print("\nTo install dependencies:")
    print("  pip install faster-whisper sounddevice scipy numpy")
    print("\nOptional GPU acceleration:")
    print("  pip install torch")