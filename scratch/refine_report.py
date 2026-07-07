"""
Refinement pass for UPDATED REPORT.docx
Fixes identified issues from the full audit:
  1. Restore ACKNOWLEDGEMENT heading (P[53])
  2. Fix awkward analogy paragraph (P[104])
  3. Remove leftover biology stub (P[146])
  4. Replace old biology list items (P[168-170])
  5. Fix dangling fragment (P[209])
  6. Fix heading that reads as body text (P[250])
  7. Promote orphaned section title (P[252])
  8. Fix fragment at P[262]
  9. Update Table of Contents (Table 2) chapter titles
  10. Update remaining generic PO/PSO justifications
"""

import docx

doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)
print(f"Loaded: {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables")

# ── 1. Restore ACKNOWLEDGEMENT heading (P[53]) ──────────────────────────
doc.paragraphs[53].text = "ACKNOWLEDGEMENT"
print("Fixed P[53]: Restored ACKNOWLEDGEMENT heading")

# ── 2. Fix awkward "oxidative stress" analogy (P[104]) ───────────────────
doc.paragraphs[104].text = (
    "Context bloating in agentic loops is a critical performance bottleneck. "
    "When the full contents of large files, verbose logs, and irrelevant code "
    "are injected into the LLM context window, the model loses focus on the "
    "target lines, produces lower-quality outputs, and incurs unnecessary API "
    "costs. By applying semantic compression filters and log output truncators, "
    "the system retains only the critical messages, preserving generation "
    "accuracy while significantly lowering token consumption."
)
print("Fixed P[104]: Removed awkward biology analogy")

# ── 3. Clear leftover biology stub (P[146]) ──────────────────────────────
doc.paragraphs[146].text = (
    "All benchmark results were analyzed using token counting utilities and "
    "latency profiling to determine the effectiveness of each optimization tool."
)
print("Fixed P[146]: Replaced leftover biology stub")

# ── 4. Replace old biology list items (P[168-170]) ───────────────────────
doc.paragraphs[168].text = (
    "For file reads under 500 tokens, the overhead of AST parsing is negligible "
    "and direct full-file reads remain acceptable."
)
doc.paragraphs[169].text = (
    "For files between 500 and 5,000 tokens, function-specific isolation via "
    "get_pruned_context provides the optimal balance of context and cost."
)
doc.paragraphs[170].text = (
    "For files exceeding 5,000 tokens, surgical header extraction "
    "(fetch_file_headers) is essential to prevent context window exhaustion."
)
print("Fixed P[168-170]: Replaced biology list items with token threshold analysis")

# ── 5. Fix dangling fragment (P[209]) ────────────────────────────────────
doc.paragraphs[209].text = (
    "These results strongly support the conclusion that token-optimized context "
    "engineering is essential for running software developer agents in production. "
    "Without surgical optimizations, agents quickly exhaust their context windows "
    "and trigger API rate limit failures, making iterative development infeasible."
)
print("Fixed P[209]: Completed dangling fragment into full sentence")

# ── 6. Fix heading that reads as body text (P[250]) ──────────────────────
doc.paragraphs[250].text = "System Reliability and Safety Analysis"
print("Fixed P[250]: Replaced body-text heading with proper section title")

# ── 7. Promote orphaned text to proper content (P[252]) ──────────────────
doc.paragraphs[252].text = (
    "System performance diagnostics were conducted during live API runs to "
    "identify and resolve integration issues. Three critical bugs were discovered "
    "and fixed: LLM provider API key cross-contamination causing 401 errors, "
    "directory safety guardrails rejecting legitimate sibling project folders, "
    "and a TypeError crash in the output caching layer caused by unhashable "
    "list types. Each fix was verified through end-to-end integration tests."
)
print("Fixed P[252]: Expanded orphaned title into diagnostic summary paragraph")

# ── 8. Fix dangling fragment (P[262]) ────────────────────────────────────
doc.paragraphs[262].text = (
    "The live debugging process validated the robustness of the platform by "
    "resolving provider key contamination (401 Authentication errors), extending "
    "directory safety guardrails for multi-repo workspaces, and fixing cache "
    "hashing crashes caused by unhashable list return types."
)
print("Fixed P[262]: Replaced fragment with complete diagnostic discussion paragraph")

# ── 9. Update Table of Contents (Table 2) ────────────────────────────────
toc = doc.tables[1]  # Table 2 (0-indexed: index 1)
toc_updates = {
    2: ("1.", "Weekly Overview of Internship Activities", "09"),
    3: ("2.", "Introduction", "10"),
    4: ("3.", "System Architecture & Agent Design", "11"),
    5: ("4.", "Methodology: Retrieval, Caching & Optimization Tools", "12"),
    6: ("5.", "Results & Performance Benchmarks", "20"),
    7: ("6.", "Diagnostics, Discussion & Analysis", "29"),
    8: ("7.", "Conclusion and Future Scope", "30"),
    9: ("8.", "PO & PSO Attainment", "31"),
    10: ("9.", "Internship Completion Certificate", "33"),
}
for row_idx, (chap, title, page) in toc_updates.items():
    if row_idx < len(toc.rows):
        toc.rows[row_idx].cells[0].text = chap
        toc.rows[row_idx].cells[1].text = title
        toc.rows[row_idx].cells[2].text = page
print("Fixed Table 2: Updated Table of Contents chapter titles")

# ── 10. Update remaining generic PO/PSO justifications (Table 9) ─────────
po_table = doc.tables[8]  # Table 9 (after Table 9 deletion, PO table is index 8)
po_justifications = {
    1: "Applied engineering principles of modular software design, state machines, and vector database indexing.",
    2: "Analyzed context window limitations, API cost structures, and token optimization trade-offs.",
    6: "The platform enables developers to build software faster, reducing time-to-market for applications.",
    8: "Ensured ethical AI practices including human-in-the-loop approval gates and path safety guardrails to prevent unauthorized file modifications.",
    9: "Individually developed the RAG engine, agent configurations, and benchmark scripts; collaborated with mentors on architecture decisions.",
    10: "Produced clear technical documentation, benchmark reports, and a web-based chat UI for effective communication of results.",
}
for row_idx, justification in po_justifications.items():
    if row_idx < len(po_table.rows):
        po_table.rows[row_idx].cells[3].text = justification
print("Fixed Table 9 (PO): Updated generic justifications")

# Update PO11/PO12 table (Table 10, index 9)
po2_table = doc.tables[9]
po2_table.rows[1].cells[3].text = (
    "Managed the project timeline across 4 weeks, balancing research, development, "
    "benchmarking, and documentation phases within budget constraints."
)
po2_table.rows[2].cells[3].text = (
    "Gained proficiency in LangGraph, Weaviate, FastAPI, and context engineering — "
    "skills that support continuous professional development in AI/ML engineering."
)
print("Fixed Table 10 (PO11-12): Updated justifications")

# ── 11. Fix section heading style for "Materials and Method" ─────────────
doc.paragraphs[111].text = "Materials and Methods"
print("Fixed P[111]: Corrected heading to 'Materials and Methods'")

# ── 12. Fix the Discussion heading to be a proper heading ────────────────
doc.paragraphs[259].text = "Discussion"
print("Fixed P[259]: Cleaned Discussion heading")

# ── Save ─────────────────────────────────────────────────────────────────
doc.save(doc_path)
print("\n✓ All refinements applied and saved successfully.")
