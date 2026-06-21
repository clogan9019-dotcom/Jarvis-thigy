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

def click(x: int = None, y: int = None, button: str = "left") -> dict:
    """Click at screen coordinates. e.g. click(x=100, y=200)"""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        
        if x is not None and y is not None:
            pyautogui.click(x, y, button=button)
            return {"ok": True, "clicked": f"{button} click at ({x}, {y})"}
        else:
            # Click at current position
            pyautogui.click(button=button)
            return {"ok": True, "clicked": f"{button} click at current position"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def move_to(x: int, y: int) -> dict:
    """Move mouse to coordinates"""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.moveTo(x, y)
        return {"ok": True, "moved_to": f"({x}, {y})"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_cursor_pos() -> dict:
    """Get current mouse position"""
    try:
        import pyautogui
        x, y = pyautogui.position()
        return {"ok": True, "x": x, "y": y}
    except Exception as e:
        return {"ok": False, "error": str(e)}
