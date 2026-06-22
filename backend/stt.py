"""
  Speech-to-Text - Purely Local (No API Keys!)
  Uses faster-whisper for local transcription
  """

  import os
  import time
  import tempfile
  from pathlib import Path

  # ── Module-level cache ────────────────────────────────────────────────────────
  _model_cache: dict = {}
  _cuda_works: bool | None = None   # None = untested, True = ok, False = broken


  def _add_cuda_dll_dirs():
      """
      Windows: register CUDA bin dirs with Python's DLL search path BEFORE
      ctranslate2 is imported.
      Also creates a cublas64_12.dll shim if only cublas64_13.dll (or newer) exists,
      since ctranslate2 looks for the exact name 'cublas64_12.dll'.
      """
      if os.name != "nt":
          return

      import glob, shutil

      candidates = []
      for env_var in ("CUDA_PATH", "CUDA_HOME", "CUDA_ROOT"):
          p = os.environ.get(env_var)
          if p:
              candidates.append(os.path.join(p, "bin"))

      base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
      if os.path.isdir(base):
          for d in sorted(glob.glob(os.path.join(base, "v*", "bin")), reverse=True):
              candidates.append(d)

      for env_var in ("CUDNN_PATH", "TRT_ROOT"):
          p = os.environ.get(env_var)
          if p:
              candidates.append(os.path.join(p, "bin"))

      added = []
      shim_dir = None

      for cuda_bin in candidates:
          if not os.path.isdir(cuda_bin):
              continue

          # ── CUDA 13→12 shim: ctranslate2 hard-codes cublas64_12.dll ──────────
          cublas12 = os.path.join(cuda_bin, "cublas64_12.dll")
          if not os.path.exists(cublas12):
              # look for cublas64_13.dll (or any other version)
              matches = glob.glob(os.path.join(cuda_bin, "cublas64_??.dll"))
              if matches:
                  if shim_dir is None:
                      shim_dir = os.path.join(tempfile.gettempdir(), "jarvis_cuda_shim")
                      os.makedirs(shim_dir, exist_ok=True)
                  shim_dst = os.path.join(shim_dir, "cublas64_12.dll")
                  if not os.path.exists(shim_dst):
                      shutil.copy2(matches[0], shim_dst)
                      print(f"[STT] CUDA shim: copied {os.path.basename(matches[0])} → cublas64_12.dll")

          try:
              os.add_dll_directory(cuda_bin)
              added.append(cuda_bin)
          except (AttributeError, OSError):
              pass

      # Add shim dir last so it's only a fallback
      if shim_dir and os.path.isdir(shim_dir):
          try:
              os.add_dll_directory(shim_dir)
              added.append(shim_dir)
          except (AttributeError, OSError):
              pass

      if added:
          print(f"[STT] CUDA DLL dirs registered: {added}")
      else:
          print("[STT] WARNING: No CUDA bin dirs found — CUDA may still fail.")


  def _load_whisper_model(model_size: str):
      """
      Load WhisperModel once and cache it.
      After the first CUDA inference failure, permanently uses CPU so startup is instant.
      """
      global _cuda_works

      # If we already know CUDA is broken, skip straight to CPU
      if _cuda_works is False:
          return _load_cpu_model(model_size)

      if model_size in _model_cache:
          return _model_cache[model_size]

      _add_cuda_dll_dirs()

      from faster_whisper import WhisperModel
      download_root = os.path.join(os.getenv("APPDATA", "."), "jarvis", "models")

      for compute in ("int8_float16", "float16"):
          try:
              model = WhisperModel(
                  model_size, device="cuda",
                  compute_type=compute,
                  download_root=download_root
              )
              print(f"[STT] Loaded Whisper model: {model_size} (cuda/{compute})")
              _model_cache[model_size] = model
              return model
          except Exception as e:
              print(f"[STT] CUDA/{compute} unavailable: {e}")

      return _load_cpu_model(model_size)


  def _load_cpu_model(model_size: str):
      """Always returns a CPU int8 model, cached."""
      cpu_key = f"{model_size}_cpu"
      if cpu_key in _model_cache:
          return _model_cache[cpu_key]

      from faster_whisper import WhisperModel
      download_root = os.path.join(os.getenv("APPDATA", "."), "jarvis", "models")
      model = WhisperModel(
          model_size, device="cpu",
          compute_type="int8",
          download_root=download_root
      )
      print(f"[STT] Loaded Whisper model: {model_size} (cpu/int8)")
      _model_cache[cpu_key] = model
      return model


  def transcribe_audio(audio_path: str = None) -> dict:
      """
      Transcribe an audio file using faster-whisper. Completely local, no API keys.
      """
      global _cuda_works

      if audio_path is None:
          return {"ok": False, "error": "Audio path required."}
      if not os.path.exists(audio_path):
          return {"ok": False, "error": f"File not found: {audio_path}"}

      try:
          model_size = os.getenv("WHISPER_MODEL", "base.en")
          model = _load_whisper_model(model_size)

          t0 = time.time()
          print("[STT] Transcribing...")

          def _run_transcribe(m):
              segs, inf = m.transcribe(
                  audio_path, language="en",
                  beam_size=1, vad_filter=False
              )
              return " ".join([s.text for s in segs]).strip(), inf

          try:
              full_text, info = _run_transcribe(model)
              if _cuda_works is None:
                  _cuda_works = True   # first successful inference on GPU
          except Exception as cuda_err:
              err_lower = str(cuda_err).lower()
              if any(k in err_lower for k in ("dll", "cuda", "cublas", "library", "cublaslt")):
                  print(f"[STT] CUDA inference failed ({cuda_err}) — switching to CPU permanently")
                  _cuda_works = False
                  # Replace cache entry so next call goes straight to CPU
                  _model_cache.pop(model_size, None)
                  cpu_model = _load_cpu_model(model_size)
                  _model_cache[model_size] = cpu_model   # next _load_whisper_model returns CPU
                  full_text, info = _run_transcribe(cpu_model)
              else:
                  raise

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
  