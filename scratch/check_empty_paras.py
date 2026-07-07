import docx

doc = docx.Document("UPDATED REPORT.docx")

empty_indices = []
for idx, p in enumerate(doc.paragraphs):
    t = p.text.strip()
    if not t:
        empty_indices.append(idx)

print(f"Total empty paragraphs: {len(empty_indices)}")
print(f"Empty paragraph indices: {empty_indices[:50]}...")
