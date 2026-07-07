"""
Insert generated figures into UPDATED REPORT.docx using a simpler approach.
Uses python-docx's built-in add_picture to create the image element properly,
then moves it to the correct position in the document.
"""

import docx
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import os

doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)

# Figure mapping: caption text prefix -> image file
figure_map = [
    ("Figure 4. Token load comparison", "scratch/fig2_token_savings.png"),
    ("Figure 5. Memory usage and query latency", "scratch/fig3_rag_pipeline.png"),
    ("Figure 5. (Heatmap)", "scratch/fig5_heatmap.png"),
    ("Figure 6. Diagram of agent coordination", "scratch/fig4_state_diagram.png"),
    ("Figure 7. Flowchart of state transitions", "scratch/fig1_architecture.png"),
]

# Additional figure to insert after heading
extra_figure = {
    "heading": "System Architecture & Agent Roles",
    "image": "scratch/fig1_architecture.png",
    "caption": "Figure 1. Multi-Agent System Architecture with Supervisor Routing Pattern"
}

def add_image_paragraph_before(doc, target_para, image_path, width=Inches(5.0)):
    """
    Add a centered image paragraph before target_para.
    Uses the approach of adding to the end, then moving the XML element.
    """
    # Add a paragraph with the picture at the end of the document
    new_para = doc.add_paragraph()
    run = new_para.add_run()
    run.add_picture(image_path, width=width)
    
    # Center align
    new_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Add spacing
    pPr = new_para._element.get_or_add_pPr()
    spacing = docx.oxml.OxmlElement('w:spacing')
    spacing.set(qn('w:before'), '120')
    spacing.set(qn('w:after'), '120')
    pPr.append(spacing)
    
    # Move the paragraph element to before the target paragraph
    target_para._element.addprevious(new_para._element)
    
    return new_para

def add_caption_paragraph_before(doc, target_para, caption_text):
    """Add an italic, centered caption paragraph before target_para."""
    new_para = doc.add_paragraph()
    run = new_para.add_run(caption_text)
    run.italic = True
    run.font.size = Pt(10)
    new_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Move before target
    target_para._element.addprevious(new_para._element)
    
    return new_para


inserted = 0

# 1. Insert figures before their existing captions
for caption_prefix, image_file in figure_map:
    found = False
    for idx, para in enumerate(doc.paragraphs):
        if para.text.strip().startswith(caption_prefix):
            if os.path.exists(image_file):
                add_image_paragraph_before(doc, para, image_file, width=Inches(5.0))
                inserted += 1
                print(f"[OK] Inserted {os.path.basename(image_file)} before: {para.text[:60]}...")
            else:
                print(f"[WARN] Image not found: {image_file}")
            found = True
            break
    if not found:
        print(f"[WARN] Caption not found: '{caption_prefix}'")

# 2. Insert Figure 1 (System Architecture) after the heading
heading_text = extra_figure["heading"]
image_file = extra_figure["image"]
caption_text = extra_figure["caption"]

for idx, para in enumerate(doc.paragraphs):
    if heading_text in para.text and para.style.name.startswith("Heading"):
        # Find the next paragraph after this heading
        if idx + 1 < len(doc.paragraphs):
            next_para = doc.paragraphs[idx + 1]
            
            if os.path.exists(image_file):
                # Insert caption first (it will appear after the image)
                add_caption_paragraph_before(doc, next_para, caption_text)
                # Then insert image (it will appear before the caption)
                add_image_paragraph_before(doc, doc.paragraphs[idx + 1], image_file, width=Inches(5.0))
                inserted += 1
                print(f"[OK] Inserted {os.path.basename(image_file)} + caption after '{heading_text}' heading")
        break

doc.save(doc_path)
print(f"\nDone! Inserted {inserted} figures into the report.")
