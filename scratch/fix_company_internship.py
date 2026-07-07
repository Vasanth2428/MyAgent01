"""
Clean up college COE template artifacts in UPDATED REPORT.docx and UPDATED PPT.pptx.
Replaces COE Internship terms with Apphelix / Professional Internship terms,
and ensures Vasanth's name and register number are correctly reflected on the Certificate slide/page.
"""

import docx
import pptx
from pptx.util import Inches, Pt
import os

# ─────────────────────────────────────────────────────────────────────────────
# 1. Clean up Word Document
# ─────────────────────────────────────────────────────────────────────────────
doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)
print(f"Loaded: {len(doc.paragraphs)} paragraphs.")

# Let's replace systematically:
replacements = {
    "COE Internship Report": "Internship Report",
    "COE Internship": "Internship",
    "COE internship": "Internship",
    "COE INTERNSHIP": "INTERNSHIP",
    "HeLa Cell Assay": "Context Benchmarking",
    "HeLa cell assays": "Context Benchmarking",
}

for idx, p in enumerate(doc.paragraphs):
    t = p.text
    
    # Specific paragraph overrides to fix details
    if "VASANTHAVEL K" in t or "24CS1021" in t:
        p.text = (
            "This is to certify that the “Internship Report” Submitted by VASANTH S "
            "(Reg no: 210424104085) is work done by him and submitted during 2026-2027 academic year, "
            "in partial fulfilment of the requirements for the award of the degree of "
            "BACHELOR OF ENGINEERING in COMPUTER SCIENCE AND ENGINEERING, at CHENNAI INSTITUTE OF TECHNOLOGY."
        )
        print(f"Fixed P[{idx}] (Certificate page): Replaced with Vasanth's details.")
        continue

    if "giving me the opportunity to do an internship within the organization" in t:
        p.text = (
            "First, I would like to thank Chennai Institute of Technology and Apphelix for "
            "giving me the opportunity to do an internship at Apphelix."
        )
        print(f"Fixed P[{idx}] (Acknowledgement): Replaced with Apphelix reference.")
        continue
        
    if "complete internship in above said organization" in t:
        p.text = (
            "I would like to thank our internship coordinator and Ms. M. Selva Jothi (Year Coordinator, CSE) "
            "for their support and advice to complete this internship at Apphelix."
        )
        print(f"Fixed P[{idx}]: Replaced with Apphelix reference.")
        continue

    # Bulk text replacements
    changed = False
    for old, new in replacements.items():
        if old in t:
            t = t.replace(old, new)
            changed = True
            
    if changed:
        p.text = t
        print(f"Replaced text in P[{idx}]: {p.text[:80]}...")

# Save Word Doc
doc.save(doc_path)
print("✓ Word document updated.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Clean up PPT Slides
# ─────────────────────────────────────────────────────────────────────────────
ppt_path = "UPDATED PPT.pptx"
prs = pptx.Presentation(ppt_path)
print(f"\nLoaded PPT presentation. Total slides: {len(prs.slides)}")

for idx, slide in enumerate(prs.slides):
    print(f"Slide {idx+1}:")
    for shape in slide.shapes:
        if shape.has_text_frame:
            tf = shape.text_frame
            t = tf.text
            changed = False
            
            # Specific Slide 1 replacements
            if idx == 0:
                if "COE INTERNSHIP" in t:
                    t = t.replace("COE INTERNSHIP", "INTERNSHIP AT APPHELIX")
                    changed = True
                if "COE Internship" in t:
                    t = t.replace("COE Internship", "Apphelix Internship")
                    changed = True
            
            # Bulk replacements
            for old, new in replacements.items():
                if old in t:
                    t = t.replace(old, new)
                    changed = True
            
            if "COE" in t:
                t = t.replace("COE", "Apphelix")
                changed = True
                
            if changed:
                # Re-apply text and formatting
                tf.text = t
                # Reset font to be professional
                for p in tf.paragraphs:
                    p.font.name = "Calibri"
                print(f"  Shape [{shape.name}] text updated: {t.replace(chr(10), ' ')[:60]}...")

# Save PPT presentation
prs.save(ppt_path)
print("✓ PPT presentation updated.")
