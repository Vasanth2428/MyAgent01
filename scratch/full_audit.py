import docx

doc = docx.Document("UPDATED REPORT.docx")

with open("scratch/full_audit.txt", "w", encoding="utf-8") as f:
    f.write(f"=== FULL DOCUMENT AUDIT ===\n")
    f.write(f"Total paragraphs: {len(doc.paragraphs)}\n")
    f.write(f"Total tables: {len(doc.tables)}\n\n")
    
    for idx, para in enumerate(doc.paragraphs):
        style = para.style.name if para.style else "Normal"
        text = para.text
        # Flag empty paragraphs, short stubs, and heading mismatches
        flags = []
        if not text.strip():
            flags.append("EMPTY")
        elif len(text.strip()) < 10 and style == "Body Text":
            flags.append("STUB")
        if style.startswith("Heading"):
            flags.append(f"H:{style}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        f.write(f"P[{idx}] ({style}){flag_str}: {text}\n")
    
    f.write(f"\n\n=== TABLES ===\n")
    for t_idx, table in enumerate(doc.tables):
        f.write(f"\n--- Table {t_idx+1}: {len(table.rows)}r x {len(table.columns)}c ---\n")
        for r_idx, row in enumerate(table.rows):
            cells = [cell.text.strip().replace("\n", " ")[:80] for cell in row.cells]
            f.write(f"  R{r_idx}: {cells}\n")

print("Full audit written to scratch/full_audit.txt")
