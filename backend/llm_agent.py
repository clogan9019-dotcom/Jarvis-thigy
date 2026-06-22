"""
J.A.R.V.I.S LLM Agent - Ollama Only (No API Keys Required)
Features: Tool calling, streaming, memory, deep research, full browser control
"""

import os, json, re, asyncio, time
from typing import AsyncGenerator, List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

# ── Persistent conversation history ──────────────────────────────────────────
import pathlib, datetime as _dt

_HISTORY_FILE = pathlib.Path.home() / "Jarvis" / "conversation_history.json"
_HISTORY_MAX  = 200   # keep last 200 messages in the file (~100 exchanges)


def _load_history() -> list:
    """Load conversation history from disk. Returns [] on any error."""
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _HISTORY_FILE.exists():
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                msgs = json.load(f)
            # Only keep role/content fields for the LLM; strip metadata
            return [{"role": m["role"], "content": m["content"]} for m in msgs if "role" in m]
    except Exception as e:
        print(f"[JARVIS] Could not load conversation history: {e}")
    return []


def _save_history(history: list) -> None:
    """Append timestamp metadata and write history to disk, trimmed to _HISTORY_MAX."""
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if _HISTORY_FILE.exists():
            try:
                with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        stamped = []
        for m in history:
            stamped.append({
                "role": m["role"],
                "content": m["content"],
                "saved_at": _dt.datetime.now().isoformat(timespec="seconds")
            })
        trimmed = stamped[-_HISTORY_MAX:]
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[JARVIS] Could not save conversation history: {e}")


# Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder-14b-instruct-abliterated:latest")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:latest")

# Import tools
from tools import screen_vision, computer_control, file_terminal, web_search, memory_rag, deep_research as dr_module, system_stats as sys_stats
from tools import browser_control as bc

TOOLS = {
    # ── Screen & Vision ──
    "screen_capture":      screen_vision.screen_capture,
    "analyze_screen":      screen_vision.analyze_screen,

    # ── Computer Control ──
    "open_app":            computer_control.open_app,
    "type_text":           computer_control.type_text,
    "hotkey":              computer_control.hotkey,
    "click":               computer_control.click,
    "move_to":             computer_control.move_to,
    "get_cursor_pos":      computer_control.get_cursor_pos,

    # ── Files & Terminal ──
    "read_file":           file_terminal.read_file,
    "write_file":          file_terminal.write_file,
    "run_cmd":             file_terminal.run_cmd,

    # ── Web Search ──
    "web_search":          web_search.web_search,

    # ── Memory ──
    "memory_add":          memory_rag.memory_add,
    "memory_search":       memory_rag.memory_search,

    # ── Research ──
    "deep_research":       dr_module.deep_research,

    # ── System Stats ──
    "get_system_stats":    sys_stats.get_system_stats,

    # ── Browser Control (Full) ──
    "browser_open":              bc.browser_open,
    "browser_back":              bc.browser_back,
    "browser_forward":           bc.browser_forward,
    "browser_refresh":           bc.browser_refresh,
    "browser_get_url":           bc.browser_get_url,
    "browser_new_tab":           bc.browser_new_tab,
    "browser_list_tabs":         bc.browser_list_tabs,
    "browser_switch_tab":        bc.browser_switch_tab,
    "browser_close_tab":         bc.browser_close_tab,
    "browser_close":             bc.browser_close,
    "browser_click":             bc.browser_click,
    "browser_right_click":       bc.browser_right_click,
    "browser_hover":             bc.browser_hover,
    "browser_drag":              bc.browser_drag,
    "browser_type":              bc.browser_type,
    "browser_press_key":         bc.browser_press_key,
    "browser_clear_input":       bc.browser_clear_input,
    "browser_select_option":     bc.browser_select_option,
    "browser_check":             bc.browser_check,
    "browser_uncheck":           bc.browser_uncheck,
    "browser_scroll":            bc.browser_scroll,
    "browser_scroll_to_element": bc.browser_scroll_to_element,
    "browser_get_text":          bc.browser_get_text,
    "browser_get_html":          bc.browser_get_html,
    "browser_find_elements":     bc.browser_find_elements,
    "browser_get_attribute":     bc.browser_get_attribute,
    "browser_get_value":         bc.browser_get_value,
    "browser_execute_js":        bc.browser_execute_js,
    "browser_inject_js":         bc.browser_inject_js,
    "browser_fill_form":         bc.browser_fill_form,
    "browser_upload_file":       bc.browser_upload_file,
    "browser_screenshot":        bc.browser_screenshot,
    "browser_wait_for":          bc.browser_wait_for,
    "browser_wait_ms":           bc.browser_wait_ms,
    "browser_get_cookies":       bc.browser_get_cookies,
    "browser_set_cookie":        bc.browser_set_cookie,
    "browser_clear_cookies":     bc.browser_clear_cookies,
    "browser_get_local_storage": bc.browser_get_local_storage,
    "browser_set_local_storage": bc.browser_set_local_storage,
    "browser_download":          bc.browser_download,
    "browser_intercept_next_request": bc.browser_intercept_next_request,
    "browser_handle_dialog":     bc.browser_handle_dialog,
    "browser_get_frames":        bc.browser_get_frames,
    "browser_frame_execute_js":  bc.browser_frame_execute_js,
    "browser_get_page_info":     bc.browser_get_page_info,
    "browser_highlight":         bc.browser_highlight,
}

