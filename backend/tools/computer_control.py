import os, subprocess, time

def open_app(app_name: str) -> dict:
    """Open a Windows app. e.g. 'notepad', 'code', 'chrome'"""
    try:
        # try start
        subprocess.Popen(f'start "" "{app_name}"', shell=True)
        return {"ok": True, "launched": app_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def type_text(text: str) -> dict:
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.typewrite(text, interval=0.012)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def hotkey(keys: str) -> dict:
    """e.g. 'ctrl,c' or 'alt,tab'"""
    try:
        import pyautogui
        parts = [k.strip() for k in keys.split(",")]
        pyautogui.hotkey(*parts)
        return {"ok": True, "pressed": parts}
    except Exception as e:
        return {"ok": False, "error": str(e)}
