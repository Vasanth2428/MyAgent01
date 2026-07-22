import logging
import os
import re
from typing import List, Dict, Any

from src.core.code.indexer import CodeIndexer
from src.core.code.code_registry import CodeRegistry
from src.core.retriever import WeaviateRetriever

logger = logging.getLogger("RAG.CodeRetrievalService")

# Security vulnerability patterns for auditing
SECURITY_PATTERNS = {
    "hardcoded_secret": [
        r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)(api_key|apikey|api-key)\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)(secret|token)\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)(private_key|privatekey)\s*=\s*['\"][^'\"]+['\"]",
    ],
    "sql_injection": [
        r"(?i)(execute|query|cursor)\s*\(\s*f['\"]",
        r"(?i)(execute|query)\s*\(\s*['\"].*\+",
    ],
    "command_injection": [
        r"(?i)(subprocess|os\.system|os\.popen)\s*\(\s*f['\"]",
        r"(?i)(subprocess|os\.system)\s*\([^)]*\+[^)]*\)",
        r"(?i)subprocess\.call\s*\(\s*f['\"]",
        r"(?i)subprocess\.run\s*\(\s*f['\"]",
        r"(?i)subprocess\.Popen\s*\(\s*f['\"]",
        r"(?i)shell\s*=\s*True",
    ],
    "path_traversal": [
        r"(?i)open\s*\([^)]*\.\./",
        r"(?i)(send|write|read)\s*\([^)]*\.\./",
    ],
}

