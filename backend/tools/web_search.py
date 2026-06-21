"""
Web Search - Purely Local (No API Keys!)
Uses DuckDuckGo (free, no key required)
Optional: Brave Search API if key is provided
"""

import os

def web_search(query: str) -> dict:
    """
    Search the web - completely free, no API key needed!
    
    Uses DuckDuckGo by default (free, no limits)
    Optional: Set BRAVE_SEARCH_API_KEY in .env for better results
    """
    
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if brave_key:
        try:
            import httpx
            response = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": brave_key},
                params={"q": query, "count": 5},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            results = [
                {
                    "title": w.get("title", ""),
                    "url": w.get("url", ""),
                    "desc": w.get("description", "")
                }
                for w in data.get("web", {}).get("results", [])
            ]
            return {"ok": True, "provider": "brave", "results": results}
        except Exception as e:
            print(f"[WebSearch] Brave error: {e}")
    
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=5))
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("url", "")),
                    "desc": r.get("body", r.get("desc", ""))
                }
                for r in raw
            ]
            return {"ok": True, "provider": "duckduckgo", "results": results}
            
    except ImportError:
        return {
            "ok": False, 
            "error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
