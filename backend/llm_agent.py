"""
J.A.R.V.I.S LLM Agent - Ollama Only (No API Keys Required)
Features: Tool calling, streaming, memory, deep research
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
        # Re-read file so we don't lose entries from a parallel process
        existing = []
        if _HISTORY_FILE.exists():
            try:
                with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        # history is the full in-memory list — write it with a saved_at field
        stamped = []
        for m in history:
            stamped.append({
                "role": m["role"],
                "content": m["content"],
                "saved_at": _dt.datetime.now().isoformat(timespec="seconds")
            })
        # Trim to last _HISTORY_MAX
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

TOOLS = {
    "screen_capture": screen_vision.screen_capture,
    "analyze_screen": screen_vision.analyze_screen,
    "open_app": computer_control.open_app,
    "type_text": computer_control.type_text,
    "hotkey": computer_control.hotkey,
    "click": computer_control.click,
    "read_file": file_terminal.read_file,
    "write_file": file_terminal.write_file,
    "run_cmd": file_terminal.run_cmd,
    "web_search": web_search.web_search,
    "memory_add": memory_rag.memory_add,
    "memory_search": memory_rag.memory_search,
    "deep_research": dr_module.deep_research,
    "get_system_stats": sys_stats.get_system_stats,
}

TOOL_DESCRIPTIONS = """
You have access to these tools. To use one, output EXACTLY this format on its own line:
[TOOL: tool_name] {"arg": "value"}

Available tools:

1. analyze_screen - Screenshot and describe what's on screen
   [TOOL: analyze_screen] {}

2. web_search - Search the web
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

10. click - Click screen coordinates
    [TOOL: click] {"x": 100, "y": 200}

11. get_system_stats - Get live PC hardware stats (CPU, RAM, GPU, disk, network, top processes)
    [TOOL: get_system_stats] {}

IMPORTANT: When the user asks to research, investigate, or study any topic, use deep_research.
When asked about the screen, use analyze_screen.
Always save important user facts with memory_add.
"""

SYSTEM_PROMPT = f"""You are J.A.R.V.I.S., Tony Stark's AI assistant. Helpful, concise, slightly witty, very capable.

{TOOL_DESCRIPTIONS}

Guidelines:
- Be conversational but concise
- Use tools when you need real information or to take actions
- For research requests, ALWAYS use deep_research — it's powerful and saves a full report
- Output the [TOOL: ...] line exactly as shown, then continue your response
- Format code with backticks

