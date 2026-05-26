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
import csv
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
from fastapi import FastAPI, HTTPException, UploadFile, File, Security, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Literal, Optional
from pypdf import PdfReader
from dotenv import load_dotenv

from core.config import CHUNK_SIZE, CHUNK_OVERLAP
from core.retriever import WeaviateRetriever
from core.engine import AgenticSystem
from core.splitter import RecursiveCharacterSplitter, ParentChildSplitter


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
# Security / API Key Verification
# ------------------------------------------------------------------

api_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_bearer = HTTPBearer(auto_error=False)

async def verify_api_key(
    x_api_key: Optional[str] = Security(api_header),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(api_bearer)
):
    expected_key = os.getenv("RAG_API_KEY", "rag-admin-secret-key-2026")
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif auth:
        token = auth.credentials.strip()
        
    logger.info(f"verify_api_key: token={'[PRESENT]' if token else '[MISSING]'}, length={len(token) if token else 0}")
    if not token or token != expected_key:
        logger.warning(f"API Authentication failed: received={token!r}, expected={expected_key!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key."
        )


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
async def query_rag(request: QueryRequest, auth: None = Depends(verify_api_key)):
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
async def query_rag_stream(request: QueryRequest, auth: None = Depends(verify_api_key)):
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


def parse_csv_to_parent_child_pairs(csv_content: str, filename: str) -> list:
    f = io.StringIO(csv_content)
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames or []
    
    # Clean fieldnames (strip whitespace)
    fieldnames = [field.strip() for field in fieldnames]
    
    # Identify if it matches our standard schemas
    is_customers = all(h in fieldnames for h in ["customer_id", "customer_name", "email"])
    is_products = all(h in fieldnames for h in ["product_id", "product_name", "category"])
    is_orders = all(h in fieldnames for h in ["order_id", "customer_id", "order_date", "shipping_cost"])
    is_order_items = all(h in fieldnames for h in ["order_item_id", "order_id", "product_id", "total_price"])
    
    pairs = []
    
    for row in reader:
        # Strip keys and values
        clean_row = {k.strip() if k else "": v.strip() if v else "" for k, v in row.items()}
        
        if is_customers:
            try:
                p_key = int(clean_row["customer_id"])
            except Exception:
                p_key = clean_row.get("customer_id", "unknown")
            text = (
                f"Customer {clean_row.get('customer_name', 'Unknown')} (ID: {p_key}) "
                f"has email {clean_row.get('email', 'N/A')}. Resides in {clean_row.get('city', 'N/A')}, "
                f"{clean_row.get('state', 'N/A')}, {clean_row.get('country', 'N/A')}. "
                f"Segment: {clean_row.get('customer_segment', 'N/A')}. Signed up on {clean_row.get('signup_date', 'N/A')}."
            )
        elif is_products:
            try:
                p_key = int(clean_row["product_id"])
            except Exception:
                p_key = clean_row.get("product_id", "unknown")
            try:
                unit_price = float(clean_row["unit_price"])
                price_str = f"${unit_price:.2f}"
            except Exception:
                price_str = clean_row.get("unit_price", "N/A")
            try:
                stock_quantity = int(clean_row["stock_quantity"])
                stock_str = f"{stock_quantity} units"
            except Exception:
                stock_str = clean_row.get("stock_quantity", "N/A")
                
            text = (
                f"Product {clean_row.get('product_name', 'Unknown')} (ID: {p_key}) "
                f"is in category {clean_row.get('category', 'N/A')}. Unit price: {price_str}. "
                f"Supplier: {clean_row.get('supplier', 'N/A')}. Stock quantity: {stock_str}."
            )
        elif is_orders:
            try:
                p_key = int(clean_row["order_id"])
            except Exception:
                p_key = clean_row.get("order_id", "unknown")
            try:
                cust_id = int(clean_row["customer_id"])
            except Exception:
                cust_id = clean_row.get("customer_id", "unknown")
            try:
                shipping_cost = float(clean_row["shipping_cost"])
                shipping_str = f"${shipping_cost:.2f}"
            except Exception:
                shipping_str = clean_row.get("shipping_cost", "N/A")
                
            text = (
                f"Order ID {p_key} was placed on {clean_row.get('order_date', 'N/A')} "
                f"by Customer ID {cust_id}. Region: {clean_row.get('region', 'N/A')}, "
                f"Channel: {clean_row.get('sales_channel', 'N/A')}, Payment: {clean_row.get('payment_method', 'N/A')}, "
                f"Status: {clean_row.get('order_status', 'N/A')}. Shipping cost: {shipping_str}."
            )
        elif is_order_items:
            try:
                p_key = int(clean_row["order_item_id"])
            except Exception:
                p_key = clean_row.get("order_item_id", "unknown")
            try:
                ord_id = int(clean_row["order_id"])
            except Exception:
                ord_id = clean_row.get("order_id", "unknown")
            try:
                prod_id = int(clean_row["product_id"])
            except Exception:
                prod_id = clean_row.get("product_id", "unknown")
            try:
                quantity = int(clean_row["quantity"])
                qty_str = str(quantity)
            except Exception:
                qty_str = clean_row.get("quantity", "N/A")
            try:
                unit_price = float(clean_row["unit_price"])
                price_str = f"${unit_price:.2f}"
            except Exception:
                price_str = clean_row.get("unit_price", "N/A")
            try:
                discount_percent = float(clean_row["discount_percent"])
                disc_str = f"{discount_percent}%"
            except Exception:
                disc_str = clean_row.get("discount_percent", "N/A")
            try:
                total_price = float(clean_row["total_price"])
                total_str = f"${total_price:.2f}"
            except Exception:
                total_str = clean_row.get("total_price", "N/A")
                
            text = (
                f"Order Item ID {p_key} is part of Order ID {ord_id}. "
                f"Product ID: {prod_id}, Quantity: {qty_str}, "
                f"Unit price: {price_str}, Discount: {disc_str}, "
                f"Total price: {total_str}."
            )
        else:
            # Generic CSV mapping
            row_description = ", ".join(f"{k}: {v}" for k, v in clean_row.items() if k)
            text = f"Record in {filename}: {row_description}"
            
        pairs.append((text, [text]))
        
    return pairs


