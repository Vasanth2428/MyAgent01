import os
from dotenv import load_dotenv
load_dotenv()

from core.retriever import WeaviateRetriever

try:
    retriever = WeaviateRetriever()
    print("Connected to Weaviate.")
    
    try:
        agg = retriever.collection.aggregate.over_all(group_by="source")
        print("Aggregation grouped by source succeeded!")
        for group in agg.groups:
            print("Group key:", group.grouped_by.value, "Count:", group.total_count)
    except Exception as ae:
        print("Aggregation failed:", ae)
        
    retriever.close()
except Exception as e:
    print("Error:", e)
