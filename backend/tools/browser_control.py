"""
Browser Control - Full Playwright-based browser automation for J.A.R.V.I.S
Gives complete control over any browser: navigation, clicking, typing,
JavaScript execution, form filling, screenshots, tabs, downloads, cookies, and more.
"""

import asyncio
import os
import base64
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

# ── Singleton browser state ───────────────────────────────────────────────────
_browser = None
_context = None
_page = None
_playwright = None
_loop = None

DOWNLOADS_DIR = Path.home() / "Jarvis" / "downloads"
SCREENSHOTS_DIR = Path.home() / "Jarvis" / "screenshots"


def _ensure_dirs():
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _get_or_create_loop():
    global _loop
    try:
        _loop = asyncio.get_event_loop()
        if _loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _run(coro):
    """Run an async coroutine from sync context."""
    loop = _get_or_create_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(asyncio.run, coro)
            return fut.result(timeout=60)
    return loop.run_until_complete(coro)


async def _ensure_browser(headless: bool = False):
    """Launch browser if not already open. Stays open between calls."""
    global _browser, _context, _page, _playwright
    _ensure_dirs()

    if _playwright is None:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()

    if _browser is None or not _browser.is_connected():
        _browser = await _playwright.chromium.launch(
            headless=headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )

    if _context is None:
        _context = await _browser.new_context(
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
            downloads_path=str(DOWNLOADS_DIR),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

    if _page is None or _page.is_closed():
        pages = _context.pages
        _page = pages[0] if pages else await _context.new_page()

    return _page


async def _get_page():
    """Get the current active page, launching browser if needed."""
    global _page
    if _page is None or _page.is_closed():
        await _ensure_browser()
    return _page


# ═══════════════════════════════════════════════════════════
#  NAVIGATION
# ═══════════════════════════════════════════════════════════

def browser_open(url: str, wait_until: str = "domcontentloaded") -> dict:
    """Navigate to a URL. Opens the browser if it's not running."""
    async def _go():
        page = await _ensure_browser()
        if not url.startswith("http"):
            full_url = "https://" + url
        else:
            full_url = url
        await page.goto(full_url, wait_until=wait_until, timeout=30000)
        title = await page.title()
        return {"ok": True, "url": page.url, "title": title}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_back() -> dict:
    """Go back in browser history."""
    async def _go():
        page = await _get_page()
        await page.go_back(wait_until="domcontentloaded", timeout=10000)
        return {"ok": True, "url": page.url, "title": await page.title()}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_forward() -> dict:
    """Go forward in browser history."""
    async def _go():
        page = await _get_page()
        await page.go_forward(wait_until="domcontentloaded", timeout=10000)
        return {"ok": True, "url": page.url, "title": await page.title()}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_refresh() -> dict:
    """Reload the current page."""
    async def _go():
        page = await _get_page()
        await page.reload(wait_until="domcontentloaded", timeout=15000)
        return {"ok": True, "url": page.url, "title": await page.title()}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_url() -> dict:
    """Get the current page URL and title."""
    async def _go():
        page = await _get_page()
        return {"ok": True, "url": page.url, "title": await page.title()}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════

def browser_new_tab(url: str = "about:blank") -> dict:
    """Open a new tab and optionally navigate to a URL."""
    async def _go():
        global _page
        page_new = await _context.new_page()
        _page = page_new
        if url and url != "about:blank":
            nav_url = url if url.startswith("http") else "https://" + url
            await page_new.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
        title = await page_new.title()
        tabs = _context.pages
        return {"ok": True, "url": page_new.url, "title": title, "tab_index": tabs.index(page_new), "total_tabs": len(tabs)}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_list_tabs() -> dict:
    """List all open tabs."""
    async def _go():
        if _context is None:
            return {"ok": True, "tabs": []}
        tabs = []
        for i, p in enumerate(_context.pages):
            try:
                tabs.append({"index": i, "url": p.url, "title": await p.title(), "active": p == _page})
            except Exception:
                tabs.append({"index": i, "url": "unknown", "title": "unknown", "active": False})
        return {"ok": True, "tabs": tabs}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_switch_tab(index: int) -> dict:
    """Switch to a tab by its index (0-based)."""
    async def _go():
        global _page
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        tabs = _context.pages
        if index < 0 or index >= len(tabs):
            return {"ok": False, "error": f"Tab index {index} out of range (0-{len(tabs)-1})"}
        _page = tabs[index]
        await _page.bring_to_front()
        return {"ok": True, "url": _page.url, "title": await _page.title()}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_close_tab(index: int = -1) -> dict:
    """Close a tab. Defaults to the current active tab."""
    async def _go():
        global _page
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        tabs = _context.pages
        if not tabs:
            return {"ok": False, "error": "No tabs open"}
        tab = tabs[index] if index >= 0 else _page
        await tab.close()
        remaining = _context.pages
        if remaining:
            _page = remaining[-1]
            await _page.bring_to_front()
            return {"ok": True, "remaining_tabs": len(remaining), "current_url": _page.url}
        else:
            _page = None
            return {"ok": True, "remaining_tabs": 0}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_close() -> dict:
    """Close the browser entirely."""
    global _browser, _context, _page, _playwright
    async def _go():
        global _browser, _context, _page, _playwright
        if _browser:
            await _browser.close()
        if _playwright:
            await _playwright.stop()
        _browser = _context = _page = _playwright = None
        return {"ok": True, "message": "Browser closed"}
    try:
        return _run(_go())
    except Exception as e:
        _browser = _context = _page = _playwright = None
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  CLICKING & MOUSE
# ═══════════════════════════════════════════════════════════

def browser_click(selector: str = None, x: int = None, y: int = None,
                  button: str = "left", double: bool = False, timeout: int = 10000) -> dict:
    """
    Click an element by CSS selector, XPath, text, or screen coordinates.
    Examples:
      browser_click(selector="#submit-btn")
      browser_click(selector="text=Sign in")
      browser_click(x=500, y=300)
    """
    async def _go():
        page = await _get_page()
        if x is not None and y is not None:
            if double:
                await page.mouse.dblclick(x, y)
            else:
                await page.mouse.click(x, y, button=button)
            return {"ok": True, "clicked": f"({x}, {y})"}
        if selector:
            el = page.locator(selector).first
            if double:
                await el.dblclick(timeout=timeout)
            else:
                await el.click(button=button, timeout=timeout)
            return {"ok": True, "clicked": selector}
        return {"ok": False, "error": "Provide selector or x/y coordinates"}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_right_click(selector: str = None, x: int = None, y: int = None) -> dict:
    """Right-click an element or coordinates."""
    return browser_click(selector=selector, x=x, y=y, button="right")


def browser_hover(selector: str = None, x: int = None, y: int = None, timeout: int = 10000) -> dict:
    """Hover over an element or coordinates."""
    async def _go():
        page = await _get_page()
        if x is not None and y is not None:
            await page.mouse.move(x, y)
            return {"ok": True, "hovered": f"({x}, {y})"}
        if selector:
            await page.locator(selector).first.hover(timeout=timeout)
            return {"ok": True, "hovered": selector}
        return {"ok": False, "error": "Provide selector or coordinates"}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_drag(from_selector: str = None, to_selector: str = None,
                 from_x: int = None, from_y: int = None,
                 to_x: int = None, to_y: int = None) -> dict:
    """Drag from one element/position to another."""
    async def _go():
        page = await _get_page()
        if from_x is not None and to_x is not None:
            await page.mouse.move(from_x, from_y)
            await page.mouse.down()
            await page.mouse.move(to_x, to_y, steps=10)
            await page.mouse.up()
            return {"ok": True, "dragged": f"({from_x},{from_y}) → ({to_x},{to_y})"}
        if from_selector and to_selector:
            src = page.locator(from_selector).first
            dst = page.locator(to_selector).first
            await src.drag_to(dst)
            return {"ok": True, "dragged": f"{from_selector} → {to_selector}"}
        return {"ok": False, "error": "Provide from/to selectors or coordinates"}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  KEYBOARD & TYPING
# ═══════════════════════════════════════════════════════════

def browser_type(selector: str, text: str, clear_first: bool = True,
                 press_enter: bool = False, timeout: int = 10000) -> dict:
    """Type text into an input field."""
    async def _go():
        page = await _get_page()
        el = page.locator(selector).first
        await el.wait_for(state="visible", timeout=timeout)
        if clear_first:
            await el.clear()
        await el.fill(text)
        if press_enter:
            await el.press("Enter")
        return {"ok": True, "typed": text[:80] + ("..." if len(text) > 80 else ""), "selector": selector}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_press_key(key: str, selector: str = None) -> dict:
    """
    Press a keyboard key. Works globally or on a specific element.
    Examples: 'Enter', 'Escape', 'Tab', 'ArrowDown', 'Control+a', 'Control+c'
    """
    async def _go():
        page = await _get_page()
        if selector:
            await page.locator(selector).first.press(key)
        else:
            await page.keyboard.press(key)
        return {"ok": True, "pressed": key}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_clear_input(selector: str, timeout: int = 10000) -> dict:
    """Clear an input field."""
    async def _go():
        page = await _get_page()
        await page.locator(selector).first.clear(timeout=timeout)
        return {"ok": True, "cleared": selector}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_select_option(selector: str, value: str = None, label: str = None,
                          index: int = None, timeout: int = 10000) -> dict:
    """Select an option from a <select> dropdown."""
    async def _go():
        page = await _get_page()
        el = page.locator(selector).first
        if value:
            await el.select_option(value=value, timeout=timeout)
            return {"ok": True, "selected": value}
        if label:
            await el.select_option(label=label, timeout=timeout)
            return {"ok": True, "selected": label}
        if index is not None:
            await el.select_option(index=index, timeout=timeout)
            return {"ok": True, "selected": f"index {index}"}
        return {"ok": False, "error": "Provide value, label, or index"}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_check(selector: str, timeout: int = 10000) -> dict:
    """Check a checkbox or radio button."""
    async def _go():
        page = await _get_page()
        await page.locator(selector).first.check(timeout=timeout)
        return {"ok": True, "checked": selector}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_uncheck(selector: str, timeout: int = 10000) -> dict:
    """Uncheck a checkbox."""
    async def _go():
        page = await _get_page()
        await page.locator(selector).first.uncheck(timeout=timeout)
        return {"ok": True, "unchecked": selector}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  SCROLLING
# ═══════════════════════════════════════════════════════════

def browser_scroll(direction: str = "down", amount: int = 500,
                   selector: str = None) -> dict:
    """
    Scroll the page or a specific element.
    direction: 'up', 'down', 'left', 'right', 'top', 'bottom'
    amount: pixels to scroll (ignored for top/bottom)
    """
    async def _go():
        page = await _get_page()
        if direction == "top":
            await page.evaluate("window.scrollTo(0, 0)")
        elif direction == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "down":
            await page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            await page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "right":
            await page.evaluate(f"window.scrollBy({amount}, 0)")
        elif direction == "left":
            await page.evaluate(f"window.scrollBy(-{amount}, 0)")
        return {"ok": True, "scrolled": direction}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  CONTENT EXTRACTION
# ═══════════════════════════════════════════════════════════

def browser_get_text(selector: str = None) -> dict:
    """
    Get visible text from an element or the whole page.
    If no selector, returns full page text (cleaned up).
    """
    async def _go():
        page = await _get_page()
        if selector:
            text = await page.locator(selector).first.inner_text()
            return {"ok": True, "text": text}
        text = await page.evaluate("""
            () => {
                const el = document.body.cloneNode(true);
                ['script','style','noscript'].forEach(t => el.querySelectorAll(t).forEach(n => n.remove()));
                return el.innerText.replace(/\\n{3,}/g, '\\n\\n').trim().slice(0, 15000);
            }
        """)
        return {"ok": True, "text": text, "url": page.url}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_html(selector: str = None, outer: bool = False) -> dict:
    """Get HTML source of an element or the full page."""
    async def _go():
        page = await _get_page()
        if selector:
            el = page.locator(selector).first
            html = await el.outer_html() if outer else await el.inner_html()
        else:
            html = await page.content()
        return {"ok": True, "html": html[:20000], "length": len(html)}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_find_elements(selector: str, attributes: List[str] = None) -> dict:
    """
    Find all elements matching a CSS selector and return their text/attributes.
    attributes: list of attribute names to extract, e.g. ['href', 'src', 'id']
    """
    async def _go():
        page = await _get_page()
        locator = page.locator(selector)
        count = await locator.count()
        items = []
        attrs = attributes or []
        for i in range(min(count, 50)):
            el = locator.nth(i)
            try:
                text = await el.inner_text()
                item = {"index": i, "text": text.strip()[:200]}
                for attr in attrs:
                    try:
                        item[attr] = await el.get_attribute(attr)
                    except Exception:
                        item[attr] = None
                items.append(item)
            except Exception:
                continue
        return {"ok": True, "count": count, "elements": items}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_attribute(selector: str, attribute: str, timeout: int = 10000) -> dict:
    """Get an attribute value from an element (e.g. href, src, value, class)."""
    async def _go():
        page = await _get_page()
        value = await page.locator(selector).first.get_attribute(attribute, timeout=timeout)
        return {"ok": True, "selector": selector, "attribute": attribute, "value": value}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_value(selector: str, timeout: int = 10000) -> dict:
    """Get the current value of an input field."""
    async def _go():
        page = await _get_page()
        value = await page.locator(selector).first.input_value(timeout=timeout)
        return {"ok": True, "selector": selector, "value": value}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  JAVASCRIPT
# ═══════════════════════════════════════════════════════════

def browser_execute_js(script: str, arg: Any = None) -> dict:
    """
    Execute arbitrary JavaScript on the current page.
    The script can return any serialisable value.
    Examples:
      browser_execute_js("document.title")
      browser_execute_js("window.scrollY")
      browser_execute_js("document.querySelector('#result').textContent")
      browser_execute_js("fetch('/api/data').then(r=>r.json())")
    """
    async def _go():
        page = await _get_page()
        if arg is not None:
            result = await page.evaluate(f"(arg) => {{ return {script} }}", arg)
        else:
            result = await page.evaluate(script)
        return {"ok": True, "result": result}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_inject_js(script: str) -> dict:
    """Inject a JS script that runs in page context (side effects only, no return value needed)."""
    async def _go():
        page = await _get_page()
        await page.add_script_tag(content=script)
        return {"ok": True}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  FORMS
# ═══════════════════════════════════════════════════════════

def browser_fill_form(fields: Dict[str, str], submit_selector: str = None) -> dict:
    """
    Fill multiple form fields at once and optionally submit.
    fields: {selector: value} mapping
    Example:
      browser_fill_form({
        "#username": "john",
        "#password": "secret",
        "#email": "john@example.com"
      }, submit_selector="#login-btn")
    """
    async def _go():
        page = await _get_page()
        filled = []
        errors = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    await el.select_option(value=value)
                elif await el.get_attribute("type") in ("checkbox", "radio"):
                    if value.lower() in ("true", "1", "yes", "on"):
                        await el.check()
                    else:
                        await el.uncheck()
                else:
                    await el.clear()
                    await el.fill(value)
                filled.append(selector)
            except Exception as e:
                errors.append({"selector": selector, "error": str(e)})

        result = {"ok": len(errors) == 0, "filled": filled}
        if errors:
            result["errors"] = errors

        if submit_selector:
            try:
                await page.locator(submit_selector).first.click()
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                result["submitted"] = True
                result["url_after"] = page.url
            except Exception as e:
                result["submit_error"] = str(e)

        return result
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_upload_file(selector: str, file_path: str, timeout: int = 10000) -> dict:
    """Upload a file via a file input element."""
    async def _go():
        page = await _get_page()
        path = Path(file_path).expanduser()
        if not path.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}
        await page.locator(selector).first.set_input_files(str(path), timeout=timeout)
        return {"ok": True, "uploaded": str(path)}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  SCREENSHOTS
