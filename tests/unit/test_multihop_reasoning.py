import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.core.engine import RAGContextEngine
from src.core.config import PipelineConfig