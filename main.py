"""
RAG Context Engine API

This is the main entry point for the RAG system. It starts a web server with endpoints for:
- Uploading documents (PDF and text files)
- Asking questions (with both regular and streaming responses)
- Checking system statistics
- Viewing conversation history
- Loading the web interface
"""

import os
import io
import json
import logging
import traceback
import psutil
import asyncio
import sys
import sentence_transformers
import transformers

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        try:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

print(f"DEBUG: sys.executable = {sys.executable}", flush=True)
print(f"DEBUG: sentence-transformers = {sentence_transformers.__version__}", flush=True)
print(f"DEBUG: transformers = {transformers.__version__}", flush=True)
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, HTTPException, UploadFile, File, Response, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
from pypdf import PdfReader
from dotenv import load_dotenv

def _serialize_event(event):
    """
    Serialize an event dict to JSON, handling non-serializable LangChain message objects.
    AIMessage, HumanMessage, ToolMessage, etc. are converted to their content string.
    """
    def _convert(value):
        if isinstance(value, dict):
            return {k: _convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_convert(v) for v in value]
        # Handle LangChain BaseMessage subclasses (AIMessage, HumanMessage, etc.)
        if hasattr(value, "content"):
            return str(value.content)
        # Leave primitives as-is
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        return str(value)
    
    try:
        return json.dumps(_convert(event))
    except Exception:
        # Fallback: try to convert the entire event
        return json.dumps(_convert(event))

# Load environment variables from config directory
load_dotenv(dotenv_path="config/.env", override=True)

import uuid

from src.core.config import CHUNK_SIZE, CHUNK_OVERLAP, PipelineConfig
from src.core.retriever import WeaviateRetriever
from src.core.engine import RAGContextEngine
from src.core.splitter import RecursiveCharacterSplitter
from src.core.scraper import close_aiohttp_session
from src.tools.coding_tools import WORKSPACE_ROOT, _get_absolute_path, _has_allowed_extension, ALLOWED_EXTENSIONS
import base64

def is_safe_workspace_path(filepath: str) -> bool:
    try:
        abs_path = _get_absolute_path(filepath)
        real_workspace = os.path.realpath(WORKSPACE_ROOT)
        if os.name == 'nt':
            return abs_path.lower().startswith(real_workspace.lower())
        return abs_path.startswith(real_workspace)
    except Exception:
        return False

# Configure Application Logging
import logging.handlers
from src.core.logging_setup import SessionFileHandler, session_id_var
os.makedirs("logs", exist_ok=True)

console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
console_handler.setFormatter(formatter)

file_handler = SessionFileHandler(
    default_log_path="logs/rag_engine.log",
    log_dir="logs/sessions",
    formatter=formatter
)

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
_model_warmup_task = None


def _warm_local_models() -> None:
    logger.info("Pre-warming local embedding and reranker models...")
    from src.core.services.grounding_service import _get_shared_embedding_model
    _ = _get_shared_embedding_model()
    from src.core.reranker import _get_flashrank_reranker
    _ = _get_flashrank_reranker()
    logger.info("Heavy ML models successfully pre-warmed.")