# ═══════════════════════════════════════════════════════════

def browser_screenshot(selector: str = None, filename: str = None,
                       full_page: bool = False) -> dict:
    """
    Take a screenshot of the current page or a specific element.
    Saves to ~/Jarvis/screenshots/ and returns the path.
    """
    async def _go():
        page = await _get_page()
        _ensure_dirs()
        name = filename or f"screenshot_{int(time.time())}.png"
        if not name.endswith(".png"):
            name += ".png"
        path = SCREENSHOTS_DIR / name

        if selector:
            el = page.locator(selector).first
            await el.screenshot(path=str(path))
        else:
            await page.screenshot(path=str(path), full_page=full_page)

        return {
            "ok": True,
            "path": str(path),
            "url": page.url,
            "full_page": full_page
        }
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  WAITING
# ═══════════════════════════════════════════════════════════

def browser_wait_for(selector: str = None, url_pattern: str = None,
                     state: str = "visible", timeout: int = 15000) -> dict:
    """
    Wait for an element to appear/become visible, or for URL to match a pattern.
    state: 'visible', 'hidden', 'attached', 'detached'
    """
    async def _go():
        page = await _get_page()
        if url_pattern:
            import re as _re
            await page.wait_for_url(_re.compile(url_pattern), timeout=timeout)
            return {"ok": True, "url": page.url}
        if selector:
            await page.locator(selector).first.wait_for(state=state, timeout=timeout)
            return {"ok": True, "found": selector, "state": state}
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return {"ok": True, "waited": "networkidle"}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_wait_ms(ms: int = 1000) -> dict:
    """Pause for a given number of milliseconds."""
    async def _go():
        page = await _get_page()
        await page.wait_for_timeout(ms)
        return {"ok": True, "waited_ms": ms}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  COOKIES & STORAGE