Current OS: Windows
Time: {time.strftime('%I:%M %p')}
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

        # Tool call loop (max 3 rounds)
        for round_idx in range(3):
            full_response = ""
            line_buf = ""  # used to filter [TOOL: ...] lines before display

            try:
                async for chunk in self._stream_ollama(messages):
                    if chunk.get("type") == "delta":
                        text = chunk["text"]
                        full_response += text
                        line_buf += text

                        # Flush complete lines — suppress any that are tool calls
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

            # Flush last partial line (no trailing newline) — suppress if tool call
            if line_buf and not re.search(r'\[TOOL:\s*\w+\]', line_buf, re.IGNORECASE):
                yield {"type": "delta", "text": line_buf}
            line_buf = ""

            # Parse tool calls from the FULL accumulated response (not per-chunk)
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

                                # Use asyncio.sleep so we don't block the event loop
                                while thread.is_alive():
                                    await asyncio.sleep(0.15)
                                    if progress_state["queries"] != last_q:
                                        last_q = progress_state["queries"]
                                        yield {
                                            "type": "research_progress",
                                            "topic": args.get("topic", ""),
                                            "queries": progress_state["queries"],
                                            "sources": progress_state["sources"],
                                            "progress": progress_state["progress"],
                                            "current_query": progress_state["current_query"]
                                        }

                                thread.join()

                                if "error" in result_holder:
                                    raise RuntimeError(result_holder["error"])
                                result = result_holder.get("result", {})
                            else:
                                result = fn(**args) if args else fn()

                            # For deep_research: give LLM a brief directive only
                            # (full report is on disk — don't make it yap the whole thing)
                            if name == "deep_research" and result.get("ok"):
                                report_path = result.get("report_path", "")
                                brief = (result.get("summary") or "")[:300]
                                if report_path:
                                    try:
                                        import subprocess as _sp
                                        _sp.Popen(["notepad.exe", report_path])
                                    except Exception:
                                        pass
                                result_str = (
                                    f"Research complete.\n"
                                    f"Report saved to: {report_path}\n"
                                    f"Stats: {result.get('queries_count',0)} queries, "
                                    f"{result.get('sources_found',0)} sources, "
                                    f"{result.get('elapsed_sec',0)}s\n"
                                    f"Opening in Notepad.\n"
                                    f"Excerpt: {brief}\n\n"
                                    "JARVIS INSTRUCTION: Tell the user the report is saved and opened. "
                                    "Give exactly ONE sentence summary of the key finding. "
                                    "Do NOT list bullet points or repeat the full report."
                                )
                            else:
                                result_str = json.dumps(result, default=str)[:4000]
                        else:
                            result_str = f"Unknown tool: {name}"
                            result = {"ok": False}

                    except Exception as e:
                        result_str = f"Error: {e}"
                        result = {"ok": False, "error": str(e)}

                    messages.append({"role": "tool", "content": result_str})

                continue
            else:
                break

        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": full_response})
        _save_history(self.history)

        yield {"type": "done", "text": full_response}

    def _parse_tool_calls(self, text: str) -> List[Dict]:
        """
        Parse tool calls from the full Ollama response text.
        Matches [TOOL: name] {json} patterns, then falls back to keyword intent.
        """
        tool_calls = []
        seen = set()

        def add(name, args):
            key = name
            if key not in seen:
                seen.add(key)
                tool_calls.append({"name": name, "args": args})

        # Pattern 1: explicit [TOOL: name] {json}
        tool_pattern = r'\[TOOL:\s*(\w+)\]\s*(\{[^}]*\})?'
        for name, args_str in re.findall(tool_pattern, text, re.IGNORECASE):
            name = name.lower()
            if name in TOOLS:
                try:
                    args = json.loads(args_str) if args_str and args_str.strip() else {}
                except Exception:
                    args = {}
                add(name, args)

        # Pattern 2: deep_research intent keywords
        text_lower = text.lower()

        deep_research_kws = [
            "deep_research", "deep research", "researching", "research on",
            "research about", "investigate", "look into", "study on"
        ]
        if any(kw in text_lower for kw in deep_research_kws):
            if "deep_research" not in seen:
                # Try to extract the topic from the user message context
                topic_match = re.search(
                    r'(?:research(?:ing)?|investigate|study)\s+(?:on\s+|about\s+)?["\']?([^"\'\n]{3,60})',
                    text_lower
                )
                topic = topic_match.group(1).strip() if topic_match else ""
                add("deep_research", {"topic": topic} if topic else {})

        # Pattern 3: analyze_screen intent
        if any(kw in text_lower for kw in ["analyze screen", "what's on my screen", "what am i looking", "screenshot"]):
            add("analyze_screen", {})

        # Pattern 4: web_search intent
        for pattern in [
            r'search(?:ing)? for ["\']([^"\']+)["\']',
            r'look(?:ing)? up ["\']([^"\']+)["\']',
            r'web search ["\']([^"\']+)["\']'
        ]:
            m = re.search(pattern, text_lower)
            if m:
                add("web_search", {"query": m.group(1)})
                break

        return tool_calls

    async def _stream_ollama(self, messages: List[Dict]) -> AsyncGenerator[Dict[str,Any], None]:
        import httpx

        prompt_parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            elif role == "tool":
                prompt_parts.append(f"Tool result: {content}")

        prompt = "\n".join(prompt_parts) + "\nAssistant:"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.4,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", f"{self.ollama_host}/api/generate", json=payload) as response:
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            j = json.loads(line)
                            text = j.get("response", "")
                            if text:
                                yield {"type": "delta", "text": text}
                            if j.get("done"):
                                break
                        except Exception:
                            pass
        except Exception as e:
            yield {"type": "delta", "text": f"\n\n[Error: Ollama not responding - {e}]"}
            yield {"type": "delta", "text": "\n\n💡 Make sure Ollama is running: `ollama serve`"}


def chat_with_jarvis(message: str) -> str:
    agent = JarvisAgent()
    result = asyncio.run(agent.chat(message))
    return result.get("reply", "")