async def _warm_local_models_background() -> None:
    try:
        await asyncio.to_thread(_warm_local_models)
    except Exception as warm_err:
        logger.warning(f"Background model warmup failed: {warm_err}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    Initializes the heavy ML models and database connections once.
    """
    global rag, retriever, _model_warmup_task
    try:
        logger.info("Starting Modular RAG Context Engine...")
        retriever = WeaviateRetriever()
        pipeline_config = PipelineConfig.from_env()
        logger.info(f"Pipeline config: hyde={pipeline_config.enable_hyde}, expansion={pipeline_config.enable_expansion}, reranking={pipeline_config.enable_reranking}, compression={pipeline_config.enable_compression}")
        
        from src.graph.checkpointer import setup_async_checkpointer
        
        async with setup_async_checkpointer() as checkpointer:
            rag = RAGContextEngine(retriever, pipeline_config, checkpointer=checkpointer)
            logger.info("RAG Engine successfully initialized.")
            _model_warmup_task = asyncio.create_task(_warm_local_models_background())
            try:
                summary = rag.registry.get_registry_summary()
                logger.info(f"Knowledge Registry Summary: Datasets={summary['datasets']}, Domains={summary['domains']}, Total Docs={summary['total_documents_count']}")
            except Exception as reg_err:
                logger.warning(f"Could not load Knowledge Registry summary on startup: {reg_err}")
            
            yield
    except Exception as e:
        logger.error(f"Critical error during startup: {e}")
        traceback.print_exc()
        yield
    finally:
        if _model_warmup_task and not _model_warmup_task.done():
            _model_warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await _model_warmup_task
        if rag:
            logger.info("Shutting down RAG Engine...")
            rag.close()
        try:
            asyncio.get_event_loop().create_task(close_aiohttp_session())
        except Exception:
            pass


# Initialize FastAPI App
app = FastAPI(
    title="Modular RAG API Prototype",
    description="A Context Engine utilizing lightweight local embeddings (all-MiniLM-L6-v2) for rapid prototyping, featuring Neural Reranking and SQLite-based Persistent Memory.",
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

from starlette.types import ASGIApp, Scope, Receive, Send

class ConditionalGZipMiddleware:
    """
    Middleware that wraps GZipMiddleware but bypasses it for streaming endpoints.
    This prevents buffering and chunked encoding errors for Server-Sent Events (SSE).
    """
    def __init__(self, app: ASGIApp, minimum_size: int = 1024):
        self.app = app
        self.gzip_middleware = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path in ("/query_stream", "/resume_stream") or "_stream" in path:
                await self.app(scope, receive, send)
                return
        await self.gzip_middleware(scope, receive, send)

# Enable Gzip compression for payloads > 1024 bytes, bypassing streaming endpoints
app.add_middleware(ConditionalGZipMiddleware, minimum_size=1024)

# Custom static files class with caching headers
class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        return response

# Serve static assets (CSS, JS) with caching headers
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")


# Pure ASGI middleware to set session_id context variable for logging.
# IMPORTANT: This must NOT use @app.middleware("http") / BaseHTTPMiddleware because
# BaseHTTPMiddleware wraps StreamingResponse bodies through an intermediate
# anyio MemoryObjectStream, which causes premature stream closure and
# ERR_INCOMPLETE_CHUNKED_ENCODING errors on SSE endpoints.
class SessionLoggingMiddleware:
    """Pure ASGI middleware that extracts session_id and sets the logging context variable."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session_id = None
        path = scope.get("path", "")

        # 1. Parse session_id from URL path segments
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("history", "sessions", "pending_approval", "resume_stream"):
            session_id = parts[1]

        # 2. Check query parameters
        if not session_id:
            from urllib.parse import parse_qs
            qs = scope.get("query_string", b"").decode("utf-8", errors="replace")
            params = parse_qs(qs)
            if "session_id" in params:
                session_id = params["session_id"][0]

        # 3. Check JSON request body for POST requests
        if not session_id and scope.get("method") == "POST":
            content_type = ""
            for hdr_name, hdr_value in scope.get("headers", []):
                if hdr_name.lower() == b"content-type":
                    content_type = hdr_value.decode("utf-8", errors="replace")
                    break

            if "application/json" in content_type:
                # Buffer the raw body bytes from the ASGI receive channel
                body_chunks = []
                while True:
                    message = await receive()
                    body_chunks.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        break
                body = b"".join(body_chunks)

                try:
                    if body:
                        data = json.loads(body)
                        session_id = data.get("session_id")
                except Exception:
                    pass

                # Replace receive so downstream handlers can still read the body
                original_receive = receive
                body_replayed = False
                async def replay_receive():
                    nonlocal body_replayed
                    if not body_replayed:
                        body_replayed = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    # Delegate subsequent calls to original receive channel to block correctly
                    return await original_receive()

                receive = replay_receive

        token = session_id_var.set(session_id)
        try:
            await self.app(scope, receive, send)
        finally:
            session_id_var.reset(token)

app.add_middleware(SessionLoggingMiddleware)


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
    bypass_hitl: bool = False
    model_provider: Optional[str] = None
    model_name: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """Request schema for creating a new session."""
    session_id: Optional[str] = None
    title: str = "New Chat"


class RenameSessionRequest(BaseModel):
    """Request schema for renaming a session."""
    title: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


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

    return await rag.ask_async(
        request.question,
        session_id=request.session_id,
        mode=request.mode,
        source_filter=request.source_filter,
        top_k=5,
        context_limit=request.context_limit,
        bypass_hitl=request.bypass_hitl,
        model_provider=request.model_provider,
        model_name=request.model_name
    )


@app.post("/query_stream")
async def query_rag_stream(request: QueryRequest):
    """
    Streaming endpoint for AI chat.
    Orchestrates the retrieval and generation pipeline chunk-by-chunk.
    """
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    
    async def event_generator():
        try:
            logger.info(f"Stream Query from session {request.session_id}: {request.question[:50]}...")
            async for event in rag.ask_stream_async(
                request.question,
                session_id=request.session_id,
                mode=request.mode,
                source_filter=request.source_filter,
                context_limit=request.context_limit,
                bypass_hitl=request.bypass_hitl,
                model_provider=request.model_provider,
                model_name=request.model_name
            ):
                yield f"data: {_serialize_event(event)}\n\n"
        except asyncio.CancelledError:
            logger.warning(f"Client disconnected from query stream for session {request.session_id}.")
        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            yield f"data: {_serialize_event({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")



