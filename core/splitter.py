"""
================================================================================
RAG CONTEXT ENGINE - SPLITTER MODULE
================================================================================
Recursive character-based text splitting to partition raw uploaded files
into semantically cohesive document chunks.
"""

import logging
from typing import List, Tuple
import tiktoken

from core.config import (
    CHUNK_SIZE, CHUNK_OVERLAP, PARENT_CHUNK_SIZE,
    CHILD_CHUNK_SIZE, CHILD_CHUNK_OVERLAP, TOKENIZER_ENCODING
)

logger = logging.getLogger("RAG.Splitter")


class RecursiveCharacterSplitter:
    """
    Splits text by looking at separators in priority order:
    paragraphs → newlines → sentences → spaces → characters.
    """

    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size
            if end >= text_len:
                chunks.append(text[start:])
                break

            # Try to find a good separator split point
            split_pos = -1
            for sep in self.separators:
                if sep == "":
                    split_pos = end
                    break
                pos = text.rfind(sep, start, end)
                if pos != -1 and pos >= start + self.overlap:
                    split_pos = pos + len(sep)
                    break

            chunks.append(text[start:split_pos])
            start = split_pos - self.overlap
            if start < 0:
                start = split_pos

        return chunks


class ParentChildSplitter:
    """
    Splits text into parent chunks (~1500 tokens) and child chunks (~300 tokens)
    with an overlap (~50 tokens).
    """

    def __init__(
        self,
        parent_size: int = PARENT_CHUNK_SIZE,
        child_size: int = CHILD_CHUNK_SIZE,
        child_overlap: int = CHILD_CHUNK_OVERLAP
    ):
        self.parent_size = parent_size
        self.child_size = child_size
        self.child_overlap = child_overlap
        self.tokenizer = tiktoken.get_encoding(TOKENIZER_ENCODING)

    def split_by_tokens(self, text: str, max_tokens: int, overlap_tokens: int = 0) -> List[str]:
        """Helper to split string raw text into chunks of exact token counts."""
        tokens = self.tokenizer.encode(text)
        if not tokens:
            return []
        
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunks.append(self.tokenizer.decode(chunk_tokens))
            if end == len(tokens):
                break
            start = end - overlap_tokens
            if start >= end:
                start = end - 1
        return chunks

    def split_into_parents(self, text: str) -> List[str]:
        """
        Splits document text into parents of self.parent_size tokens,
        respecting paragraph and sentence boundaries where possible.
        """
        paragraphs = text.split("\n\n")
        parents = []
        current_chunks = []
        current_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_tokens = len(self.tokenizer.encode(para))
            if para_tokens > self.parent_size:
                # If we have accumulated previous paragraphs, save them
                if current_chunks:
                    parents.append("\n\n".join(current_chunks))
                    current_chunks = []
                    current_tokens = 0
                
                # Split large paragraph by sentences
                sentences = para.split(". ")
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    sent_tokens = len(self.tokenizer.encode(sent))
                    if sent_tokens > self.parent_size:
                        # Split sentence directly by tokens
                        token_chunks = self.split_by_tokens(sent, self.parent_size, overlap_tokens=100)
                        parents.extend(token_chunks)
                    else:
                        if current_tokens + sent_tokens > self.parent_size:
                            parents.append(". ".join(current_chunks) + ".")
                            current_chunks = [sent]
                            current_tokens = sent_tokens
                        else:
                            current_chunks.append(sent)
                            current_tokens += sent_tokens
            else:
                if current_tokens + para_tokens > self.parent_size:
                    parents.append("\n\n".join(current_chunks))
                    current_chunks = [para]
                    current_tokens = para_tokens
                else:
                    current_chunks.append(para)
                    current_tokens += para_tokens

        if current_chunks:
            parents.append("\n\n".join(current_chunks))
        return parents

    def split_text(self, text: str) -> List[Tuple[str, List[str]]]:
        """
        Splits raw text into a list of (parent_text, child_texts) pairs.
        """
        if not text or not text.strip():
            return []

        parents = self.split_into_parents(text)
        pairs = []
        for parent in parents:
            children = self.split_by_tokens(parent, self.child_size, overlap_tokens=self.child_overlap)
            if children:
                pairs.append((parent, children))
        return pairs