@app.post("/upload")
async def upload_document(file: UploadFile = File(...), auth: None = Depends(verify_api_key)):
    """
    Handles file uploads, extracts text, and indexes it into the vector store.
    Supports PDF, TXT, and CSV.
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
        
        # Identify file type based on magic bytes / extension
        is_pdf = first_chunk.startswith(b"%PDF")
        is_csv = filename.lower().endswith(".csv")
        is_txt = False
        
        if not is_pdf and not is_csv:
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
        elif is_csv:
            logger.info(f"File extension verified: CSV file detected for {filename}")
        elif is_txt:
            logger.info(f"Magic bytes verified: Plain text file detected for {filename}")
        else:
            raise HTTPException(
                status_code=400, 
                detail="Unsupported or invalid file format. Only valid PDF, UTF-8 TXT, and CSV files are allowed."
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
        parent_child_pairs = []
        is_csv_processed = False

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
        elif is_csv:
            try:
                csv_content = file_bytes.decode("utf-8")
                parent_child_pairs = parse_csv_to_parent_child_pairs(csv_content, filename)
                is_csv_processed = True
            except UnicodeDecodeError as csv_dec_err:
                logger.error(f"Failed to decode CSV file as UTF-8: {csv_dec_err}")
                raise HTTPException(
                    status_code=400,
                    detail="Failed to decode CSV file as UTF-8."
                )
            except Exception as csv_err:
                logger.error(f"Failed to parse CSV file: {csv_err}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to parse CSV file: {str(csv_err)}"
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

        if not is_csv_processed:
            if not content.strip():
                raise HTTPException(status_code=400, detail="File content is empty or contains no extractable text.")

            splitter = ParentChildSplitter()
            parent_child_pairs = splitter.split_text(content)

        # Count total children for logging
        total_children = sum(len(children) for _, children in parent_child_pairs)
        logger.info(f"Generated {len(parent_child_pairs)} parent chunks and {total_children} child chunks. Indexing...")
        await asyncio.to_thread(retriever.add_parent_child_documents, parent_child_pairs, source=filename)

        return {"status": "success", "message": f"Indexed {len(parent_child_pairs)} parent and {total_children} child chunks from {filename}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats(auth: None = Depends(verify_api_key)):
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
async def get_session_history(session_id: str, auth: None = Depends(verify_api_key)):
    """Retrieves conversation history for a specific session."""
    if not rag:
        raise HTTPException(status_code=500, detail="Engine not ready")
    return rag.persistent_memory.get_history(session_id)


if __name__ == "__main__":
    import uvicorn
    if not os.getenv("RAG_API_KEY"):
        logger.warning("RAG_API_KEY environment variable is not set. Defaulting to 'rag-admin-secret-key-2026' for verification.")
    logger.info("Launching Uvicorn server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
