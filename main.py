"""
================================================================================
RAG CONTEXT ENGINE API (FastAPI)
================================================================================
This is the primary entry point for the RAG system. It exposes REST endpoints for:
- Document Upload (.pdf, .txt)
- Semantic Search & Querying (Dual-mode)
- System Monitoring (Stats)
- Conversation History
- Static File Serving (UI)
"""

import os
import io
import logging
import traceback
import psutil
import asyncio
import sys
import sentence_transformers
import transformers

print(f"DEBUG: sys.executable = {sys.executable}", flush=True)
print(f"DEBUG: sentence-transformers = {sentence_transformers.__version__}", flush=True)
print(f"DEBUG: transformers = {transformers.__version__}", flush=True)
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Literal, Optional
from pypdf import PdfReader
from dotenv import load_dotenv

from core.config import CHUNK_SIZE, CHUNK_OVERLAP
from core.retriever import WeaviateRetriever
from core.engine import AgenticSystem
from core.splitter import RecursiveCharacterSplitter

# Load environment variables
load_dotenv()

# Configure Application Logging
import logging.handlers
os.makedirs("logs", exist_ok=True)

file_handler = logging.handlers.RotatingFileHandler(
    "logs/rag_engine.log", maxBytes=5*1024*1024, backupCount=3
)
console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger("RAG-API")

# Silence noisy library logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("weaviate").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

# Global instances initialized during lifespan
rag = None
retriever = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    Initializes the heavy ML models and database connections once.
    """
    global rag, retriever
    try:
        logger.info("Starting Agentic System...")
        retriever = WeaviateRetriever()
        rag = AgenticSystem(retriever)
        logger.info("Agentic System successfully initialized.")
        yield
    except Exception as e:
        logger.error(f"Critical error during startup: {e}")
        traceback.print_exc()
        yield
    finally:
        if rag:
            logger.info("Shutting down Agentic System...")
            rag.close()


# Initialize FastAPI App
app = FastAPI(
    title="Premium Modular RAG API",
    description="A high-performance Context Engine with Neural Reranking and Persistent Memory.",
    lifespan=lifespan
)

# Configure CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Serve static assets (CSS, JS)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ------------------------------------------------------------------
# Request / Response Models
# ------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Request schema for the /query endpoint."""
    question: str
    session_id: str = "default"
    mode: Literal["context_engine", "normal", "agentic"] = "context_engine"
    source_filter: Optional[str] = None
    context_limit: Optional[int] = None


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/")
async def serve_ui():
    """Serves the main UI dashboard."""
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(index_path)


@app.post("/query")
async def query_rag(request: QueryRequest):
    """
    Primary endpoint for AI chat.
    Orchestrates the retrieval and generation pipeline.
    """
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    try:
        logger.info(f"Query from session {request.session_id}: {request.question[:50]}...")
        result = await asyncio.to_thread(
            rag.ask,
            request.question,
            session_id=request.session_id,
            mode=request.mode,
            source_filter=request.source_filter,
            context_limit=request.context_limit
        )
        return result
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error processing query: {e}\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Engine Error: {str(e)}\n\nTRACEBACK:\n{error_details}")


