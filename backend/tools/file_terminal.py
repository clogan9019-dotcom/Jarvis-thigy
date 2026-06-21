import subprocess, os
from pathlib import Path

def read_file(path: str) -> dict:
    try:
        p = Path(path).expanduser()
        text = p.read_text(encoding="utf-8", errors="ignore")
        return {"ok": True, "content": text[:12000]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def write_file(path: str, content: str) -> dict:
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run_cmd(command: str, timeout: int = 20) -> dict:
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "code": r.returncode,
                "stdout": r.stdout[-6000:], "stderr": r.stderr[-2000:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
