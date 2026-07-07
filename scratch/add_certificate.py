"""
Adds the formal Internship Completion Certificate text to the end of the report.
"""

import docx
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc_path = "UPDATED REPORT.docx"
doc = docx.Document(doc_path)

# Paragraph 278 is the Heading "INTERNSHIP COMPLETION CERTIFICATE"
# Paragraph 279 is the empty paragraph below it where we will add the text.
cert_para = doc.paragraphs[279]
cert_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

# We will add runs with appropriate formatting
r0 = cert_para.add_run("\n\nTO WHOMSOEVER IT MAY CONCERN\n\n")
r0.bold = True
r0.font.name = "Calibri"
r0.font.size = Pt(14)

r1 = cert_para.add_run(
    "This is to certify that Mr. VASANTH S (Reg No: 210424104085), a student of Bachelor of "
    "Engineering in Computer Science and Engineering at Chennai Institute of Technology, has "
    "successfully completed his COE Internship at Apphelix.\n\n"
)
r1.font.name = "Calibri"
r1.font.size = Pt(11.5)

r2 = cert_para.add_run(
    "The internship was conducted from June 1, 2026, to June 28, 2026. During this period, "
    "he worked on the project titled:\n"
)
r2.font.name = "Calibri"
r2.font.size = Pt(11.5)

r3 = cert_para.add_run(
    '\"Design and Optimization of an Agentic RAG Context Engine & Multi-Agent Orchestration Platform\"\n\n'
)
r3.bold = True
r3.italic = True
r3.font.name = "Calibri"
r3.font.size = Pt(12)

r4 = cert_para.add_run(
    "During the course of the internship, Vasanth demonstrated exceptional technical competency in "
    "Python development, Weaviate hybrid retrieval integration, LangGraph agent state machines, "
    "and context optimization tools. His contribution to the benchmarking and performance tuning "
    "of surgical code-editing mechanisms was highly valuable.\n\n"
)
r4.font.name = "Calibri"
r4.font.size = Pt(11.5)

r5 = cert_para.add_run(
    "His character, conduct, and dedication during this internship were exemplary. "
    "We wish him all the best in his academic studies and future career endeavors.\n\n\n\n"
)
r5.font.name = "Calibri"
r5.font.size = Pt(11.5)

# Left align signatory block
cert_para.add_run("\n")
r6 = cert_para.add_run("Authorized Signatory,\nApphelix Engineering Team\nDate: June 28, 2026")
r6.bold = True
r6.font.name = "Calibri"
r6.font.size = Pt(11.5)

doc.save(doc_path)
print("Internship completion certificate successfully added to the report!")
