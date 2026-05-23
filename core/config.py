"""
================================================================================
RAG CONTEXT ENGINE - CONFIGURATION
================================================================================
Centralized constants and tuning parameters for the entire pipeline.
Change values here instead of hunting through multiple files.
"""

# --- LLM ---
LLM_MODEL = "llama-3.1-8b-instant"
LLM_TEMPERATURE = 0.1
CONTEXT_WINDOW_LIMIT = 8192

# --- Embedding ---
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# --- Reranker ---
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# --- Retrieval ---
HYBRID_ALPHA_DEFAULT = 0.50
HYBRID_ALPHA_KEYWORD = 0.20
MAX_CANDIDATES = 12
DEFAULT_TOP_K = 5

# --- Token Budgets ---
TOTAL_CONTEXT_BUDGET = 1500       # Total tokens for memory + knowledge
MEMORY_TOKEN_BUDGET = 300         # Max tokens for conversation memory
MIN_KNOWLEDGE_BUDGET = 300        # Floor for knowledge even if memory is large
TOKENIZER_ENCODING = "cl100k_base"

# --- Compression ---
COMPRESSION_SCORE_THRESHOLD = 0.02
SAFETY_CHAR_LIMIT = 16000        # Hard character limit for Simple RAG mode

# --- Chunking ---
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

# --- Memory ---
MEMORY_DECAY_RATE = 0.1
MEMORY_WEIGHT_THRESHOLD = 0.1

# --- Database ---
DB_PATH = "memory.db"
HISTORY_LIMIT = 10

# --- HyDE ---
HYDE_MAX_TOKENS = 150
HYDE_TEMPERATURE = 0.3

# --- Query Expansion ---
EXPANSION_MIN_WORDS = 5           # Queries shorter than this skip expansion

# --- Cost (Groq Llama 3.1 8B Pricing) ---
COST_PER_INPUT_TOKEN = 0.05 / 1_000_000
COST_PER_OUTPUT_TOKEN = 0.08 / 1_000_000

# --- Conversation Budget ---
CONVERSATION_TOKEN_LIMIT = 15000  # Total token limit for the entire conversation session

# --- REACT AGENT ---
AGENT_CONFIG = {
    # Core behavior
    "max_iterations": 5,
    "default_llm_timeout_seconds": 30,
    
    # Tool timeouts (by tool type)
    "tool_timeouts": {
        "knowledge_base": 15,
        "web": 10,
        "web_fetch": 15,
        "system": 5,
        "chat": 5,
    },
    
    # Retry strategy
    "default_retry_count": 2,
    "retry_backoff_factor": 2.0,  # Exponential backoff multiplier
    "max_retry_delay_seconds": 10,
    
    # Input validation
    "max_query_length": 5000,
    "min_query_length": 1,
    "max_tool_arg_length": 1000,
    
    # Greeting detection
    "greeting_words": {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"},
    "conversational_words": {"hi", "hello", "hey", "thanks", "thank", "bye", "okay", "ok", "sure", "yes", "no", "please"},
    "short_chat_threshold": 2,  # Words <= this triggers early exit
    
    # Metrics
    "enable_metrics": True,
    "metrics_retention_limit": 100,  # Keep last N metric entries
}