TOOL_DESCRIPTIONS = """
You have access to these tools. To use one, output EXACTLY this format on its own line:
[TOOL: tool_name] {"arg": "value"}

═══ CORE TOOLS ═══

1. analyze_screen - Screenshot and describe what's on screen
   [TOOL: analyze_screen] {}

2. web_search - Search the web (DuckDuckGo, no key needed)
   [TOOL: web_search] {"query": "your search query"}

3. deep_research - Autonomous deep research (20-60 seconds, saves full report)
   [TOOL: deep_research] {"topic": "research topic", "max_queries": 10}

4. open_app - Open a Windows application
   [TOOL: open_app] {"app_name": "notepad"}

5. run_cmd - Run a shell command
   [TOOL: run_cmd] {"command": "dir"}

6. read_file - Read a text file
   [TOOL: read_file] {"path": "C:/path/to/file.txt"}

7. write_file - Write text to a file
   [TOOL: write_file] {"path": "C:/path/file.txt", "content": "text"}

8. memory_add - Save a fact to long-term memory
   [TOOL: memory_add] {"text": "fact to remember"}

9. memory_search - Search long-term memory
   [TOOL: memory_search] {"query": "what to look for"}

10. click - Click screen coordinates (desktop/OS level)
    [TOOL: click] {"x": 100, "y": 200}

11. get_system_stats - Get live PC hardware stats (CPU, RAM, GPU, disk, network)
    [TOOL: get_system_stats] {}

═══ BROWSER CONTROL — FULL CONTROL ═══
The browser stays open between commands. You can chain many browser tools in one response.

NAVIGATION:
  [TOOL: browser_open] {"url": "https://example.com"}
  [TOOL: browser_back] {}
  [TOOL: browser_forward] {}
  [TOOL: browser_refresh] {}
  [TOOL: browser_get_url] {}

TABS:
  [TOOL: browser_new_tab] {"url": "https://google.com"}
  [TOOL: browser_list_tabs] {}
  [TOOL: browser_switch_tab] {"index": 1}
  [TOOL: browser_close_tab] {}
  [TOOL: browser_close] {}

CLICKING & MOUSE:
  [TOOL: browser_click] {"selector": "#submit-btn"}
  [TOOL: browser_click] {"selector": "text=Sign in"}
  [TOOL: browser_click] {"x": 500, "y": 300}
  [TOOL: browser_right_click] {"selector": ".item"}
  [TOOL: browser_hover] {"selector": ".dropdown-trigger"}
  [TOOL: browser_drag] {"from_selector": ".card", "to_selector": ".dropzone"}

TYPING & KEYBOARD:
  [TOOL: browser_type] {"selector": "#search-input", "text": "hello world", "press_enter": true}
  [TOOL: browser_press_key] {"key": "Escape"}
  [TOOL: browser_press_key] {"key": "Control+a"}
  [TOOL: browser_select_option] {"selector": "#country", "label": "United States"}
  [TOOL: browser_check] {"selector": "#agree-checkbox"}

SCROLLING:
  [TOOL: browser_scroll] {"direction": "down", "amount": 500}
  [TOOL: browser_scroll] {"direction": "bottom"}
  [TOOL: browser_scroll_to_element] {"selector": "#footer"}

CONTENT READING:
  [TOOL: browser_get_text] {}
  [TOOL: browser_get_text] {"selector": ".article-body"}
  [TOOL: browser_get_html] {"selector": "#main"}
  [TOOL: browser_find_elements] {"selector": "a[href]", "attributes": ["href", "text"]}
  [TOOL: browser_get_attribute] {"selector": "img.logo", "attribute": "src"}
  [TOOL: browser_get_page_info] {}

FORMS:
  [TOOL: browser_fill_form] {"fields": {"#email": "user@example.com", "#password": "secret"}, "submit_selector": "#login-btn"}
  [TOOL: browser_upload_file] {"selector": "input[type=file]", "file_path": "C:/Users/me/doc.pdf"}

JAVASCRIPT:
  [TOOL: browser_execute_js] {"script": "document.title"}
  [TOOL: browser_execute_js] {"script": "document.querySelector('#price').textContent"}
  [TOOL: browser_inject_js] {"script": "document.body.style.background='red'"}

SCREENSHOTS:
  [TOOL: browser_screenshot] {}
  [TOOL: browser_screenshot] {"selector": ".chart", "filename": "chart.png"}
  [TOOL: browser_screenshot] {"full_page": true}

WAITING:
  [TOOL: browser_wait_for] {"selector": "#results", "state": "visible"}
  [TOOL: browser_wait_for] {"url_pattern": ".*dashboard.*"}
  [TOOL: browser_wait_ms] {"ms": 2000}

COOKIES & STORAGE:
  [TOOL: browser_get_cookies] {}
  [TOOL: browser_set_cookie] {"name": "session", "value": "abc123"}
  [TOOL: browser_clear_cookies] {}
  [TOOL: browser_get_local_storage] {}
  [TOOL: browser_set_local_storage] {"key": "theme", "value": "dark"}

DOWNLOADS & NETWORK:
  [TOOL: browser_download] {"url": "https://example.com/file.pdf", "filename": "report.pdf"}
  [TOOL: browser_intercept_next_request] {}

DIALOGS & FRAMES:
  [TOOL: browser_handle_dialog] {"action": "accept"}
  [TOOL: browser_get_frames] {}
  [TOOL: browser_frame_execute_js] {"frame_index": 0, "script": "document.title"}

HIGHLIGHTING:
  [TOOL: browser_highlight] {"selector": ".important", "color": "red"}
"""