# ═══════════════════════════════════════════════════════════

def browser_get_cookies(url: str = None) -> dict:
    """Get cookies for the current page or a specific URL."""
    async def _go():
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        cookies = await _context.cookies(urls=[url] if url else None)
        return {"ok": True, "cookies": cookies, "count": len(cookies)}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_set_cookie(name: str, value: str, domain: str = None,
                       path: str = "/", secure: bool = False) -> dict:
    """Set a cookie in the browser context."""
    async def _go():
        if _context is None:
            await _ensure_browser()
        page = await _get_page()
        cookie = {"name": name, "value": value, "path": path, "secure": secure}
        if domain:
            cookie["domain"] = domain
        else:
            from urllib.parse import urlparse
            cookie["domain"] = urlparse(page.url).hostname or "localhost"
        await _context.add_cookies([cookie])
        return {"ok": True, "set": name}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_clear_cookies() -> dict:
    """Clear all cookies from the browser context."""
    async def _go():
        if _context is None:
            return {"ok": False, "error": "No browser open"}
        await _context.clear_cookies()
        return {"ok": True, "cleared": "all cookies"}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_get_local_storage(key: str = None) -> dict:
    """Get localStorage values from the current page."""
    async def _go():
        page = await _get_page()
        if key:
            val = await page.evaluate(f"localStorage.getItem('{key}')")
            return {"ok": True, "key": key, "value": val}
        data = await page.evaluate("Object.fromEntries(Object.entries(localStorage))")
        return {"ok": True, "storage": data}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_set_local_storage(key: str, value: str) -> dict:
    """Set a localStorage value on the current page."""
    async def _go():
        page = await _get_page()
        await page.evaluate(f"localStorage.setItem('{key}', '{value}')")
        return {"ok": True, "set": key}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  DOWNLOADS & NETWORK
