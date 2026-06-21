import os, uuid
from pathlib import Path

_mem_client = None
_mem_collection = None

def _get_collection():
    global _mem_client, _mem_collection
    if _mem_collection is not None:
        return _mem_collection
    import chromadb
    store_dir = Path(os.getenv("APPDATA", ".")) / "jarvis" / "memory"
    store_dir.mkdir(parents=True, exist_ok=True)
    _mem_client = chromadb.PersistentClient(path=str(store_dir))
    try:
        _mem_collection = _mem_client.get_collection("jarvis_mem")
    except:
        _mem_collection = _mem_client.create_collection("jarvis_mem")
    return _mem_collection

def memory_add(text: str) -> dict:
    try:
        col = _get_collection()
        col.add(documents=[text], ids=[str(uuid.uuid4())])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def memory_search(query: str, k: int = 5) -> list:
    try:
        col = _get_collection()
        r = col.query(query_texts=[query], n_results=k)
        docs = r.get("documents", [[]])[0]
        return [{"text": d} for d in docs]
    except Exception:
        return []
