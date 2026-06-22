"""
Browser Control - Full Playwright-based browser automation for J.A.R.V.I.S
Uses the sync Playwright API so it works cleanly when called from FastAPI's
thread pool (run_in_executor) without any event-loop conflicts.

Install:
    pip install playwright
    python -m playwright install chromium
"""

import logging
import os
import time
import threading
import traceback
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Logger setup ──────────────────────────────────────────────────────────────
log = logging.getLogger("browser")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[BROWSER] %(asctime)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    log.addHandler(_handler)
log.setLevel(logging.DEBUG)


DOWNLOADS_DIR   = Path.home() / "Jarvis" / "downloads"
SCREENSHOTS_DIR = Path.home() / "Jarvis" / "screenshots"


def _ensure_dirs():
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Singleton browser state ───────────────────────────────────────────────────
_lock        = threading.Lock()
_pw          = None
_browser     = None
_context     = None
_active_page = None          # named _active_page to avoid shadowing


def _attach_page_listeners(page):
    """Wire up per-page event listeners for detailed logging."""

    def on_request(req):
        if req.resource_type in ("document", "xhr", "fetch"):
            log.debug("→ REQUEST  %s  %s", req.method, req.url[:120])

    def on_response(resp):
        if resp.request.resource_type in ("document", "xhr", "fetch"):
            status = resp.status
            level = logging.WARNING if status >= 400 else logging.DEBUG
            log.log(level, "← RESPONSE %s  %s  %s",
                    status, resp.request.method, resp.url[:120])

    def on_console(msg):
        lvl = {
            "error": logging.ERROR,
            "warning": logging.WARNING,
        }.get(msg.type, logging.DEBUG)
        log.log(lvl, "PAGE CONSOLE [%s] %s", msg.type, msg.text[:200])

    def on_pageerror(exc):
        log.error("PAGE ERROR  %s", exc)

    def on_crash(_):
        log.critical("PAGE CRASHED")

    def on_dialog(dialog):
        log.info("DIALOG [%s] message=%r  defaultValue=%r",
                 dialog.type, dialog.message, dialog.default_value)

    def on_load(_):
        try:
            log.info("PAGE LOAD COMPLETE  url=%s  title=%r", page.url, page.title())
        except Exception:
            pass

    page.on("request",   on_request)
    page.on("response",  on_response)
    page.on("console",   on_console)
    page.on("pageerror", on_pageerror)
    page.on("crash",     on_crash)
    page.on("dialog",    on_dialog)
    page.on("load",      on_load)


