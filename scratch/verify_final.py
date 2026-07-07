"""Final verification: check for any remaining issues."""
import docx

doc = docx.Document("UPDATED REPORT.docx")

issues = []

# 1. Check biology keywords
bio_kw = ["hela", "tinospora", "cervical cancer", "mtt assay", "phytochemical", 
          "berberine", "quercetin", "palmatine", "magnoflorine", "tinosporaside",
          "formazan", "monolayer", "trypsin", "µg/ml"]
for idx, para in enumerate(doc.paragraphs):
    t = para.text.lower()
    for kw in bio_kw:
        if kw in t:
            issues.append(f"BIO_KEYWORD: P[{idx}] contains '{kw}': {para.text[:80]}")

# 2. Check for orphaned fragments (starts lowercase, not empty)
for idx, para in enumerate(doc.paragraphs):
    t = para.text.strip()
    if t and t[0].islower() and len(t) > 20 and para.style.name != "List Paragraph":
        issues.append(f"FRAGMENT: P[{idx}] starts lowercase: {t[:80]}")

# 3. Check ACKNOWLEDGEMENT heading
if doc.paragraphs[53].text.strip() != "ACKNOWLEDGEMENT":
    issues.append(f"HEADING: P[53] should be ACKNOWLEDGEMENT, got: {doc.paragraphs[53].text[:50]}")

# 4. Verify TOC chapter titles
toc = doc.tables[1]
expected_titles = [
    "Weekly Overview of Internship Activities",
    "Introduction",
    "System Architecture & Agent Design",
    "Methodology: Retrieval, Caching & Optimization Tools",
    "Results & Performance Benchmarks",
    "Diagnostics, Discussion & Analysis",
    "Conclusion and Future Scope",
    "PO & PSO Attainment",
    "Internship Completion Certificate"
]
for i, title in enumerate(expected_titles):
    actual = toc.rows[i+2].cells[1].text.strip()
    if actual != title:
        issues.append(f"TOC: Row {i+2} expected '{title}', got '{actual}'")

# 5. Check tables still intact
with open("scratch/verification_report.txt", "w", encoding="utf-8") as f:
    f.write(f"=== VERIFICATION REPORT ===\n")
    f.write(f"Paragraphs: {len(doc.paragraphs)}\n")
    f.write(f"Tables: {len(doc.tables)}\n\n")
    
    if not issues:
        f.write("STATUS: ALL CLEAN - No issues found!\n")
    else:
        f.write(f"STATUS: {len(issues)} issues found:\n\n")
        for issue in issues:
            f.write(f"  - {issue}\n")
    
    # Print key sections for spot-check
    key_paras = [53, 81, 83, 95, 97, 99, 104, 111, 146, 158, 168, 169, 170, 
                 193, 209, 250, 252, 259, 262, 264]
    f.write(f"\n=== KEY PARAGRAPH SPOT-CHECK ===\n")
    for idx in key_paras:
        if idx < len(doc.paragraphs):
            p = doc.paragraphs[idx]
            f.write(f"\nP[{idx}] ({p.style.name}): {p.text[:120]}\n")

print("Verification complete. Results in scratch/verification_report.txt")
