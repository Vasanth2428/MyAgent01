import os
import docx

doc_path = "UPDATED REPORT.docx"

if not os.path.exists(doc_path):
    print(f"Error: {doc_path} not found.")
    exit(1)

doc = docx.Document(doc_path)
print(f"Loaded report with {len(doc.paragraphs)} paragraphs.")

# Define substring mappings for precise replacements
substring_replacements = {
    "Anticancer Activity of Tinospora cordifolia on HeLa Cells: An In Vitro and In Silico Study": 
        "Design and Optimization of an Agentic RAG Context Engine & Multi-Agent Orchestration Platform",
        
    "The selection of phytochemical ligands was based on extensive phytochemical profiling of Tinospora":
        "The selection of agent configurations was based on the required roles and LLM capacities. The Supervisor and Web Searcher agents use gpt-4o-mini to minimize costs, while the Coding Worker uses gemini-2.5-flash to support complex, multi-file surgical editing.",
        
    "The molecular structures of all selected phytochemicals were retrieved from the PubChem database":
        "The agent parameters were retrieved from config/.env to initialize the LangGraph workspace. The state saver checkpointing enables persistence, allowing the agentic pipeline to resume seamlessly after completing user approval check gates.",
        
    "the Protein Data Bank (PDB) in their experimentally determined crystallographic forms. Upon retrieval, each protein":
        "The system components represent the core libraries and tools involved in the context engine. These include the weaviate-client for vector search, flashrank for cross-encoder reranking, and langgraph for supervisor state coordination.",
        
    "Table 3. Effect of Tinospora cordifolia extract on HeLa cell viability":
        "Table 6. Token Savings achieved via Context Compression & Truncation",
        
    "quantitative data from the MTT assay and qualitative microscopic observations confirm":
        "The comparative token saving metrics demonstrate that surgical context engineering (such as fetch_file_headers and apply_surgical_edit) drastically reduces input and output sizes, enabling fast execution and low API costs.",
        
    "strongly support the idea that Tinospora cordifolia contains structurally diverse phytochemicals":
        "strongly support the conclusion that token-optimized context engineering is essential for running software developer agents in production, preventing rate limit failures and context window exhaustion.",
        
    "berberine likewise places its aromatic surface adjacent to conserved aromatic residues producing":
        "The Supervisor agent routes queries by matching user intents to specialized tools. When a coding query is detected, the workflow branches to the Coding Worker to write or modify workspace files.",
        
    "Quercetin’s binding is dominated by its polyhydroxylated flavonoid scaffold, which enables":
        "The Coding Worker's execution is guided by strict coding prompts, enabling the agent to output search-and-replace target blocks rather than rewriting the entire source file.",
        
    "with residues such as Asn49, Glu26 or analogous polar side chains, and also engages in edge-to-face":
        "The Critic Worker validates the modified code by checking syntax correctness and running unit tests, routing errors back to the Coding Worker if modifications fail.",
        
    "Palmatine, structurally related to berberine, shows a mixture of":
        "The Web Searcher agent fetches live data via Tavily and parses URL contents to resolve documentation references, providing external knowledge to the RAG loop.",
        
    "Magnoflorine and tinosporaside exhibit shallower pocket insertion and fewer aromatic stacking":
        "The Utility Worker handles calculations and summarizes session histories, enabling the Supervisor to maintain a compact state context across multiple turns.",
        
    "interactions with nonpolar residues while forming fewer hydrogen bonds compared to quercetin or berberine. Palmatine":
        "The generated applications are styled using modern design tokens, implementing Outfit/Inter typography, linear gradients, card layouts, and responsive grids.",
        
    "This multi-dimensional inhibitory pattern underscores the therapeutic relevance of phytochemicals and supports the":
        "This multi-agent coordination workflow demonstrates that isolating developer tasks into collaborative nodes significantly improves code quality and execution safety.",
        
    "The combined figure 8 illustrates the detailed molecular interactions of four major phytochemicals":
        "The benchmark results illustrate the efficiency of surgical tools, comparing token consumption and execution latency between optimized and traditional pipelines.",
        
    "binding affinity toward key proteins involved in cervical cancer progression, including HPV16 E6, HPV18 E7, COX-2, and":
        "the diagnostic resolutions of provider key contamination, directory safety guardrails, and caching list type unhashable errors.",
        
    "Although the present findings are limited to in-vitro and computational analyses, they establish a robust":
        "Although the current system is evaluated on python-based codebases, the architectural patterns can be extended to other programming languages and multi-repo setups."
}

updated_count = 0
for idx, para in enumerate(doc.paragraphs):
    text = para.text
    for target, replacement in substring_replacements.items():
        if target in text:
            para.text = text.replace(text, replacement)
            print(f"Replaced Para [{idx}] matching '{target[:30]}...'")
            updated_count += 1
            break

doc.save(doc_path)
print(f"Replacements applied successfully. Total paragraphs updated: {updated_count}")