SYSTEM_PROMPT = f"""You are J.A.R.V.I.S. (Just A Rather Very Intelligent System) — the personal AI of your user, modelled after the JARVIS from Iron Man: calm, precise, dry wit, never flustered, always one step ahead.
Running entirely on the user's local Windows PC. No cloud, no API keys, full privacy.

═══ PERSONALITY & TONE ═══
- Speak like a real assistant, not a chatbot. Short, direct sentences.
- Dry British wit welcome — a light quip is fine, never at expense of being helpful.
- Never say "As an AI..." — you CAN do things. Find a way.
- Never apologise excessively. Acknowledge, fix, move on.
- Occasionally address the user as "sir" — but not every message.
- No bullet-point essays when a sentence will do.

═══ CAPABILITIES ═══
{TOOL_DESCRIPTIONS}

═══ TOOL RULES ═══
- Output [TOOL: name] EXACTLY as shown — parsed literally.
- Research/investigation → ALWAYS use deep_research (writes full report, opens in Notepad).
- Screen questions → analyze_screen first, then answer.
- CPU/RAM/GPU/VRAM/temp questions → get_system_stats.
- Facts, current events → web_search.
- Save user preferences/facts with memory_add so you remember next session.
- You have persistent conversation history. Use it.
- Do NOT narrate tool calls ("I will now search..."). Just do it and report the result.
- After a tool returns, summarise the key finding — never dump raw data at the user.

═══ BROWSER RULES ═══
- The browser persists between commands — treat it like a real browser you're controlling live.
- For web tasks, chain browser tools: open → inspect → interact → read results.
- Use browser_get_page_info first to understand a new page's structure before clicking.
- Use browser_get_text to read page content before trying to find elements.
- Use browser_wait_for after navigation or actions that trigger loading.
- Use browser_execute_js for anything that CSS selectors can't reach.
- You can fill entire forms with browser_fill_form in one shot.
- Always take browser_screenshot after a complex sequence so the user can see the result.
- If a selector doesn't work, try "text=Button Label" or use browser_execute_js to find it.

═══ ENVIRONMENT ═══
OS: Windows 11 | Mode: Fully local (Ollama + local STT/TTS)
Date/Time: {time.strftime('%A %d %B %Y, %I:%M %p')}
"""


