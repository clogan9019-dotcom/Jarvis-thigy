"""
J.A.R.V.I.S LLM Agent - Ollama Only (No API Keys Required)
Features: Tool calling, streaming, memory, deep research
"""

import os, json, re, asyncio, time
from typing import AsyncGenerator, List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

# Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder-14b-instruct-abliterated:latest")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:latest")

# Import tools
from tools import screen_vision, computer_control, file_terminal, web_search, memory_rag, deep_research as dr_module

# Tool definitions (will be used to parse Ollama responses)
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
}

# Tool descriptions for Ollama prompt
TOOL_DESCRIPTIONS = """
You have access to these tools (use them when needed):

1. analyze_screen - Take a screenshot and describe what's on screen
   Input: question (optional string)
   
2. web_search - Search the web for information
   Input: query (string)
   
3. deep_research - Autonomous deep research on a topic
   Input: topic (string), max_queries (optional, 5-20)
   This takes 20-60 seconds and produces a full research report saved to ~/Jarvis/Projects/
   
4. open_app - Open a Windows application by name
   Input: app_name (string, e.g., "notepad", "chrome", "vscode")
   
5. run_cmd - Run a Windows shell command
   Input: command (string)
   
6. read_file - Read a text file
   Input: path (string)
   
7. write_file - Write text to a file
   Input: path (string), content (string)
   
8. memory_add - Save a fact to long-term memory
   Input: text (string)
   
9. memory_search - Search long-term memory
   Input: query (string)
   
10. click - Click on screen coordinates
    Input: x (int), y (int)

When the user asks to research, study, or learn about something, use deep_research.
When they ask "what's on my screen", use analyze_screen.
When they mention something about themselves, use memory_add to save it.
"""

SYSTEM_PROMPT = f"""You are J.A.R.V.I.S., Tony Stark's AI assistant. You are helpful, concise, slightly witty, and very capable.

You run on a Windows desktop and have access to various tools to help the user.

{TOOL_DESCRIPTIONS}

Guidelines:
- Be conversational but concise
- Use tools when you need real information or to take actions
- For research/study requests, use deep_research - it's very powerful
- For screen questions, use analyze_screen
- Remember important facts about the user with memory_add
- When using tools, execute them and report results
- Format code or technical info with backticks

Current OS: Windows
Time: {time.strftime('%I:%M %p')}
"""