@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Handles file uploads, extracts text, and indexes it into the vector store.
    """
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    try:
        filename = file.filename
        logger.info(f"Processing upload for: {filename}")

        content = ""
        if filename.endswith(".txt"):
            content = (await file.read()).decode("utf-8")
        elif filename.endswith(".pdf"):
            pdf_data = await file.read()
            pdf_reader = PdfReader(io.BytesIO(pdf_data))
            for page in pdf_reader.pages:
                content += page.extract_text() + "\n"
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type.")

        if not content.strip():
            raise HTTPException(status_code=400, detail="File content is empty.")

        splitter = RecursiveCharacterSplitter(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        chunks = splitter.split_text(content)

        logger.info(f"Generated {len(chunks)} semantic chunks. Indexing...")
        await asyncio.to_thread(retriever.add_documents, chunks, source=filename)

        return {"status": "success", "message": f"Indexed {len(chunks)} chunks from {filename}"}
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


# ------------------------------------------------------------------
# Session Management Endpoints
# ------------------------------------------------------------------

@app.get("/sessions")
async def list_sessions():
    """Returns all sessions ordered by most recently updated."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    return rag.persistent_memory.list_sessions()


@app.post("/sessions", status_code=201)
async def create_session(request: CreateSessionRequest):
    """Creates a new chat session."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    sid = request.session_id or ("SID-" + uuid.uuid4().hex[:8].upper())
    rag.persistent_memory.create_session(sid, request.title)
    return {"session_id": sid, "title": request.title}


@app.patch("/sessions/{session_id}")
async def rename_session(session_id: str, request: RenameSessionRequest):
    """Renames an existing session."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    rag.persistent_memory.rename_session(session_id, request.title.strip()[:80])
    return {"session_id": session_id, "title": request.title}


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """Deletes a session and all its conversation history."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    rag.delete_session(session_id)
    return None


# ------------------------------------------------------------------
# Workspace IDE Endpoints
# ------------------------------------------------------------------

class WriteFileRequest(BaseModel):
    path: str
    content: str


@app.post("/workspace/browse-native")
async def browse_workspace_native():
    """Opens a native folder picker dialog and sets the workspace root."""
    import tkinter as tk
    from tkinter import filedialog
    import threading
    import src.tools.coding_tools as ct
    
    result = {"path": None}
    
    def _open_dialog():
        root = tk.Tk()
        root.attributes("-topmost", True)
        root.withdraw()
        path = filedialog.askdirectory(parent=root, title="Select Workspace Root")
        result["path"] = path
        root.destroy()
        
    thread = threading.Thread(target=_open_dialog)
    thread.start()
    thread.join()
    
    selected_path = result["path"]
    if selected_path:
        ct.WORKSPACE_ROOT = selected_path
        os.environ["AGENT_WORKSPACE_ROOT"] = selected_path
        global WORKSPACE_ROOT
        WORKSPACE_ROOT = selected_path
        return {"success": True, "path": selected_path}
    return {"success": False, "error": "No folder selected"}


@app.get("/workspace/files")
async def list_workspace_files():
    """Recursively lists all allowed files in the workspace, excluding temporary/cache folders."""
    if not os.path.exists(WORKSPACE_ROOT):
        return []
    
    exclude_dirs = {
        ".git", ".venv", "venv", "node_modules", ".backups", "checkpoints",
        ".pytest_cache", ".ruff_cache", "__pycache__"
    }
    exclude_files = {
        ".env", ".gitignore", ".python-version"
    }
    
    files_list = []
    real_workspace = os.path.realpath(WORKSPACE_ROOT)
    
    for root, dirs, files in os.walk(real_workspace):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file in exclude_files:
                continue
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, real_workspace)
            rel_path_web = rel_path.replace("\\", "/")
            files_list.append(rel_path_web)
            
    return files_list


@app.get("/workspace/file")
async def get_workspace_file(path: str):
    """Reads a file from the workspace, base64-encoding it if it is an image."""
    if not is_safe_workspace_path(path):
        raise HTTPException(status_code=403, detail="Access denied: outside workspace boundary")
        
    abs_path = _get_absolute_path(path)
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    _, ext = os.path.splitext(abs_path)
    ext = ext.lower()
    
    binary_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"}
    
    try:
        if ext in binary_extensions:
            with open(abs_path, "rb") as f:
                content_bytes = f.read()
            encoded = base64.b64encode(content_bytes).decode("utf-8")
            
            mime_type = "image/png"
            if ext in (".jpg", ".jpeg"):
                mime_type = "image/jpeg"
            elif ext == ".gif":
                mime_type = "image/gif"
            elif ext == ".svg":
                mime_type = "image/svg+xml"
            elif ext == ".ico":
                mime_type = "image/x-icon"
                
            return {
                "is_binary": True,
                "mime_type": mime_type,
                "content": f"data:{mime_type};base64,{encoded}"
            }
        else:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "is_binary": False,
                "content": content
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@app.post("/workspace/write")
async def write_workspace_file(request: WriteFileRequest):
    """Safely saves code file changes to disk inside the workspace."""
    if not is_safe_workspace_path(request.path):
        raise HTTPException(status_code=403, detail="Access denied: outside workspace boundary")
        
    if not _has_allowed_extension(request.path):
        allowed_str = ", ".join(ALLOWED_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"File extension not allowed. Approved extensions: {allowed_str}"
        )
        
    abs_path = _get_absolute_path(request.path)
    dir_name = os.path.dirname(abs_path)
    if not os.path.exists(dir_name):
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create directory: {str(e)}")
            
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(request.content)
        return {"status": "success", "message": f"Successfully saved {request.path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing file: {str(e)}")



# ------------------------------------------------------------------
# Approval Management Endpoints (Human-in-the-Loop)
# ------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    session_id: str
    approve: bool

@app.get("/pending_approval/{session_id}")
async def get_pending_approval(session_id: str):
    """Check if there are pending file changes awaiting approval."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    from src.agents.coding_worker import get_pending_approval
    pending = get_pending_approval(session_id)
    if pending:
        return {
            "has_pending": True, 
            "filepath": pending["filepath"], 
            "tool": pending["tool"],
            "diff": pending.get("diff", "")
        }
    return {"has_pending": False}

