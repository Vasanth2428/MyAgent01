import time
import logging
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger("MultiAgent.WorkerCache")

_IN_MEMORY_CACHE: Dict[str, Dict] = {}
_CACHE_TTL_SECONDS = 3600
_last_eviction_time = 0.0
_cache_lock = threading.Lock()


def _evict_stale() -> None:
    global _last_eviction_time
    now = time.time()
    if now - _last_eviction_time < 60:
        return
    _last_eviction_time = now
    cutoff = now - _CACHE_TTL_SECONDS
    stale = [key for key, value in _IN_MEMORY_CACHE.items() if value.get("timestamp", 0) < cutoff]
    for key in stale:
        del _IN_MEMORY_CACHE[key]


def store_worker_output(worker_name: str, output: str, *, session_id: Optional[str] = None) -> Tuple[str, str]:
    if not isinstance(output, str):
        output = str(output)
    cache_id = f"wo_{worker_name}_{abs(hash(output)) & 0xFFFFFFFF:x}"
    with _cache_lock:
        _IN_MEMORY_CACHE[cache_id] = {
            "text": output,
            "worker": worker_name,
            "session_id": session_id,
            "timestamp": time.time(),
        }
        _evict_stale()
    summary = output[:160].replace("\n", " ") + ("..." if len(output) > 160 else "")
    return cache_id, summary


def get_worker_output(cache_id: str) -> str:
    with _cache_lock:
        entry = _IN_MEMORY_CACHE.get(cache_id)
    if entry is None:
        return ""
    return entry.get("text", "")


def get_worker_output_summary(cache_id: str) -> str:
    text = get_worker_output(cache_id)
    return text[:160].replace("\n", " ") + ("..." if len(text) > 160 else "")

