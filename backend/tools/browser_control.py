"""
Browser Control - Full Playwright-based browser automation for J.A.R.V.I.S
Uses the sync Playwright API so it works cleanly when called from FastAPI's
thread pool (run_in_executor) without any event-loop conflicts.

Install:
    pip install playwright
    python -m playwright install chromium
"""

import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

DOWNLOADS_DIR   = Path.home() / "Jarvis" / "downloads"
SCREENSHOTS_DIR = Path.home() / "Jarvis" / "screenshots"


def _ensure_dirs():
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Singleton browser state (one per process, thread-safe via lock) ───────────
_lock     = threading.Lock()
_pw       = None   # Playwright instance
_browser  = None   # Browser instance
_context  = None   # BrowserContext
_active_page = None  # Currently active Page  (named _active_page to avoid shadowing)


def _get_page(headless: bool = False):
    """Return the active Page, launching browser/context/page if needed."""
    global _pw, _browser, _context, _active_page
    with _lock:
        from playwright.sync_api import sync_playwright

        if _pw is None:
            _pw = sync_playwright().start()

        if _browser is None or not _browser.is_connected():
            _browser = _pw.chromium.launch(
                headless=headless,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )

        if _context is None:
            _ensure_dirs()
            _context = _browser.new_context(
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True,
                downloads_path=str(DOWNLOADS_DIR),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

        if _active_page is None or _active_page.is_closed():
            pages = _context.pages
            _active_page = pages[0] if pages else _context.new_page()

        return _active_page


# ═══════════════════════════════════════════════════════════
#  NAVIGATION
# ═══════════════════════════════════════════════════════════

def browser_open(url: str, wait_until: str = "domcontentloaded") -> dict:
    """Navigate to a URL. Opens the browser if not already running."""
    try:
        p = _get_page()
        if not url.startswith("http"):
            url = "https://" + url
        p.goto(url, wait_until=wait_until, timeout=30000)
        return {"ok": True, "url": p.url, "title": p.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_back() -> dict:
    try:
        p = _get_page()
        p.go_back(wait_until="domcontentloaded", timeout=10000)
        return {"ok": True, "url": p.url, "title": p.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_forward() -> dict:
    try:
        p = _get_page()
        p.go_forward(wait_until="domcontentloaded", timeout=10000)
        return {"ok": True, "url": p.url, "title": p.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_refresh() -> dict:
    try:
        p = _get_page()
        p.reload(wait_until="domcontentloaded", timeout=15000)
        return {"ok": True, "url": p.url, "title": p.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_url() -> dict:
    try:
        p = _get_page()
        return {"ok": True, "url": p.url, "title": p.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════

def browser_new_tab(url: str = "about:blank") -> dict:
    global _active_page
    try:
        with _lock:
            _get_page()  # ensure browser/context exists
            new_p = _context.new_page()
            _active_page = new_p
        if url and url != "about:blank":
            nav_url = url if url.startswith("http") else "https://" + url
            new_p.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
        tabs = _context.pages
        return {
            "ok": True,
            "url": new_p.url,
            "title": new_p.title(),
            "tab_index": tabs.index(new_p),
            "total_tabs": len(tabs),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_list_tabs() -> dict:
    try:
        if _context is None:
            return {"ok": True, "tabs": []}
        tabs = []
        for i, pg in enumerate(_context.pages):
            try:
                tabs.append({
                    "index": i, "url": pg.url,
                    "title": pg.title(), "active": pg == _active_page
                })
            except Exception:
                tabs.append({"index": i, "url": "unknown", "title": "unknown", "active": False})
        return {"ok": True, "tabs": tabs}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_switch_tab(index: int) -> dict:
    global _active_page
    try:
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        tabs = _context.pages
        if index < 0 or index >= len(tabs):
            return {"ok": False, "error": f"Tab index {index} out of range (0–{len(tabs)-1})"}
        with _lock:
            _active_page = tabs[index]
        _active_page.bring_to_front()
        return {"ok": True, "url": _active_page.url, "title": _active_page.title()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_close_tab(index: int = -1) -> dict:
    global _active_page
    try:
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        tabs = _context.pages
        if not tabs:
            return {"ok": False, "error": "No tabs open"}
        tab = tabs[index] if index >= 0 else _active_page
        tab.close()
        remaining = _context.pages
        if remaining:
            with _lock:
                _active_page = remaining[-1]
            _active_page.bring_to_front()
            return {"ok": True, "remaining_tabs": len(remaining), "current_url": _active_page.url}
        with _lock:
            _active_page = None
        return {"ok": True, "remaining_tabs": 0}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_close() -> dict:
    global _pw, _browser, _context, _active_page
    try:
        with _lock:
            if _browser:
                _browser.close()
            if _pw:
                _pw.stop()
            _pw = _browser = _context = _active_page = None
        return {"ok": True, "message": "Browser closed"}
    except Exception as e:
        with _lock:
            _pw = _browser = _context = _active_page = None
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  CLICKING & MOUSE
# ═══════════════════════════════════════════════════════════

def browser_click(
    selector: str = None,
    x: int = None,
    y: int = None,
    button: str = "left",
    double: bool = False,
    timeout: int = 10000,
) -> dict:
    """Click by CSS selector, XPath, text ('text=Sign in'), or x/y coords."""
    try:
        p = _get_page()
        if x is not None and y is not None:
            if double:
                p.mouse.dblclick(x, y)
            else:
                p.mouse.click(x, y, button=button)
            return {"ok": True, "clicked": f"({x}, {y})"}
        if selector:
            el = p.locator(selector).first
            if double:
                el.dblclick(timeout=timeout)
            else:
                el.click(button=button, timeout=timeout)
            return {"ok": True, "clicked": selector}
        return {"ok": False, "error": "Provide selector or x/y coordinates"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_right_click(selector: str = None, x: int = None, y: int = None) -> dict:
    return browser_click(selector=selector, x=x, y=y, button="right")


def browser_hover(
    selector: str = None, x: int = None, y: int = None, timeout: int = 10000
) -> dict:
    try:
        p = _get_page()
        if x is not None and y is not None:
            p.mouse.move(x, y)
            return {"ok": True, "hovered": f"({x}, {y})"}
        if selector:
            p.locator(selector).first.hover(timeout=timeout)
            return {"ok": True, "hovered": selector}
        return {"ok": False, "error": "Provide selector or coordinates"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_drag(
    from_selector: str = None,
    to_selector: str = None,
    from_x: int = None,
    from_y: int = None,
    to_x: int = None,
    to_y: int = None,
) -> dict:
    try:
        p = _get_page()
        if from_x is not None and to_x is not None:
            p.mouse.move(from_x, from_y)
            p.mouse.down()
            p.mouse.move(to_x, to_y, steps=10)
            p.mouse.up()
            return {"ok": True, "dragged": f"({from_x},{from_y}) → ({to_x},{to_y})"}
        if from_selector and to_selector:
            p.locator(from_selector).first.drag_to(p.locator(to_selector).first)
            return {"ok": True, "dragged": f"{from_selector} → {to_selector}"}
        return {"ok": False, "error": "Provide from/to selectors or coordinates"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  KEYBOARD & TYPING
# ═══════════════════════════════════════════════════════════

def browser_type(
    selector: str,
    text: str,
    clear_first: bool = True,
    press_enter: bool = False,
    timeout: int = 10000,
) -> dict:
    try:
        p = _get_page()
        el = p.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        if clear_first:
            el.clear()
        el.fill(text)
        if press_enter:
            el.press("Enter")
        return {
            "ok": True,
            "typed": text[:80] + ("..." if len(text) > 80 else ""),
            "selector": selector,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_press_key(key: str, selector: str = None) -> dict:
    """Press a key globally or on a specific element.
    Examples: 'Enter', 'Escape', 'Tab', 'Control+a', 'Control+c'"""
    try:
        p = _get_page()
        if selector:
            p.locator(selector).first.press(key)
        else:
            p.keyboard.press(key)
        return {"ok": True, "pressed": key}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_clear_input(selector: str, timeout: int = 10000) -> dict:
    try:
        _get_page().locator(selector).first.clear(timeout=timeout)
        return {"ok": True, "cleared": selector}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_select_option(
    selector: str,
    value: str = None,
    label: str = None,
    index: int = None,
    timeout: int = 10000,
) -> dict:
    try:
        p = _get_page()
        el = p.locator(selector).first
        if value is not None:
            el.select_option(value=value, timeout=timeout)
            return {"ok": True, "selected": value}
        if label is not None:
            el.select_option(label=label, timeout=timeout)
            return {"ok": True, "selected": label}
        if index is not None:
            el.select_option(index=index, timeout=timeout)
            return {"ok": True, "selected": f"index {index}"}
        return {"ok": False, "error": "Provide value, label, or index"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_check(selector: str, timeout: int = 10000) -> dict:
    try:
        _get_page().locator(selector).first.check(timeout=timeout)
        return {"ok": True, "checked": selector}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_uncheck(selector: str, timeout: int = 10000) -> dict:
    try:
        _get_page().locator(selector).first.uncheck(timeout=timeout)
        return {"ok": True, "unchecked": selector}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  SCROLLING
# ═══════════════════════════════════════════════════════════

def browser_scroll(
    direction: str = "down", amount: int = 500, selector: str = None
) -> dict:
    """direction: 'up' | 'down' | 'left' | 'right' | 'top' | 'bottom'"""
    try:
        p = _get_page()
        if direction == "top":
            p.evaluate("window.scrollTo(0, 0)")
        elif direction == "bottom":
            p.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "down":
            p.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            p.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "right":
            p.evaluate(f"window.scrollBy({amount}, 0)")
        elif direction == "left":
            p.evaluate(f"window.scrollBy(-{amount}, 0)")
        return {"ok": True, "scrolled": direction}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_scroll_to_element(selector: str) -> dict:
    try:
        _get_page().locator(selector).first.scroll_into_view_if_needed()
        return {"ok": True, "scrolled_to": selector}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  CONTENT EXTRACTION
# ═══════════════════════════════════════════════════════════

def browser_get_text(selector: str = None) -> dict:
    try:
        p = _get_page()
        if selector:
            return {"ok": True, "text": p.locator(selector).first.inner_text()}
        text = p.evaluate("""
            () => {
                const el = document.body.cloneNode(true);
                ['script','style','noscript'].forEach(t =>
                    el.querySelectorAll(t).forEach(n => n.remove()));
                return el.innerText.replace(/\\n{3,}/g, '\\n\\n').trim().slice(0, 15000);
            }
        """)
        return {"ok": True, "text": text, "url": p.url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_html(selector: str = None, outer: bool = False) -> dict:
    try:
        p = _get_page()
        if selector:
            el = p.locator(selector).first
            html = el.outer_html() if outer else el.inner_html()
        else:
            html = p.content()
        return {"ok": True, "html": html[:20000], "length": len(html)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_find_elements(selector: str, attributes: List[str] = None) -> dict:
    try:
        p = _get_page()
        locator = p.locator(selector)
        count = locator.count()
        items = []
        for i in range(min(count, 50)):
            el = locator.nth(i)
            try:
                item = {"index": i, "text": el.inner_text().strip()[:200]}
                for attr in (attributes or []):
                    try:
                        item[attr] = el.get_attribute(attr)
                    except Exception:
                        item[attr] = None
                items.append(item)
            except Exception:
                continue
        return {"ok": True, "count": count, "elements": items}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_attribute(selector: str, attribute: str, timeout: int = 10000) -> dict:
    try:
        value = _get_page().locator(selector).first.get_attribute(attribute, timeout=timeout)
        return {"ok": True, "selector": selector, "attribute": attribute, "value": value}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_value(selector: str, timeout: int = 10000) -> dict:
    try:
        value = _get_page().locator(selector).first.input_value(timeout=timeout)
        return {"ok": True, "selector": selector, "value": value}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  JAVASCRIPT
# ═══════════════════════════════════════════════════════════

def browser_execute_js(script: str, arg: Any = None) -> dict:
    """Run any JavaScript on the page and return the result."""
    try:
        p = _get_page()
        if arg is not None:
            result = p.evaluate(f"(arg) => {{ return {script} }}", arg)
        else:
            result = p.evaluate(script)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_inject_js(script: str) -> dict:
    try:
        _get_page().add_script_tag(content=script)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  FORMS
# ═══════════════════════════════════════════════════════════

def browser_fill_form(fields: Dict[str, str], submit_selector: str = None) -> dict:
    """Fill multiple fields and optionally submit.
    fields: {selector: value}  e.g. {"#email": "me@x.com", "#pass": "secret"}
    """
    try:
        p = _get_page()
        filled, errors = [], []
        for selector, value in fields.items():
            try:
                el = p.locator(selector).first
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    el.select_option(value=value)
                elif el.get_attribute("type") in ("checkbox", "radio"):
                    if value.lower() in ("true", "1", "yes", "on"):
                        el.check()
                    else:
                        el.uncheck()
                else:
                    el.clear()
                    el.fill(value)
                filled.append(selector)
            except Exception as e:
                errors.append({"selector": selector, "error": str(e)})

        result: dict = {"ok": len(errors) == 0, "filled": filled}
        if errors:
            result["errors"] = errors
        if submit_selector:
            try:
                p.locator(submit_selector).first.click()
                p.wait_for_load_state("domcontentloaded", timeout=10000)
                result["submitted"] = True
                result["url_after"] = p.url
            except Exception as e:
                result["submit_error"] = str(e)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_upload_file(selector: str, file_path: str, timeout: int = 10000) -> dict:
    try:
        path = Path(file_path).expanduser()
        if not path.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}
        _get_page().locator(selector).first.set_input_files(str(path), timeout=timeout)
        return {"ok": True, "uploaded": str(path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  SCREENSHOTS
# ═══════════════════════════════════════════════════════════

def browser_screenshot(
    selector: str = None, filename: str = None, full_page: bool = False
) -> dict:
    """Screenshot the page or an element. Saves to ~/Jarvis/screenshots/."""
    try:
        _ensure_dirs()
        p = _get_page()
        name = filename or f"screenshot_{int(time.time())}.png"
        if not name.endswith(".png"):
            name += ".png"
        path = SCREENSHOTS_DIR / name
        if selector:
            p.locator(selector).first.screenshot(path=str(path))
        else:
            p.screenshot(path=str(path), full_page=full_page)
        return {"ok": True, "path": str(path), "url": p.url, "full_page": full_page}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  WAITING
# ═══════════════════════════════════════════════════════════

def browser_wait_for(
    selector: str = None,
    url_pattern: str = None,
    state: str = "visible",
    timeout: int = 15000,
) -> dict:
    try:
        p = _get_page()
        if url_pattern:
            import re as _re
            p.wait_for_url(_re.compile(url_pattern), timeout=timeout)
            return {"ok": True, "url": p.url}
        if selector:
            p.locator(selector).first.wait_for(state=state, timeout=timeout)
            return {"ok": True, "found": selector, "state": state}
        p.wait_for_load_state("networkidle", timeout=timeout)
        return {"ok": True, "waited": "networkidle"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_wait_ms(ms: int = 1000) -> dict:
    try:
        _get_page().wait_for_timeout(ms)
        return {"ok": True, "waited_ms": ms}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  COOKIES & STORAGE
# ═══════════════════════════════════════════════════════════

def browser_get_cookies(url: str = None) -> dict:
    try:
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        cookies = _context.cookies(urls=[url] if url else None)
        return {"ok": True, "cookies": cookies, "count": len(cookies)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_set_cookie(
    name: str, value: str, domain: str = None, path: str = "/", secure: bool = False
) -> dict:
    try:
        p = _get_page()
        from urllib.parse import urlparse
        cookie = {
            "name": name, "value": value, "path": path, "secure": secure,
            "domain": domain or urlparse(p.url).hostname or "localhost",
        }
        _context.add_cookies([cookie])
        return {"ok": True, "set": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_clear_cookies() -> dict:
    try:
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        _context.clear_cookies()
        return {"ok": True, "cleared": "all cookies"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_local_storage(key: str = None) -> dict:
    try:
        p = _get_page()
        if key:
            val = p.evaluate(f"localStorage.getItem('{key}')")
            return {"ok": True, "key": key, "value": val}
        data = p.evaluate("Object.fromEntries(Object.entries(localStorage))")
        return {"ok": True, "storage": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_set_local_storage(key: str, value: str) -> dict:
    try:
        _get_page().evaluate(f"localStorage.setItem('{key}', '{value}')")
        return {"ok": True, "set": key}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  DOWNLOADS & NETWORK
# ═══════════════════════════════════════════════════════════

def browser_download(url: str, filename: str = None) -> dict:
    """Download a file. Saves to ~/Jarvis/downloads/."""
    try:
        _ensure_dirs()
        p = _get_page()
        nav_url = url if url.startswith("http") else "https://" + url
        with p.expect_download() as dl_info:
            p.goto(nav_url)
        download = dl_info.value
        name = filename or download.suggested_filename or f"download_{int(time.time())}"
        dest = DOWNLOADS_DIR / name
        download.save_as(str(dest))
        return {"ok": True, "path": str(dest), "filename": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_intercept_next_request(url_pattern: str = "**/*") -> dict:
    """Capture the next network response."""
    try:
        p = _get_page()
        captured = {}

        def handle(response):
            if not captured:
                try:
                    captured.update({
                        "url": response.url, "status": response.status,
                        "headers": dict(response.headers), "body": response.text()[:5000],
                    })
                except Exception:
                    pass

        p.on("response", handle)
        p.wait_for_timeout(5000)
        p.remove_listener("response", handle)
        return {"ok": bool(captured), "response": captured}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  DIALOGS & FRAMES
# ═══════════════════════════════════════════════════════════

def browser_handle_dialog(action: str = "accept", text: str = "") -> dict:
    try:
        def _handler(dialog):
            if action == "accept":
                dialog.accept(text or "")
            else:
                dialog.dismiss()
        _get_page().once("dialog", _handler)
        return {"ok": True, "configured": action}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_frames() -> dict:
    try:
        p = _get_page()
        frames = [{"index": i, "name": f.name, "url": f.url} for i, f in enumerate(p.frames)]
        return {"ok": True, "frames": frames}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_frame_execute_js(frame_index: int, script: str) -> dict:
    try:
        p = _get_page()
        frames = p.frames
        if frame_index >= len(frames):
            return {"ok": False, "error": f"Frame {frame_index} not found (total: {len(frames)})"}
        return {"ok": True, "result": frames[frame_index].evaluate(script)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  PAGE INFO & HIGHLIGHTING
# ═══════════════════════════════════════════════════════════

def browser_get_page_info() -> dict:
    try:
        p = _get_page()
        info = p.evaluate("""
        () => {
            const links = Array.from(document.querySelectorAll('a[href]')).slice(0,30)
                .map(a => ({text: a.innerText.trim().slice(0,80), href: a.href}));
            const inputs = Array.from(document.querySelectorAll('input,textarea,select')).slice(0,20)
                .map(el => ({
                    tag: el.tagName.toLowerCase(), type: el.type||null,
                    id: el.id||null, name: el.name||null,
                    placeholder: el.placeholder||null,
                    value: (el.type!=='password' ? el.value : '***')||null
                }));
            const meta = {};
            document.querySelectorAll('meta[name],meta[property]').forEach(m => {
                meta[m.getAttribute('name')||m.getAttribute('property')] = m.getAttribute('content');
            });
            return { title: document.title, links, inputs,
                     forms: document.forms.length, images: document.images.length,
                     description: meta['description']||meta['og:description']||null };
        }
        """)
        info["url"] = p.url
        return {"ok": True, **info}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_highlight(selector: str, color: str = "red", duration_ms: int = 2000) -> dict:
    try:
        _get_page().evaluate(f"""
        () => {{
            const el = document.querySelector('{selector}');
            if (!el) return;
            const orig = el.style.outline;
            el.style.outline = '4px solid {color}';
            el.scrollIntoView({{behavior:'smooth',block:'center'}});
            setTimeout(() => el.style.outline = orig, {duration_ms});
        }}
        """)
        return {"ok": True, "highlighted": selector}
    except Exception as e:
        return {"ok": False, "error": str(e)}
