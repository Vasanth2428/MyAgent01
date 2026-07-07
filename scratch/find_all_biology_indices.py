import docx

doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)

keywords = ["hela", "tinospora", "cervical", "cancer", "mtt", "docking", "phytochemical", "berberine", "quercetin", "palmatine", "magnoflorine", "tinosporaside", "cox-2", "caspase-3"]

with open("scratch/biology_indices.txt", "w", encoding="utf-8") as f:
    for idx, para in enumerate(doc.paragraphs):
        text_lower = para.text.lower()
        for kw in keywords:
            if kw in text_lower:
                f.write(f"Index [{idx}] | Style: {para.style.name} | Keyword: {kw} | Text: {para.text[:120]}\n")
                break
print("Done. Output written to scratch/biology_indices.txt")
