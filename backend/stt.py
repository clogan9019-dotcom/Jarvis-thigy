import os
_model = None

def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        size = os.getenv("WHISPER_MODEL", "base")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model

def transcribe_file(path: str) -> str:
    m = get_model()
    segments, info = m.transcribe(path, beam_size=1)
    return " ".join([s.text for s in segments]).strip()