# ═══════════════════════════════════════════════════════════

def browser_download(url: str, filename: str = None) -> dict:
    """Download a file by navigating to its URL. Saves to ~/Jarvis/downloads/."""
    async def _go():
        page = await _get_page()
        _ensure_dirs()

        async with page.expect_download() as dl_info:
            await page.goto(url if url.startswith("http") else "https://" + url)
        download = await dl_info.value

        name = filename or download.suggested_filename or f"download_{int(time.time())}"
        dest = DOWNLOADS_DIR / name
        await download.save_as(str(dest))
        return {"ok": True, "path": str(dest), "filename": name}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_intercept_next_request(url_pattern: str = "**/*") -> dict:
    """
    Intercept and inspect the next network request matching a URL pattern.
    Returns the request URL, method, headers, and response body.
    """
    async def _go():
        page = await _get_page()
        captured = {}

        async def handle(response):
            if not captured:
                try:
                    body = await response.text()
                    captured.update({
                        "url": response.url,
                        "status": response.status,
                        "headers": dict(response.headers),
                        "body": body[:5000]
                    })
                except Exception:
                    pass

        page.once("response", handle)
        await page.wait_for_timeout(5000)
        page.remove_listener("response", handle)
        return {"ok": bool(captured), "response": captured}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  DIALOGS & POPUPS
