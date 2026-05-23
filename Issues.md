## Code Review: RAG Context Engine

Overall this is a well-structured project for a student — proper module decomposition, retry logic, SSE streaming, and a test suite. But there are real issues worth addressing before this goes on a resume or gets shown to an interviewer.

---

## Critical Issues

**1. `app.js` — Prototype Pollution via `onclick` injection**

```javascript
// app.js line ~165
onclick='viewTelemetryDetails(${JSON.stringify(telemetry)}, ...)'
```

You're injecting arbitrary JSON directly into an `onclick` attribute. If telemetry data contains `'` or `</script>`, this breaks or opens XSS. Your own `escapeHtml` function exists — it's not applied to the JSON blob here. Use `data-*` attributes + event delegation, or store telemetry in a `Map` keyed by message ID and reference it by ID in the handler.

**2. `agent.py` — Early exit grep is a footgun**

```python
greetings = {"hi", "hello", ...}
if clean_query in greetings or len(clean_query.split()) <= 2 and not any(w in clean_query for w in [...]):
```

Operator precedence: `and` binds tighter than `or`, so this is evaluated as `(A) or (B and C)`. A 2-word query like `"drop table"` hits the set check first, misses, then falls through to the short-circuit — but the intent is clearly wrong. The condition needs explicit parentheses and logic correction. Also, short-circuit on `len <= 2` can suppress legitimate 2-word technical queries like `"redis config"`.

**3. `engine.py` — Double memory persistence in streaming path**

In `ask_stream`, you call `self.save_memory(session_id, query, "user")` after generation completes. But `get_memory()` at the top of the call already restores from SQLite. If the user sends two requests in rapid succession, you'll write the user message twice (once per call before the deduplication logic in `ConversationMemory.add` catches it via Jaccard — but Jaccard is 0.7 threshold and identical strings will deduplicate, so it works, but it's a latency-wasting double-write and fragile).

**4. `retriever.py` — Batch insert error check is broken**

```python
failed = self.collection.batch.failed_objects
if failed:
    raise weaviate.exceptions.WeaviateQueryError(...)
```

`self.collection.batch.failed_objects` is accessed *after* the `with` block closes. Weaviate's batch context manager resets state on exit in some client versions. This check may silently miss failures. Access it inside the `with` block or check the return value of `batch.add_object`.

---

## Significant Issues

**5. `compressor.py` — Lexical overlap scoring is too naive**

```python
overlap = len(query_words & segment_words) / (len(query_words) + 1)
```

This is raw Jaccard-like overlap with no IDF weighting. Common words like "the", "is", "how" inflate scores for irrelevant segments. The test suite actually reveals this — PARA-5 ("The French Revolution...") survived compression in your eviction report despite being completely irrelevant, because the word "the" and generic function words matched. Add a stopword filter before scoring. Python's `nltk.corpus.stopwords` or even a hardcoded 50-word set would fix this.

**6. `memory.py` — Chronological sort index is fragile**

```python
indexed_entries = list(enumerate(self.entries))
```

When `_handle_context_overflow` prunes `memory.entries` in place via `memory.entries = temp_entries`, it truncates the list. On the next `get_active_context()` call, the enumeration indices restart from 0 on the already-truncated list — so chronological ordering is preserved relative to the pruned set, which is correct — but if entries are ever inserted out-of-order or rehydrated from SQLite in a different order than insertion (which your persistence layer can do, since you sort by `timestamp DESC` then reverse, but `timestamp` resolution is 1 second), you'll get incorrect ordering for same-second inserts.

**7. `main.py` — `asyncio.Queue` with `run_in_executor` is incorrect**

```python
loop = asyncio.get_event_loop()
# ...
def run_sync_gen(queue):
    loop.call_soon_threadsafe(queue.put_nowait, event)

loop.run_in_executor(None, run_sync_gen, queue)
```

`loop.run_in_executor` is called from within a coroutine, which is correct. But inside the executor thread, `queue.put_nowait` is called via `call_soon_threadsafe` — that's safe. However, you never `await` the future returned by `run_in_executor`, so if the thread raises an unhandled exception, it's silently swallowed. Capture the future and await it, or use `asyncio.wrap_executor_future`.

**8. `agent.py` — `search_cache` is request-scoped but solves the wrong problem**

The in-request cache prevents duplicate tool calls within one ReAct loop, which is fine. But across requests, there's no shared cache. For a production system, the expensive `_phase_expand` + `_phase_retrieve` + `compress` chain for repeated queries (e.g., "what is the database password" asked 10 times across sessions) runs fully every time. Since the retriever is deterministic for the same query, a TTL cache at the `WeaviateRetriever.retrieve()` level using `functools.lru_cache` with `maxsize` and a time-based invalidation wrapper would significantly reduce Weaviate and embedding model load.

---

## Design/Architecture Issues

**9. `config.py` — `COST_PER_INPUT_TOKEN` is hardcoded to stale pricing**

```python
COST_PER_INPUT_TOKEN = 0.05 / 1_000_000
```

Groq pricing changes. This should be in `.env` or at minimum documented with a "last verified" date comment. The UI displays `query_cost` to users — silently showing wrong numbers is worse than showing none.

**10. `engine.py` — `_handle_context_overflow` is duplicated between `ask` and `ask_stream`**

Both paths call the same method but have separate telemetry assembly blocks that are nearly identical copy-pastes (~40 lines each). Extract the telemetry dict construction into a `_build_telemetry(...)` private method.

**11. No rate limiting on `/upload`**

The upload endpoint has no size cap, no rate limit, and no content-type validation beyond filename extension. `filename.endswith(".pdf")` is trivially bypassed. A user can upload a 2GB binary with a `.txt` extension and exhaust memory during the `decode("utf-8")` call. Add `python-multipart` size limits and validate actual MIME type via `python-magic` or check the first bytes.

---

## Minor Issues

**12. `retriever.py` — `_TECHNICAL_KEYWORDS` contains `"def "` and `"class "` with trailing spaces**

These will never match `.lower()` output since `query_lower` is stripped. The trailing space is a subtle bug — it won't cause a crash but the code path for those keywords is dead.

**13. `test_introspective.py` — Tests write to filesystem with hardcoded relative paths**

```python
report_path = os.path.join(os.path.dirname(...), "results", "report.md")
```

Running tests from a different working directory will silently fail to write reports without failing the test assertion. The test passes even if the report write fails, because the `assertXxx` calls come before the write in some test methods (or the write exception isn't caught).

**14. `app.js` — `localStorage` session ID is not cleared on error**

If the backend rejects a session (e.g., corrupted history), the frontend keeps reusing the same SID forever. There's no recovery path.

---

## What's Actually Good

- Module decomposition is clean — `core/` package with single-responsibility classes is correct.
- The retry/backoff pattern in `LLMService`, `WeaviateRetriever`, and `PersistentMemoryStore` is production-quality.
- SQLite WAL mode + composite index is the right call.
- SSE streaming with abort controller on the frontend is solid.
- Test structure (unit/integration/stress/diagnostics) shows real engineering discipline — most students skip this entirely.
- The ReAct self-correction loop (feeding format errors back as observations) is genuinely clever.

---

## Priority Order for Fixes

1. XSS in `onclick` injection — security
2. Operator precedence bug in early-exit greeting — correctness
3. Upload endpoint hardening — security  
4. Stopword filter in compressor — quality (your test data already proves this is wrong)
5. `run_in_executor` exception swallowing — reliability
6. Deduplicate telemetry assembly — maintainability