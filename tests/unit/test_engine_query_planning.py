import asyncio
import time
import unittest

from src.core.config import PipelineConfig
from src.core.engine import RAGContextEngine


class TestEngineQueryPlanning(unittest.IsolatedAsyncioTestCase):
    async def test_expansion_and_hyde_run_concurrently(self):
        engine = object.__new__(RAGContextEngine)
        engine.pipeline_config = PipelineConfig(enable_expansion=True, enable_hyde=True)
        latencies = {}
        events = []

        async def expand(query, mode, latencies):
            events.append(("expand_start", time.perf_counter()))
            await asyncio.sleep(0.1)
            events.append(("expand_end", time.perf_counter()))
            latencies["phase_1_expansion_ms"] = 100.0
            return [query, "expanded query"]

        async def hyde(query, mode, latencies):
            events.append(("hyde_start", time.perf_counter()))
            await asyncio.sleep(0.1)
            events.append(("hyde_end", time.perf_counter()))
            latencies["phase_1_5_hyde_ms"] = 100.0
            return "hypothetical document"

        engine._phase_expand_async = expand
        engine._phase_hyde_async = hyde

        started = time.perf_counter()
        search_queries, hyde_doc = await engine._phase_expand_and_hyde_async(
            "original query", "context_engine", latencies
        )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.16)
        self.assertEqual(search_queries, ["original query", "expanded query", "hypothetical document"])
        self.assertEqual(hyde_doc, "hypothetical document")

        event_times = dict(events)
        self.assertLess(event_times["hyde_start"], event_times["expand_end"])
        self.assertLess(event_times["expand_start"], event_times["hyde_end"])

    async def test_expand_and_hyde_helper_respects_pipeline_flags(self):
        engine = object.__new__(RAGContextEngine)
        engine.pipeline_config = PipelineConfig(enable_expansion=False, enable_hyde=True)
        latencies = {}

        async def expand(query, mode, latencies):
            raise AssertionError("Expansion should be disabled")

        async def hyde(query, mode, latencies):
            return "hypothetical document"

        engine._phase_expand_async = expand
        engine._phase_hyde_async = hyde

        search_queries, hyde_doc = await engine._phase_expand_and_hyde_async(
            "original query", "context_engine", latencies
        )

        self.assertEqual(search_queries, ["original query", "hypothetical document"])
        self.assertEqual(hyde_doc, "hypothetical document")
        self.assertEqual(latencies["phase_1_expansion_ms"], 0.0)
