import os, httpx

def web_search(query: str) -> dict:
    # Try Brave first
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if brave_key:
        try:
            r = httpx.get("https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": brave_key},
                params={"q": query, "count": 5}, timeout=10)
            r.raise_for_status()
            j = r.json()
            results = [{"title": w.get("title"), "url": w.get("url"), "desc": w.get("description")}
                       for w in j.get("web", {}).get("results", [])]
            return {"ok": True, "provider": "brave", "results": results}
        except Exception as e:
            pass
    # DuckDuckGo fallback
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            return {"ok": True, "provider": "duckduckgo", "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}
