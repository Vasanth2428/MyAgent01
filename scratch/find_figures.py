import docx

doc = docx.Document("UPDATED REPORT.docx")

with open("scratch/figure_refs.txt", "w", encoding="utf-8") as f:
    for idx, para in enumerate(doc.paragraphs):
        t = para.text.strip()
        if "figure" in t.lower() or "fig." in t.lower():
            f.write(f"P[{idx}] ({para.style.name}): {t}\n")

print("Done. Figure references written to scratch/figure_refs.txt")
