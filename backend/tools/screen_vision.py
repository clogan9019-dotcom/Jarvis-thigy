"""
Screen Vision - Purely Local
Uses MSS for capture, Ollama for analysis (no OpenAI!)
"""

import base64, os, io
from pathlib import Path

def screen_capture(save_path: str = None) -> dict:
    """Capture the primary monitor."""
    try:
        from mss import mss
        with mss() as sct:
            shot = sct.grab(sct.monitors[1])
            from PIL import Image
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            
            if save_path:
                img.save(save_path)
                return {"ok": True, "path": save_path, "width": img.width, "height": img.height}
            
            # Return dimensions
            return {
                "ok": True, 
                "width": img.width, 
                "height": img.height,
                "message": "Screenshot captured. Use analyze_screen for AI analysis."
            }
    except ImportError:
        return {"ok": False, "error": "mss not installed. Run: pip install mss"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def analyze_screen(question: str = "What is on the screen?") -> dict:
    """
    Capture screen and analyze with Ollama vision model.
    Falls back to local description if no vision model available.
    """
    try:
        from mss import mss
        with mss() as sct:
            shot = sct.grab(sct.monitors[1])
            from PIL import Image
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except ImportError:
        return {"ok": False, "error": "mss not installed. Run: pip install mss"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    
    # Check for Ollama vision model
    vision_model = os.getenv("OLLAMA_VISION_MODEL", "llava:latest")
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    
    # Save image to temp
    temp_path = Path.home() / "Jarvis" / "temp_screenshot.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(temp_path))
    
    # Try Ollama vision
    try:
        import httpx
        import base64
        
        # Read and encode image
        with open(temp_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        
        # Check if llava is available
        try:
            models_resp = httpx.get(f"{ollama_host}/api/tags", timeout=5)
            models = [m.get("name", "") for m in models_resp.json().get("models", [])]
            
            if not any("llava" in m.lower() for m in models):
                return {
                    "ok": True,
                    "analysis": "Screenshot captured but no vision model installed.\n\n"
                               f"💡 To enable AI analysis, install llava:\n"
                               f"   ollama pull llava\n\n"
                               f"Screenshot: {img.width}x{img.height}"
                }
        except:
            pass
        
        # Try with llava
        payload = {
            "model": vision_model,
            "prompt": f"Question: {question}\n\nDescribe what's shown in this screenshot in detail.",
            "images": [img_b64],
            "stream": False
        }
        
        response = httpx.post(f"{ollama_host}/api/generate", json=payload, timeout=60)
        result = response.json()
        analysis = result.get("response", "").strip()
        
        if analysis:
            return {"ok": True, "analysis": analysis}
        
    except Exception as e:
        print(f"[ScreenVision] Ollama vision error: {e}")
    
    # Fallback: return basic info
    return {
        "ok": True,
        "analysis": f"Screenshot captured: {img.width}x{img.height}\n\n"
                   f"To enable AI analysis, install a vision model:\n"
                   f"   ollama pull llava\n\n"
                   f"Or set OLLAMA_VISION_MODEL in .env to your vision model."
    }