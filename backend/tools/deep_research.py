import os, json, time
from pathlib import Path
from typing import List, Dict

"""
Deep Research Agent – Manina Labs style
- Expands a topic into sub-queries
- Runs web searches in rounds
- Summarizes sources into a markdown report
- Saves to ~/Jarvis/Projects/<slug>/
"""

def _llm(prompt: str, system: str = "You are a concise research assistant.") -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return ""

def _slugify(s: str) -> str:
    import re
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:60] or "research"

def deep_research_stream(topic: str, max_queries: int = 10, save: bool = True):
    """
    Generator version – yields progress events for the Neural Interface HUD.
    Yields dicts: {"type":"progress", "queries":n, "sources":n, "progress":0-100, "current_query":str}
    Final yield: {"type":"result", **result_dict}
    """
    from . import web_search
    max_queries = max(2, min(int(max_queries), 20))
    start = time.time()
    queries_run: List[str] = []
    all_sources: List[Dict] = []

    def emit_progress(current_q=""):
        prog = int(5 + (len(queries_run) / max(max_queries,1)) * 70)
        yield {"type":"progress", "topic": topic,
               "queries": len(queries_run), "sources": len({s["url"] for s in all_sources if s["url"]}),
               "progress": prog, "current_query": current_q}
    # actually we need a real generator, so this wrapper is awkward – do it inline below
    # (keeping simple: just use deep_research() for non-streaming, see below)

    return None  # placeholder, real streaming is in the wrapper below

def deep_research(topic: str, max_queries: int = 10, save: bool = True, progress_callback=None) -> dict:
    """
    Autonomous deep research on a topic.
    Runs multiple web searches, synthesizes a report.
    
    topic: research question / topic
    max_queries: max number of web searches (default 10, capped at 20)
    save: save markdown report to ~/Jarvis/Projects/
    progress_callback: optional fn(queries, sources, progress_pct, current_query)
    """
    from . import web_search
    max_queries = max(2, min(int(max_queries), 20))

    start = time.time()
    queries_run: List[str] = []
    all_sources: List[Dict] = []

    def ping(q=""):
        if progress_callback:
            try:
                sources_unique = len({s["url"] for s in all_sources if s["url"]})
                pct = int(5 + (len(queries_run) / max_queries) * 70)
                progress_callback(len(queries_run), sources_unique, pct, q)
            except Exception:
                pass

    # 1. Plan sub-queries
    plan_prompt = f"""Research topic: "{topic}"

Generate {min(5, max_queries)} diverse, specific web search queries that together would give comprehensive coverage of this topic.
Return ONLY a JSON list of strings, no other text.
Example: ["query 1", "query 2", "query 3"]"""
    
    plan_text = _llm(plan_prompt, "You generate research search queries. Return JSON only.")
    try:
        # try to extract json array
        import re
        m = re.search(r'\[.*?\]', plan_text, re.DOTALL)
        if m:
            sub_queries = json.loads(m.group(0))
        else:
            sub_queries = json.loads(plan_text)
        sub_queries = [str(q) for q in sub_queries if q][:max_queries]
    except Exception:
        sub_queries = []

    if not sub_queries:
        # fallback generic queries
        sub_queries = [
            topic,
            f"{topic} latest research 2024 2025",
            f"{topic} technical overview",
            f"{topic} limitations challenges",
        ][:max_queries]

    # Always include the original topic first
    if topic not in sub_queries:
        sub_queries = [topic] + sub_queries
    sub_queries = sub_queries[:max_queries]

    # 2. Search rounds
    for q in sub_queries:
        ping(q)
        try:
            res = web_search.web_search(q)
            queries_run.append(q)
            if res.get("ok"):
                for r in res.get("results", []):
                    all_sources.append({
                        "query": q,
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("desc", "") or r.get("body", "")[:400]
                    })
        except Exception:
            continue
        ping(q)
        time.sleep(0.25)
        if len(queries_run) >= max_queries:
            break

    # dedupe by url
    seen = set()
    unique_sources = []
    for s in all_sources:
        u = s["url"]
        if u and u not in seen:
            seen.add(u)
            unique_sources.append(s)

    # 3. Synthesize report
    sources_text = "\n\n".join([
        f"[{i+1}] {s['title']}\n{s['url']}\n{s['snippet']}"
        for i, s in enumerate(unique_sources[:25])
    ])

    synth_prompt = f"""Research Topic: {topic}

Sources:
{sources_text}

Write a concise, well-structured research briefing in markdown.

Include:
## Summary
2-3 sentence executive summary

## Key Findings
5-8 bullet points with the most important facts

## Detailed Analysis
2-4 short paragraphs synthesizing the sources

## Open Questions / Gaps
What remains unknown

## Sources
Numbered list with titles and URLs

Be factual, neutral, cite source numbers [1], [2] etc inline where relevant.
"""
    report_md = _llm(synth_prompt, "You are a PhD-level research analyst. Be concise and accurate.")
    
    if not report_md:
        # fallback without LLM
        report_md = f"# Research Report: {topic}\n\n## Sources ({len(unique_sources)})\n\n" + "\n\n".join(
            [f"### [{i+1}] {s['title']}\n{s['url']}\n\n{s['snippet']}\n" for i, s in enumerate(unique_sources[:25])]
        )

    # 4. Save
    report_path = None
    if save:
        projects_dir = Path.home() / "Jarvis" / "Projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(topic)
        proj_dir = projects_dir / slug
        proj_dir.mkdir(exist_ok=True)
        report_path = proj_dir / "research_report.md"
        # avoid overwrite – timestamp if exists
        if report_path.exists():
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
            report_path = proj_dir / f"research_report_{ts}.md"
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
            f.write(f"\n\n---\n\n*Generated by J.A.R.V.I.S. Deep Research*\n")
            f.write(f"*Queries: {len(queries_run)} • Sources: {len(unique_sources)} • {time.time()-start:.1f}s*\n")

        # also save sources json
        with open(proj_dir / "sources.json", "w", encoding="utf-8") as f:
            json.dump(unique_sources, f, indent=2)

    elapsed = time.time() - start
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
