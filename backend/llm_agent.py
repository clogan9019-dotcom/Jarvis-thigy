import os, json, asyncio
from typing import AsyncGenerator, List, Dict, Any
from dotenv import load_dotenv
load_dotenv()

LLM_BACKEND = os.getenv("JARVIS_LLM", "openai").lower()

# --- Tool definitions ---
from tools import screen_vision, computer_control, file_terminal, web_search, memory_rag, deep_research as dr_module

TOOLS = {
    "screen_capture": screen_vision.screen_capture,
    "analyze_screen": screen_vision.analyze_screen,
    "open_app": computer_control.open_app,
    "type_text": computer_control.type_text,
    "hotkey": computer_control.hotkey,
    "read_file": file_terminal.read_file,
    "write_file": file_terminal.write_file,
    "run_cmd": file_terminal.run_cmd,
    "web_search": web_search.web_search,
    "memory_add": memory_rag.memory_add,
    "memory_search": memory_rag.memory_search,
    "deep_research": dr_module.deep_research,
}

TOOL_SCHEMA_OPENAI = [
    {"type":"function","function":{"name":"analyze_screen","description":"Take a screenshot and describe what is on screen. Use when user asks 'what am I looking at?'",
        "parameters":{"type":"object","properties":{"question":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"web_search","description":"Search the web for current information.",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
    {"type":"function","function":{"name":"deep_research","description":"Autonomous deep research agent. Use when the user asks to research a topic in depth, study something, or 'spend hours learning X'. Runs 5-20 web searches, synthesizes sources, and saves a markdown research report to ~/Jarvis/Projects/<topic>/. This is the Arc Reactor / nuclear physics PhD-level research mode. Takes 20-60 seconds.",
        "parameters":{"type":"object","properties":{
            "topic":{"type":"string","description":"The research topic / question"},
            "max_queries":{"type":"integer","description":"Number of web searches, 5-20, default 10"}
        },"required":["topic"]}}},
    {"type":"function","function":{"name":"open_app","description":"Open a Windows application by name.",
        "parameters":{"type":"object","properties":{"app_name":{"type":"string"}},"required":["app_name"]}}},
    {"type":"function","function":{"name":"run_cmd","description":"Run a Windows shell command. Be careful.",
        "parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"read_file","description":"Read a text file.",
        "parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"write_file","description":"Write text to a file.",
        "parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"memory_add","description":"Save a fact to long-term memory.",
        "parameters":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}}},
    {"type":"function","function":{"name":"memory_search","description":"Search long-term memory.",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
]

JARVIS_SYSTEM = """You are J.A.R.V.I.S., a helpful, concise, slightly witty Windows desktop AI assistant.
- Be brief and actionable.
- Use tools when you need real information or to take actions.
- For research / "study X / learn about Y / deep dive" requests: use the deep_research tool. It spends 20-60 seconds doing 5-20 web searches and synthesizes a full report saved to ~/Jarvis/Projects/.
- Current OS: Windows.
- Respond conversationally, like Tony Stark's JARVIS but friendly.
"""

class JarvisAgent:
    def __init__(self):
        self.llm_backend = LLM_BACKEND
        self.history: List[Dict[str,str]] = []
        if self.llm_backend == "openai":
            from openai import OpenAI
            self.oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
            if not self.oai:
                print("[Jarvis] No OPENAI_API_KEY, falling back to ollama")
                self.llm_backend = "ollama"
        if self.llm_backend == "ollama":
            import httpx
            self.ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
            self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    async def chat(self, user_msg: str) -> Dict[str, Any]:
        out = ""
        async for c in self.stream_chat(user_msg):
            if c.get("type") == "delta":
                out += c["text"]
        return {"reply": out}

    async def stream_chat(self, user_msg: str) -> AsyncGenerator[Dict[str,Any], None]:
        # memory recall
        try:
            mem = memory_rag.memory_search(user_msg, k=3)
            mem_ctx = "\n".join([m["text"] for m in mem]) if mem else ""
        except Exception:
            mem_ctx = ""
        
        sys_prompt = JARVIS_SYSTEM
        if mem_ctx:
            sys_prompt += f"\n\nRelevant memory:\n{mem_ctx}"

        messages = [{"role": "system", "content": sys_prompt}]
        messages += self.history[-12:]
        messages.append({"role": "user", "content": user_msg})

        if self.llm_backend == "openai" and getattr(self, "oai", None):
            yield from self._stream_openai(messages)
        else:
            async for chunk in self._stream_ollama(messages):
                yield chunk
        return

    def _stream_openai(self, messages):
        # sync generator wrapped to look async-friendly
        if not getattr(self, "oai", None):
            yield {"type":"delta","text":"[No OpenAI key set. Set OPENAI_API_KEY or use Ollama.]"}
            yield {"type":"done"}
            return

        # tool loop, max 3 rounds
        for round_idx in range(3):
            stream = self.oai.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOL_SCHEMA_OPENAI,
                tool_choice="auto",
                stream=True,
                temperature=0.4,
            )
            collected_text = ""
            tool_calls = {}
            for ev in stream:
                choice = ev.choices[0]
                delta = choice.delta
                if delta.content:
                    collected_text += delta.content
                    yield {"type":"delta","text": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {"name": "", "arguments": ""}
                        if tc.function.name:
                            tool_calls[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    break

            if tool_calls:
                messages.append({"role":"assistant", "content": collected_text or None,
                                 "tool_calls": [
                    {"id": f"call_{i}", "type":"function",
                     "function":{"name:": v["name"], "name": v["name"], "arguments": v["arguments"]}}
                    for i, v in tool_calls.items()
                ]})
                # execute
                for i, v in tool_calls.items():
                    name = v["name"]
                    try:
                        args = json.loads(v["arguments"] or "{}")
                    except: args = {}
                    yield {"type":"tool","name":name,"args":args}
                    fn = TOOLS.get(name)
                    if fn:
                        try:
                            # Special streaming for deep_research -> push live progress to the HUD
                            if name == "deep_research":
                                import threading, time
                                progress_state = {"queries":0, "sources":0, "progress":0, "current_query":"", "done": False}
                                result_holder = {}
                                def progress_cb(queries, sources, progress, current_query):
                                    progress_state.update({"queries": queries, "sources": sources, "progress": progress, "current_query": current_query})
                                def run():
                                    try:
                                        result_holder["result"] = fn(progress_callback=progress_cb, **args)
                                    except Exception as e:
                                        result_holder["error"] = str(e)
                                    progress_state["done"] = True
                                t = threading.Thread(target=run, daemon=True)
                                t.start()
                                last_q = -1
                                while t.is_alive():
                                    # stream research progress events to the frontend
                                    if progress_state["queries"] != last_q:
                                        last_q = progress_state["queries"]
                                        yield {"type":"research_progress",
                                               "topic": args.get("topic",""),
                                               "queries": progress_state["queries"],
                                               "sources": progress_state["sources"],
                                               "progress": progress_state["progress"],
                                               "current_query": progress_state["current_query"]}
                                    time.sleep(0.15)
                                t.join()
                                if "error" in result_holder:
                                    raise RuntimeError(result_holder["error"])
                                result = result_holder.get("result", {})
                            else:
                                result = fn(**args) if args else fn()
                            result_str = json.dumps(result, default=str)[:4000]
                        except Exception as e:
                            result_str = f"Error: {e}"
                            result = {"ok": False, "error": str(e)}
                    else:
                        result_str = f"Unknown tool {name}"
                        result = {"ok": False}
                    messages.append({"role":"tool","tool_call_id":f"call_{i}","content":result_str})
                continue  # next round
            else:
                break

        # save history
        self.history.append({"role":"user","content":messages[-1]["content"] if isinstance(messages[-1], dict) else user_msg})
        self.history.append({"role":"assistant","content": collected_text})
        yield {"type":"done","text":collected_text}

    async def _stream_ollama(self, messages):
        import httpx
        # Simplified: no tool calling in ollama path yet, just chat
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        url = f"{self.ollama_host}/api/generate"
        payload = {"model": self.ollama_model, "prompt": prompt, "stream": True}
        full = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, json=payload) as r:
                    async for line in r.aiter_lines():
                        if not line: continue
                        try:
                            j = json.loads(line)
                            t = j.get("response","")
                            if t:
                                full += t
                                yield {"type":"delta","text": t}
                            if j.get("done"):
                                break
                        except: pass
        except Exception as e:
            yield {"type":"delta","text": f"[Ollama error: {e} - is Ollama running? ollama run {self.ollama_model}]"}
        self.history.append({"role":"user","content": messages[-1]["content"]})
        self.history.append({"role":"assistant","content": full})
        yield {"type":"done","text": full}