class CodeRetrievalService:
    """
    Coordinates repository-level code semantic search and symbol analysis.
    """
    def __init__(self, project_root: str, retriever: WeaviateRetriever) -> None:
        self.project_root = project_root
        self.retriever = retriever
        
        self.indexer = CodeIndexer(self.project_root)
        index_file = os.path.join(self.project_root, "checkpoints", "code_index.json")
        self.registry = CodeRegistry(index_file, self.indexer)
        
        # Load pre-existing index if available, otherwise compile one
        if not self.registry.load_index():
            self.indexer.index_repository()
            self.registry.save_index()
            self._push_chunks_to_weaviate()

    def sync_index(self) -> None:
        """Forces a directory scan and persists the updated index on a background task."""
        import asyncio
        
        def _sync_blocking():
            try:
                logger.info("Synchronizing code index in background...")
                self.indexer.index_repository()
                self.registry.save_index()
                self._push_chunks_to_weaviate()
                logger.info("Code index synchronization complete.")
            except Exception as e:
                logger.error(f"Failed background index synchronization: {e}")
                
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _sync_blocking)
        except RuntimeError:
            # Fallback if no event loop is running
            import threading
            threading.Thread(target=_sync_blocking, daemon=True).start()

    def _push_chunks_to_weaviate(self) -> None:
        """Collects semantic chunks from parsed symbols and pushes them to Weaviate."""
        if not hasattr(self.retriever, "add_code_chunks"):
            return
            
        logger.info("Extracting semantic chunks for Weaviate RAG index...")
        chunks = []
        for sym in self.indexer.symbol_table.get_all_symbols():
            if sym.get("text"):
                chunks.append({
                    "text": sym["text"],
                    "filepath": sym.get("filepath", ""),
                    "symbol_name": sym.get("name", ""),
                    "symbol_type": sym.get("type", ""),
                    "start_line": sym.get("start_line", 1),
                    "end_line": sym.get("end_line", 1),
                })
        
        if chunks:
            self.retriever.add_code_chunks(chunks)
            logger.info(f"Pushed {len(chunks)} semantic code chunks to Weaviate.")

    def search_symbols(self, query: str) -> List[Dict[str, Any]]:
        """Fuzzy searches the symbol table for matching functions, methods, or classes."""
        logger.info(f"Symbol query lookup: '{query}'")
        return self.indexer.symbol_table.search_symbols(query)

    def get_symbol_definition(self, name: str) -> List[Dict[str, Any]]:
        """Retrieves exact symbol metadata instances matching name."""
        return self.indexer.symbol_table.get_symbols_by_name(name)

    def get_file_imports(self, filepath: str) -> List[str]:
        """Gets imports declared inside the target file."""
        return self.indexer.dependency_graph.get_imports(filepath)

    def get_file_imported_by(self, filepath: str) -> List[str]:
        """Gets files importing the target file module."""
        return self.indexer.dependency_graph.get_imported_by(filepath)

    def get_symbol_dependencies(self, symbol_name: str) -> Dict[str, List[str]]:
        """Retrieves calls and caller lists for the symbol."""
        return {
            "callees": self.indexer.dependency_graph.get_callees(symbol_name),
            "callers": self.indexer.dependency_graph.get_callers(symbol_name)
        }

    async def hybrid_retrieve(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves matching code snippets using Weaviate vector index and symbol lookup.
        """
        logger.info(f"Hybrid code retrieval query: '{query}'")
        
        # 1. Query Weaviate RAGCode collection if retriever is active
        vector_results = []
        if hasattr(self.retriever, "search_code_chunks"):
            try:
                # We search Weaviate code chunks
                vector_results = self.retriever.search_code_chunks(query, limit=limit)
            except Exception as e:
                logger.error(f"Failed to query Weaviate RAGCode collection: {e}")

        # 2. Extract static symbol matches
        symbol_matches = self.search_symbols(query)
        
        # 3. Combine results
        combined_results = []
        for res in vector_results:
            combined_results.append({
                "type": "code_snippet",
                "text": res.get("text"),
                "filepath": res.get("filepath"),
                "start_line": res.get("start_line"),
                "end_line": res.get("end_line"),
                "symbol_name": res.get("symbol_name"),
                "symbol_type": res.get("symbol_type")
            })

        for sym in symbol_matches[:limit]:
            combined_results.append({
                "type": "symbol_def",
                "text": f"class {sym['name']}" if sym['type'] == 'class' else f"def {sym['name']}",
                "filepath": sym.get("filepath"),
                "start_line": sym.get("start_line"),
                "end_line": sym.get("end_line"),
                "symbol_name": sym.get("name"),
                "symbol_type": sym.get("type"),
                "docstring": sym.get("docstring")
            })

        return combined_results

    async def audit_security(self, filepath: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scans a file for potential security vulnerabilities asynchronously.
        Returns a dict with vulnerability categories and findings.
        """
        import asyncio
        findings = {category: [] for category in SECURITY_PATTERNS}
        
        full_path = os.path.realpath(os.path.join(self.project_root, filepath))
        if not os.path.isfile(full_path):
            logger.warning(f"File not found for security audit: {filepath}")
            return {"error": [f"File '{filepath}' not found for audit"]}

        def _read_file():
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                return content.splitlines()

        try:
            loop = asyncio.get_running_loop()
            lines = await loop.run_in_executor(None, _read_file)
        except RuntimeError:
            lines = _read_file()
        except Exception as e:
            return {"error": [f"Failed to read file for audit: {e}"]}

        for category, patterns in SECURITY_PATTERNS.items():
            for pattern in patterns:
                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        findings[category].append({
                            "line": line_num,
                            "match": line.strip(),
                            "pattern": pattern
                        })
        
        return findings

    def find_symbols_by_file(self, filepath: str) -> List[Dict[str, Any]]:
        """Returns all symbols defined in a specific file."""
        all_symbols = self.indexer.symbol_table.get_all_symbols()
        return [s for s in all_symbols if s.get("filepath") == filepath]

    def get_call_graph(self) -> Dict[str, Dict[str, List[str]]]:
        """Returns the full call graph (callers and callees) for security dependency analysis."""
        return {
            "calls": {k: list(v) for k, v in self.indexer.dependency_graph.calls.items()},
            "called_by": {k: list(v) for k, v in self.indexer.dependency_graph.called_by.items()},
        }

    def store_agent_memory(self, session_id: str, action_summary: str, outcome: str, success: bool = False):
        """Asynchronously stores an episodic memory entry into Weaviate."""
        if hasattr(self.retriever, "store_memory"):
            self.retriever.store_memory(session_id, action_summary, outcome, success)

    def search_agent_memory(self, query: str, session_id: str, limit: int = 2) -> List[Dict[str, Any]]:
        """Retrieves semantically similar episodic memories for the session."""
        if hasattr(self.retriever, "search_memory"):
            return self.retriever.search_memory(query, session_id, limit)
        return []

    def store_rag_doc(self, content: str, library_name: str, url: str = ""):
        """Asynchronously stores an official documentation chunk."""
        if hasattr(self.retriever, "store_rag_doc"):
            self.retriever.store_rag_doc(content, library_name, url)

    def search_rag_docs(self, query: str, library_name: str = None, limit: int = 5) -> List[Dict[str, str]]:
        """Retrieves semantically similar official documentation."""
        if hasattr(self.retriever, "search_rag_docs"):
            return self.retriever.search_rag_docs(query, library_name, limit)
        return []
