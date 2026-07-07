import docx

doc = docx.Document("UPDATED REPORT.docx")

for idx, p in enumerate(doc.paragraphs):
    if "live debugging process" in p.text:
        print(f"P[{idx}]: {p.text[:100]}")