@app.post("/approve_changes")
async def approve_changes(request: ApprovalRequest):
    """Approve or reject pending file changes and continue workflow."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    from src.agents.coding_worker import get_pending_approval, execute_pending_approval, clear_pending_approval
    from langchain_core.messages import HumanMessage, AIMessage
    from src.graph.workflow import get_graph_config
    from src.graph.supervisor import approve_file
    from src.tools.coding_tools import _get_absolute_path
    
    session_id = request.session_id
    pending = get_pending_approval(session_id)
    
    if not pending:
        return {"status": "no_pending_approval"}
    
    config = get_graph_config(session_id)
    
    if request.approve:
        try:
            abs_path = os.path.realpath(_get_absolute_path(pending['filepath']))
            approve_file(session_id, abs_path)
        except Exception as e:
            logger.warning(f"Failed to register approval for {pending['filepath']}: {e}")
            
        result = execute_pending_approval(session_id)
        logger.info(f"Approval executed: {result}")
        
        if hasattr(rag.multi_agent_graph, "aupdate_state"):
            await rag.multi_agent_graph.aupdate_state(config, {
                "scratchpad": f"\n- [SYSTEM HITL]: User approved modifications. Action result: {result}",
                "waiting_for_approval": False,
                "pending_file_approvals": {},
                "approval_decision": "approved",
                "next_agent": "supervisor",
                "current_task": "Resume after approved file operation.",
                "coding_worker_resume_tool_result": result,
                "coding_worker_resume_tool_call_id": pending.get("tool_call_id")
            })
        else:
            rag.multi_agent_graph.update_state(config, {
                "scratchpad": f"\n- [SYSTEM HITL]: User approved modifications. Action result: {result}",
                "waiting_for_approval": False,
                "pending_file_approvals": {},
                "approval_decision": "approved",
                "next_agent": "supervisor",
                "current_task": "Resume after approved file operation.",
                "coding_worker_resume_tool_result": result,
                "coding_worker_resume_tool_call_id": pending.get("tool_call_id")
            })
        
        return {"status": "approved", "result": result, "message": "Tool executed successfully"}
    else:
        clear_pending_approval(session_id)
        try:
            if hasattr(rag.multi_agent_graph, "aupdate_state"):
                await rag.multi_agent_graph.aupdate_state(config, {
                    "waiting_for_approval": False,
                    "pending_file_approvals": {},
                    "worker_outputs": {"coding_worker": "User rejected file changes."},
                    "approval_decision": "rejected",
                    "next_agent": "supervisor",
                    "current_task": "User rejected file changes; continue without applying them.",
                    "coding_worker_resume_tool_result": "Error: User rejected the file modifications.",
                    "coding_worker_resume_tool_call_id": pending.get("tool_call_id")
                })
            else:
                rag.multi_agent_graph.update_state(config, {
                    "waiting_for_approval": False,
                    "pending_file_approvals": {},
                    "worker_outputs": {"coding_worker": "User rejected file changes."},
                    "approval_decision": "rejected",
                    "next_agent": "supervisor",
                    "current_task": "User rejected file changes; continue without applying them.",
                    "coding_worker_resume_tool_result": "Error: User rejected the file modifications.",
                    "coding_worker_resume_tool_call_id": pending.get("tool_call_id")
                })
        except Exception:
            pass
        return {"status": "rejected"}


@app.get("/resume_stream/{session_id}")
async def resume_stream(session_id: str):
    """
    Resume a paused workflow (e.g., after file approval) and stream the continued
    execution as Server-Sent Events.  The frontend calls this after POSTing to
    /approve_changes so the user can see the resumed agent output live.
    """
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")

    from src.graph.workflow import get_graph_config

    async def event_generator():
        config = get_graph_config(session_id)
        try:
            logger.info(f"Resuming workflow stream for session {session_id}")
            if hasattr(rag.multi_agent_graph, "astream"):
                async for event in rag.multi_agent_graph.astream(None, config=config):
                    for node_name, state_delta in event.items():
                        yield f"data: {_serialize_event({'event': 'node_start', 'node': node_name})}\n\n"

                        worker_type = state_delta.get("worker_type", "") or node_name.replace("_node", "")
                        response = ""
                        if "worker_outputs" in state_delta and worker_type:
                            response = state_delta["worker_outputs"].get(worker_type, "")
                        if not response and "messages" in state_delta and state_delta["messages"]:
                            response = state_delta["messages"][-1].content

                        if response:
                            yield f"data: {_serialize_event({'event': 'thought', 'text': f'{worker_type}: {response[:120]}'})}\n\n"
                            yield f"data: {_serialize_event({'event': 'observation', 'output': response})}\n\n"

                        if state_delta.get("waiting_for_approval"):
                            approval_filepath = state_delta.get("approval_filepath", "")
                            approval_tool = state_delta.get("approval_tool", "")
                            from src.agents.coding_worker import get_pending_approval
                            pending = get_pending_approval(session_id)
                            diff_val = pending.get("diff", "") if pending else ""
                            yield f"data: {_serialize_event({'event': 'blocked_tool', 'filepath': approval_filepath, 'tool': approval_tool, 'diff': diff_val})}\n\n"
                            yield f"data: {_serialize_event({'event': 'waiting_for_approval', 'filepath': approval_filepath, 'tool': approval_tool})}\n\n"
                            return

                        if "final_answer" in state_delta and state_delta["final_answer"]:
                            answer = state_delta["final_answer"]
                            for chunk in answer.split(" "):
                                yield f"data: {_serialize_event({'event': 'answer_chunk', 'text': chunk + ' '})}\n\n"

                yield f"data: {_serialize_event({'event': 'done', 'stats': {}})}\n\n"
                
                # Check if workflow is waiting for approval after graph completes
                try:
                    current_state = await rag.multi_agent_graph.aget_state(config)
                    if current_state and current_state.values:
                        state_values = current_state.values
                        waiting_for_approval = state_values.get("waiting_for_approval", False)
                        if waiting_for_approval:
                            pending_file_approvals = state_values.get("pending_file_approvals", {})
                            approval_filepath = state_values.get("approval_filepath", "")
                            approval_tool = state_values.get("approval_tool", "")
                            
                            from src.agents.coding_worker import get_pending_approval
                            pending = get_pending_approval(session_id)
                            diff_val = pending.get("diff", "") if pending else ""
                            
                            approval_packet = {
                                "waiting_for_approval": True,
                                "pending_file_approvals": pending_file_approvals,
                                "approval_filepath": approval_filepath,
                                "approval_tool": approval_tool,
                                "diff": diff_val,
                                "text": "\n\n⚠️ **Action Required:** This modification requires security validation. Please approve or reject below."
                            }
                            yield f"data: {_serialize_event(approval_packet)}\n\n"
                except Exception as state_err:
                    logger.warning(f"Failed to get state after stream: {state_err}")
        except asyncio.CancelledError:
            logger.warning(f"Client disconnected from resume stream for session {session_id}.")
        except Exception as e:
            logger.error(f"Resume stream error: {e}")
            yield f"data: {_serialize_event({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# =================================================================
# Git & Interactive Terminal Support Endpoints
# =================================================================

class GitCloneRequest(BaseModel):
    url: str
    pat: Optional[str] = None

class GitStageRequest(BaseModel):
    file_path: str
    stage: bool

class GitCommitRequest(BaseModel):
    message: str


async def run_git_command(*args: str) -> str:
    """Helper to run a git command in the workspace root."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=WORKSPACE_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
        return output.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git command failed: {str(e)}")


