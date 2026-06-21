"""
Deep Research Agent - Purely Local (Ollama + DuckDuckGo)
No API keys required!
"""

import os, json, time
from pathlib import Path
from typing import List, Dict, Callable, Optional
import re

def _slugify(s: str) -> str:
    """Convert topic to URL-safe slug"""
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    return s[:60] or "research"

def _ollama_llm(prompt: str, system: str = "You are a helpful assistant.") -> str:
    """Call Ollama for text generation"""
    import httpx
    
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder-14b-instruct-abliterated:latest")
    
    payload = {
        "model": model,
        "prompt": f"System: {system}\n\nUser: {prompt}",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 800}
    }
    
    try:
        response = httpx.post(f"{host}/api/generate", json=payload, timeout=60)
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"[DeepResearch] Ollama error: {e}")
        return ""

def deep_research(
    topic: str, 
    max_queries: int = 10, 
    save: bool = True, 
    progress_callback: Optional[Callable] = None
) -> dict:
    """
    Autonomous deep research on a topic - purely local!
    Uses Ollama for query planning and synthesis
    Uses DuckDuckGo for web searches (no API key needed)
    """
    from . import web_search
    
    max_queries = max(2, min(int(max_queries), 20))
    start_time = time.time()
    queries_run: List[str] = []
    all_sources: List[Dict] = []

    def ping(query: str = ""):
        if progress_callback:
            try:
                sources_unique = len({s["url"] for s in all_sources if s.get("url")})
                pct = int(5 + (len(queries_run) / max_queries) * 70)
                progress_callback(len(queries_run), sources_unique, pct, query)
            except Exception:
                pass

    print(f"[DeepResearch] Starting research on: {topic}")

    # 1. Generate research sub-queries using Ollama
    plan_prompt = f"""Research topic: "{topic}"

Generate exactly {min(5, max_queries)} diverse, specific search queries that together would give comprehensive coverage of this topic.

Return ONLY a JSON list of strings, nothing else. Example: ["query 1", "query 2", "query 3"]"""

    plan_text = _ollama_llm(
        plan_prompt, 
        "You are a research assistant. Generate search queries. Return ONLY JSON list."
    )
    
    sub_queries = []
    try:
        # Try to extract JSON array
        match = re.search(r'\[.*?\]', plan_text, re.DOTALL)
        if match:
            sub_queries = json.loads(match.group(0))
        sub_queries = [str(q).strip() for q in sub_queries if q][:max_queries]
    except Exception:
        sub_queries = []

    # Fallback queries if Ollama parsing failed
    if not sub_queries:
        sub_queries = [
            topic,
            f"{topic} overview introduction",
            f"{topic} how it works technical details",
            f"{topic} applications uses",
            f"{topic} advantages benefits",
            f"{topic} limitations challenges",
        ][:max_queries]

    # Always include the original topic
    if topic not in sub_queries:
        sub_queries = [topic] + sub_queries
    sub_queries = sub_queries[:max_queries]

    print(f"[DeepResearch] Generated {len(sub_queries)} search queries")

    # 2. Run web searches
    for i, query in enumerate(sub_queries):
        print(f"[DeepResearch] Query {i+1}/{len(sub_queries)}: {query}")
        ping(query)
        
        try:
            result = web_search.web_search(query)
            queries_run.append(query)
            
            if result.get("ok"):
                for r in result.get("results", []):
                    all_sources.append({
                        "query": query,
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("desc", "") or r.get("body", "")[:400]
                    })
        except Exception as e:
            print(f"[DeepResearch] Search error: {e}")
            continue
        
        ping(query)
        time.sleep(0.3)  # Be nice to DuckDuckGo

    # Dedupe by URL
    seen = set()
    unique_sources = []
    for s in all_sources:
        url = s.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_sources.append(s)

    print(f"[DeepResearch] Found {len(unique_sources)} unique sources")

    # 3. Synthesize report using Ollama
    sources_text = "\n\n".join([
        f"[Source {i+1}] {s['title']}\nURL: {s['url']}\n{s['snippet']}"
        for i, s in enumerate(unique_sources[:20])
    ])

    synth_prompt = f"""Research Topic: {topic}

Sources gathered:
{sources_text}

Write a comprehensive research briefing in markdown format.

Structure your response as:

## Summary
2-3 sentence executive summary of the topic

## Key Findings
5-8 important facts as bullet points (use - prefix)

## Detailed Analysis
2-3 paragraphs synthesizing the information

## Open Questions
What remains unknown or needs more research

## Sources
List all source URLs

Be factual and cite information from the sources provided."""

    print("[DeepResearch] Synthesizing report with Ollama...")
    report_md = _ollama_llm(
        synth_prompt,
        "You are a research analyst. Write comprehensive, factual reports."
    )
    
    if not report_md:
        # Fallback without LLM
        report_md = f"# Research Report: {topic}\n\n"
        report_md += f"Generated {len(unique_sources)} sources.\n\n"
        report_md += "## Sources\n\n"
        for i, s in enumerate(unique_sources[:20]):
            report_md += f"{i+1}. [{s['title']}]({s['url']})\n"

    # 4. Save report
    report_path = None
    if save:
        projects_dir = Path.home() / "Jarvis" / "Projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(topic)
        proj_dir = projects_dir / slug
        proj_dir.mkdir(exist_ok=True)
        
        report_path = proj_dir / "research_report.md"
        
        # Timestamp if exists
        if report_path.exists():
            ts = time.strftime("%Y%m%d-%H%M")
            report_path = proj_dir / f"research_report_{ts}.md"
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
            f.write(f"\n\n---\n*Generated by J.A.R.V.I.S. Deep Research (Local)*\n")
            f.write(f"*Queries: {len(queries_run)} | Sources: {len(unique_sources)} | Time: {time.time()-start_time:.1f}s*\n")
        
        # Also save sources JSON
        with open(proj_dir / "sources.json", "w", encoding="utf-8") as f:
            json.dump(unique_sources, f, indent=2)
        
        print(f"[DeepResearch] Report saved to: {report_path}")

    elapsed = time.time() - start_time
    return {
        "ok": True,
        "topic": topic,
        "queries_run": queries_run,
        "queries_count": len(queries_run),
        "sources_found": len(unique_sources),
        "report_chars": len(report_md),
        "report_path": str(report_path) if report_path else None,
        "elapsed_sec": round(elapsed, 1),
        "summary": report_md[:600] + ("..." if len(report_md) > 600 else "")
    }