@app.post("/query_stream")
async def query_rag_stream(request: QueryRequest):
    """
    Streaming endpoint for AI chat.
    Orchestrates the retrieval and generation pipeline chunk-by-chunk.
    """
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    
    async def event_generator():
        import json
        try:
            logger.info(f"Stream Query from session {request.session_id}: {request.question[:50]}...")
            loop = asyncio.get_event_loop()
            
            def run_sync_gen(queue):
                try:
                    for event in rag.ask_stream(
                        request.question,
                        session_id=request.session_id,
                        mode=request.mode,
                        source_filter=request.source_filter,
                        context_limit=request.context_limit
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                    loop.call_soon_threadsafe(queue.put_nowait, None)
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, {"event": "error", "message": str(e)})
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            queue = asyncio.Queue()
            fut = loop.run_in_executor(None, run_sync_gen, queue)

            def _on_bg_done(f):
                try:
                    f.result()
                except Exception as bg_err:
                    logger.error(f"Background stream thread failed: {bg_err}", exc_info=True)

            fut.add_done_callback(_on_bg_done)

            while True:
                event = await queue.get()
                if event is None:
                    break
                if isinstance(event, dict) and event.get("event") == "error":
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
                
        except asyncio.CancelledError:
            logger.warning(f"Client disconnected from query stream for session {request.session_id}.")
        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Handles file uploads, extracts text, and indexes it into the vector store.
    """
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    try:
        filename = os.path.basename(file.filename)  # sanitize against path traversal
        logger.info(f"Processing upload for: {filename}")

        # Enforce 10MB limit and validate magic bytes using chunked read
        max_size = 10 * 1024 * 1024  # 10MB
        magic_size = 8192  # 8KB
        
        # Read the first chunk for magic bytes validation
        first_chunk = await file.read(magic_size)
        if not first_chunk:
            raise HTTPException(status_code=400, detail="File content is empty.")
        
        total_read = len(first_chunk)
        
        # Identify file type based on magic bytes
        is_pdf = first_chunk.startswith(b"%PDF")
        is_txt = False
        
        if not is_pdf:
            # Check for null bytes to verify it's not binary
            if b"\x00" not in first_chunk:
                # Try to decode the first chunk as UTF-8
                try:
                    first_chunk.decode("utf-8")
                    is_txt = True
                except UnicodeDecodeError:
                    # It might be UTF-8 but cut in the middle of a multi-byte char
                    try:
                        for i in range(4):
                            try:
                                (first_chunk[:len(first_chunk)-i] if i > 0 else first_chunk).decode("utf-8")
                                is_txt = True
                                break
                            except UnicodeDecodeError:
                                continue
                    except Exception:
                        pass
        
        # Validate that we matched at least one allowed type
        if is_pdf:
            logger.info(f"Magic bytes verified: PDF file detected for {filename}")
        elif is_txt:
            logger.info(f"Magic bytes verified: Plain text file detected for {filename}")
        else:
            raise HTTPException(
                status_code=400, 
                detail="Unsupported or invalid file format. Only valid PDF and UTF-8 TXT files are allowed."
            )

        # Read the rest of the file in chunks
        chunks_data = [first_chunk]
        chunk_size = 1024 * 1024  # 1MB chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > max_size:
                raise HTTPException(
                    status_code=400,
                    detail="File too large. Maximum allowed size is 10MB."
                )
            chunks_data.append(chunk)

        file_bytes = b"".join(chunks_data)

        # Extract text based on detected file type
        content = ""
        if is_pdf:
            try:
                pdf_reader = PdfReader(io.BytesIO(file_bytes))
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        content += page_text + "\n"
            except Exception as pdf_err:
                logger.error(f"Failed to parse PDF file content: {pdf_err}")
                raise HTTPException(
                    status_code=400,
                    detail="Failed to parse PDF file content. The file may be corrupt."
                )
        else:  # is_txt
            try:
                content = file_bytes.decode("utf-8")
            except UnicodeDecodeError as txt_err:
                logger.error(f"Failed to decode text file as UTF-8: {txt_err}")
                raise HTTPException(
                    status_code=400,
                    detail="Failed to decode file as UTF-8 text."
                )

        if not content.strip():
            raise HTTPException(status_code=400, detail="File content is empty or contains no extractable text.")

        splitter = RecursiveCharacterSplitter(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        chunks = splitter.split_text(content)

        logger.info(f"Generated {len(chunks)} semantic chunks. Indexing...")
        await asyncio.to_thread(retriever.add_documents, chunks, source=filename)

        return {"status": "success", "message": f"Indexed {len(chunks)} chunks from {filename}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """Returns system performance and database statistics."""
    if not rag:
        return {"status": "initializing"}
    return {
        "queries_handled": rag.stats["queries"],
        "avg_compression": round(rag.stats["avg_compression_ratio"], 3),
        "avg_latency_ms": round(rag.stats.get("avg_latency_ms", 0.0), 2),
        "document_count": retriever.get_count(),
        "cpu_usage_percent": psutil.cpu_percent(interval=None),
        "memory_usage_percent": psutil.virtual_memory().percent,
        "status": "online"
    }


@app.get("/history/{session_id}")
async def get_session_history(session_id: str):
    """Retrieves conversation history for a specific session."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    return rag.persistent_memory.get_history(session_id)


if __name__ == "__main__":
    import uvicorn
    logger.info("Launching Uvicorn server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