# ═══════════════════════════════════════════════════════════

def browser_handle_dialog(action: str = "accept", text: str = "") -> dict:
    """
    Set how the browser handles the NEXT alert/confirm/prompt dialog.
    action: 'accept' or 'dismiss'
    text: text to enter for prompt dialogs
    """
    async def _go():
        page = await _get_page()

        async def _handler(dialog):
            if action == "accept":
                await dialog.accept(text or "")
            else:
                await dialog.dismiss()

        page.once("dialog", _handler)
        return {"ok": True, "configured": action}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  FRAMES & IFRAMES
# ═══════════════════════════════════════════════════════════

def browser_get_frames() -> dict:
    """List all frames (iframes) on the current page."""
    async def _go():
        page = await _get_page()
        frames = []
        for i, frame in enumerate(page.frames):
            frames.append({"index": i, "name": frame.name, "url": frame.url})
        return {"ok": True, "frames": frames}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_frame_execute_js(frame_index: int, script: str) -> dict:
    """Execute JavaScript inside a specific iframe."""
    async def _go():
        page = await _get_page()
        frames = page.frames
        if frame_index >= len(frames):
            return {"ok": False, "error": f"Frame {frame_index} not found (total: {len(frames)})"}
        result = await frames[frame_index].evaluate(script)
        return {"ok": True, "result": result}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  ACCESSIBILITY & INSPECTION
