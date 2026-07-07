import docx

doc = docx.Document("UPDATED REPORT.docx")

with open("scratch/coe_occurrences.txt", "w", encoding="utf-8") as f:
    for idx, p in enumerate(doc.paragraphs):
        if "coe" in p.text.lower() or "within the organization" in p.text.lower():
            f.write(f"P[{idx}]: {p.text}\n")

print("COE search written to scratch/coe_occurrences.txt")