class JarvisAgent:
    def __init__(self):
        self.history: List[Dict[str,str]] = []
        self.ollama_host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        
        # Check if Ollama is available
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
            print(f"  → Or change OLLAMA_HOST in .env")

    async def chat(self, user_msg: str) -> Dict[str, Any]:
        """Non-streaming chat (fallback)"""
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
        
        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if mem_ctx:
            messages.append({"role": "system", "content": f"\n\nRelevant memory:\n{mem_ctx}"})
        messages += self.history[-10:]  # Keep last 10 messages for context
        messages.append({"role": "user", "content": user_msg})
        
        # Tool call loop (max 3 rounds)
        for round_idx in range(3):
            full_response = ""
            tool_calls = []
            
            try:
                async for chunk in self._stream_ollama(messages):
                    if chunk.get("type") == "delta":
                        text = chunk["text"]
                        full_response += text
                        yield chunk
                        
                        # Detect tool calls in the text
                        detected = self._parse_tool_calls(text)
                        for tc in detected:
                            if tc not in tool_calls:
                                tool_calls.append(tc)
                                
                    elif chunk.get("type") == "done":
                        break
                        
            except Exception as e:
                yield {"type": "delta", "text": f"[Ollama error: {e}]"}
                yield {"type": "done"}
                return
            
            # Execute tool calls
            if tool_calls:
                messages.append({"role": "assistant", "content": full_response})
                
                for tool_call in tool_calls:
                    name = tool_call.get("name")
                    args = tool_call.get("args", {})
                    
                    yield {"type": "tool", "name": name, "args": args}
                    
                    try:
                        fn = TOOLS.get(name)
                        if fn:
                            # Special handling for deep_research - stream progress
                            if name == "deep_research":
                                import threading
                                progress_state = {"queries": 0, "sources": 0, "progress": 0, "current_query": "", "done": False}
                                result_holder = {}
                                
                                def progress_cb(queries, sources, progress, current_query):
                                    progress_state.update({"queries": queries, "sources": sources, "progress": progress, "current_query": current_query})
                                
                                def run():
                                    try:
                                        result_holder["result"] = fn(progress_callback=progress_cb, **args)
                                    except Exception as e:
                                        result_holder["error"] = str(e)
                                    progress_state["done"] = True
                                
                                thread = threading.Thread(target=run, daemon=True)
                                thread.start()
                                last_q = -1
                                
                                while thread.is_alive():
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
                                    time.sleep(0.15)
                                
                                thread.join()
                                
                                if "error" in result_holder:
                                    raise RuntimeError(result_holder["error"])
                                result = result_holder.get("result", {})
                            else:
                                result = fn(**args) if args else fn()
                            
                            result_str = json.dumps(result, default=str)[:4000]
                        else:
                            result_str = f"Unknown tool: {name}"
                            result = {"ok": False}
                            
                    except Exception as e:
                        result_str = f"Error: {e}"
                        result = {"ok": False, "error": str(e)}
                    
                    messages.append({"role": "tool", "content": result_str})
                
                # Continue conversation after tool results
                continue
            else:
                # No tool calls, conversation is done
                break
        
        # Save to history
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": full_response})
        
        yield {"type": "done", "text": full_response}

    def _parse_tool_calls(self, text: str) -> List[Dict]:
        """Parse potential tool calls from Ollama response text"""
        tool_calls = []
        
        # Look for patterns like:
        # [TOOL: analyze_screen] {"question": "..."}
        # Tool: analyze_screen
        # I'll use analyze_screen to...
        
        # Pattern 1: [TOOL: name] json
        tool_pattern = r'\[TOOL:\s*(\w+)\]\s*(\{[^}]+\}|\S+)?'
        matches = re.findall(tool_pattern, text, re.IGNORECASE)
        for name, args_str in matches:
            if name in TOOLS:
                try:
                    args = json.loads(args_str) if args_str and args_str.strip() else {}
                except:
                    args = {}
                tool_calls.append({"name": name, "args": args})
        
        # Pattern 2: Detect intent from text
        text_lower = text.lower()
        
        # Screen analysis
        if any(kw in text_lower for kw in ["analyze screen", "what's on my screen", "what am i looking", "screenshot"]):
            if "analyze_screen" not in [t["name"] for t in tool_calls]:
                tool_calls.append({"name": "analyze_screen", "args": {}})
        
        # Web search
        search_patterns = [
            r'search(?:ing)? for ["\']([^"\']+)["\']',
            r'look(?:ing)? up ["\']([^"\']+)["\']',
            r'web search ["\']([^"\']+)["\']'
        ]
        for pattern in search_patterns:
            match = re.search(pattern, text_lower)
            if match and "web_search" not in [t["name"] for t in tool_calls]:
                tool_calls.append({"name": "web_search", "args": {"query": match.group(1)}})
        
        return tool_calls

    async def _stream_ollama(self, messages: List[Dict]) -> AsyncGenerator[Dict[str,Any], None]:
        """Stream from Ollama"""
        import httpx
        
        # Convert messages format for Ollama
        ollama_messages = []
        for msg in messages:
            if msg["role"] == "system":
                ollama_messages.append({"role": "system", "content": msg["content"]})
            else:
                ollama_messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Build prompt with tool instructions
        prompt_parts = []
        for msg in ollama_messages:
            if msg["role"] == "system":
                prompt_parts.append(f"System: {msg['content']}")
            elif msg["role"] == "user":
                prompt_parts.append(f"User: {msg['content']}")
            elif msg["role"] == "assistant":
                prompt_parts.append(f"Assistant: {msg['content']}")
            elif msg["role"] == "tool":
                prompt_parts.append(f"Tool result: {msg['content']}")
        
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
                        except:
                            pass
        except Exception as e:
            yield {"type": "delta", "text": f"\n\n[Error: Ollama not responding - {e}]"}
            yield {"type": "delta", "text": "\n\n💡 Make sure Ollama is running: `ollama serve`"}


# Alias for backward compatibility
def chat_with_jarvis(message: str) -> str:
    """Synchronous wrapper for simple usage"""
    agent = JarvisAgent()
    import asyncio
    result = asyncio.run(agent.chat(message))
    return result.get("reply", "")