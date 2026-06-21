import base64, os, io
from PIL import Image

def screen_capture(save_path: str | None = None) -> dict:
    """Capture the primary monitor."""
    try:
        from mss import mss
        with mss() as sct:
            shot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            if save_path:
                img.save(save_path)
                return {"ok": True, "path": save_path, "width": img.width, "height": img.height}
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {"ok": True, "width": img.width, "height": img.height, "b64_preview": b64[:120]+"..."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def analyze_screen(question: str = "What is on the screen?") -> dict:
    """Capture screen and send to OpenAI vision. Falls back to local description."""
    from mss import mss
    with mss() as sct:
        shot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    
    # try OpenAI vision
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role":"user",
                    "content":[
                        {"type":"text","text": question},
                        {"type":"image_url","image_url":{"url": f"data:image/png;base64,{b64}", "detail":"low"}}
                    ]
                }],
                max_tokens=250,
            )
            return {"ok": True, "analysis": r.choices[0].message.content}
        except Exception as e:
            return {"ok": False, "error": str(e), "fallback": f"screenshot captured {img.width}x{img.height}"}
    return {"ok": True, "analysis": f"Screenshot captured {img.width}x{img.height}. Set OPENAI_API_KEY for AI vision analysis."}