@app.get("/git/status")
async def git_status():
    """Gets the current git branch and uncommitted modifications in the workspace."""
    git_dir = os.path.join(WORKSPACE_ROOT, ".git")
    if not os.path.exists(git_dir):
        return {"is_repo": False, "branch": "", "files": []}
        
    branch = await run_git_command("branch", "--show-current")
    status_output = await run_git_command("status", "--porcelain")
    
    files = []
    if status_output:
        for line in status_output.split("\n"):
            if not line or len(line) < 4:
                continue
            xy = line[:2]
            file_path = line[3:].strip()
            
            # Map index/worktree status codes
            status_tag = 'untracked'
            if 'M' in xy:
                status_tag = 'modified'
            elif 'A' in xy:
                status_tag = 'added'
            elif 'D' in xy:
                status_tag = 'deleted'
            elif '??' in xy:
                status_tag = 'untracked'
                
            files.append({
                "path": file_path,
                "status": status_tag,
                "raw": xy
            })
            
    return {"is_repo": True, "branch": branch, "files": files}


@app.post("/git/init")
async def git_init():
    """Initializes a new git repository in the workspace."""
    output = await run_git_command("init")
    return {"status": "success", "output": output}


@app.post("/git/clone")
async def git_clone(request: GitCloneRequest):
    """Clones a remote git repository into a folder in the workspace."""
    url = request.url
    if request.pat:
        if "github.com/" in url:
            prefix = "https://" if url.startswith("https://") else ""
            clean_url = url.replace("https://", "")
            url = f"{prefix}{request.pat}@{clean_url}"
            
    try:
        repo_name = url.split("/")[-1].replace(".git", "")
        target_path = os.path.join(WORKSPACE_ROOT, repo_name)
        
        if not is_safe_workspace_path(target_path):
            raise HTTPException(status_code=403, detail="Access denied: target path is outside workspace")
            
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            url,
            target_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            raise HTTPException(status_code=400, detail=f"Clone failed: {err_msg}")
        return {"status": "success", "message": f"Successfully cloned into {repo_name}"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Clone failed: {str(e)}")


@app.post("/git/stage")
async def git_stage(request: GitStageRequest):
    """Stages (add) or unstages (reset) a file in Git."""
    if not is_safe_workspace_path(request.file_path):
        raise HTTPException(status_code=403, detail="Access denied: file path is outside workspace")
        
    if request.stage:
        output = await run_git_command("add", request.file_path)
    else:
        output = await run_git_command("reset", "HEAD", request.file_path)
    return {"status": "success", "output": output}


@app.post("/git/commit")
async def git_commit(request: GitCommitRequest):
    """Commits staged changes in Git."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Commit message cannot be empty")
    output = await run_git_command("commit", "-m", request.message)
    return {"status": "success", "output": output}


@app.post("/git/sync")
async def git_sync():
    """Pulls recent changes and pushes committed work to the remote repo."""
    pull_output = await run_git_command("pull")
    push_output = await run_git_command("push")
    return {
        "status": "success",
        "pull_output": pull_output,
        "push_output": push_output
    }


@app.websocket("/terminal")
async def terminal_endpoint(websocket: WebSocket):
    """Establishes an interactive shell terminal subprocess via WebSocket.
    Uses PTY on Unix for proper line editing (backspace, history, etc.).
    Windows uses enhanced pipe mode due to lack of native PTY support."""
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if origin and host:
        from urllib.parse import urlparse
        parsed_origin = urlparse(origin)
        if parsed_origin.netloc != host:
            await websocket.close(code=1008)
            return

    await websocket.accept()

    try:
        if sys.platform == "win32":
            await _run_windows_terminal(websocket)
        else:
            await _run_unix_terminal(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"\r\n[Terminal Error] {str(e)}\r\n")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _run_unix_terminal(websocket: WebSocket):
    """Run terminal with PTY on Unix for proper terminal behavior."""
    import pty
    import fcntl
    import termios
    import struct

    shell = os.environ.get("SHELL", "/bin/bash")

    master_fd, slave_fd = pty.openpty()

    try:
        try:
            winsize = struct.pack("HHHH", 24, 80, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

        try:
            proc = await asyncio.create_subprocess_exec(
                shell,
                "-i",
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start shell: {e}") from e
        finally:
            os.close(slave_fd)
            slave_fd = -1

        loop = asyncio.get_event_loop()

        def _forward_master_to_ws():
            try:
                data = os.read(master_fd, 4096)
                if data:
                    asyncio.ensure_future(
                        websocket.send_text(data.decode("utf-8", errors="replace"))
                    )
            except (OSError, ValueError):
                pass
            except Exception:
                pass

        try:
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except Exception:
            pass

        loop.add_reader(master_fd, _forward_master_to_ws)

        async def ws_reader():
            try:
                while True:
                    message = await websocket.receive_text()

                    try:
                        resize_data = json.loads(message)
                        if resize_data.get("type") == "resize":
                            try:
                                cols = int(resize_data.get("cols", 80))
                                rows = int(resize_data.get("rows", 24))
                                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                            except Exception:
                                pass
                            continue
                    except ( ValueError, TypeError):
                        pass

                    try:
                        os.write(master_fd, message.encode("utf-8"))
                    except (OSError, ValueError):
                        break
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        ws_task = asyncio.create_task(ws_reader())

        try:
            await proc.wait()
        except Exception:
            pass
        finally:
            try:
                loop.remove_reader(master_fd)
            except Exception:
                pass
            try:
                os.close(master_fd)
            except Exception:
                pass
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await proc.wait()
                except Exception:
                    pass
    finally:
        if slave_fd > 0:
            try:
                os.close(slave_fd)
            except Exception:
                pass


async def _run_windows_terminal(websocket: WebSocket):
    """Run terminal on Windows with basic line-editing support.
    Without a native PTY on Windows, the shell runs in pipe mode and
    does not expose native line editing. This wrapper buffers the
    current input line locally so backspace works and the full line
    is only forwarded on Enter."""
    shell = "powershell.exe"
    args = ["-NoLogo"]

    try:
        proc = await asyncio.create_subprocess_exec(
            shell,
            *args,
            cwd=WORKSPACE_ROOT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=0x08000000,
        )
    except Exception as e:
        await websocket.send_text(f"\r\n[Terminal Error] Failed to start shell: {str(e)}\r\n")
        await websocket.close()
        return

    async def read_stdout():
        try:
            while True:
                data = await proc.stdout.read(1024)
                if not data:
                    break
                await websocket.send_text(data.decode("utf-8", errors="replace"))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def read_stderr():
        try:
            while True:
                data = await proc.stderr.read(1024)
                if not data:
                    break
                await websocket.send_text(data.decode("utf-8", errors="replace"))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def read_websocket():
        line_buffer = ""
        try:
            while True:
                message = await websocket.receive_text()

                if message in ("\x7f", "\x08"):
                    if line_buffer:
                        line_buffer = line_buffer[:-1]
                        await websocket.send_text("\x08 \x08")
                    continue

                if message == "\x03":
                    line_buffer = ""
                    try:
                        proc.stdin.write(b"\x03")
                        await proc.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    continue

                if message == "\x04":
                    line_buffer = ""
                    try:
                        proc.stdin.write(b"\x04")
                        await proc.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    continue

                if message in ("\r", "\n"):
                    try:
                        proc.stdin.write((line_buffer + "\r\n").encode("utf-8"))
                        await proc.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    line_buffer = ""
                    continue

                line_buffer += message
                try:
                    proc.stdin.write(message.encode("utf-8"))
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    break
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    tasks = [
        asyncio.create_task(read_stdout()),
        asyncio.create_task(read_stderr()),
        asyncio.create_task(read_websocket()),
    ]

    try:
        await proc.wait()
    except Exception:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        if proc.returncode is None:
            try:
                proc.terminate()
                await proc.wait()
            except Exception:
                pass

        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    logger.info("Launching Uvicorn server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
