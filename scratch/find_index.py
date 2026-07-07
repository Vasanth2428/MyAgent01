import docx

doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)

keywords = ["hela", "tinospora", "cervical", "cancer", "mtt", "docking", "phytochemical", "berberine", "quercetin", "palmatine", "magnoflorine", "tinosporaside"]

for idx, para in enumerate(doc.paragraphs):
    text_lower = para.text.lower()
    for kw in keywords:
        if kw in text_lower:
            print(f"Index [{idx}] | Style: {para.style.name} | Text: {para.text[:80]}")
            break
print("Finished search.")