def _tool(fn):
    """Decorator: log every browser tool call — args, result, duration, errors."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Build a compact arg summary for the log line
        arg_parts = [repr(a)[:60] for a in args]
        arg_parts += [f"{k}={repr(v)[:60]}" for k, v in kwargs.items()]
        arg_str = ", ".join(arg_parts) or "()"
        log.info("CALL  %s(%s)", fn.__name__, arg_str)
        t0 = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            ok = result.get("ok", "?") if isinstance(result, dict) else "?"
            if ok is True or ok == "?":
                log.info("DONE  %s  ok=%s  %.0fms", fn.__name__, ok, elapsed)
            else:
                err = result.get("error", "") if isinstance(result, dict) else ""
                log.warning("FAIL  %s  ok=%s  %.0fms  error=%r",
                             fn.__name__, ok, elapsed, err)
            return result
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            log.error("EXCEPTION  %s  %.0fms\n%s",
                      fn.__name__, elapsed, traceback.format_exc())
            return {"ok": False, "error": str(exc)}
    return wrapper


def _get_page(headless: bool = False):
    """Return the active Page, launching browser/context/page if needed."""
    global _pw, _browser, _context, _active_page
    with _lock:
        from playwright.sync_api import sync_playwright

        if _pw is None:
            log.info("Starting Playwright …")
            _pw = sync_playwright().start()
            log.info("Playwright started  (sync API)")

        if _browser is None or not _browser.is_connected():
            log.info("Launching Chromium  headless=%s", headless)
            _browser = _pw.chromium.launch(
                headless=headless,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            log.info("Chromium launched  version=%s", _browser.version)

        if _context is None:
            _ensure_dirs()
            log.info("Creating browser context  downloads=%s", DOWNLOADS_DIR)
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
            log.info("Browser context created")

        if _active_page is None or _active_page.is_closed():
            pages = _context.pages
            log.debug("Active page is None/closed; existing pages=%d", len(pages))
            _active_page = pages[0] if pages else _context.new_page()
            _attach_page_listeners(_active_page)
            log.info("Active page ready  url=%s", _active_page.url)

        return _active_page


# ═══════════════════════════════════════════════════════════
#  NAVIGATION
# ═══════════════════════════════════════════════════════════

@_tool
def browser_open(url: str, wait_until: str = "domcontentloaded") -> dict:
    """Navigate to a URL. Opens the browser if not already running."""
    p = _get_page()
    if not url.startswith("http"):
        url = "https://" + url
    log.debug("Navigating to %s  wait_until=%s", url, wait_until)
    t0 = time.perf_counter()
    p.goto(url, wait_until=wait_until, timeout=30000)
    log.info("Navigation complete  %.0fms  url=%s  title=%r",
             (time.perf_counter()-t0)*1000, p.url, p.title())
    return {"ok": True, "url": p.url, "title": p.title()}


@_tool
def browser_back() -> dict:
    p = _get_page()
    p.go_back(wait_until="domcontentloaded", timeout=10000)
    return {"ok": True, "url": p.url, "title": p.title()}


@_tool
def browser_forward() -> dict:
    p = _get_page()
    p.go_forward(wait_until="domcontentloaded", timeout=10000)
    return {"ok": True, "url": p.url, "title": p.title()}


@_tool
def browser_refresh() -> dict:
    p = _get_page()
    p.reload(wait_until="domcontentloaded", timeout=15000)
    return {"ok": True, "url": p.url, "title": p.title()}


@_tool
def browser_get_url() -> dict:
    p = _get_page()
    return {"ok": True, "url": p.url, "title": p.title()}


# ═══════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════

@_tool
def browser_new_tab(url: str = "about:blank") -> dict:
    global _active_page
    with _lock:
        _get_page()
        new_p = _context.new_page()
        _attach_page_listeners(new_p)
        _active_page = new_p
    log.info("New tab opened (index=%d)", len(_context.pages)-1)
    if url and url != "about:blank":
        nav_url = url if url.startswith("http") else "https://" + url
        new_p.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
    tabs = _context.pages
    return {
        "ok": True, "url": new_p.url, "title": new_p.title(),
        "tab_index": tabs.index(new_p), "total_tabs": len(tabs),
    }


@_tool
def browser_list_tabs() -> dict:
    if _context is None:
        return {"ok": True, "tabs": []}
    tabs = []
    for i, pg in enumerate(_context.pages):
        try:
            tabs.append({
                "index": i, "url": pg.url,
                "title": pg.title(), "active": pg is _active_page
            })
        except Exception:
            tabs.append({"index": i, "url": "unknown", "title": "unknown", "active": False})
    log.debug("Tabs: %s", [(t["index"], t["url"][:60]) for t in tabs])
    return {"ok": True, "tabs": tabs}


@_tool
def browser_switch_tab(index: int) -> dict:
    global _active_page
    if _context is None:
        return {"ok": False, "error": "No browser open"}
    tabs = _context.pages
    if index < 0 or index >= len(tabs):
        return {"ok": False, "error": f"Tab index {index} out of range (0–{len(tabs)-1})"}
    with _lock:
        _active_page = tabs[index]
    _active_page.bring_to_front()
    log.info("Switched to tab %d  url=%s", index, _active_page.url)
    return {"ok": True, "url": _active_page.url, "title": _active_page.title()}


@_tool
def browser_close_tab(index: int = -1) -> dict:
    global _active_page
    if _context is None:
        return {"ok": False, "error": "No browser open"}
    tabs = _context.pages
    if not tabs:
        return {"ok": False, "error": "No tabs open"}
    tab = tabs[index] if index >= 0 else _active_page
    log.info("Closing tab  url=%s", tab.url)
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


@_tool
def browser_close() -> dict:
    global _pw, _browser, _context, _active_page
    log.info("Closing browser …")
    with _lock:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
        _pw = _browser = _context = _active_page = None
    log.info("Browser closed and Playwright stopped")
    return {"ok": True, "message": "Browser closed"}


# ═══════════════════════════════════════════════════════════
#  CLICKING & MOUSE
# ═══════════════════════════════════════════════════════════

@_tool
def browser_click(
    selector: str = None,
    x: int = None,
    y: int = None,
    button: str = "left",
    double: bool = False,
    timeout: int = 10000,
) -> dict:
    p = _get_page()
    if x is not None and y is not None:
        log.debug("Mouse %s-click at (%d, %d)", "double" if double else button, x, y)
        if double:
            p.mouse.dblclick(x, y)
        else:
            p.mouse.click(x, y, button=button)
        return {"ok": True, "clicked": f"({x}, {y})"}
    if selector:
        log.debug("Element %s-click  selector=%r", "double" if double else button, selector)
        el = p.locator(selector).first
        if double:
            el.dblclick(timeout=timeout)
        else:
            el.click(button=button, timeout=timeout)
        return {"ok": True, "clicked": selector}
    return {"ok": False, "error": "Provide selector or x/y coordinates"}


@_tool
def browser_right_click(selector: str = None, x: int = None, y: int = None) -> dict:
    return browser_click.__wrapped__(selector=selector, x=x, y=y, button="right")


@_tool
def browser_hover(
    selector: str = None, x: int = None, y: int = None, timeout: int = 10000
) -> dict:
    p = _get_page()
    if x is not None and y is not None:
        p.mouse.move(x, y)
        return {"ok": True, "hovered": f"({x}, {y})"}
    if selector:
        p.locator(selector).first.hover(timeout=timeout)
        return {"ok": True, "hovered": selector}
    return {"ok": False, "error": "Provide selector or coordinates"}


@_tool
def browser_drag(
    from_selector: str = None, to_selector: str = None,
    from_x: int = None, from_y: int = None,
    to_x: int = None, to_y: int = None,
) -> dict:
    p = _get_page()
    if from_x is not None and to_x is not None:
        log.debug("Drag (%d,%d) → (%d,%d)", from_x, from_y, to_x, to_y)
        p.mouse.move(from_x, from_y)
        p.mouse.down()
        p.mouse.move(to_x, to_y, steps=10)
        p.mouse.up()
        return {"ok": True, "dragged": f"({from_x},{from_y}) → ({to_x},{to_y})"}
    if from_selector and to_selector:
        p.locator(from_selector).first.drag_to(p.locator(to_selector).first)
        return {"ok": True, "dragged": f"{from_selector} → {to_selector}"}
    return {"ok": False, "error": "Provide from/to selectors or coordinates"}


# ═══════════════════════════════════════════════════════════
#  KEYBOARD & TYPING
# ═══════════════════════════════════════════════════════════

@_tool
def browser_type(
    selector: str,
    text: str,
    clear_first: bool = True,
    press_enter: bool = False,
    timeout: int = 10000,
) -> dict:
    p = _get_page()
    preview = text[:40] + ("…" if len(text) > 40 else "")
    log.debug("Type into %r  text=%r  clear=%s  enter=%s", selector, preview, clear_first, press_enter)
    el = p.locator(selector).first
    el.wait_for(state="visible", timeout=timeout)
    if clear_first:
        el.clear()
    el.fill(text)
    if press_enter:
        el.press("Enter")
    return {"ok": True, "typed": preview, "selector": selector}


@_tool
def browser_press_key(key: str, selector: str = None) -> dict:
    p = _get_page()
    log.debug("Press key=%r  selector=%r", key, selector)
    if selector:
        p.locator(selector).first.press(key)
    else:
        p.keyboard.press(key)
    return {"ok": True, "pressed": key}


@_tool
def browser_clear_input(selector: str, timeout: int = 10000) -> dict:
    _get_page().locator(selector).first.clear(timeout=timeout)
    return {"ok": True, "cleared": selector}


@_tool
def browser_select_option(
    selector: str,
    value: str = None, label: str = None, index: int = None,
    timeout: int = 10000,
) -> dict:
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


@_tool
def browser_check(selector: str, timeout: int = 10000) -> dict:
    _get_page().locator(selector).first.check(timeout=timeout)
    return {"ok": True, "checked": selector}


@_tool
def browser_uncheck(selector: str, timeout: int = 10000) -> dict:
    _get_page().locator(selector).first.uncheck(timeout=timeout)
    return {"ok": True, "unchecked": selector}


# ═══════════════════════════════════════════════════════════
#  SCROLLING
# ═══════════════════════════════════════════════════════════

@_tool
def browser_scroll(
    direction: str = "down", amount: int = 500, selector: str = None
) -> dict:
    p = _get_page()
    log.debug("Scroll %s  amount=%d", direction, amount)
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


@_tool
def browser_scroll_to_element(selector: str) -> dict:
    _get_page().locator(selector).first.scroll_into_view_if_needed()
    return {"ok": True, "scrolled_to": selector}


# ═══════════════════════════════════════════════════════════
#  CONTENT EXTRACTION
# ═══════════════════════════════════════════════════════════

@_tool
def browser_get_text(selector: str = None) -> dict:
    p = _get_page()
    if selector:
        text = p.locator(selector).first.inner_text()
        log.debug("Got text from %r  len=%d", selector, len(text))
        return {"ok": True, "text": text}
    text = p.evaluate("""
        () => {
            const el = document.body.cloneNode(true);
            ['script','style','noscript'].forEach(t =>
                el.querySelectorAll(t).forEach(n => n.remove()));
            return el.innerText.replace(/\\n{3,}/g, '\\n\\n').trim().slice(0, 15000);
        }
    """)
    log.debug("Got full page text  len=%d  url=%s", len(text), p.url)
    return {"ok": True, "text": text, "url": p.url}


@_tool
def browser_get_html(selector: str = None, outer: bool = False) -> dict:
    p = _get_page()
    if selector:
        el = p.locator(selector).first
        html = el.outer_html() if outer else el.inner_html()
    else:
        html = p.content()
    log.debug("Got HTML  len=%d  selector=%r", len(html), selector)
    return {"ok": True, "html": html[:20000], "length": len(html)}


@_tool
def browser_find_elements(selector: str, attributes: List[str] = None) -> dict:
    p = _get_page()
    locator = p.locator(selector)
    count = locator.count()
    log.debug("Found %d elements for selector=%r", count, selector)
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
        except Exception as e:
            log.debug("Element %d skipped: %s", i, e)
    return {"ok": True, "count": count, "elements": items}


@_tool
def browser_get_attribute(selector: str, attribute: str, timeout: int = 10000) -> dict:
    value = _get_page().locator(selector).first.get_attribute(attribute, timeout=timeout)
    log.debug("Attribute %r of %r = %r", attribute, selector, value)
    return {"ok": True, "selector": selector, "attribute": attribute, "value": value}


@_tool
def browser_get_value(selector: str, timeout: int = 10000) -> dict:
    value = _get_page().locator(selector).first.input_value(timeout=timeout)
    return {"ok": True, "selector": selector, "value": value}


# ═══════════════════════════════════════════════════════════
#  JAVASCRIPT
# ═══════════════════════════════════════════════════════════

@_tool
def browser_execute_js(script: str, arg: Any = None) -> dict:
    p = _get_page()
    log.debug("Execute JS  script=%r", script[:80])
    if arg is not None:
        result = p.evaluate(f"(arg) => {{ return {script} }}", arg)
    else:
        result = p.evaluate(script)
    log.debug("JS result: %r", str(result)[:120])
    return {"ok": True, "result": result}


@_tool
def browser_inject_js(script: str) -> dict:
    _get_page().add_script_tag(content=script)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
#  FORMS
# ═══════════════════════════════════════════════════════════

@_tool
def browser_fill_form(fields: Dict[str, str], submit_selector: str = None) -> dict:
    p = _get_page()
    log.info("Filling form  fields=%d  submit=%r", len(fields), submit_selector)
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
            log.debug("  Filled %r = %r", selector, value[:40] if value else "")
            filled.append(selector)
        except Exception as e:
            log.warning("  Failed to fill %r: %s", selector, e)
            errors.append({"selector": selector, "error": str(e)})

    result: dict = {"ok": len(errors) == 0, "filled": filled}
    if errors:
        result["errors"] = errors
    if submit_selector:
        try:
            log.debug("Submitting form via %r", submit_selector)
            p.locator(submit_selector).first.click()
            p.wait_for_load_state("domcontentloaded", timeout=10000)
            log.info("Form submitted  url_after=%s", p.url)
            result["submitted"] = True
            result["url_after"] = p.url
        except Exception as e:
            log.warning("Form submit failed: %s", e)
            result["submit_error"] = str(e)
    return result


@_tool
def browser_upload_file(selector: str, file_path: str, timeout: int = 10000) -> dict:
    path = Path(file_path).expanduser()
    if not path.exists():
        return {"ok": False, "error": f"File not found: {file_path}"}
    log.info("Uploading file  path=%s  selector=%r", path, selector)
    _get_page().locator(selector).first.set_input_files(str(path), timeout=timeout)
    return {"ok": True, "uploaded": str(path)}


# ═══════════════════════════════════════════════════════════
#  SCREENSHOTS
# ═══════════════════════════════════════════════════════════

@_tool
def browser_screenshot(
    selector: str = None, filename: str = None, full_page: bool = False
) -> dict:
    _ensure_dirs()
    p = _get_page()
    name = filename or f"screenshot_{int(time.time())}.png"
    if not name.endswith(".png"):
        name += ".png"
    path = SCREENSHOTS_DIR / name
    log.info("Screenshot → %s  selector=%r  full_page=%s", path, selector, full_page)
    if selector:
        p.locator(selector).first.screenshot(path=str(path))
    else:
        p.screenshot(path=str(path), full_page=full_page)
    size_kb = path.stat().st_size // 1024
    log.info("Screenshot saved  %d KB", size_kb)
    return {"ok": True, "path": str(path), "url": p.url, "full_page": full_page, "size_kb": size_kb}


# ═══════════════════════════════════════════════════════════
#  WAITING
# ═══════════════════════════════════════════════════════════

@_tool
def browser_wait_for(
    selector: str = None,
    url_pattern: str = None,
    state: str = "visible",
    timeout: int = 15000,
) -> dict:
    p = _get_page()
    if url_pattern:
        import re as _re
        log.debug("Waiting for URL pattern %r  timeout=%d", url_pattern, timeout)
        p.wait_for_url(_re.compile(url_pattern), timeout=timeout)
        return {"ok": True, "url": p.url}
    if selector:
        log.debug("Waiting for selector %r  state=%s  timeout=%d", selector, state, timeout)
        p.locator(selector).first.wait_for(state=state, timeout=timeout)
        return {"ok": True, "found": selector, "state": state}
    log.debug("Waiting for networkidle  timeout=%d", timeout)
    p.wait_for_load_state("networkidle", timeout=timeout)
    return {"ok": True, "waited": "networkidle"}


@_tool
def browser_wait_ms(ms: int = 1000) -> dict:
    log.debug("Waiting %d ms", ms)
    _get_page().wait_for_timeout(ms)
    return {"ok": True, "waited_ms": ms}


# ═══════════════════════════════════════════════════════════
#  COOKIES & STORAGE
# ═══════════════════════════════════════════════════════════

@_tool
def browser_get_cookies(url: str = None) -> dict:
    if _context is None:
        return {"ok": False, "error": "No browser open"}
    cookies = _context.cookies(urls=[url] if url else None)
    log.debug("Got %d cookies", len(cookies))
    return {"ok": True, "cookies": cookies, "count": len(cookies)}


@_tool
def browser_set_cookie(
    name: str, value: str, domain: str = None, path: str = "/", secure: bool = False
) -> dict:
    p = _get_page()
    from urllib.parse import urlparse
    cookie = {
        "name": name, "value": value, "path": path, "secure": secure,
        "domain": domain or urlparse(p.url).hostname or "localhost",
    }
    log.debug("Set cookie  name=%r  domain=%r", name, cookie["domain"])
    _context.add_cookies([cookie])
    return {"ok": True, "set": name}


@_tool
def browser_clear_cookies() -> dict:
    if _context is None:
        return {"ok": False, "error": "No browser open"}
    _context.clear_cookies()
    log.info("All cookies cleared")
    return {"ok": True, "cleared": "all cookies"}


@_tool
def browser_get_local_storage(key: str = None) -> dict:
    p = _get_page()
    if key:
        val = p.evaluate(f"localStorage.getItem('{key}')")
        return {"ok": True, "key": key, "value": val}
    data = p.evaluate("Object.fromEntries(Object.entries(localStorage))")
    log.debug("LocalStorage: %d keys", len(data))
    return {"ok": True, "storage": data}


@_tool
def browser_set_local_storage(key: str, value: str) -> dict:
    _get_page().evaluate(f"localStorage.setItem('{key}', '{value}')")
    return {"ok": True, "set": key}


# ═══════════════════════════════════════════════════════════
#  DOWNLOADS & NETWORK
# ═══════════════════════════════════════════════════════════

@_tool
def browser_download(url: str, filename: str = None) -> dict:
    _ensure_dirs()
    p = _get_page()
    nav_url = url if url.startswith("http") else "https://" + url
    log.info("Starting download  url=%s", nav_url)
    with p.expect_download() as dl_info:
        p.goto(nav_url)
    download = dl_info.value
    name = filename or download.suggested_filename or f"download_{int(time.time())}"
    dest = DOWNLOADS_DIR / name
    download.save_as(str(dest))
    size_kb = dest.stat().st_size // 1024
    log.info("Download complete  path=%s  %d KB", dest, size_kb)
    return {"ok": True, "path": str(dest), "filename": name, "size_kb": size_kb}


@_tool
def browser_intercept_next_request(url_pattern: str = "**/*") -> dict:
    p = _get_page()
    log.info("Intercepting next response  pattern=%r", url_pattern)
    captured = {}

    def handle(response):
        if not captured:
            try:
                captured.update({
                    "url": response.url, "status": response.status,
                    "headers": dict(response.headers), "body": response.text()[:5000],
                })
                log.debug("Intercepted  status=%d  url=%s", response.status, response.url[:120])
            except Exception:
                pass

    p.on("response", handle)
    p.wait_for_timeout(5000)
    p.remove_listener("response", handle)
    return {"ok": bool(captured), "response": captured}


# ═══════════════════════════════════════════════════════════
#  DIALOGS & FRAMES
# ═══════════════════════════════════════════════════════════

@_tool
def browser_handle_dialog(action: str = "accept", text: str = "") -> dict:
    def _handler(dialog):
        log.info("Dialog auto-%s  type=%s  msg=%r", action, dialog.type, dialog.message[:80])
        if action == "accept":
            dialog.accept(text or "")
        else:
            dialog.dismiss()
    _get_page().once("dialog", _handler)
    return {"ok": True, "configured": action}


@_tool
def browser_get_frames() -> dict:
    p = _get_page()
    frames = [{"index": i, "name": f.name, "url": f.url} for i, f in enumerate(p.frames)]
    log.debug("Frames: %d", len(frames))
    return {"ok": True, "frames": frames}


@_tool
def browser_frame_execute_js(frame_index: int, script: str) -> dict:
    p = _get_page()
    frames = p.frames
    if frame_index >= len(frames):
        return {"ok": False, "error": f"Frame {frame_index} not found (total: {len(frames)})"}
    log.debug("Execute JS in frame %d", frame_index)
    return {"ok": True, "result": frames[frame_index].evaluate(script)}


# ═══════════════════════════════════════════════════════════
#  PAGE INFO & HIGHLIGHTING
# ═══════════════════════════════════════════════════════════

@_tool
def browser_get_page_info() -> dict:
    p = _get_page()
    log.debug("Getting page info  url=%s", p.url)
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
    log.debug("Page info: title=%r  links=%d  inputs=%d", info.get("title"), len(info.get("links",[])), len(info.get("inputs",[])))
    info["url"] = p.url
    return {"ok": True, **info}


@_tool
def browser_highlight(selector: str, color: str = "red", duration_ms: int = 2000) -> dict:
    log.debug("Highlight %r  color=%s", selector, color)
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
