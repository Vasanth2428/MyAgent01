"""Final cleanup pass: fix the 4 remaining issues."""
import docx

doc = docx.Document("UPDATED REPORT.docx")

# Issue 1 & 2: P[171] and P[172] still contain biology µg/mL content
# These were the OLD P[169] and P[170] that shifted after the table deletion
# Let's find them by content match instead of index
fixed = 0
for idx, para in enumerate(doc.paragraphs):
    t = para.text.strip()
    
    # Fix leftover biology list items about µg/mL
    if "At 25 and 50 µg/mL, viability falls" in t:
        para.text = (
            "For files between 500 and 5,000 tokens, function-specific isolation via "
            "get_pruned_context provides the optimal balance of context and cost."
        )
        fixed += 1
        print(f"Fixed P[{idx}]: Replaced biology µg/mL list item")
        
    elif "At 100 and 200 µg/mL, the viability drops" in t:
        para.text = (
            "For files exceeding 5,000 tokens, surgical header extraction "
            "(fetch_file_headers) is essential to prevent context window exhaustion."
        )
        fixed += 1
        print(f"Fixed P[{idx}]: Replaced biology µg/mL list item")
    
    # Issue 3: Fragment starting "strongly support the conclusion..."
    elif t.startswith("strongly support the conclusion"):
        para.text = (
            "These results strongly support the conclusion that token-optimized context "
            "engineering is essential for running software developer agents in production. "
            "Without surgical optimizations, agents quickly exhaust their context windows "
            "and trigger API rate limit failures, making iterative development infeasible."
        )
        fixed += 1
        print(f"Fixed P[{idx}]: Capitalized and completed fragment")
    
    # Issue 4: Fragment starting "the diagnostic resolutions..."
    elif t.startswith("the diagnostic resolutions of provider"):
        para.text = (
            "The live debugging process validated the robustness of the platform by "
            "resolving provider key contamination (401 Authentication errors), extending "
            "directory safety guardrails for multi-repo workspaces, and fixing cache "
            "hashing crashes caused by unhashable list return types."
        )
        fixed += 1
        print(f"Fixed P[{idx}]: Capitalized and completed fragment")

    # Also fix P[264] which showed empty in spot-check (Conclusion heading)
    elif idx == 264 and para.style.name.startswith("Heading") or (idx == 264 and not t):
        # Check if it's the Conclusion heading that got blanked
        pass  # Leave as-is if empty, it's a spacer

# Also check P[264] explicitly
p264 = doc.paragraphs[264]
if not p264.text.strip() and p264.style.name.startswith("Heading"):
    p264.text = "Conclusion and Future Scope"
    print("Fixed P[264]: Restored Conclusion heading")

doc.save("UPDATED REPORT.docx")
print(f"\nDone. Fixed {fixed} issues total.")