# ═══════════════════════════════════════════════════════════

def browser_get_page_info() -> dict:
    """Get comprehensive info about the current page: title, URL, meta tags, links, forms."""
    async def _go():
        page = await _get_page()
        info = await page.evaluate("""
        () => {
            const links = Array.from(document.querySelectorAll('a[href]'))
                .slice(0, 30)
                .map(a => ({text: a.innerText.trim().slice(0,80), href: a.href}));
            const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
                .slice(0, 20)
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || null,
                    id: el.id || null,
                    name: el.name || null,
                    placeholder: el.placeholder || null,
                    value: (el.type !== 'password' ? el.value : '***') || null
                }));
            const meta = {};
            document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                const k = m.getAttribute('name') || m.getAttribute('property');
                meta[k] = m.getAttribute('content');
            });
            return {
                title: document.title,
                description: meta['description'] || meta['og:description'] || null,
                links,
                inputs,
                forms: document.forms.length,
                images: document.images.length,
                scripts: document.scripts.length,
            };
        }
        """)
        info["url"] = page.url
        return {"ok": True, **info}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_highlight(selector: str, color: str = "red", duration_ms: int = 2000) -> dict:
    """Visually highlight an element on the page with a colored border."""
    async def _go():
        page = await _get_page()
        await page.evaluate(f"""
        () => {{
            const el = document.querySelector('{selector}');
            if (!el) return;
            const orig = el.style.outline;
            el.style.outline = '4px solid {color}';
            el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            setTimeout(() => el.style.outline = orig, {duration_ms});
        }}
        """)
        return {"ok": True, "highlighted": selector}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browser_scroll_to_element(selector: str) -> dict:
    """Scroll the page until an element is visible."""
    async def _go():
        page = await _get_page()
        await page.locator(selector).first.scroll_into_view_if_needed()
        return {"ok": True, "scrolled_to": selector}
    try:
        return _run(_go())
    except Exception as e:
        return {"ok": False, "error": str(e)}
