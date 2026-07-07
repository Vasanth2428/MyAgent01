"""
Fix and clean the paragraph structure at the end of the report (P[250] to P[270]).
Ensures headings, body text, and Discussion section flow logically without duplication.
"""

import docx

doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)

# Let's inspect the paragraphs in the range and replace them precisely.
# We will do this by clear-and-set to avoid styling issues.

# Define the new text sequence for P[250] through P[271]
new_paragraphs = {
    250: ("System Reliability and Safety Analysis", "Heading 7"),
    251: ("A core focus of the multi-agent orchestration platform is maintaining high reliability and preventing unauthorized operations. To achieve this, safety guardrails are integrated into the execution graph. Path validation restricts coding worker edits to approved workspace root paths. In addition, the human-in-the-loop (HITL) check gate pauses execution before code generation and presents diff changes to the user for approval.", "Body Text"),
    252: ("", "Body Text"),  # Empty spacer
    253: ("", "Normal"),     # Empty spacer
    254: ("", "Body Text"),  # Empty spacer
    255: ("", "Body Text"),  # Empty spacer
    256: ("", "Normal"),     # Empty spacer
    257: ("System Performance Diagnostics", "Heading 7"),
    258: ("", "Body Text"),  # Empty spacer
    259: ("System performance diagnostics were conducted during live API runs to identify and resolve integration issues. Three critical bugs were discovered and fixed: LLM provider API key cross-contamination causing 401 errors, directory safety guardrails rejecting legitimate sibling project folders, and a TypeError crash in the output caching layer caused by unhashable list types. Each fix was verified through end-to-end integration tests.", "Normal"),
    260: ("Discussion: Trade-Offs and Architectural Recommendations", "Heading 7"),
    261: ("", "Body Text"),  # Empty spacer
    262: ("The findings suggest that context engineering is as important as model capacity for developer agents. Surgical edits not only save API spend but also decrease user waiting times from 30s to under 1s. We recommend utilizing AST-based signatures by default for dependency analyses. The live debugging process validated the robustness of the platform by resolving provider key contamination (401 Authentication errors), extending directory safety guardrails for multi-repo workspaces, and fixing cache hashing crashes caused by unhashable list return types.", "Body Text"),
    263: ("", "Body Text"),  # Empty spacer
    264: ("Conclusion and Future Scope", "Heading 7"),
    265: ("In conclusion, the Modular RAG Context Engine and Multi-Agent Orchestration Platform successfully solves context bloat in agentic software development, achieving up to 99.79% token savings. Future work will implement knowledge graph traversing for multi-hop reasoning. Although the current system is evaluated on python-based codebases, the architectural patterns can be extended to other programming languages and multi-repo setups.", "Body Text"),
    266: ("", "Body Text"),  # Empty spacer
    267: ("", "Body Text"),  # Empty spacer
    268: ("PO & PSO Attainment", "Heading 4"),
    269: ("The student's performance and attainment of Program Outcomes (POs) and Program Specific Outcomes (PSOs) during the COE internship are evaluated and documented in this section. The tables below outline the attainment status and engineering justifications for each criteria.", "Body Text"),
    270: ("", "Body Text"),  # Empty spacer
}

for idx, (text, style_name) in new_paragraphs.items():
    if idx < len(doc.paragraphs):
        p = doc.paragraphs[idx]
        p.text = text
        if style_name:
            try:
                p.style = style_name
            except Exception as e:
                print(f"Could not apply style {style_name} to P[{idx}]: {e}")
        print(f"Updated P[{idx}] -> style: {p.style.name}, text: {repr(p.text[:60])}")

doc.save(doc_path)
print("\n✓ End sections cleaned and saved successfully!")
