"""
================================================================================
RAG CONTEXT ENGINE - RETRIEVER MODULE
================================================================================
This module manages the connection to Weaviate Cloud and implements:
- Vector Indexing (with deterministic UUIDs)
- Hybrid Search (Vector + BM25 with dynamic alpha)
- Metadata Filtering
- Local Embedding Generation
"""

import os
import re
import uuid
import logging
import time
import random
import weaviate
import weaviate.classes as wvc
from weaviate.classes.init import Auth
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional, Tuple
import weaviate.exceptions
from weaviate.classes.query import QueryReference


from core.config import EMBEDDING_MODEL, HYBRID_ALPHA_DEFAULT, HYBRID_ALPHA_KEYWORD

logger = logging.getLogger("RAG.Retriever")

# Technical keywords that signal a query should favor BM25 keyword matching
_TECHNICAL_KEYWORDS = [
    "error", "exception", "status", "syntax", "null", "none",
    "def", "class", "import", "void", "public", "private",
    "int", "str", "code"
]


class WeaviateRetriever:
    """
    Service for interacting with the Weaviate vector database.
    """

    def __init__(self):
        self.url = os.getenv("WEAVIATE_URL")
        self.api_key = os.getenv("WEAVIATE_API_KEY")

        # Connect to Weaviate Cloud with extended timeouts for stability
        config = wvc.init.AdditionalConfig(
            timeout=wvc.init.Timeout(init=60, query=120, insert=120)
        )

        max_conn_retries = 3
        conn_base_delay = 1.0
        for attempt in range(max_conn_retries):
            try:
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=self.url,
                    auth_credentials=Auth.api_key(self.api_key),
                    additional_config=config
                )
                break
            except Exception as e:
                if attempt == max_conn_retries - 1:
                    logger.error(f"Failed to connect to Weaviate Cloud after {max_conn_retries} attempts: {e}")
                    raise
                delay = conn_base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    f"Connection attempt {attempt+1} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                time.sleep(delay)

        # Ensure the collection schema is initialized
        if not self.client.collections.exists("RAGParentKnowledge"):
            logger.info("Initializing 'RAGParentKnowledge' collection...")
            self.client.collections.create(
                name="RAGParentKnowledge",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=[
                    wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
                ]
            )

        recreate_child = False
        if self.client.collections.exists("RAGKnowledge"):
            coll = self.client.collections.get("RAGKnowledge")
            config = coll.config.get()
            has_parent_ref = any(ref.name == "parent" for ref in config.references)
            if not has_parent_ref:
                logger.info("RAGKnowledge collection exists but is missing 'parent' reference. Deleting and recreating for parent-child schema support.")
                self.client.collections.delete("RAGKnowledge")
                recreate_child = True

        if recreate_child or not self.client.collections.exists("RAGKnowledge"):
            logger.info("Initializing 'RAGKnowledge' collection with parent-child references...")
            self.client.collections.create(
                name="RAGKnowledge",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=[
                    wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                    wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
                ],
                references=[
                    wvc.config.ReferenceProperty(
                        name="parent",
                        target_collection="RAGParentKnowledge"
                    )
                ]
            )

        self.collection = self.client.collections.get("RAGKnowledge")
        self.alpha = HYBRID_ALPHA_DEFAULT

        # Load local embedding model
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    def execute_with_retry(self, func, *args, **kwargs):
        """
        Executes a Weaviate client operation with automatic retries on transient errors.
        """
        max_retries = 3
        base_delay = 0.5
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except (
                weaviate.exceptions.WeaviateConnectionError,
                weaviate.exceptions.UnexpectedStatusCodeError,
                weaviate.exceptions.WeaviateQueryError,
                Exception
            ) as e:
                err_name = type(e).__name__
                err_msg = str(e).lower()
                is_transient = any(
                    x in err_msg 
                    for x in ["timeout", "connection", "rate limit", "429", "502", "503", "504", "unavailable", "network"]
                )
                if hasattr(e, "status_code"):
                    if e.status_code == 429 or (e.status_code and e.status_code >= 500):
                        is_transient = True
                
                if not is_transient:
                    raise

                
                if attempt == max_retries - 1:
                    logger.error(f"Weaviate operation failed after {max_retries} attempts: {e}")
                    raise
                
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"Weaviate operation failed with {err_name}: {e}. "
                    f"Retrying in {delay:.2f}s (Attempt {attempt+1}/{max_retries})...."
                )
                time.sleep(delay)

    def add_parent_child_documents(self, parent_child_pairs: List[Tuple[str, List[str]]], tags: List[str] = None, source: str = "unknown"):
        """
        Processes and indexes parent-child document chunks into Weaviate.
        - parent_child_pairs is a list of (parent_text, List[child_texts]).
        - Inserts parent chunks into RAGParentKnowledge and child chunks into RAGKnowledge.
        - Child chunks reference their corresponding parent chunk.
        """
        t_start = time.time()

        parent_objects = []
        child_objects = []
        child_texts = []

        parent_coll = self.client.collections.get("RAGParentKnowledge")
        child_coll = self.client.collections.get("RAGKnowledge")

        for parent_text, children in parent_child_pairs:
            # Deterministic Parent UUID
            parent_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"parent_{parent_text}")
            parent_objects.append({
                "uuid": parent_uuid,
                "properties": {"text": parent_text, "source": source}
            })

            for child_text in children:
                # Deterministic Child UUID
                child_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"child_{child_text}")
                child_texts.append(child_text)
                child_objects.append({
                    "uuid": child_uuid,
                    "parent_uuid": parent_uuid,
                    "properties": {
                        "text": child_text,
                        "tags": tags or [],
                        "source": source
                    }
                })

        if not child_texts:
            return

        # Generate embeddings for all children
        embeddings = self.embedding_model.encode(child_texts)
        t_embed = time.time()
        logger.debug(f"Generated {len(child_texts)} embeddings in {(t_embed - t_start)*1000:.1f}ms")

        # Dynamic Batch Insert Parents
        def _batch_insert_parents():
            with parent_coll.batch.dynamic() as batch:
                for p in parent_objects:
                    batch.add_object(
                        properties=p["properties"],
                        uuid=p["uuid"]
                    )
                batch.flush()
                failed = parent_coll.batch.failed_objects
                if failed:
                    raise Exception(
                        f"Weaviate parent batch insert failed for {len(failed)} objects. First error: {failed[0].message}"
                    )

        self.execute_with_retry(_batch_insert_parents)

        # Dynamic Batch Insert Children pointing to Parents
        def _batch_insert_children():
            with child_coll.batch.dynamic() as batch:
                for i, c in enumerate(child_objects):
                    batch.add_object(
                        properties=c["properties"],
                        vector=embeddings[i].tolist() if hasattr(embeddings[i], "tolist") else embeddings[i],
                        uuid=c["uuid"],
                        references={"parent": c["parent_uuid"]}
                    )
                batch.flush()
                failed = child_coll.batch.failed_objects
                if failed:
                    raise Exception(
                        f"Weaviate child batch insert failed for {len(failed)} objects. First error: {failed[0].message}"
                    )

        self.execute_with_retry(_batch_insert_children)

        t_batch = time.time()
        logger.info(
            f"Indexed {len(parent_objects)} parents and {len(child_objects)} children from '{source}' in {(t_batch - t_start)*1000:.1f}ms "
            f"(Embed: {(t_embed - t_start)*1000:.1f}ms, Insert: {(t_batch - t_embed)*1000:.1f}ms)"
        )

    def add_documents(self, docs: List[str], tags: List[str] = None, source: str = "unknown"):
        """
        Backward compatible flat document chunk list ingestion.
        Treats each document chunk as its own parent.
        """
        # Convert each chunk to a parent-child relationship where the chunk is both parent and child
        pairs = [(doc, [doc]) for doc in docs]
        self.add_parent_child_documents(pairs, tags=tags, source=source)


    def _detect_alpha(self, query: str) -> float:
        """
        Dynamically adjusts hybrid alpha based on query content.
        Technical/code queries shift toward BM25 keyword matching.
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        if any(kw in query_words for kw in _TECHNICAL_KEYWORDS) or re.search(r'[\{\}\[\]\(\)\.\\_\|]', query):
            return HYBRID_ALPHA_KEYWORD
        return HYBRID_ALPHA_DEFAULT

    def retrieve(self, query: str, top_k: int = 5, source_filter: str = None) -> List[Dict]:
        """
        Performs a Hybrid Search (Semantic + Keyword) with optional hard filtering.
        Retrieves the small child chunks, but resolves and serves their parent chunks.
        """
        t_start = time.time()
        query_vector = self.embedding_model.encode(query).tolist()
        t_embed = time.time()

        # Construct property filter
        filters = wvc.query.Filter.by_property("source").equal(source_filter) if source_filter else None

        # Dynamically classify query type
        alpha = self._detect_alpha(query)
        self.alpha = alpha

        def _query_db():
            return self.collection.query.hybrid(
                query=query,
                vector=query_vector,
                alpha=alpha,
                limit=top_k,
                filters=filters,
                return_properties=["text", "tags", "source"],
                return_references=[
                    QueryReference(
                        link_on="parent",
                        return_properties=["text", "source"]
                    )
                ],
                return_metadata=wvc.query.MetadataQuery(score=True)
            )

        response = self.execute_with_retry(_query_db)

        t_search = time.time()
        self.last_embed_latency_ms = (t_embed - t_start) * 1000
        self.last_search_latency_ms = (t_search - t_embed) * 1000

        res = []
        for obj in response.objects:
            text = obj.properties["text"]  # child text fallback
            if "parent" in obj.references and obj.references["parent"].objects:
                parent_text = obj.references["parent"].objects[0].properties.get("text")
                if parent_text:
                    text = parent_text
            
            res.append({
                "text": text,
                "tags": obj.properties.get("tags") or [],
                "source": obj.properties.get("source"),
                "score": obj.metadata.score
            })

        logger.info(
            f"Hybrid search (alpha={alpha}) found {len(res)} results "
            f"in {(t_search - t_start)*1000:.1f}ms"
        )
        return res

    def get_count(self) -> int:
        """Returns the total number of objects in the RAGKnowledge collection."""
        try:
            def _aggregate():
                res = self.collection.aggregate.over_all(total_count=True)
                return res.total_count
            return self.execute_with_retry(_aggregate)
        except Exception:
            return 0

    def get_sources(self) -> List[str]:
        """Returns a list of all unique source names in the collection."""
        try:
            def _aggregate():
                res = self.collection.aggregate.over_all(group_by="source")
                return [group.grouped_by.value for group in res.groups if group.grouped_by and group.grouped_by.value]
            return self.execute_with_retry(_aggregate)
        except Exception as e:
            logger.error(f"Failed to aggregate sources: {e}")
            return []

    def close(self):
        """Safely terminates the connection to Weaviate Cloud."""
        if self.client:
            self.client.close()