class JarvisAgent:
    def __init__(self):
        self.history: List[Dict[str,str]] = _load_history()
        self.ollama_host = OLLAMA_HOST
        self.model = OLLAMA_MODEL

        try:
            import httpx
            response = httpx.get(f"{self.ollama_host}/api/tags", timeout=5)
            models = response.json().get("models", [])
            print(f"[JARVIS] Ollama connected! Available models: {len(models)}")
            for m in models[:3]:
                print(f"  - {m.get('name', 'unknown')}")
        except Exception as e:
            print(f"[JARVIS] Warning: Ollama not responding: {e}")
            print(f"  → Start Ollama: ollama serve")

        # Warm-up: load model into VRAM immediately
        try:
            import threading as _t
            def _warmup():
                try:
                    import httpx as _hx
                    _hx.post(
                        f"{self.ollama_host}/api/generate",
                        json={"model": self.model, "prompt": " ", "stream": False, "keep_alive": -1},
                        timeout=60
                    )
                    print(f"[JARVIS] Ollama model '{self.model}' loaded into VRAM and ready.")
                except Exception as we:
                    print(f"[JARVIS] Warmup skipped: {we}")
            _t.Thread(target=_warmup, daemon=True).start()
        except Exception:
            pass

    async def chat(self, user_msg: str) -> Dict[str, Any]:
        out = ""
        async for chunk in self.stream_chat(user_msg):
            if chunk.get("type") == "delta":
                out += chunk["text"]
        return {"reply": out}

    async def stream_chat(self, user_msg: str) -> AsyncGenerator[Dict[str,Any], None]:
        """Main streaming chat with tool calling via Ollama"""

        # Memory recall
        try:
            mem = memory_rag.memory_search(user_msg, k=3)
            mem_ctx = "\n".join([m["text"] for m in mem]) if mem else ""
        except Exception:
            mem_ctx = ""

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if mem_ctx:
            messages.append({"role": "system", "content": f"\n\nRelevant memory:\n{mem_ctx}"})
        messages += self.history[-10:]
        messages.append({"role": "user", "content": user_msg})

        # Tool call loop (max 6 rounds to support chained browser actions)
        for round_idx in range(6):
            full_response = ""
            line_buf = ""

            try:
                async for chunk in self._stream_ollama(messages):
                    if chunk.get("type") == "delta":
                        text = chunk["text"]
                        full_response += text
                        line_buf += text

                        while "\n" in line_buf:
                            line, line_buf = line_buf.split("\n", 1)
                            if not re.search(r'\[TOOL:\s*\w+\]', line, re.IGNORECASE):
                                yield {"type": "delta", "text": line + "\n"}
                    elif chunk.get("type") == "done":
                        break
            except Exception as e:
                yield {"type": "delta", "text": f"[Ollama error: {e}]"}
                yield {"type": "done"}
                return

            if line_buf and not re.search(r'\[TOOL:\s*\w+\]', line_buf, re.IGNORECASE):
                yield {"type": "delta", "text": line_buf}
            line_buf = ""

            tool_calls = self._parse_tool_calls(full_response)

            if tool_calls:
                messages.append({"role": "assistant", "content": full_response})

                for tool_call in tool_calls:
                    name = tool_call.get("name")
                    args = tool_call.get("args", {})

                    yield {"type": "tool", "name": name, "args": args}

                    try:
                        fn = TOOLS.get(name)
                        if fn:
                            if name == "deep_research":
                                import threading
                                progress_state = {
                                    "queries": 0, "sources": 0,
                                    "progress": 0, "current_query": ""
                                }
                                result_holder = {}

                                def progress_cb(queries, sources, progress, current_query):
                                    progress_state.update({
                                        "queries": queries,
                                        "sources": sources,
                                        "progress": progress,
                                        "current_query": current_query
                                    })

                                def run():
                                    try:
                                        result_holder["result"] = fn(
                                            progress_callback=progress_cb, **args
                                        )
                                    except Exception as e:
                                        result_holder["error"] = str(e)

                                thread = threading.Thread(target=run, daemon=True)
                                thread.start()
                                last_q = -1

                                while thread.is_alive():
                                    await asyncio.sleep(0.15)
                                    if progress_state["queries"] != last_q:
                                        last_q = progress_state["queries"]
                                        yield {
                                            "type": "tool_progress",
                                            "name": name,
                                            "queries": progress_state["queries"],
                                            "sources": progress_state["sources"],
                                            "progress": progress_state["progress"],
                                            "current_query": progress_state["current_query"]
                                        }

                                if "error" in result_holder:
                                    raise RuntimeError(result_holder["error"])
                                result = result_holder.get("result", {})

                                report_path = result.get("report_path", "")
                                if report_path and os.path.exists(report_path):
                                    try:
                                        import subprocess as _sp
                                        _sp.Popen(["notepad.exe", report_path])
                                    except Exception:
                                        pass
                                result_str = (
                                    f"Research complete.\n"
                                    f"Report saved to: {report_path}\n"
                                    f"Stats: {result.get('queries_run', 0)} queries, "
                                    f"{result.get('sources_found', 0)} sources\n"
                                    f"Summary: {str(result.get('synthesis', ''))[:800]}"
                                )
                                result_str += "\n\nReport is now open in Notepad. "
                                result_str += "Do NOT list bullet points of the report — give a 1-2 sentence summary only."

                            elif name in (
                                # Browser tools that may be slow — run in thread to avoid blocking
                                "browser_open", "browser_download", "browser_wait_for",
                                "browser_fill_form", "browser_intercept_next_request",
                            ):
                                import threading
                                result_holder = {}

                                def _run_browser():
                                    try:
                                        result_holder["result"] = fn(**args)
                                    except Exception as e:
                                        result_holder["error"] = str(e)

                                t = threading.Thread(target=_run_browser, daemon=True)
                                t.start()
                                while t.is_alive():
                                    await asyncio.sleep(0.1)

                                if "error" in result_holder:
                                    result = {"ok": False, "error": result_holder["error"]}
                                else:
                                    result = result_holder.get("result", {})
                                result_str = json.dumps(result)

                            else:
                                loop = asyncio.get_event_loop()
                                result = await loop.run_in_executor(None, lambda: fn(**args))
                                result_str = json.dumps(result)

                        else:
                            result_str = json.dumps({"error": f"Unknown tool: {name}"})
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)})

                    messages.append({
                        "role": "user",
                        "content": f"[TOOL RESULT: {name}]\n{result_str}"
                    })

                continue
            else:
                # No tool calls — final response
                self.history.append({"role": "user", "content": user_msg})
                self.history.append({"role": "assistant", "content": full_response})
                if len(self.history) > _HISTORY_MAX:
                    self.history = self.history[-_HISTORY_MAX:]
                _save_history(self.history)
                yield {"type": "done"}
                return

        yield {"type": "done"}

    async def _stream_ollama(self, messages):
        import httpx
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {
                "temperature": 0.7,
                "num_ctx": 8192,
            }
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self.ollama_host}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        j = json.loads(line)
                        if j.get("done"):
                            yield {"type": "done"}
                            return
                        content = j.get("message", {}).get("content", "")
                        if content:
                            yield {"type": "delta", "text": content}
                    except Exception:
                        continue

    def _parse_tool_calls(self, text: str) -> list:
        """Extract [TOOL: name] {args} patterns from LLM output."""
        tool_pattern = r'\[TOOL:\s*(\w+)\]\s*(\{[^}]*\}|\{[^}]*\})'
        calls = []

        def add(name, args):
            if name in TOOLS:
                calls.append({"name": name, "args": args})

        for name_str, args_str in re.findall(tool_pattern, text, re.IGNORECASE | re.DOTALL):
            name = name_str.lower()
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            add(name, args)

        # Pattern 2: web_search inference from plain questions
        if not calls:
            text_lower = text.lower()
            for pattern in [
                r'search(?:ing)?\s+(?:for\s+)?["\']([^"\']+)["\']',
                r'look(?:ing)?\s+up\s+["\']([^"\']+)["\']',
            ]:
                m = re.search(pattern, text_lower)
                if m:
                    add("web_search", {"query": m.group(1)})
                    break

        # Pattern 3: analyze_screen inference
        if not calls:
            text_lower = text.lower()
            for pattern in [
                r'analyz(?:e|ing)\s+(?:the\s+)?screen',
                r'look(?:ing)?\s+at\s+(?:the\s+)?screen',
            ]:
                if re.search(pattern, text_lower):
                    add("analyze_screen", {})
                    break

        return calls
